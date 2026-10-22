# Power estimate: zero-skip gating across sparsity

This is the simulated prediction for the chip's activity-mode measurement (`host/README.md`, "Measuring the
energy saving"). It runs the same weights and zero shares as `bringup.power_sweep()`, gated and with BYPASS
high, on the gate-level netlist in SkyWater sky130 standard cells.

## Results

Typical corner (25 °C, 1.80 V), 50 MHz, 2,000-cycle windows of continuous activity-mode computation.
Weights `[37, -88, 101, -15, 64, 127, -127, 9, -50]`; the zero share is the share of zero pixels.

| Zero share | Chip gated (µW) | Chip BYPASS (µW) | Chip saving | MAC gated (µW) | MAC BYPASS (µW) | MAC saving | MAC dynamic saving |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | 1070.8 | 1070.8 | 0.0% | 353.4 | 353.4 | 0.0% | 0.0% |
| 25% | 1029.6 | 1051.5 | 2.1% | 311.6 | 333.4 | 6.5% | 10.2% |
| 50% | 973.2 | 1015.4 | 4.2% | 258.1 | 300.3 | 14.0% | 23.3% |
| 75% | 910.9 | 971.1 | 6.2% | 200.1 | 260.3 | 23.1% | 42.8% |
| 90% | 864.5 | 936.2 | 7.7% | 156.1 | 227.9 | 31.5% | 66.3% |

Idle (clock running, no computation): chip 709.1 µW, MAC 119.6 µW.

- **MAC** is the `mac_core` instance (operand registers, multiplier, accumulator, skip counter).
  **MAC dynamic saving** compares power above the MAC's idle power: the part that computation adds.
- The gated and BYPASS results are identical at 0% zeros, as they should be: with no zero operands the
  gating never acts.
- The chip's gated-vs-BYPASS difference equals the MAC's difference to 0.1 µW at every share (21.8, 42.2,
  60.2 and 71.8 µW), confirming the gating changes nothing outside the MAC.
- BYPASS power also falls as zeros increase, because a zero operand makes the multiplier's partial products
  quiet even without gating. The gating's saving is the difference on top of that.
- **Most of the chip's power is flop clock power** (709 µW idle across 344 flops), which the gating does not
  touch: operand isolation holds the multiplier's inputs but the registers are still clocked. Clock-gating
  the MAC's registers on zero taps is the natural next step and would raise the chip-level saving.

The rows are in `results/power.csv`; the full OpenSTA reports are in `results/reports/`.

## Method

1. **Synthesis** (`synth_hier.tcl`, Yosys): the RTL in `src/` mapped to sky130_fd_sc_hd cells, with the
   module hierarchy kept so the MAC can be reported on its own (1,992 cells, 19,137 µm²). The liberty is
   filtered by `filter_lib.py` to the cells LibreLane's synthesis uses. `synth.tcl` is the flat version.
2. **Gate-level simulation** (`tb_power.v`, `test_power.py`, Icarus Verilog + cocotb): the netlist with the
   cells' functional models (`flatten_models.py` collects them). One simulation per condition: load the
   weights, set the threshold and BYPASS, `RUN 0`, wait 50 cycles, then dump a VCD for 2,000 cycles with
   no SPI traffic. The same netlist passes the chip tests (`test/test.py`), so its activity is trustworthy.
3. **Power** (OpenSTA `report_power`): the VCD annotates all 7,551 pins; clock 20 ns.

```
python power/run_power.py           # simulate all 11 conditions, then analyze
python power/run_power.py --no-sim  # re-analyze existing VCDs
```

Environment variables give the tool paths: `LIB` (liberty), `NETLIST`, `MODELS`, `STA`, `TT_TEST`.

## Limits of this estimate

- **Pre-layout.** No wire capacitance and an ideal clock, so switching power is underestimated and clock-tree
  power is missing. Rerunning with the post-layout netlist and parasitics (SPEF) from the Tiny Tapeout
  layout run would tighten it; the gated-vs-BYPASS *difference* should change less than the absolute values.
- **Typical corner only.**
- **Activity-mode data.** Generated pixels, not wafer maps. The wafer-map network has 77% zero taps, between
  the 75% and 90% rows.
- The silicon measurement includes the Tiny Tapeout I/O and multiplexer on the same supply, which adds a
  constant offset; measuring gated and BYPASS back to back cancels it.
