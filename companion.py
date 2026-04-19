# companion.py — dev companion mode

from machine import PWM, Pin
from roboeyes import RoboEyes, ON, OFF
from roboeyes import DEFAULT, TIRED, ANGRY, HAPPY, FROZEN, SCARY, CURIOUS
import time
import framebuf as _framebuf

import protocol
from health import HealthTimer

# ── Config ────────────────────────────────────────────────────
MSG_HOLD_MS      = 3_000   # pause after full typewriter reveal before clearing
TYPEWRITER_MS    = 55      # ms between each revealed character (~18 chars/s)
BREAK_MSG        = "Hey. Stand up. 5 min walk."
WAKE_SETTLE_MS   = 600

# Default eye geometry (must match __init__ calls below)
_EYE_W        = 80
_EYE_H        = 70
_EYE_RADIUS   = 14

# Focused face: circular eyes, slower blink — visually distinct from default
_FOCUSED_SIZE   = 65
_FOCUSED_RADIUS = 32   # half of 65 → near-perfect circle

# Text band geometry (bottom of 240x240 screen)
BAND_Y  = 176              # y where the dark band starts
BAND_H  = 64               # band height in pixels
SCALE   = 2                # font scale (8x8 → 16x16)
MAX_VIS = 240 // (8 * SCALE)  # max visible chars at this scale (= 15)

# ── Face map ──────────────────────────────────────────────────
FACE_MAP = {
    "default":  DEFAULT,
    "happy":    HAPPY,
    "tired":    TIRED,
    "angry":    ANGRY,
    "curious":  CURIOUS,
    "focused":  DEFAULT,  # handled specially in _set_face (circular eyes)
    "scary":    SCARY,
    "frozen":   FROZEN,
    "excited":  HAPPY,    # handled specially in _set_face (idle mode on)
}

# ── Colours ───────────────────────────────────────────────────
_WHITE     = 0xFFFF
_BLACK     = 0x0000


