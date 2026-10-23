"""Write a hierarchical KiCad 7 schematic from a netlist-style description.

Each part is placed on a grid; every pin gets a short wire stub ending in a
net label, a power symbol, or a no-connect flag. Connectivity is therefore
exactly the description, and KiCad's own netlist export checks it.
"""
import math
import uuid

import symlib as L
from sexpr import Q, dump

NS = uuid.UUID('7b0c3f9e-1d2a-4c55-9a77-5e2b1c3d4f60')
GRID = 2.54
POWER = {'GND': 'power:GND', '+3V3': 'power:+3V3', '+5V': 'power:+5V', '+1V1': 'power:+1V1'}
POWER_DOWN = {'GND'}           # graphic points away from the pin, downward by default


def uid(*parts):
    return Q(str(uuid.uuid5(NS, '/'.join(map(str, parts)))))


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def fnt(size=1.27):
    return ['font', ['size', size, size]]


def _pin_screen(px, py, pa, rot):
    """Pin end offset and outward unit vector on screen for a symbol rotated by rot degrees."""
    r = math.radians(rot)
    sx, sy = px, -py                                   # library y is up, schematic y is down
    ox = sx * math.cos(r) + sy * math.sin(r)
    oy = -sx * math.sin(r) + sy * math.cos(r)
    bx, by = math.cos(math.radians(pa)), -math.sin(math.radians(pa))   # toward the body
    rbx = bx * math.cos(r) + by * math.sin(r)
    rby = -bx * math.sin(r) + by * math.cos(r)
    return round(ox, 4), round(oy, 4), -round(rbx), -round(rby)


def _bbox_rot(sym, unit, rot):
    x0, y0, x1, y1 = L.bbox(sym, unit)
    if rot % 180 == 0:
        return x0, y0, x1, y1
    pts = []
    for (X, Y) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        ox, oy, _, _ = _pin_screen(X, -Y, 0, rot)
        pts.append((ox, oy))
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def _label_room(part, sym, unit, rot, prj):
    """Space needed outside the body for stubs and labels, per side."""
    room = {'l': 2.54, 'r': 2.54, 't': 2.54, 'b': 2.54}
    for (pu, num, nm, px, py, pa, ln, et) in L.pins(sym):
        if pu not in (0, unit):
            continue
        _, _, dx, dy = _pin_screen(px, py, pa, rot)
        net = part.nets.get(num)
        size = 7.62 if (net is None or net in POWER) else 5.08 + 1.1 * len(net) + 3
        side = {(-1, 0): 'l', (1, 0): 'r', (0, -1): 't', (0, 1): 'b'}[(dx, dy)]
        room[side] = max(room[side], size)
    return room


class Part:
    def __init__(self, ref, lib_id, value, nets, footprint='', fields=None, dnp=False, sym=None):
        self.ref, self.lib_id, self.value = ref, lib_id, value
        self.nets = nets                     # {pin number: net name or None for no-connect}
        self.footprint = footprint
        self.fields = fields or {}
        self.dnp = dnp
        self.sym = sym                       # pre-loaded symbol tree (for embedded symbols)


class Sheet:
    def __init__(self, name, file, title, paper='A3', cols=4):
        self.name, self.file, self.title, self.paper, self.cols = name, file, title, paper, cols
        self.parts = []
        self.notes = []

    def add(self, *parts):
        self.parts.extend(parts)

    def note(self, text):
        self.notes.append(text)


PAPER = {'A4': (297, 210), 'A3': (420, 297), 'A2': (594, 420), 'A1': (841, 594)}


