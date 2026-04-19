#!/usr/bin/env python3
"""
host/demo.py — interactive walkthrough of all pico_eyes features.

Run with: python3 host/demo.py
Pico must be plugged in via USB before running.
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from serial_link import SerialLink

HB_INTERVAL = 8   # send HB at least this often (well under the 30 s Pico timeout)


def _pause(link: SerialLink, seconds: float):
    """Sleep for `seconds`, sending HB immediately and every 8 s so the Pico stays alive."""
    link.send("HB")          # reset heartbeat timer right at the start of every pause
    remaining = seconds
    while remaining > 0.1:
        sleep_for = min(HB_INTERVAL, remaining)
        time.sleep(sleep_for)
        remaining -= sleep_for
        if remaining > 0.1:
            link.send("HB")
    if remaining > 0:
        time.sleep(remaining)


def step(label: str, cmd: str, link: SerialLink, hold: float = 4.0):
    print(f"\n  [{label}]")
    print(f"  → {cmd}")
    ack = link.send(cmd)
    print(f"  ← {ack}")
    _pause(link, hold)


def section(title: str):
    print(f"\n{'─' * 52}")
    print(f"  {title}")
    print(f"{'─' * 52}")


def main():
    link = SerialLink()

    print("\npico_eyes demo — connecting...")
    if not link.connect():
        print("ERROR: Pico not found on /dev/ttyACM*. Plug it in and retry.")
        sys.exit(1)
    print("  connected.\n")
    _pause(link, 1.5)

    # ── 1. All faces ──────────────────────────────────────────────
    section("1 / 7  FACES — mood expressions")
    print("  Cycling through all available expressions.\n")
    step("wake up",         "FACE:tired",    link, hold=4)
    step("neutral",         "FACE:default",  link, hold=4)
    step("curious",         "FACE:curious",  link, hold=5)
    step("happy",           "FACE:happy",    link, hold=4)
    step("angry",           "FACE:angry",    link, hold=4)
    step("scary",           "FACE:scary",    link, hold=4)
    step("frozen",          "FACE:frozen",   link, hold=4)
    step("excited (git!)",  "FACE:excited",  link, hold=6)
    step("back to neutral", "FACE:default",  link, hold=3)

    # ── 2. Activity intensity (as daemon drives it) ────────────────
    section("2 / 7  ACTIVITY INTENSITY")
    print("  Simulates the daemon's face selection based on keystrokes/min.\n")
    step("low  (0–20 keys/min)  → default",  "FACE:default",  link, hold=5)
    step("mid  (21–80 keys/min) → focused",  "FACE:focused",  link, hold=7)
    step("high (>80 keys/min)   → excited",  "FACE:excited",  link, hold=6)
    step("idle (5 min silent)   → tired",    "FACE:tired",    link, hold=5)
    step("returns from idle     → default",  "FACE:default",  link, hold=4)

    # ── 3. Focused face up close ───────────────────────────────────
    section("3 / 7  FOCUSED FACE  (circular eyes)")
    print("  Large circular eyes + slower blink = 'locked-in' look.\n")
    step("default  (rectangular)", "FACE:default",  link, hold=5)
    step("focused  (circular)",    "FACE:focused",  link, hold=8)
    step("back to default",        "FACE:default",  link, hold=4)

    # ── 4. Message overlay ─────────────────────────────────────────
    section("4 / 7  MESSAGE OVERLAY  (typewriter effect)")
    print("  Text scrolls in at the bottom of the screen.\n")
    step("short message",   "MSG:Hello, Sayed!",              link, hold=5)
    step("break reminder",  "MSG:Hey. Stand up. 5 min walk.", link, hold=7)
    step("weather + temp",  "MSG:28\u00b0C \u26c5 | pico:24\u00b0C", link, hold=7)

    # ── 5. Temperature sensor ──────────────────────────────────────
    section("5 / 7  PICO INTERNAL TEMPERATURE")
    print("  Reads the RP2040 on-chip temperature sensor (ADC channel 4).\n")
    print("  [read chip temp]")
    print("  → TEMP")
    ack = link.send("TEMP")
    print(f"  ← {ack}")
    parts = ack.split(":")
    if len(parts) >= 3 and parts[0] == "ACK":
        try:
            celsius = float(parts[2])
            print(f"\n  Chip temperature: {celsius:.1f} °C")
        except ValueError:
            print("  (could not parse)")
    _pause(link, 4)

    # ── 6. Brightness ──────────────────────────────────────────────
    section("6 / 7  BACKLIGHT BRIGHTNESS")
    print("  Dimming and restoring the display.\n")
    step("dim   20%",  "BRIGHTNESS:20",  link, hold=4)
    step("mid   60%",  "BRIGHTNESS:60",  link, hold=4)
    step("full 100%",  "BRIGHTNESS:100", link, hold=4)

    # ── 7. Break timer reset ───────────────────────────────────────
    section("7 / 7  BREAK TIMER RESET")
    print("  Sent by daemon when you return from idle → restarts 30-min countdown.\n")
    step("reset break timer", "RESET_BREAK", link, hold=4)

    # ── Done ────────────────────────────────────────────────────────
    section("DONE")
    print("  All features demonstrated. Sending BYE — Pico returns to bedside.\n")
    link.disconnect()
    print("  Disconnected.\n")
    print("  Next steps:")
    print("    Upload firmware : python3 host/pico_upload.py main.py protocol.py companion.py")
    print("    Start daemon    : python3 host/daemon.py\n")


if __name__ == "__main__":
    main()
