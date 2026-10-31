"""Generate a small fake dataset in the same format as WM-811K's LSWMD.pkl.

Use it to check that the pipeline runs before the real data is downloaded:
    python make_synthetic.py --n 6000 --out data/synthetic.pkl
    python prepare_data.py --pkl data/synthetic.pkl --out data/synthetic_32.npz
    python train_float.py --data data/synthetic_32.npz --out runs/synthetic --epochs 5

The patterns are crude imitations. Results on this data say nothing about
accuracy on real wafer maps.
"""
import argparse

import numpy as np
import pandas as pd

# Rough class mix, loosely like the real labeled set (mostly "none").
MIX = {"none": 0.60, "Edge-Ring": 0.10, "Edge-Loc": 0.06, "Center": 0.06, "Loc": 0.05,
       "Scratch": 0.04, "Random": 0.04, "Donut": 0.03, "Near-full": 0.02}


def make_wafer(cls: str, rng) -> np.ndarray:
    n = int(rng.integers(26, 64))
    h, w = n, n + int(rng.integers(-3, 4))
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx - (w - 1) / 2) / ((w - 1) / 2)
    v = (yy - (h - 1) / 2) / ((h - 1) / 2)
    r, theta = np.hypot(u, v), np.arctan2(v, u)
    die = r <= 1.0

    p = np.full((h, w), 0.02)  # background fail rate
    if cls == "Center":
        p[r < rng.uniform(0.2, 0.35)] = 0.7
    elif cls == "Donut":
        a = rng.uniform(0.25, 0.35)
        p[(r > a) & (r < a + 0.25)] = 0.7
    elif cls == "Edge-Ring":
        p[r > rng.uniform(0.82, 0.9)] = 0.75
    elif cls == "Edge-Loc":
        ang = rng.uniform(-np.pi, np.pi)
        d = np.angle(np.exp(1j * (theta - ang)))
        p[(r > 0.75) & (np.abs(d) < rng.uniform(0.35, 0.7))] = 0.7
    elif cls == "Loc":
        c = rng.uniform(-0.5, 0.5, 2)
        p[np.hypot(u - c[0], v - c[1]) < rng.uniform(0.12, 0.2)] = 0.7
    elif cls == "Scratch":
        c, ang = rng.uniform(-0.4, 0.4, 2), rng.uniform(0, np.pi)
        dx, dy = np.cos(ang), np.sin(ang)
        along = (u - c[0]) * dx + (v - c[1]) * dy
        across = np.abs(-(u - c[0]) * dy + (v - c[1]) * dx)
        p[(np.abs(along) < 0.4) & (across < 0.05)] = 0.85
    elif cls == "Random":
        p[:] = 0.25
    elif cls == "Near-full":
        p[:] = 0.85

    m = np.where(die, 1, 0).astype(np.uint8)
    m[die & (rng.random((h, w)) < p)] = 2
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6000, help="labeled maps to generate")
    ap.add_argument("--unlabeled", type=float, default=0.3, help="extra unlabeled maps, as a share of --n")
    ap.add_argument("--out", default="data/synthetic.pkl")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    names, probs = list(MIX), np.array(list(MIX.values()))
    labels = list(rng.choice(names, size=args.n, p=probs / probs.sum()))
    labels += [None] * int(args.n * args.unlabeled)
    rng.shuffle(labels)

    rows = []
    for i, cls in enumerate(labels):
        m = make_wafer(cls or str(rng.choice(names)), rng)
        tag = np.array([[cls]], dtype=object) if cls else np.array([], dtype=object)
        rows.append({"waferMap": m, "dieSize": float((m > 0).sum()), "lotName": f"lot{i // 25}",
                     "waferIndex": float(i % 25 + 1), "trianTestLabel": tag, "failureType": tag})
    pd.DataFrame(rows).to_pickle(args.out)
    print(f"Wrote {len(rows):,} maps ({args.n:,} labeled) to {args.out}")


if __name__ == "__main__":
    main()
