"""Draws the figures for docs/wafer_to_class.md.

Runs one wafer map through the exact integer model the chip implements
(test/refmodel.py) and the trained, quantized weights, and draws every stage.

    python docs/figures/make_figures.py --weights demo_data.npz --wafers synthetic.pkl

--weights: the quantized model (model/export_demo_data.py writes it).
--wafers:  a pickle in WM-811K's format (model/make_synthetic.py writes one).
The example is a generated Donut map, used because its full die grid can be
shown; the per-class strip uses the nine real WM-811K test maps in host/vectors.
"""
import argparse, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'test'))
sys.path.insert(0, os.path.join(ROOT, 'model'))
import refmodel as R

INK, QUIET, CHIP, BOARD, FAIL, PASS = '#1f2328', '#656d76', '#c2410c', '#2a6fdb', '#d1242f', '#cfe8d5'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.edgecolor': '#8c959f'})
HEAT = 'magma'


def density(m, size=32):
    """Same as model/prepare_data.py to_fail_grids(mode='density'), without torch."""
    m = np.asarray(m)
    fail = (m == 2).astype(np.float64)
    h, w = fail.shape
    out = np.zeros((size, size))
    for i in range(size):
        r0, r1 = (i * h) // size, -((-(i + 1) * h) // size)
        for j in range(size):
            c0, c1 = (j * w) // size, -((-(j + 1) * w) // size)
            out[i, j] = fail[r0:r1, c0:c1].mean()
    v = np.rint(out * 255)
    v[(out > 0) & (v < 1)] = 1
    return v.astype(np.uint8)


def label_of(value):
    flat = np.asarray(value, dtype=object).ravel()
    return str(flat[0]).strip() if flat.size else None


def strip(ax):
    ax.set_xticks([]); ax.set_yticks([])


def fig_dataset(m, x, path):
    """Die-level wafer map -> 32 x 32 density map."""
    m = np.asarray(m); h, w = m.shape
    fig = plt.figure(figsize=(13, 4.9))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1], wspace=0.28)
    cmap = ListedColormap(['#ffffff', PASS, FAIL])
    ax = fig.add_subplot(gs[0])
    ax.imshow(m, cmap=cmap, vmin=0, vmax=2, interpolation='nearest')
    for k in range(w + 1):
        ax.axvline(k - 0.5, color='#e6e9ec', lw=0.3)
    for k in range(h + 1):
        ax.axhline(k - 0.5, color='#e6e9ec', lw=0.3)
    strip(ax)
    ax.set_title(f'1. Test result per die ({h} x {w} dies)', loc='left', fontsize=11, color=INK)
    n_die, n_fail = int((m > 0).sum()), int((m == 2).sum())
    ax.text(0, -0.05, f'{n_die} dies, {n_fail} failed.\nStored as 0 = no die, 1 = pass, 2 = fail.',
            transform=ax.transAxes, va='top', fontsize=9, color=QUIET)
    ax.legend(handles=[Rectangle((0, 0), 1, 1, fc=PASS, ec='#8c959f'), Rectangle((0, 0), 1, 1, fc=FAIL)],
              labels=['pass (1)', 'fail (2)'], loc='lower right', fontsize=8, frameon=False, bbox_to_anchor=(1.0, -0.02))

    ax = fig.add_subplot(gs[1])
    ax.imshow(m, cmap=cmap, vmin=0, vmax=2, interpolation='nearest')
    for i in range(33):
        ax.axhline((i * h) / 32 - 0.5, color='#24292f', lw=0.35, alpha=0.6)
        ax.axvline((i * w) / 32 - 0.5, color='#24292f', lw=0.35, alpha=0.6)
    strip(ax)
    ax.set_title('2. Cut into a 32 x 32 grid of cells', loc='left', fontsize=11, color=INK)
    ax.text(0, -0.05, 'Wafers come in many die counts; every one\nbecomes the same 32 x 32 grid.',
            transform=ax.transAxes, va='top', fontsize=9, color=QUIET)

    ax = fig.add_subplot(gs[2])
    im = ax.imshow(x, cmap=HEAT, vmin=0, vmax=255, interpolation='nearest')
    strip(ax)
    ax.set_title('3. Share of failing dies per cell, x 255', loc='left', fontsize=11, color=INK)
    z = (x == 0).mean()
    ax.text(0, -0.05, f'This 32 x 32 map of bytes is the network input.\n{z:.0%} of cells are 0 (no failing die).',
            transform=ax.transAxes, va='top', fontsize=9, color=QUIET)
    cax = ax.inset_axes([1.03, 0, 0.05, 1]); cb = fig.colorbar(im, cax=cax); cb.set_ticks([0, 64, 128, 191, 255]); cb.ax.tick_params(labelsize=8)
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)


