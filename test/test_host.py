# SPDX-FileCopyrightText: © 2026 Izaiah Thigpen
# SPDX-License-Identifier: Apache-2.0
"""Runs the demo-board test program (host/board/bringup.py) against the chip.

The board code is used unchanged. Its two pin functions, write ui_in and
read uo_out, are bridged into the simulator, and each call takes OP_NS of
simulated time, standing in for MicroPython's speed. So this checks the SPI
bit-banging, the command sequences, the vector files and the pass/fail logic
together, on the RTL and (in GitHub Actions) on the post-layout netlist.

The project clock is 10 MHz, the default the board program sets.
"""
import os
import sys
import tempfile

import cocotb
from cocotb.clock import Clock
from cocotb.task import bridge, resume
from cocotb.triggers import ClockCycles, Timer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "host"), os.path.join(HERE, "..", "host", "board")]
import bringup  # noqa: E402
import make_vectors  # noqa: E402
import numpy as np  # noqa: E402
from tt_spi import Spi  # noqa: E402

GATE_LEVEL = os.environ.get("GATES") == "yes"
CLOCK_NS = 100                                       # 10 MHz
OP_NS = int(os.environ.get("HOST_OP_NS", "500"))     # time per pin access


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_NS, unit="ns").start())
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.ui_in.value = 0b10           # chip select idle high
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)


def pin_functions(dut):
    @resume
    async def write_ui(v):
        dut.ui_in.value = v
        await Timer(OP_NS, unit="ns")

    @resume
    async def read_uo():
        v = int(dut.uo_out.value)
        await Timer(OP_NS, unit="ns")
        return v

    return write_ui, read_uo


def make_random_vectors(n_maps):
    d = tempfile.mkdtemp(prefix="vectors_")
    rng = np.random.default_rng(7)
    q, names = make_vectors.random_model(rng)
    X, y = make_vectors.random_maps(rng, n_maps)
    with open(os.path.join(d, "model.bin"), "wb") as f:
        f.write(make_vectors.model_bytes(q, names))
    for i, (x, label) in enumerate(zip(X, y)):
        with open(os.path.join(d, "map_%02d.bin" % i), "wb") as f:
            f.write(make_vectors.map_bytes(x, label, q)[0])
    return d


@cocotb.test()
async def board_program_quick(dut):
    """The board program's smoke tests plus sampled network outputs, all passing."""
    await start(dut)
    vectors = make_random_vectors(1)
    bringup.QUICK_MAPS = 1
    bringup.QUICK_SAMPLES = 3 if GATE_LEVEL else 8
    write_ui, read_uo = pin_functions(dut)

    def program():
        spi = Spi(write_ui, read_uo)
        return bringup.run(spi, "quick", vector_dir=vectors, n_random=2 if GATE_LEVEL else 6)

    ok = await bridge(program)()
    assert ok, "the board program reported failures (see the log above)"


@cocotb.test()
async def board_program_detects_faults(dut):
    """With a deliberately wrong expected value, the board program must report FAIL."""
    await start(dut)
    vectors = make_random_vectors(1)
    path = os.path.join(vectors, "map_00.bin")
    data = bytearray(open(path, "rb").read())
    # Corrupt every expected layer-1 output for kernel 0 (just after the 10-byte header and 32x32 map)
    for i in range(10 + 1024, 10 + 1024 + 900):
        data[i] ^= 0x01
    open(path, "wb").write(bytes(data))
    bringup.QUICK_MAPS = 1
    bringup.QUICK_SAMPLES = 20
    write_ui, read_uo = pin_functions(dut)

    rng_state = bringup.Rng

    def program():
        spi = Spi(write_ui, read_uo)
        rep = bringup.Report()
        model, names = bringup.load_vectors(vectors)
        vec = bringup.cp.WaferVector(open(path, "rb").read(), model.n1, model.n2)
        # Sample only kernel 0 of layer 1, where every expected value is wrong
        _, bad = bringup.run_layer(
            spi, rep, "layer 1", 1, vec.h1, vec.w1,
            lambda k, r, c: [(bringup.cp.window(vec.x, vec.h, vec.w, r, c), None)],
            model.kernel1, model.b1, model.sh1, vec.conv1, vec.skips1, 5, rng_state(3))
        return bad, rep.failed

    bad, failed = await bridge(program)()
    assert bad == 5 and failed >= 1, f"expected 5 mismatches to be reported, got {bad} ({failed} failed checks)"
