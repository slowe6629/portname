"""Privilege elevation helpers for portname."""

import os
import shutil
import subprocess
import sys


def ensure_root_or_exit():
    """Exit with a helpful message if not running as root."""
    if os.geteuid() != 0:
        print("Error: This command requires root privileges.", file=sys.stderr)
        print("Run with: sudo portname ...", file=sys.stderr)
        sys.exit(1)


def run_as_root(args):
    """Run a portname command with pkexec elevation. For GUI use.

    Args:
        args: list of arguments to pass to portname (e.g. ["rename", "analog-output-lineout", "My Name"])

    Returns:
        subprocess.CompletedProcess
    """
    portname_path = shutil.which("portname")
    if portname_path:
        cmd = ["pkexec", portname_path] + args
    else:
        # Not installed system-wide — find the project root from this file's location
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
        cmd = ["pkexec", "env", f"PYTHONPATH={env['PYTHONPATH']}", sys.executable, "-m", "portname"] + args
        return subprocess.run(cmd, capture_output=True, text=True)

    return subprocess.run(cmd, capture_output=True, text=True)
