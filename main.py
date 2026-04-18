from machine import Pin, SPI
import st7789
from tft_adapter import TFTAdapter
from roboeyes import RoboEyes, ON
import time

# ── Display ───────────────────────────────────────────────────
spi = SPI(0, baudrate=31250000, sck=Pin(2), mosi=Pin(3))

tft = st7789.ST7789(
    spi, 240, 240,
    reset=Pin(0, Pin.OUT),
    dc=Pin(4, Pin.OUT),
    cs=Pin(5, Pin.OUT),
    backlight=Pin(6, Pin.OUT),
    rotation=0,
)

# ── Framebuffer adapter (blue eyes on black) ──────────────────
lcd = TFTAdapter(tft, bgcolor=0x0000, fgcolor=0x001F)

# ── on_show: blits the finished frame to the display ─────────
def robo_show(roboeyes):
    lcd.show()

# ── RoboEyes ─────────────────────────────────────────────────
robo = RoboEyes(lcd, 240, 240, frame_rate=20, on_show=robo_show)

robo.set_auto_blinker(ON, 3, 2)
robo.set_idle_mode(ON, 2, 2)

# Let eyes open smoothly
start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < 1500:
    robo.update()

print("Running.")
while True:
    robo.update()
