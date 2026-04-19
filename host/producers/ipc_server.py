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
            try:
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
            except Exception as e:
                print("ipc_server: accept error:", e)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
