"""Bundle a small test set and the quantized model into one file for the board.

    python export_demo_data.py --data data/wm811k_32_density.npz \
        --run runs/d_k16_all --out ../pynq/demo_data.npz

The file holds up to --per-class test maps of each class (so rare classes
show up in the demo), their labels, the class names, and every array from
quant_params.npz. It is a few hundred kilobytes.
"""
import argparse
from pathlib import Path

import numpy as np

from net import CLASS_NAMES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default="../pynq/demo_data.npz")
    ap.add_argument("--per-class", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    d = np.load(args.data)
    q = dict(np.load(Path(args.run) / "quant" / "quant_params.npz"))
    rng = np.random.default_rng(args.seed)
    X, y = d["X_test"], d["y_test"]
    pick = []
    for k in range(len(CLASS_NAMES)):
        idx = np.flatnonzero(y == k)
        pick.extend(rng.choice(idx, min(args.per_class, len(idx)), replace=False))
    pick = rng.permutation(pick)
    np.savez_compressed(args.out, X=X[pick], y=y[pick], class_names=np.array(CLASS_NAMES), **q)
    counts = np.bincount(y[pick], minlength=len(CLASS_NAMES))
    print(f"Saved {len(pick)} maps to {args.out}: " +
          ", ".join(f"{n} {c}" for n, c in zip(CLASS_NAMES, counts)))


if __name__ == "__main__":
    main()
