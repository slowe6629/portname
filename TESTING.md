# Testing portname

## What CI covers

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR across three jobs:

### 1. Unit tests (`test`)
Runs on Python 3.8, 3.11, and 3.12. Covers all core logic including `check_and_reapply`,
name persistence, clobber detection, and rename/revert flows — no real distro needed.

### 2. Ubuntu integration (`integration`)
Runs on `ubuntu-latest` with a real `alsa-card-profile` install. Verifies the `.conf`
parser against actual system files and confirms `portname list` and `portname check`
exit gracefully when PipeWire is not running.

### 3. Docker end-to-end (`docker-integration`)
Runs `tests/docker/test_arch.sh` and `tests/docker/test_fedora.sh` inside
`archlinux:latest` and `fedora:latest` containers. This is the primary coverage for the
`NativeBackend` / `portname check` path since neither distro has `dpkg-divert`.

Each Docker test:
1. Installs `alsa-card-profiles` and portname inside the container
2. Runs the full unit test suite
3. Picks a real `.conf` file from `/usr/share/alsa-card-profile/mixer/paths/`
4. Renames a route and asserts the file was modified
5. Simulates a package-manager upgrade clobbering the file (`cp .orig -> .conf`)
6. Runs `portname check` and asserts the custom name was re-applied
7. Reverts with `portname revert --all` and asserts the original is restored

`PORTNAME_SKIP_RESTART=1` is set inside the scripts to bypass the `systemctl` call
since PipeWire is not running in the container.

## Running the Docker tests locally

Requires Docker installed and running.

```bash
# Arch
docker run --rm -v "$PWD:/portname" archlinux:latest \
  bash /portname/tests/docker/test_arch.sh

# Fedora
docker run --rm -v "$PWD:/portname" fedora:latest \
  bash /portname/tests/docker/test_fedora.sh
```

## Running unit tests locally

```bash
python3 -m unittest discover -v tests/
```
