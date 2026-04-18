# main.py — entry point
#
# Boot sequence
# ─────────────
# 1. Initialise hardware (SPI, TFT, framebuffer adapter)
# 2. Wait up to HELLO_TIMEOUT_MS for the PC to send HELLO
#    - Received → enter companion mode
#    - Timeout  → enter bedside mode
# 3. In companion mode: watch for a heartbeat (HELLO or HB).
#    If HB_TIMEOUT_MS passes with no heartbeat, fall through to bedside.
# 4. Bedside mode runs indefinitely (no timeout / no exit).
#
# Protocol reminder (all newline-terminated):
#   HELLO / HB            keep-alive / announce connection
#   BYE                   clean disconnect
#   TIME:HH:MM:SS         sync RTC
#   FACE:<name>           eye expression
#   MSG:<text>            notification overlay
#   BRIGHTNESS:<0-100>    backlight level
#   RESET_BREAK           reset 30-min break timer

import sys
import time
import select
from machine import Pin, SPI

import st7789
from tft_adapter import TFTAdapter
import protocol

# ── Timings ───────────────────────────────────────────────────
HELLO_TIMEOUT_MS = 3_000    # wait this long at boot for a HELLO
HB_TIMEOUT_MS    = 30_000   # fall back to bedside if no heartbeat for 30 s

# ── Hardware init ─────────────────────────────────────────────
spi = SPI(0, baudrate=31_250_000, sck=Pin(2), mosi=Pin(3))

tft = st7789.ST7789(
    spi, 240, 240,
    reset=Pin(0, Pin.OUT),
    dc=Pin(4, Pin.OUT),
    cs=Pin(5, Pin.OUT),
    backlight=Pin(6, Pin.OUT),
    rotation=0,
)

# Framebuffer adapter — blue eyes on black (companion default)
lcd = TFTAdapter(tft, bgcolor=0x0000, fgcolor=0x001F)

# ── Serial helpers ────────────────────────────────────────────

def _readline_nonblocking():
    """
    Return one newline-terminated line from USB serial if available,
    or None if no data is ready right now.
    """
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if r:
        try:
            return sys.stdin.readline()
        except Exception:
            return None
    return None


def _wait_for_hello(timeout_ms):
    """
    Poll serial for HELLO/HB.  Returns (found, time_payload).
    Any TIME command seen en route is returned so the RTC can be
    set before either mode starts.
    """
    t0       = time.ticks_ms()
    time_msg = None

    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        line = _readline_nonblocking()
        if line:
            cmd, payload = protocol.parse(line)
            if cmd in (protocol.HELLO, protocol.HEARTBEAT):
                return True, time_msg
            if cmd == protocol.TIME:
                time_msg = payload
        time.sleep_ms(20)

    return False, time_msg

# ── Boot: decide mode ─────────────────────────────────────────
pc_connected, pending_time = _wait_for_hello(HELLO_TIMEOUT_MS)

# ── Companion mode loop ───────────────────────────────────────
if pc_connected:
    from companion import CompanionMode

    companion  = CompanionMode(lcd)
    last_hb    = time.ticks_ms()
    exit_loop  = False
    _saved_time = pending_time   # carry TIME forward to bedside if needed

    while not exit_loop:
        line = _readline_nonblocking()

        if line:
            cmd, payload = protocol.parse(line)

            if cmd in (protocol.HELLO, protocol.HEARTBEAT):
                last_hb = time.ticks_ms()

            elif cmd == protocol.BYE:
                exit_loop = True

            elif cmd == protocol.TIME:
                # Time is only needed for bedside RTC; store and carry forward
                _saved_time = payload

            elif cmd:
                companion.handle(cmd, payload)

        # Heartbeat watchdog — assume cable pulled or PC script crashed
        if time.ticks_diff(time.ticks_ms(), last_hb) > HB_TIMEOUT_MS:
            exit_loop = True

        companion.update()

    # Release PWM pin and free memory before loading bedside
    companion.deinit()
    del companion
    pending_time = _saved_time

# ── Bedside mode loop (runs indefinitely) ─────────────────────
from bedside import BedsideMode

bedside = BedsideMode(lcd)

# Sync RTC if we received a TIME at any point before now
if pending_time:
    result = protocol.parse_time(pending_time)
    if result:
        bedside.set_time(*result)

bedside.update()   # draw immediately without waiting for minute tick

while True:
    # Even in bedside mode, keep an ear out for the PC script.
    # If it reconnects, do a soft reset to re-enter companion cleanly.
    line = _readline_nonblocking()
    if line:
        cmd, payload = protocol.parse(line)
        if cmd in (protocol.HELLO, protocol.HEARTBEAT):
            import machine
            machine.reset()    # clean re-boot → will detect HELLO next time
        elif cmd == protocol.TIME:
            result = protocol.parse_time(payload)
            if result:
                bedside.set_time(*result)

    bedside.update()
    time.sleep_ms(100)
