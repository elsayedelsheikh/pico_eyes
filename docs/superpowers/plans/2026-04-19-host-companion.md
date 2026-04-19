# Host Companion Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python daemon that runs on the host PC as a systemd service, monitors keyboard activity / git pushes / weather, and drives the Pico Eyes display over USB serial.

**Architecture:** Event-queue pattern — multiple producer threads push typed event objects into a `queue.Queue`; the main thread is the sole consumer and sole writer to the serial port. All business logic lives in a pure `StateMachine` class that takes events and returns serial command strings, making it fully testable without hardware.

**Tech Stack:** Python 3.10+, `pyserial`, `pynput`, `requests`, `pytest`, MicroPython on Pico (existing), `mpremote` (dev tool, not a dependency of the daemon)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `protocol.py` | Add `TEMP` constant |
| Modify | `companion.py` | Handle `TEMP` command, read RP2040 ADC |
| Create | `host/events.py` | All event dataclasses |
| Create | `host/serial_link.py` | Serial port owner: connect, send, reconnect |
| Create | `host/state_machine.py` | Pure state machine: events in, serial commands out |
| Create | `host/producers/__init__.py` | Empty package marker |
| Create | `host/producers/keyboard.py` | pynput keyboard+mouse → queue |
| Create | `host/producers/weather.py` | wttr.in poll → queue |
| Create | `host/producers/ipc_server.py` | Unix socket: git push + upload → queue |
| Create | `host/producers/temp.py` | Periodic TempRequestEvent → queue |
| Create | `host/daemon.py` | Entry point: start threads, run event loop |
| Create | `host/pico_upload.py` | CLI upload wrapper with daemon handshake |
| Create | `host/pico_eyes.service` | systemd user unit |
| Create | `tests/host/test_state_machine.py` | State machine unit tests |
| Create | `tests/host/test_weather.py` | Weather text parsing tests |
| Create | `tests/host/test_pico_upload.py` | Upload handshake tests |

---

## Task 1: Pico — Add TEMP command

**Files:**
- Modify: `protocol.py`
- Modify: `companion.py`

- [ ] **Step 1: Add TEMP constant to protocol.py**

Open `protocol.py`. After the `RESET_BREAK` constant line, add:

```python
TEMP          = "TEMP"
```

- [ ] **Step 2: Handle TEMP in companion.py**

In `companion.py`, inside `CompanionMode.handle()`, add a new `elif` branch after the `BRIGHTNESS` block (before the final `else`):

```python
        elif cmd == protocol.TEMP:
            try:
                from machine import ADC
                sensor = ADC(4)
                reading = sensor.read_u16() * 3.3 / 65535
                celsius = 27 - (reading - 0.706) / 0.001721
                return protocol.ack(cmd, "{:.1f}".format(celsius))
            except Exception:
                return protocol.ack(cmd, status="ERR")
```

- [ ] **Step 3: Upload and manually verify**

```bash
systemctl --user stop pico_eyes 2>/dev/null; true
mpremote cp protocol.py : + cp companion.py :
```

Then open a serial terminal at 115200 and test:
```
HELLO            → ACK:HELLO:OK
TEMP             → ACK:TEMP:24.3:OK   (value will vary by room temp)
```

- [ ] **Step 4: Commit**

```bash
git add protocol.py companion.py
git commit -m "feat(pico): add TEMP command to read RP2040 internal sensor"
```

---

## Task 2: Host scaffold — events.py

**Files:**
- Create: `host/events.py`
- Create: `host/producers/__init__.py`

- [ ] **Step 1: Create host/producers/__init__.py**

```bash
mkdir -p host/producers
touch host/producers/__init__.py
```

- [ ] **Step 2: Create host/events.py**

```python
# host/events.py
from dataclasses import dataclass
import socket as _socket


@dataclass
class KeystrokeEvent:
    timestamp: float


@dataclass
class MouseMoveEvent:
    timestamp: float


@dataclass
class GitPushEvent:
    branch: str


@dataclass
class UploadRequestEvent:
    conn: _socket.socket


@dataclass
class WeatherUpdateEvent:
    text: str


@dataclass
class TempRequestEvent:
    pass


@dataclass
class TickEvent:
    pass
```

