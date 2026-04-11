"""Core business logic for portname: reading devices, renaming ports, reverting."""

import json
import logging
import os
import pwd
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

_DEFAULT_PATHS_DIR = "/usr/share/alsa-card-profile/mixer/paths"
_STATE_FILE = "/var/lib/portname/state.json"

# Allow override for testing, but ignore it when running as root to prevent
# a malicious env var from redirecting file operations during privilege escalation.
if os.geteuid() == 0:
    PATHS_DIR = _DEFAULT_PATHS_DIR
else:
    PATHS_DIR = os.environ.get("PORTNAME_PATHS_DIR", _DEFAULT_PATHS_DIR)

# Port names must be reasonable: 1-64 chars, no control characters
_VALID_NAME_RE = re.compile(r"^[^\x00-\x1f]{1,64}$")


class DpkgDivertBackend:
    """File-protection backend using dpkg-divert (Debian/Ubuntu only)."""

    def add(self, path, name=None):
        """Register a diversion: atomically move path -> path.orig."""
        try:
            subprocess.run(
                ["dpkg-divert", "--local", "--rename", "--divert", path + ".orig", "--add", path],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"dpkg-divert failed: {e.stderr.strip() or 'unknown error'}")

    def remove(self, path):
        """Remove the diversion and restore path.orig -> path."""
        try:
            subprocess.run(
                ["dpkg-divert", "--local", "--rename", "--divert", path + ".orig", "--remove", path],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"dpkg-divert revert failed: {e.stderr.strip() or 'unknown error'}")

    def list_paths(self):
        """Return all locally-diverted file paths (original locations, not .orig)."""
        result = subprocess.run(
            ["dpkg-divert", "--list"], capture_output=True, text=True
        )
        paths = []
        for line in result.stdout.splitlines():
            if "local diversion" not in line:
                continue
            parts = line.split()
            try:
                idx = parts.index("of")
                paths.append(parts[idx + 1])
            except (ValueError, IndexError):
                continue
        return paths


class NativeBackend:
    """Distro-agnostic backend: direct filesystem operations + JSON state file.

    On non-Debian systems there is no package-manager hook to protect the
    modified files from being overwritten by an upgrade; that is a known
    limitation.  Everything else (backup, restore, tracking) works identically.
    """

    def __init__(self, state_file=_STATE_FILE):
        self._state_file = state_file

    def _load(self):
        try:
            with open(self._state_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"diversions": {}}

    def _save(self, state):
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        tmp = self._state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, self._state_file)

    def add(self, path, name=None):
        """Back up path -> path.orig and record the diversion."""
        backup = path + ".orig"
        try:
            os.rename(path, backup)
        except OSError as e:
            raise RuntimeError(f"Failed to back up {path}: {e}")
        state = self._load()
        state["diversions"][path] = {"backup": backup, "name": name}
        self._save(state)

    def update_name(self, path, name):
        """Update the stored custom name for an already-diverted path."""
        state = self._load()
        if path in state["diversions"]:
            state["diversions"][path]["name"] = name
            self._save(state)

    def get_custom_name(self, path):
        """Return the stored custom name for a diverted path, or None."""
        return self._load()["diversions"].get(path, {}).get("name")

    def remove(self, path):
        """Restore path.orig -> path and remove the diversion record."""
        backup = path + ".orig"
        try:
            if os.path.exists(backup):
                os.rename(backup, path)
        except OSError as e:
            raise RuntimeError(f"Failed to restore {path}: {e}")
        state = self._load()
        state["diversions"].pop(path, None)
        self._save(state)

    def list_paths(self):
        """Return all diverted file paths recorded in the state file."""
        return list(self._load()["diversions"].keys())


_divert_backend = None


def _get_divert_backend():
    """Return the active divert backend, auto-detected from available tools."""
    global _divert_backend
    if _divert_backend is None:
        if shutil.which("dpkg-divert"):
            _divert_backend = DpkgDivertBackend()
        else:
            _divert_backend = NativeBackend()
    return _divert_backend


def _set_divert_backend(backend):
    """Override the active divert backend. For testing only."""
    global _divert_backend
    _divert_backend = backend


