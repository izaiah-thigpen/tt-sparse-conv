"""Check that every symbol pin has a pad with the same number in its footprint.

Footprints are looked up in: the project's TinyTapeout.pretty, KiCad 7's
standard libraries, and (for footprints added in KiCad 8/9) copies embedded
in the Tiny Tapeout demo board's .kicad_pcb.
"""
import os
import re
import sys

import design
import symlib as L

STD_FP = '/usr/share/kicad/footprints'
LOCAL = os.path.join(design.OUT, 'libs', 'TinyTapeout.pretty')
DEMO_PCB = os.path.join(design.DEMO, 'tinytapeout-demo.kicad_pcb')


def pads_from_text(text):
    return set(re.findall(r'\(pad "?([^"\s)]*)"?', text))


def demo_footprints():
    if not os.path.exists(DEMO_PCB):
        print(f"note: {DEMO_PCB} not found; footprints added in KiCad 8/9 are reported as not found")
        return {}
    text = open(DEMO_PCB).read()
    out = {}
    for m in re.finditer(r'\(footprint "([^"]+)"', text):
        start = m.start()
        depth, i = 0, start
        while True:
            c = text[i]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.setdefault(m.group(1).split(':')[-1], pads_from_text(text[start:i]))
    return out


def lookup(fp, demo):
    lib, name = fp.split(':')
    for path in (os.path.join(LOCAL, name + '.kicad_mod') if lib == 'TinyTapeout' else None,
                 os.path.join(STD_FP, lib + '.pretty', name + '.kicad_mod')):
        if path and os.path.exists(path):
            return pads_from_text(open(path).read()), path
    if name in demo:
        return demo[name], 'demo board pcb'
    return None, None


def main():
    demo = demo_footprints()
    bad = 0
    for sh in design.prj.sheets:
        for p in sh.parts:
            if p.ref.startswith('#'):
                continue
            if not p.footprint:
                print(f"{p.ref}: no footprint"); bad += 1; continue
            pads, src = lookup(p.footprint, demo)
            if pads is None:
                print(f"{p.ref}: footprint {p.footprint} not found"); bad += 1; continue
            pins = {n for _, n, *_ in L.pins(design.prj._sym(p))}
            missing = pins - pads
            if missing:
                print(f"{p.ref} ({p.value}): pins {sorted(missing)} have no pad in {p.footprint} [{src}]"); bad += 1
    print("footprint check:", "PASS" if not bad else f"{bad} problem(s)")
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
