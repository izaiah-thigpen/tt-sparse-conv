"""Build one Verilog file with the SkyWater functional models for the cells a
netlist uses, resolving each model's `include lines (which are relative to
the model's own folder), so Icarus Verilog can simulate the netlist.

    python flatten_models.py PDK_LIB_DIR netlist.v models_out.v
PDK_LIB_DIR is a checkout of github.com/google/skywater-pdk-libs-sky130_fd_sc_hd.
"""
import os
import re
import sys

INC = re.compile(r'^\s*`include\s+"([^"]+)"', re.M)


def expand(path, seen, out, depth=0):
    """Inline every include. Not deduplicated here: an include can sit in an
    inactive `ifdef branch, so the models' own include guards do the dedup."""
    if depth > 20:
        raise RuntimeError("include nesting too deep at " + path)
    path = os.path.normpath(path)
    seen.add(path)
    text = open(path).read()
    pos = 0
    for m in INC.finditer(text):
        out.append(text[pos:m.start()])
        expand(os.path.join(os.path.dirname(path), m.group(1)), seen, out, depth + 1)
        pos = m.end()
    out.append(text[pos:])


def main(pdk, netlist, dst):
    cells = sorted(set(re.findall(r"\b(sky130_fd_sc_hd__\w+?_\d+)\s+\S+\s*\(", open(netlist).read())))
    out, seen, missing = [], set(), []
    for c in cells:
        base = re.sub(r"_\d+$", "", c).replace("sky130_fd_sc_hd__", "")
        f = os.path.join(pdk, "cells", base, c + ".v")
        if not os.path.exists(f):
            missing.append(c)
            continue
        expand(f, seen, out)
    open(dst, "w").write("\n".join(out))
    print("%d cell types, %d files" % (len(cells), len(seen)) + (", missing %s" % missing if missing else ""))


if __name__ == "__main__":
    main(*sys.argv[1:4])
