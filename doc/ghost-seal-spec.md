## 1. Purpose

Every image we publish that was made with a generative model must disclose that
fact. The disclosure has to satisfy two audiences that pull in opposite directions:

- **A regulator or complainant** must be able to find an unambiguous disclosure on
  the asset itself, and a machine must be able to read it without human help.
- **A customer** must not be pushed away by a warning label stuck on our marketing.

The Ghost Seal resolves this by separating the two jobs. The **machine-readable
metadata** carries the legal weight: an explicit, standards-based declaration that
the image is synthetic. The **visible seal** carries the human-facing courtesy: a
small carved stamp in the corner, findable on inspection, ignorable at a glance.

The visible mark is deliberately quiet. The provenance record is deliberately loud.

---

## 2. Regulatory context, stated honestly

The EU AI Act's transparency obligations (Article 50) work on two levels: synthetic
image content should be **marked in a machine-readable format** so it is detectable
as artificially generated, and certain publications must additionally be **disclosed
to the viewer**. The IPTC `digitalSourceType` vocabulary term
`trainedAlgorithmicMedia` is the interoperable industry expression of the
machine-readable part, and it is what we embed.

What this document does **not** claim:

- It does not certify us as compliant. It implements marking practice that is
  consistent with the regulation's intent and with industry standards.
- It does not decide whether a given asset triggers Article 50 duties at all, or
  whether we act as provider or deployer for that asset. That is a question for
  counsel, and the answer may differ per campaign.
- The metadata we write is **unsigned**, therefore strippable. If we need a
  tamper-evident chain, C2PA signing with a company certificate goes on top of this;
  it does not replace it.

Treat this as the engineering half of compliance. The legal half needs sign-off.

---

## 3. How we got to the Ghost Seal

The seal was not the first idea. Six disclosure treatments were built at full
resolution on a real campaign asset (a 1792x2400 product ad), then measured rather
than debated. Two numbers drove the decision:

- **ΔL\* on ink** — the mean CIE L\* (perceptual lightness) difference between the
  mark and the background it sits on. This is how much the mark "pops".
- **Thumbnail RMS** — the root-mean-square pixel difference between the marked and
  unmarked frame after downscaling to 1/10 scale. This approximates how much of the
  mark survives into a feed-sized thumbnail, i.e. how much it costs us in the scroll.

| Candidate | ΔL\* on ink | Thumbnail RMS | Verdict |
|---|---|---|---|
| Glass etch | 8.6 | 0.45 | Very quiet, but reads as a plain text label |
| Frosted micro-badge | 4.6 | 0.72 | Clean, but a UI chip on a print-grade ad |
| Folded corner ribbon | 4.5 | 0.84 | Rejected: looks like a stock-photo sample watermark |
| Hologram seal | 7.7 | 1.57 | Chosen direction: reads as a certification, not a warning |
| Edge caption | 14.9 | 1.11 | Explicit, but obvious legal fine print |
| Legal strip below frame | n/a | 0.00 | Strongest compliance, changes the composition |

The hologram seal won on positioning: a seal reads as *provenance* and even as a
quality mark, where a caption reads as *disclaimer*. But at first build it was too
loud — 8.3% of frame width with a saturated iridescent disc.

Four progressively quieter revisions followed, each dropping the "sticker"
qualities: the solid fill went away, the rim went away, the iridescence was reduced
to a single diagonal sheen band, and the seal geometry was re-expressed as **pure
luminance relief** — the mark became something pressed into the surface rather than
placed on top of it.

| Revision | Diameter | ΔL\* | Thumbnail RMS |
|---|---|---|---|
| Original holo seal | 149px (8.3% W) | 7.7 | 1.57 |
| D — visible | 122px (6.8% W) | 4.4 | 0.66 |
| C — foil | 108px (6.0% W) | 3.4 | 0.42 |
| B — carved | 99px (5.5% W) | 2.6 | 0.25 |
| **A — ghost (adopted)** | **90px (5.0% W)** | **2.0** | **0.06** |

Ghost was adopted because it removes colour entirely. Colour is what makes a mark
fight with artwork — it can clash with a palette, and it behaves unpredictably
across the range of backgrounds in our library. A relief that only modulates
lightness cannot clash with any palette by construction, which makes it the only
variant that is safe to apply library-wide without art-directing each case.

