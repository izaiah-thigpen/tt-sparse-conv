# SPDX-FileCopyrightText: © 2026 Izaiah Thigpen
# SPDX-License-Identifier: Apache-2.0
"""Chip tests through the Tiny Tapeout pins only.

These run twice in GitHub Actions: on the RTL, and on the gate-level netlist
after layout (GATES=yes). So they touch nothing but the pins, and every result
is checked against refmodel.py, the bit-exact integer model of the design.
"""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer

import refmodel as rm

CLK_NS = 20  # 50 MHz, matching CLOCK_PERIOD in src/config.json
GATE_LEVEL = os.environ.get("GATES") == "yes"
RANDOM_VALUES = int(os.environ.get("RANDOM_VALUES", "6" if GATE_LEVEL else "25"))

SCLK, CS_N, MOSI, BYPASS = 0, 1, 2, 3
MISO, DONE, SKIP, BUSY = 0, 1, 2, 3


class Pins:
    def __init__(self, dut):
        self.dut = dut
        self.ui = 1 << CS_N

    def set(self, bit, value):
        self.ui = (self.ui | (1 << bit)) if value else (self.ui & ~(1 << bit))
        self.dut.ui_in.value = self.ui

    def get(self, bit):
        return (int(self.dut.uo_out.value) >> bit) & 1


class Spi:
    """SPI mode 0 master, timed independently of the chip clock.
    ratio = system clock cycles per SCLK period (the chip needs at least 8)."""

    def __init__(self, pins, ratio=8):
        self.pins = pins
        self.half_ns = ratio * CLK_NS / 2

    async def half(self):
        await Timer(self.half_ns, unit="ns")

    async def xfer(self, data, hold_cs=False, abort_after_bits=None):
        p = self.pins
        p.set(CS_N, 0)
        await self.half()
        out, bits = [], 0
        for byte in data:
            got = 0
            for b in range(7, -1, -1):
                p.set(MOSI, (byte >> b) & 1)
                await self.half()
                got = (got << 1) | p.get(MISO)
                p.set(SCLK, 1)
                await self.half()
                p.set(SCLK, 0)
                bits += 1
                if abort_after_bits is not None and bits == abort_after_bits:
                    break
            out.append(got)
            if abort_after_bits is not None and bits == abort_after_bits:
                break
        await self.half()
        if not hold_cs:
            p.set(CS_N, 1)
            for _ in range(4):
                await self.half()
        return out


class ChipHost:
    """One method per SPI command; the same sequence a real host runs."""

    def __init__(self, spi):
        self.spi = spi

    async def read_id(self):
        return (await self.spi.xfer([0x7F, 0x00]))[1]

    async def write_weights(self, w):
        await self.spi.xfer([0x01] + [int(x) & 0xFF for x in w])

    async def load_acc(self, v):
        v &= 0xFFFFFF
        await self.spi.xfer([0x02, v >> 16, (v >> 8) & 0xFF, v & 0xFF])

    async def write_config(self, shift, gate=1):
        await self.spi.xfer([0x03, (shift & 0xF) | (gate << 4)])

    async def compute(self, pixels):
        await self.spi.xfer([0x10] + [int(x) for x in pixels])

    async def read_result(self):
        return (await self.spi.xfer([0x20, 0x00]))[1]

    async def read_acc(self):
        r = await self.spi.xfer([0x21, 0, 0, 0])
        v = (r[1] << 16) | (r[2] << 8) | r[3]
        return v - (1 << 24) if v & 0x800000 else v

    async def read_skips(self):
        r = await self.spi.xfer([0x22, 0, 0])
        return (r[1] << 8) | r[2]

    async def clear_skips(self):
        await self.spi.xfer([0x23])

    async def set_activity(self, threshold):
        await self.spi.xfer([0x30, threshold])

    async def run(self, n_taps):
        await self.spi.xfer([0x31, (n_taps >> 16) & 0xFF, (n_taps >> 8) & 0xFF, n_taps & 0xFF])

    async def stop(self):
        await self.spi.xfer([0x32])

    async def output_value(self, groups, bias, shift, gate=1):
        await self.write_config(shift, gate)
        await self.load_acc(bias)
        for pix, wts in groups:
            await self.write_weights(wts)
            await self.compute(pix)
        return await self.read_result()


