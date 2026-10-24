# Starting placement

Places all 110 footprints of the host board, using the Tiny Tapeout demo board's proven
arrangement for every part the two boards share (shifted so the demo's breakout socket lands on
our J3), plus positions for the parts the demo board lacks (power monitor, analog pull-downs,
SWD, logic-analyzer header, mounting holes).

    kicad-cli sch export netlist --format kicadsexpr -o board.net ../../sparse-conv-host/sparse-conv-host.kicad_sch
    python3 place.py        # needs KiCad 7's pcbnew module; writes placed.kicad_pcb and placement.csv
    python3 preview.py      # draws placement-preview.png

`place.py` checks that no two courtyards overlap, that every part is on the 100 x 85 mm board
(USB-C and the PMOD sockets overhang the edge on purpose), and that nothing tall sits under
the breakout board. `libs7/` holds KiCad 7-readable stand-ins for footprints KiCad 7 cannot load
(the breakout socket and RP2350B outlines, generated from the real pad positions); KiCad
replaces them with the real footprints when the board is updated from the schematic.

Outputs are in `../../placement/`.
