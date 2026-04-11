#!/usr/bin/env bash
# End-to-end portname check test on Fedora.
# Run inside a fedora:latest container with the repo mounted at /portname.
#
#   docker run --rm -v $PWD:/portname fedora:latest bash /portname/tests/docker/test_fedora.sh

set -euo pipefail
export PORTNAME_SKIP_RESTART=1

echo "=== Installing dependencies (Fedora) ==="
dnf install -y python3 python3-pip alsa-card-profiles

echo "=== Installing portname ==="
pip3 install -e /portname --quiet

echo "=== Running unit tests ==="
python3 -m unittest discover -v /portname/tests/

# Run shared end-to-end test
source "$(dirname "$0")/test_common.sh"
