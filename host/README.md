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
| `board/ina228.py` | Board | Driver for the INA228 power monitor on the host board (`pcb/`); unused on a demo board |
| `vectors/` | Board | `model.bin` (quantized weights) and `map_NN.bin` (wafer maps with expected outputs) |
| `make_vectors.py` | PC | Writes `vectors/` from a trained model |
| `spi_convert.py` | PC | Prints the exact SPI bytes for any single output, for use with any SPI adapter or logic analyzer |
| `tests/` | PC | A software model of the chip and of the INA228, to run the board program and the power sweep without hardware |
| `../power/` | PC | Gate-level power simulation of the same sweep, the prediction for the measurement |

## Testing a chip

**Equipment:** the Tiny Tapeout demo board with this chip, a USB-C cable, and a computer with Python.
An oscilloscope is optional.

1. Install the board tool: `pip install mpremote`
2. Plug in the demo board. From this repository's root, copy the program and vectors:

   ```
   mpremote fs cp host/chip_protocol.py host/board/tt_spi.py host/board/bringup.py host/board/ina228.py :
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

## Measuring the energy saving (activity mode)

This is the measurement for a paper. Over SPI the chip computes at most one tap per byte, so its
current barely changes with the data. The activity mode (`SET_ACTIVITY`, `RUN`, `STOP`) instead runs
the multiplier every clock on generated pixels, a chosen share of them zero, so the gating's saving
shows up in the supply current.

**On the host board (`pcb/`)** the measurement is automatic. Route the core supply through the board's
shunt (see `pcb/README.md`), then run:

```
mpremote exec "import bringup; bringup.power_sweep()"
```

Each step holds 5 seconds while the INA228 records mean current, its spread, core voltage, and power from its
energy accumulator. The sweep runs the chip at 50 MHz, its sign-off clock, prints a table of gated vs ungated
power and the saving at each share of zeros, and writes everything to `power_sweep.csv`.

**On a demo board** with an external meter:

1. Put a current meter (or a sense resistor and a scope) on the chip's supply. Keep the clock fixed.
2. Run the same command, pressing Enter after recording each reading. For a logging meter,
   `bringup.power_sweep(hold_s=10)` holds each step 10 seconds instead.
3. `mpremote fs cp :power_sweep.csv .` retrieves the step list; add the currents to its columns.

The quick test already checks that activity runs give exactly the model's accumulator and skip count, so a
passing quick test means the generator and gating work before any current is measured. The simulated
prediction to compare against is in `power/results/power.md`.

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

Training and quantization are in `model/` (see `model/README.md`). To make vectors from a trained model:

```
python model/export_demo_data.py --data DATA.npz --run RUN_DIR --out demo_data.npz
python host/make_vectors.py --demo demo_data.npz --out host/vectors --per-class 1
```

## How this kit is verified

- `test/test_host.py` runs `board/bringup.py`, unchanged, against the chip RTL in simulation, with its pin
  accesses bridged into the simulator. GitHub Actions runs it on every push, on the RTL and on the
  post-layout gate-level netlist.
- `tests/run_emulated.py` runs the same program on MicroPython against `tests/chip_emulator.py`, a
  software model of the chip, to confirm the board files are MicroPython-compatible.
- `tests/test_power_sweep.py` runs the power sweep against the chip model and a register-level model of the
  INA228 whose current follows the chip's state, on CPython and MicroPython; it must recover each modeled
  gated-vs-ungated difference to 0.1 µA.
- In simulation the data stays correct down to 2 chip clocks per pin access; the board gives far more.
