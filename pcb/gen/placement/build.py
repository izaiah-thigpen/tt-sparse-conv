"""Load every footprint with its nets into a fresh pcbnew board (no placement yet)
and dump pad positions relative to each footprint origin, for planning."""
import os, re, sys, json
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, '..', '..'))
STD = '/usr/share/kicad/footprints'
LIBS = os.path.join(PCB, 'sparse-conv-host', 'libs')


def parse_net(path):
    t = open(path).read()
    comps = re.findall(r'\(comp \(ref "([^"]+)"\)\s*\(value "[^"]*"\)\s*\(footprint "([^"]+)"\)', t)
    nets = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)', t, re.S):
        name = m.group(1)
        for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2)):
            nets[(ref, pin)] = name
    return comps, nets


def libpath(lib):
    if lib in ('TinyTapeout', 'SparseConvHost') or os.path.exists(os.path.join(HERE, 'libs7', lib + '.pretty')) and lib == 'Package_DFN_QFN':
        return os.path.join(HERE, 'libs7', lib + '.pretty')
    return os.path.join(STD, lib + '.pretty')


def build():
    comps, pinnet = parse_net(os.path.join(HERE, 'board.net'))
    board = pcbnew.BOARD()
    netinfo = {}
    for n in sorted(set(pinnet.values())):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        netinfo[n] = ni
    fps = {}
    for ref, fpid in comps:
        lib, name = fpid.split(':')
        if name == 'L_2016X120N':
            lib, name = 'Inductor_SMD', 'L_Murata_DFE201610P'
        if name == 'SOIC-8_5.3x5.3mm_P1.27mm':
            name = 'SOIC-8_5.275x5.275mm_P1.27mm'
        fp = pcbnew.FootprintLoad(libpath(lib), name)
        assert fp, fpid
        fp.SetReference(ref)
        board.Add(fp)
        for pad in fp.Pads():
            n = pinnet.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])
        fps[ref] = fp
    return board, fps, pinnet


if __name__ == '__main__':
    board, fps, pinnet = build()
    out = {}
    for ref, fp in fps.items():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else fp.GetBoundingBox(False, False)
        out[ref] = {'crt': [pcbnew.ToMM(cy.GetLeft()), pcbnew.ToMM(cy.GetTop()), pcbnew.ToMM(cy.GetRight()), pcbnew.ToMM(cy.GetBottom())],
                    'pads': {p.GetNumber(): [pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p.GetNetname()] for p in fp.Pads()}}
    json.dump(out, open(os.path.join(HERE, 'fpinfo.json'), 'w'), indent=0)
    print(len(fps), 'footprints,', len(set(pinnet.values())), 'nets')
