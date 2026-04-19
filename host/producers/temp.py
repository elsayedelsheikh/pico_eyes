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
