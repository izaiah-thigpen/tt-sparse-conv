"""A register-level software INA228 on a fake I2C bus, for testing the host
board's power-sweep code without hardware. Runs on CPython and MicroPython.

The current it reports comes from a callable (amps), so a test can tie it to
the chip emulator's state. Energy accumulates in real time between resets.
"""
import time

import ina228 as I


def _now():
    try:
        return time.ticks_ms() / 1000
    except AttributeError:
        return time.monotonic()


class FakeINA228:
    def __init__(self, current_fn, shunt_ohms, vsupply=1.8, addr=I.ADDR):
        self.current_fn, self.r, self.vsupply, self.addr = current_fn, shunt_ohms, vsupply, addr
        self.regs = {I.MANUFACTURER_ID: 0x5449, I.DEVICE_ID: 0x2281, I.CONFIG: 0, I.ADC_CONFIG: 0xFB68,
                     I.SHUNT_CAL: 0x1000, I.DIAG_ALRT: 0x0002}
        self.energy_j = 0.0
        self.t_last = _now()

    def _adc_range(self):
        return (self.regs[I.CONFIG] >> 4) & 1

    def _accumulate(self):
        t = _now()
        i = self.current_fn()
        v = self.vsupply - i * self.r
        self.energy_j += v * i * (t - self.t_last)
        self.t_last = t

    def scan(self):
        return [self.addr]

    def writeto_mem(self, addr, reg, data):
        assert addr == self.addr
        v = (data[0] << 8) | data[1]
        self._accumulate()
        if reg == I.CONFIG:
            if v & 0x8000:                       # reset
                self.regs[I.CONFIG] = 0
                self.energy_j = 0.0
                return
            if v & 0x4000:                       # RSTACC
                self.energy_j = 0.0
            v &= ~0x4000
        self.regs[reg] = v

    def readfrom_mem(self, addr, reg, n):
        assert addr == self.addr
        self._accumulate()
        i = self.current_fn()
        if reg == I.VSHUNT:
            raw = int(round(i * self.r / I.VSHUNT_LSB[self._adc_range()])) & 0xFFFFF
            val = raw << 4
        elif reg == I.VBUS:
            val = int(round((self.vsupply - i * self.r) / I.VBUS_LSB)) << 4
        elif reg == I.DIETEMP:
            val = int(25 / I.TEMP_LSB)
        elif reg == I.ENERGY:
            cal = self.regs[I.SHUNT_CAL]
            lsb = cal / (13107.2e6 * self.r * (4 if self._adc_range() else 1))
            val = int(self.energy_j / (16 * 3.2 * lsb))
        else:
            val = self.regs.get(reg, 0)
        return bytes((val >> (8 * k)) & 0xFF for k in range(n - 1, -1, -1))