- [ ] **Step 3: Commit**

```bash
git add host/events.py host/producers/__init__.py
git commit -m "feat(host): add event dataclasses and producers package"
```

---

## Task 3: serial_link.py

**Files:**
- Create: `host/serial_link.py`

- [ ] **Step 1: Create host/serial_link.py**

```python
# host/serial_link.py
import glob
import time
import serial

BAUD    = 115200
TIMEOUT = 2.0


class SerialLink:

    def __init__(self):
        self._ser = None

    def connect(self) -> bool:
        """Scan /dev/ttyACM*, open the first one, send HELLO + TIME. Returns True on success."""
        ports = glob.glob('/dev/ttyACM*')
        if not ports:
            return False
        try:
            self._ser = serial.Serial(ports[0], BAUD, timeout=TIMEOUT)
            time.sleep(0.5)          # give Pico time to settle after USB reset
            t = time.localtime()
            self.send("HELLO")
            self.send("TIME:{:02d}:{:02d}:{:02d}".format(t.tm_hour, t.tm_min, t.tm_sec))
            return True
        except Exception:
            self._ser = None
            return False

    def disconnect(self):
        """Send BYE and close the port."""
        if self._ser and self._ser.is_open:
            try:
                self._ser.write(b"BYE\n")
                self._ser.flush()
            except Exception:
                pass
            self._ser.close()
        self._ser = None

    def send(self, cmd: str) -> str:
        """Write cmd + newline, read and return the ACK line. Returns '' on any failure."""
        if not self._ser or not self._ser.is_open:
            return ''
        try:
            self._ser.write((cmd + '\n').encode())
            self._ser.flush()
            return self._ser.readline().decode().strip()
        except Exception:
            self._ser = None
            return ''

    def ensure_connected(self) -> bool:
        """Reconnect if not connected. Returns True if connected after the call."""
        if self.connected:
            return True
        return self.connect()

    @property
    def connected(self) -> bool:
        return self._ser is not None and self._ser.is_open
```

- [ ] **Step 2: Commit**

```bash
git add host/serial_link.py
git commit -m "feat(host): add SerialLink — serial port owner with auto-reconnect"
```

---

## Task 4: state_machine.py + tests

**Files:**
- Create: `host/state_machine.py`
- Create: `tests/host/test_state_machine.py`

- [ ] **Step 1: Write the failing tests first**

```bash
mkdir -p tests/host
```

Create `tests/host/test_state_machine.py`:

