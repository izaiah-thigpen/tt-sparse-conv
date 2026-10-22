![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# Sparsity-Aware Convolution Core

An 8-bit 3×3 convolution multiply-accumulate core for Tiny Tapeout (SkyWater 130 nm),
controlled over SPI. It skips the switching work of any tap whose pixel or weight is
zero, and counts how many it skipped. It is the silicon half of a wafer-map defect
classifier: on the trained network, 77% of taps have a zero operand.

- [Datasheet: how it works and how to test](docs/info.md)

## Layout

| Path | Contents |
| --- | --- |
| `src/project.v` | Tiny Tapeout top level (`tt_um_izaiah_thigpen_sparse_conv`) |
| `src/conv_chip.sv` | SPI interface, command decoder, weight registers |
| `src/mac_core.sv` | Multiply-accumulate core, zero-skip gating, skip counter, output stage |
| `test/test.py` | cocotb tests through the pins only, checked against `test/refmodel.py` |
| `test/refmodel.py` | Bit-exact integer model of the design |

## Run the tests locally

```
cd test
make
```

Needs Icarus Verilog and `pip install -r test/requirements.txt`.

## GitHub Actions

Every push runs the RTL tests, builds the layout with LibreLane, runs Tiny Tapeout's
precheck, reruns the tests on the gate-level netlist, and publishes a layout viewer.
The viewer needs GitHub Pages enabled: Settings → Pages → Source: GitHub Actions.
