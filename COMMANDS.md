# pico_eyes — Serial Command Reference

All commands are sent over USB serial as plain ASCII, newline-terminated.
Baud rate: 115200. Commands are case-insensitive on the Pico side.

The Pico sends back an ACK or NACK line after every command so the PC
script can confirm delivery and validity.

---

## ACK / NACK format

| Response | Meaning |
|----------|---------|
| `ACK:<CMD>:OK` | Command recognised and applied |
| `ACK:<CMD>:<detail>:OK` | Command applied (detail echoes the value used) |
| `ACK:<CMD>:<detail>:UNKNOWN` | Command known but value not recognised (fallback applied) |
| `ACK:<CMD>:<detail>:ERR` | Command known but value was invalid / unparseable |
| `NACK:<CMD>:UNKNOWN` | Command not recognised at all |

---

## Connection / lifecycle

| Command | Example | ACK response | Description |
|---------|---------|--------------|-------------|
| `HELLO` | `HELLO` | `ACK:HELLO:OK` | Announce connection. Must arrive within 10 s of boot to enter companion mode. Also acts as a heartbeat. |
| `HB`    | `HB`    | `ACK:HB:OK`    | Heartbeat keep-alive. Send every ~10 s to stay in companion mode. 30 s without one → Pico falls back to bedside. |
| `BYE`   | `BYE`   | `ACK:BYE:OK`   | Clean disconnect. Pico immediately switches to bedside (clock) mode. |

---

## Time

| Command | Example | ACK response | Description |
|---------|---------|--------------|-------------|
| `TIME:HH:MM:SS` | `TIME:14:30:00` | `ACK:TIME:14:30:00:OK` | Sync the Pico RTC. Send on connect so the bedside clock is accurate after you unplug. `HH:MM` also accepted (seconds default to 0). Invalid values → `ERR`. |

---

## Companion mode — display

| Command | Example | ACK response | Description |
|---------|---------|--------------|-------------|
| `FACE:<name>` | `FACE:happy` | `ACK:FACE:happy:OK` | Change the RoboEyes expression. Unknown name → `UNKNOWN` status, falls back to `default`. |
| `MSG:<text>`  | `MSG:Update your Jira ticket` | `ACK:MSG:OK` | Shows a typewriter-animated text overlay at the bottom of the screen. Eyes stay alive above it. Text scrolls if longer than 15 chars. Clears automatically after a 3 s hold. |
| `BRIGHTNESS:<0-100>` | `BRIGHTNESS:40` | `ACK:BRIGHTNESS:40:OK` | Set backlight brightness as a percentage. Non-integer value → `ERR`. |

### Face names

| Name      | ACK detail | Expression |
|-----------|------------|------------|
| `default` | `default`  | Neutral, relaxed |
| `happy`   | `happy`    | Wide, upbeat |
| `tired`   | `tired`    | Half-closed, droopy |
| `angry`   | `angry`    | Furrowed, intense |
| `curious` | `curious`  | Tilted, interested |
| `scary`   | `scary`    | Wide, unsettling |
| `frozen`  | `frozen`   | Locked open, unblinking |

Any other name → `ACK:FACE:<name>:UNKNOWN`, falls back to `default`.

---

## Health / break timer

| Command | Example | ACK response | Description |
|---------|---------|--------------|-------------|
| `RESET_BREAK` | `RESET_BREAK` | `ACK:RESET_BREAK:OK` | Restart the 30-minute break countdown. The Pico fires a typewriter message automatically when time is up. Call this after the user acknowledges the reminder. |

---

## Mode behaviour summary

```
Boot
 └─ wait 10 s for HELLO
     ├─ HELLO received  → companion mode
     │    └─ BYE or 30 s no heartbeat → bedside mode
     │         └─ HELLO received any time → back to companion (no reboot)
     └─ timeout         → bedside mode
          └─ HELLO received any time → back to companion (no reboot)
```

Bedside mode shows a dim HH:MM clock with sleepy eyes. Brightness
adjusts automatically by hour (3 % at night, 65 % during the day).

---

## Quick test sequence (PuTTY / any serial terminal at 115200)

```
HELLO                        → ACK:HELLO:OK
TIME:09:00:00                → ACK:TIME:09:00:00:OK
FACE:happy                   → ACK:FACE:happy:OK
FACE:tired                   → ACK:FACE:tired:OK
FACE:angry                   → ACK:FACE:angry:OK
FACE:blorp                   → ACK:FACE:blorp:UNKNOWN
MSG:PR approved nice work    → ACK:MSG:OK
MSG:Hey stand up take a walk → ACK:MSG:OK
BRIGHTNESS:50                → ACK:BRIGHTNESS:50:OK
BRIGHTNESS:xx                → ACK:BRIGHTNESS:xx:ERR
RESET_BREAK                  → ACK:RESET_BREAK:OK
FOOBAR                       → NACK:FOOBAR:UNKNOWN
BYE                          → ACK:BYE:OK
```
