# host/state_machine.py
from enum import Enum
import time as _time

GIT_EXCITED_S = 8
IDLE_AFTER_S  = 5 * 60

# (threshold, face_name) — first threshold the count exceeds wins
_INTENSITY = [
    (80, "excited"),
    (20, "focused"),
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
            print("pico_eyes: IDLE → ACTIVE  (resetting break timer)")
            cmds.append("RESET_BREAK")
        self._last_activity = ts
        self._keystroke_times.append(ts)
        cutoff = ts - 60
        self._keystroke_times = [t for t in self._keystroke_times if t >= cutoff]
        return cmds

    def on_git_push(self, now: float) -> list:
        print("pico_eyes: git push → FACE:excited for {}s".format(GIT_EXCITED_S))
        self._pre_git_face      = self._last_face
        self._git_excited_until = now + GIT_EXCITED_S
        self._last_face         = "excited"
        return ["FACE:excited"]

    def on_upload_completed(self, now: float) -> list:
        print("pico_eyes: upload done → FACE:excited for 5s")
        self._pre_git_face      = self._last_face
        self._git_excited_until = now + 5
        self._last_face         = "excited"
        return ["FACE:excited"]

    def on_weather(self, text: str) -> list:
        print("pico_eyes: weather update →", text)
        self._last_weather = text
        return self._maybe_combined()

    def on_temp(self, celsius: float) -> list:
        print("pico_eyes: pico temp → {:.1f}°C".format(celsius))
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
                print("pico_eyes: git-excited ended → restoring FACE:{}".format(face))
                cmds.append("FACE:{}".format(face))
            return cmds

        # idle transition
        if self.state == State.ACTIVE and (now - self._last_activity) >= IDLE_AFTER_S:
            self.state = State.IDLE
            self._last_face = "tired"
            print("pico_eyes: ACTIVE → IDLE  (no activity for 5 min) → FACE:tired")
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
                print("pico_eyes: FACE:{} ({} keys/min)".format(face, count))
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
