"""Write the test vectors for the chip from a trained, quantized model.

    python make_vectors.py --demo demo_data.npz --out vectors --per-class 1

--demo is the file written by model/export_demo_data.py in the main project:
the quantized weights (quant_params.npz contents), test wafer maps, labels and
class names. Every expected value comes from test/refmodel.py, the integer
model the chip RTL is verified against.

Writes vectors/model.bin and vectors/map_NN.bin (formats in chip_protocol.py).
Without --demo, writes a random model and random maps (--random), which is
what the CI test uses.
"""
import argparse
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "test"))
import refmodel as rm  # noqa: E402

import chip_protocol as cp  # noqa: E402

QUANT_KEYS = ("w1", "b1", "sh1", "w2", "b2", "sh2", "s_out2", "fc_w", "fc_b")


def random_model(rng, n1=16, n2=16, n_classes=9):
    names = ["Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc", "Near-full", "Random", "Scratch", "none"]
    return {
        # Weights lean positive so random maps give a spread of outputs, not mostly zeros
        "w1": rng.integers(-60, 128, size=(n1, 1, 3, 3)).astype(np.int8),
        "b1": rng.integers(-4000, 4000, size=n1),
        "sh1": rng.integers(6, 10, size=n1),
        "w2": rng.integers(-110, 128, size=(n2, n1, 3, 3)).astype(np.int8),
        "b2": rng.integers(-4000, 4000, size=n2),
        "sh2": rng.integers(12, 15, size=n2),
        "s_out2": (rng.random(n2) * 0.05).astype(np.float32),
        "fc_w": rng.standard_normal((n_classes, n2 * 36)).astype(np.float32),
        "fc_b": rng.standard_normal(n_classes).astype(np.float32),
    }, names[:n_classes]


def random_maps(rng, n, sparsity=0.7):
    x = rng.integers(1, 256, size=(n, 32, 32))
    x[rng.random((n, 32, 32)) < sparsity] = 0
    return x.astype(np.uint8), rng.integers(0, 9, size=n)


def model_bytes(q, names):
    n1, n2 = q["w1"].shape[0], q["w2"].shape[0]
    ncls, fc_in = q["fc_w"].shape
    if q["w1"].shape[1:] != (1, 3, 3) or q["w2"].shape[1:] != (n1, 3, 3):
        raise ValueError("unexpected weight shapes")
    b = bytearray(cp.MODEL_MAGIC)
    b += struct.pack("<HHHHH", cp.VERSION, n1, n2, ncls, fc_in)
    b += q["w1"].astype(np.int8).tobytes()
    b += q["b1"].astype("<i4").tobytes()
    b += q["sh1"].astype(np.uint8).tobytes()
    b += q["w2"].astype(np.int8).tobytes()
    b += q["b2"].astype("<i4").tobytes()
    b += q["sh2"].astype(np.uint8).tobytes()
    b += q["s_out2"].astype("<f4").tobytes()
    b += q["fc_w"].astype("<f4").tobytes()
    b += q["fc_b"].astype("<f4").tobytes()
    text = "\n".join(names).encode()
    b += struct.pack("<H", len(text)) + text
    return bytes(b)


def skips_per_kernel(a, wq):
    """Skipped taps per kernel over a whole layer: (pixel == 0) or (weight == 0)."""
    win = rm._windows(a)  # (1, H, W, C*9)
    az = (win == 0).reshape(-1, win.shape[-1])
    wz = (wq.reshape(wq.shape[0], -1) == 0)
    return [int((az | wz[k]).sum()) for k in range(wq.shape[0])]


def map_bytes(x, label, q):
    logits, mid = rm.run_network(x[None], q, return_intermediate=True)
    c1, c2 = mid["conv1_out"][0], mid["conv2_out"][0]
    s1 = skips_per_kernel(mid["conv1_in"], q["w1"])
    s2 = skips_per_kernel(mid["conv2_in"], q["w2"])
    pred = int(np.argmax(logits[0]))
    h, w = x.shape
    b = bytearray(cp.MAP_MAGIC)
    b += struct.pack("<HBBBB", cp.VERSION, int(label), pred, h, w)
    b += x.astype(np.uint8).tobytes()
    b += c1.astype(np.uint8).tobytes()
    b += c2.astype(np.uint8).tobytes()
    b += struct.pack("<%dI" % len(s1), *s1)
    b += struct.pack("<%dI" % len(s2), *s2)
    return bytes(b), pred, logits[0]


def check_round_trip(mb, maps, q):
    """Read the files back with the board-side reader and compare."""
    m = cp.Model(mb)
    assert list(m.w1) == q["w1"].ravel().tolist()
    assert list(m.w2) == q["w2"].ravel().tolist()
    assert list(m.b2) == q["b2"].tolist()
    for data, x, logits in maps:
        v = cp.WaferVector(data, m.n1, m.n2)
        p2 = [rm.maxpool2(np.frombuffer(v.conv2, np.uint8).reshape(1, m.n2, v.h2, v.w2))[0].ravel()][0]
        scores = m.classify(list(p2))
        assert np.allclose(scores, logits, rtol=1e-4, atol=1e-3), "dense layer on the reader differs"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", help="demo_data.npz from model/export_demo_data.py")
    ap.add_argument("--random", action="store_true", help="random model and maps (for CI)")
    ap.add_argument("--out", default=os.path.join(HERE, "vectors"))
    ap.add_argument("--per-class", type=int, default=1, help="maps per class from --demo")
    ap.add_argument("--n", type=int, default=2, help="maps with --random")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    if args.demo:
        d = np.load(args.demo)
        q = {k: d[k] for k in QUANT_KEYS}
        names = [str(n) for n in d["class_names"]]
        X, y = d["X"], d["y"]
        pick = []
        for k in range(len(names)):
            pick.extend(np.flatnonzero(y == k)[:args.per_class].tolist())
        X, y = X[pick], y[pick]
    elif args.random:
        q, names = random_model(rng)
        X, y = random_maps(rng, args.n)
    else:
        ap.error("give --demo or --random")

    os.makedirs(args.out, exist_ok=True)
    mb = model_bytes(q, names)
    with open(os.path.join(args.out, "model.bin"), "wb") as f:
        f.write(mb)
    written = []
    for i, (x, label) in enumerate(zip(X, y)):
        data, pred, logits = map_bytes(x, label, q)
        with open(os.path.join(args.out, "map_%02d.bin" % i), "wb") as f:
            f.write(data)
        written.append((data, x, logits))
        print("map_%02d.bin  label %-10s  model predicts %-10s" % (i, names[int(label)], names[pred]))
    check_round_trip(mb, written, q)
    total = len(mb) + sum(len(d) for d, _, _ in written)
    print("Wrote model.bin and %d maps to %s (%.0f KB). Round-trip check passed."
          % (len(written), args.out, total / 1024))


if __name__ == "__main__":
    main()
