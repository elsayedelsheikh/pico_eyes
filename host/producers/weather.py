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
            else:
                time.sleep(300)   # retry after 5 min on failure

    t = threading.Thread(target=loop, daemon=True)
    t.start()
