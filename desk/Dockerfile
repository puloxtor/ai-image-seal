# Ghost Seal Desk — the self-hosted service (Railway, Fly, Render, any Docker host).
#
# Build context is the REPO ROOT, not this folder, because the service imports the
# production applier and the pinned mask directly:
#
#   docker build -f desk/Dockerfile -t ghost-seal-desk:1.0.0 .
#   docker run --rm -p 8080:8080 -e ACCESS_CODE=... -v gsd:/data ghost-seal-desk:1.0.0
#
# The interpreter and libraries are pinned for the same reason the mask is: the
# seal is scaled with LANCZOS resampling, and resampling can shift between
# versions. Bump these deliberately and re-run the selftest when you do.

FROM python:3.11.2-slim

# exiftool writes the machine-readable provenance. Without it the seal still
# applies but the compliance-critical metadata does not, so it is not optional.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libimage-exiftool-perl \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      "pillow==12.3.0" \
      "numpy==2.4.6" \
      "flask==3.1.0" \
      "gunicorn==23.0.0"

WORKDIR /app

# The standard: applier, pinned mask, pinned hash, plus the CI fixture.
COPY ghost_seal.py build_master.py verify_tree.py seal_master.png seal_master.json ./
COPY tests/ ./tests/
COPY desk/ ./desk/

# The build FAILS if the seal misbehaves on this runtime: determinism,
# idempotency, non-destructiveness, chroma stability, and the relief landing on
# white, black, mid, gradient, noise and the fixture. A broken image never ships.
RUN python3 ghost_seal.py selftest

# Storage. ATTACH A RAILWAY VOLUME AT /data (Docker's VOLUME instruction is not
# supported on Railway's builder) — without one, originals, sealed masters and
# the audit trail vanish on the next deploy.
ENV DATA_DIR=/data \
    GHOST_SEAL_MANIFEST=/data/manifest.jsonl \
    PYTHONUNBUFFERED=1 \
    PORT=8080
RUN mkdir -p /data

EXPOSE 8080

# Threaded workers: sealing is CPU-bound NumPy that releases the GIL, and each
# request is short. Two workers keep memory modest on a small instance.
CMD exec gunicorn \
      --bind "0.0.0.0:${PORT}" \
      --workers 2 \
      --threads 4 \
      --timeout 180 \
      --access-logfile - \
      desk.app:app
