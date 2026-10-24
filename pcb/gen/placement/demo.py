"""Parse the demo board: footprint ref, lib name, position, rotation, side, pad->net."""
import re, json, sys

import os
PCB = os.environ.get('TT_DEMO_PCB', os.path.join(os.path.dirname(__file__), '..', 'tt-demo-pcb', 'tinytapeout-demo.kicad_pcb'))


def blocks(text, head):
    for m in re.finditer(r'\(' + head + r' "', text):
        s = m.start(); d = 0; i = s
        while True:
            c = text[i]
            if c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            elif c == '"':
                i += 1
                while text[i] != '"':
                    if text[i] == '\\':
                        i += 1
                    i += 1
            i += 1
        yield text[s:i + 1]


def parse():
    t = open(PCB).read()
    out = []
    for b in blocks(t, 'footprint'):
        name = re.match(r'\(footprint "([^"]+)"', b).group(1)
        at = re.search(r'\n\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', b)
        layer = re.search(r'\(layer "([^"]+)"\)', b).group(1)
        ref = re.search(r'\(property "Reference" "([^"]+)"', b)
        val = re.search(r'\(property "Value" "([^"]+)"', b)
        pads = {}
        for p in re.finditer(r'\(pad "([^"]*)".*?\(net \d+ "([^"]*)"\)', b, re.S):
            pads.setdefault(p.group(1), p.group(2))
        out.append(dict(ref=ref.group(1) if ref else '?', val=val.group(1) if val else '', fp=name,
                        x=float(at.group(1)), y=float(at.group(2)), rot=float(at.group(3) or 0),
                        side=layer, pads=pads))
    return out


if __name__ == '__main__':
    fps = parse()
    json.dump(fps, open('demo.json', 'w'), indent=0)
    for f in sorted(fps, key=lambda f: f['ref']):
        print(f['ref'], f['val'], f['fp'].split(':')[-1], f['x'], f['y'], f['rot'], f['side'])