class Project:
    def __init__(self, name, title, rev, company, date):
        self.name, self.title, self.rev, self.company, self.date = name, title, rev, company, date
        self.sheets = []
        self.root_uuid = uid(name, 'root')
        self.symbols = {}

    def sheet(self, *a, **k):
        s = Sheet(*a, **k)
        self.sheets.append(s)
        return s

    # -------------------------------------------------------------- symbols
    def _sym(self, part):
        if part.lib_id not in self.symbols:
            self.symbols[part.lib_id] = part.sym if part.sym is not None else L.std(part.lib_id)
        return self.symbols[part.lib_id]

    def _psym(self, net):
        lib = POWER[net]
        if lib not in self.symbols:
            self.symbols[lib] = L.std(lib)
        return lib

    # -------------------------------------------------------------- checks
    def check(self):
        refs = set()
        net_sheets = {}
        for sh in self.sheets:
            for p in sh.parts:
                assert p.ref not in refs, f"duplicate reference {p.ref}"
                refs.add(p.ref)
                sym = self._sym(p)
                pins = {n for _, n, *_ in L.pins(sym)}
                missing = pins - set(p.nets)
                extra = set(p.nets) - pins
                assert not missing, f"{p.ref}: pins without a net or NC: {sorted(missing)}"
                assert not extra, f"{p.ref}: unknown pins {sorted(extra)}"
                for n in p.nets.values():
                    if n and n not in POWER:
                        net_sheets.setdefault(n, set()).add(sh.name)
        self.global_nets = {n for n, s in net_sheets.items() if len(s) > 1}
        return net_sheets

    # -------------------------------------------------------------- writing
    def write(self, outdir):
        import os
        os.makedirs(outdir, exist_ok=True)
        net_sheets = self.check()
        self.page = {sh.file: i + 2 for i, sh in enumerate(self.sheets)}
        for sh in self.sheets:
            open(os.path.join(outdir, sh.file), 'w').write(self._sheet_file(sh))
        open(os.path.join(outdir, self.name + '.kicad_sch'), 'w').write(self._root_file())
        return net_sheets

    def _title_block(self, title, page_comment=''):
        return ['title_block', ['title', Q(title)], ['date', Q(self.date)], ['rev', Q(self.rev)],
                ['company', Q(self.company)], ['comment', 1, Q(page_comment)]]

    def _root_file(self):
        body = ['kicad_sch', ['version', 20230121], ['generator', 'eeschema'],
                ['uuid', self.root_uuid], ['paper', Q('A4')],
                self._title_block(self.title, 'Top level: one block per sheet'),
                ['lib_symbols']]
        x, y = 30.48, 40.64
        for i, sh in enumerate(self.sheets):
            su = uid(self.name, 'sheet', sh.file)
            sh.uuid = su
            w, h = 50.8, 20.32
            body.append(['sheet', ['at', x, y], ['size', w, h], ['fields_autoplaced'],
                         ['stroke', ['width', 0.1524], ['type', 'solid']],
                         ['fill', ['color', 0, 0, 0, 0.0]], ['uuid', su],
                         ['property', Q('Sheetname'), Q(sh.title), ['at', x, y - 0.7116, 0],
                          ['effects', fnt(), ['justify', 'left', 'bottom']]],
                         ['property', Q('Sheetfile'), Q(sh.file), ['at', x, y + h + 0.5846, 0],
                          ['effects', fnt(), ['justify', 'left', 'top']]],
                         ['instances', ['project', Q(self.name),
                                        ['path', Q('/' + self.root_uuid), ['page', Q(str(self.page[sh.file]))]]]]])
            x += 76.2
            if (i + 1) % 2 == 0:
                x = 30.48; y += 45.72
        body.append(['text', Q(self.notes_root()), ['at', 30.48, 150, 0],
                     ['effects', fnt(1.5), ['justify', 'left', 'top']], ['uuid', uid(self.name, 'rootnote')]])
        body.append(['sheet_instances', ['path', Q('/'), ['page', Q('1')]]])
        return dump(body) + '\n'

    def notes_root(self):
        return getattr(self, 'root_note', '')

    def _sheet_file(self, sh):
        pw, ph = PAPER[sh.paper]
        su = uid(self.name, 'sheet', sh.file)
        sh.uuid = su
        path = Q('/' + self.root_uuid + '/' + su)
        items, used = [], set()
        # layout: rows left to right; two-pin parts drawn horizontally
        margin_l, margin_t = 20.32, 25.4
        x, y, row_h = margin_l, margin_t, 0.0
        right, bottom = pw - 15, ph - 50
        placements = []
        for p in sh.parts:
            sym = self._sym(p)
            used.add(p.lib_id)
            pl = L.pins(sym)
            rot = 90 if len(pl) == 2 and all(a in (90.0, 270.0) for *_, a, ln, t in pl) else 0
            for u in L.units(sym):
                x0, y0, x1, y1 = _bbox_rot(sym, u, rot)
                lab = _label_room(p, sym, u, rot, self)
                w = (x1 - x0) + lab['l'] + lab['r'] + 7.62
                h = (y1 - y0) + lab['t'] + lab['b'] + 7.62
                if x + w > right and x > margin_l:
                    x = margin_l; y += row_h; row_h = 0.0
                ax = snap(x + lab['l'] - x0)
                ay = snap(y + lab['t'] - y0 + 3.81)
                placements.append((p, u, ax, ay, rot))
                x += w
                row_h = max(row_h, h)
        if y + row_h > bottom:
            raise ValueError(f"sheet {sh.file} overflows {sh.paper}: needs {y + row_h:.0f} mm of {bottom:.0f}")
        pwr_n = 0
        for p, u, ax, ay, rot in placements:
            sym = self._sym(p)
            bx0, by0, bx1, by1 = _bbox_rot(sym, u, rot)
            ty = ay + by0 - 1.27
            props = [['property', Q('Reference'), Q(p.ref), ['at', ax + bx0, ty - 2.54, 0], ['effects', fnt(), ['justify', 'left']]],
                     ['property', Q('Value'), Q(p.value), ['at', ax + bx0, ty, 0], ['effects', fnt(), ['justify', 'left']]],
                     ['property', Q('Footprint'), Q(p.footprint), ['at', ax, ay, 0], ['effects', fnt(), 'hide']],
                     ['property', Q('Datasheet'), Q(p.fields.get('Datasheet', '~')), ['at', ax, ay, 0], ['effects', fnt(), 'hide']]]
            for k, v in p.fields.items():
                if k != 'Datasheet':
                    props.append(['property', Q(k), Q(v), ['at', ax, ay, 0], ['effects', fnt(), 'hide']])
            inst = ['symbol', ['lib_id', Q(p.lib_id)], ['at', ax, ay, rot], ['unit', u],
                    ['in_bom', 'yes'], ['on_board', 'yes'], ['dnp', 'yes' if p.dnp else 'no'],
                    ['uuid', uid(self.name, sh.file, p.ref, u)]] + props
            for (pu, num, nm, px, py, pa, ln, et) in L.pins(sym):
                if pu not in (0, u):
                    continue
                inst.append(['pin', Q(num), ['uuid', uid(self.name, sh.file, p.ref, 'pin', num)]])
            inst.append(['instances', ['project', Q(self.name), ['path', path, ['reference', Q(p.ref)], ['unit', u]]]])
            items.append(inst)
            # stubs and labels
            for (pu, num, nm, px, py, pa, ln, et) in L.pins(sym):
                if pu not in (0, u):
                    continue
                ox, oy, dx, dy = _pin_screen(px, py, pa, rot)
                X, Y = round(ax + ox, 4), round(ay + oy, 4)
                net = p.nets[num]
                if net is None:
                    items.append(['no_connect', ['at', X, Y], ['uuid', uid(self.name, sh.file, p.ref, num, 'nc')]])
                    continue
                ex, ey = round(X + dx * 2.54, 4), round(Y + dy * 2.54, 4)
                items.append(['wire', ['pts', ['xy', X, Y], ['xy', ex, ey]],
                              ['stroke', ['width', 0], ['type', 'default']],
                              ['uuid', uid(self.name, sh.file, p.ref, num, 'w')]])
                if net in POWER:
                    lib = self._psym(net); used.add(lib)
                    if net in POWER_DOWN:
                        prot = {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}[(dx, dy)]
                    else:
                        prot = {(0, -1): 0, (0, 1): 180, (1, 0): 270, (-1, 0): 90}[(dx, dy)]
                    pwr_n += 1
                    pref = f"#PWR{sh.file[:3].upper()}{pwr_n:03d}"
                    items.append(['symbol', ['lib_id', Q(lib)], ['at', ex, ey, prot], ['unit', 1],
                                  ['in_bom', 'yes'], ['on_board', 'yes'], ['dnp', 'no'],
                                  ['uuid', uid(self.name, sh.file, pref)],
                                  ['property', Q('Reference'), Q(pref), ['at', ex, ey, 0], ['effects', fnt(), 'hide']],
                                  ['property', Q('Value'), Q(net), ['at', ex, ey, 0], ['effects', fnt(1.0), 'hide']],
                                  ['property', Q('Footprint'), Q(''), ['at', ex, ey, 0], ['effects', fnt(), 'hide']],
                                  ['property', Q('Datasheet'), Q(''), ['at', ex, ey, 0], ['effects', fnt(), 'hide']],
                                  ['pin', Q('1'), ['uuid', uid(self.name, sh.file, pref, 'pin')]],
                                  ['instances', ['project', Q(self.name), ['path', path, ['reference', Q(pref)], ['unit', 1]]]]])
                else:
                    ang = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[(dx, dy)]
                    just = 'right' if ang in (180, 270) else 'left'
                    kind = 'global_label' if net in self.global_nets else 'label'
                    lab = [kind, Q(net)]
                    if kind == 'global_label':
                        lab.append(['shape', 'passive'])
                    lab += [['at', ex, ey, ang], ['fields_autoplaced'],
                            ['effects', fnt(), ['justify', just]],
                            ['uuid', uid(self.name, sh.file, p.ref, num, 'l')]]
                    if kind == 'global_label':
                        lab.append(['property', Q('Intersheetrefs'), Q('${INTERSHEET_REFS}'), ['at', ex, ey, 0],
                                    ['effects', fnt(), 'hide']])
                    items.append(lab)
        lib_symbols = ['lib_symbols'] + [self.symbols[k] for k in sorted(used)]
        body = ['kicad_sch', ['version', 20230121], ['generator', 'eeschema'], ['uuid', su],
                ['paper', Q(sh.paper)], self._title_block(sh.title, sh.name), lib_symbols]
        ny = ph - 30
        if sh.notes:
            body.append(['text', Q('\n\n'.join(sh.notes)), ['at', 25.4, ph - 38, 0],
                         ['effects', fnt(1.5), ['justify', 'left', 'top']], ['uuid', uid(self.name, sh.file, 'note')]])
        body += items
        return dump(body) + '\n'
