#!/usr/bin/env python3
"""
verify_tree.py — publish gate. Fails if any image in a tree is unsealed.

Drop this in front of anything that ships imagery (CI job, release script,
CMS export check). Exit code 1 = something unsealed is about to be published.

    python3 verify_tree.py ./dist/assets
    python3 verify_tree.py ./dist/assets --strict-metadata --json report.json

--strict-metadata also requires the machine-readable IPTC provenance, not just
the visible seal. Use it for anything leaving the building; without it, files
whose metadata a platform has stripped still pass on the pixel evidence.
"""
import argparse, json, os, sys

import numpy as np
from PIL import Image

import ghost_seal as GS

EXTS = GS.EXTS


def check(path, strict):
    try:
        im = Image.open(path)
        arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
    except Exception as e:
        return dict(path=path, ok=False, reason=f"unreadable: {e!r}")

    h, w = arr.shape[:2]
    if min(w, h) < GS.SPEC["min_short_side"]:
        return dict(path=path, ok=True, skipped=True,
                    reason=f"derivative ({w}x{h}) — must come from a sealed master")

    master, _ = GS.load_master()
    r = GS.seal_correlation(arr, master)
    seal = abs(r) >= GS.DETECT_R
    meta = "trainedAlgorithmicMedia" in GS.exif_read(path, "-XMP-iptcExt:DigitalSourceType")

    ok = seal and (meta or not strict)
    reason = ""
    if not seal:
        reason = f"NO VISIBLE SEAL (r={r:.3f})"
    elif strict and not meta:
        reason = "seal present but machine-readable provenance MISSING"
    return dict(path=path, ok=ok, correlation=round(r, 4), seal=seal,
                provenance=meta, reason=reason)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--strict-metadata", action="store_true")
    ap.add_argument("--json", help="write a full report here")
    args = ap.parse_args()

    files = []
    for dp, _, fn in os.walk(args.root):
        files += [os.path.join(dp, f) for f in sorted(fn)
                  if os.path.splitext(f)[1].lower() in EXTS]
    if not files:
        print(f"no images found under {args.root}")
        return 0

    results = [check(p, args.strict_metadata) for p in files]
    bad = [r for r in results if not r["ok"]]
    skipped = [r for r in results if r.get("skipped")]

    for r in bad:
        print(f"FAIL  {r['path']}  — {r['reason']}")
    for r in skipped:
        print(f"note  {r['path']}  — {r['reason']}")

    print(json.dumps({"checked": len(files), "failed": len(bad),
                      "derivatives_skipped": len(skipped),
                      "strict_metadata": args.strict_metadata}, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
