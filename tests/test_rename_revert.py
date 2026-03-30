"""Integration tests for rename and revert flows using mocked system commands."""

import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch, MagicMock, call

import portname.core as core


SAMPLE_CONF = textwrap.dedent("""\
    [General]
    priority = 90
    description-key = analog-output-lineout

    [Jack Line Out]
    required-any = any
""")


class TestRenamePort(unittest.TestCase):
    """Test rename_port with a real temp filesystem and mocked subprocess calls."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        # Create a fake .conf file
        self.conf_path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        with open(self.conf_path, "w") as f:
            f.write(SAMPLE_CONF)

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        # Clean up temp files
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.restart_pipewire")
    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_rename_creates_modified_file(self, mock_euid, mock_run, mock_restart):
        mock_run.return_value = MagicMock(returncode=0)

        # Simulate what dpkg-divert does: move .conf -> .conf.orig
        def fake_divert(*args, **kwargs):
            os.rename(self.conf_path, self.conf_path + ".orig")
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_divert

        core.rename_port("analog-output-lineout", "My Speakers")

        # The .conf file should now have the new description
        with open(self.conf_path) as f:
            content = f.read()
        self.assertIn("description = My Speakers", content)
        self.assertNotIn("description-key", content)

        # dpkg-divert should have been called
        mock_run.assert_called_once()
        # PipeWire should have been restarted
        mock_restart.assert_called_once()

    @patch("portname.core.restart_pipewire")
    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_rename_already_renamed(self, mock_euid, mock_run, mock_restart):
        """Renaming an already-renamed port should skip dpkg-divert."""
        # Set up as if already diverted
        orig_path = self.conf_path + ".orig"
        os.rename(self.conf_path, orig_path)
        # Write modified content as current .conf
        with open(self.conf_path, "w") as f:
            f.write(SAMPLE_CONF.replace("description-key = analog-output-lineout",
                                         "description = Old Name"))

        core.rename_port("analog-output-lineout", "New Name")

        # dpkg-divert should NOT have been called (already renamed)
        mock_run.assert_not_called()
        # But the file should have the new name
        with open(self.conf_path) as f:
            content = f.read()
        self.assertIn("description = New Name", content)
        mock_restart.assert_called_once()

    @patch("os.geteuid", return_value=1000)
    def test_rename_requires_root(self, mock_euid):
        with self.assertRaises(PermissionError):
            core.rename_port("analog-output-lineout", "Test")

    @patch("portname.core.restart_pipewire")
    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_rename_validates_name(self, mock_euid, mock_run, mock_restart):
        with self.assertRaises(ValueError):
            core.rename_port("analog-output-lineout", "")


class TestRevertPort(unittest.TestCase):
    """Test revert_port with a real temp filesystem and mocked subprocess calls."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

        # Set up as if already renamed: .orig exists and modified .conf exists
        self.conf_path = os.path.join(self.tmpdir, "analog-output-lineout.conf")
        self.orig_path = self.conf_path + ".orig"
        with open(self.orig_path, "w") as f:
            f.write(SAMPLE_CONF)
        with open(self.conf_path, "w") as f:
            f.write(SAMPLE_CONF.replace("description-key = analog-output-lineout",
                                         "description = Custom Name"))

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.restart_pipewire")
    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_revert_removes_modified_file(self, mock_euid, mock_run, mock_restart):
        mock_run.return_value = MagicMock(returncode=0)

        core.revert_port("analog-output-lineout")

        # Modified .conf should have been removed
        self.assertFalse(os.path.exists(self.conf_path))
        # dpkg-divert --remove should have been called
        mock_run.assert_called_once()
        divert_args = mock_run.call_args[0][0]
        self.assertIn("--remove", divert_args)
        mock_restart.assert_called_once()

    @patch("os.geteuid", return_value=1000)
    def test_revert_requires_root(self, mock_euid):
        with self.assertRaises(PermissionError):
            core.revert_port("analog-output-lineout")

    @patch("os.geteuid", return_value=0)
    def test_revert_not_renamed_raises(self, mock_euid):
        # Remove the .orig file so it looks like it was never renamed
        os.remove(self.orig_path)
        with self.assertRaises(ValueError) as ctx:
            core.revert_port("analog-output-lineout")
        self.assertIn("has not been renamed", str(ctx.exception))


class TestRevertAll(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.revert_port")
    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_revert_all_finds_diverted_ports(self, mock_euid, mock_run, mock_revert):
        divert_output = (
            f"local diversion of {self.tmpdir}/analog-output-lineout.conf "
            f"to {self.tmpdir}/analog-output-lineout.conf.orig\n"
            f"local diversion of {self.tmpdir}/analog-input-rear-mic.conf "
            f"to {self.tmpdir}/analog-input-rear-mic.conf.orig\n"
        )
        mock_run.return_value = MagicMock(stdout=divert_output, returncode=0)

        reverted = core.revert_all()

        self.assertEqual(reverted, ["analog-output-lineout", "analog-input-rear-mic"])
        self.assertEqual(mock_revert.call_count, 2)

    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_revert_all_empty(self, mock_euid, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        reverted = core.revert_all()
        self.assertEqual(reverted, [])


class TestGetAllRenamed(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir

    @patch("portname.core.subprocess.run")
    def test_returns_renamed_routes(self, mock_run):
        divert_output = (
            f"local diversion of {self.tmpdir}/analog-output-lineout.conf "
            f"to {self.tmpdir}/analog-output-lineout.conf.orig\n"
        )
        mock_run.return_value = MagicMock(stdout=divert_output, returncode=0)

        renamed = core.get_all_renamed()
        self.assertEqual(renamed, ["analog-output-lineout"])


class TestRepairDistribDiversions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_paths_dir = core.PATHS_DIR
        core.PATHS_DIR = self.tmpdir

    def tearDown(self):
        core.PATHS_DIR = self._orig_paths_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("portname.core.restart_pipewire")
    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_repairs_distrib_diversions(self, mock_euid, mock_run, mock_restart):
        divert_output = (
            f"local diversion of {self.tmpdir}/analog-output-lineout.conf "
            f"to {self.tmpdir}/analog-output-lineout.conf.distrib\n"
            f"local diversion of {self.tmpdir}/analog-output-headphones.conf "
            f"to {self.tmpdir}/analog-output-headphones.conf.distrib\n"
        )
        # First call is --list, subsequent calls are --remove
        mock_run.side_effect = [
            MagicMock(stdout=divert_output, returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]

        repaired = core.repair_distrib_diversions()

        self.assertEqual(repaired, ["analog-output-lineout", "analog-output-headphones"])
        # Should have restarted PipeWire once
        mock_restart.assert_called_once()

    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_skips_orig_diversions(self, mock_euid, mock_run):
        """Working .orig diversions should not be touched."""
        divert_output = (
            f"local diversion of {self.tmpdir}/analog-output-lineout.conf "
            f"to {self.tmpdir}/analog-output-lineout.conf.orig\n"
        )
        mock_run.return_value = MagicMock(stdout=divert_output, returncode=0)

        repaired = core.repair_distrib_diversions()

        self.assertEqual(repaired, [])
        # Only the --list call should have happened
        mock_run.assert_called_once()

    @patch("portname.core.subprocess.run")
    @patch("os.geteuid", return_value=0)
    def test_nothing_to_repair(self, mock_euid, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        repaired = core.repair_distrib_diversions()

        self.assertEqual(repaired, [])

    @patch("os.geteuid", return_value=1000)
    def test_requires_root(self, mock_euid):
        with self.assertRaises(PermissionError):
            core.repair_distrib_diversions()


if __name__ == "__main__":
    unittest.main()
