"""Switching activity for the power estimate, on the gate-level netlist.

One condition per simulation (POWER_COND), because a simulator writes one VCD:
  idle             clock running, weights loaded, no computation
  T<thr>_gated     activity run, zero threshold <thr>, gating on
  T<thr>_bypass    the same run with the BYPASS pin high (gating off)

The run is started with RUN 0 (until STOP), the SPI pins go quiet, and the dump
covers WINDOW clock cycles of pure computation. The same weights as the board's
power sweep (host/board/bringup.py) so simulation and silicon are comparable.
"""
import os

import cocotb
from cocotb.triggers import ClockCycles

from test import setup, BYPASS, BUSY  # tt-repo/test/test.py

SWEEP_WEIGHTS = [37, -88, 101, -15, 64, 127, -127, 9, -50]
WINDOW = int(os.environ.get("POWER_WINDOW", "2000"))


@cocotb.test()
async def power_window(dut):
    cond = os.environ["POWER_COND"]
    pins, host = await setup(dut)
    await host.write_weights(SWEEP_WEIGHTS)
    await host.write_config(0, 1)
    await host.load_acc(0)
    await host.clear_skips()
    if cond != "idle":
        thr, mode = cond[1:].split("_")
        pins.set(BYPASS, 1 if mode == "bypass" else 0)
        await host.set_activity(int(thr))
        await host.run(0)
        assert pins.get(BUSY) == 1, "activity run did not start"
    await ClockCycles(dut.clk, 50)        # let the SPI synchronizers settle
    dut.dump_on.value = 1
    await ClockCycles(dut.clk, WINDOW)
    if cond != "idle":
        assert pins.get(BUSY) == 1, "run stopped inside the window"
    dut._log.info(f"{cond}: dumped {WINDOW} cycles")
