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


class TestNativeBackendNameStorage(unittest.TestCase):
    """Tests for custom-name persistence added to NativeBackend."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "state.json")
        self.backend = core.NativeBackend(self.state_file)

        self.conf_path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        with open(self.conf_path, "w") as f:
            f.write("[General]\ndescription-key = analog-output-lineout\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_stores_custom_name(self):
        self.backend.add(self.conf_path, name="JBL Headset")
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["diversions"][self.conf_path]["name"], "JBL Headset")

    def test_add_without_name_stores_none(self):
        self.backend.add(self.conf_path)
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertIsNone(state["diversions"][self.conf_path]["name"])

    def test_get_custom_name_returns_stored_name(self):
        self.backend.add(self.conf_path, name="Pebble Speakers")
        self.assertEqual(self.backend.get_custom_name(self.conf_path), "Pebble Speakers")

    def test_get_custom_name_returns_none_for_unknown_path(self):
        self.assertIsNone(self.backend.get_custom_name("/nonexistent/path.conf"))

    def test_update_name_changes_stored_name(self):
        self.backend.add(self.conf_path, name="Old Name")
        self.backend.update_name(self.conf_path, "New Name")
        self.assertEqual(self.backend.get_custom_name(self.conf_path), "New Name")

    def test_update_name_no_op_for_unknown_path(self):
        self.backend.update_name("/nonexistent.conf", "Whatever")  # Must not raise


class TestRenamePortStoresName(unittest.TestCase):
    """rename_port must persist the custom name for check_and_reapply to use."""

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
    def test_rename_stores_custom_name_in_state(self, mock_euid, mock_restart):
        core.rename_port("analog-output-lineout", "JBL Headset")

        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["diversions"][self.conf_path]["name"], "JBL Headset")

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_re_rename_updates_stored_name(self, mock_euid, mock_restart):
        """Re-renaming an already-renamed port must update the stored name."""
        # First rename
        core.rename_port("analog-output-lineout", "First Name")
        # Second rename
        core.rename_port("analog-output-lineout", "Second Name")

        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["diversions"][self.conf_path]["name"], "Second Name")


class TestCheckAndReapply(unittest.TestCase):
    """Tests for check_and_reapply()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        self.state_file = os.path.join(self.tmpdir, "state.json")
        self._orig_backend = core._divert_backend
        core._set_divert_backend(core.NativeBackend(self.state_file))

        self.conf_path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        self.orig_path = self.conf_path + ".orig"

    def _write_conf(self, path, description):
        content = SAMPLE_CONF.replace(
            "description-key = analog-output-lineout", f"description = {description}"
        )
        with open(path, "w") as f:
            f.write(content)

    def _write_state(self, name):
        state = {
            "diversions": {
                self.conf_path: {"backup": self.orig_path, "name": name}
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        core._set_divert_backend(self._orig_backend)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("os.geteuid", return_value=1000)
    def test_requires_root(self, mock_euid):
        with self.assertRaises(PermissionError):
            core.check_and_reapply()

    @patch("portname.core.shutil.which", return_value="/usr/bin/dpkg-divert")
    @patch("os.geteuid", return_value=0)
    def test_returns_empty_on_debian(self, mock_euid, mock_which):
        """No-op when dpkg-divert is present (Debian/Ubuntu)."""
        core._set_divert_backend(core.DpkgDivertBackend())
        result = core.check_and_reapply()
        self.assertEqual(result, [])

    @patch("os.geteuid", return_value=0)
    def test_returns_empty_when_all_intact(self, mock_euid):
        """Nothing to fix when .conf already has the custom name."""
        self._write_conf(self.orig_path, "analog-output-lineout")
        self._write_conf(self.conf_path, "JBL Headset")
        self._write_state("JBL Headset")

        result = core.check_and_reapply()
        self.assertEqual(result, [])

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_reapplies_clobbered_rename(self, mock_euid, mock_restart):
        """After a package upgrade overwrites .conf, check re-applies the name."""
        # .orig = original file, .conf = overwritten by upgrade (has original name)
        with open(self.orig_path, "w") as f:
            f.write(SAMPLE_CONF)  # original: description-key = analog-output-lineout
        self._write_conf(self.conf_path, "analog-output-lineout")  # upgrade clobbered it
        self._write_state("JBL Headset")

        result = core.check_and_reapply()

        self.assertEqual(result, [("analog-output-lineout", "JBL Headset")])
        with open(self.conf_path) as f:
            content = f.read()
        self.assertIn("description = JBL Headset", content)
        mock_restart.assert_called_once()

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_reapplies_when_conf_missing(self, mock_euid, mock_restart):
        """If the upgrade deleted .conf entirely, check recreates it from .orig."""
        with open(self.orig_path, "w") as f:
            f.write(SAMPLE_CONF)
        # No .conf — simulates a package that removed the file
        self._write_state("JBL Headset")

        result = core.check_and_reapply()

        self.assertEqual(result, [("analog-output-lineout", "JBL Headset")])
        self.assertTrue(os.path.exists(self.conf_path))

    @patch("os.geteuid", return_value=0)
    def test_skips_entry_without_stored_name(self, mock_euid):
        """Entries with no stored name (legacy state) are skipped gracefully."""
        with open(self.orig_path, "w") as f:
            f.write(SAMPLE_CONF)
        self._write_conf(self.conf_path, "analog-output-lineout")
        state = {"diversions": {self.conf_path: {"backup": self.orig_path, "name": None}}}
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        result = core.check_and_reapply()
        self.assertEqual(result, [])

    @patch("portname.core.restart_pipewire")
    @patch("os.geteuid", return_value=0)
    def test_reapplies_multiple_clobbered_ports(self, mock_euid, mock_restart):
        """All clobbered ports in a single run are re-applied."""
        conf2 = os.path.join(self.tmpdir, "analog-output-headphones.conf")
        orig2 = conf2 + ".orig"

        headphones_conf = SAMPLE_CONF.replace("analog-output-lineout", "analog-output-headphones")
        with open(self.orig_path, "w") as f:
            f.write(SAMPLE_CONF)
        self._write_conf(self.conf_path, "analog-output-lineout")

        with open(orig2, "w") as f:
            f.write(headphones_conf)
        with open(conf2, "w") as f:
            f.write(headphones_conf.replace(
                "description-key = analog-output-headphones", "description = analog-output-headphones"
            ))

        state = {
            "diversions": {
                self.conf_path: {"backup": self.orig_path, "name": "JBL Headset"},
                conf2: {"backup": orig2, "name": "Pebble Speakers"},
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        result = core.check_and_reapply()

        self.assertEqual(len(result), 2)
        self.assertIn(("analog-output-lineout", "JBL Headset"), result)
        self.assertIn(("analog-output-headphones", "Pebble Speakers"), result)
        mock_restart.assert_called_once()


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