Thumbnail RMS 0.06 means the seal is effectively absent at feed scale, while the
full-resolution asset still carries a legible seal.

---

## 4. Why the bottom-right corner

Placement was chosen from viewing behaviour, not taste.

- **Image saliency is centre-biased.** Fixations cluster toward the middle of a
  frame, so all four corners are low-attention real estate. Corner placement is
  therefore cheap wherever we put it.
- **Reading order makes the corners unequal.** In left-to-right cultures the
  top-left is the entry fixation — the most expensive corner. The Gutenberg diagram
  labels the bottom-right the *terminal area*: the eye arrives there after the
  subject and the message, so a mark placed there interrupts nothing.
- **Convention buys us habituation.** The bottom-right is where viewers have been
  trained by decades of photo credits and watermarks to expect a small mark, so they
  skip it automatically.
- **Convention also buys us defensibility.** The bottom-left is arguably the very
  weakest-attention corner, but putting a legal disclosure in an unconventional spot
  invites the accusation that we hid it. The bottom-right is the corner an auditor
  checks first — which is exactly what we want from a disclosure.

Net: lowest practical cost in attention, highest discoverability when someone comes
looking. Corner is a single configuration value and can be changed house-wide, but
it should not be changed per asset — consistency is part of the defence.

---

## 5. What the seal is

A circular stamp built from four concentric elements, all defined as fractions of
the seal diameter so the design is resolution-independent:

| Element | Geometry | Purpose |
|---|---|---|
| Outer double rule | inset 1.2% and 6.2% of diameter | Reads as a seal at a glance |
| Radial guilloche ticks | 60 ticks, radius 32.5%-42.5% | Security-print texture; hard to fake casually |
| Ring microtext | "AI-GENERATED IMAGE ·" repeated, radius 37.5% | The actual disclosure, in words |
| Centre monogram | "AI", cap height 23.5% | Recognisable at the smallest sizes |

Applied specification (the house standard):

| Parameter | Value |
|---|---|
| Placement | Bottom-right, margin 3.0% of the short side |
| Diameter | 5.0% of the short side, clamped to 64-260px |
| Relief strength | 5.0 L\* peak, bipolar; 6.0 L\* single-direction |
| Visibility floor | 3.5 L\* — never eased below this |
| Colour | None. a\* and b\* are not modified |
| Pixels touched | ~0.1% of the frame |
| Minimum input | 512px short side |

---

## 6. Models and technology

**No generative model is involved in the seal.** This matters: a diffusion model
asked to "add a seal" produces a different seal every time, cannot be audited, and
would repaint the artwork. The seal is deterministic code compositing.

Generative models are involved only *upstream* — they produce the imagery we are
disclosing. That is precisely the fact the seal declares.

| Component | Technology | Role |
|---|---|---|
| Seal geometry | `build_master.py`, Pillow vector drawing at 2048x2048 | Draws the master mask once, ever |
| Typography | Inter 4.0 (SemiBold, Bold), font hashes recorded | Monogram and ring microtext |
| Colour model | CIELAB, D65 white point, computed in NumPy float64 | Perceptual lightness control; leaves hue untouched |
| Resampling | LANCZOS, 4x supersampled relief build | Sub-pixel relief edges without aliasing |
| Metadata | ExifTool 12.57, XMP + EXIF, IPTC `digitalSourceType` | Machine-readable provenance |
| Runtime | Python 3.11, Pillow 12.3, NumPy 2.4 | Application and verification |

**The pinned master mask is the source of truth.** `seal_master.png` is a
2048x2048 8-bit greyscale mask of the seal linework:

```
SHA-256  6a6089230d3904f1c4357314102e47fe30b54c1ee386324530664d84c7f511e2
```

The applier never re-draws the seal; it scales this asset. This is what makes the
mark identical across every image, machine, font version and library version — and
the applier **refuses to run** if the master's hash does not match, so a silently
edited seal cannot enter the pipeline.

---

## 7. How the seal is applied

1. **Load and hash-check the master.** Mismatch aborts the run.
2. **Compute geometry** from the image's short side: diameter, margin, corner
   position. Integer, deterministic, no rounding drift.
