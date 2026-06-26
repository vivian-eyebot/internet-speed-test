# Internet Speed Test

Automated Ookla Speedtest and Gcloud upload/download test.

## Download Ookla speed test
Downloads the [Ookla Speedtest CLI](https://www.speedtest.net/apps/cli) build into `bin/speedtest`
```sh
./install_speedtest.sh
```

## Run the speed test

```sh
python3 speed_test.py --device testing_device --gcloud true_or_false
```
### Flags
```
--device DEVICE      Run this script on the kiosk ('Kiosk') or the test stand ('Stand')
--gcloud GCLOUD      True if testing on kiosk for gcloud upload/download
--duration DURATION  Total duration in seconds to run the test for; default 30hrs
--interval INTERVAL  Interval in seconds between network speed runs; default 5mins
```

## Looking at output data
```sh
cd data/2026Jun26_09_48_40 
```

## Gcloud bucket

- `internet-speed-test` - where all the test files exist
- `internet-speed-test/session-images/` - 60 images from a session to be downloaded
- `internet-speed-test/session-images-upload/` - where the 60 images will upload to each speed test run. Images overwrite each other per run. There are 67 images in total.

