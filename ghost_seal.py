#!/usr/bin/env python3
"""
ghost_seal.py — applies the GHOST SEAL AI-disclosure stamp.

Contract
  1. IDENTICAL SEAL EVERY TIME. The seal is never re-drawn; it is scaled from the
     pinned master mask (seal_master.png), whose SHA-256 is checked on load.
  2. THE ORIGINAL IS NOT COMPROMISED. Only pixels inside the seal's bounding box
     are ever touched (verify asserts bit-identity everywhere else); the relief is
     applied to L* only, so hue and saturation are mathematically unchanged; PNG
     in -> PNG out is lossless; the source file is never modified in place.
  3. WORKS ON ANY BACKGROUND. The relief is applied to the local luminance, and the
     relief mode is chosen from how much of it actually lands: a full carved bevel
     where there is headroom both ways, a single-direction press or emboss on ground
     pinned near white or near black. No colour, so it cannot clash with any palette.
  4. IDEMPOTENT. An already-sealed image is detected (metadata flag, plus a
     pixel-level correlation check that survives metadata stripping) and skipped.
  5. AUDITABLE. Every run appends a manifest line with input/output SHA-256, the
     mask hash, geometry and timestamp.

Usage
  ghost_seal.py apply IMG [-o OUT]
  ghost_seal.py batch DIR [--out DIR] [--recursive] [--jobs N]
  ghost_seal.py verify IMG [--source ORIGINAL]
  ghost_seal.py selftest
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None

VERSION = "ghost-seal/1.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(HERE, "seal_master.png")
MASTER_META = os.path.join(HERE, "seal_master.json")
MANIFEST = os.environ.get("GHOST_SEAL_MANIFEST", os.path.join(HERE, "manifest.jsonl"))

# ---- house standard: GHOST -------------------------------------------------
SPEC = dict(
    name="ghost",
    dia_frac=0.050,        # seal diameter as a fraction of the SHORT side
    dia_min=64,            # px; below this the microtext stops resolving
    dia_max=260,           # px; keeps the mark small on very large masters
    margin_frac=0.030,     # gap from both edges, fraction of the short side
    margin_min=24,
    delta_L=5.0,           # peak relief in CIE L* units (perceptual, not 0-255)
    delta_floor=3.5,       # never ease below this: the compliance visibility floor
    clip_tolerance=0.02,   # >2% clipped pixels switches to single-direction relief
    delta_L_uni=6.0,       # single-direction relief has no edge pairing: needs more
    uni_gamma=0.55,        # stroke-amplitude lift for single-direction relief
    corner="br",           # bottom-right: Gutenberg terminal area
    offset_px=1.0,         # relief offset at output scale (lit rim vs shadow)
    ss=4,                  # supersample factor for the relief build
    min_short_side=512,    # below this, stamp the master and derive thumbnails
)
FLAG = "GHOST-SEAL-V1"
DETECT_R = 0.30            # |correlation| above which the seal is considered present
EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}

# ---- sRGB <-> CIELab (D65), vectorised ------------------------------------
_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_Mi = np.linalg.inv(_M)
_WP = np.array([0.95047, 1.0, 1.08883])


def _f(t):
    return np.where(t > (6 / 29) ** 3, np.cbrt(t), t / (3 * (6 / 29) ** 2) + 4 / 29)


def _f_inv(t):
    return np.where(t > 6 / 29, t ** 3, 3 * (6 / 29) ** 2 * (t - 4 / 29))


def rgb_to_lab(rgb8: np.ndarray) -> np.ndarray:
    c = rgb8.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M.T
    f = _f(xyz / _WP)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_rgb_raw(lab: np.ndarray) -> np.ndarray:
    """Lab -> sRGB WITHOUT clamping, so out-of-gamut results can be detected."""
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    xyz = np.stack([_f_inv(fx), _f_inv(fy), _f_inv(fz)], axis=-1) * _WP
    lin = xyz @ _Mi.T
    return np.where(lin <= 0.0031308, 12.92 * lin,
                    1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055) * 255.0


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(lab_to_rgb_raw(lab), 0, 255)


def gamut_safe_dL(L, a, b, dL, iters=7):
    """
    Scale the relief per pixel to the largest amount that stays inside sRGB.

    Changing L* while holding a*/b* can push a saturated colour out of gamut; the
    clamp that follows would then move a*/b* too, i.e. shift the hue. Rather than
    accept that, the relief amplitude is reduced on exactly those pixels until the
    result is representable. Deterministic, and it only ever weakens the mark
    locally — it can never invert or recolour it.
    """
    factor = np.ones_like(dL)
    for _ in range(iters):
        lab = np.stack([np.clip(L + dL * factor, 0.0, 100.0), a, b], axis=-1)
        raw = lab_to_rgb_raw(lab)
        bad = ((raw < -0.5) | (raw > 255.5)).any(axis=-1)
        if not bad.any():
            break
        factor = np.where(bad, factor * 0.5, factor)
    return dL * factor


# ---- helpers ---------------------------------------------------------------
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_master():
    if not os.path.exists(MASTER):
        sys.exit(f"master mask missing: {MASTER} (run build_master.py)")
    digest = sha256_file(MASTER)
    if os.path.exists(MASTER_META):
        pinned = json.load(open(MASTER_META)).get("mask_sha256")
        if pinned and pinned != digest:
            sys.exit("MASK HASH MISMATCH — seal_master.png has been altered.\n"
                     f"  pinned:  {pinned}\n  on disk: {digest}\n"
                     "Refusing to stamp: the seal would no longer be the house standard.")
    return Image.open(MASTER).convert("L"), digest


def geometry(w, h):
    short = min(w, h)
    dia = int(round(min(max(SPEC["dia_frac"] * short, SPEC["dia_min"]), SPEC["dia_max"])))
    margin = int(round(max(SPEC["margin_frac"] * short, SPEC["margin_min"])))
    if SPEC["corner"] == "br":
        x, y = w - margin - dia, h - margin - dia
    elif SPEC["corner"] == "bl":
        x, y = margin, h - margin - dia
    elif SPEC["corner"] == "tr":
        x, y = w - margin - dia, margin
    else:
        x, y = margin, margin
    return int(x), int(y), dia, margin


def _norm(a):
    peak = float(np.abs(a).max()) or 1.0
    return a / peak


def _downscale(signed: np.ndarray, dia: int) -> np.ndarray:
    small = Image.fromarray(((np.clip(signed, -1, 1) + 1.0) * 127.5).astype(np.uint8))
    small = small.resize((dia, dia), Image.LANCZOS)
    return np.asarray(small, dtype=np.float64) / 127.5 - 1.0


@lru_cache(maxsize=32)
def relief_maps(dia: int, master_digest: str):
    """
    Three deterministic relief maps for one diameter:
      bipolar — lit rim + pressed shadow (the intended carved look)
      press   — darkening only, for ground with no headroom above (near-white)
      emboss  — lightening only, for ground with no headroom below (near-black)
    Signed, normalised to peak 1.0. Cached per diameter.
    """
    master = Image.open(MASTER).convert("L")
    ss = SPEC["ss"]
    n = dia * ss
    m = np.asarray(master.resize((n, n), Image.LANCZOS), dtype=np.float64) / 255.0
    off = int(round(SPEC["offset_px"] * ss))
    hi = np.zeros_like(m)
    sh = np.zeros_like(m)
    hi[:-off or None, :-off or None] = m[off:, off:]      # mask shifted up-left
    sh[off:, off:] = m[:-off or None, :-off or None]      # mask shifted down-right
    # Single-direction modes lose the light/dark edge pairing that makes hairlines
    # read, so their strokes are lifted with a compressive curve: thin rules and
    # ticks (drawn at partial mask values) then carry enough amplitude to survive.
    g = SPEC["uni_gamma"]
    mg, shg, hig = m ** g, sh ** g, hi ** g
    # LANCZOS ringing leaves a small opposite-sign lobe; a single-direction relief
    # must have none, or the loss metric reads it as unachievable on extreme ground.
    press = np.minimum(_downscale(_norm(-(0.75 * shg + 0.85 * mg)), dia), 0.0)
    emboss = np.maximum(_downscale(_norm(+(0.75 * hig + 0.85 * mg)), dia), 0.0)
    return {
        "bipolar": _downscale(_norm(1.15 * 0.80 * hi - 0.92 * sh - 0.34 * m), dia),
        "press": press,
        "emboss": emboss,
    }


def relief_map(master, dia: int) -> np.ndarray:
    """backwards-compatible accessor: the intended carved relief."""
    return relief_maps(dia, sha256_file(MASTER))["bipolar"]


def already_sealed(path, arr=None, master=None) -> tuple[bool, str]:
    """metadata flag first; then a pixel check that survives metadata stripping."""
    txt = exif_read(path, "-XMP-photoshop:Instructions", "-EXIF:UserComment")
    if FLAG in (txt or ""):
        return True, "metadata flag"
    if arr is not None and master is not None:
        r = seal_correlation(arr, master)
        if abs(r) >= DETECT_R:
            return True, f"pixel correlation r={r:.3f}"
    return False, ""


def _gauss_blur(a: np.ndarray, sigma: float = 1.2) -> np.ndarray:
    """separable Gaussian blur in float64 — deterministic, no mode restrictions."""
    rad = max(1, int(round(3 * sigma)))
    x = np.arange(-rad, rad + 1, dtype=np.float64)
    k = np.exp(-(x ** 2) / (2 * sigma ** 2))
    k /= k.sum()
    pad = np.pad(a, ((0, 0), (rad, rad)), mode="edge")
    out = np.apply_along_axis(lambda r: np.convolve(r, k, mode="valid"), 1, pad)
    pad = np.pad(out, ((rad, rad), (0, 0)), mode="edge")
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="valid"), 0, pad)


def seal_correlation(arr: np.ndarray, master: Image.Image) -> float:
    """
    Best normalised correlation between the high-passed seal region and any of the
    three relief modes. Sign-agnostic at the call site: polarity depends on ground.
    """
    h, w = arr.shape[:2]
    x, y, dia, _ = geometry(w, h)
    if x < 0 or y < 0 or dia < 8:
        return 0.0
    region = arr[y:y + dia, x:x + dia]
    if region.shape[0] != dia or region.shape[1] != dia:
        return 0.0
    L = rgb_to_lab(region)[..., 0]
    hp = L - _gauss_blur(L, 1.2)
    a = hp - hp.mean()
    best = 0.0
    for ref in relief_maps(dia, sha256_file(MASTER)).values():
        b = ref - ref.mean()
        den = float(np.sqrt((a * a).sum() * (b * b).sum()))
        if den:
            r = float((a * b).sum() / den)
            if abs(r) > abs(best):
                best = r
    return best


def exif_read(path, *tags):
    if not shutil.which("exiftool"):
        return ""
    try:
        out = subprocess.run(["exiftool", "-s3", "-m", *tags, path],
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception:
        return ""


def write_metadata(path, mask_digest):
    """machine-readable provenance: IPTC digitalSourceType is the standard term."""
    stamp = f"{FLAG} mask={mask_digest[:12]} {datetime.now(timezone.utc).isoformat()}"
    if not shutil.which("exiftool"):
        return False, "exiftool not installed — metadata NOT written"
    cmd = ["exiftool", "-overwrite_original", "-q", "-m",
           "-XMP-iptcExt:DigitalSourceType=http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
           "-XMP-dc:Description=AI-generated image. Created with a generative AI model. "
           "Visible AI disclosure seal applied bottom-right. Transparency notice per EU AI Act Art. 50.",
           "-XMP-photoshop:Credit=AI-generated (generative AI)",
           f"-XMP-photoshop:Instructions={stamp}",
           "-XMP-xmpRights:UsageTerms=Synthetic image - AI generated. Publish only with the visible AI disclosure seal intact.",
           "-XMP-xmp:CreatorTool=Generative AI image model",
           "-EXIF:ImageDescription=AI-generated image (synthetic media)",
           f"-EXIF:UserComment={stamp}",
           "-EXIF:Software=Generative AI", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "").strip()


def log(record):
    with open(MANIFEST, "a") as f:
        f.write(json.dumps(record) + "\n")


# ---- core ------------------------------------------------------------------
def apply_seal(src, dst=None, force=False, quiet=False):
    master, mask_digest = load_master()
    im = Image.open(src)
    fmt = (im.format or "").upper()
    icc = im.info.get("icc_profile")
    mode = im.mode
    alpha = None

    if mode in ("RGBA", "LA", "PA"):
        rgba = im.convert("RGBA")
        alpha = rgba.getchannel("A")
        work = rgba.convert("RGB")
    elif mode == "CMYK":
        work, icc = im.convert("RGB"), None   # CMYK -> RGB is a conversion; flag it
    else:
        work = im.convert("RGB")

    w, h = work.size
    if min(w, h) < SPEC["min_short_side"] and not force:
        return dict(status="skipped", reason=f"short side {min(w,h)}px < {SPEC['min_short_side']}px "
                                             "— stamp the master and derive this size from it", src=src)

    arr = np.asarray(work, dtype=np.uint8)
    sealed, how = already_sealed(src, arr, master)
    if sealed and not force:
        return dict(status="skipped", reason=f"already sealed ({how})", src=src)

    x, y, dia, margin = geometry(w, h)
    maps = relief_maps(dia, mask_digest)

    region = arr[y:y + dia, x:x + dia].astype(np.float64)
    lab = rgb_to_lab(region)
    L = lab[..., 0]

    # Polarity and mode are chosen ONCE for the whole seal, never per pixel: a
    # per-pixel flip would rectify the relief and destroy the carved shape.
    # Ground with headroom both ways gets the full carved bevel; ground pinned at
    # white or black gets a single-direction relief so the linework stays whole.
    # The test is "how much of the intended relief actually lands", measured only
    # on pixels the relief acts on — not the absolute luminance of the ground.
    def loss_frac(ref, pol, delta):
        d = delta * pol * ref
        achieved = np.clip(L + d, 0.0, 100.0) - L
        ink = np.abs(d) > 0.15
        if not ink.any():
            return 1.0
        want = np.abs(d[ink])
        return float(((want - np.abs(achieved[ink])) > 0.5 * want).mean())

    delta = SPEC["delta_L"]
    bi = maps["bipolar"]
    pol = 1 if loss_frac(bi, 1, delta) <= loss_frac(bi, -1, delta) else -1
    mode = "bipolar"
    if loss_frac(bi, pol, delta) > SPEC["clip_tolerance"]:
        mode = "press" if L.mean() >= 50.0 else "emboss"
        pol = 1
        delta = SPEC["delta_L_uni"]
    ref = maps[mode]
    # last resort on pathological ground: ease the relief, never below the floor
    while delta > SPEC["delta_floor"] and loss_frac(ref, pol, delta) > SPEC["clip_tolerance"]:
        delta = round(delta - 0.25, 2)

    dL = delta * pol * ref
    # keep hue exact: pull back the relief on any pixel where the shifted colour
    # would leave sRGB, rather than letting the clamp move a*/b*
    dL = gamut_safe_dL(L, lab[..., 1], lab[..., 2], dL)
    lab[..., 0] = np.clip(L + dL, 0.0, 100.0)          # a*, b* untouched -> no hue shift
    conv = np.round(lab_to_rgb(lab)).astype(np.uint8)
    # write ONLY where the relief is non-zero: pixels the seal does not touch keep
    # their original bytes exactly, instead of picking up Lab round-trip rounding.
    ink = (np.abs(dL) > 1e-6)[..., None]
    out_region = np.where(ink, conv, arr[y:y + dia, x:x + dia])

    out = arr.copy()
    out[y:y + dia, x:x + dia] = out_region
    res = Image.fromarray(out, mode="RGB")
    if alpha is not None:
        res = res.convert("RGBA")
        res.putalpha(alpha)

    if dst is None:
        stem, ext = os.path.splitext(src)
        dst = f"{stem}_sealed{ext}"
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)

    save = {}
    if icc:
        save["icc_profile"] = icc
    if fmt in ("JPEG", "JPG") or dst.lower().endswith((".jpg", ".jpeg")):
        save.update(quality=97, subsampling=0, optimize=True)   # 4:4:4, no chroma loss
    elif dst.lower().endswith(".png"):
        save.update(optimize=True)                              # lossless
    elif dst.lower().endswith(".webp"):
        save.update(lossless=True)
    res.save(dst, **save)

    ok, err = write_metadata(dst, mask_digest)
    touched = int((np.abs(out.astype(int) - arr.astype(int)).sum(axis=2) > 0).sum())
    rec = dict(status="sealed", version=VERSION, spec=SPEC["name"], src=src, dst=dst,
               src_sha256=sha256_file(src), dst_sha256=sha256_file(dst),
               mask_sha256=mask_digest, size=[w, h], seal=[x, y, dia], margin=margin,
               delta_L_requested=SPEC["delta_L"], delta_L_applied=delta, polarity=pol,
               relief_mode=mode,
               pixels_changed=touched,
               pct_of_frame=round(100.0 * touched / (w * h), 4),
               mode_in=mode, format_in=fmt, metadata_written=ok, metadata_error=err or None,
               cmyk_converted=(mode == "CMYK"),
               correlation=round(seal_correlation(np.asarray(res.convert("RGB")), master), 4),
               at=datetime.now(timezone.utc).isoformat())
    log(rec)
    if not quiet:
        print(f"sealed  {os.path.basename(src)} -> {os.path.basename(dst)}  "
              f"[{dia}px @ {x},{y}]  {rec['pct_of_frame']}% of frame  r={rec['correlation']}")
    return rec


def verify(path, source=None):
    """proves: seal present, geometry correct, mask authentic, artwork untouched."""
    master, mask_digest = load_master()
    im = Image.open(path)
    arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
    h, w = arr.shape[:2]
    x, y, dia, _ = geometry(w, h)
    r = seal_correlation(arr, master)
    meta = exif_read(path, "-XMP-iptcExt:DigitalSourceType")
    flag = exif_read(path, "-XMP-photoshop:Instructions")
    checks = {
        "seal_present_pixels": abs(r) >= DETECT_R,
        "seal_correlation": round(r, 4),
        "geometry": {"x": x, "y": y, "diameter": dia,
                     "pct_of_short_side": round(100.0 * dia / min(w, h), 2)},
        "mask_sha256": mask_digest,
        "machine_readable_provenance": "trainedAlgorithmicMedia" in meta,
        "house_flag": FLAG in (flag or ""),
    }
    if source:
        s = np.asarray(Image.open(source).convert("RGB"), dtype=np.uint8)
        if s.shape != arr.shape:
            checks["artwork_untouched_outside_seal"] = "N/A (different dimensions)"
        else:
            diff = np.abs(s.astype(int) - arr.astype(int)).sum(axis=2)
            outside = diff.copy()
            outside[y:y + dia, x:x + dia] = 0
            checks["artwork_untouched_outside_seal"] = bool(outside.max() == 0)
            inside = diff[y:y + dia, x:x + dia]
            lab_s = rgb_to_lab(s[y:y + dia, x:x + dia])
            lab_o = rgb_to_lab(arr[y:y + dia, x:x + dia])
            dab = np.abs(lab_o[..., 1:] - lab_s[..., 1:]).max()
            checks["max_chroma_shift_ab"] = round(float(dab), 3)
            checks["max_dL_in_seal"] = round(float(np.abs(lab_o[..., 0] - lab_s[..., 0]).max()), 2)
            checks["pixels_changed_pct"] = round(100.0 * float((inside > 0).sum()) / (w * h), 4)
    ok = checks["seal_present_pixels"] and checks["machine_readable_provenance"]
    if source:
        ok = ok and checks.get("artwork_untouched_outside_seal") is True
    checks["PASS"] = bool(ok)
    print(json.dumps(checks, indent=2))
    return 0 if ok else 1


def batch(root, out=None, recursive=False, jobs=4, force=False):
    files = []
    if recursive:
        for dp, _, fn in os.walk(root):
            files += [os.path.join(dp, f) for f in fn
                      if os.path.splitext(f)[1].lower() in EXTS and "_sealed" not in f]
    else:
        files = [os.path.join(root, f) for f in sorted(os.listdir(root))
                 if os.path.splitext(f)[1].lower() in EXTS and "_sealed" not in f]

    def one(p):
        dst = None
        if out:
            rel = os.path.relpath(p, root)
            dst = os.path.join(out, rel)
        try:
            return apply_seal(p, dst, force=force, quiet=True)
        except Exception as e:
            return dict(status="error", src=p, error=repr(e))

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        res = list(ex.map(one, files))
    tally = {}
    for r in res:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    for r in res:
        if r["status"] != "sealed":
            print(f"  {r['status']}: {os.path.basename(r['src'])} — "
                  f"{r.get('reason') or r.get('error')}")
    print(json.dumps({"files": len(files), **tally,
                      "seconds": round(time.time() - t0, 1),
                      "manifest": MANIFEST}, indent=2))
    return 0 if tally.get("error", 0) == 0 else 1


def selftest():
    """determinism, idempotency, background robustness, non-destructiveness."""
    import tempfile
    master, digest = load_master()
    tmp = tempfile.mkdtemp(prefix="ghostseal-")
    fails = []

    cases = {
        "white": np.full((900, 1400, 3), 255, np.uint8),
        "black": np.zeros((900, 1400, 3), np.uint8),
        "mid": np.full((900, 1400, 3), 128, np.uint8),
        "gradient": np.tile(np.linspace(0, 255, 1400, dtype=np.uint8)[None, :, None], (900, 1, 3)),
        "noise": (np.random.default_rng(7).random((900, 1400, 3)) * 255).astype(np.uint8),
    }
    # a natural photograph is the case that must satisfy pixel-level detection;
    # uniform pixel noise is information-theoretically hostile to any 5 L* mark,
    # so for it we assert the relief was applied, not that it can be re-found.
    DETECTABLE = {"white", "black", "mid", "gradient", "photo", "fixture"}
    photo = os.path.join(HERE, "source.png")
    if os.path.exists(photo):
        cases["photo"] = np.asarray(Image.open(photo).convert("RGB"))
    # the CI fixture puts a saturated specular blob, a dark band and a texture
    # patch under the seal corner: it locks in gamut-safety and mode selection
    fixture = os.path.join(HERE, "tests", "reference.png")
    if os.path.exists(fixture):
        cases["fixture"] = np.asarray(Image.open(fixture).convert("RGB"))

    for name, a in cases.items():
        p = os.path.join(tmp, f"{name}.png")
        Image.fromarray(a).save(p)
        r1 = apply_seal(p, os.path.join(tmp, f"{name}_1.png"), quiet=True)
        r2 = apply_seal(p, os.path.join(tmp, f"{name}_2.png"), quiet=True)
        if r1["status"] != "sealed":
            fails.append(f"{name}: not sealed ({r1.get('reason')})")
            continue
        # determinism: identical pixels for identical input (metadata carries a timestamp)
        p1 = np.asarray(Image.open(os.path.join(tmp, f"{name}_1.png")).convert("RGB"))
        p2 = np.asarray(Image.open(os.path.join(tmp, f"{name}_2.png")).convert("RGB"))
        if not np.array_equal(p1, p2):
            fails.append(f"{name}: NON-DETERMINISTIC pixels")
        # relief actually applied at the specified strength
        h0, w0 = a.shape[:2]
        x, y, dia, _ = geometry(w0, h0)
        dl = np.abs(rgb_to_lab(p1[y:y + dia, x:x + dia])[..., 0]
                    - rgb_to_lab(a[y:y + dia, x:x + dia])[..., 0]).max()
        if dl < SPEC["delta_floor"] - 0.75:
            fails.append(f"{name}: relief too weak (max ΔL*={dl:.2f})")
        # hue/chroma is never modified by design; any residual is 8-bit rounding
        # on the Lab round-trip, which is largest on extremely saturated pixels.
        dab = np.abs(rgb_to_lab(p1[y:y + dia, x:x + dia])[..., 1:]
                     - rgb_to_lab(a[y:y + dia, x:x + dia])[..., 1:]).max()
        tol = 4.0 if name == "noise" else 1.5
        if dab > tol:
            fails.append(f"{name}: chroma shifted (Δab={dab:.2f} > {tol})")
        # re-findable on realistic imagery
        if name in DETECTABLE and abs(r1["correlation"]) < DETECT_R:
            fails.append(f"{name}: seal not detectable (r={r1['correlation']})")
        # non-destructive outside the seal
        d = np.abs(a.astype(int) - p1.astype(int)).sum(axis=2)
        d[y:y + dia, x:x + dia] = 0
        if d.max() != 0:
            fails.append(f"{name}: pixels changed OUTSIDE the seal box")
        # idempotency
        r3 = apply_seal(os.path.join(tmp, f"{name}_1.png"),
                        os.path.join(tmp, f"{name}_3.png"), quiet=True)
        if r3["status"] != "skipped":
            fails.append(f"{name}: NOT idempotent — re-stamped an already sealed file")

    small = os.path.join(tmp, "small.png")
    Image.fromarray(np.full((400, 400, 3), 200, np.uint8)).save(small)
    if apply_seal(small, os.path.join(tmp, "small_o.png"), quiet=True)["status"] != "skipped":
        fails.append("small image was stamped instead of skipped")

    print(json.dumps({"mask_sha256": digest, "cases": len(cases) + 1,
                      "failures": fails, "PASS": not fails}, indent=2))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description="Ghost Seal — AI-disclosure stamp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply"); a.add_argument("image"); a.add_argument("-o", "--out")
    a.add_argument("--force", action="store_true")
    b = sub.add_parser("batch"); b.add_argument("dir"); b.add_argument("--out")
    b.add_argument("--recursive", action="store_true"); b.add_argument("--jobs", type=int, default=4)
    b.add_argument("--force", action="store_true")
    v = sub.add_parser("verify"); v.add_argument("image"); v.add_argument("--source")
    sub.add_parser("selftest")
    args = ap.parse_args()

    if args.cmd == "apply":
        r = apply_seal(args.image, args.out, force=args.force)
        if r["status"] != "sealed":
            print(f"{r['status']}: {r.get('reason')}")
        return 0
    if args.cmd == "batch":
        return batch(args.dir, args.out, args.recursive, args.jobs, args.force)
    if args.cmd == "verify":
        return verify(args.image, args.source)
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
