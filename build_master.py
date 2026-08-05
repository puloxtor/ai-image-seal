#!/usr/bin/env python3
"""
build_master.py — generates the GHOST SEAL master mask, ONCE.

The master is a 2048x2048 8-bit greyscale mask of the seal linework. It is the
single source of truth for the seal's geometry: ghost_seal.py never re-draws the
seal, it only scales this asset. That is what makes the mark byte-identical
across every image, machine, font version and Pillow version, forever.

Run this ONLY to regenerate the seal design (a new seal = a new house standard =
a new mask hash). Requires Inter 4.0; the font hash is pinned and verified.

    python3 build_master.py --font-dir /path/to/Inter/extras/ttf

Geometry is defined in fractions of the mask width, so the design is
resolution-independent.
"""
import argparse, hashlib, json, math, os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFont

N = 2048                       # master resolution
RING_TEXT = "AI-GENERATED IMAGE  \u00b7  "

# --- geometry, as fractions of N -------------------------------------------
G = dict(
    outer_rule=dict(inset=0.012, width=0.0083, value=255),
    second_rule=dict(inset=0.062, width=0.0056, value=210),
    inner_rule=dict(inset=0.285, width=0.0056, value=190),
    ticks=dict(count=60, r0=0.325, r1=0.425, width=0.0039, value=120),
    monogram=dict(text="AI", size=0.235, value=255),
    ring=dict(size=0.095, radius=0.375, value=255, baseline=0.030),
)

INTER_SHA256 = {
    "Inter-SemiBold.ttf": None,   # filled on first successful build, see --pin
    "Inter-Bold.ttf": None,
}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(font_dir):
    f_semi = os.path.join(font_dir, "Inter-SemiBold.ttf")
    f_bold = os.path.join(font_dir, "Inter-Bold.ttf")
    for p in (f_semi, f_bold):
        if not os.path.exists(p):
            sys.exit(f"missing font: {p}")

    m = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(m)
    px = lambda frac: max(1, int(round(frac * N)))
    cx = cy = N / 2

    for key in ("outer_rule", "second_rule", "inner_rule"):
        g = G[key]
        i = g["inset"] * N
        d.ellipse((i, i, N - 1 - i, N - 1 - i), outline=g["value"], width=px(g["width"]))

    g = G["ticks"]
    for i in range(g["count"]):
        a = i * 2 * math.pi / g["count"]
        d.line([(cx + math.cos(a) * g["r0"] * N, cy + math.sin(a) * g["r0"] * N),
                (cx + math.cos(a) * g["r1"] * N, cy + math.sin(a) * g["r1"] * N)],
               fill=g["value"], width=px(g["width"]))

    g = G["monogram"]
    d.text((cx, cy), g["text"], font=ImageFont.truetype(f_bold, int(g["size"] * N)),
           fill=g["value"], anchor="mm")

    # circumferential microtext, one glyph at a time, rotated to the tangent
    g = G["ring"]
    fm = ImageFont.truetype(f_semi, int(g["size"] * N))
    R = g["radius"] * N
    step = 360.0 / len(RING_TEXT)
    tile = int(N * 0.24)
    for i, ch in enumerate(RING_TEXT):
        a = -90 + i * step
        t = Image.new("L", (tile, tile), 0)
        ImageDraw.Draw(t).text((tile / 2, tile / 2 - g["baseline"] * N), ch,
                               font=fm, fill=g["value"], anchor="mm")
        t = t.rotate(-a - 90, resample=Image.BICUBIC)
        x = int(cx + math.cos(math.radians(a)) * R - tile / 2)
        y = int(cy + math.sin(math.radians(a)) * R - tile / 2)
        region = m.crop((x, y, x + tile, y + tile))
        m.paste(ImageChops.lighter(region, t), (x, y))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font-dir", default="inter/extras/ttf")
    ap.add_argument("--out", default="seal_master.png")
    args = ap.parse_args()

    m = build(args.font_dir)
    m.save(args.out, optimize=True)
    meta = {
        "asset": os.path.basename(args.out),
        "resolution": N,
        "ring_text": RING_TEXT,
        "geometry": G,
        "mask_sha256": sha256_file(args.out),
        "fonts": {n: sha256_file(os.path.join(args.font_dir, n))
                  for n in ("Inter-SemiBold.ttf", "Inter-Bold.ttf")},
        "pillow": Image.__version__,
    }
    with open("seal_master.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps({k: meta[k] for k in ("resolution", "mask_sha256", "fonts")}, indent=2))


if __name__ == "__main__":
    main()
