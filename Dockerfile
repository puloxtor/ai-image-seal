# The pinned runtime for the Ghost Seal.
#
# Pinning the interpreter matters as much as pinning the mask: the seal is scaled
# from seal_master.png with LANCZOS resampling, and resampling output can shift
# between library versions. Every lane — CI, the ingest worker, the web tool,
# laptops — runs THIS image, so the seal is identical everywhere by construction.
#
# Tag it with the seal standard's version (ghost-seal:1.0.0), never `latest`.
#
#   docker build -t ghost-seal:1.0.0 .
#   docker run --rm -v "$PWD":/w ghost-seal:1.0.0 apply /w/img.png -o /w/img_sealed.png
#   docker run --rm -v "$PWD":/w ghost-seal:1.0.0 batch /w/library --out /w/sealed --recursive --jobs 8
#   docker run --rm -v "$PWD":/w --entrypoint python3 ghost-seal:1.0.0 verify_tree.py /w/dist --strict-metadata

FROM python:3.11.2-slim

# exiftool writes the machine-readable provenance. Without it the seal still
# applies, but the compliance-critical metadata does not — so it is not optional.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libimage-exiftool-perl \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "pillow==12.3.0" "numpy==2.4.6"

WORKDIR /app
COPY ghost_seal.py build_master.py verify_tree.py seal_master.png seal_master.json ./
COPY tests/ ./tests/

# The build fails if the seal misbehaves on this runtime: determinism,
# idempotency, non-destructiveness, chroma stability, and the relief landing on
# white / black / mid / gradient / noise / photograph. A broken image cannot ship.
RUN python3 ghost_seal.py selftest

# Manifest lines land here; mount a volume to keep them.
ENV GHOST_SEAL_MANIFEST=/manifests/manifest.jsonl
RUN mkdir -p /manifests

ENTRYPOINT ["python3", "ghost_seal.py"]
CMD ["selftest"]
