## How it works

This is the compute core of a small neural-network accelerator for wafer-map defect
classification. It computes one output value of a 3×3 convolution at a time:
nine signed 8-bit weights times nine unsigned 8-bit pixels, added into a 24-bit
accumulator that can be preloaded with a bias and chained across up to 16 input
channels. The result is shifted right by a per-kernel amount and clamped to 0–255.

Its distinguishing feature is **zero-skip gating**. When a pixel or weight is zero,
the multiplier's input registers hold their previous values and the accumulator
does not update, so the multiplier does not switch for that tap. The result is
identical either way. A skip counter records how many taps were skipped, and the
BYPASS pin turns the gating off so the same data can be compared on the same chip.
On the trained wafer-map network, 77% of taps have a zero operand.

The core takes one tap per clock in a two-stage pipeline (operand registers, then
multiply-accumulate). All commands arrive over SPI.

### SPI commands

SPI mode 0, most significant bit first. The system clock must be at least 8× SCLK.
Several commands may share one chip-select frame; unknown bytes (including 0x00) are
ignored. For reads, send 0x00 dummy bytes after the opcode to clock out the response.

| Opcode | Command | Data | Effect |
| --- | --- | --- | --- |
| 0x01 | WRITE_WEIGHTS | 9 bytes in | Nine signed weights, row-major |
| 0x02 | LOAD_ACC | 3 bytes in | Accumulator preload (bias), MSB first |
| 0x03 | WRITE_CONFIG | 1 byte in | Bits 3:0 shift, bit 4 gating enable (on after reset) |
| 0x10 | COMPUTE | 9 bytes in | Nine pixels; adds nine products, then raises DONE |
| 0x20 | READ_RESULT | 1 byte out | (accumulator >>> shift) clamped to 0–255 |
| 0x21 | READ_ACC | 3 bytes out | Raw accumulator, MSB first |
| 0x22 | READ_SKIPS | 2 bytes out | Zero-operand tap count, MSB first |
| 0x23 | CLEAR_SKIPS | none | Zeroes the skip counter |
| 0x30 | SET_ACTIVITY | 1 byte in | Activity-mode zero threshold T (0–255) |
| 0x31 | RUN | 3 bytes in | Activity run of N taps, MSB first; N = 0 runs until STOP |
| 0x32 | STOP | none | Ends an activity run |
| 0x7F | READ_ID | 1 byte out | Always 0xA5 |

### Activity mode (for measuring the gating's energy saving)

Over SPI the core gets at most one tap per byte, so it is idle most of the time and the
gating's effect on supply current is too small to measure. RUN feeds the core one tap per
clock from an on-chip generator instead: a 32-bit xorshift sequence (seed 0x2545F491) makes
each pixel, zero when its top byte is below T (about T/256 of taps), otherwise an odd
nonzero value; the weights cycle through the nine loaded weights. BUSY is high during a run
and DONE rises when it ends. The accumulator wraps at 24 bits and the skip counter
saturates at 65,535; both match a software model exactly, so a run is also a self-check.
Comparing supply current with BYPASS low and high, at several thresholds, measures the
energy saved per skipped tap. Gate-level simulation predicts the multiply-accumulate unit's
dynamic power falls by 23% at 50% zero taps and by 66% at 90% (see `power/` in the repository).

## How to test

The `host/` folder of the repository has a complete test kit; see `host/README.md`. In short, with the
chip on a Tiny Tapeout demo board:

```
pip install mpremote
mpremote fs cp host/chip_protocol.py host/board/tt_spi.py host/board/bringup.py :
mpremote fs cp -r host/vectors :
mpremote run host/board/bringup.py
```

The RP2040 then runs smoke tests (chip ID, hand-checked values, gating on and off) and the convolution
layers of a stored network, comparing every output with precomputed values, and prints PASS or FAIL.

To test by hand: reset the chip, then send `7F 00` with chip select low. The second byte read back should
be `A5`. Then send `03 10` (shift 0, gating on), `02 00 00 00` (zero the accumulator), `01` followed by
nine weights, `10` followed by nine pixels, and `20 00`; the second byte read back is the result. With
weights all 1 and pixels 1 to 9, the result is 45. `host/spi_convert.py` prints the bytes for any output.

Watch SKIP (uo[2]) on a scope while computing with some zero pixels: it pulses once per skipped multiply.
With BYPASS (ui[3]) high the results are the same; only the switching activity differs.

To measure the energy saving, run `mpremote exec "import bringup; bringup.power_sweep()"` with
a meter on the chip's supply: it steps through idle and five zero shares, gated and with BYPASS,
and writes the steps to `power_sweep.csv` for the readings.

## External hardware

An SPI host, such as a microcontroller or a PYNQ FPGA board, on ui[0..2] and uo[0].
Optionally an oscilloscope on SKIP (uo[2]) and DONE (uo[1]), and a current meter on the
project supply for the activity-mode power measurement.
