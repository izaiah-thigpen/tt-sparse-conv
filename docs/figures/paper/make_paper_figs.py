"""Figures for the SoutheastCon 2027 extended abstract.
Fig. 1: the MAC with its zero-skip (operand isolation) path.
Fig. 2: power saving against zero share, from power/results/power.csv.
Sized for one IEEE column (3.5 in) and readable in grayscale."""
import csv, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Polygon

INK, QUIET, GRID = '#0b0b0b', '#52514e', '#d9d8d4'
BLUE, ORANGE = '#2a78d6', '#eb6834'          # categorical slots 1 and 2
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7, 'axes.linewidth': 0.6,
                     'pdf.fonttype': 42, 'svg.fonttype': 'none'})


def box(ax, x, y, w, h, text, ec=INK, fs=6.6, lw=0.9, fc='white'):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                fc=fc, ec=ec, lw=lw, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center', fontsize=fs, color=INK, zorder=4, linespacing=1.15)


def wire(ax, pts, c=INK, lw=0.9, arrow=True, ls='-'):
    xs, ys = zip(*pts)
    ax.plot(xs[:-1] + (xs[-1],), ys, color=c, lw=lw, ls=ls, zorder=2, solid_capstyle='butt')
    if arrow:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        ax.annotate('', xy=(x1, y1), xytext=(x0 + 0.7 * (x1 - x0), y0 + 0.7 * (y1 - y0)),
                    arrowprops=dict(arrowstyle='-|>,head_length=0.35,head_width=0.18', color=c, lw=lw), zorder=2)


def dot(ax, x, y, c=INK):
    ax.add_patch(Circle((x, y), 0.06, color=c, zorder=5))


def fig_mac(path):
    fig, ax = plt.subplots(figsize=(3.5, 2.15))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6.15); ax.axis('off')
    # inputs
    ax.text(0.0, 4.55, 'pixel', fontsize=6.6, va='center')
    ax.text(0.0, 3.55, 'weight', fontsize=6.6, va='center')
    wire(ax, [(0.85, 4.55), (1.75, 4.55)], arrow=False)
    wire(ax, [(1.36, 3.55), (1.75, 3.55)], arrow=False)
    # stage 1: operand registers
    box(ax, 1.75, 3.1, 1.15, 1.9, 'input\nregs')
    ax.text(2.27, 5.25, 'stage 1', ha='center', fontsize=6, color=QUIET)
    # multiplier
    box(ax, 3.3, 3.45, 0.85, 1.2, '×', fs=10)
    wire(ax, [(2.9, 4.4), (3.3, 4.4)]); wire(ax, [(2.9, 3.7), (3.3, 3.7)])
    ax.text(4.55, 4.25, '17 b', fontsize=5.8, color=QUIET, ha='center')
    # adder and accumulator
    ax.add_patch(Circle((5.25, 4.05), 0.33, fc='white', ec=INK, lw=0.9, zorder=3))
    ax.text(5.25, 4.05, '+', ha='center', va='center', fontsize=9, zorder=4)
    wire(ax, [(4.15, 4.05), (4.92, 4.05)])
    box(ax, 5.95, 3.4, 1.0, 1.3, 'acc\n24 b')
    ax.text(6.45, 5.25, 'stage 2', ha='center', fontsize=6, color=QUIET)
    wire(ax, [(5.58, 4.05), (5.95, 4.05)])
    wire(ax, [(6.95, 4.05), (7.2, 4.05), (7.2, 5.55), (5.25, 5.55), (5.25, 4.38)])   # feedback
    # output stage
    box(ax, 7.55, 3.25, 1.35, 1.6, 'shift,\nclamp\n0..255')
    wire(ax, [(7.2, 4.05), (7.55, 4.05)], arrow=True)
    wire(ax, [(8.9, 4.05), (9.95, 4.05)])
    ax.text(9.95, 4.3, 'result', ha='right', fontsize=6.6)
    # zero detect on the incoming tap
    dot(ax, 1.47, 4.55); dot(ax, 1.62, 3.55)
    wire(ax, [(1.47, 4.55), (1.47, 2.05)], c=ORANGE)
    wire(ax, [(1.62, 3.55), (1.62, 2.05)], c=ORANGE)
    box(ax, 0.95, 1.15, 1.0, 0.9, 'zero?', ec=ORANGE, lw=1.1)
    # gate with gate_en
    wire(ax, [(1.95, 1.6), (2.55, 1.6)], c=ORANGE)
    box(ax, 2.55, 1.15, 0.95, 0.9, 'AND', ec=ORANGE, lw=1.1, fs=6)
    ax.text(3.15, 0.72, 'gate_en', ha='left', va='center', fontsize=5.8, color=QUIET)
    wire(ax, [(3.0, 0.55), (3.0, 1.15)], c=INK)
    # hold -> register enable (hold freezes operands and the accumulator)
    wire(ax, [(3.5, 1.6), (3.95, 1.6), (3.95, 2.6), (2.27, 2.6), (2.27, 3.1)], c=ORANGE)
    ax.text(3.0, 2.78, 'hold', fontsize=6.4, color=ORANGE, ha='center', weight='bold')
    wire(ax, [(3.95, 2.6), (6.45, 2.6), (6.45, 3.4)], c=ORANGE, ls=(0, (3, 1.5)))
    ax.text(4.15, 2.35, 'acc enable (next cycle)', fontsize=5.8, color=ORANGE, ha='left', va='center')
    # skip counter
    wire(ax, [(1.3, 1.15), (1.3, 0.3), (5.4, 0.3), (5.4, 1.15)], c=ORANGE)
    box(ax, 4.45, 1.15, 1.95, 0.9, 'skip count\n16 b', ec=INK, fs=6)
    ax.text(6.6, 1.6, 'zero taps, read\nover SPI', fontsize=5.8, color=QUIET, va='center', linespacing=1.1)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)


