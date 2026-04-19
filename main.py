# main.py — entry point
#
# Boot sequence
# ─────────────
# 1. Initialise hardware (SPI, TFT, framebuffer adapter)
# 2. Outer loop: wait up to HELLO_TIMEOUT_MS for the PC to send HELLO
#    - Received → companion mode (handles FACE, MSG, etc.)
#    - Timeout  → bedside mode (clock + sleepy eyes)
# 3. Either mode can exit back to the outer loop:
#    - Companion exits when BYE received or heartbeat times out
#    - Bedside exits the moment HELLO is received
#    No reboot needed — transitions are seamless.
#
# Protocol (all newline-terminated):
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
HELLO_TIMEOUT_MS = 10_000   # how long to wait for HELLO before going to bedside
HB_TIMEOUT_MS    = 30_000   # companion → bedside if no heartbeat for 30 s

# ── Hardware init (once, shared across all modes) ─────────────
spi = SPI(0, baudrate=31_250_000, sck=Pin(2), mosi=Pin(3))

tft = st7789.ST7789(
    spi, 240, 240,
    reset=Pin(0, Pin.OUT),
    dc=Pin(4, Pin.OUT),
    cs=Pin(5, Pin.OUT),
    backlight=Pin(6, Pin.OUT),
    rotation=0,
)

lcd = TFTAdapter(tft, bgcolor=0x0000, fgcolor=0x001F)

# ── Serial helpers ────────────────────────────────────────────

def _readline_nonblocking():
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if r:
        try:
            return sys.stdin.readline()
        except Exception:
            return None
    return None


def _wait_for_hello(timeout_ms):
    """
    Poll serial for HELLO/HB up to timeout_ms.
    Returns (found: bool, time_payload: str|None).
    """
    t0       = time.ticks_ms()
    time_msg = None
    last_sec = -1

    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        elapsed_s = time.ticks_diff(time.ticks_ms(), t0) // 1000
        if elapsed_s != last_sec:
            remaining = (timeout_ms // 1000) - elapsed_s
            print("  waiting:", remaining, "s  (send HELLO to enter companion mode)")
            last_sec = elapsed_s

        line = _readline_nonblocking()
        if line:
            cmd, payload = protocol.parse(line)
            if cmd in (protocol.HELLO, protocol.HEARTBEAT):
                print(protocol.ack(cmd))
                return True, time_msg
            if cmd == protocol.TIME:
                time_msg = payload
        time.sleep_ms(20)

    return False, time_msg

# ── Shared RTC sync ───────────────────────────────────────────
_pending_time = None   # TIME payload carried between modes

# ── Main loop — cycles between companion and bedside ─────────
while True:

    # ── Wait for PC ──────────────────────────────────────────
    print("pico_eyes: waiting for HELLO ({:d}s)...".format(HELLO_TIMEOUT_MS // 1000))
    pc_connected, t = _wait_for_hello(HELLO_TIMEOUT_MS)
    if t:
        _pending_time = t

    # ── Companion mode ────────────────────────────────────────
    if pc_connected:
        from companion import CompanionMode

        print("pico_eyes: entering companion mode")
        companion = CompanionMode(lcd)
        last_hb   = time.ticks_ms()
        exit_companion = False

        while not exit_companion:
            line = _readline_nonblocking()

            if line:
                cmd, payload = protocol.parse(line)

                if cmd in (protocol.HELLO, protocol.HEARTBEAT):
                    last_hb = time.ticks_ms()
                    print(protocol.ack(cmd))

                elif cmd == protocol.BYE:
                    print(protocol.ack(cmd))
                    exit_companion = True

                elif cmd == protocol.TIME:
                    _pending_time = payload
                    if protocol.parse_time(payload):
                        print(protocol.ack(cmd, payload))
                    else:
                        print(protocol.ack(cmd, payload, status="ERR"))

                elif cmd:
                    print(companion.handle(cmd, payload))

                # empty / unparseable line — silently ignore

            if time.ticks_diff(time.ticks_ms(), last_hb) > HB_TIMEOUT_MS:
                print("pico_eyes: heartbeat lost, switching to bedside")
                exit_companion = True

            companion.update()

        companion.deinit()
        del companion
        # Loop back to top → will wait for HELLO again before bedside
        continue

    # ── Bedside mode ──────────────────────────────────────────
    from bedside import BedsideMode

    print("pico_eyes: entering bedside mode")
    bedside = BedsideMode(lcd)

    if _pending_time:
        result = protocol.parse_time(_pending_time)
        if result:
            bedside.set_time(*result)

    bedside.update()

    while True:
        line = _readline_nonblocking()
        if line:
            cmd, payload = protocol.parse(line)
            if cmd in (protocol.HELLO, protocol.HEARTBEAT):
                print(protocol.ack(cmd))
                print("pico_eyes: HELLO received, switching to companion")
                del bedside
                break   # breaks inner while → outer while → wait for HELLO
            elif cmd == protocol.TIME:
                result = protocol.parse_time(payload)
                if result:
                    _pending_time = payload
                    bedside.set_time(*result)
                    print(protocol.ack(cmd, payload))
                else:
                    print(protocol.ack(cmd, payload, status="ERR"))

        bedside.update()
        time.sleep_ms(100)