async def setup(dut, ratio=8):
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    pins = Pins(dut)
    dut.ui_in.value = pins.ui
    dut.uio_in.value = 0
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    await Timer(7, unit="ns")  # SPI timing out of phase with the clock
    return pins, ChipHost(Spi(pins, ratio))


def reference(groups, bias, shift):
    acc, skips = bias, 0
    for pix, wts in groups:
        acc, s = rm.mac9(pix, wts, acc)
        skips += s
    return rm.output_stage(acc, shift), acc, skips


async def check_value(host, groups, bias, shift, gate=1, label=""):
    await host.clear_skips()
    got = await host.output_value(groups, bias, shift, gate)
    want, want_acc, want_skips = reference(groups, bias, shift)
    acc = await host.read_acc()
    skips = await host.read_skips()
    assert acc == want_acc, f"{label}: acc {acc} != ref {want_acc}"
    assert got == want, f"{label}: result {got} != ref {want}"
    assert skips == want_skips, f"{label}: skips {skips} != ref {want_skips}"


def random_group(rng, sparsity):
    pix = [0 if rng.random() < sparsity else rng.randint(1, 255) for _ in range(9)]
    return pix, [rng.randint(-127, 127) for _ in range(9)]


@cocotb.test()
async def read_id(dut):
    """READ_ID returns 0xA5; MISO is low while chip select is high."""
    pins, host = await setup(dut)
    assert pins.get(MISO) == 0
    assert await host.read_id() == 0xA5


@cocotb.test()
async def corner_values(dut):
    """Corner cases with gating on, gating off by config, and gating off by the BYPASS pin."""
    pins, host = await setup(dut)
    cases = [
        ([0] * 9, [5, -3, 7, 1, 2, -8, 9, 4, 6]),
        ([10, 20, 30, 40, 50, 60, 70, 80, 90], [0] * 9),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9], [9, -8, 7, -6, 5, -4, 3, -2, 1]),
        ([255] * 9, [127] * 9),
        ([255] * 9, [-127] * 9),
    ]
    for pix, wts in cases:
        for gate, bypass in ((1, 0), (0, 0), (1, 1)):
            pins.set(BYPASS, bypass)
            for bias, shift in ((0, 0), (-5000, 4), (300_000, 11)):
                await check_value(host, [(pix, wts)], bias, shift, gate, f"gate={gate} bypass={bypass}")
    pins.set(BYPASS, 0)


@cocotb.test()
async def chained_values(dut):
    """Layer-2 style values: up to 16 channels summed into one output."""
    pins, host = await setup(dut)
    rng = random.Random(2)
    await check_value(host, [([255] * 9, [127] * 9)] * 16, 0, 15, 1, "worst-case chain")
    for i in range(RANDOM_VALUES):
        sparsity = rng.choice((0.0, 0.25, 0.5, 0.75, 0.9))
        groups = [random_group(rng, sparsity) for _ in range(rng.randint(1, 16))]
        await check_value(host, groups, rng.randint(-(1 << 20), 1 << 20), rng.randint(0, 15),
                          rng.randint(0, 1), f"value {i}")


@cocotb.test()
async def command_framing(dut):
    """Several commands in one frame, ignored bytes, and aborted commands."""
    pins, host = await setup(dut)
    spi = host.spi
    pix, wts = [3, 0, 5, 7, 0, 2, 9, 1, 4], [2, 4, -6, 8, 1, 0, -3, 5, 7]
    want, want_acc, _ = reference([(pix, wts)], 100, 2)
    frame = ([0x00, 0x03, 2 | 16, 0x55, 0x02, 0, 0, 100, 0x00, 0x01]
             + [w & 0xFF for w in wts] + [0x10] + pix + [0x20, 0x00])
    r = await spi.xfer(frame)
    assert r[-1] == want, f"one-frame result {r[-1]} != {want}"
    assert await host.read_acc() == want_acc
    await spi.xfer([0x02, 0x12, 0x34])
    assert await host.read_acc() == want_acc, "aborted LOAD_ACC changed the accumulator"
    await spi.xfer([0x02, 0x7F], abort_after_bits=12)
    assert await host.read_id() == 0xA5
    assert await host.read_acc() == want_acc