def fig_power(csv_path, path):
    rows = {r['condition']: r for r in csv.DictReader(open(csv_path))}
    idle_mac = float(rows['idle']['mac_uW'])
    xs, chip, mac = [], [], []
    for t in ('T0', 'T64', 'T128', 'T192', 'T230'):
        g, b = rows[t + '_gated'], rows[t + '_bypass']
        xs.append(100 * float(g['zero_share']))
        chip.append(100 * (1 - float(g['total_uW']) / float(b['total_uW'])))
        mg, mb = float(g['mac_uW']) - idle_mac, float(b['mac_uW']) - idle_mac
        mac.append(100 * (1 - mg / mb))
    fig, ax = plt.subplots(figsize=(3.5, 2.05))
    ax.plot(xs, mac, color=BLUE, lw=1.6, marker='o', ms=4, mec='white', mew=0.8, zorder=3)
    ax.plot(xs, chip, color=ORANGE, lw=1.6, marker='s', ms=4, mec='white', mew=0.8, ls=(0, (4, 1.6)), zorder=3)
    ax.text(xs[-1] - 1.5, mac[-1], f'MAC dynamic\npower ({mac[-1]:.0f}%)', ha='right', va='center', fontsize=6.6, color=INK)
    ax.text(xs[-1] - 1.5, chip[-1] + 6.5, f'whole chip ({chip[-1]:.1f}%)', ha='right', va='bottom', fontsize=6.6, color=INK)
    ax.set_xlim(0, 95); ax.set_ylim(0, 72)
    ax.set_xticks([0, 25, 50, 75, 90]); ax.set_yticks([0, 20, 40, 60])
    ax.set_xlabel('Share of zero pixels (%)', fontsize=7, color=INK)
    ax.set_ylabel('Power saving, gated\nvs. BYPASS (%)', fontsize=7, color=INK)
    ax.grid(axis='y', color=GRID, lw=0.5); ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=6.6, colors=QUIET, length=2.5, width=0.5)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return xs, mac, chip


if __name__ == '__main__':
    out = sys.argv[2] if len(sys.argv) > 2 else '.'
    fig_mac(out + '/fig1_mac')
    print(fig_power(sys.argv[1], out + '/fig2_power'))
