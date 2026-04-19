# protocol.py — USB serial message parser
#
# All messages are newline-terminated ASCII strings.
# Format:  CMD:payload\n   or   CMD\n  (for commands with no payload)
#
# Example messages the PC sends:
#   HELLO                 → announce connection / heartbeat
#   HB                    → heartbeat (keep-alive, same effect as HELLO)
#   BYE                   → clean disconnect, Pico falls back to bedside
#   TIME:14:30:00         → set RTC (HH:MM:SS)
#   FACE:happy            → change eye expression
#   MSG:Update Jira       → show text overlay, then return to eyes
#   BRIGHTNESS:40         → set backlight 0-100%
#   RESET_BREAK           → reset the 30-min break timer

# ── Command type constants ─────────────────────────────────────
HELLO         = "HELLO"
HEARTBEAT     = "HB"
BYE           = "BYE"
TIME          = "TIME"
FACE          = "FACE"
MSG           = "MSG"
BRIGHTNESS    = "BRIGHTNESS"
RESET_BREAK   = "RESET_BREAK"

# ── Valid face names ───────────────────────────────────────────
FACES = {
    "default", "happy", "tired", "angry",
    "curious", "scary", "frozen", "excited",
}


def parse(line):
    """
    Parse one serial line into (cmd, payload).

    Returns:
        (str, str | None)  — e.g. ("FACE", "happy") or ("HELLO", None)
        (None, None)       — blank / unparseable line
    """
    line = line.strip()
    if not line:
        return None, None

    if ":" in line:
        cmd, _, payload = line.partition(":")
        return cmd.upper().strip(), payload.strip()

    return line.upper().strip(), None


def parse_time(payload):
    """
    Parse a TIME payload "HH:MM:SS" or "HH:MM".

    Returns (h, m, s) as ints, or None on failure.
    """
    try:
        parts = payload.split(":")
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        if 0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60:
            return h, m, s
    except Exception:
        pass
    return None

# ── ACK / NACK helpers ────────────────────────────────────────
# Pico prints these back over serial so the PC script can confirm
# every command was received and whether it was understood.
#
# Statuses:
#   OK       — recognised and applied
#   UNKNOWN  — command or value not recognised
#   ERR      — recognised command but value was invalid


def ack(cmd, detail=None, status="OK"):
    """Return an ACK line to print() back to the PC."""
    if detail is not None:
        return "ACK:{}:{}:{}".format(cmd, detail, status)
    return "ACK:{}:{}".format(cmd, status)


def nack(cmd, status="UNKNOWN"):
    """Return a NACK line for unrecognised commands."""
    return "NACK:{}:{}".format(cmd, status)
