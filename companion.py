# companion.py — dev companion mode
#
# Drives RoboEyes expressions based on messages from the PC script.
# Also shows brief text overlays for notifications and break reminders.
#
# Supported protocol commands:
#   FACE:<name>      → change expression (see FACE_MAP below)
#   MSG:<text>       → text overlay for MSG_SHOW_MS, then eyes return
#   BRIGHTNESS:<pct> → set backlight 0-100 %
#   RESET_BREAK      → reset the 30-min break timer

from machine import PWM, Pin
from roboeyes import RoboEyes, ON, OFF
from roboeyes import DEFAULT, TIRED, ANGRY, HAPPY, FROZEN, SCARY, CURIOUS
import time

import protocol
from health import HealthTimer

# ── Config ────────────────────────────────────────────────────
MSG_SHOW_MS      = 5_000   # how long a text overlay stays on screen
BREAK_MSG        = "Hey. Stand up. 5 min walk."
WAKE_SETTLE_MS   = 600     # ms to let RoboEyes tweens reach target

# ── Face name → RoboEyes mood constant ───────────────────────
FACE_MAP = {
    "default":  DEFAULT,
    "happy":    HAPPY,
    "tired":    TIRED,
    "angry":    ANGRY,
    "curious":  CURIOUS,
    "scary":    SCARY,
    "frozen":   FROZEN,
}

# ── Colours (RGB565 standard, adapter handles byte-swap) ──────
_WHITE = 0xFFFF
_BLACK = 0x0000


class CompanionMode:
    """
    Initialise RoboEyes, play a wake-up animation, then handle messages.
    Call handle(cmd, payload) for each parsed serial message.
    Call update() every loop iteration.
    """

    def __init__(self, lcd, bl_pin=6):
        self.lcd    = lcd
        self._pwm   = PWM(Pin(bl_pin))
        self._pwm.freq(1000)
        self._pwm.duty_u16(65535)   # full brightness on wake-up

        # ── RoboEyes setup ────────────────────────────────────
        self.robo = RoboEyes(
            lcd, 240, 240,
            frame_rate=20,
            on_show=lambda r: lcd.show(),
        )
        self.robo.eyes_width(80, 80)
        self.robo.eyes_height(70, 70)
        self.robo.eyes_radius(14, 14)
        self.robo.set_auto_blinker(ON, 3, 2)
        self.robo.set_idle_mode(OFF)

        # ── Wake-up animation ─────────────────────────────────
        # Start tired/half-closed, let size tween finish, then centre
        self.robo.set_mood(TIRED)
        self._settle(WAKE_SETTLE_MS)
        self.robo.set_position(DEFAULT)
        self._settle(WAKE_SETTLE_MS)
        # Open eyes fully
        self.robo.set_mood(DEFAULT)

        # ── Internal state ────────────────────────────────────
        self._health      = HealthTimer()
        self._msg_until   = 0          # ticks_ms deadline for current overlay
        self._showing_msg = False
        self._current_mood = DEFAULT

    # ── Public API ────────────────────────────────────────────

    def handle(self, cmd, payload):
        """Dispatch a parsed protocol command."""
        if cmd == protocol.FACE:
            self._set_face(payload or "default")

        elif cmd == protocol.MSG:
            self._show_message(payload or "")

        elif cmd == protocol.RESET_BREAK:
            self._health.reset()

        elif cmd == protocol.BRIGHTNESS:
            try:
                pct = int(payload)
                self._pwm.duty_u16(int(65535 * max(0, min(100, pct)) / 100))
            except Exception:
                pass

    def update(self):
        """Call every loop iteration."""
        # ── End of message overlay? ───────────────────────────
        if self._showing_msg:
            if time.ticks_diff(time.ticks_ms(), self._msg_until) >= 0:
                self._showing_msg = False
                # Restore eyes with last known mood
                self.robo.set_mood(self._current_mood)

        # ── Break reminder due? ───────────────────────────────
        if self._health.due:
            self._show_message(BREAK_MSG)

        # ── Tick RoboEyes (only when eyes are visible) ────────
        if not self._showing_msg:
            self.robo.update()

    # ── Private helpers ───────────────────────────────────────

    def deinit(self):
        """Release PWM so bedside mode can take over pin 6."""
        self._pwm.deinit()

    def _set_face(self, name):
        mood = FACE_MAP.get(name.lower(), DEFAULT)
        self._current_mood = mood
        if not self._showing_msg:
            self.robo.set_mood(mood)

    def _show_message(self, text):
        """Clear screen, render wrapped text, set expiry timer."""
        self.lcd.fill(_BLACK)

        lines    = _wrap(text, max_chars=26)   # 26 × 8px ≈ 208px wide
        line_h   = 14                          # px per line (8px font + leading)
        total_h  = len(lines) * line_h
        y        = max(0, (240 - total_h) // 2)

        for line in lines:
            x = max(0, (240 - len(line) * 8) // 2)
            self.lcd.text(line, x, y, _WHITE)
            y += line_h

        self.lcd.show()
        self._msg_until   = time.ticks_ms() + MSG_SHOW_MS
        self._showing_msg = True

    def _settle(self, ms):
        """Run the RoboEyes update loop for `ms` milliseconds."""
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < ms:
            self.robo.update()


# ── Utility ───────────────────────────────────────────────────

def _wrap(text, max_chars):
    """
    Word-wrap `text` to lines of at most `max_chars` characters.
    Returns a list of strings (never empty).
    """
    words = text.split()
    if not words:
        return [""]
    lines, current = [], ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
