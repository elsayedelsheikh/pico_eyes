# bedside.py — minimal bedside clock mode
#
# Display layout (240×240):
#   - Two thin sleepy-eye slits, vertically centred around y=90
#   - Large 7-segment HH:MM clock, centred in the lower half
#
# Brightness dims automatically based on the hour:
#   23:00–05:00  →  3 %   (almost off, doesn't disturb sleep)
#   05:00–07:00  →  15 %  (gentle dawn ramp)
#   07:00–09:00  →  40 %  (morning)
#   09:00–23:00  →  65 %  (normal room)
#
# Time is kept by the RP2040 hardware RTC.
# The PC-side script should send  TIME:HH:MM:SS  on first connect
# so the RTC is accurate; after that it runs autonomously.

from machine import RTC, PWM, Pin
import time

# ── RGB565 colours (standard, adapter handles byte-swap) ──────
_BG         = 0x0000   # black
_AMBER      = 0xFD20   # warm amber  (R=31 G=41 B=0) — clock digits
_EYE_GREY   = 0x2104   # very dim grey — sleepy eye slits

# ── 7-segment digit geometry ──────────────────────────────────
# Each digit cell: W×H pixels
_DW = 36   # digit width
_DH = 58   # digit height
_T  = 6    # bar thickness

# Segment definitions — offsets relative to cell origin (x, y)
# Returns dict {seg_name: (rx, ry, rw, rh)}  ready for fill_rect
def _make_segs(x, y):
    w, h, t = _DW, _DH, _T
    mid = h // 2
    return {
        'a': (x + t,     y,              w - 2*t, t     ),  # top horiz
        'b': (x + w - t, y + t,          t,       mid - t),  # top-right vert
        'c': (x + w - t, y + mid,        t,       mid - t),  # bot-right vert
        'd': (x + t,     y + h - t,      w - 2*t, t     ),  # bot horiz
        'e': (x,         y + mid,        t,       mid - t),  # bot-left vert
        'f': (x,         y + t,          t,       mid - t),  # top-left vert
        'g': (x + t,     y + mid - t//2, w - 2*t, t     ),  # middle horiz
    }

# Which segments are ON for each character
_SEGS_ON = {
    '0': 'abcdef',
    '1': 'bc',
    '2': 'abdeg',
    '3': 'abcdg',
    '4': 'bcfg',
    '5': 'acdfg',
    '6': 'acdefg',
    '7': 'abc',
    '8': 'abcdefg',
    '9': 'abcdfg',
}

_COLON_W = 18   # width reserved for the colon separator
_GAP     = 5    # gap between digit cells


def _total_clock_width():
    # "HH:MM" → 4 digits + 1 colon + gaps
    return 4 * _DW + _COLON_W + 4 * _GAP


class BedsideMode:
    """
    Bedside clock.  Call update() in a loop — it redraws only when the
    minute changes, so it's extremely light on CPU.
    """

    def __init__(self, lcd, bl_pin=6):
        """
        lcd     — TFTAdapter instance (already initialised)
        bl_pin  — GPIO pin number used for backlight (PWM-capable)
        """
        self.lcd  = lcd
        self._pwm = PWM(Pin(bl_pin))
        self._pwm.freq(1000)
        self._rtc = RTC()
        self._last_min = -1   # force first draw

        # Start at appropriate brightness right away
        dt = self._rtc.datetime()
        self._set_brightness(self._brightness_for(dt[4]))

    # ── Public API ────────────────────────────────────────────

    def set_time(self, h, m, s=0):
        """Sync RTC from a TIME:HH:MM:SS message."""
        dt = self._rtc.datetime()
        # Keep date fields, update time fields
        self._rtc.datetime((dt[0], dt[1], dt[2], dt[3], h, m, s, 0))
        self._last_min = -1   # force immediate redraw

    def update(self):
        """Call this in the main loop. Redraws on minute change."""
        dt  = self._rtc.datetime()
        h, m = dt[4], dt[5]
        if m != self._last_min:
            self._last_min = m
            self._draw(h, m)
            self._set_brightness(self._brightness_for(h))

    def force_redraw(self):
        """Redraw immediately (e.g. after switching from companion mode)."""
        self._last_min = -1

    # ── Private helpers ───────────────────────────────────────

    def _set_brightness(self, pct):
        """Set backlight brightness 0–100 %."""
        self._pwm.duty_u16(int(65535 * max(0, min(100, pct)) / 100))

    @staticmethod
    def _brightness_for(hour):
        if hour >= 23 or hour < 5:
            return 3
        elif hour < 7:
            return 15
        elif hour < 9:
            return 40
        else:
            return 65

    def _draw_digit(self, ch, x, y):
        """Draw a single 7-segment digit at cell origin (x, y)."""
        segs   = _make_segs(x, y)
        active = _SEGS_ON.get(ch, '')
        for name, rect in segs.items():
            color = _AMBER if name in active else _BG
            self.lcd.fill_rect(*rect, color)

    def _draw_colon(self, x, y):
        """Draw the HH:MM separator dots."""
        cx = x + _COLON_W // 2 - 3
        dot_h = _T
        self.lcd.fill_rect(cx, y + _DH // 3,       6, dot_h, _AMBER)
        self.lcd.fill_rect(cx, y + 2 * _DH // 3,   6, dot_h, _AMBER)

    def _draw(self, h, m):
        """Full screen redraw."""
        lcd = self.lcd
        lcd.fill(_BG)

        # ── Sleepy eyes (two thin horizontal slits) ───────────
        ey = 88    # vertical centre of eyes
        # left slit
        lcd.fill_rect(48,  ey, 58, 5, _EYE_GREY)
        # right slit
        lcd.fill_rect(134, ey, 58, 5, _EYE_GREY)

        # ── Clock ─────────────────────────────────────────────
        tw  = _total_clock_width()
        x0  = (240 - tw) // 2
        y0  = 142   # vertically centred in lower half

        time_str = "{:02d}:{:02d}".format(h, m)
        x = x0
        for ch in time_str:
            if ch == ':':
                self._draw_colon(x, y0)
                x += _COLON_W + _GAP
            else:
                self._draw_digit(ch, x, y0)
                x += _DW + _GAP

        lcd.show()
