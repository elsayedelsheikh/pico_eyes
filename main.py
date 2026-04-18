from machine import Pin, SPI
import st7789
from tft_adapter import TFTAdapter
from roboeyes import RoboEyes, ON, OFF
from roboeyes import DEFAULT, TIRED, ANGRY, HAPPY, FROZEN, SCARY, CURIOUS
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

def robo_show(roboeyes):
    lcd.show()

# ── RoboEyes ─────────────────────────────────────────────────
robo = RoboEyes(lcd, 240, 240, frame_rate=20, on_show=robo_show)

# Bigger eyes
robo.eyes_width(80, 80)
robo.eyes_height(70, 70)
robo.eyes_radius(14, 14)

robo.set_idle_mode(OFF)
robo.set_auto_blinker(ON, 3, 2)

# ── Step 1: let the SIZE tween finish (~500ms) ────────────────
# eyes_width() sets eyeLwidthNext but not eyeLwidthCurrent.
# set_position(DEFAULT) uses eyeLwidthCurrent for the centering math,
# so we must call it AFTER update() has tweened the width to 80px.
start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < 600:
    robo.update()

# ── Step 2: now recentre with the correct width in effect ─────
robo.set_position(DEFAULT)

# ── Step 3: let the POSITION tween reach centre ───────────────
start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < 600:
    robo.update()

# ── Mood cycle ────────────────────────────────────────────────
MOODS      = [DEFAULT, HAPPY, TIRED, ANGRY, CURIOUS, SCARY, FROZEN]
MOOD_NAMES = ["DEFAULT", "HAPPY",  "TIRED", "ANGRY", "CURIOUS", "SCARY", "FROZEN"]
HOLD_MS    = 3000   # ms per mood — edit to taste

current    = 0
robo.set_mood(MOODS[current])
print("Expression test — mood:", MOOD_NAMES[current])
print("Cycling every", HOLD_MS // 1000, "s")

mood_start = time.ticks_ms()
while True:
    robo.update()

    if time.ticks_diff(time.ticks_ms(), mood_start) >= HOLD_MS:
        current    = (current + 1) % len(MOODS)
        robo.set_mood(MOODS[current])
        print("Mood:", MOOD_NAMES[current])
        mood_start = time.ticks_ms()
