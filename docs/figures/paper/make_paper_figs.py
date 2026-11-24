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


def fig_input(pkl, path):
    """Fig. 3 (full paper): die-level map and the 32 x 32 network input, one column wide."""
    import numpy as np, pandas as pd
    from matplotlib.colors import ListedColormap
    sys.path.insert(0, '/home/claude/tt-sparse-conv/docs/figures')
    from make_figures import density, label_of
    df = pd.read_pickle(pkl)
    m = np.asarray([w for w, f in zip(df.waferMap, df.failureType) if label_of(f) == 'Donut'][0])
    x = density(m)
    fig, axs = plt.subplots(1, 2, figsize=(3.5, 1.95), gridspec_kw={'wspace': 0.12})
    axs[0].imshow(m, cmap=ListedColormap(['#ffffff', '#c9c8c3', '#0b0b0b']), vmin=0, vmax=2, interpolation='nearest')
    axs[1].imshow(x, cmap='gray_r', vmin=0, vmax=255, interpolation='nearest')
    h, w = m.shape
    axs[0].set_title(f'(a) die results, {h} x {w}', fontsize=6.6, color=INK, pad=3)
    axs[1].set_title('(b) network input, 32 x 32', fontsize=6.6, color=INK, pad=3)
    for ax in axs:
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.5); s.set_color('#8c959f')
    axs[0].text(0.5, -0.06, 'white: no die\ngray: pass, black: fail', transform=axs[0].transAxes, ha='center', va='top', fontsize=5.8, color=QUIET, linespacing=1.15)
    axs[1].text(0.5, -0.06, f'darker: more failing dies\n{(x == 0).mean():.0%} of cells are zero', transform=axs[1].transAxes, ha='center', va='top', fontsize=5.8, color=QUIET, linespacing=1.15)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return m.shape, int((m > 0).sum()), float((x == 0).mean())


def fig_breakdown(csv_path, path):
    """Full paper: chip power split into the clock floor, flip-flop data switching and logic."""
    import numpy as np
    rows = {r['condition']: r for r in csv.DictReader(open(csv_path))}
    idle = float(rows['idle']['sequential_uW'])
    labels, floor, ff, comb = [], [], [], []
    for t, z in (('T0', '0'), ('T64', '25'), ('T128', '50'), ('T192', '75'), ('T230', '90')):
        for mode, tag in (('bypass', 'B'), ('gated', 'G')):
            r = rows[f'{t}_{mode}']
            labels.append((z, tag))
            floor.append(idle); ff.append(float(r['sequential_uW']) - idle); comb.append(float(r['combinational_uW']))
    x = []
    for i in range(5):
        x += [i * 2.6, i * 2.6 + 1.05]
    x = np.array(x)
    fig, ax = plt.subplots(figsize=(3.5, 2.15))
    c_floor, c_ff, c_comb = '#c9c8c3', BLUE, ORANGE
    ax.bar(x, floor, 0.95, color=c_floor, edgecolor='white', linewidth=0.6, label='clock floor (idle flip-flops)')
    ax.bar(x, ff, 0.95, bottom=floor, color=c_ff, edgecolor='white', linewidth=0.6, label='flip-flop data switching')
    ax.bar(x, comb, 0.95, bottom=np.array(floor) + np.array(ff), color=c_comb, edgecolor='white', linewidth=0.6, label='combinational logic')
    for xi, (z, tag) in zip(x, labels):
        ax.text(xi, -40, tag, ha='center', va='top', fontsize=5.8, color=QUIET)
    for i, z in enumerate(('0', '25', '50', '75', '90')):
        ax.text(i * 2.6 + 0.52, -120, z + '%', ha='center', va='top', fontsize=6.6, color=INK)
    ax.text(5 * 2.6 - 0.3, -120, 'zeros', ha='left', va='top', fontsize=6.6, color=QUIET)
    ax.set_xticks([]); ax.set_xlim(-0.8, 12.6); ax.set_ylim(0, 1150)
    ax.set_ylabel('Chip power (µW)', fontsize=7, color=INK)
    ax.grid(axis='y', color=GRID, lw=0.5); ax.set_axisbelow(True)
    for s in ('top', 'right', 'bottom'):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=6.6, colors=QUIET, length=2.5, width=0.5)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.2), ncol=2, fontsize=5.8, frameon=False, handlelength=1.2, columnspacing=1.0)
    ax.text(0.0, -0.2, 'B = BYPASS, G = gated', transform=ax.transAxes, fontsize=5.8, color=QUIET)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)


