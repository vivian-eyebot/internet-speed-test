#!/usr/bin/env python3
"""Run a speed test every 2 minutes for 2 hours on kiosk and test stand."""

import os
import time
import csv
import json
import subprocess
from datetime import datetime, timezone
import argparse

import speed_test



get_folder_name = lambda: datetime.now().strftime("%Y%b%d_%H_%M_%S")


class AutoSpeedTest:
    """Run speed_test.main() on a fixed interval until a total duration elapses."""

    def __init__(self, device:str):

        self.interval_seconds = 1 * 60   # 2 minutes
        self.duration_seconds = 2 * 60   #2 hours

        self.start_time = None   # set when the run begins
        self.run_count = 0

        self.create_csv(device)


    def create_csv(self, device):
        """Create the csv files for kiosk and test stand"""

        folder_time = get_folder_name()
        self.folder_path = os.path.join(os.getcwd(), "data", folder_time)

        try:
            os.mkdir(self.folder_path)
        except FileExistsError:
            print("File already exists. Rerun.")

        self.csv_filename = os.path.join(self.folder_path, f"{device}_Network_Data.csv")

        with open(self.csv_filename, 'w', newline='') as f:
            csv.writer(f).writerow([
                "timestamp",
                "download_mbps", "upload_mbps",
                "ping_ms", "jitter_ms", "packet_loss_pct",
                "server_name", "server_location",
                "isp", "external_ip",
                "is_vpn",
            ])

        print(f"Started recording to {self.csv_filename}")


    def write_row(self, row):
        with open(self.csv_filename, 'a', newline='') as f:
            csv.writer(f).writerow(row)

    @staticmethod
    def bandwidth_to_mbps(bytes_per_sec: float) -> float:
        """Ookla reports bandwidth in bytes/sec; Mbps is decimal megabits."""
        return round(bytes_per_sec * 8 / 1_000_000, 2)


    def is_done(self):
        """True once the next scheduled tick would fall outside the window."""
        next_run = self.run_count * self.interval_seconds
        return next_run >= self.duration_seconds
    

    def speed_test(self):
        """Run the Ookla CLI and return a flat dict row for the CSV.

        If show_all is True, also pretty-print the full parsed JSON to stdout.
        """

        try:
            proc = subprocess.run(
                [
                    str(os.path.join(os.getcwd(), "bin", "speedtest")),
                    "--accept-license",
                    "--accept-gdpr",
                    "--format=json",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print("Speedtest timed out after 120s")

        if proc.returncode != 0:
            # CLI prints a JSON error on stdout, or a message on stderr.
            detail = (proc.stdout or proc.stderr or "").strip().replace("\n", " ")
            print(f"exit {proc.returncode}: {detail[:300]}")

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            print(f"could not parse JSON: {e}")
            return

        server = data.get("server", {})
        packet_loss = round(data["packetLoss"], 2) if data.get("packetLoss") is not None else ""
        interface = data.get("interface", {})

        self.write_row([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            self.bandwidth_to_mbps(data["download"]["bandwidth"]),
            self.bandwidth_to_mbps(data["upload"]["bandwidth"]),
            round(data["ping"]["latency"], 2),
            round(data["ping"]["jitter"], 2),
            packet_loss,
            server.get("name", ""),
            server.get("location", ""),
            data.get("isp", ""),
            interface.get("externalIp", ""),
            interface.get("isVpn", False),
        ])


    def run_speed_tests(self):
        """Loop: wait until the next wall-clock tick, then run a test.

        Ticks are anchored to the wall clock (multiples of the interval since
        the Unix epoch) rather than to this process's start time, so two
        devices fire on the same :00 boundaries (12:00:00, 12:02:00, ...) and
        their timestamps line up regardless of when each script was launched.
        """

        self.start_time = time.monotonic()

        while not self.is_done():
            # Sleep until the next interval boundary on the wall clock. Both
            # devices share the same epoch reference, so they wake together.
            now = time.time()
            next_tick = (int(now) // self.interval_seconds + 1) * self.interval_seconds
            time.sleep(next_tick - now)

            self.run_count += 1
            print(f"--- Run {self.run_count}:  {datetime.now().time()}---")
            self.speed_test()  # runs one test, appends a row to results.csv
        
        print(f"\nFinished logging network speed for {self.duration_seconds / 3600} hours.")


def main():
    parser = argparse.ArgumentParser(description="Run network speed test on a device.")
    parser.add_argument("--device", type=str, required=True, help="Run this script on the kiosk ('Kiosk') or the test stand ('Stand')")
    args = parser.parse_args()

    try:
        test = AutoSpeedTest(device=args.device)
        test.run_speed_tests()
    except KeyboardInterrupt:
        print("Ctrl+C received — closing devices")
    finally:
        print(f"\nLogging saved to file: {test.csv_filename}")


if __name__ == "__main__":
    main()
