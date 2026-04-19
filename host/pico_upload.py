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
        s.sendall(b"UPLOAD\n")
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