def fig_classes(npz, vectors_dir, path):
    """Full paper: the nine classes (real WM-811K test maps), 3 x 3, with the integer model's answer."""
    import numpy as np, os
    sys.path.insert(0, '/home/claude/tt-sparse-conv/test')
    import refmodel as R
    q = dict(np.load(npz, allow_pickle=True))
    names = [str(n) for n in q['class_names']]
    maps = [np.fromfile(os.path.join(vectors_dir, f'map_{i:02d}.bin'), dtype=np.uint8)[10:10 + 1024].reshape(32, 32) for i in range(9)]
    pred = R.run_network(np.stack(maps), q).argmax(1)
    truth = ['Center', 'Donut', 'Edge-Loc', 'Edge-Ring', 'Loc', 'Near-full', 'Random', 'Scratch', 'none']
    fig, axs = plt.subplots(3, 3, figsize=(3.5, 3.75), gridspec_kw={'wspace': 0.06, 'hspace': 0.42})
    right = 0
    for i, ax in enumerate(axs.flat):
        ax.imshow(maps[i], cmap='gray_r', vmin=0, vmax=255, interpolation='nearest')
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.5); s.set_color('#8c959f')
        ok = names[pred[i]] == truth[i]; right += ok
        ax.set_title(truth[i], fontsize=6.6, color=INK, pad=2)
        ax.text(0.5, -0.04, ('✓ ' if ok else '✗ ') + names[pred[i]], transform=ax.transAxes, ha='center', va='top',
                fontsize=5.8, color=INK if ok else ORANGE, weight='normal' if ok else 'bold')
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return right


def fig_flow(path):
    """Full paper: the open-source design and verification flow."""
    fig, ax = plt.subplots(figsize=(3.5, 2.0))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6.0); ax.axis('off')
    rows = [
        (5.0, [('Training', 'PyTorch, WM-811K'), ('Quantization', '8-bit integers'), ('Integer model', 'Python, bit-exact')]),
        (3.0, [('RTL', 'SystemVerilog'), ('Simulation', 'cocotb + Icarus'), ('Layout', 'LibreLane (OpenROAD)')]),
        (1.0, [('Signoff', 'DRC, LVS, precheck'), ('Power analysis', 'VCD into OpenSTA'), ('Fabrication', 'SKY130, Tiny Tapeout')]),
    ]
    xs = [0.1, 3.5, 6.9]
    for y, items in rows:
        for x, (name, sub) in zip(xs, items):
            box(ax, x, y - 0.6, 3.0, 1.2, '', ec=INK, lw=0.8)
            ax.text(x + 1.5, y + 0.2, name, ha='center', va='center', fontsize=6.4, color=INK, zorder=5, weight='bold')
            ax.text(x + 1.5, y - 0.27, sub, ha='center', va='center', fontsize=5.2, color=QUIET, zorder=5)
        for x0 in xs[:2]:
            wire(ax, [(x0 + 3.0, y), (x0 + 3.4, y)], lw=0.8)
    wire(ax, [(8.4, 4.4), (8.4, 4.0), (1.6, 4.0), (1.6, 3.6)], lw=0.8)
    wire(ax, [(8.4, 2.4), (8.4, 2.0), (1.6, 2.0), (1.6, 1.6)], lw=0.8)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)


