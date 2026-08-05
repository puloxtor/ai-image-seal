#!/usr/bin/env python3
"""
Ghost Seal Desk — self-hosted single service (Railway / any Docker host).

Why this shape: on a container host the seal runs IN THIS PROCESS using the
production applier and the pinned mask, so what the desk returns is what CI
returns. There is no JavaScript reimplementation anywhere in the request path,
and therefore nothing that can drift from the house standard.

Environment
  ACCESS_CODE      required — the shared team code that unlocks the desk
  SESSION_SECRET   optional — HMAC key for the session cookie (random if unset,
                   which simply means sessions end at redeploy)
  DATA_DIR         optional — where originals, sealed masters, the SQLite index
                   and manifest.jsonl live. Default /data (mount a volume!)
  MAX_UPLOAD_MB    optional — per-file cap, default 32
  WORKERS          optional — parallel sealing threads, default 2

Routes
  GET  /                  the desk
  POST /unlock            exchange the access code for a session cookie
  POST /upload            multipart, one or many files
  GET  /api/jobs          queue + counts as JSON (the page polls this)
  GET  /download/<id>     the sealed master
  GET  /manifest.jsonl    the audit export
  GET  /healthz           liveness for the platform
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import (
    Flask,
    abort,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
)

import ghost_seal as GS

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "32"))
WORKERS = int(os.environ.get("WORKERS", "2"))
SESSION_TTL = 12 * 60 * 60
COOKIE = "gsd_session"
ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

INCOMING = DATA_DIR / "incoming"
MASTERS = DATA_DIR / "masters"
DB_PATH = DATA_DIR / "desk.sqlite3"
MANIFEST = DATA_DIR / "manifest.jsonl"

for directory in (INCOMING, MASTERS):
    directory.mkdir(parents=True, exist_ok=True)

# The applier appends its own manifest lines here too, so the CLI and the desk
# share one audit trail.
os.environ.setdefault("GHOST_SEAL_MANIFEST", str(MANIFEST))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024 * 40
pool = ThreadPoolExecutor(max_workers=WORKERS)
_db_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS seal_jobs (
  id            TEXT PRIMARY KEY,
  filename      TEXT NOT NULL,
  size          INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'queued',
  incoming_path TEXT NOT NULL,
  output_path   TEXT,
  output_name   TEXT,
  reason        TEXT,
  manifest      TEXT,
  correlation   REAL,
  relief_mode   TEXT,
  delta_l       REAL,
  seal_geometry TEXT,
  src_sha256    TEXT,
  dst_sha256    TEXT,
  mask_sha256   TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seal_jobs_created ON seal_jobs (created_at DESC);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _db_lock, connect() as conn:
        conn.executescript(SCHEMA)


def write(sql: str, params: tuple = ()) -> None:
    with _db_lock, connect() as conn:
        conn.execute(sql, params)
        conn.commit()


def read_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute(sql, params))


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- session ----
def sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_cookie(response):
    expires = int(time.time()) + SESSION_TTL
    payload = f"desk.{expires}"
    response.set_cookie(
        COOKIE,
        f"{payload}.{sign(payload)}",
        max_age=SESSION_TTL,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return response


def unlocked() -> bool:
    raw = request.cookies.get(COOKIE, "")
    parts = raw.split(".")
    if len(parts) != 3:
        return False
    scope, expires, signature = parts
    if scope != "desk" or not expires.isdigit() or int(expires) < time.time():
        return False
    return hmac.compare_digest(signature, sign(f"{scope}.{expires}"))


def require_unlocked() -> None:
    if not unlocked():
        abort(401)


# ------------------------------------------------------------------ sealing ---
def safe_name(name: str) -> str:
    base = os.path.basename(name or "file").replace("\\", "_")
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)
    return cleaned[-120:] or "file"


def seal_job(job_id: str) -> None:
    """Runs in a worker thread: the production applier, unmodified."""
    rows = read_all("SELECT * FROM seal_jobs WHERE id = ?", (job_id,))
    if not rows:
        return
    job = rows[0]
    write("UPDATE seal_jobs SET status='running', updated_at=? WHERE id=?", (now(), job_id))

    src = Path(job["incoming_path"])
    stem, ext = os.path.splitext(job["filename"])
    out_dir = MASTERS / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{stem}_sealed{ext or '.png'}"

    try:
        record = GS.apply_seal(str(src), str(dst), quiet=True)
    except Exception as exc:  # a bad file should fail one job, not the service
        write(
            "UPDATE seal_jobs SET status='error', reason=?, updated_at=? WHERE id=?",
            (f"{type(exc).__name__}: {exc}", now(), job_id),
        )
        return

    status = record.get("status")
    seal = record.get("seal") or []
    geometry = f"{seal[2]}px @ {seal[0]},{seal[1]}" if len(seal) == 3 else None

    write(
        """UPDATE seal_jobs
              SET status=?, output_path=?, output_name=?, reason=?, manifest=?,
                  correlation=?, relief_mode=?, delta_l=?, seal_geometry=?,
                  src_sha256=?, dst_sha256=?, mask_sha256=?, updated_at=?
            WHERE id=?""",
        (
            "sealed" if status == "sealed" else ("skipped" if status == "skipped" else "error"),
            str(dst) if status == "sealed" else None,
            dst.name if status == "sealed" else None,
            record.get("reason"),
            json.dumps(record),
            record.get("correlation"),
            record.get("relief_mode"),
            record.get("delta_L_applied"),
            geometry,
            record.get("src_sha256"),
            record.get("dst_sha256"),
            record.get("mask_sha256"),
            now(),
            job_id,
        ),
    )


# ------------------------------------------------------------------- routes ---
@app.get("/healthz")
def healthz():
    return jsonify(
        ok=True,
        version=GS.VERSION,
        mask=GS.sha256_file(GS.MASTER)[:12],
        spec=GS.SPEC["name"],
    )


@app.get("/")
def index():
    return render_template(
        "index.html",
        unlocked=unlocked(),
        mask=GS.sha256_file(GS.MASTER),
        version=GS.VERSION,
        spec=GS.SPEC,
        max_mb=MAX_UPLOAD_MB,
        error=request.args.get("error"),
    )


@app.post("/unlock")
def unlock():
    if not ACCESS_CODE:
        return redirect("/?error=The+desk+has+no+ACCESS_CODE+configured.")
    code = (request.form.get("code") or "").strip()
    if not hmac.compare_digest(code, ACCESS_CODE):
        return redirect("/?error=That+code+does+not+match.")
    return issue_cookie(redirect("/"))


@app.post("/upload")
def upload():
    require_unlocked()
    files = request.files.getlist("files")
    if not files:
        return jsonify(ok=False, message="No files were attached."), 400

    accepted, rejected = [], []
    for storage in files:
        filename = safe_name(storage.filename or "")
        extension = os.path.splitext(filename)[1].lower()
        if extension not in ALLOWED:
            rejected.append({"filename": filename, "reason": f"unsupported type ({extension or 'none'})"})
            continue

        job_id = str(uuid.uuid4())
        target_dir = INCOMING / job_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        storage.save(target)
        size = target.stat().st_size

        if size == 0:
            target.unlink(missing_ok=True)
            rejected.append({"filename": filename, "reason": "empty file"})
            continue
        if size > MAX_UPLOAD_MB * 1024 * 1024:
            target.unlink(missing_ok=True)
            rejected.append({"filename": filename, "reason": f"larger than {MAX_UPLOAD_MB} MB"})
            continue

        stamp = now()
        write(
            """INSERT INTO seal_jobs (id, filename, size, status, incoming_path, created_at, updated_at)
               VALUES (?, ?, ?, 'queued', ?, ?, ?)""",
            (job_id, filename, size, str(target), stamp, stamp),
        )
        pool.submit(seal_job, job_id)
        accepted.append({"id": job_id, "filename": filename, "size": size})

    return jsonify(ok=True, accepted=accepted, rejected=rejected)


@app.get("/api/jobs")
def api_jobs():
    require_unlocked()
    rows = read_all(
        """SELECT id, filename, size, status, output_name, reason, correlation,
                  relief_mode, delta_l, seal_geometry, created_at
             FROM seal_jobs ORDER BY created_at DESC LIMIT 120"""
    )
    counts: dict[str, int] = {}
    for row in read_all("SELECT status, COUNT(*) AS n FROM seal_jobs GROUP BY status"):
        counts[row["status"]] = row["n"]
    return jsonify(ok=True, jobs=[dict(r) for r in rows], counts=counts)


@app.get("/download/<job_id>")
def download(job_id: str):
    require_unlocked()
    rows = read_all("SELECT output_path, output_name FROM seal_jobs WHERE id=?", (job_id,))
    if not rows or not rows[0]["output_path"]:
        abort(404)
    path = Path(rows[0]["output_path"])
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=rows[0]["output_name"])


@app.get("/manifest.jsonl")
def manifest():
    require_unlocked()
    lines = [
        row["manifest"].strip()
        for row in read_all(
            "SELECT manifest FROM seal_jobs WHERE manifest IS NOT NULL ORDER BY created_at ASC"
        )
        if row["manifest"]
    ]
    body = ("\n".join(lines) + "\n") if lines else ""
    response = make_response(body)
    response.headers["Content-Type"] = "application/x-ndjson; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="ghost-seal-manifest.jsonl"'
    return response


@app.errorhandler(401)
def unauthorized(_):
    return jsonify(ok=False, code="locked", message="Enter the team access code."), 401


@app.after_request
def harden(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


init_db()

# Fail loudly at boot if this runtime cannot reproduce the house seal: a mask that
# does not match the pinned hash makes every seal it applies unauthorised.
GS.load_master()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
