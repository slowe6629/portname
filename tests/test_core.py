"""Tests for portname core module."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from portname.core import (
    _read_description,
    _modify_description,
    get_devices,
    is_renamed,
)


SAMPLE_PATH_FILE = """# Comment
; Another comment

[General]
priority = 90
description-key = analog-output-lineout

[Jack Line Out]
required-any = any

[Element Master]
switch = mute
volume = merge

.include analog-output.conf.common
"""

SAMPLE_PATH_FILE_RENAMED = """# Comment
; Another comment

[General]
priority = 90
description = JBL Headset

[Jack Line Out]
required-any = any

[Element Master]
switch = mute
volume = merge

.include analog-output.conf.common
"""

SAMPLE_PW_DUMP = [
    {
        "id": 47,
        "type": "PipeWire:Interface:Device",
        "info": {
            "props": {
                "device.api": "alsa",
                "device.name": "alsa_card.pci-0000_2d_00.4",
                "device.description": "Starship/Matisse HD Audio Controller",
                "alsa.card": 1,
                "alsa.card_name": "HD-Audio Generic",
            },
            "params": {
                "EnumRoute": [
                    {
                        "index": 0,
                        "direction": "Output",
                        "name": "analog-output-lineout",
                        "description": "Line Out",
                        "available": "yes",
                    },
                    {
                        "index": 1,
                        "direction": "Output",
                        "name": "analog-output-headphones",
                        "description": "Headphones",
                        "available": "yes",
                    },
                    {
                        "index": 2,
                        "direction": "Input",
                        "name": "analog-input-rear-mic",
                        "description": "Rear Microphone",
                        "available": "yes",
                    },
                ],
            },
        },
    }
]


class TestReadDescription(unittest.TestCase):
    def test_reads_description_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(SAMPLE_PATH_FILE)
            f.flush()
            result = _read_description(f.name)
        os.unlink(f.name)
        self.assertEqual(result, "analog-output-lineout")

    def test_reads_description_value(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(SAMPLE_PATH_FILE_RENAMED)
            f.flush()
            result = _read_description(f.name)
        os.unlink(f.name)
        self.assertEqual(result, "JBL Headset")


class TestModifyDescription(unittest.TestCase):
    def test_replaces_description_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(SAMPLE_PATH_FILE)
            f.flush()
            result = _modify_description(f.name, "My Speakers")
        os.unlink(f.name)
        self.assertIn("description = My Speakers", result)
        self.assertNotIn("description-key", result)

    def test_replaces_existing_description(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(SAMPLE_PATH_FILE_RENAMED)
            f.flush()
            result = _modify_description(f.name, "New Name")
        os.unlink(f.name)
        self.assertIn("description = New Name", result)
        self.assertNotIn("JBL Headset", result)

    def test_preserves_other_sections(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(SAMPLE_PATH_FILE)
            f.flush()
            result = _modify_description(f.name, "Test")
        os.unlink(f.name)
        self.assertIn("[Jack Line Out]", result)
        self.assertIn("[Element Master]", result)
        self.assertIn("priority = 90", result)
        self.assertIn(".include analog-output.conf.common", result)


class TestGetDevices(unittest.TestCase):
    @patch("portname.core.os.path.exists")
    @patch("portname.core.subprocess.run")
    def test_parses_pw_dump(self, mock_run, mock_exists):
        mock_run.return_value = MagicMock(
            stdout=json.dumps(SAMPLE_PW_DUMP),
            returncode=0,
        )
        mock_exists.return_value = True

        devices = get_devices()

        self.assertEqual(len(devices), 1)
        dev = devices[0]
        self.assertEqual(dev["device_description"], "Starship/Matisse HD Audio Controller")
        self.assertEqual(dev["alsa_card"], "1")
        self.assertEqual(len(dev["routes"]), 3)
        self.assertEqual(dev["routes"][0]["name"], "analog-output-lineout")
        self.assertEqual(dev["routes"][0]["direction"], "Output")


class TestIsRenamed(unittest.TestCase):
    @patch("portname.core.os.path.exists")
    def test_returns_true_when_orig_exists(self, mock_exists):
        mock_exists.side_effect = lambda p: p.endswith(".orig") or not p.endswith(".orig")
        self.assertTrue(is_renamed("analog-output-lineout"))

    @patch("portname.core.os.path.exists")
    def test_returns_false_when_no_orig(self, mock_exists):
        def exists_side_effect(path):
            if path.endswith(".orig"):
                return False
            return True
        mock_exists.side_effect = exists_side_effect
        self.assertFalse(is_renamed("analog-output-lineout"))


if __name__ == "__main__":
    unittest.main()
