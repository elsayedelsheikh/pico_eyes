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