```python
# tests/host/test_state_machine.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host'))

import time
from state_machine import StateMachine, State

NOW = 1_000_000.0   # arbitrary fixed timestamp


def _sm():
    """Fresh state machine with stable timestamp baseline."""
    sm = StateMachine()
    sm._last_activity = NOW
    return sm


def test_initial_state_is_active():
    assert _sm().state == State.ACTIVE


def test_activity_while_idle_transitions_to_active_and_resets_break():
    sm = _sm()
    sm.state = State.IDLE
    cmds = sm.on_activity(NOW)
    assert sm.state == State.ACTIVE
    assert "RESET_BREAK" in cmds


def test_activity_while_active_does_not_reset_break():
    sm = _sm()
    cmds = sm.on_activity(NOW)
    assert "RESET_BREAK" not in cmds


def test_tick_after_5min_silence_transitions_to_idle():
    sm = _sm()
    sm._last_activity = NOW - 301
    cmds = sm.on_tick(NOW)
    assert sm.state == State.IDLE
    assert "FACE:tired" in cmds


def test_tick_before_5min_does_not_idle():
    sm = _sm()
    sm._last_activity = NOW - 100
    cmds = sm.on_tick(NOW)
    assert sm.state == State.ACTIVE
    assert "FACE:tired" not in cmds


def test_low_keystroke_count_sends_default_face():
    sm = _sm()
    sm._keystroke_times = [NOW] * 5        # 5 keystrokes — below 20 threshold
    sm._last_face = "curious"               # force a face change
    cmds = sm.on_tick(NOW)
    assert "FACE:default" in cmds


def test_medium_keystroke_count_sends_curious_face():
    sm = _sm()
    sm._keystroke_times = [NOW] * 50       # 50 keystrokes — 21–80 range
    sm._last_face = "default"
    cmds = sm.on_tick(NOW)
    assert "FACE:curious" in cmds


def test_high_keystroke_count_sends_excited_face():
    sm = _sm()
    sm._keystroke_times = [NOW] * 100      # 100 keystrokes — above 80
    sm._last_face = "default"
    cmds = sm.on_tick(NOW)
    assert "FACE:excited" in cmds


def test_face_not_resent_if_unchanged():
    sm = _sm()
    sm._keystroke_times = []
    sm._last_face = "default"              # already at default
    cmds = sm.on_tick(NOW)
    assert "FACE:default" not in cmds


def test_git_push_sends_excited_and_records_restore_face():
    sm = _sm()
    sm._last_face = "curious"
    cmds = sm.on_git_push(NOW)
    assert "FACE:excited" in cmds
    assert sm._pre_git_face == "curious"


def test_git_excited_restores_face_after_timeout():
    sm = _sm()
    sm._last_face = "curious"
    sm.on_git_push(NOW)
    # advance time past the 8s git hold
    cmds = sm.on_tick(NOW + 9)
    assert "FACE:curious" in cmds
    assert sm._git_excited_until == 0


def test_git_excited_does_not_restore_before_timeout():
    sm = _sm()
    sm.on_git_push(NOW)
    cmds = sm.on_tick(NOW + 3)
    assert not any(c.startswith("FACE:") for c in cmds)


def test_combined_msg_sent_when_both_weather_and_temp_available():
    sm = _sm()
    sm.on_weather("28°C ⛅")
    cmds = sm.on_temp(24.0)
    assert any(c.startswith("MSG:") for c in cmds)
    combined = next(c for c in cmds if c.startswith("MSG:"))
    assert "28°C" in combined
    assert "24" in combined


def test_combined_msg_not_sent_with_only_weather():
    sm = _sm()
    cmds = sm.on_weather("28°C ⛅")
    assert not any(c.startswith("MSG:") for c in cmds)


def test_combined_msg_not_sent_with_only_temp():
    sm = _sm()
    cmds = sm.on_temp(24.0)
    assert not any(c.startswith("MSG:") for c in cmds)


def test_weather_and_temp_cache_cleared_after_msg():
    sm = _sm()
    sm.on_weather("28°C ⛅")
    sm.on_temp(24.0)
    # second pair — should trigger a new MSG
    sm.on_weather("30°C ☀")
    cmds = sm.on_temp(25.0)
    assert any(c.startswith("MSG:") for c in cmds)
```