def tiles(ax, maps, cols, title, sub, vmax=None):
    vmax = vmax or max(int(maps.max()), 1)
    k, hh, ww = maps.shape
    rows = -(-k // cols); gap = 1
    canvas = np.full((rows * (hh + gap) - gap, cols * (ww + gap) - gap), np.nan)
    for i in range(k):
        r, c = divmod(i, cols)
        canvas[r * (hh + gap):r * (hh + gap) + hh, c * (ww + gap):c * (ww + gap) + ww] = maps[i]
    cm = matplotlib.colormaps[HEAT].copy(); cm.set_bad('white')
    ax.imshow(canvas, cmap=cm, vmin=0, vmax=vmax, interpolation='nearest')
    strip(ax)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title, fontsize=10.5, color=INK, pad=6)
    ax.text(0.5, -0.04, sub, transform=ax.transAxes, ha='center', va='top', fontsize=8.6, color=QUIET, linespacing=1.35)


def fig_layers(x, inter, logits, names, skips, path):
    c1, p1, c2 = inter['conv1_out'][0], inter['conv2_in'][0], inter['conv2_out'][0]
    p2 = R.maxpool2(inter['conv2_out'])[0]
    fig = plt.figure(figsize=(16, 5.6))
    gs = fig.add_gridspec(1, 7, width_ratios=[1, 1.25, 1.1, 1.05, 0.95, 0.6, 1.1], wspace=0.22)
    ax = fig.add_subplot(gs[0]); tiles(ax, x[None], 1, 'Input\n32 x 32', f'1 map\n{(x == 0).mean():.0%} zeros')
    ax = fig.add_subplot(gs[1]); tiles(ax, c1, 4, 'Conv 1  (chip)\n16 maps, 30 x 30',
                                       f'each pixel = 9 multiplies\n129,600 multiplies\n{skips[0]:.0%} have a zero: skipped')
    ax = fig.add_subplot(gs[2]); tiles(ax, p1, 4, 'Max pool  (board)\n16 maps, 15 x 15',
                                       f'keep the largest of\neach 2 x 2 block\n{(p1 == 0).mean():.0%} zeros')
    ax = fig.add_subplot(gs[3]); tiles(ax, c2, 4, 'Conv 2  (chip)\n16 maps, 13 x 13',
                                       f'each pixel = 144 multiplies\n389,376 multiplies\n{skips[1]:.0%} have a zero: skipped')
    ax = fig.add_subplot(gs[4]); tiles(ax, p2, 4, 'Max pool  (board)\n16 maps, 6 x 6', f'16 x 6 x 6\n= 576 numbers\n{(p2 == 0).mean():.0%} zeros')
    ax = fig.add_subplot(gs[5]); ax.axis('off')
    ax.annotate('', xy=(0.95, 0.5), xytext=(0.05, 0.5), xycoords='axes fraction',
                arrowprops=dict(arrowstyle='-|>', color=QUIET, lw=1.5))
    ax.text(0.5, 0.58, 'Dense\n(board)', ha='center', va='bottom', fontsize=10.5, color=INK, transform=ax.transAxes)
    ax.text(0.5, 0.42, '576 x 9\nweights', ha='center', va='top', fontsize=8.6, color=QUIET, transform=ax.transAxes)
    ax = fig.add_subplot(gs[6])
    best = int(np.argmax(logits))
    ys = np.arange(len(names))[::-1]
    cols = [CHIP if i == best else '#afb8c1' for i in range(len(names))]
    ax.barh(ys, logits, color=cols, height=0.65)
    ax.set_yticks(ys); ax.set_yticklabels(names, fontsize=9); ax.yaxis.tick_right()
    ax.axvline(0, color='#8c959f', lw=0.8)
    for s in ('top', 'left'):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis='x', labelsize=8)
    ax.set_title('9 scores, one per class', fontsize=10.5, color=INK, pad=6)
    ax.text(0.5, -0.12, f'highest score = answer: {names[best]}', transform=ax.transAxes, ha='center', va='top',
            fontsize=9.5, color=CHIP, weight='bold')
    fig.suptitle('One wafer map through the network.  Black = 0; each stage is scaled to its own brightest value.', x=0.125, ha='left', y=1.03, fontsize=12, color=INK)
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)


