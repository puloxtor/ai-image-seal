#!/usr/bin/env python3
"""
make_fixture.py — builds tests/reference.png, the CI byte-stability fixture.

Deterministic and synthetic on purpose: no brand asset belongs in the repo, and a
seeded generator means the fixture can be rebuilt identically on any machine. It
deliberately puts hostile ground under the seal corner — a bright specular blob, a
dark band and a texture patch — so the determinism check exercises mode selection
rather than a flat plate.
"""
import hashlib
import numpy as np
from PIL import Image

W, H = 1600, 1100
rng = np.random.default_rng(20260805)

y, x = np.mgrid[0:H, 0:W].astype(np.float64)
# base: diagonal pastel gradient
r = 120 + 90 * (x / W) + 30 * (y / H)
g = 150 + 60 * (1 - x / W) + 25 * (y / H)
b = 200 - 70 * (y / H)

# a bright specular blob near the seal corner (forces near-white handling)
cx, cy, rad = W * 0.88, H * 0.86, W * 0.10
blob = np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2 * rad ** 2)))
r += 110 * blob
g += 105 * blob
b += 95 * blob

# a dark band crossing the lower third (forces near-black handling)
band = np.exp(-((y - H * 0.72) ** 2) / (2 * (H * 0.035) ** 2))
r -= 120 * band
g -= 115 * band
b -= 100 * band

# a fine texture patch (high-frequency ground)
tex = np.zeros_like(x)
sl = (slice(int(H * 0.05), int(H * 0.35)), slice(int(W * 0.60), int(W * 0.95)))
tex[sl] = rng.normal(0, 26, tex[sl].shape)
r += tex
g += tex
b += tex

img = np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)
Image.fromarray(img).save("tests/reference.png", optimize=True)

with open("tests/reference.png", "rb") as f:
    print("tests/reference.png", f"{W}x{H}", "sha256", hashlib.sha256(f.read()).hexdigest())
