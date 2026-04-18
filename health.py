# health.py — autonomous 30-minute break timer
#
# Runs entirely on the Pico using ticks_ms().
# No PC involvement needed — the Pico tracks elapsed desk time itself.
#
# Usage:
#   timer = HealthTimer()
#   ...
#   if timer.due:          # fires once per interval, then waits for reset()
#       show_break_reminder()
#   ...
#   timer.reset()          # call when user acknowledges the reminder

import time

# ── Config ────────────────────────────────────────────────────
BREAK_INTERVAL_MS = 30 * 60 * 1000   # 30 minutes


class HealthTimer:

    def __init__(self):
        self.reset()

    def reset(self):
        """Restart the countdown. Call on acknowledgement or mode switch."""
        self._t0     = time.ticks_ms()
        self._fired  = False

    @property
    def due(self):
        """
        True exactly once when the interval has elapsed.
        Stays False until reset() is called.
        """
        if self._fired:
            return False
        elapsed = time.ticks_diff(time.ticks_ms(), self._t0)
        if elapsed >= BREAK_INTERVAL_MS:
            self._fired = True
            return True
        return False

    @property
    def minutes_elapsed(self):
        """How many full minutes since last reset (useful for debug prints)."""
        return time.ticks_diff(time.ticks_ms(), self._t0) // 60_000

    @property
    def waiting_for_reset(self):
        """True if the timer has fired and is waiting to be reset."""
        return self._fired
