#!/usr/bin/env bash
# Download the correct Ookla Speedtest CLI build for THIS machine into
# ./bin/speedtest. Works on macOS and on Linux / Raspberry Pi — it picks the
# build from the OS (uname -s) and CPU (uname -m), so you don't have to guess
# macosx-universal vs linux-aarch64 vs linux-armhf.
#
# Usage:  ./install_speedtest.sh
set -euo pipefail

VERSION="1.2.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"

os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
  Darwin)
    # One universal build covers both Intel and Apple Silicon Macs.
    pkg="macosx-universal"
    ;;
  Linux)
    case "$arch" in
      aarch64 | arm64)         pkg="linux-aarch64" ;;  # 64-bit Raspberry Pi OS (Pi 3/4/5)
      armv7l | armv6l | armhf) pkg="linux-armhf"   ;;  # 32-bit Raspberry Pi OS
      x86_64 | amd64)          pkg="linux-x86_64"  ;;
      i386 | i686)             pkg="linux-i386"    ;;
      *)
        echo "Unsupported Linux architecture: $arch" >&2
        echo "See https://www.speedtest.net/apps/cli for available builds." >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $os (this script handles macOS and Linux)" >&2
    echo "See https://www.speedtest.net/apps/cli for available builds." >&2
    exit 1
    ;;
esac

url="https://install.speedtest.net/app/cli/ookla-speedtest-${VERSION}-${pkg}.tgz"
echo "Detected: $os / $arch  ->  $pkg"
echo "Downloading: $url"

mkdir -p "$BIN_DIR"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl -fsSL -o "$tmp" "$url"
tar -xzf "$tmp" -C "$BIN_DIR" speedtest
chmod +x "$BIN_DIR/speedtest"

echo "Installed: $BIN_DIR/speedtest"
"$BIN_DIR/speedtest" --version
