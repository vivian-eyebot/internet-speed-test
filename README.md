# internet-speed-test

Runs an Ookla Speedtest every 2 minutes for 2 hours and logs to a CSV.

## Download Ookla speed test
Downloads the [Ookla Speedtest CLI](https://www.speedtest.net/apps/cli) build into `bin/speedtest`
```sh
./install_speedtest.sh
```

## Run the speed test

```sh
python3 speed_test.py --device testing_device
```

## Looking at output data
```sh
cd data/ 
```