class CompanionMode:

    def __init__(self, lcd, bl_pin=6):
        self.lcd  = lcd
        self._pwm = PWM(Pin(bl_pin))
        self._pwm.freq(1000)
        self._pwm.duty_u16(65535)

        # ── Message state (must exist before RoboEyes init, ──────
        # because RoboEyes calls on_show() during its own __init__)
        self._msg_full     = ""
        self._msg_reveal   = 0
        self._msg_scroll   = 0
        self._next_char_t  = 0
        self._msg_hold_end = 0
        self._showing_msg  = False
        self._health       = HealthTimer()
        self._current_mood = DEFAULT

        # ── RoboEyes ─────────────────────────────────────────
        self.robo = RoboEyes(
            lcd, 240, 240,
            frame_rate=20,
            on_show=self._on_show,
        )
        self.robo.eyes_width(80, 80)
        self.robo.eyes_height(70, 70)
        self.robo.eyes_radius(14, 14)
        self.robo.set_auto_blinker(ON, 3, 2)
        self.robo.set_idle_mode(OFF)

        # ── Wake-up animation ─────────────────────────────────
        self.robo.set_mood(TIRED)
        self._settle(WAKE_SETTLE_MS)
        self.robo.set_position(DEFAULT)
        self._settle(WAKE_SETTLE_MS)
        self.robo.set_mood(DEFAULT)

    # ── Public API ────────────────────────────────────────────

    def handle(self, cmd, payload):
        """
        Dispatch command and return an ACK/NACK string for the PC.
        The caller (main.py) is responsible for print()ing it.
        """
        if cmd == protocol.FACE:
            name = (payload or "default").lower()
            if name in FACE_MAP:
                self._set_face(name)
                return protocol.ack(cmd, name)
            else:
                # Unknown face name — fall back to default
                self._set_face("default")
                return protocol.ack(cmd, name, status="UNKNOWN")

        elif cmd == protocol.MSG:
            self._start_message(payload or "")
            return protocol.ack(cmd)

        elif cmd == protocol.RESET_BREAK:
            self._health.reset()
            return protocol.ack(cmd)

        elif cmd == protocol.BRIGHTNESS:
            try:
                pct = int(payload)
                self._pwm.duty_u16(int(65535 * max(0, min(100, pct)) / 100))
                return protocol.ack(cmd, payload)
            except Exception:
                return protocol.ack(cmd, payload, status="ERR")

        elif cmd == protocol.TEMP:
            try:
                from machine import ADC
                sensor = ADC(4)
                reading = sensor.read_u16() * 3.3 / 65535
                celsius = 27 - (reading - 0.706) / 0.001721
                return protocol.ack(cmd, "{:.1f}".format(celsius))
            except Exception:
                return protocol.ack(cmd, status="ERR")

        else:
            return protocol.nack(cmd)

    def update(self):
        now = time.ticks_ms()

        # ── Typewriter advance ────────────────────────────────
        if self._showing_msg:
            full_len = len(self._msg_full)

            if self._msg_reveal < full_len:
                # Still revealing characters
                if time.ticks_diff(now, self._next_char_t) >= 0:
                    self._msg_reveal += 1
                    self._next_char_t = now + TYPEWRITER_MS
                    # Scroll window if text wider than band
                    if self._msg_reveal > MAX_VIS:
                        self._msg_scroll = self._msg_reveal - MAX_VIS
            else:
                # All revealed — count down hold timer
                if self._msg_hold_end == 0:
                    self._msg_hold_end = now + MSG_HOLD_MS
                elif time.ticks_diff(now, self._msg_hold_end) >= 0:
                    self._showing_msg  = False
                    self._msg_hold_end = 0
                    self.robo.set_mood(self._current_mood)

        # ── Health timer ──────────────────────────────────────
        if self._health.due:
            self._start_message(BREAK_MSG)

        # ── Eyes (always running) ─────────────────────────────
        # _on_show() stamps the text overlay after each render
        self.robo.update()

    def deinit(self):
        self._pwm.deinit()

    # ── Private helpers ───────────────────────────────────────

    def _on_show(self, robo):
        """Called by RoboEyes after every frame. Stamp overlay then blit."""
        if self._showing_msg:
            self._stamp_overlay()
        self.lcd.show()

    def _stamp_overlay(self):
        """Stamp text directly over the already-rendered eyes frame (no background)."""
        lcd = self.lcd

        # Visible slice of the text
        start  = self._msg_scroll
        end    = min(start + MAX_VIS, self._msg_reveal)
        visible = self._msg_full[start:end]

        if visible:
            text_w = len(visible) * 8 * SCALE
            x = (240 - text_w) // 2
            y = BAND_Y + (BAND_H - 8 * SCALE) // 2
            _draw_text(lcd, visible, x, y, _WHITE, scale=SCALE)

        # Blinking cursor while still revealing
        if self._msg_reveal < len(self._msg_full):
            cx = (240 + len(visible) * 8 * SCALE) // 2
            if (time.ticks_ms() // 250) % 2 == 0:   # blink at 2 Hz
                lcd.fill_rect(cx + 2, BAND_Y + (BAND_H - 8 * SCALE) // 2,
                              SCALE, 8 * SCALE, _WHITE)

    def _start_message(self, text):
        self._msg_full     = text
        self._msg_reveal   = 0
        self._msg_scroll   = 0
        self._msg_hold_end = 0
        self._next_char_t  = time.ticks_ms() + TYPEWRITER_MS
        self._showing_msg  = True

    def _set_face(self, name):
        # Always restore default eye geometry first (in case we came from focused)
        self.robo.eyes_width(_EYE_W, _EYE_W)
        self.robo.eyes_height(_EYE_H, _EYE_H)
        self.robo.eyes_radius(_EYE_RADIUS, _EYE_RADIUS)
        self.robo.set_auto_blinker(ON, 3, 2)

        if name == "excited":
            self.robo.set_idle_mode(ON, 3, 1)
            self.robo.set_mood(HAPPY)
            self._current_mood = HAPPY
        elif name == "curious":
            # Idle wandering makes eyes drift to edges — that's when the outer
            # eye enlarges and the curious effect is actually visible
            self.robo.set_idle_mode(ON, 1, 2)
            self.robo.set_mood(CURIOUS)
            self._current_mood = CURIOUS
        elif name == "focused":
            # Circular eyes + slow blink = visually distinct "locked-in" look
            self.robo.set_idle_mode(OFF)
            self.robo.eyes_width(_FOCUSED_SIZE, _FOCUSED_SIZE)
            self.robo.eyes_height(_FOCUSED_SIZE, _FOCUSED_SIZE)
            self.robo.eyes_radius(_FOCUSED_RADIUS, _FOCUSED_RADIUS)
            self.robo.set_auto_blinker(ON, 6, 3)  # blink less when focused
            self.robo.set_mood(DEFAULT)
            self._current_mood = DEFAULT
        else:
            self.robo.set_idle_mode(OFF)
            mood = FACE_MAP.get(name, DEFAULT)
            self._current_mood = mood
            self.robo.set_mood(mood)

    def _settle(self, ms):
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < ms:
            self.robo.update()


# ── Text rendering ────────────────────────────────────────────

def _draw_text(lcd, text, x, y, color, scale=1):
    """
    Render text via a temporary MONO FrameBuffer (MicroPython built-in 8x8
    font), then blit each run of lit pixels with fill_rect at given scale.
    """
    w = len(text) * 8
    if w == 0:
        return
    buf = bytearray((w * 8 + 7) // 8)
    tmp = _framebuf.FrameBuffer(buf, w, 8, _framebuf.MONO_HLSB)
    tmp.fill(0)
    tmp.text(text, 0, 0, 1)
    for row in range(8):
        col = 0
        while col < w:
            bit_pos = row * w + col
            if buf[bit_pos >> 3] & (0x80 >> (bit_pos & 7)):
                run = col + 1
                while run < w:
                    bp = row * w + run
                    if buf[bp >> 3] & (0x80 >> (bp & 7)):
                        run += 1
                    else:
                        break
                lcd.fill_rect(
                    x + col * scale,
                    y + row * scale,
                    (run - col) * scale,
                    scale,
                    color,
                )
                col = run
            else:
                col += 1


# ── Word wrap (used externally if needed) ─────────────────────

def _wrap(text, max_chars):
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
