"""Turn WM-811K (LSWMD.pkl) into 32 x 32 binary fail maps with train/val/test splits.

Usage:
    python prepare_data.py --pkl data/LSWMD.pkl --out data/wm811k_32.npz

Steps (spec section "Model and dataset"):
  1. Keep only labeled wafer maps.
  2. Encode each die: fail -> 1, pass and no-die -> 0.
  3. Resize to 32 x 32. Default: each cell holds the share of failed dies,
     scaled to 0-255 (see to_fail_grids). --resize max gives 0/1 cells.
  4. Split about 71 / 14 / 14 into train / val / test, stratified by class.
     By default whole lots stay together (see --split below).

WM-811K encodes each die as 0 = no die, 1 = pass, 2 = fail.
"""
import argparse
import collections
import pickle
import sys
import time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

from net import CLASS_NAMES, INPUT_SIZE


class _LegacyUnpickler(pickle.Unpickler):
    """LSWMD.pkl was written by an old pandas whose module paths have moved."""

    def find_class(self, module, name):
        if module.startswith("pandas.indexes"):
            module = module.replace("pandas.indexes", "pandas.core.indexes", 1)
        return super().find_class(module, name)


def load_lswmd(path: str) -> pd.DataFrame:
    try:
        return pd.read_pickle(path)
    except Exception as first_error:
        for encoding in ("ASCII", "latin1"):
            try:
                with open(path, "rb") as f:
                    return _LegacyUnpickler(f, encoding=encoding).load()
            except Exception:
                continue
        sys.exit(
            f"Could not load {path}: {first_error!r}\n"
            "The file was saved by an old pandas. If this keeps failing, make a "
            "separate environment with an older pandas, for example:\n"
            "  python -m venv wm-env && wm-env/bin/pip install 'pandas<2' numpy\n"
            "then load it there and re-save with df.to_pickle('LSWMD_new.pkl')."
        )


def label_of(value):
    """failureType is a nested array like [['Center']], or empty when unlabeled."""
    flat = np.asarray(value, dtype=object).ravel()
    if flat.size == 0:
        return None
    name = str(flat[0]).strip()
    return name if name in CLASS_NAMES else None


def to_fail_grids(maps, mode: str = "density", size: int = INPUT_SIZE, chunk: int = 4096) -> np.ndarray:
    """Resize fail maps to size x size, batched by original shape.

    mode "density": each cell holds the share of its area that failed, scaled
        to 1..255 (0 only when no die in the cell failed). Scattered background
        failures stay faint, so small clusters and scratches stand out.
    mode "max": each cell is 1 if any die in it failed. Simple, but on large
        wafers background failures light up a large share of cells.

    Either way a cell is zero exactly when none of its dies failed, so the
    zero-skip rate is the same.
    """
    out = np.zeros((len(maps), size, size), dtype=np.uint8)
    by_shape = collections.defaultdict(list)
    for i, m in enumerate(maps):
        by_shape[np.asarray(m).shape].append(i)
    for idx in by_shape.values():
        for start in range(0, len(idx), chunk):
            part = idx[start:start + chunk]
            fail = np.stack([np.asarray(maps[i]) == 2 for i in part]).astype(np.float32)
            t = torch.from_numpy(fail)[:, None]
            if mode == "max":
                out[part] = F.adaptive_max_pool2d(t, size)[:, 0].numpy().astype(np.uint8)
            else:
                frac = F.adaptive_avg_pool2d(t, size)[:, 0].numpy()
                val = np.rint(frac * 255)
                val[(frac > 0) & (val < 1)] = 1  # keep any failure nonzero
                out[part] = val.astype(np.uint8)
    return out


def split_indices(y, groups, mode: str, seed: int):
    """Return train, val and test index arrays.

    mode "lot": wafers from one lot never straddle two splits. Wafers in a lot
    often share a defect pattern, so a random split can leak near-duplicates
    into the test set and inflate the score.
    mode "random": plain stratified random split, 70 / 15 / 15.
    """
    idx = np.arange(len(y))
    if mode == "random" or groups is None:
        train, temp = train_test_split(idx, test_size=0.30, stratify=y, random_state=seed)
        val, test = train_test_split(temp, test_size=0.50, stratify=y[temp], random_state=seed)
        return train, val, test
    outer = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=seed)
    rest, test = next(outer.split(idx, y, groups))
    inner = StratifiedGroupKFold(n_splits=6, shuffle=True, random_state=seed)
    tr, va = next(inner.split(rest, y[rest], groups[rest]))
    return rest[tr], rest[va], test


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pkl", required=True, help="path to LSWMD.pkl")
    ap.add_argument("--out", default="data/wm811k_32.npz")
    ap.add_argument("--split", choices=["lot", "random"], default="lot")
    ap.add_argument("--resize", choices=["density", "max"], default="density")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    t0 = time.time()
    df = load_lswmd(args.pkl)
    print(f"Loaded {len(df):,} wafer maps in {time.time() - t0:.0f} s")

    labels = df["failureType"].map(label_of)
    keep = labels.notna().to_numpy()
    df, labels = df[keep].reset_index(drop=True), labels[keep].reset_index(drop=True)
    y = labels.map(CLASS_NAMES.index).to_numpy(dtype=np.int64)
    print(f"Labeled maps: {len(df):,}")

    t0 = time.time()
    X = to_fail_grids(df["waferMap"].tolist(), mode=args.resize)
    print(f"Resized to {INPUT_SIZE} x {INPUT_SIZE} ({args.resize}) in {time.time() - t0:.0f} s")

    groups = df["lotName"].astype(str).to_numpy() if "lotName" in df else None
    train, val, test = split_indices(y, groups, args.split, args.seed)

    print(f"\n{'Class':<10}{'All':>9}{'Train':>9}{'Val':>8}{'Test':>8}")
    for k, name in enumerate(CLASS_NAMES):
        counts = [int((y[s] == k).sum()) for s in (np.arange(len(y)), train, val, test)]
        print(f"{name:<10}" + "".join(f"{c:>{w},}" for c, w in zip(counts, (9, 9, 8, 8))))
    print(f"{'Total':<10}{len(y):>9,}{len(train):>9,}{len(val):>8,}{len(test):>8,}")
    print(f"\nShare of zero pixels in the inputs: {(X == 0).mean():.1%}")

    np.savez_compressed(
        args.out,
        X_train=X[train], y_train=y[train],
        X_val=X[val], y_val=y[val],
        X_test=X[test], y_test=y[test],
        class_names=np.array(CLASS_NAMES), split=np.array(args.split),
        resize=np.array(args.resize), input_scale=np.array(1 if args.resize == "max" else 255),
    )
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
