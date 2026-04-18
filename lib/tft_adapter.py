# tft_adapter.py
# Double-buffered adapter for mchobby/micropython-roboeyes on ST7789.
#
# All drawing goes to a RAM FrameBuffer (no SPI during draw).
# show() blits the complete buffer to the display in one transfer —
# the display only ever sees finished frames, so no flicker.
#
# NOTE: RP2040 is little-endian; FrameBuffer RGB565 stores colors
# little-endian, but ST7789 expects big-endian. Colors are byte-swapped
# on entry so blit_buffer sends the correct bytes.

import framebuf

class TFTAdapter:
    """
    Parameters
    ----------
    tft     : initialised ST7789 object
    bgcolor : RGB565 background colour (default black  0x0000)
    fgcolor : RGB565 foreground colour (default blue   0x001F)
    """

    def __init__(self, tft, bgcolor=0x0000, fgcolor=0x001F):
        self.tft = tft
        # Allocate 240x240 RGB565 framebuffer in RAM
        self._buf = bytearray(240 * 240 * 2)
        self._fb  = framebuf.FrameBuffer(self._buf, 240, 240, framebuf.RGB565)
        # Byte-swap colours for little-endian FrameBuffer → big-endian ST7789
        self._bgcolor = self._swap(bgcolor)
        self._fgcolor = self._swap(fgcolor)
        self._palette = {0: self._bgcolor, 1: self._fgcolor}
        self._fb.fill(self._bgcolor)

    @staticmethod
    def _swap(color):
        """Swap high/low bytes: 0x001F → 0x1F00."""
        return ((color & 0xFF) << 8) | ((color >> 8) & 0xFF)

    def _c(self, color):
        return self._palette.get(color, self._swap(color))

    # ── FrameBuffer-compatible drawing (all go to RAM) ────────

    def fill(self, color):
        self._fb.fill(self._c(color))

    def fill_rect(self, x, y, w, h, color):
        self._fb.fill_rect(x, y, w, h, self._c(color))

    def hline(self, x, y, w, color):
        self._fb.hline(x, y, w, self._c(color))

    def vline(self, x, y, h, color):
        self._fb.vline(x, y, h, self._c(color))

    def pixel(self, x, y, color):
        self._fb.pixel(x, y, self._c(color))

    def rect(self, x, y, w, h, color):
        self._fb.rect(x, y, w, h, self._c(color))

    def show(self):
        """Blit the complete framebuffer to the TFT in one SPI transfer."""
        self.tft.blit_buffer(self._buf, 0, 0, 240, 240)
