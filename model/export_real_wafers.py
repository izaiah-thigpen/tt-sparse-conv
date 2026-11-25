"""Export a small set of real WM-811K wafer maps (die-level) for the paper's figures.

    python model/export_real_wafers.py --pkl path/to/LSWMD.pkl

Writes real_wafers.npz (a few hundred kB) holding, for each of the nine classes,
up to --per-class wafers from the lot-split TEST set, with their raw die maps
(0 = no die, 1 = pass, 2 = fail), lot name, wafer index and 32 x 32 density map.
It also finds the raw maps behind the nine test vectors in host/vectors/, so the
class figure can show the exact wafers the chip test kit uses.

Uses the same loading, labeling, resize and split as prepare_data.py, so the
wafers are exactly those the model was tested on.
"""
import argparse, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from prepare_data import load_lswmd, label_of, to_fail_grids, split_indices  # noqa: E402
from net import CLASS_NAMES  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pkl", required=True)
    ap.add_argument("--out", default="real_wafers.npz")
    ap.add_argument("--per-class", type=int, default=12)
    ap.add_argument("--vectors", default=os.path.join(HERE, "..", "host", "vectors"))
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    df = load_lswmd(a.pkl)
    labels = df["failureType"].map(label_of)
    keep = labels.notna().to_numpy()
    df, labels = df[keep].reset_index(drop=True), labels[keep].reset_index(drop=True)
    y = labels.map(CLASS_NAMES.index).to_numpy(dtype=np.int64)
    groups = df["lotName"].astype(str).to_numpy()
    _, _, test = split_indices(y, groups, "lot", a.seed)
    print(f"Labeled maps: {len(df):,}; test set: {len(test):,}")

    rng = np.random.default_rng(a.seed)
    chosen = []
    for k in range(len(CLASS_NAMES)):
        idx = test[y[test] == k]
        chosen += list(rng.choice(idx, size=min(a.per_class, len(idx)), replace=False))

    # the nine test vectors' source wafers: match their 32 x 32 maps against the test set
    vec = []
    for i in range(9):
        path = os.path.join(a.vectors, f"map_{i:02d}.bin")
        if os.path.exists(path):
            vec.append(np.fromfile(path, dtype=np.uint8)[10:10 + 1024].reshape(32, 32))
    matched = []
    if vec:
        X = to_fail_grids(df["waferMap"].iloc[test].tolist(), mode="density")
        for v in vec:
            hits = np.flatnonzero((X == v).all(axis=(1, 2)))
            matched.append(int(test[hits[0]]) if len(hits) else -1)
        print("test vectors matched to wafers:", sum(m >= 0 for m in matched), "of", len(vec))
    chosen = sorted(set(int(c) for c in chosen) | {m for m in matched if m >= 0})

    maps = [np.asarray(df["waferMap"].iloc[i], dtype=np.uint8) for i in chosen]
    out = np.empty(len(maps), dtype=object)
    out[:] = maps
    np.savez_compressed(
        a.out,
        wafer_maps=out,
        labels=np.array([CLASS_NAMES[y[i]] for i in chosen]),
        lots=np.array([str(df["lotName"].iloc[i]) for i in chosen]),
        wafer_index=np.array([float(np.asarray(df["waferIndex"].iloc[i]).ravel()[0]) if "waferIndex" in df else -1 for i in chosen]),
        row=np.array(chosen),
        density=to_fail_grids(maps, mode="density"),
        vector_rows=np.array(matched),
        class_names=np.array(CLASS_NAMES),
    )
    print(f"Saved {len(chosen)} real wafers to {a.out} ({os.path.getsize(a.out) / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
