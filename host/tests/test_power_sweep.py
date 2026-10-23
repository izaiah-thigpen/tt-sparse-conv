"""The host board's power sweep, end to end, against the chip emulator and a
fake INA228 whose current follows the emulated chip.

    python test_power_sweep.py            (CPython)
    micropython test_power_sweep.py       (MICROPYPATH=..:../board:.)

Model: idle 0.40 mA; running 0.60 mA ungated; gating removes 45 uA times the
share of zero taps. The sweep must find each gated-vs-ungated difference.
"""
import bringup
import chip_protocol as cp
import ina228
from chip_emulator import ChipEmulator, BYPASS
from fake_ina228 import FakeINA228
from tt_spi import Spi

IDLE, RUN, SAVE_AT_FULL = 0.40e-3, 0.60e-3, 45e-6


def main():
    emu = ChipEmulator()
    spi = Spi(emu.write_ui, emu.read_uo)

    def current():
        if not emu.running:
            return IDLE
        gated = emu.gate and not (emu.ui & BYPASS)
        share = cp.zero_share(bringup.SWEEP_WEIGHTS, emu.act_thresh)
        return RUN - (SAVE_AT_FULL * share if gated else 0.0)

    fake = FakeINA228(current, ina228.R_NORMAL)
    ina = ina228.INA228(fake, ina228.R_NORMAL, conv_us=50, avg=1)
    rows = bringup.power_sweep(hold_s=0.2, spi=spi, ina=ina, log_path="power_sweep_test.csv")
    data = [r.split(",") for r in rows[1:]]
    ok = True
    by = {(d[1], d[3]): d for d in data}
    i_idle = float(by[("", "idle")][4]) * 1e-3
    if abs(i_idle - IDLE) > 1e-7:
        print("FAIL idle current %.7f A, want %.7f" % (i_idle, IDLE)); ok = False
    for t in bringup.SWEEP_THRESHOLDS:
        share = cp.zero_share(bringup.SWEEP_WEIGHTS, t)
        g = float(by[(str(t), "gated")][4]) * 1e-3
        u = float(by[(str(t), "ungated")][4]) * 1e-3
        want = SAVE_AT_FULL * share
        if abs((u - g) - want) > 0.1e-6:
            print("FAIL T=%d: measured saving %.3f uA, want %.3f" % (t, (u - g) * 1e6, want * 1e6)); ok = False
        pg, pu = float(by[(str(t), "gated")][7]), float(by[(str(t), "ungated")][7])
        vg = 1.8 - g * ina228.R_NORMAL
        if abs(pg - vg * g * 1e6) > 0.05 * vg * g * 1e6:
            print("FAIL T=%d: energy-based power %.2f uW, want about %.2f" % (t, pg, vg * g * 1e6)); ok = False
        if t > 0 and not pu > pg:
            print("FAIL T=%d: gated power not below ungated" % t); ok = False
    v = float(by[("", "idle")][6])
    if abs(v - (1.8 - IDLE * ina228.R_NORMAL)) > 0.001:
        print("FAIL core voltage %.4f" % v); ok = False
    print("=== power sweep test:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