- [ ] **Step 2: Run tests — expect ImportError (file doesn't exist yet)**

```bash
cd /home/sayed/Projects/pico_eyes
pytest tests/host/test_state_machine.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'state_machine'`

- [ ] **Step 3: Create host/state_machine.py**

```python
# host/state_machine.py
from enum import Enum
import time as _time

GIT_EXCITED_S = 8
IDLE_AFTER_S  = 5 * 60

# (threshold, face_name) — first threshold the count exceeds wins
_INTENSITY = [
    (80, "excited"),
    (20, "curious"),
    (0,  "default"),
]


class State(Enum):
    ACTIVE = "active"
    IDLE   = "idle"


class StateMachine:

    def __init__(self):
        self.state              = State.ACTIVE
        self._last_activity     = _time.time()
        self._keystroke_times   = []    # timestamps in the last 60 s
        self._git_excited_until = 0.0
        self._pre_git_face      = "default"
        self._last_face         = "default"
        self._last_weather      = None
        self._last_temp         = None

    # ── Event handlers — each returns a list of serial command strings ──

    def on_activity(self, ts: float) -> list:
        cmds = []
        if self.state == State.IDLE:
            self.state = State.ACTIVE
            cmds.append("RESET_BREAK")
        self._last_activity = ts
        self._keystroke_times.append(ts)
        cutoff = ts - 60
        self._keystroke_times = [t for t in self._keystroke_times if t >= cutoff]
        return cmds

    def on_git_push(self, now: float) -> list:
        self._pre_git_face      = self._last_face
        self._git_excited_until = now + GIT_EXCITED_S
        self._last_face         = "excited"
        return ["FACE:excited"]

    def on_weather(self, text: str) -> list:
        self._last_weather = text
        return self._maybe_combined()

    def on_temp(self, celsius: float) -> list:
        self._last_temp = celsius
        return self._maybe_combined()

    def on_tick(self, now: float) -> list:
        cmds = []

        # git-excited timeout
        if self._git_excited_until:
            if now >= self._git_excited_until:
                self._git_excited_until = 0.0
                face = self._pre_git_face
                self._last_face = face
                cmds.append("FACE:{}".format(face))
            return cmds     # suppress other face changes while git-excited

        # idle transition
        if self.state == State.ACTIVE and (now - self._last_activity) >= IDLE_AFTER_S:
            self.state = State.IDLE
            self._last_face = "tired"
            cmds.append("FACE:tired")
            return cmds

        # intensity face (only while ACTIVE)
        if self.state == State.ACTIVE:
            count = len(self._keystroke_times)
            face = "default"
            for threshold, name in _INTENSITY:
                if count > threshold:
                    face = name
                    break
            if face != self._last_face:
                self._last_face = face
                cmds.append("FACE:{}".format(face))

        return cmds

    # ── Private ──

    def _maybe_combined(self) -> list:
        if self._last_weather is not None and self._last_temp is not None:
            msg = "MSG:{} | pico:{:.0f}C".format(self._last_weather, self._last_temp)
            self._last_weather = None
            self._last_temp    = None
            return [msg]
        return []
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/host/test_state_machine.py -v
```

Expected output: `17 passed`

- [ ] **Step 5: Commit**

```bash
git add host/state_machine.py tests/host/test_state_machine.py
git commit -m "feat(host): add StateMachine with full test coverage"
```

---

## Task 5: producers/keyboard.py

**Files:**
- Create: `host/producers/keyboard.py`

- [ ] **Step 1: Install pynput if needed**

```bash
pip install pynput
python -c "import pynput; print('ok')"
```

- [ ] **Step 2: Create host/producers/keyboard.py**

```python
# host/producers/keyboard.py
import time
import queue as _queue
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pynput import keyboard, mouse
from events import KeystrokeEvent, MouseMoveEvent


def start(q: _queue.Queue) -> None:
    """Start keyboard and mouse listeners as daemon threads."""

    def on_press(key):
        q.put(KeystrokeEvent(timestamp=time.time()))

    def on_move(x, y):
        q.put(MouseMoveEvent(timestamp=time.time()))

    kb = keyboard.Listener(on_press=on_press)
    ms = mouse.Listener(on_move=on_move)
    kb.daemon = True
    ms.daemon = True
    kb.start()
    ms.start()
```

- [ ] **Step 3: Commit**

```bash
git add host/producers/keyboard.py
git commit -m "feat(host): add keyboard/mouse activity producer"
```

---

## Task 6: producers/weather.py + tests

**Files:**
- Create: `host/producers/weather.py`
- Create: `tests/host/test_weather.py`

- [ ] **Step 1: Write failing tests**

Create `tests/host/test_weather.py`:

```python
# tests/host/test_weather.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host', 'producers'))

from unittest.mock import patch, MagicMock
from weather import _fetch, _parse


def test_parse_strips_city_name():
    assert _parse("Cairo: ⛅ +28°C") == "⛅ +28°C"


def test_parse_no_colon_returns_as_is():
    assert _parse("⛅ +28°C") == "⛅ +28°C"


def test_parse_truncates_to_20_chars():
    long = "A" * 30
    assert len(_parse(long)) <= 20


def test_fetch_returns_parsed_text():
    mock_resp = MagicMock()
    mock_resp.text = "Cairo: ⛅ +28°C\n"
    mock_resp.raise_for_status = lambda: None
    with patch('weather.requests.get', return_value=mock_resp):
        result = _fetch()
    assert result == "⛅ +28°C"


def test_fetch_returns_none_on_network_error():
    with patch('weather.requests.get', side_effect=Exception("timeout")):
        result = _fetch()
    assert result is None
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
pytest tests/host/test_weather.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'weather'`

- [ ] **Step 3: Create host/producers/weather.py**

```python
# host/producers/weather.py
import time
import queue as _queue
import threading
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests
from events import WeatherUpdateEvent

INTERVAL_S = 30 * 60
_URL       = "https://wttr.in/?format=3"


def _parse(text: str) -> str:
    text = text.strip()
    if ": " in text:
        text = text.split(": ", 1)[1]
    return text[:20]


def _fetch() -> str | None:
    try:
        r = requests.get(_URL, timeout=10)
        r.raise_for_status()
        return _parse(r.text)
    except Exception:
        return None


def start(q: _queue.Queue) -> None:
    def loop():
        while True:
            text = _fetch()
            if text:
                q.put(WeatherUpdateEvent(text=text))
            time.sleep(INTERVAL_S)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/host/test_weather.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Install requests if needed**

```bash
pip install requests
python -c "import requests; print('ok')"
```

- [ ] **Step 6: Commit**

```bash
git add host/producers/weather.py tests/host/test_weather.py
git commit -m "feat(host): add weather producer with wttr.in parsing"
```

---

## Task 7: producers/ipc_server.py

**Files:**
- Create: `host/producers/ipc_server.py`

- [ ] **Step 1: Create host/producers/ipc_server.py**

```python
# host/producers/ipc_server.py
import os
import socket
import threading
import queue as _queue
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from events import GitPushEvent, UploadRequestEvent

SOCK_PATH = "/tmp/pico_eyes.sock"


def start(q: _queue.Queue) -> None:
    def loop():
        if os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCK_PATH)
        srv.listen(1)
        while True:
            conn, _ = srv.accept()
            try:
                data = conn.recv(256).decode().strip()
                if data.startswith("PUSH:"):
                    branch = data[5:]
                    q.put(GitPushEvent(branch=branch))
                    conn.close()
                elif data == "UPLOAD":
                    # keep conn open — main thread writes "OK\n" after releasing serial
                    q.put(UploadRequestEvent(conn=conn))
                else:
                    conn.close()
            except Exception:
                conn.close()

    t = threading.Thread(target=loop, daemon=True)
    t.start()
