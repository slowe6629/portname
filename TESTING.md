# Testing portname

## What the CI covers today

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR:

- **Unit tests** on Python 3.8, 3.11, and 3.12 — covers all core logic including
  `check_and_reapply`, name persistence, clobber detection, rename/revert flows.
- **Integration smoke tests** on `ubuntu-latest` with a real `alsa-card-profile`
  install — verifies the `.conf` parser against actual system files and confirms
  `portname list` and `portname check` exit gracefully when PipeWire is not running.

## What CI does NOT cover yet: Arch / Fedora Docker plan

The remaining gap is verifying `portname check` end-to-end on a non-Debian distro
where `dpkg-divert` is absent and the `NativeBackend` is actually used.

### Plan: Docker-based Arch / Fedora integration test

The idea is a self-contained shell script (or a second CI job) that:

1. Pulls `archlinux:latest` (or `fedora:latest`) and installs dependencies:
   ```
   # Arch
   pacman -Sy --noconfirm python alsa-card-profile

   # Fedora
   dnf install -y python3 alsa-utils
   ```

2. Installs portname inside the container:
   ```
   pip install -e /portname
   ```

3. Picks a real `.conf` file from `/usr/share/alsa-card-profile/mixer/paths/`,
   runs `portname rename <route> "Test Speaker"`, and asserts the file was modified.

4. Simulates a package-manager upgrade clobbering the file:
   ```
   cp <route>.conf.orig <route>.conf   # mimic overwrite by package manager
   ```

5. Runs `portname check` and asserts:
   - The `.conf` file contains `description = Test Speaker` again.
   - Exit code is 0.

6. Reverts with `portname revert --all` and asserts the original file is restored.

### Why it isn't wired into CI yet

- Docker-in-Docker on GitHub Actions works but requires `--privileged` or
  `docker buildx` setup; the added complexity wasn't worth it before the
  `check` command even existed.
- PipeWire is not running inside the container, so the test script should set
  `PORTNAME_SKIP_RESTART=1` to bypass the `systemctl` call in `restart_pipewire()`.
  This env var is already supported.

### Next steps to implement this

1. ~~Add `PORTNAME_SKIP_RESTART` env-var support to `core.restart_pipewire()`~~ — done.
2. Write `tests/docker/test_arch.sh` and `tests/docker/test_fedora.sh`.
3. Add a `docker` job to `.github/workflows/ci.yml` that builds the container
   and runs the scripts.

Track progress on this in the GitHub issue created alongside this file.
