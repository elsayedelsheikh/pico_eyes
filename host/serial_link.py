# host/serial_link.py
import glob
import time
import serial

BAUD            = 115200
TIMEOUT         = 2.0
SETTLE_DELAY_S  = 0.5   # give Pico time to settle after USB reset


class SerialLink:
    """USB serial port manager for Pico communication.

    Not thread-safe — must only be called from the main thread.
    """

    def __init__(self):
        self._ser = None

    def connect(self) -> bool:
        """Scan /dev/ttyACM*, open the first one, send HELLO + TIME. Returns True on success."""
        ports = glob.glob('/dev/ttyACM*')
        if not ports:
            print("serial_link: no /dev/ttyACM* port found")
            return False
        try:
            self._ser = serial.Serial(ports[0], BAUD, timeout=TIMEOUT)
            time.sleep(SETTLE_DELAY_S)
            self.send("HELLO")
            # Second HELLO needed when Pico was in bedside mode: the first one
            # wakes it to _wait_for_hello, the second actually enters companion.
            time.sleep(0.4)
            self.send("HELLO")
            t = time.localtime()
            self.send("TIME:{:02d}:{:02d}:{:02d}".format(t.tm_hour, t.tm_min, t.tm_sec))
            return True
        except (serial.SerialException, OSError, UnicodeDecodeError) as e:
            print("serial_link: connect failed:", e)
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
        except (serial.SerialException, OSError, UnicodeDecodeError) as e:
            print("serial_link: send failed ({!r}):".format(cmd), e)
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
