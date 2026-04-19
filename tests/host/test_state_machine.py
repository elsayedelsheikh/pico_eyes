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
    sm._last_face = "focused"               # force a face change
    cmds = sm.on_tick(NOW)
    assert "FACE:default" in cmds


def test_medium_keystroke_count_sends_focused_face():
    sm = _sm()
    sm._keystroke_times = [NOW] * 50       # 50 keystrokes — 21–80 range
    sm._last_face = "default"
    cmds = sm.on_tick(NOW)
    assert "FACE:focused" in cmds


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
    sm._last_face = "focused"
    cmds = sm.on_git_push(NOW)
    assert "FACE:excited" in cmds
    assert sm._pre_git_face == "focused"


def test_git_excited_restores_face_after_timeout():
    sm = _sm()
    sm._last_face = "focused"
    sm.on_git_push(NOW)
    # advance time past the 8s git hold
    cmds = sm.on_tick(NOW + 9)
    assert "FACE:focused" in cmds
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
