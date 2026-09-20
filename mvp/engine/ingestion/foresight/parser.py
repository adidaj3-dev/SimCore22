import logging

logger = logging.getLogger(__name__)


def parse_foresight_packet(raw_packet: bytes) -> dict | None:
    """
    Converts a raw Foresight LM packet into a normalized dictionary.

    Expected output keys:
        - device
        - ball_speed
        - launch_angle
        - azimuth
        - spin_rate
        - spin_axis
        - club_speed
        - carry
        - total

    Returns None for non-shot packets.
    """

    if not raw_packet:
        return None

    try:
        # ---------------------------------------------------------
        # Placeholder decoding logic
        # ---------------------------------------------------------
        # Real Falcon/Hawk/Quad packets are binary structures.
        # On Tuesday, we will capture a few packets and decode them.
        #
        # For now, assume the packet is UTF-8 JSON-like for testing.
        # Replace this with real binary parsing later.
        # ---------------------------------------------------------

        text = raw_packet.decode(errors="ignore")

        if "SHOT" not in text.upper():
            return None  # ignore heartbeats, pings, etc.

        # Fake test payload structure for dry runs
        payload = {
            "device": detect_device(text),
            "ball_speed": extract_value(text, "ball_speed"),
            "launch_angle": extract_value(text, "launch_angle"),
            "azimuth": extract_value(text, "azimuth"),
            "spin_rate": extract_value(text, "spin"),
            "spin_axis": extract_value(text, "spin_axis"),
            "club_speed": extract_value(text, "club_speed"),
            "carry": extract_value(text, "carry"),
            "total": extract_value(text, "total"),
        }

        return payload

    except Exception as e:
        logger.error(f"Failed to parse Foresight packet: {e}")
        return None


def detect_device(text: str) -> str:
    """
    Detects whether the packet came from Falcon, Hawk, or GCQuad.
    """

    t = text.lower()

    if "falcon" in t:
        return "Falcon"
    if "hawk" in t:
        return "Hawk"
    if "quad" in t or "gcquad" in t:
        return "GCQuad"

    return "Foresight"


def extract_value(text: str, key: str) -> float | None:
    """
    Extracts a numeric value from a test packet string.
    This is a placeholder until we decode real binary packets.
    """

    try:
        marker = f"{key}="
        if marker not in text:
            return None

        segment = text.split(marker)[1]
        value = segment.split(",")[0].strip()

        return float(value)

    except Exception:
        return None