3. **Build three relief maps** for that exact diameter, cached per run:
   - `bipolar` — the mask offset up-left as a lit rim, offset down-right as a
     pressed shadow, plus a faint core so the linework has body. This is the carved
     look.
   - `press` — darkening only, for ground pinned near white.
   - `emboss` — lightening only, for ground pinned near black.
   Single-direction maps lose the light/dark edge pairing that makes hairlines
   visible, so their strokes are lifted with a compressive curve (gamma 0.55); the
   opposite-sign ringing lobe left by LANCZOS is clamped to zero.
4. **Convert the seal region to CIELAB** in float64.
5. **Choose polarity and mode once for the whole seal.** The test is how much of the
   intended relief actually lands: for each candidate, compare the requested ΔL\*
   against what survives clamping to the 0-100 L\* range, and count the fraction of
   ink pixels that lose more than half. If the bipolar bevel loses more than 2%, the
   seal switches to a single-direction mode. **This decision is never made per
   pixel** — a per-pixel flip rectifies the relief and destroys the carved shape,
   which was a real defect caught in review and fixed.
6. **Apply the relief to L\* only.** a\* and b\* are passed through untouched, so
   hue and saturation are mathematically preserved.
7. **Pull the relief back where sRGB cannot represent it.** Shifting L\* on an
   already-saturated colour can push it outside the gamut; the clamp that follows
   would then move a\* and b\* too, which is a hue shift. Instead the relief
   amplitude is halved, per pixel, until the result is representable — up to seven
   times. It only ever weakens the mark locally; it can never invert or recolour it.
   On a fixture with a blown specular highlight under the seal this cut the worst
   chroma error from Δab 5.24 to **0.468**, i.e. from a visible-in-principle shift
   to pure 8-bit rounding.
8. **Write only ink pixels.** Pixels inside the seal box that the relief does not
   act on keep their original bytes rather than picking up rounding from the Lab
   round-trip.
9. **Save without gratuitous loss.** PNG stays lossless; JPEG is re-encoded at
   quality 97 with 4:4:4 chroma; WebP is lossless; ICC profiles are carried through.
10. **Write metadata**, then **log a manifest line** with input and output SHA-256,
   mask hash, geometry, relief mode, applied ΔL\*, pixel count and timestamp.

### Metadata written

| Field | Value |
|---|---|
| `XMP-iptcExt:DigitalSourceType` | `...digitalsourcetype/trainedAlgorithmicMedia` |
| `XMP-dc:Description` | Human-readable AI disclosure incl. Art. 50 reference |
| `XMP-photoshop:Credit` | `AI-generated (generative AI)` |
| `XMP-photoshop:Instructions` | House flag `GHOST-SEAL-V1`, mask hash prefix, UTC timestamp |
| `XMP-xmpRights:UsageTerms` | Publish only with the visible seal intact |
| `EXIF:ImageDescription` / `Software` / `UserComment` | Same disclosure, EXIF-side |

---

## 8. Guarantees, and the evidence for them

Measured on the reference campaign asset (1792x2400):

| Guarantee | Evidence |
|---|---|
| Identical seal every time | Two runs on the same input produce **pixel-identical** output; seal scaled from a hash-pinned master |
| Artwork not compromised | `artwork_untouched_outside_seal: true` — bit-identical outside the 90px seal box |
| Hue and saturation preserved | Max chroma shift Δ(a\*,b\*) = **0.486** on the campaign asset and **0.468** on a fixture with a blown highlight under the seal — both pure 8-bit rounding, because out-of-gamut cases are pulled back rather than clamped |
| Relief lands as specified | Max ΔL\* in seal = **4.98** against a 5.0 requested |
| Minimal footprint | **0.0999%** of frame pixels changed |
| Findable on audit | Correlation against the reference relief = **0.895** |
| Works on any background | Selftest passes on pure white, pure black, mid-grey, full-range gradient, pixel noise, and a real photograph |
| Never double-stamped | Re-running on a sealed file skips it, including after all metadata is stripped (detected by pixel correlation r = 0.895) |
| Survives JPEG | Seal still detected at r = 0.868 after a quality-97 re-encode |

### The selftest is the gate

`ghost_seal.py selftest` builds hostile cases and asserts, per case: determinism,
relief strength above the floor, chroma stability, detectability, zero modification
outside the seal box, and idempotency. It also asserts that a 400px image is
**skipped**, not stamped. It must print `"PASS": true` before any production run,
and again after any change to the script, the master, Pillow, or the machine.

