"""A pin-level software model of the chip, for running the board program
without hardware (including under MicroPython). Independent of the RTL;
the RTL is checked separately by test/test_host.py.

    emu = ChipEmulator()
    spi = Spi(emu.write_ui, emu.read_uo)

Follows src/conv_chip.sv: SPI mode 0, MSB first; the reply byte loads on the
falling SCLK edge that ends a byte; unknown opcodes are ignored; raising chip
select abandons a command (LOAD_ACC and WRITE_CONFIG only apply when complete).
"""
SCLK, CS_N, MOSI, BYPASS = 0x01, 0x02, 0x04, 0x08


class ChipEmulator:
    def __init__(self):
        self.ui = CS_N
        self.weights = [0] * 9
        self.acc = 0
        self.shift = 0
        self.gate = True
        self.skips = 0
        self.done = False
        self.busy = False
        self.pin_writes = 0
        self._reset_frame()
        self.tx = 0

    def _reset_frame(self):
        self.state = "idle"
        self.idx = 0
        self.bits = 0
        self.rx = 0
        self.buf = []
        self.resp = []
        self.next_tx = 0
        self.tx = 0
        if self.busy:
            self.busy = False

    # ---- pins ----
    def write_ui(self, v):
        self.pin_writes += 1
        old = self.ui
        self.ui = v
        if v & CS_N:
            if not old & CS_N:
                self._reset_frame()
            return
        if old & CS_N:          # chip select just went low
            self.bits = 0
        rise = (v & SCLK) and not (old & SCLK)
        fall = (old & SCLK) and not (v & SCLK)
        if rise:
            self.rx = ((self.rx << 1) | (1 if v & MOSI else 0)) & 0xFF
            self.bits += 1
            if self.bits == 8:
                self.bits = 0
                self._byte(self.rx)
        elif fall:
            if self.bits == 0:
                self.tx = self.next_tx
            else:
                self.tx = (self.tx << 1) & 0xFF

    def read_uo(self):
        miso = 1 if (not self.ui & CS_N) and (self.tx & 0x80) else 0
        tap = self.idx if self.state == "compute" else 0
        return miso | (0x02 if self.done else 0) | (0x08 if self.busy else 0) | (tap << 4)

    # ---- command decoder ----
    def _gating(self):
        return self.gate and not (self.ui & BYPASS)

    def _byte(self, b):
        self.next_tx = 0
        s = self.state
        if s == "idle":
            self.idx = 0
            if b == 0x01:
                self.state = "weights"
            elif b == 0x02:
                self.state, self.buf = "load", []
            elif b == 0x03:
                self.state = "config"
            elif b == 0x10:
                self.state, self.busy, self.done = "compute", True, False
            elif b == 0x23:
                self.skips = 0
            elif b in (0x20, 0x21, 0x22, 0x7F):
                if b == 0x20:
                    v = self.acc >> self.shift
                    resp = [0 if v < 0 else (255 if v > 255 else v)]
                elif b == 0x21:
                    a = self.acc & 0xFFFFFF
                    resp = [(a >> 16) & 0xFF, (a >> 8) & 0xFF, a & 0xFF]
                elif b == 0x22:
                    resp = [(self.skips >> 8) & 0xFF, self.skips & 0xFF]
                else:
                    resp = [0xA5]
                self.next_tx, self.resp, self.state = resp[0], resp[1:], "read"
        elif s == "weights":
            self.weights[self.idx] = b - 256 if b & 0x80 else b
            self.idx += 1
            if self.idx == 9:
                self.state = "idle"
        elif s == "load":
            self.buf.append(b)
            if len(self.buf) == 3:
                v = (self.buf[0] << 16) | (self.buf[1] << 8) | self.buf[2]
                self.acc = v - (1 << 24) if v & 0x800000 else v
                self.state = "idle"
        elif s == "config":
            self.shift, self.gate, self.state = b & 0x0F, bool(b & 0x10), "idle"
        elif s == "compute":
            w = self.weights[self.idx]
            if b == 0 or w == 0:
                self.skips = min(self.skips + 1, 0xFFFF)
            else:
                self.acc += b * w
            self.idx += 1
            if self.idx == 9:
                self.state, self.busy, self.done = "idle", False, True
        elif s == "read":
            if self.resp:
                self.next_tx = self.resp.pop(0)
            else:
                self.state = "idle"
