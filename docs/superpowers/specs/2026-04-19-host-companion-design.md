# Host Companion Daemon — Design Spec
**Date:** 2026-04-19
**Branch:** feat/dev-companion

---

## Overview

A Python daemon running as a systemd user service on the host PC. It connects to the Pico over USB serial and drives the display based on real-world desk events: keyboard activity, git pushes, weather, and Pico temperature. The Pico's existing serial protocol (`HELLO/HB/BYE/FACE/MSG/BRIGHTNESS/RESET_BREAK`) is extended with one new command (`TEMP`).

---

## Pico Changes

### New command: `TEMP`

The RP2040 has an internal temperature sensor on ADC channel 4.

- **Host sends:** `TEMP`
- **Pico responds:** `ACK:TEMP:23.4:OK`
- **On error:** `ACK:TEMP:ERR`

**Files to change:**
- `protocol.py` — add `TEMP = "TEMP"` constant
- `companion.py` — handle `TEMP` in `handle()`: read ADC channel 4, convert to °C, return ACK with value
- `main.py` — no changes needed (already routes all commands through `companion.handle()`)

**ADC conversion formula:**
```python
from machine import ADC
sensor = ADC(4)
reading = sensor.read_u16() * 3.3 / 65535
celsius = 27 - (reading - 0.706) / 0.001721
```

---

## Host Daemon

### File layout

```
host/
├── daemon.py             # entry point: main event loop + state machine
├── events.py             # event dataclasses
├── serial_link.py        # owns serial port: HELLO/HB/reconnect
├── producers/
│   ├── keyboard.py       # pynput: keystrokes + mouse → activity events
│   ├── weather.py        # wttr.in poll every 30 min
│   ├── ipc_server.py     # Unix socket server: git push + upload events
│   └── temp.py           # sends TEMP to Pico every 30 min
├── pico_upload.py        # CLI wrapper: coordinates upload handshake + mpremote
└── pico_eyes.service     # systemd user unit file
```

### Events (`events.py`)

Plain `dataclass` objects pushed into a `queue.Queue` by producer threads:

| Event | Fields | Source |
|-------|--------|--------|
| `KeystrokeEvent` | `timestamp: float` | keyboard.py |
| `MouseMoveEvent` | `timestamp: float` | keyboard.py |
| `GitPushEvent` | `branch: str` | ipc_server.py |
| `UploadRequestEvent` | `conn: socket` | ipc_server.py (carries open conn for ACK) |
| `WeatherUpdateEvent` | `text: str` | weather.py |
| `TempRequestEvent` | — | temp.py (fires every 30 min) |
| `TickEvent` | — | daemon.py (1 Hz timer thread) |

---

### State machine (`daemon.py`)

Two states:

```
ACTIVE   — recent keyboard/mouse activity detected
IDLE     — no activity for ≥ 5 minutes
```

**Activity intensity → face (evaluated each TickEvent while ACTIVE):**

| Keystrokes in last 60 s | Face sent |
|------------------------|-----------|
| 0–20 | `FACE:default` |
| 21–80 | `FACE:curious` |
| > 80 | `FACE:excited` |

**State transitions:**

```
ACTIVE  + no events for 5 min    → IDLE   → FACE:tired  (yawning/bored look)
IDLE    + KeystrokeEvent         → ACTIVE + send RESET_BREAK
ACTIVE/IDLE + GitPushEvent       → send FACE:excited, hold 8 s, restore face
```

**Break flow:** The Pico's `HealthTimer` fires autonomously after 30 min and shows the break message on the display — no host involvement needed. When the user returns to the keyboard (first `KeystrokeEvent` while IDLE), the host sends `RESET_BREAK`, which restarts the Pico's 30-min countdown, and transitions back to `ACTIVE`. Sending `RESET_BREAK` on any IDLE→ACTIVE transition is always correct: whether the user was on a break or just stepped away briefly, restarting the countdown is the right behaviour.

**Weather + temp (any state):**
Every 30 min `WeatherUpdateEvent` and `TempReadingEvent` arrive in sequence. Main loop combines them into a single `MSG`:
```
MSG:28°C ☁ | pico:24°C
```

---

### Serial link (`serial_link.py`)