def validate_port_name(name):
    """Validate a port display name. Raises ValueError if invalid."""
    if not name or not name.strip():
        raise ValueError("Port name cannot be empty")
    name = name.strip()
    if not _VALID_NAME_RE.match(name):
        raise ValueError("Port name must be 1-64 characters with no control characters")
    return name


def get_devices():
    """Get all ALSA audio devices and their routes from PipeWire.

    Returns a list of dicts:
        [{"device_name": str, "device_description": str, "alsa_card": str,
          "routes": [{"name": str, "description": str, "direction": str, "available": str}]}]
    """
    log.debug("Discovering audio devices via pw-dump")
    if not shutil.which("pw-dump"):
        raise RuntimeError(
            "pw-dump not found. Is PipeWire installed?\n"
            "Install with: sudo apt install pipewire"
        )

    try:
        result = subprocess.run(
            ["pw-dump"], capture_output=True, text=True, check=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        log.error("pw-dump timed out")
        raise RuntimeError("pw-dump timed out — PipeWire may not be running")
    except subprocess.CalledProcessError as e:
        log.error("pw-dump failed: %s", e.stderr.strip())
        raise RuntimeError(f"pw-dump failed: {e.stderr.strip() or 'unknown error'}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        log.error("pw-dump returned invalid JSON")
        raise RuntimeError("pw-dump returned invalid JSON — PipeWire may be misconfigured")

    devices = []
    for obj in data:
        props = obj.get("info", {}).get("props", {})
        if props.get("device.api") != "alsa":
            continue
        if "device.name" not in props:
            continue

        params = obj.get("info", {}).get("params", {})
        enum_routes = params.get("EnumRoute", [])
        if not enum_routes:
            continue

        routes = []
        for route in enum_routes:
            route_name = route.get("name", "")
            # Only include routes that have a corresponding path file
            path_file = os.path.join(PATHS_DIR, f"{route_name}.conf")
            orig_file = path_file + ".orig"
            if not os.path.exists(path_file) and not os.path.exists(orig_file):
                continue

            routes.append({
                "name": route_name,
                "description": route.get("description", route_name),
                "direction": route.get("direction", "Unknown"),
                "available": route.get("available", "unknown"),
            })

        if routes:
            devices.append({
                "device_name": props.get("device.name", ""),
                "device_description": props.get("device.description", props.get("alsa.card_name", "Unknown")),
                "alsa_card": str(props.get("alsa.card", "")),
                "routes": routes,
            })

    log.info("Found %d device(s) with %d total route(s)",
             len(devices), sum(len(d["routes"]) for d in devices))
    return devices


def get_path_file(route_name):
    """Return the full path to the ALSA path config file for a route."""
    if ".." in route_name or "/" in route_name or "\\" in route_name:
        raise ValueError(f"Invalid route name: {route_name}")
    path = os.path.join(PATHS_DIR, f"{route_name}.conf")
    if not os.path.exists(path) and not os.path.exists(path + ".orig"):
        raise FileNotFoundError(f"No path file found for route '{route_name}'")
    return path


def is_renamed(route_name):
    """Check if a port has been renamed (backup .orig file is present)."""
    path = get_path_file(route_name)
    return os.path.exists(path + ".orig")


def get_original_description(route_name):
    """Get the original description key/value from the .orig file."""
    path = get_path_file(route_name)
    orig = path + ".orig"
    if not os.path.exists(orig):
        return None
    return _read_description(orig)


def _read_description(filepath):
    """Read the description or description-key from a path file's [General] section."""
    in_general = False
    try:
        with open(filepath) as f:
            for line in f:
                stripped = line.strip()
                if stripped == "[General]":
                    in_general = True
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    if in_general:
                        break
                    continue
                if in_general:
                    if stripped.startswith("description ="):
                        return stripped.split("=", 1)[1].strip()
                    if stripped.startswith("description-key ="):
                        return stripped.split("=", 1)[1].strip()
    except (OSError, UnicodeDecodeError):
        return None
    return None


def _modify_description(orig_path, new_description):
    """Read a path file and return modified content with a new description."""
    try:
        with open(orig_path) as f:
            lines = f.readlines()
    except OSError as e:
        raise RuntimeError(f"Cannot read path file {orig_path}: {e}")

    in_general = False
    found = False
    result = []

    for line in lines:
        stripped = line.strip()
        if stripped == "[General]":
            in_general = True
            result.append(line)
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_general = False
            result.append(line)
        elif in_general and not found and (
            stripped.startswith("description-key") or stripped.startswith("description")
        ):
            result.append(f"description = {new_description}\n")
            found = True
        else:
            result.append(line)

    if not found:
        raise RuntimeError(
            f"Could not find description field in [General] section of {orig_path}. "
            "The file may be corrupted or in an unexpected format."
        )

    return "".join(result)


def rename_port(route_name, new_name):
    """Rename an audio port. Must be run as root."""
    if os.geteuid() != 0:
        raise PermissionError("Must be run as root")

    new_name = validate_port_name(new_name)
    path = get_path_file(route_name)
    log.info("Renaming port '%s' to '%s'", route_name, new_name)
    log.debug("Path file: %s", path)

    # Back up the original file if not already done
    backend = _get_divert_backend()
    if not is_renamed(route_name):
        log.debug("Backing up %s", path)
        backend.add(path, new_name)
    elif isinstance(backend, NativeBackend):
        backend.update_name(path, new_name)

    # Read from .orig, write modified version to the main path
    content = _modify_description(path + ".orig", new_name)
    try:
        with open(path, "w") as f:
            f.write(content)
    except OSError as e:
        log.error("Cannot write to %s: %s", path, e)
        raise RuntimeError(f"Cannot write to {path}: {e}")

    restart_pipewire()
    log.info("Port '%s' renamed successfully", route_name)


def revert_port(route_name):
    """Revert a renamed port to its original name. Must be run as root."""
    if os.geteuid() != 0:
        raise PermissionError("Must be run as root")

    path = get_path_file(route_name)
    log.info("Reverting port '%s'", route_name)

    if not is_renamed(route_name):
        raise ValueError(f"Port '{route_name}' has not been renamed")

    # Remove our modified copy
    if os.path.exists(path):
        os.remove(path)

    # Restore original (moves path.orig -> path)
    log.debug("Restoring original file for %s", path)
    _get_divert_backend().remove(path)

    restart_pipewire()
    log.info("Port '%s' reverted successfully", route_name)


def revert_all():
    """Revert all renamed ports. Must be run as root."""
    if os.geteuid() != 0:
        raise PermissionError("Must be run as root")

    reverted = []
    for path in _get_divert_backend().list_paths():
        if PATHS_DIR not in path:
            continue
        route_name = os.path.basename(path).replace(".conf", "")
        revert_port(route_name)
        reverted.append(route_name)
    return reverted


def get_all_renamed():
    """Return a list of all currently renamed route names."""
    renamed = []
    for path in _get_divert_backend().list_paths():
        if PATHS_DIR in path:
            renamed.append(os.path.basename(path).replace(".conf", ""))
    return renamed


def repair_distrib_diversions():
    """Fix broken state left by old versions that used dpkg-divert without --divert.

    On some systems (e.g. Linux Mint), dpkg-divert defaults to a .distrib suffix
    instead of .orig. The old code assumed .orig, so failed renames left .distrib
    files behind with an active diversion — making ports vanish from the list.

    This scans for those orphaned diversions, removes them, and restores the
    original .conf files. Only relevant on Debian/Ubuntu; returns [] elsewhere.
    Must be run as root.

    Returns a list of repaired route names.
    """
    if not shutil.which("dpkg-divert"):
        return []

    if os.geteuid() != 0:
        raise PermissionError("Must be run as root")

    result = subprocess.run(
        ["dpkg-divert", "--list"], capture_output=True, text=True
    )

    repaired = []
    for line in result.stdout.splitlines():
        if PATHS_DIR not in line or "local diversion" not in line:
            continue

        # Parse: "local diversion of /path/file.conf to /path/file.conf.distrib"
        parts = line.split()
        try:
            of_idx = parts.index("of")
            to_idx = parts.index("to")
            path = parts[of_idx + 1]
            divert_target = parts[to_idx + 1]
        except (ValueError, IndexError):
            continue

        # Only fix .distrib diversions (the broken ones), skip .orig (working ones)
        if not divert_target.endswith(".distrib"):
            continue

        route_name = os.path.basename(path).replace(".conf", "")
        log.info("Repairing broken diversion for '%s' (%s)", route_name, divert_target)

        # Remove the broken diversion — this restores .distrib back to .conf
        try:
            subprocess.run(
                ["dpkg-divert", "--local", "--rename", "--remove", path],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            log.error("Failed to repair '%s': %s", route_name, e.stderr.strip())
            continue

        repaired.append(route_name)

    if repaired:
        restart_pipewire()

    return repaired


def check_and_reapply():
    """Detect renames clobbered by a package upgrade and re-apply them.

    On Arch, Fedora, and similar distros there is no package-manager hook to
    protect modified .conf files, so an upgrade of alsa-card-profile will
    silently overwrite them.  This function compares the description in each
    tracked .conf against the stored custom name; when they differ the custom
    name is written back and PipeWire is restarted.

    Returns a list of (route_name, custom_name) tuples for every port that was
    re-applied.  Returns [] on Debian/Ubuntu (dpkg-divert already prevents
    upgrades from clobbering the files).

    Must be run as root.
    """
    if os.geteuid() != 0:
        raise PermissionError("Must be run as root")

    backend = _get_divert_backend()
    if not isinstance(backend, NativeBackend):
        return []

    reapplied = []
    for path in backend.list_paths():
        if PATHS_DIR not in path:
            continue

        orig = path + ".orig"
        if not os.path.exists(orig):
            continue

        custom_name = backend.get_custom_name(path)
        if not custom_name:
            log.warning(
                "No stored name for %s — skipping (re-run 'portname rename' manually)", path
            )
            continue

        current_desc = _read_description(path) if os.path.exists(path) else None
        if current_desc == custom_name:
            continue  # Still correct, nothing to do

        route_name = os.path.basename(path).replace(".conf", "")
        log.info("Re-applying rename for '%s' -> '%s'", route_name, custom_name)

        content = _modify_description(orig, custom_name)
        try:
            with open(path, "w") as f:
                f.write(content)
        except OSError as e:
            raise RuntimeError(f"Cannot write to {path}: {e}")

        reapplied.append((route_name, custom_name))

    if reapplied:
        restart_pipewire()

    return reapplied


def _get_real_user():
    """Get the real logged-in user when running under sudo/pkexec."""
    # Try SUDO_USER first
    user = os.environ.get("SUDO_USER")
    if user:
        return user, str(pwd.getpwnam(user).pw_uid)

    # Try PKEXEC_UID
    uid = os.environ.get("PKEXEC_UID")
    if uid:
        return pwd.getpwuid(int(uid)).pw_name, uid

    # Fallback
    uid = os.getuid()
    return pwd.getpwuid(uid).pw_name, str(uid)


def restart_pipewire():
    """Restart PipeWire services. Runs as the real user if we're root via sudo/pkexec.

    Set PORTNAME_SKIP_RESTART=1 to skip the systemctl call entirely (useful in
    containers or test environments where PipeWire is not running).
    """
    if os.environ.get("PORTNAME_SKIP_RESTART") == "1":
        log.info("PORTNAME_SKIP_RESTART=1 — skipping PipeWire restart")
        return
    log.info("Restarting PipeWire services")
    try:
        if os.geteuid() == 0:
            user, uid = _get_real_user()
            subprocess.run(
                ["sudo", "-u", user, "env",
                 f"XDG_RUNTIME_DIR=/run/user/{uid}",
                 "systemctl", "--user", "restart",
                 "pipewire", "pipewire-pulse", "wireplumber"],
                check=True, capture_output=True, text=True, timeout=15,
            )
        else:
            subprocess.run(
                ["systemctl", "--user", "restart",
                 "pipewire", "pipewire-pulse", "wireplumber"],
                check=True, capture_output=True, text=True, timeout=15,
            )
    except subprocess.TimeoutExpired:
        log.error("PipeWire restart timed out after 15s")
        raise RuntimeError("PipeWire restart timed out")
    except subprocess.CalledProcessError as e:
        log.error("PipeWire restart failed: %s", e.stderr.strip())
        raise RuntimeError(f"PipeWire restart failed: {e.stderr.strip() or 'unknown error'}")
    log.debug("PipeWire services restarted")