@cocotb.test()
async def done_and_busy(dut):
    """BUSY is high during COMPUTE; DONE rises when it finishes and clears on the next."""
    pins, host = await setup(dut)
    spi = host.spi
    await host.write_weights([1] * 9)
    assert pins.get(DONE) == 0 and pins.get(BUSY) == 0
    await spi.xfer([0x10, 1, 2, 3, 4], hold_cs=True)
    assert pins.get(BUSY) == 1 and pins.get(DONE) == 0
    await spi.xfer([5, 6, 7, 8, 9])
    assert pins.get(BUSY) == 0 and pins.get(DONE) == 1
    await spi.xfer([0x10, 1], hold_cs=True)
    assert pins.get(DONE) == 0 and pins.get(BUSY) == 1
    await spi.xfer([1] * 8)
    assert pins.get(DONE) == 1


@cocotb.test()
async def spi_clock_ratios(dut):
    """SCLK at 1/8, 1/10 and 1/16 of the system clock."""
    rng = random.Random(3)
    groups = [random_group(rng, 0.5) for _ in range(4)]
    pins, _ = await setup(dut)
    for ratio in (8, 10, 16):
        await check_value(ChipHost(Spi(pins, ratio)), groups, -1234, 6, 1, f"ratio {ratio}")


async def wait_done(dut, pins, max_cycles):
    for _ in range(max_cycles):
        if pins.get(DONE) and not pins.get(BUSY):
            return
        await ClockCycles(dut.clk, 1)
    raise AssertionError("activity run did not finish")


async def activity_check(dut, pins, host, weights, bias, threshold, n_taps, gate, label):
    await host.write_weights(weights)
    await host.write_config(0, gate)
    await host.load_acc(bias)
    await host.clear_skips()
    await host.set_activity(threshold)
    await host.run(n_taps)
    assert pins.get(BUSY) == 1 or n_taps < 40, f"{label}: BUSY not high during the run"
    await wait_done(dut, pins, n_taps + 200)
    want_acc, want_skips = rm.activity_run(weights, n_taps, threshold, acc=bias)
    acc, skips = await host.read_acc(), await host.read_skips()
    assert acc == want_acc, f"{label}: acc {acc} != model {want_acc}"
    assert skips == want_skips, f"{label}: skips {skips} != model {want_skips}"
    return skips


@cocotb.test()
async def activity_runs(dut):
    """Activity mode: generated taps at several zero thresholds, gated, ungated and BYPASS."""
    pins, host = await setup(dut)
    rng = random.Random(9)
    n = 300 if GATE_LEVEL else 900
    for threshold in (0, 64, 128, 230, 255):
        weights = [rng.randint(-127, 127) for _ in range(9)]
        weights[rng.randint(0, 8)] = 0
        for gate, bypass in ((1, 0), (0, 0), (1, 1)):
            pins.set(BYPASS, bypass)
            await activity_check(dut, pins, host, weights, rng.randint(-50000, 50000), threshold, n, gate,
                                 f"T={threshold} gate={gate} bypass={bypass}")
    pins.set(BYPASS, 0)
    assert await host.read_id() == 0xA5, "SPI broken after activity runs"


@cocotb.test()
async def activity_wrap_and_saturate(dut):
    """Long runs: the accumulator wraps at 24 bits and the skip counter saturates."""
    pins, host = await setup(dut)
    n = 70000
    await activity_check(dut, pins, host, [127] * 9, 0, 0, n, 1, "wrap")
    skips = await activity_check(dut, pins, host, [127] * 9, 0, 255, n, 1, "saturate")
    assert skips == 0xFFFF


@cocotb.test()
async def activity_until_stop(dut):
    """RUN 0 runs until STOP; the taps executed match the model for some count."""
    pins, host = await setup(dut)
    weights = [3, -7, 0, 11, 25, -1, 9, 4, -60]
    await host.write_weights(weights)
    await host.write_config(0, 1)
    await host.load_acc(0)
    await host.clear_skips()
    await host.set_activity(100)
    await host.run(0)
    await ClockCycles(dut.clk, 500)
    assert pins.get(BUSY) == 1 and pins.get(DONE) == 0, "not running"
    await host.stop()
    await ClockCycles(dut.clk, 10)
    assert pins.get(BUSY) == 0 and pins.get(DONE) == 1, "did not stop"
    acc, skips = await host.read_acc(), await host.read_skips()
    await ClockCycles(dut.clk, 100)
    assert (await host.read_acc(), await host.read_skips()) == (acc, skips), "kept running after STOP"
    for n in range(400, 3000):
        if rm.activity_run(weights, n, 100) == (acc, skips):
            dut._log.info(f"stopped after {n} taps")
            break
    else:
        raise AssertionError(f"acc {acc}, skips {skips} match no run length")
