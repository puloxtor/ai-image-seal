# Ghost Seal

The house AI-disclosure standard for generated imagery: a carved holographic stamp
in the bottom-right corner, plus embedded machine-readable provenance.

The visible seal is the courtesy to the viewer. The metadata is the compliance
artifact. They ship together, always.

```
docker build -t ghost-seal:1.0.0 .
docker run --rm -v "$PWD":/w ghost-seal:1.0.0 apply /w/img.png -o /w/img_sealed.png
docker run --rm -v "$PWD":/w ghost-seal:1.0.0 verify /w/img_sealed.png --source /w/img.png
```

## The five rules

1. **Never draw the seal.** It is scaled from `seal_master.png`, whose SHA-256 is
   checked on every run. A new seal design is a house-standard change, not an edit.
2. **Never edit the artwork.** Only pixels inside the seal box change, and only
   L\* is modified — hue and saturation are mathematically preserved.
3. **Never stamp derivatives.** Seal masters; generate crops, resizes and
   thumbnails *from* the sealed master. Anything under 512px short side is skipped.
4. **Never re-stamp.** Sealed files are detected and skipped, including after
   metadata has been stripped (pixel correlation).
5. **Never write one half.** Visible seal without metadata, or metadata without
   the visible seal, fails the standard.

## Commands

| Command | Use |
|---|---|
| `apply IMG [-o OUT]` | Seal one image |
| `batch DIR [--out DIR] [--recursive] [--jobs N]` | Seal a library; skips sealed and too-small files, so it is resumable |
| `verify IMG [--source ORIGINAL]` | Audit one file; with `--source` it proves the artwork outside the seal is bit-identical |
| `selftest` | The gate. Must print `"PASS": true` |
| `verify_tree.py DIR [--strict-metadata]` | Publish gate. Non-zero exit if anything unsealed is about to ship |

## Repo contents

| File | Role |
|---|---|
| `seal_master.png` | The pinned seal geometry. Source of truth. `6a608923…f511e2` |
| `seal_master.json` | Pinned mask hash, geometry table, font hashes |
| `ghost_seal.py` | Applier, verifier, batch runner, selftest |
| `build_master.py` | Regenerates the master. Run **only** to change the standard |
| `verify_tree.py` | Publish gate |
| `tests/reference.png` | Deterministic fixture for the CI byte-stability check |
| `Dockerfile` | The pinned CLI runtime — every lane runs this image |
| `desk/` | The self-hosted web desk (Flask + gunicorn) for non-terminal users. Seals in-process with this same applier. See `desk/README.md` |
| `runner.py` | Queue drainer, for the hosted variant where the UI and the sealing run apart |
| `railway.json` | Points a Railway deploy at `desk/Dockerfile` with the repo root as context |
| `doc/ghost-seal-spec.md` | Why the seal looks like this, how it works, the guarantees and their evidence |
| `doc/team-rollout.md` | Where it is stored, how each group uses it, rollout sequence |

## Enforcement, strongest first

1. **Seal on ingest** — a worker seals every new generation into `masters/`; raw
   model output stays in `incoming/` and is not publishable.
2. **Gate on publish** — `verify_tree.py ./dist/assets --strict-metadata` in the
   release job. A gate that only warns is a gate that is ignored.
3. **Web desk / CLI** — for designers and exceptions. `desk/` is a single
   container: `docker build -f desk/Dockerfile -t ghost-seal-desk:1.0.0 .`

## Changing the standard

The mask hash is pinned in four places: `seal_master.json`, `doc/ghost-seal-spec.md`,
`.github/workflows/ci.yml`, and the agent skill's metadata. CI fails unless all
agree. Changing the seal therefore requires one reviewed diff touching all four,
with brand and legal approval via `CODEOWNERS` — and a `--force` re-seal of the
library afterwards. Two seal versions in circulation is worse than either alone,
because it makes "which assets were marked" unanswerable.

## Limits, stated plainly

- Resized or re-cropped derivatives keep their metadata but may fall below the
  pixel-detection threshold. Derive from sealed masters.
- Extreme high-frequency texture can hide a 5 L\* relief from re-detection. The
  relief is still applied; the metadata still discloses.
- Metadata is unsigned and strippable, and many platforms strip it on upload. Add
  C2PA signing if tamper evidence is required.
- CMYK input is converted to RGB and flagged in the manifest.
- This implements marking practice. Whether a given asset triggers EU AI Act
  Art. 50 duties, and in which role, is a question for counsel.
