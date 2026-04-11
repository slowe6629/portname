#!/usr/bin/env bash
# End-to-end portname check test on Arch Linux.
# Run inside an archlinux:latest container with the repo mounted at /portname.
#
#   docker run --rm -v $PWD:/portname archlinux:latest bash /portname/tests/docker/test_arch.sh

set -euo pipefail
export PORTNAME_SKIP_RESTART=1

echo "=== Installing dependencies (Arch) ==="
pacman -Sy --noconfirm python alsa-card-profiles

echo "=== Installing portname ==="
pip install -e /portname --quiet

echo "=== Running unit tests ==="
python -m unittest discover -v /portname/tests/

# Run shared end-to-end test
source "$(dirname "$0")/test_common.sh"
