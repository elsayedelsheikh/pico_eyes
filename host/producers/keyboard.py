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
