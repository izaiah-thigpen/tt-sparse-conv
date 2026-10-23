"""TI INA228 power monitor on the host board (pcb/), for the chip's core supply.

Runs on MicroPython (RP2350) and CPython. The bus is any object with
readfrom_mem(addr, reg, n) and writeto_mem(addr, reg, data), e.g.
machine.SoftI2C(scl=Pin(13), sda=Pin(12)) on the host board.

Shunt voltage is read directly and divided by the shunt resistance, so the
current does not depend on SHUNT_CAL; SHUNT_CAL is still set so the chip's own
power and energy accumulators are in watts and joules.

Register map and scaling: TI INA228 datasheet (SBOSA20), section 7.6.
"""
ADDR = 0x40                      # A0 = A1 = GND on the host board

CONFIG, ADC_CONFIG, SHUNT_CAL = 0x00, 0x01, 0x02
VSHUNT, VBUS, DIETEMP, CURRENT, POWER, ENERGY, CHARGE = 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A
DIAG_ALRT, MANUFACTURER_ID, DEVICE_ID = 0x0B, 0x3E, 0x3F

VSHUNT_LSB = {0: 312.5e-9, 1: 78.125e-9}   # volts per step for ADCRANGE 0 / 1
VBUS_LSB = 195.3125e-6
TEMP_LSB = 7.8125e-3
CT_CODE = {50: 0, 84: 1, 150: 2, 280: 3, 540: 4, 1052: 5, 2074: 6, 4120: 7}       # microseconds
AVG_CODE = {1: 0, 4: 1, 16: 2, 64: 3, 128: 4, 256: 5, 512: 6, 1024: 7}

R_NORMAL = 0.499 + 4.99          # RANGE jumper open
R_HIGH = 0.499                   # RANGE jumper fitted


def _signed(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


class INA228:
    def __init__(self, i2c, shunt_ohms=R_NORMAL, addr=ADDR, max_current=0.010,
                 conv_us=1052, avg=64, adc_range=1):
        self.i2c, self.addr, self.r = i2c, addr, shunt_ohms
        self.adc_range = adc_range
        man, dev = self._r(MANUFACTURER_ID, 2), self._r(DEVICE_ID, 2)
        if man != 0x5449 or (dev >> 4) != 0x228:
            raise OSError("no INA228 at 0x%02X (manufacturer 0x%04X, device 0x%04X)" % (addr, man, dev))
        self._w(CONFIG, 0x8000)                                  # reset
        self._w(CONFIG, (adc_range & 1) << 4)
        ct = CT_CODE[conv_us]
        # continuous bus + shunt + temperature, same conversion time for each
        self._w(ADC_CONFIG, (0xF << 12) | (ct << 9) | (ct << 6) | (ct << 3) | AVG_CODE[avg])
        self.current_lsb = max_current / (1 << 19)
        cal = int(13107.2e6 * self.current_lsb * shunt_ohms * (4 if adc_range else 1))
        if not 0 < cal < 0x8000:
            raise ValueError("SHUNT_CAL out of range: %d" % cal)
        self._w(SHUNT_CAL, cal)
        self.conversion_s = 3 * conv_us * 1e-6 * avg

    # --- registers
    def _r(self, reg, n):
        b = self.i2c.readfrom_mem(self.addr, reg, n)
        v = 0
        for x in b:
            v = (v << 8) | x
        return v

    def _w(self, reg, v):
        self.i2c.writeto_mem(self.addr, reg, bytes([(v >> 8) & 0xFF, v & 0xFF]))

    # --- measurements
    def shunt_voltage(self):
        return _signed(self._r(VSHUNT, 3) >> 4, 20) * VSHUNT_LSB[self.adc_range]

    def current(self):
        """Amperes, from the shunt voltage and the shunt resistance."""
        return self.shunt_voltage() / self.r

    def bus_voltage(self):
        """Volts at VBUS, which is the chip side of the shunt (the core supply VCCD)."""
        return (self._r(VBUS, 3) >> 4) * VBUS_LSB

    def die_temp(self):
        return _signed(self._r(DIETEMP, 2), 16) * TEMP_LSB

    def reset_accumulators(self):
        self._w(CONFIG, ((self.adc_range & 1) << 4) | (1 << 14))

    def energy(self):
        """Joules accumulated since reset_accumulators()."""
        return self._r(ENERGY, 5) * 16 * 3.2 * self.current_lsb

    def charge(self):
        """Coulombs accumulated since reset_accumulators()."""
        return _signed(self._r(CHARGE, 5), 40) * self.current_lsb

    def ready(self):
        return bool(self._r(DIAG_ALRT, 2) & 0x0002)     # CNVRF


def open_host_board(shunt_ohms=R_NORMAL):
    """The INA228 on the host board: SoftI2C on GPIO12 (SDA) and GPIO13 (SCL).
    Returns None on a plain demo board, where nothing answers."""
    try:
        from machine import Pin, SoftI2C
        i2c = SoftI2C(scl=Pin(13), sda=Pin(12), freq=400000)
        if ADDR not in i2c.scan():
            return None
        return INA228(i2c, shunt_ohms)
    except Exception:
        return None
