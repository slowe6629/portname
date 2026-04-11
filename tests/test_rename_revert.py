"""Integration tests for rename and revert flows using NativeBackend."""

import json
import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch, MagicMock

import portname.core as core


SAMPLE_CONF = textwrap.dedent("""\
    [General]
    priority = 90
    description-key = analog-output-lineout

    [Jack Line Out]
    required-any = any
""")


class TestRenamePort(unittest.TestCase):
    """Test rename_port with NativeBackend and real filesystem operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        self.state_file = os.path.join(self.tmpdir, "state.json")
        self._orig_backend = core._divert_backend
        core._set_divert_backend(core.NativeBackend(self.state_file))

        self.conf_path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        with open(self.conf_path, "w") as f:
            f.write(SAMPLE_CONF)

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        core._set_divert_backend(self._orig_backend)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_rename_creates_modified_file(self, mock_euid, mock_restart):
        core.rename_port("analog-output-lineout", "My Speakers")

        with open(self.conf_path) as f:
            content = f.read()
        self.assertIn("description = My Speakers", content)
        self.assertNotIn("description-key", content)

        # Backup must exist
        self.assertTrue(os.path.exists(self.conf_path + ".orig"))
        mock_restart.assert_called_once()

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_rename_already_renamed(self, mock_euid, mock_restart):
        """Renaming an already-renamed port should skip the backup step."""
        orig_path = self.conf_path + ".orig"
        os.rename(self.conf_path, orig_path)
        with open(self.conf_path, "w") as f:
            f.write(SAMPLE_CONF.replace("description-key = analog-output-lineout",
                                         "description = Old Name"))

        core.rename_port("analog-output-lineout", "New Name")

        with open(self.conf_path) as f:
            content = f.read()
        self.assertIn("description = New Name", content)
        mock_restart.assert_called_once()

    @patch("os.geteuid", return_value=1000)
    def test_rename_requires_root(self, mock_euid):
        with self.assertRaises(PermissionError):
            core.rename_port("analog-output-lineout", "Test")

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_rename_validates_name(self, mock_euid, mock_restart):
        with self.assertRaises(ValueError):
            core.rename_port("analog-output-lineout", "")


class TestRevertPort(unittest.TestCase):
    """Test revert_port with NativeBackend and real filesystem operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        self.state_file = os.path.join(self.tmpdir, "state.json")
        self._orig_backend = core._divert_backend
        core._set_divert_backend(core.NativeBackend(self.state_file))

        self.conf_path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        self.orig_path = self.conf_path + ".orig"

        # Pre-populate: .orig holds the original, .conf holds the modified version
        with open(self.orig_path, "w") as f:
            f.write(SAMPLE_CONF)
        with open(self.conf_path, "w") as f:
            f.write(SAMPLE_CONF.replace("description-key = analog-output-lineout",
                                         "description = Custom Name"))
        state = {"diversions": {self.conf_path: {"backup": self.orig_path}}}
        with open(self.state_file, "w") as f:
            json.dump(state, f)

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        core._set_divert_backend(self._orig_backend)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_revert_restores_original(self, mock_euid, mock_restart):
        core.revert_port("analog-output-lineout")

        # Original content should be back at the main path
        self.assertTrue(os.path.exists(self.conf_path))
        with open(self.conf_path) as f:
            content = f.read()
        self.assertIn("description-key = analog-output-lineout", content)

        # Backup should be gone
        self.assertFalse(os.path.exists(self.orig_path))
        mock_restart.assert_called_once()

    @patch("os.geteuid", return_value=1000)
    def test_revert_requires_root(self, mock_euid):
        with self.assertRaises(PermissionError):
            core.revert_port("analog-output-lineout")

    @patch("os.geteuid", return_value=0)
    def test_revert_not_renamed_raises(self, mock_euid):
        os.remove(self.orig_path)
        with self.assertRaises(ValueError) as ctx:
            core.revert_port("analog-output-lineout")
        self.assertIn("has not been renamed", str(ctx.exception))


