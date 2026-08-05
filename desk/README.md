# Ghost Seal Desk — self-hosted service

The desk for people who should not need a terminal: drop masters in, get them back
sealed, with the measured relief and the manifest line on record.

On a container host the seal runs **in this process** using the production applier
and the pinned mask, so what the desk returns is what CI returns. There is no
JavaScript reimplementation in the request path, and therefore nothing that can
drift from the house standard. (The visibility bench on the page is a labelled
preview and never touches a real file.)

## Deploy on Railway

1. **Push this repo** (root must contain `ghost_seal.py`, `seal_master.png`,
   `seal_master.json`, `tests/`, `desk/`).
2. **New Project → Deploy from GitHub repo.** Railway reads `railway.json`, which
   points at `desk/Dockerfile` with the repo root as build context. If you'd
   rather not use `railway.json`, set Build → Dockerfile Path to `desk/Dockerfile`
   manually.
3. **Add a volume** and mount it at **`/data`**. Do this before the first real
   upload: without it, originals, sealed masters and the audit trail are wiped on
   every redeploy.
4. **Set variables**:

   | Variable | Required | Notes |
   |---|---|---|
   | `ACCESS_CODE` | yes | the shared team code that unlocks the desk |
   | `SESSION_SECRET` | recommended | any 32+ random hex string; if unset, sessions simply end at each redeploy |
   | `DATA_DIR` | no | defaults to `/data`, matching the mount |
   | `MAX_UPLOAD_MB` | no | per-file cap, default 32 |
   | `WORKERS` | no | parallel sealing threads per gunicorn worker, default 2 |

   `PORT` is injected by Railway; the container binds it automatically.
5. **Generate a domain** (Settings → Networking). Health check path: `/healthz`.

First boot verifies the mask hash and runs nothing else: if `seal_master.png` does
not match the hash pinned in `seal_master.json`, the service refuses to start
rather than issue seals that are not the house standard.

## Sizing

Sealing is short, CPU-bound NumPy. A 4000 px master takes roughly a second on a
shared vCPU, and memory scales with the image, not the queue. Railway's smallest
instance handles a design team comfortably; raise `--workers` in the Dockerfile
CMD only if several people upload large batches at once.

## Routes

| Route | Purpose |
|---|---|
| `GET /` | the desk (locked until the access code is entered) |
| `POST /unlock` | exchange the access code for an HttpOnly session cookie |
| `POST /upload` | multipart, one or many files, sealing starts immediately |
| `GET /api/jobs` | queue and counts as JSON (the page polls this) |
| `GET /download/<id>` | the sealed master |
| `GET /manifest.jsonl` | the audit export, oldest first |
| `GET /healthz` | liveness, plus the running mask hash and version |

## Run it locally first

```bash
docker build -f desk/Dockerfile -t ghost-seal-desk:1.0.0 .
docker run --rm -p 8080:8080 \
  -e ACCESS_CODE=change-me \
  -e SESSION_SECRET="$(openssl rand -hex 32)" \
  -v "$PWD/.data:/data" \
  ghost-seal-desk:1.0.0
```

Then open `http://localhost:8080`, unlock, drop an image, and confirm the sealed
file from the CLI as an independent check:

```bash
python3 ghost_seal.py verify path/to/downloaded_sealed.png --source path/to/original.png
```

`artwork_untouched_outside_seal: true` and `machine_readable_provenance: true` is
the pass condition.

## Operating notes

- **Masters only.** Derive crops, resizes and thumbnails from the sealed file.
  Anything under 512 px on the short side is deliberately skipped, not stamped.
- **The volume is the record.** `manifest.jsonl` and the SQLite index on `/data`
  are the audit trail; back them up or ship them to a log store.
- **Access is a shared code, not accounts.** It exists because the desk holds
  unsealed originals. Put it behind your VPN or an identity proxy if you want per
  person access.
- **This desk is convenience, not enforcement.** The strong lane is still sealing
  on ingest plus `verify_tree.py --strict-metadata` in the release job. A desk that
  people must remember to visit will eventually be forgotten.
