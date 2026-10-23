"""Check KiCad's exported netlist against design.py, and run ERC-style rules.

    python check_netlist.py path/to/exported.net

1. Every net in the design is exactly one KiCad net with the same pins.
2. Every no-connect pin is alone.
3. No net has a single pin (except deliberate test points).
4. Power-input pins sit on a net with a driver (power output or PWR_FLAG).
5. No two output-type pins share a net.
6. The breakout socket pin map equals the Tiny Tapeout demo board's.
"""
import sys
from collections import defaultdict

import design
from sexpr import find, one, parse


def kicad_nets(path):
    root = parse(open(path).read())
    nets = {}
    for n in find(one(root, 'nets'), 'net'):
        name = str(one(n, 'name')[1])
        nodes = []
        for nd in find(n, 'node'):
            nodes.append((str(one(nd, 'ref')[1]), str(one(nd, 'pin')[1]),
                          str(one(nd, 'pintype')[1]) if one(nd, 'pintype') else ''))
        nets[name] = nodes
    return nets


def main(path):
    prj = design.prj
    want = defaultdict(set)          # net -> {(ref, pin)}
    nc = set()
    for sh in prj.sheets:
        for p in sh.parts:
            if p.ref.startswith('#'):
                continue
            for pin, net in p.nets.items():
                if net is None:
                    nc.add((p.ref, pin))
                else:
                    want[net].add((p.ref, pin))
    got = kicad_nets(path)
    by_pin = {}
    for name, nodes in got.items():
        for r, pn, t in nodes:
            by_pin[(r, pn)] = name
    errors = []
    for net, pins in sorted(want.items()):
        names = {by_pin.get(rp) for rp in pins}
        if len(names) != 1 or None in names:
            errors.append(f"net {net}: split across {sorted(map(str, names))}")
            continue
        kn = names.pop()
        kpins = {(r, pn) for r, pn, t in got[kn]}
        if kpins != pins:
            errors.append(f"net {net} (KiCad {kn}): extra {sorted(kpins - pins)} missing {sorted(pins - kpins)}")
    for rp in sorted(nc):
        kn = by_pin.get(rp)
        if kn is None or len(got[kn]) != 1:
            errors.append(f"no-connect pin {rp} is not alone: {kn}")
    singles = [n for n, pins in want.items() if len(pins) == 1]
    tps = {n for n in singles if all(r.startswith('TP') for r, _ in want[n])}
    for n in singles:
        if n not in tps:
            errors.append(f"net {n} has a single pin {sorted(want[n])}")
    flagged = {p.nets['1'] for sh in prj.sheets for p in sh.parts if p.ref.startswith('#FLG')}
    for name, nodes in got.items():
        types = [t for _, _, t in nodes]
        if 'power_in' in types and 'power_out' not in types:
            plain = name.lstrip('/').split('/')[-1]
            if plain not in flagged:
                errors.append(f"net {name}: power input without a driver")
        if sum(t in ('output', 'power_out') for t in types) > 1:
            errors.append(f"net {name}: more than one output {nodes}")
    # 6. carrier pin map vs the TT demo board (j5map.txt from the demo schematic)
    import os
    demo = os.path.join(os.path.dirname(design.DEMO), 'j5map.txt')
    if os.path.exists(demo):
        rename = {'+3V3': '+3V3', 'VBUS': '+5V', 'GND': 'GND', '~{project_rst}': 'PROJ_RST_N',
                  'project_clk': 'PROJ_CLK', '~{ctrl_sel_rst}': 'CTRL_SEL_RST_N', 'ctrl_ena': 'CTRL_ENA',
                  'ctrl_sel_inc': 'CTRL_SEL_INC'}
        cref = next(p for sh in prj.sheets for p in sh.parts if p.lib_id == 'TinyTapeout:TT_HRS_BREAKOUT_REVB')
        checked = 0
        for line in open(demo):
            pin, pname, _, dnet = line.split(maxsplit=3)
            dnet = dnet.strip()
            exp = rename.get(dnet)
            if exp is None:
                for pre, ours in (('ui_in', 'UI_IN'), ('uio', 'UIO'), ('uo_out', 'UO_OUT')):
                    if dnet.startswith(pre) and dnet[len(pre):].isdigit():
                        exp = ours + dnet[len(pre):]
            if exp is None:
                continue
            checked += 1
            if cref.nets.get(pin) != exp:
                errors.append(f"carrier {pin} ({pname}): demo board has {dnet}, we have {cref.nets.get(pin)}")
        print(f"carrier pins compared with the demo board: {checked}")
    print(f"design nets: {len(want)}, KiCad nets: {len(got)}, no-connect pins: {len(nc)}, test-point-only nets: {sorted(tps)}")
    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print('  ' + e)
        sys.exit(1)
    print("netlist check: PASS")


if __name__ == '__main__':
    main(sys.argv[1])
