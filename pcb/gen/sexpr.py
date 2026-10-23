"""S-expression read/write for KiCad files, keeping track of quoted strings."""
import re


class Q(str):
    """A string that was (or must be) written in double quotes."""


_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse(text):
    stack, cur = [], []
    for t in _TOK.findall(text):
        if t == '(':
            stack.append(cur)
            cur = []
        elif t == ')':
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif t.startswith('"'):
            cur.append(Q(bytes(t[1:-1], 'utf-8').decode('unicode_escape') if '\\' in t else t[1:-1]))
        else:
            cur.append(t)
    return cur[0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(a, float):
        s = f"{a:.4f}".rstrip('0').rstrip('.')
        return '0' if s in ('-0', '') else s
    return str(a)


def dump(node, indent=0):
    """Serialize, keeping child order. Short all-atom or shallow lists stay on one line."""
    if not isinstance(node, list):
        return _atom(node)
    flat = all(not isinstance(c, list) for c in node)
    shallow = len(node) <= 4 and all(not isinstance(c, list) or all(not isinstance(x, list) for x in c) for c in node)
    if flat or shallow:
        return '(' + ' '.join(dump(c) for c in node) + ')'
    pad = '  ' * (indent + 1)
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        i += 1
    out = '(' + ' '.join(_atom(c) for c in node[:i])
    for c in node[i:]:
        out += '\n' + pad + (dump(c, indent + 1) if isinstance(c, list) else _atom(c))
    return out + '\n' + '  ' * indent + ')'


def find(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def one(node, name):
    r = find(node, name)
    return r[0] if r else None
