import csv, pcbnew, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
b = pcbnew.LoadBoard('placed.kicad_pcb')
grp = {r['ref']: r['group'] for r in csv.DictReader(open('../../placement/placement.csv'))}
cols = {'Fixed parts': '#555555', 'USB, 3.3 V, BOOT, SWD, logic analyzer': '#2a6fdb', 'RP2350B block': '#c2410c',
        'PMODs, PROJ RESET, control pull-ups': '#15803d', 'Analog pull-downs': '#7c3aed', 'Power monitor': '#be123c'}
fig, ax = plt.subplots(figsize=(13, 11.5))
ax.add_patch(Rectangle((100, 100), 100, 85, fill=False, lw=2, ec='black'))
ax.add_patch(Rectangle((120.225, 113.3), 50, 50, fill=True, fc='#f3f0e6', ec='#9a8f6a', ls='--', lw=1.2, zorder=0))
ax.text(145.2, 164.6, 'breakout board sits above this 50 x 50 mm area (parts under it < 4 mm tall)', ha='center', va='top', fontsize=8, color='#7a6f4a')
for fp in b.GetFootprints():
    r = fp.GetReference(); c = cols[grp[r]]
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    for i in range(cy.OutlineCount()):
        bb = cy.Outline(i).BBox()
        x0, y0, x1, y1 = [pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())]
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True, fc=c, alpha=0.13, ec=c, lw=0.8))
    for p in fp.Pads():
        q = p.GetPosition(); s = p.GetBoundingBox()
        ax.add_patch(Rectangle((pcbnew.ToMM(s.GetLeft()), pcbnew.ToMM(s.GetTop())), pcbnew.ToMM(s.GetWidth()), pcbnew.ToMM(s.GetHeight()), fc=c, ec='none', alpha=0.55))
    pos = fp.GetPosition(); x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    if r == 'J3':
        ax.text(126.2, 124.5, 'J3 60-pin', fontsize=8, ha='center', color=c, weight='bold')
        ax.text(164.2, 142.5, 'J3 50-pin', fontsize=8, ha='center', color=c, weight='bold')
        continue
    small = fp.GetArea() < pcbnew.FromMM(1) ** 2 * 6 if hasattr(fp, 'GetArea') else False
    ax.text(x, y, r, fontsize=5.2 if r[0] in 'RCD' and len(r) > 1 and r not in ('D3','D4','D5') else 7.5, ha='center', va='center', color='black', weight='bold' if r[0] in 'UJHS' or r in('Y1','L1','F1','FB1','TP1','TP2','TP3') else 'normal')
for k, c in cols.items():
    ax.plot([], [], 's', color=c, label=k, ms=9)
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.03), ncol=3, fontsize=9, frameon=False)
ax.set_xlim(98, 202); ax.set_ylim(196, 96); ax.set_aspect('equal')
ax.set_xticks(range(100, 201, 10)); ax.set_yticks(range(100, 186, 10)); ax.grid(alpha=0.25)
ax.set_title('Host board placement, top view (KiCad coordinates in mm; Y grows downward)', fontsize=12)
plt.tight_layout(); plt.savefig('../../placement/placement-preview.png', dpi=130)
