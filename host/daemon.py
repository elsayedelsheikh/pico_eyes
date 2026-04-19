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

    try:
        kb_prod.start(q)
    except Exception as e:
        print("pico_eyes host: keyboard/mouse monitoring unavailable:", e)
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

        try:
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
                for cmd in sm.on_upload_completed(time.time()):
                    link.send(cmd)

            elif isinstance(event, WeatherUpdateEvent):
                for cmd in sm.on_weather(event.text):
                    link.send(cmd)

            elif isinstance(event, TempRequestEvent):
                ack = link.send("TEMP")
                # ACK format: ACK:TEMP:23.4:OK
                parts = ack.split(":")
                if len(parts) >= 3 and parts[-1].strip() == "OK":
                    try:
                        for cmd in sm.on_temp(float(parts[2])):
                            link.send(cmd)
                    except ValueError:
                        print("pico_eyes host: could not parse TEMP ack:", ack)
                else:
                    print("pico_eyes host: TEMP read failed:", ack)

            elif isinstance(event, TickEvent):
                tick_count += 1
                if tick_count % HB_EVERY_TICKS == 0:
                    if not link.send("HB"):
                        link.ensure_connected()
                for cmd in sm.on_tick(time.time()):
                    link.send(cmd)
        except Exception as e:
            print("pico_eyes host: event dispatch error:", e)


if __name__ == "__main__":
    run()
