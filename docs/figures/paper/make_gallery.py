"""Gallery of real WM-811K test wafers (from model/export_real_wafers.py): 6 per class, original die grids."""
import sys, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
npz = sys.argv[1] if len(sys.argv) > 1 else 'model/real_wafers.npz'
out = sys.argv[2] if len(sys.argv) > 2 else 'docs/figures/paper/real_wafer_gallery'
d = np.load(npz, allow_pickle=True)
classes = ['Center', 'Donut', 'Edge-Loc', 'Edge-Ring', 'Loc', 'Near-full', 'Random', 'Scratch', 'none']
N = 6
cmap = ListedColormap(['#ffffff', '#c9c8c3', '#0b0b0b'])
fig, axs = plt.subplots(len(classes), N, figsize=(7.5, 11.2), gridspec_kw={'wspace': 0.08, 'hspace': 0.42})
for r, c in enumerate(classes):
    idx = [i for i in range(len(d['labels'])) if d['labels'][i] == c][:N]
    for j, ax in enumerate(axs[r]):
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.5); s.set_color('#8c959f')
        if j >= len(idx):
            ax.axis('off'); continue
        i = idx[j]; m = np.asarray(d['wafer_maps'][i])
        ax.imshow(m, cmap=cmap, vmin=0, vmax=2, interpolation='nearest', aspect='auto')
        ax.set_title(f"{d['lots'][i]} #{int(d['wafer_index'][i])}  {m.shape[0]}×{m.shape[1]}", fontsize=5.6, color='#57606a', pad=2)
    axs[r][0].set_ylabel(c, fontsize=8.5, color='#1f2328', rotation=0, ha='right', va='center', labelpad=8)
fig.suptitle('Real WM-811K test wafers (lots held out of training), 6 per class\nwhite: no die   gray: pass   black: fail', fontsize=9, color='#1f2328', y=0.935)
fig.savefig(out + '.png', dpi=200, bbox_inches='tight', facecolor='white')
fig.savefig(out + '.pdf', bbox_inches='tight', facecolor='white')
print('ok')
