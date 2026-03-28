"""Auto-Mute Mode control via amixer."""

import subprocess


def get_auto_mute_status(card):
    """Get Auto-Mute Mode status for an ALSA card.

    Returns "Enabled", "Disabled", or None if the control doesn't exist.
    """
    try:
        result = subprocess.run(
            ["amixer", "-c", str(card), "sget", "Auto-Mute Mode"],
            capture_output=True, text=True, check=True,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Item0:"):
                value = stripped.split("'")[1]
                return value
    except (subprocess.CalledProcessError, IndexError):
        return None
    return None


def set_auto_mute(card, enabled):
    """Set Auto-Mute Mode for an ALSA card."""
    value = "Enabled" if enabled else "Disabled"
    subprocess.run(
        ["amixer", "-c", str(card), "sset", "Auto-Mute Mode", value],
        capture_output=True, text=True, check=True,
    )


def get_cards_with_auto_mute(devices):
    """Return list of (card_number, device_description) for cards that have Auto-Mute.

    Args:
        devices: list from core.get_devices()
    """
    results = []
    seen = set()
    for dev in devices:
        card = dev["alsa_card"]
        if card in seen or not card:
            continue
        seen.add(card)
        status = get_auto_mute_status(card)
        if status is not None:
            results.append((card, dev["device_description"]))
    return results
