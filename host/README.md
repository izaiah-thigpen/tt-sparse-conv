# Host kit: testing the chip

Everything needed to test the fabricated chip on a Tiny Tapeout demo board, without the designer present.
The demo board's RP2040 microcontroller acts as the SPI host: it converts wafer maps and weights into SPI
commands, sends them, and checks every reply against values precomputed by the reference model.

## What is here

| File | Runs on | Purpose |
| --- | --- | --- |
| `chip_protocol.py` | PC and board | The data-to-SPI and SPI-to-data converter: one encoder per command, decoders for replies, and readers for the vector files |
| `board/tt_spi.py` | Board | Bit-banged SPI through the demo board's pins |
| `board/bringup.py` | Board | The test program: smoke tests, then the trained network on stored wafer maps, with PASS/FAIL per check |
| `vectors/` | Board | `model.bin` (quantized weights) and `map_NN.bin` (wafer maps with expected outputs) |
| `make_vectors.py` | PC | Writes `vectors/` from a trained model |
| `spi_convert.py` | PC | Prints the exact SPI bytes for any single output, for use with any SPI adapter or logic analyzer |
| `tests/` | PC | A software model of the chip, to run the board program without hardware |

## Testing a chip

**Equipment:** the Tiny Tapeout demo board with this chip, a USB-C cable, and a computer with Python.
An oscilloscope is optional.

1. Install the board tool: `pip install mpremote`
2. Plug in the demo board. From this repository's root, copy the program and vectors:

   ```
   mpremote fs cp host/chip_protocol.py host/board/tt_spi.py host/board/bringup.py :
   mpremote fs cp -r host/vectors :
   ```

3. Run the quick test (about a minute):

   ```
   mpremote run host/board/bringup.py
   ```

4. Run the full test, every output of every stored map (several minutes per map; the quick test prints an estimate):

   ```
   mpremote exec "import bringup; bringup.main('full')"
   ```

Each check prints `PASS` or `FAIL`, and the last line is the overall result. Everything is also appended
to `results.txt` on the board: `mpremote fs cp :results.txt .` retrieves it.

The program selects the project, sets a 10 MHz project clock and resets it. If the very first check
(`READ_ID returns 0xA5`) fails, nothing else will work: check the board is powered, the project is
selected, and the clock is running.

**Optional measurements:**
- `uo_out[2]` (SKIP) pulses once per skipped multiply; on a scope it shows the zero-skip gating working.
- `ui_in[3]` (BYPASS) high turns gating off. Results must not change; only the switching activity does.
- Comparing the chip's supply current with BYPASS low and high, on the same data, measures the
  energy the gating saves.

## How data becomes SPI

The chip computes one output of a 3×3 convolution at a time. For each output the host sends:

| Command | Bytes | Meaning |
| --- | --- | --- |
| `WRITE_CONFIG` | `03 SS` | Shift amount and gating enable for this kernel |
| `LOAD_ACC` | `02 BB BB BB` | The kernel's bias, 24-bit, MSB first |
| `WRITE_WEIGHTS` | `01 w0 … w8` | Nine signed 8-bit weights for one input channel |
| `COMPUTE` | `10 p0 … p8` | Nine 8-bit pixels: the 3×3 window of that channel |
| `READ_RESULT` | `20 00` | The chip replies with the 8-bit output during the `00` |

A layer-1 output is one `COMPUTE` (one input channel); a layer-2 output repeats `WRITE_WEIGHTS` +
`COMPUTE` for each of its 16 input channels into the same sum. `spi_convert.py` prints a worked example
for any output.

## Training and weights

The chip only runs the network; it does not train and stores no weights between commands. Training
happens once on a PC (PyTorch, on the WM-811K wafer-map dataset), followed by conversion to 8-bit integers.
`make_vectors.py` packs those integers into `model.bin`, and the host streams them to the chip with each
computation. A different trained model needs only new vector files, not a different chip.

To make vectors from a new model, export it from the main project with `model/export_demo_data.py`, then:

```
python host/make_vectors.py --demo demo_data.npz --out host/vectors --per-class 1
```

## How this kit is verified

- `test/test_host.py` runs `board/bringup.py`, unchanged, against the chip RTL in simulation, with its pin
  accesses bridged into the simulator. GitHub Actions runs it on every push, on the RTL and on the
  post-layout gate-level netlist.
- `tests/run_emulated.py` runs the same program on MicroPython against `tests/chip_emulator.py`, a
  software model of the chip, to confirm the board files are MicroPython-compatible.
- In simulation the data stays correct down to 2 chip clocks per pin access; the board gives far more.
