#!/usr/bin/env python3
"""
runner.py — drains the Ghost Seal Desk queue using THE PINNED IMAGE.

The desk (the web tool) never seals anything itself: a JavaScript or WASM
reimplementation of the relief maths would drift from the image CI runs, and the
whole standard rests on the seal being identical everywhere. So the desk queues,
and this runner — running inside ghost-seal:<version> — does the work and
reports back the verbatim manifest line.

Run it wherever the pinned image runs (a cron box, a CI schedule, a small VM):

    GHOST_SEAL_DESK=https://ghost-seal-desk.higgsfield.ai \
    GHOST_SEAL_TOKEN=<runner token> \
      python3 runner.py --interval 10

    # inside the pinned image
    docker run --rm \
      -e GHOST_SEAL_DESK=... -e GHOST_SEAL_TOKEN=... \
      --entrypoint python3 ghost-seal:1.0.0 runner.py --interval 10

Only stdlib plus the seal module itself, so it adds nothing to the image.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import ghost_seal as GS

DESK = os.environ.get("GHOST_SEAL_DESK", "").rstrip("/")
TOKEN = os.environ.get("GHOST_SEAL_TOKEN", "")


def _request(method: str, path: str, *, body: bytes | None = None,
             content_type: str | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(f"{DESK}{path}", data=body, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def claim() -> dict | None:
    status, payload = _request("POST", "/api/runner/claim")
    if status == 204:
        return None
    if status != 200:
        raise RuntimeError(f"claim failed: HTTP {status} {payload[:300]!r}")
    return json.loads(payload)["job"]


def fetch_blob(path: str) -> bytes:
    status, payload = _request("GET", path)
    if status != 200:
        raise RuntimeError(f"blob fetch failed: HTTP {status} {payload[:300]!r}")
    return payload


def multipart(fields: dict[str, str], file: tuple[str, bytes] | None) -> tuple[bytes, str]:
    boundary = f"----ghostseal{uuid.uuid4().hex}"
    out = bytearray()
    for name, value in fields.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += f"{value}\r\n".encode()
    if file is not None:
        filename, blob = file
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        out += f"--{boundary}\r\n".encode()
        out += (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode()
        out += blob + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def complete(job_id: str, status: str, *, manifest: str = "", reason: str = "",
             file: tuple[str, bytes] | None = None) -> None:
    fields = {"job_id": job_id, "status": status}
    if manifest:
        fields["manifest"] = manifest
    if reason:
        fields["reason"] = reason
    body, ctype = multipart(fields, file)
    code, payload = _request("POST", "/api/runner/complete", body=body, content_type=ctype)
    if code != 200:
        raise RuntimeError(f"complete failed: HTTP {code} {payload[:300]!r}")


def process(job: dict) -> str:
    """Seal one job with the production applier. Returns a one-line log summary."""
    blob = fetch_blob(job["blob_url"])
    with tempfile.TemporaryDirectory(prefix="ghost-seal-") as work:
        stem, ext = os.path.splitext(job["filename"])
        src = os.path.join(work, job["filename"])
        dst = os.path.join(work, f"{stem}_sealed{ext or '.png'}")
        with open(src, "wb") as f:
            f.write(blob)

        # One manifest line per asset, written by the applier itself. We capture it
        # from the return value rather than re-deriving anything.
        record = GS.apply_seal(src, dst, quiet=True)
        status = record.get("status")

        if status == "sealed":
            with open(dst, "rb") as f:
                sealed = f.read()
            complete(job["id"], "sealed", manifest=json.dumps(record),
                     file=(os.path.basename(dst), sealed))
            return (f"sealed   {job['filename']} "
                    f"[{record['relief_mode']} ΔL={record['delta_L_applied']} "
                    f"r={record['correlation']}]")

        if status == "skipped":
            complete(job["id"], "skipped", manifest=json.dumps(record),
                     reason=str(record.get("reason") or "skipped"))
            return f"skipped  {job['filename']} — {record.get('reason')}"

        complete(job["id"], "error", manifest=json.dumps(record),
                 reason=str(record.get("reason") or "unknown applier state"))
        return f"error    {job['filename']} — {record.get('reason')}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain the Ghost Seal Desk queue")
    parser.add_argument("--interval", type=float, default=10.0,
                        help="seconds to wait when the queue is empty (default 10)")
    parser.add_argument("--once", action="store_true",
                        help="drain what is queued now, then exit (for cron / CI)")
    args = parser.parse_args()

    if not DESK or not TOKEN:
        print("set GHOST_SEAL_DESK and GHOST_SEAL_TOKEN", file=sys.stderr)
        return 2

    # Fail fast if this runtime cannot reproduce the house seal.
    _, digest = GS.load_master()
    print(f"[runner] desk={DESK} mask={digest[:12]}… version={GS.VERSION}")

    idle = 0
    while True:
        try:
            job = claim()
        except Exception as e:  # network / desk hiccup — back off, do not spin
            print(f"[runner] claim error: {e}", file=sys.stderr)
            time.sleep(min(60.0, args.interval * 3))
            continue

        if job is None:
            if args.once:
                print(f"[runner] queue empty, {idle} sealed this run")
                return 0
            time.sleep(args.interval)
            continue

        try:
            print("[runner] " + process(job))
            idle += 1
        except Exception as e:
            print(f"[runner] job {job['id']} failed: {e}", file=sys.stderr)
            try:
                complete(job["id"], "error", reason=f"runner exception: {e}")
            except Exception as inner:
                print(f"[runner] could not report failure: {inner}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