Three defects were found by this harness and fixed before adoption: the per-pixel
polarity flip that rectified the relief on extreme backgrounds; a clipping metric
that mistook an already-white background for an unachievable relief and needlessly
weakened the seal; and out-of-gamut clamping that shifted hue by up to Δab 5.24 on a
blown specular highlight.

---

## 9. Operating rules

**Stamp masters, derive everything else.** Apply the seal to the master asset, then
produce crops, resizes and thumbnails *from the sealed master*. Never stamp a
derivative: pixel-level re-detection depends on the original geometry, and a
shrunken seal is neither legible nor findable. Images with a short side below 512px
are skipped by design for this reason.

**One image**

```
python3 ghost_seal.py apply IMG.png -o out/IMG_sealed.png
python3 ghost_seal.py verify out/IMG_sealed.png --source IMG.png
```

**A library** — mirrors the input tree, one manifest line per file, resumable
because sealed files are skipped:

```
python3 ghost_seal.py batch ./library --out ./library_sealed --recursive --jobs 8
```

**Audit a published file** — no original required:

```
python3 ghost_seal.py verify suspect.jpg
```

**The manifest is the audit trail.** `manifest.jsonl` records, per asset: source and
output SHA-256, mask hash, geometry, relief mode, applied ΔL\*, pixels changed,
whether metadata was written, and the UTC timestamp. Keep it in version control or
ship it to a log store; it is what turns "we mark our AI images" into a claim we can
evidence per file.

---

## 10. Known limits — disclose these internally

- **Resized or re-cropped derivatives** keep their metadata but may fall below the
  pixel-detection threshold. Derive from sealed masters.
- **Extreme high-frequency texture** (uniform pixel noise) can hide a 5 L\* relief
  from re-detection. The relief is still applied and the metadata still discloses.
- **Metadata is unsigned and strippable**, and many platforms strip it on upload.
  The visible seal is what survives a platform re-encode; C2PA signing is the answer
  if we need tamper evidence.
- **CMYK input is converted to RGB** and flagged in the manifest. Seal the RGB
  master; let prepress convert.
- **Legal scope is not settled here.** See section 2.

---

## 11. Change control

The seal is a house standard, and its value comes from being the same everywhere.

- Changing **strength, size or corner** = editing `SPEC` in `ghost_seal.py`. Re-run
  the selftest, re-seal with `--force`.
- Changing the **seal artwork** = editing `build_master.py` geometry, rebuilding the
  master, re-pinning its SHA-256 in the skill metadata and in this document, then
  re-sealing the library with `--force`.
- Either change needs explicit sign-off, and the old and new mask hashes recorded.
  Two different seals in circulation is worse than either seal alone: it invites the
  question of which assets were marked and which were missed.

---

## 12. File inventory

| File | SHA-256 | Role |
|---|---|---|
| `seal_master.png` | `6a6089230d3904f1c4357314102e47fe30b54c1ee386324530664d84c7f511e2` | The pinned seal geometry. Source of truth |
| `ghost_seal.py` | `2415519056bad73984ea144a56a055a2c2f2ca01cbca031ecc07017566578e47` | Applier, verifier, batch runner, selftest |
| `build_master.py` | `0592891e326c9a3801a4a79ee6efea26d264185999fa8ac715ccdb8f0aa6f532` | Regenerates the master. Run only to change the standard |
| `seal_master.json` | — | Pinned mask hash, geometry table, font hashes |
| `verify_tree.py` | `3aa2a0c3514b94653d1992f03a0ab7335716afe79d8eba195f540088af15a0a4` | Publish gate: non-zero exit if anything unsealed ships |
| `tests/reference.png` | `a15f4f79cd40157d170b1a8cecef66031541f760ce27dac460337ffe2e0f5dc7` | Deterministic CI fixture (hostile ground under the seal) |
| `manifest.jsonl` | — | Append-only per-asset audit trail |

Reference `verify` output on the campaign asset:

```
seal_present_pixels ............ true
seal_correlation ............... 0.8954
geometry ....................... x 1648, y 2256, diameter 90 (5.02% of short side)
mask_sha256 .................... 6a6089230d3904f1c4357314102e47fe30b54c1ee386324530664d84c7f511e2
machine_readable_provenance .... true
house_flag ..................... true
artwork_untouched_outside_seal.. true
max_chroma_shift_ab ............ 0.486
max_dL_in_seal ................. 4.98
pixels_changed_pct ............. 0.0999
PASS ........................... true
```
