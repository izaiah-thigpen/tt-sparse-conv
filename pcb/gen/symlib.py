"""Load schematic symbols as KiCad 7 trees.

Sources: KiCad 7 standard libraries (/usr/share/kicad/symbols), resolving
`extends`; and symbols embedded in KiCad 9 schematics (Tiny Tapeout's demo
board), converted to KiCad 7 syntax.
"""
import copy
import math
import os

from sexpr import Q, find, one, parse

STD = '/usr/share/kicad/symbols'
_cache = {}


def _lib(path):
    if path not in _cache:
        _cache[path] = parse(open(path).read())
    return _cache[path]


def _rename(sym, old, new):
    """Rename a symbol; its unit sub-symbols take the bare name (no 'Lib:' prefix)."""
    old_bare, new_bare = old.split(':')[-1], new.split(':')[-1]
    sym[1] = Q(new)
    for sub in find(sym, 'symbol'):
        name = sub[1].split(':')[-1]
        if name.startswith(old_bare + '_'):
            sub[1] = Q(new_bare + name[len(old_bare):])


def std(lib_id):
    """A standard-library symbol, flattened, named 'Lib:Name'."""
    lib, name = lib_id.split(':')
    root = _lib(os.path.join(STD, lib + '.kicad_sym'))
    syms = {s[1]: s for s in find(root, 'symbol')}
    s = copy.deepcopy(syms[name])
    ext = one(s, 'extends')
    if ext:
        parent = copy.deepcopy(syms[ext[1]])
        _rename(parent, ext[1], name)
        # child properties override the parent's
        props = {p[1]: p for p in find(s, 'property')}
        out = [c for c in parent if not (isinstance(c, list) and c[0] == 'property' and c[1] in props)]
        ins = next(i for i, c in enumerate(out) if isinstance(c, list) and c[0] == 'symbol')
        out[ins:ins] = list(props.values())
        s = out
    _rename(s, name, lib_id)
    return s


_DROP = {'exclude_from_sim', 'embedded_fonts', 'show_name', 'do_not_autoplace', 'duplicate_pin_numbers_are_jumpers'}


def _to_v7(node):
    if not isinstance(node, list):
        return node
    out = []
    for c in node:
        if isinstance(c, list) and c:
            if c[0] in _DROP:
                continue
            if c[0] in ('hide', 'bold', 'italic') and len(c) == 2:
                if c[1] == 'yes':
                    out.append(c[0])
                continue
            out.append(_to_v7(c))
        else:
            out.append(c)
    if out and out[0] == 'property':
        out = [c for c in out if not (isinstance(c, list) and c[0] == 'id')]
    return out


def embedded(sch_path, lib_id, new_id=None):
    """A symbol cached in a KiCad 9 schematic's lib_symbols, as KiCad 7."""
    root = _lib(sch_path)
    for s in find(one(root, 'lib_symbols'), 'symbol'):
        if s[1] == lib_id:
            s = _to_v7(copy.deepcopy(s))
            if new_id:
                _rename(s, lib_id, new_id)
            # drop KiCad-9-only properties KiCad 7 treats as user fields anyway
            return [c for c in s if not (isinstance(c, list) and c[0] == 'property'
                                         and c[1] in ('Component Class', 'ki_locked'))]
    raise KeyError(lib_id)


def pins(sym):
    """[(unit, number, name, x, y, angle, length, etype)] in symbol coordinates (y up)."""
    out = []
    for sub in find(sym, 'symbol'):
        parts = sub[1].rsplit('_', 2)
        unit = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else 0
        for p in find(sub, 'pin'):
            at = one(p, 'at')
            out.append((unit, str(one(p, 'number')[1]), str(one(p, 'name')[1]),
                        float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                        float(one(p, 'length')[1]), p[1]))
    return out


def units(sym):
    return sorted({u for u, *_ in pins(sym) if u > 0}) or [1]


def bbox(sym, unit):
    """Rough body+pin extent for one unit: (xmin, ymin, xmax, ymax) in schematic coords (y down)."""
    xs, ys = [0.0], [0.0]
    for u, n, nm, x, y, a, ln, t in pins(sym):
        if u in (0, unit):
            xs.append(x); ys.append(-y)
    for sub in find(sym, 'symbol'):
        parts = sub[1].rsplit('_', 2)
        u = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else 0
        if u not in (0, unit):
            continue
        for r in find(sub, 'rectangle'):
            for k in ('start', 'end'):
                pt = one(r, k); xs.append(float(pt[1])); ys.append(-float(pt[2]))
        for pl in find(sub, 'polyline'):
            for pt in find(one(pl, 'pts'), 'xy'):
                xs.append(float(pt[1])); ys.append(-float(pt[2]))
    return min(xs), min(ys), max(xs), max(ys)


def from_lib(path, name, lib_id):
    """A symbol from a project .kicad_sym library (no extends), named lib_id."""
    root = _lib(path)
    for sym in find(root, 'symbol'):
        if sym[1] == name:
            sym = copy.deepcopy(sym)
            _rename(sym, name, lib_id)
            return sym
    raise KeyError(name)
