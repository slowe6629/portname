"""Tests for portname CLI commands."""

import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

from portname.cli import main


SAMPLE_DEVICES = [
    {
        "device_name": "alsa_card.pci-0000_2d_00.4",
        "device_description": "HD Audio Controller",
        "alsa_card": "1",
        "routes": [
            {
                "name": "analog-output-lineout",
                "description": "Line Out",
                "direction": "Output",
                "available": "yes",
            },
            {
                "name": "analog-input-rear-mic",
                "description": "Rear Microphone",
                "direction": "Input",
                "available": "no",
            },
        ],
    }
]


class TestCmdList(unittest.TestCase):
    @patch("portname.cli.is_renamed", return_value=False)
    @patch("portname.cli.get_devices", return_value=SAMPLE_DEVICES)
    @patch("sys.argv", ["portname", "list"])
    def test_list_shows_devices(self, mock_devices, mock_renamed):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        output = mock_out.getvalue()
        self.assertIn("HD Audio Controller", output)
        self.assertIn("analog-output-lineout", output)
        self.assertIn("Line Out", output)
        self.assertIn("Output:", output)
        self.assertIn("Input:", output)

    @patch("portname.cli.get_devices", return_value=[])
    @patch("sys.argv", ["portname", "list"])
    def test_list_empty(self, mock_devices):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        self.assertIn("No audio devices", mock_out.getvalue())

    @patch("portname.cli.is_renamed", return_value=True)
    @patch("portname.cli.get_devices", return_value=SAMPLE_DEVICES)
    @patch("sys.argv", ["portname", "list"])
    def test_list_shows_renamed_tag(self, mock_devices, mock_renamed):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        self.assertIn("renamed", mock_out.getvalue())


class TestCmdRename(unittest.TestCase):
    @patch("portname.cli.rename_port")
    @patch("portname.cli.ensure_root_or_exit")
    @patch("sys.argv", ["portname", "rename", "analog-output-lineout", "My Speakers"])
    def test_rename_success(self, mock_root, mock_rename):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        mock_rename.assert_called_once_with("analog-output-lineout", "My Speakers")
        self.assertIn("Renamed", mock_out.getvalue())

    @patch("portname.cli.rename_port", side_effect=FileNotFoundError("No path file found"))
    @patch("portname.cli.ensure_root_or_exit")
    @patch("sys.argv", ["portname", "rename", "nonexistent", "Test"])
    def test_rename_not_found(self, mock_root, mock_rename):
        with patch("sys.stderr", new_callable=StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)


class TestCmdRevert(unittest.TestCase):
    @patch("portname.cli.revert_port")
    @patch("portname.cli.ensure_root_or_exit")
    @patch("sys.argv", ["portname", "revert", "analog-output-lineout"])
    def test_revert_success(self, mock_root, mock_revert):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        mock_revert.assert_called_once_with("analog-output-lineout")
        self.assertIn("Reverted", mock_out.getvalue())

    @patch("portname.cli.revert_all", return_value=["analog-output-lineout", "analog-input-rear-mic"])
    @patch("portname.cli.ensure_root_or_exit")
    @patch("sys.argv", ["portname", "revert", "--all"])
    def test_revert_all(self, mock_root, mock_revert_all):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        output = mock_out.getvalue()
        self.assertIn("analog-output-lineout", output)
        self.assertIn("analog-input-rear-mic", output)

    @patch("portname.cli.revert_all", return_value=[])
    @patch("portname.cli.ensure_root_or_exit")
    @patch("sys.argv", ["portname", "revert", "--all"])
    def test_revert_all_nothing(self, mock_root, mock_revert_all):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        self.assertIn("No renamed ports", mock_out.getvalue())


class TestCmdAutoMute(unittest.TestCase):
    @patch("portname.cli.get_auto_mute_status", return_value="Enabled")
    @patch("portname.cli.get_cards_with_auto_mute", return_value=[("1", "HD Audio")])
    @patch("portname.cli.get_devices", return_value=SAMPLE_DEVICES)
    @patch("sys.argv", ["portname", "auto-mute", "status"])
    def test_auto_mute_status(self, mock_devices, mock_cards, mock_status):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        self.assertIn("Enabled", mock_out.getvalue())

    @patch("portname.cli.set_auto_mute")
    @patch("portname.cli.get_cards_with_auto_mute", return_value=[("1", "HD Audio")])
    @patch("portname.cli.get_devices", return_value=SAMPLE_DEVICES)
    @patch("sys.argv", ["portname", "auto-mute", "off"])
    def test_auto_mute_off(self, mock_devices, mock_cards, mock_set):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main()
        mock_set.assert_called_once_with("1", False)
        self.assertIn("Disabled", mock_out.getvalue())


if __name__ == "__main__":
    unittest.main()
