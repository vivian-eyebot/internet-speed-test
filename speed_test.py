#!/usr/bin/env python3
"""Run a speed test every 2 minutes for 2 hours on kiosk and test stand."""

import os
import time
import csv
import json
import subprocess
from datetime import datetime, timezone
import argparse
from typing import List, Optional

try:
    import kiosk_data_client as gcs
except Exception as _e:
    print(f"GCS benchmark unavailable ({_e}); running speed test only.")
    gcs = None


get_folder_name = lambda: datetime.now().strftime("%Y%b%d_%H_%M_%S")


class AutoSpeedTest:
    """Run speed_test.main() on a fixed interval until a total duration elapses."""

    def __init__(self, device:str, gcloud:bool, interval=5*60, duration=30*60*60):

        self.interval_seconds = interval   # default: 5 minutes
        self.duration_seconds = duration   # default: 30 hours, ~360 data points

        self.gcloud = gcloud

        self.start_time = None   # set when the run begins
        self.run_count = 0

        self.create_csv(device)


    def create_csv(self, device):
        """Create the csv files for kiosk and test stand"""

        try:
            os.mkdir(os.path.join(os.getcwd(), "data"))
            os.mkdir(os.path.join(os.getcwd(), "Test_Session_Images"))
        except FileExistsError:
            pass

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
                *(["gcs_upload_mbps", "gcs_download_mbps"] if self.gcloud else []),
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
    
    def clear_folder(self):
        for filename in os.listdir(gcs.LOCAL_IMAGE_DIR):
            file_path = os.path.join(gcs.LOCAL_IMAGE_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        print("[clean] clearing downloaded contents")
    

    def speed_test(self, timestamp):
        """Run the Ookla CLI and Gcloud test, then save to csv."""

        # Run Ookla speed test
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
            return

        if proc.returncode != 0:
            # CLI prints a JSON error on stdout, or a message on stderr.
            detail = (proc.stdout or proc.stderr or "").strip().replace("\n", " ")
            print(f"exit {proc.returncode}: {detail[:300]}")
            return

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            print(f"could not parse JSON: {e}")
            return

        server = data.get("server", {})
        packet_loss = round(data["packetLoss"], 2) if data.get("packetLoss") is not None else ""
        interface = data.get("interface", {})

        row = [
            timestamp,
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
        ]
        print(f"[log] saved {len(row)} data points from speedtest cli")

        # Run gcloud upload/download tests
        if self.gcloud:
            gcs_metrics = {}
            if gcs is not None:
                try:
                    gcs_metrics = gcs.main()
                except Exception as e:
                    print(f"GCS benchmark failed: {e}")

            row += [
                gcs_metrics.get("gcs_upload_mbps", ""),
                gcs_metrics.get("gcs_download_mbps", ""),
            ]

        self.write_row(row)


    def run_speed_tests(self):
        """
        Main loop logic.
        Run a test on the  :00 dot to sync up test on multiple devices.
        """

        self.start_time = time.monotonic()

        while not self.is_done():
            # Sleep until the next interval boundary on the wall clock. Both
            # devices share the same epoch reference, so they wake together.
            now = time.time()
            next_tick = (int(now) // self.interval_seconds + 1) * self.interval_seconds
            time.sleep(next_tick - now)

            self.run_count += 1
            timestamp = datetime.now()
            print(f"--- Run {self.run_count}:  {str(timestamp).split('.')[0]}---")

            try:
                self.speed_test(timestamp)
                self.clear_folder()     # clear Test_Session_Images/
                print(f"--- [finish] Run {self.run_count} in {str((datetime.now() - timestamp)).split('.')[0]}---")
            except Exception as e:
                print(f"Run {self.run_count} failed: {e}")
        
        print(f"\nFinished logging network speed for {self.duration_seconds / 3600} hours.")

def parse_args(argv: Optional[List[str]] = None):
    p = argparse.ArgumentParser(description="Run network speed test on a device.")
    p.add_argument("--device", type=str, required=True, help="Run this script on the kiosk ('Kiosk') or the test stand ('Stand')")
    p.add_argument("--gcloud", type=bool, required=True, help="True if testing on kiosk for gcloud upload/download")
    p.add_argument("--duration", type=int, required=False, help="Total duration in seconds to run the test for; default 30hrs")
    p.add_argument("--interval", type=int, required=False, help="Interval in seconds between network speed runs; default 5mins")
    return p.parse_args(argv)

def main(argv: Optional[List[str]] = None):

    args = parse_args(argv)

    # Only forward flags that were actually supplied so AutoSpeedTest's own
    # defaults apply; passing None would clobber them.
    kwargs = {}
    if args.interval is not None:
        kwargs["interval"] = args.interval
    if args.duration is not None:
        kwargs["duration"] = args.duration

    test = None
    try:
        test = AutoSpeedTest(device=args.device, gcloud=args.gcloud, **kwargs)
        test.run_speed_tests()
    except KeyboardInterrupt:
        print("\nCtrl+C received — closing devices")
        if test is not None:
            print(f"Logging stopped before {test.duration_seconds / 3600} hours.")
    finally:
        if test is not None:
            print(f"\nLogging saved to file: {test.csv_filename}")


if __name__ == "__main__":
    main()
