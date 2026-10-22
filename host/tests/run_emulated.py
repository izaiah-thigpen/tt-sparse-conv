"""Run the board program against the software chip model.

Works under CPython and MicroPython (that is the point: it checks the board
files run on MicroPython before they ever reach the RP2040):

    micropython run_emulated.py VECTOR_DIR [quick|full|smoke]
    python run_emulated.py VECTOR_DIR [quick|full|smoke]

With MicroPython, set MICROPYPATH to include host/ and host/board/.
Exit status 0 means every check passed.
"""
import sys

import bringup
from chip_emulator import ChipEmulator
from tt_spi import Spi


def main():
    vector_dir = sys.argv[1] if len(sys.argv) > 1 else "vectors"
    mode = sys.argv[2] if len(sys.argv) > 2 else "quick"
    emu = ChipEmulator()
    spi = Spi(emu.write_ui, emu.read_uo)
    ok = bringup.run(spi, mode, vector_dir=vector_dir)
    print("pin writes: %d" % emu.pin_writes)
    sys.exit(0 if ok else 1)


main()
