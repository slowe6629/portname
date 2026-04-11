#!/usr/bin/env bash
# End-to-end portname check test on Arch Linux.
# Run inside an archlinux:latest container with the repo mounted at /portname.
#
#   docker run --rm -v $PWD:/portname archlinux:latest bash /portname/tests/docker/test_arch.sh

set -euo pipefail
export PORTNAME_SKIP_RESTART=1

echo "=== Installing dependencies (Arch) ==="
pacman -Sy --noconfirm python python-pip alsa-card-profiles

echo "=== Installing portname ==="
pip install --break-system-packages -e /portname --quiet

echo "=== Running unit tests ==="
cd /portname && python -m unittest discover -v tests/

# Run shared end-to-end test
source "$(dirname "$0")/test_common.sh"
