# Portname — Rename Audio Ports on Linux

Ever wished you could change "Line Out" to "JBL Headset" or "Headphones" to "Pebble Speakers" in your Sound Settings? Now you can.

**Portname** lets you rename the audio input/output ports that appear in your system's Sound Settings panel. Works with PipeWire and ALSA on Debian/Ubuntu-based distros (Linux Mint, Ubuntu, Pop!_OS, etc.).

## Before & After

```
Before:                              After:
  Line Out                             JBL Headset
  Starship/Matisse HD Audio            Starship/Matisse HD Audio

  Headphones                           Pebble Speakers
  Starship/Matisse HD Audio            Starship/Matisse HD Audio
```

## Install

```bash
git clone https://github.com/slowe/portname.git
cd portname
chmod +x install.sh
./install.sh
```

## Usage

### GUI (recommended for beginners)

Just run `portname` or find **Portname** in your application menu. Click **Rename** next to any audio port, type a new name, and enter your password when prompted.

### Command Line

```bash
# List all audio devices and ports
portname list

# Rename a port (requires sudo)
sudo portname rename analog-output-lineout "JBL Headset"
sudo portname rename analog-output-headphones "Pebble Speakers"
sudo portname rename analog-input-rear-mic "JBL Headset Mic"

# Revert a single port
sudo portname revert analog-output-lineout

# Revert all renamed ports
sudo portname revert --all

# Toggle Auto-Mute Mode (fixes issue where front jack silences rear jacks)
portname auto-mute off
portname auto-mute on
portname auto-mute status
```

## How It Works

Audio port names on Linux come from ALSA card profile path files in `/usr/share/alsa-card-profile/mixer/paths/`. Portname:

1. Uses `dpkg-divert` to safely back up the original file
2. Writes a modified copy with your custom name
3. Restarts PipeWire so the change appears immediately

Your custom names survive reboots. The originals are protected from package updates via `dpkg-divert`, so system updates won't overwrite your changes.

## Requirements

- Linux with PipeWire (standard on Linux Mint 22+, Ubuntu 22.10+, Fedora 34+)
- Python 3.8+
- GTK3 via PyGObject (pre-installed on most desktop Linux distros)
- Debian/Ubuntu-based distro (for `dpkg-divert` support)

## Uninstall

```bash
cd portname
./install.sh --uninstall
```

This reverts all renamed ports to their original names and removes portname.

## License

MIT
