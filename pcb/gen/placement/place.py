"""Placement for the host board: demo-board positions shifted onto our board,
plus the parts the demo board does not have. Writes placed.kicad_pcb, checks
courtyard overlaps, board-edge fit and the breakout keep-in, and prints a table."""
import os, sys, csv
import pcbnew
from build import build, HERE

# Board: 100 x 85 mm, top-left corner at (100, 100)
X0, Y0, W, H = 100.0, 100.0, 100.0, 85.0
# Demo board -> our board shift (demo J5 breakout at 93.225, 46.3)
DX, DY = 33.0, 87.5


def d(x, y):
    return round(x + DX, 3), round(y + DY, 3)


P = {}  # ref -> (x, y, rot)
# ---- copied from the Tiny Tapeout demo board (same parts, same jobs) ----
demo = {
    'J3': (93.225, 46.3, 0),            # breakout socket (demo J5)
    'U2': (110.3175, 63.535, 0),        # RP2350B (demo U6)
    'U3': (112.2, 45.4, 180),           # flash (U7)
    'L1': (113.95, 53.1, 0),
    'Y1': (110.1, 74.8, 0),
    'C22': (107.5, 75.32, 90),          # XIN 14 pF (C30)
    'C23': (113.0875, 73.235, -90),     # XOUT 14 pF (C32)
    'R7': (111.4875, 72.435, 0),        # 1k XOUT (R43)
    'R6': (116.6, 55.78, -90),          # 33R AVDD (R45)
    'C17': (116.6, 57.68, -90),         # 4.7u AVDD (C45)
    'C16': (114.0, 56.5, 0),            # 4.7u VREG_VIN (C46)
    'C21': (114.0, 55.0, 0),            # 4.7u +1V1 (C47)
    'C20': (111.4875, 70.735, -90),     # 4.7u +1V1 (C34)
    'C18': (102.4875, 63.335, 180),     # 100n +1V1 (C33)
    'C19': (118.4875, 63.035, 0),       # 100n +1V1 (C35)
    'C6': (106.7, 55.7, 90), 'C7': (116.5, 68.7, -90), 'C8': (107.4, 70.735, -90),
    'C9': (117.6, 58.6, 90), 'C10': (118.4875, 64.035, 0), 'C11': (102.4875, 61.335, 180),
    'C12': (110.3, 54.8, 90), 'C13': (109.4, 70.735, -90), 'C14': (101.771, 65.626787, 180),
    'C15': (135.35, 57.1, 90),
    'C24': (106.7, 47.0, 90),           # flash 100n (C31)
    'R8': (117.5, 45.165, -90),      # 10k QSPI_SS pull-up (R42)
    'R11': (110.7, 51.4, -90), 'R12': (111.75, 51.4, -90),   # USB 27R (R40, R41)
    'R19': (95.8, 67.1, 180),           # PROJ_CLK 33R, where the demo has JP1
    # USB and 3.3 V
    'J1': (143.21, 15.0, 180),
    'R1': (147.1, 22.41, -90), 'R2': (139.5, 22.69, -90),
    'D1': (141.645, 21.8, 0), 'D2': (144.645, 21.8, 180),
    'R3': (136.61, 15.5, 90), 'C1': (135.11, 15.525, 90),
    'F1': (137.8, 35.9, -90), 'FB1': (140.3, 36.4, 0),
    'C3': (140.3, 37.9, 180), 'C2': (140.25, 39.65, 180),
    'U1': (138.65, 44.25, 180),
    'C4': (131.5, 26.7, 90), 'C5': (130.0, 27.2, 90),
    'R4': (144.0, 43.2, -90), 'D3': (145.2, 44.4, 90),
    'R5': (73.9, 28.5, 90), 'D4': (73.8, 25.91, -90),
    'SW1': (147.0, 35.5, 90), 'R9': (148.1, 29.4, 90),
    'R13': (70.4, 57.41, 90), 'D5': (70.0, 54.91, -90),
    'SW2': (70.7, 70.0, 90),            # RESET, where the demo has its clock button
    'SW3': (70.7, 83.0, -90),           # PROJ RESET
    'R17': (78.8, 86.8, 90),
    'R14': (147.75, 73.6, -90), 'R15': (147.75, 76.13, -90), 'R16': (147.75, 71.07, 90),
    # PMODs and their capacitors
    'J4': (92.7, 93.0, 90), 'J5': (115.56, 93.0, 90), 'J6': (138.42, 93.0, 90),
    'C25': (80.475, 90.19, 0), 'C26': (80.7, 89.0, 180),
    'C27': (101.62, 90.7, 180), 'C28': (101.395, 89.5, 0),
    'C29': (126.3, 90.7, 0), 'C30': (126.525, 89.49, 180),
}
for r, (x, y, a) in demo.items():
    P[r] = (*d(x, y), a)

# ---- parts the demo board does not have ----
P.update({
    'H1': (104.0, 104.0, 0), 'H2': (196.0, 104.0, 0), 'H3': (104.0, 181.0, 0), 'H4': (196.0, 181.0, 0),
    'R10': (108.5, 157.5, 90),          # RUN pull-up, beside RESET
    'R18': (110.0, 170.5, 90),          # PROJ_RST_N pull-up
    'TP1': (117.5, 167.0, 0),           # PROJ_CLK test point, outside the breakout
    'J2': (192.0, 125.0, 0),            # SWD
    'J7': (189.0, 150.0, 0),            # logic analyzer
    # power monitor, above the breakout
    'J8': (136.0, 110.5, 90),
    'R42': (147.0, 108.0, 0), 'R43': (150.45, 108.0, 0),
    'J9': (149.5, 103.5, 90),
    'TP2': (143.0, 103.5, 0), 'TP3': (157.5, 103.0, 0),
    'U4': (158.0, 108.0, 180),
    'C31': (157.5, 105.2, 0), 'C32': (161.0, 105.2, 0),
    'R44': (163.0, 107.0, 0), 'R45': (163.0, 108.1, 0), 'R46': (163.0, 109.2, 0),
})
# 10 Mohm pull-downs on AN0..AN21, two columns beside the 60-pin connector's analog row
for i in range(22):
    col, row = divmod(i, 11)
    P['R%d' % (20 + i)] = (130.8 + 2.6 * col, 127.0 + 1.25 * row, 0)

