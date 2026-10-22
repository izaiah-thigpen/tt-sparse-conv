"""Bit-banged SPI to the chip through the Tiny Tapeout demo board's RP2040.

The RP2040 drives the chip's inputs (ui_in) and reads its outputs (uo_out)
through two functions passed in, so the same code runs on the board and in
simulation:

    on the board:  Spi(platform.write_ui_in_byte, platform.read_uo_out_byte)
    in the tests:  Spi(write_fn, read_fn) bridged to the RTL simulator

Pins (src/project.v):
    ui_in[0] SCLK   ui_in[1] CS_N   ui_in[2] MOSI   ui_in[3] BYPASS
    uo_out[0] MISO  uo_out[1] DONE  uo_out[2] SKIP  uo_out[3] BUSY

SPI mode 0, MSB first. Each bit is: set MOSI, read MISO, raise SCLK (the
chip samples MOSI), lower SCLK (the chip shifts MISO). The chip samples these
pins with its own clock, so every pin access must last several chip clocks.
In simulation, data stays correct down to 2 clocks per access and every check
passes at 3. MicroPython takes microseconds per access, so the default 10 MHz
project clock gives a wide margin; do not run the project clock below about
5 MHz with this driver.
"""

SCLK = 0x01
CS_N = 0x02
MOSI = 0x04
BYPASS = 0x08

MISO = 0x01
DONE = 0x02
SKIP = 0x04
BUSY = 0x08


class Spi:
    def __init__(self, write_ui, read_uo):
        self._w = write_ui
        self._r = read_uo
        self._bypass = 0
        self._in_frame = False
        self.bytes_sent = 0
        self._w(CS_N)

    def set_bypass(self, on):
        """BYPASS pin high turns gating off regardless of the config bit."""
        self._bypass = BYPASS if on else 0
        self._w((0 if self._in_frame else CS_N) | self._bypass)

    def pins(self):
        """The chip's output byte (MISO, DONE, SKIP, BUSY, TAP)."""
        return self._r()

    def frame(self, data, keep_open=False):
        """Send bytes with chip select low and return the bytes received.
        keep_open leaves chip select low so a later call continues the frame."""
        w, r = self._w, self._r
        base = self._bypass
        if not self._in_frame:
            w(base)                      # chip select low
        out = bytearray(len(data))
        for i in range(len(data)):
            byte = data[i]
            got = 0
            for b in range(7, -1, -1):
                v = base | (MOSI if (byte >> b) & 1 else 0)
                w(v)                     # MOSI set, SCLK low
                got = (got << 1) | (r() & MISO)
                w(v | SCLK)              # rising edge: chip samples MOSI
                w(v)                     # falling edge: chip shifts MISO
            out[i] = got
        self.bytes_sent += len(data)
        if keep_open:
            self._in_frame = True
        else:
            w(base | CS_N)               # chip select high
            self._in_frame = False
        return out