- Auto-detects Pico port by scanning `/dev/ttyACM*`
- Sends `HELLO` + `TIME:HH:MM:SS` on connect
- Sends `HB` every 10 s (triggered by `TickEvent` in main loop)
- Reconnects silently if Pico is unplugged and re-plugged (retry with 5 s backoff)
- Exposes single method: `send(cmd: str) -> str` — writes line, reads and returns ACK
- Only ever called from the main thread — no locking needed

---

### Producers

**`keyboard.py`**
- Uses `pynput` library
- Listens for `on_press` (keyboard) and `on_move` (mouse)
- Puts `KeystrokeEvent` / `MouseMoveEvent` into queue on each event
- Runs as a daemon thread (pynput manages its own OS-level listener)

**`weather.py`**
- GET `https://wttr.in/?format=3` every 30 min
- Parses response (e.g. `"Cairo: ⛅ +28°C"`) → strips city name → `WeatherUpdateEvent(text="28°C ⛅")`
- Sleeps 30 min between requests
- On network error: skips silently, retries next cycle

**`temp.py`**
- Puts `TempRequestEvent` into queue every 30 min
- Main loop receives it, sends `TEMP` to Pico (serial stays on main thread), parses the ACK value, caches it as `_last_temp_celsius`
- Combined MSG sent only when both `_last_weather_text` and `_last_temp_celsius` are available

**`ipc_server.py`**
- Opens Unix domain socket at `/tmp/pico_eyes.sock`
- Blocks on `accept()` waiting for connections
- Parses message prefix to determine event type:
  - `PUSH:<branch>` → puts `GitPushEvent(branch=branch)` into queue, closes connection
  - `UPLOAD` → puts `UploadRequestEvent(conn=conn)` into queue, **keeps connection open** until daemon sends `OK\n` back
- Handles git push and pico-upload from the same socket

---

### Concurrency model

```
[keyboard thread]    ──┐
[weather thread]     ──┤
[ipc_server thread]  ──┼──► queue.Queue ──► main thread ──► Pico serial
[tick thread]        ──┤                         │
[temp thread]        ──┘                    state machine
```

All threads are producers only. The main thread is the sole consumer and sole writer to the serial port. No locks needed — `queue.Queue` is thread-safe by design.

---

### Systemd unit (`pico_eyes.service`)

Installed to `~/.config/systemd/user/pico_eyes.service`:

```ini
[Unit]
Description=Pico Eyes companion daemon
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 /home/sayed/Projects/pico_eyes/host/daemon.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable: `systemctl --user enable --now pico_eyes`
Logs: `journalctl --user -u pico_eyes -f`

---

## Git Hook (global)

Global git hook so every repo triggers `FACE:excited` on push.

**`~/.git-hooks/post-push`:**
```bash
#!/bin/sh
branch=$(git rev-parse --abbrev-ref HEAD)
echo "PUSH:$branch" | nc -U /tmp/pico_eyes.sock 2>/dev/null || true
```

**`~/.gitconfig`:**
```ini
[core]
    hooksPath = ~/.git-hooks
```

The `|| true` ensures git push never fails if the daemon isn't running.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `pyserial` | USB serial to Pico |
| `pynput` | Global keyboard/mouse listener |
| `requests` | wttr.in HTTP call |

Install: `pip install pyserial pynput requests`

---

## pico-upload (`host/pico_upload.py`)

A CLI wrapper that coordinates a safe upload handshake with the daemon so you never have to manually stop/start it.

**Usage:**
```sh
python host/pico_upload.py main.py companion.py health.py
# or install as a shell alias: pico-upload main.py companion.py
```

**Flow:**
```
1. pico_upload.py connects to /tmp/pico_eyes.sock, sends "UPLOAD"
2. Daemon receives UploadRequestEvent:
   - sends BYE to Pico
   - closes serial port
   - writes "OK\n" back through the socket connection
3. pico_upload.py receives "OK" → runs: mpremote cp <files> :
4. pico_upload.py exits (socket closes)
5. Daemon's serial_link.py reconnects automatically (existing logic)
6. On reconnect → sends FACE:excited for 5 s, then returns to previous face
```

**Why keep the socket open until "OK":** ensures `mpremote` only starts after the daemon has actually released the port, not just after sending the request. Avoids a race condition on slow systems.

**If daemon is not running:** `nc` fails silently → `pico_upload.py` falls back to running `mpremote` directly without handshake.

---

## Out of scope

- No GUI or tray icon
- No config file (constants live in `daemon.py` for now)
- No MSG command from host to Pico for arbitrary notifications (can be added later as a new event type)
