#!/usr/bin/env python3
"""GCS throughput benchmark — REPO-IMPORT version.

Measures real-world Google Cloud Storage download/upload throughput so it can be
cross-checked against the Ookla CLI numbers. It does NOT define its own GCS
client/upload code — it reuses the kiosk data-upload repo:
  - storage_client          (the authenticated client)
  - gcloudstorage_mv_library (the upload primitive)

Per tick (one shared folder, LOCAL_IMAGE_DIR, which starts empty):
  1. download test — pull the session images from GCS into LOCAL_IMAGE_DIR, timed
  2. upload test   — push those same images back up to a separate prefix, timed

The same images are reused for both directions. Local files are overwritten by
name on each download (no duplicates kept); we only care about throughput.
Download runs first so the folder is always populated before the upload test.

The repo's daemon update() loop is NEVER started here — we only import the module
(which runs its module-level credential load) and call its helper functions.
Requires the repo at KIOSK_REPO and the kiosk credentials, so this is kiosk-only.
main() returns the metrics dict speed_test.py merges into its CSV row.
"""

import os
import sys
import time
import importlib.util
import concurrent.futures

# ---------------------------------------------------------------------------
# Config.
# ---------------------------------------------------------------------------
GCS_BUCKET = "internet-speed-test"

# Shared local folder used for BOTH directions (starts empty; download fills it).
LOCAL_IMAGE_DIR = os.path.expanduser("~/internet-speed-test/Test_Session_Images")

DOWNLOAD_PREFIX = "session-images"          # bucket folder the images are pulled FROM
UPLOAD_DEST_PREFIX = "session-images-upload"  # bucket folder the images are pushed TO

MAX_WORKERS = 16                            # concurrency cap

KIOSK_REPO = "/opt/KioskDataUpload/assets"

# ---------------------------------------------------------------------------
# GCS primitives — REUSED from the kiosk data-upload repo (the whole point of
# this variant). We add the repo root to sys.path so the repo module's own
# `from lib.kiosk_api import *` resolves, then load KioskDataClient.py by its
# explicit file path. The explicit-path load avoids colliding with the local
# file of the same name (internet-speed-test/KioskDataClient.py).
#
# exec_module() runs the repo's module-level code (credential load +
# storage_client creation) but NOT its update() daemon loop — that only runs
# from KioskDataClient.start(), which we never call.
# ---------------------------------------------------------------------------
if KIOSK_REPO not in sys.path:
    sys.path.insert(0, KIOSK_REPO)

_spec = importlib.util.spec_from_file_location(
    "kiosk_repo_client", os.path.join(KIOSK_REPO, "KioskDataClient.py")
)
_kdc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_kdc)

storage_client = _kdc.storage_client          # reused authenticated client
_gcloud_upload = _kdc.gcloudstorage_mv_library  # reused upload primitive


def gcs_upload(bucket_name, local_path, dest_blob):
    """Upload one local file by reusing the repo's upload primitive."""
    _gcloud_upload(bucket_name, local_path, dest_blob)


def gcs_download(bucket_name, blob_name, local_path):
    """Download one blob (the repo has no download helper, so define one here
    using the reused, already-authenticated client)."""
    bucket = storage_client.bucket(bucket_name)
    bucket.blob(blob_name).download_to_filename(local_path)


# ---------------------------------------------------------------------------
# Throughput helpers.
# ---------------------------------------------------------------------------
def _mbps(total_bytes, elapsed_s):
    """Decimal megabits per second — same unit convention as the Ookla CLI."""
    if elapsed_s <= 0:
        return 0.0
    return round(total_bytes * 8 / 1_000_000 / elapsed_s, 2)


def _run_concurrent(fn, items):
    """Run fn(item) for every item across a thread pool; return the results.

    Raises if any task raises (the caller treats a failed batch as an invalid
    measurement rather than reporting a number computed from partial data).
    """
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(fn, item) for item in items]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    return results


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------
def run_download_test():
    """Download the session images into LOCAL_IMAGE_DIR; measure throughput.

    Lists everything under DOWNLOAD_PREFIX/ and downloads it concurrently,
    overwriting local files by name (we keep no duplicates — only the speed
    matters). This also (re)populates the folder for the upload test.
    """
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)
    blobs = [
        b
        for b in storage_client.list_blobs(GCS_BUCKET, prefix=f"{DOWNLOAD_PREFIX}/")
        if not b.name.endswith("/")
    ]

    if not blobs:
        print(f"[download] no blobs under {DOWNLOAD_PREFIX}/; skipping download test")
        return {"gcs_download_mbps": "", "gcs_download_bytes": 0, "gcs_download_files": 0}

    total_bytes = sum((b.size or 0) for b in blobs)

    def _download(blob):
        rel = blob.name[len(DOWNLOAD_PREFIX) + 1:]
        local = os.path.join(LOCAL_IMAGE_DIR, rel)
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        blob.download_to_filename(local)

    start = time.monotonic()
    _run_concurrent(_download, blobs)
    elapsed = time.monotonic() - start

    mbps = _mbps(total_bytes, elapsed)
    print(f"[download] {len(blobs)} files, {total_bytes / 1e6:.1f} MB in {elapsed:.2f}s -> {mbps} Mbps")
    return {"gcs_download_mbps": mbps, "gcs_download_bytes": total_bytes, "gcs_download_files": len(blobs)}


def run_upload_test():
    """Upload everything in LOCAL_IMAGE_DIR to UPLOAD_DEST_PREFIX; measure throughput.

    Walks the folder recursively and mirrors each file's relative path into the
    destination prefix, so the upload set matches what the download test just
    fetched.
    """
    images = []
    if os.path.isdir(LOCAL_IMAGE_DIR):
        for root, _dirs, files in os.walk(LOCAL_IMAGE_DIR):
            images.extend(os.path.join(root, f) for f in files)
        images.sort()

    if not images:
        print(f"[upload] no images in {LOCAL_IMAGE_DIR}; skipping upload test")
        return {"gcs_upload_mbps": "", "gcs_upload_bytes": 0, "gcs_upload_files": 0}

    total_bytes = sum(os.path.getsize(p) for p in images)

    def _upload(path):
        rel = os.path.relpath(path, LOCAL_IMAGE_DIR)
        gcs_upload(GCS_BUCKET, path, f"{UPLOAD_DEST_PREFIX}/{rel}")

    start = time.monotonic()
    _run_concurrent(_upload, images)
    elapsed = time.monotonic() - start

    mbps = _mbps(total_bytes, elapsed)
    print(f"[upload] {len(images)} files, {total_bytes / 1e6:.1f} MB in {elapsed:.2f}s -> {mbps} Mbps")
    return {"gcs_upload_mbps": mbps, "gcs_upload_bytes": total_bytes, "gcs_upload_files": len(images)}


def main(argv=None):
    """Download first (populates the folder), then upload the same images.

    Each test is isolated so one failure doesn't block the other. Returns a flat
    metrics dict; speed_test.py reads gcs_download_mbps and gcs_upload_mbps.
    """
    results = {}
    for name, fn in (("download", run_download_test), ("upload", run_upload_test)):
        try:
            results.update(fn())
        except Exception as e:  # keep the other test (and the speed loop) alive
            print(f"[{name}] failed: {e}")
    return results


if __name__ == "__main__":
    main()