TALL = {'J1', 'J2', 'J4', 'J5', 'J6', 'J7', 'J8', 'J9', 'SW1', 'SW2', 'SW3', 'H1', 'H2', 'H3', 'H4', 'TP1', 'TP2', 'TP3'}
OVERHANG = {'J1', 'J4', 'J5', 'J6'}     # meant to hang over the board edge
ZONE = (120.225, 113.3, 170.225, 163.3)  # breakout board footprint above our board


def apply(board, fps):
    for r, fp in fps.items():
        x, y, a = P[r]
        fp.SetOrientationDegrees(0)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        fp.SetOrientationDegrees(a)
    # outline
    for (xa, ya, xb, yb) in [(X0, Y0, X0 + W, Y0), (X0 + W, Y0, X0 + W, Y0 + H),
                             (X0 + W, Y0 + H, X0, Y0 + H), (X0, Y0 + H, X0, Y0)]:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(xa), pcbnew.FromMM(ya)))
        s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(xb), pcbnew.FromMM(yb)))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)
    z = pcbnew.PCB_SHAPE(board); z.SetShape(pcbnew.SHAPE_T_RECT)
    z.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ZONE[0]), pcbnew.FromMM(ZONE[1])))
    z.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(ZONE[2]), pcbnew.FromMM(ZONE[3])))
    z.SetLayer(pcbnew.User_1); z.SetWidth(pcbnew.FromMM(0.15)); board.Add(z)


def setup(board):
    mm = pcbnew.FromMM
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.m_MinClearance = mm(0.1); ds.m_TrackMinWidth = mm(0.1); ds.m_ViasMinSize = mm(0.45)
    ds.m_MinThroughDrill = mm(0.2); ds.m_ViasMinAnnularWidth = mm(0.1); ds.m_HoleClearance = mm(0.25)
    ds.m_HoleToHoleMin = mm(0.25); ds.m_CopperEdgeClearance = mm(0.5)
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(mm(0.15)); nc.SetTrackWidth(mm(0.2)); nc.SetViaDiameter(mm(0.6)); nc.SetViaDrill(mm(0.3))
    tw = ds.m_TrackWidthList; tw.clear(); tw.append(0)
    for w in (0.15, 0.2, 0.3, 0.5):
        tw.append(mm(w))
    vl = ds.m_ViasDimensionsList; vl.clear(); vl.append(pcbnew.VIA_DIMENSION(0, 0))
    for dia, drill in ((0.6, 0.3), (0.45, 0.2)):
        vl.append(pcbnew.VIA_DIMENSION(mm(dia), mm(drill)))


def crt(fp):
    c = fp.GetCourtyard(pcbnew.F_CrtYd)
    b = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False, False)
    return [pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom())]


def check(fps):
    bad = 0
    box = {r: crt(fp) for r, fp in fps.items()}
    rs = sorted(box)
    # J3 courtyards are two separate connectors; use them as two boxes
    j3 = fps['J3']
    polys = j3.GetCourtyard(pcbnew.F_CrtYd)
    j3boxes = []
    for i in range(polys.OutlineCount()):
        b = polys.Outline(i).BBox()
        j3boxes.append([pcbnew.ToMM(v) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom())])
    def boxes(r):
        return j3boxes if r == 'J3' else [box[r]]
    for i, a in enumerate(rs):
        for b in rs[i + 1:]:
            for p in boxes(a):
                for q in boxes(b):
                    if p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3]:
                        print('OVERLAP', a, b, [round(v, 2) for v in p], [round(v, 2) for v in q]); bad += 1
    for r in rs:
        if r in OVERHANG:
            continue
        for p in boxes(r):
            if p[0] < X0 - 0.01 or p[1] < Y0 - 0.01 or p[2] > X0 + W + 0.01 or p[3] > Y0 + H + 0.01:
                print('OFF BOARD', r, [round(v, 2) for v in p]); bad += 1
        if r in TALL:
            p = box[r]
            if p[0] < ZONE[2] and ZONE[0] < p[2] and p[1] < ZONE[3] and ZONE[1] < p[3]:
                print('TALL PART UNDER BREAKOUT', r); bad += 1
    print('placement check:', 'PASS' if not bad else '%d problem(s)' % bad)
    return bad


if __name__ == '__main__':
    board, fps, _ = build()
    missing = set(fps) - set(P)
    extra = set(P) - set(fps)
    assert not missing and not extra, (missing, extra)
    apply(board, fps)
    bad = check(fps)
    setup(board)
    board.Save(os.path.join(HERE, 'placed.kicad_pcb'))
    with open(os.path.join(HERE, 'placement.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['ref', 'value', 'x_mm', 'y_mm', 'rotation_deg'])
        def key(r):
            p = r.rstrip('0123456789'); return (p, int(r[len(p):]))
        for r in sorted(P, key=key):
            x, y, a = P[r]
            w.writerow([r, fps[r].GetValue(), x, y, a])
    sys.exit(1 if bad else 0)
