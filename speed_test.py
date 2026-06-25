#!/usr/bin/env python3
"""Run one Ookla Speedtest and append the result to a CSV log.
"""

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve paths relative to this file so the script works regardless of the
# working directory the scheduler launches it from.
BASE_DIR = Path(__file__).resolve().parent
SPEEDTEST_BIN = BASE_DIR / "bin" / "speedtest"
CSV_PATH = BASE_DIR / "results.csv"

CSV_FIELDS = [
    "timestamp",
    "download_mbps",
    "upload_mbps",
    "ping_ms",
    "jitter_ms",
    "packet_loss_pct",
    "server_name",
    "server_location",
    "isp",
    "external_ip",
    "error",
]


def bandwidth_to_mbps(bytes_per_sec: float) -> float:
    """Ookla reports bandwidth in bytes/sec; Mbps is decimal megabits."""
    return round(bytes_per_sec * 8 / 1_000_000, 2)


def run_speedtest(show_all: bool = False) -> dict:
    """Run the Ookla CLI and return a flat dict row for the CSV.

    If show_all is True, also pretty-print the full parsed JSON to stdout.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {field: "" for field in CSV_FIELDS}
    row["timestamp"] = now

    if not SPEEDTEST_BIN.exists():
        row["error"] = f"speedtest binary not found at {SPEEDTEST_BIN}"
        return row

    try:
        proc = subprocess.run(
            [
                str(SPEEDTEST_BIN),
                "--accept-license",
                "--accept-gdpr",
                "--format=json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        row["error"] = "speedtest timed out after 120s"
        return row

    if proc.returncode != 0:
        # CLI prints a JSON error on stdout, or a message on stderr.
        detail = (proc.stdout or proc.stderr or "").strip().replace("\n", " ")
        row["error"] = f"exit {proc.returncode}: {detail[:300]}"
        return row

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        row["error"] = f"could not parse JSON: {e}"
        return row

    if show_all:
        print(json.dumps(data, indent=2, sort_keys=True))

    row["download_mbps"] = bandwidth_to_mbps(data["download"]["bandwidth"])
    row["upload_mbps"] = bandwidth_to_mbps(data["upload"]["bandwidth"])
    row["ping_ms"] = round(data["ping"]["latency"], 2)
    row["jitter_ms"] = round(data["ping"]["jitter"], 2)
    # packetLoss is only present on some servers/runs.
    if data.get("packetLoss") is not None:
        row["packet_loss_pct"] = round(data["packetLoss"], 2)
    server = data.get("server", {})
    row["server_name"] = server.get("name", "")
    row["server_location"] = server.get("location", "")
    row["isp"] = data.get("isp", "")
    row["external_ip"] = data.get("interface", {}).get("externalIp", "")
    return row


def append_row(row: dict) -> None:
    """Write speed test data to csv"""
    write_header = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    # Show all the avalible data
    show_all = any(arg in ("--show", "--show_all") for arg in sys.argv[1:])

    row = run_speedtest(show_all=show_all)
    append_row(row)

    if row["error"]:
        print(f"[{row['timestamp']}] ERROR: {row['error']}", file=sys.stderr)
        return 1
    
    print(
        f"[{row['timestamp']}] down={row['download_mbps']} Mbps "
        f"up={row['upload_mbps']} Mbps ping={row['ping_ms']} ms "
        f"({row['server_name']} / {row['server_location']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