def fig_window(x, q, path):
    """One conv-1 output pixel: a 3 x 3 window times one kernel, on the MAC."""
    # the first kernel and window (scanning row by row) on the ring's edge that has
    # 3 to 5 zero pixels and a clearly positive output, so both effects show
    best = None
    for k in range(q['w1'].shape[0]):
        w = q['w1'][k, 0].astype(int); b = int(q['b1'][k]); sh = int(q['sh1'][k])
        for r in range(30):
            for c in range(30):
                win = x[r:r + 3, c:c + 3].astype(int)
                if 3 <= (win == 0).sum() <= 5 and R.output_value([win.ravel()], [w.ravel()], b, sh)[0] >= 40:
                    best = (k, r, c); break
            if best:
                break
        if best:
            break
    k, r, c = best
    w = q['w1'][k, 0].astype(int); b = int(q['b1'][k]); sh = int(q['sh1'][k])
    win = x[r:r + 3, c:c + 3].astype(int)
    out, acc, skips = R.output_value([win.ravel()], [w.ravel()], b, sh)
    fig = plt.figure(figsize=(13, 4.3))
    gs = fig.add_gridspec(1, 5, width_ratios=[1.1, 0.9, 0.9, 0.9, 1.25], wspace=0.35)
    ax = fig.add_subplot(gs[0])
    ax.imshow(x, cmap=HEAT, vmin=0, vmax=255, interpolation='nearest'); strip(ax)
    ax.add_patch(Rectangle((c - 0.5, r - 0.5), 3, 3, fill=False, ec='#3fb950', lw=2))
    ax.set_title('Input map: one 3 x 3 window', fontsize=10.5, color=INK)

    def grid(ax, vals, title, fmt, shade=None):
        ax.set_xlim(-0.5, 2.5); ax.set_ylim(2.5, -0.5); strip(ax); ax.set_aspect('equal')
        for i in range(3):
            for j in range(3):
                skip = shade is not None and shade[i, j]
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fc='#eaeef2' if skip else 'white', ec='#8c959f'))
                ax.text(j, i, fmt(vals[i, j]), ha='center', va='center', fontsize=11,
                        color=QUIET if skip else INK)
        ax.set_title(title, fontsize=10.5, color=INK)

    zero = (win == 0) | (w == 0)
    grid(fig.add_subplot(gs[1]), win, 'pixels', str, zero)
    grid(fig.add_subplot(gs[2]), w, f'x  weights (kernel {k})', str, zero)
    prod = win * w
    grid(fig.add_subplot(gs[3]), prod, '=  products', lambda v: str(v), zero)
    ax = fig.add_subplot(gs[4]); ax.axis('off')
    lines = [
        (f'{int(zero.sum())} of 9 taps have a zero (grey):', INK, 'bold'),
        ('the chip skips them; the sum is unchanged', QUIET, 'normal'),
        ('', INK, 'normal'),
        (f'bias {b:+d}', INK, 'normal'),
        (f'+ sum of products {int(prod.sum()):+d}', INK, 'normal'),
        (f'= accumulator {acc:+d}', INK, 'normal'),
        (f'shift right {sh} bits, clamp to 0..255', QUIET, 'normal'),
        (f'= output pixel {out}', CHIP, 'bold'),
    ]
    for i, (t, col, wt) in enumerate(lines):
        ax.text(0.0, 0.9 - i * 0.115, t, fontsize=10.5, color=col, weight=wt, transform=ax.transAxes)
    fig.suptitle('What the chip does for one output pixel of layer 1', x=0.125, ha='left', y=1.02, fontsize=12, color=INK)
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)
    return dict(kernel=k, window=(r, c), acc=acc, out=out, skips=skips)


def fig_classes(path, q, names):
    maps, labels = [], []
    for i in range(9):
        v = np.fromfile(os.path.join(ROOT, 'host', 'vectors', f'map_{i:02d}.bin'), dtype=np.uint8)
        maps.append(v[10:10 + 1024].reshape(32, 32))  # 10-byte header, then the map
    pred = R.run_network(np.stack(maps), q).argmax(1)
    truth = ['Center', 'Donut', 'Edge-Loc', 'Edge-Ring', 'Loc', 'Near-full', 'Random', 'Scratch', 'none']
    fig, axs = plt.subplots(1, 9, figsize=(16, 2.6))
    for i, ax in enumerate(axs):
        ax.imshow(maps[i], cmap=HEAT, vmin=0, vmax=255, interpolation='nearest'); strip(ax)
        ok = names[pred[i]] == truth[i]
        ax.set_title(truth[i], fontsize=10.5, color=INK)
        ax.text(0.5, -0.08, f'model: {names[pred[i]]}', transform=ax.transAxes, ha='center', va='top', fontsize=9,
                color=QUIET if ok else FAIL)
    fig.suptitle('The 9 classes: real WM-811K test maps after the 32 x 32 resize', x=0.125, ha='left', y=1.07, fontsize=12, color=INK)
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white'); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', required=True)
    ap.add_argument('--wafers', required=True)
    ap.add_argument('--index', type=int, default=0, help='which Donut map in --wafers')
    a = ap.parse_args()
    import pandas as pd
    q = dict(np.load(a.weights, allow_pickle=True))
    names = [str(n) for n in q['class_names']]
    df = pd.read_pickle(a.wafers)
    donuts = [m for m, f in zip(df.waferMap, df.failureType) if label_of(f) == 'Donut']
    m = np.asarray(donuts[a.index])
    x = density(m)
    logits, inter = R.run_network(x[None], q, return_intermediate=True)
    s1 = R.skip_counts(inter['conv1_in'], q['w1']); s2 = R.skip_counts(inter['conv2_in'], q['w2'])
    skips = (s1['skipped'] / s1['taps'], s2['skipped'] / s2['taps'])
    fig_dataset(m, x, os.path.join(HERE, 'wafer_to_input.png'))
    fig_layers(x, inter, logits[0], names, skips, os.path.join(HERE, 'layers.png'))
    info = fig_window(x, q, os.path.join(HERE, 'one_pixel.png'))
    fig_classes(os.path.join(HERE, 'classes.png'), q, names)
    print('predicted', names[int(np.argmax(logits))], 'skips', [round(s, 3) for s in skips], info,
          'logits', np.round(logits[0], 2).tolist(), 'shape', m.shape)


if __name__ == '__main__':
    main()
