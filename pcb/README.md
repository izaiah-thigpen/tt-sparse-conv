# Host board for the sparsity-aware convolution chip

A replacement for the Tiny Tapeout demo board, built to measure the chip's power. It keeps the demo
board v3's RP2350B pin map, so Tiny Tapeout's MicroPython firmware and the `host/` test kit run on it
unchanged, and adds a TI INA228 power monitor on the chip's 1.8 V core supply.

Status: **schematic rev A done; KiCad 9 ERC has 0 errors; layout not started.**

## What is here

| Path | Contents |
| --- | --- |
| `sparse-conv-host/` | The KiCad project: open `sparse-conv-host.kicad_pro` in KiCad 9 (it upgrades the KiCad 7 files) |
| `sparse-conv-host/libs/` | Tiny Tapeout symbols (RP2350B, breakout socket, PMOD host) and footprints (Apache 2.0); `SparseConvHost.pretty` holds the two footprints KiCad 9's libraries lack (RP2350 inductor, INA228 VSSOP-10) |
| `sparse-conv-host-schematic.pdf` | The schematic, 5 pages |
| `gen/design.py` | The design as data: every part, value, footprint, part number and pin-to-net assignment |
| `gen/schgen.py`, `gen/symlib.py`, `gen/sexpr.py` | Writes the KiCad schematic from `design.py` |
| `gen/check_netlist.py`, `gen/check_footprints.py` | Checks KiCad's own exported netlist against the design |

The schematic is generated, so change `design.py` and rerun `python gen/design.py` rather than editing
connections by hand. Moving symbols around in KiCad for readability is fine; it does not change the nets.
The sheets are drawn net-label style: each pin has a short wire and a label, so the connections are
exactly the ones in `design.py`.

## Sheets

1. **Power:** USB-C, polyfuse, ESD, TLV1117LV33 3.3 V LDO, power LEDs (as on the demo board).
2. **MCU:** RP2350B, W25Q32 flash, 12 MHz crystal, internal core regulator, BOOT and RESET buttons, SWD
   header (copied from the demo board's RP2350B sheet).
3. **Breakout:** the Hirose DF12 60+50-pin socket for the chip's breakout (`TT_HRS_CARRIER_REVC`), MUX
   pull-ups, project reset and clock, three PMOD sockets, a 2×8 logic-analyzer header, 10 MΩ pull-downs
   on the analog pins, mounting holes.
4. **Power monitor:** INA228 across a 0.499 Ω + 4.99 Ω shunt in the core supply, I2C on GPIO12/13,
   ALERT on GPIO15.

## Measuring the chip's core power

The breakout regulates the chip's 1.8 V core itself: AP2112K-1.8 → `VCC_REG` → R14 (0 Ω, 0805) →
`VCCD`. To route the core supply through this board's shunt:

1. On the breakout, remove R14 and solder a 1×12 header into J2.
2. Wire J2 pin 5 (`VCC_REG`) to CORE pin 1, J2 pin 6 (`VCCD`) to CORE pin 2, and ground to CORE pin 3.
3. Normal range: 5.49 Ω, 7.5 mA full scale, 14 nA per step. For more current, fit a jumper on RANGE
   (0.499 Ω, 82 mA full scale).

Without the wires and with R14 in place, the board works exactly like a demo board.

## Checks

- KiCad 7's netlist export reads all sheets; every one of the 99 design nets is one KiCad net with
  exactly the intended pins, every no-connect pin is alone, and no net has a single pin.
- ERC-style rules: every power-input pin has a driver or power flag; no two outputs share a net.
- All 63 used pins of the breakout socket match the Tiny Tapeout demo board, and the socket's power,
  ground, I/O and MUX pins were cross-checked against the SkyWater breakout rev 3.1 schematic.
- Every symbol pin has a pad of the same number in its footprint.

- KiCad 9 ERC: 0 errors. Remaining warnings are harmless: library-copy mismatches (the schematic embeds
  KiCad 7 copies of standard symbols), QSPI_IOVDD typed bidirectional in the Tiny Tapeout RP2350 symbol,
  and the breakout socket's hidden `3v3` pins merging into `+3V3`.

Run `kicad-cli sch export netlist -o board.net sparse-conv-host/sparse-conv-host.kicad_sch`, then
`python gen/check_netlist.py board.net` and `python gen/check_footprints.py`. Run KiCad 9's ERC as well
after opening the project.

## Open items

- Confirm this shuttle's chips ship on SkyWater breakout rev 3.1.
- JLCPCB sourcing for the Hirose DF12NB(5.0)-60DP and -50DP connectors, the RP2350B, the shunts and
  the 10 MΩ resistors (LCSC numbers are filled in only where verified).
- Layout: 4 layers; Kelvin traces from the shunt pads to the INA228; follow Raspberry Pi's RP2350
  layout guidance for the crystal, flash and core regulator.

Derived from the [Tiny Tapeout demo board](https://github.com/TinyTapeout/tt-demo-pcb) and
[breakout](https://github.com/TinyTapeout/breakout-pcb) designs, © 2024–2025 Pat Deegan / Psychogenic
Technologies, Apache 2.0.