class TestRevertAll(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        self.state_file = os.path.join(self.tmpdir, "state.json")
        self._orig_backend = core._divert_backend
        core._set_divert_backend(core.NativeBackend(self.state_file))

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        core._set_divert_backend(self._orig_backend)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.revert_port")
    @patch("os.geteuid", return_value=0)
    def test_revert_all_finds_diverted_ports(self, mock_euid, mock_revert):
        state = {
            "diversions": {
                os.path.join(self.tmpdir, "analog-output-lineout.conf"): {"backup": "..."},
                os.path.join(self.tmpdir, "analog-input-rear-mic.conf"): {"backup": "..."},
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        reverted = core.revert_all()

        self.assertEqual(sorted(reverted),
                         sorted(["analog-output-lineout", "analog-input-rear-mic"]))
        self.assertEqual(mock_revert.call_count, 2)

    @patch("os.geteuid", return_value=0)
    def test_revert_all_empty(self, mock_euid):
        with open(self.state_file, "w") as f:
            json.dump({"diversions": {}}, f)

        reverted = core.revert_all()
        self.assertEqual(reverted, [])


class TestGetAllRenamed(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        self.state_file = os.path.join(self.tmpdir, "state.json")
        self._orig_backend = core._divert_backend
        core._set_divert_backend(core.NativeBackend(self.state_file))

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        core._set_divert_backend(self._orig_backend)

    def test_returns_renamed_routes(self):
        path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        state = {"diversions": {path: {"backup": path + ".orig"}}}
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        renamed = core.get_all_renamed()
        self.assertEqual(renamed, ["analog-output-lineout"])


class TestRepairDistribDiversions(unittest.TestCase):
    """Tests for the Debian-specific repair_distrib_diversions function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.shutil.which", return_value=None)
    def test_returns_empty_on_non_debian(self, mock_which):
        """Should return empty list when dpkg-divert is not available."""
        repaired = core.repair_distrib_diversions()
        self.assertEqual(repaired, [])

    @patch("portname.core.restart_pipewire")
    @patch("portname.core.subprocess.run")
    @patch("portname.core.shutil.which", return_value="/usr/bin/dpkg-divert")
    @patch("os.geteuid", return_value=0)
    def test_repairs_distrib_diversions(self, mock_euid, mock_which, mock_run, mock_restart):
        divert_output = (
            f"local diversion of {self.tmpdir}/analog-output-lineout.conf "
            f"to {self.tmpdir}/analog-output-lineout.conf.distrib\n"
            f"local diversion of {self.tmpdir}/analog-output-headphones.conf "
            f"to {self.tmpdir}/analog-output-headphones.conf.distrib\n"
        )
        mock_run.side_effect = [
            MagicMock(stdout=divert_output, returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]

        repaired = core.repair_distrib_diversions()

        self.assertEqual(repaired, ["analog-output-lineout", "analog-output-headphones"])
        mock_restart.assert_called_once()

    @patch("portname.core.subprocess.run")
    @patch("portname.core.shutil.which", return_value="/usr/bin/dpkg-divert")
    @patch("os.geteuid", return_value=0)
    def test_skips_orig_diversions(self, mock_euid, mock_which, mock_run):
        """Working .orig diversions should not be touched."""
        divert_output = (
            f"local diversion of {self.tmpdir}/analog-output-lineout.conf "
            f"to {self.tmpdir}/analog-output-lineout.conf.orig\n"
        )
        mock_run.return_value = MagicMock(stdout=divert_output, returncode=0)

        repaired = core.repair_distrib_diversions()

        self.assertEqual(repaired, [])
        mock_run.assert_called_once()

    @patch("portname.core.subprocess.run")
    @patch("portname.core.shutil.which", return_value="/usr/bin/dpkg-divert")
    @patch("os.geteuid", return_value=0)
    def test_nothing_to_repair(self, mock_euid, mock_which, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        repaired = core.repair_distrib_diversions()

        self.assertEqual(repaired, [])

    @patch("portname.core.shutil.which", return_value="/usr/bin/dpkg-divert")
    @patch("os.geteuid", return_value=1000)
    def test_requires_root(self, mock_euid, mock_which):
        with self.assertRaises(PermissionError):
            core.repair_distrib_diversions()


if __name__ == "__main__":
    unittest.main()
