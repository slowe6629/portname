#!/usr/bin/env bash
# End-to-end portname check test on Fedora.
# Run inside a fedora:latest container with the repo mounted at /portname.
#
#   docker run --rm -v $PWD:/portname fedora:latest bash /portname/tests/docker/test_fedora.sh

set -euo pipefail
export PORTNAME_SKIP_RESTART=1

echo "=== Installing dependencies (Fedora) ==="
# alsa-card-profiles is a subpackage of pipewire on Fedora 41+
dnf install -y python3 python3-pip pipewire-alsa

echo "=== Installing portname ==="
pip3 install --break-system-packages -e /portname --quiet

echo "=== Running unit tests ==="
cd /portname && python3 -m unittest discover -v tests/

# Run shared end-to-end test
source "$(dirname "$0")/test_common.sh"