```

- [ ] **Step 2: Commit**

```bash
git add host/producers/ipc_server.py
git commit -m "feat(host): add IPC socket server for git push and upload events"
```

---

## Task 8: producers/temp.py

**Files:**
- Create: `host/producers/temp.py`

- [ ] **Step 1: Create host/producers/temp.py**

```python
# host/producers/temp.py
import time
import queue as _queue
import threading
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from events import TempRequestEvent

INTERVAL_S    = 30 * 60
INITIAL_DELAY = 60   # wait 1 min before first request so weather arrives first


def start(q: _queue.Queue) -> None:
    def loop():
        time.sleep(INITIAL_DELAY)
        while True:
            q.put(TempRequestEvent())
            time.sleep(INTERVAL_S)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
```

- [ ] **Step 2: Commit**

```bash
git add host/producers/temp.py
git commit -m "feat(host): add temperature request producer"
```

---

## Task 9: daemon.py — wire everything together

**Files:**
- Create: `host/daemon.py`

- [ ] **Step 1: Create host/daemon.py**

```python
#!/usr/bin/env python3
# host/daemon.py — entry point
import os
import sys
import queue
import time
import threading

# ensure host/ is on path so sibling imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from events import (
    KeystrokeEvent, MouseMoveEvent, GitPushEvent, UploadRequestEvent,
    WeatherUpdateEvent, TempRequestEvent, TickEvent,
)
from serial_link import SerialLink
from state_machine import StateMachine
import producers.keyboard   as kb_prod
import producers.weather    as wx_prod
import producers.ipc_server as ipc_prod
import producers.temp       as tmp_prod

HB_EVERY_TICKS = 10    # send HB once per 10 TickEvents (= every 10 s)


def _tick_thread(q: queue.Queue) -> None:
    while True:
        time.sleep(1)
        q.put(TickEvent())