def fig_pixel(pkl, npz, path):
    """Full paper: one layer-1 output pixel computed by the MAC, with real weights and a real window."""
    import numpy as np, pandas as pd
    from matplotlib.patches import Rectangle
    sys.path.insert(0, '/home/claude/tt-sparse-conv/docs/figures'); sys.path.insert(0, '/home/claude/tt-sparse-conv/test')
    from make_figures import density, label_of
    import refmodel as R
    q = dict(np.load(npz, allow_pickle=True))
    df = pd.read_pickle(pkl)
    m = np.asarray([w for w, f in zip(df.waferMap, df.failureType) if label_of(f) == 'Donut'][0])
    x = density(m)
    best = None
    for k in range(q['w1'].shape[0]):
        w = q['w1'][k, 0].astype(int); b = int(q['b1'][k]); sh = int(q['sh1'][k])
        for r in range(30):
            for c in range(30):
                win = x[r:r + 3, c:c + 3].astype(int)
                if 3 <= (win == 0).sum() <= 5 and R.output_value([win.ravel()], [w.ravel()], b, sh)[0] >= 40:
                    best = (k, r, c); break
            if best: break
        if best: break
    k, r, c = best
    w = q['w1'][k, 0].astype(int); b = int(q['b1'][k]); sh = int(q['sh1'][k])
    win = x[r:r + 3, c:c + 3].astype(int)
    out, acc, skips = R.output_value([win.ravel()], [w.ravel()], b, sh)
    zero = (win == 0) | (w == 0)
    fig, axs = plt.subplots(1, 3, figsize=(3.5, 1.25), gridspec_kw={'wspace': 0.12})
    for ax, vals, title in zip(axs, (win, w, win * w), ('pixels', '× weights', '= products')):
        ax.set_xlim(-0.5, 2.5); ax.set_ylim(2.5, -0.5); ax.set_aspect('equal'); ax.axis('off')
        for i in range(3):
            for j in range(3):
                sk = zero[i, j]
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fc='#e8e7e3' if sk else 'white', ec='#8c959f', lw=0.5))
                ax.text(j, i, str(vals[i, j]), ha='center', va='center', fontsize=6.4, color=QUIET if sk else INK)
        ax.set_title(title, fontsize=6.4, color=INK, pad=2)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return dict(kernel=k, acc=acc, out=out, shift=sh, bias=b, zeros=int(zero.sum()))


def fig_board(path):
    """Full paper: host board for the silicon measurement."""
    fig, ax = plt.subplots(figsize=(3.5, 1.9))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5.4); ax.axis('off')
    box(ax, 0.1, 3.2, 1.6, 1.4, 'USB-C\n5 V', fs=6)
    box(ax, 2.3, 2.6, 2.4, 2.6, 'RP2350B\nmicro-\ncontroller', fs=6.2)
    box(ax, 6.4, 2.6, 3.4, 2.6, 'breakout board\nwith the chip', fs=6.2)
    box(ax, 2.3, 0.15, 2.4, 1.6, 'INA228\nmonitor', ec=ORANGE, lw=1.1, fs=6.2)
    box(ax, 5.4, 0.15, 2.0, 1.6, 'shunt\n0.5 + 5 Ω', ec=ORANGE, lw=1.1, fs=6)
    wire(ax, [(1.7, 3.9), (2.3, 3.9)], lw=0.8)
    wire(ax, [(4.7, 4.3), (6.4, 4.3)], lw=0.8); wire(ax, [(6.4, 3.6), (4.7, 3.6)], lw=0.8)
    ax.text(5.55, 4.45, 'SPI, clock', fontsize=5.4, color=QUIET, ha='center')
    ax.text(5.55, 3.3, 'outputs', fontsize=5.4, color=QUIET, ha='center')
    wire(ax, [(3.5, 1.75), (3.5, 2.6)], c=ORANGE, lw=0.8)
    ax.text(3.65, 2.15, 'I²C', fontsize=5.4, color=ORANGE, va='center')
    wire(ax, [(7.4, 0.95), (8.6, 0.95), (8.6, 2.6)], c=ORANGE, lw=0.9)
    ax.text(8.75, 1.55, '1.8 V\ncore', fontsize=5.4, color=ORANGE, va='center', linespacing=1.0)
    wire(ax, [(4.7, 0.95), (5.4, 0.95)], c=ORANGE, lw=0.8, arrow=False)
    ax.text(5.05, 1.95, 'Kelvin\nsense', fontsize=5.4, color=ORANGE, ha='center', linespacing=1.0)
    fig.savefig(path + '.png', dpi=600, bbox_inches='tight', facecolor='white')
    fig.savefig(path + '.pdf', bbox_inches='tight', facecolor='white')
    plt.close(fig)