def run() -> None:
    q    = queue.Queue()
    link = SerialLink()
    sm   = StateMachine()

    kb_prod.start(q)
    wx_prod.start(q)
    ipc_prod.start(q)
    tmp_prod.start(q)
    threading.Thread(target=_tick_thread, args=(q,), daemon=True).start()

    print("pico_eyes host: waiting for Pico...")
    while not link.connect():
        time.sleep(5)
    print("pico_eyes host: connected")

    tick_count = 0

    while True:
        try:
            event = q.get(timeout=2)
        except queue.Empty:
            link.ensure_connected()
            continue

        if isinstance(event, (KeystrokeEvent, MouseMoveEvent)):
            for cmd in sm.on_activity(event.timestamp):
                link.send(cmd)

        elif isinstance(event, GitPushEvent):
            for cmd in sm.on_git_push(time.time()):
                link.send(cmd)

        elif isinstance(event, UploadRequestEvent):
            link.disconnect()
            try:
                event.conn.sendall(b"OK\n")
            except Exception:
                pass
            event.conn.close()
            print("pico_eyes host: port released for upload, reconnecting...")
            time.sleep(3)
            while not link.connect():
                time.sleep(3)
            print("pico_eyes host: reconnected after upload")
            # show excited face for 5 s then restore
            link.send("FACE:excited")
            sm._git_excited_until = time.time() + 5
            sm._pre_git_face      = sm._last_face
            sm._last_face         = "excited"

        elif isinstance(event, WeatherUpdateEvent):
            for cmd in sm.on_weather(event.text):
                link.send(cmd)

        elif isinstance(event, TempRequestEvent):
            ack = link.send("TEMP")
            # ACK format: ACK:TEMP:23.4:OK
            parts = ack.split(":")
            if len(parts) >= 3:
                try:
                    for cmd in sm.on_temp(float(parts[2])):
                        link.send(cmd)
                except ValueError:
                    pass

        elif isinstance(event, TickEvent):
            tick_count += 1
            if tick_count % HB_EVERY_TICKS == 0:
                if not link.send("HB"):
                    link.ensure_connected()
            for cmd in sm.on_tick(time.time()):
                link.send(cmd)


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Smoke-test by running manually (Pico must be connected)**

```bash
cd /home/sayed/Projects/pico_eyes
python3 host/daemon.py
```

Expected output:
```
pico_eyes host: waiting for Pico...
pico_eyes host: connected
```

Press some keys — after 10 s you should see the Pico face change. `Ctrl+C` to stop.

- [ ] **Step 3: Commit**

```bash
git add host/daemon.py
git commit -m "feat(host): add main event loop daemon"
```

---

## Task 10: pico_upload.py + tests

**Files:**
- Create: `host/pico_upload.py`
- Create: `tests/host/test_pico_upload.py`

- [ ] **Step 1: Write failing tests**

Create `tests/host/test_pico_upload.py`:

```python
# tests/host/test_pico_upload.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'host'))

from unittest.mock import patch, MagicMock, call
from pico_upload import upload, _build_mpremote_args


def test_build_mpremote_args_single_file():
    args = _build_mpremote_args(["main.py"])
    assert args == ["mpremote", "cp", "main.py", ":"]


def test_build_mpremote_args_multiple_files():
    args = _build_mpremote_args(["main.py", "companion.py"])
    assert args == ["mpremote", "cp", "main.py", ":", "+", "cp", "companion.py", ":"]


def test_upload_notifies_daemon_before_mpremote():
    call_order = []

    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"OK\n"

    def fake_connect(path):
        call_order.append("connect")

    def fake_run(args):
        call_order.append("mpremote")
        return MagicMock(returncode=0)

    mock_sock.connect.side_effect = fake_connect

    with patch('pico_upload.socket.socket', return_value=mock_sock), \
         patch('pico_upload.subprocess.run', side_effect=fake_run):
        upload(["main.py"])

    assert call_order == ["connect", "mpremote"]


def test_upload_proceeds_without_daemon():
    mock_sock = MagicMock()
    mock_sock.connect.side_effect = Exception("no daemon")

    with patch('pico_upload.socket.socket', return_value=mock_sock), \
         patch('pico_upload.subprocess.run', return_value=MagicMock(returncode=0)) as mock_run:
        result = upload(["main.py"])

    assert result == 0
    mock_run.assert_called_once()


def test_upload_returns_mpremote_exit_code():
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"OK\n"

    with patch('pico_upload.socket.socket', return_value=mock_sock), \
         patch('pico_upload.subprocess.run', return_value=MagicMock(returncode=1)):
        result = upload(["main.py"])

    assert result == 1
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
pytest tests/host/test_pico_upload.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'pico_upload'`

- [ ] **Step 3: Create host/pico_upload.py**

```python
#!/usr/bin/env python3
# host/pico_upload.py
# Usage: python3 host/pico_upload.py file1.py [file2.py ...]
import socket
import subprocess
import sys

SOCK_PATH = "/tmp/pico_eyes.sock"


def _build_mpremote_args(files: list) -> list:
    args = ["mpremote"]
    for i, f in enumerate(files):
        if i > 0:
            args.append("+")
        args.extend(["cp", f, ":"])
    return args


def upload(files: list) -> int:
    # notify daemon to release serial port
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCK_PATH)
        s.sendall(b"UPLOAD")
        resp = s.recv(16)
        s.close()
        if resp.strip() != b"OK":
            print("pico-upload: unexpected daemon response, proceeding anyway")
    except Exception:
        print("pico-upload: daemon not running, uploading directly")

    result = subprocess.run(_build_mpremote_args(files))
    return result.returncode


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: pico-upload file1.py [file2.py ...]")
        sys.exit(1)
    sys.exit(upload(sys.argv[1:]))
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/host/test_pico_upload.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add host/pico_upload.py tests/host/test_pico_upload.py
git commit -m "feat(host): add pico-upload CLI with daemon handshake"
```

---

## Task 11: systemd service + global git hook

**Files:**
- Create: `host/pico_eyes.service`

- [ ] **Step 1: Create host/pico_eyes.service**

```ini
[Unit]
Description=Pico Eyes companion daemon
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 /home/sayed/Projects/pico_eyes/host/daemon.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Install the systemd unit**

```bash
mkdir -p ~/.config/systemd/user
cp host/pico_eyes.service ~/.config/systemd/user/pico_eyes.service
systemctl --user daemon-reload
systemctl --user enable --now pico_eyes
systemctl --user status pico_eyes
```

Expected: `Active: active (running)`

- [ ] **Step 3: Set up global git hook**

```bash
mkdir -p ~/.git-hooks
cat > ~/.git-hooks/post-push << 'EOF'
#!/bin/sh
branch=$(git rev-parse --abbrev-ref HEAD)
echo "PUSH:$branch" | nc -U /tmp/pico_eyes.sock 2>/dev/null || true
EOF
chmod +x ~/.git-hooks/post-push
git config --global core.hooksPath ~/.git-hooks
```

- [ ] **Step 4: Verify git hook works**

```bash
# from any repo (including this one):
git push origin HEAD
```

Expected: Eyes show `FACE:excited` for 8 seconds then return to previous face.

- [ ] **Step 5: Verify logs**

```bash
journalctl --user -u pico_eyes -f
```

- [ ] **Step 6: Commit**

```bash
git add host/pico_eyes.service
git commit -m "feat(host): add systemd service unit and global git hook instructions"
```

---

## Task 12: Run full test suite

- [ ] **Step 1: Install test dependencies**

```bash
pip install pytest pyserial pynput requests
```

- [ ] **Step 2: Run all tests**

```bash
cd /home/sayed/Projects/pico_eyes
pytest tests/host/ -v
```

Expected output:
```
tests/host/test_state_machine.py::test_initial_state_is_active PASSED
tests/host/test_state_machine.py::test_activity_while_idle_transitions_to_active_and_resets_break PASSED
... (17 state machine tests)
tests/host/test_weather.py::test_parse_strips_city_name PASSED
... (5 weather tests)
tests/host/test_pico_upload.py::test_build_mpremote_args_single_file PASSED
... (5 upload tests)

27 passed
```

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat(host): complete host companion daemon — all tests passing"
```
