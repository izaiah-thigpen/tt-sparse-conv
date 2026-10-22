"""Convert the float WaferNet to the accelerator's 8-bit integer format.

Usage:
    python quantize.py --run runs/d_k16_all --data data/wm811k_32_density.npz

Writes to <run>/quant/:
    quant_params.npz     integer weights, biases and shifts (the hardware's data)
    quant_metrics.json   float vs 8-bit accuracy, skip rates, accumulator range

How the conversion works
------------------------
Each convolution layer takes uint8 activations a with a float scale S_a per
channel (the input map: 1/255; later layers: the previous layer's output scale).
That scale is folded into the weights, W' = W * S_a, and then for each kernel k:

    weight scale   s_w[k] = max|W'[k]| / 127        so weights use -127..127
    weights        wq = round(W' / s_w[k])
    bias           bq = round(b / s_w[k])            preloaded into the accumulator
    shift          sh[k] = smallest shift that keeps the calibrated activation
                   peak at or below 255 after  acc >> sh
    output scale   S_out[k] = s_w[k] * 2^sh[k]       passed on to the next layer

So the hardware needs only integer multiply-add and a shift, and the shift is
set per kernel (one WRITE_CONFIG per kernel).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import classification_report, confusion_matrix

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test"))
import refmodel as rm  # noqa: E402  (test/refmodel.py, the chip's bit-exact model)
from net import CLASS_NAMES, WaferNet


def calibrate_peaks(conv_out: torch.Tensor, pct: float) -> np.ndarray:
    """Per-channel activation peak after ReLU: the pct-th percentile of the
    positive values. Rare larger values saturate at 255."""
    peaks = []
    for c in range(conv_out.shape[1]):
        v = conv_out[:, c].flatten()
        v = v[v > 0]
        peaks.append(float(torch.quantile(v[:2_000_000], pct / 100)) if v.numel() else 1.0)
    return np.maximum(np.array(peaks), 1e-6)


def quantize_conv(w: np.ndarray, b: np.ndarray, s_a: np.ndarray, peaks: np.ndarray):
    """Return wq (int8), bq (int64), shift (int64), s_out (float), plus notes."""
    k = w.shape[0]
    w_eff = w * s_a[None, :, None, None]  # fold input scale into the weights
    s_w = np.abs(w_eff.reshape(k, -1)).max(1) / rm.W_MAX
    s_w[s_w == 0] = 1.0
    wq = np.clip(np.rint(w_eff / s_w[:, None, None, None]), -rm.W_MAX, rm.W_MAX).astype(np.int8)
    bq = np.rint(b / s_w).astype(np.int64)
    # Need peak / (s_w * 2^sh) <= 255  ->  sh >= log2(peak / (255 * s_w))
    need = np.log2(peaks / (rm.ACT_MAX * s_w))
    raw = np.ceil(need - 1e-9).astype(np.int64)
    sh = np.clip(raw, 0, rm.SHIFT_MAX)
    notes = []
    for i in np.flatnonzero(raw != sh):
        notes.append(f"kernel {i}: wanted shift {raw[i]}, clamped to {sh[i]}")
    return wq, bq, sh, s_w * (2.0 ** sh), notes


def scalar_check(x: np.ndarray, q: dict, n_values: int, rng) -> int:
    """Recompute random output values one COMPUTE at a time (the way the host
    drives the chip) and compare with the vectorized layer. Returns mismatches."""
    a0 = x[:, None]
    c1, _ = rm.conv_layer(a0, q["w1"], q["b1"], q["sh1"])
    p1 = rm.maxpool2(c1)
    c2, _ = rm.conv_layer(p1, q["w2"], q["b2"], q["sh2"])
    bad = 0
    for layer, a, out, w, b, sh in (("conv1", a0, c1, q["w1"], q["b1"], q["sh1"]),
                                    ("conv2", p1, c2, q["w2"], q["b2"], q["sh2"])):
        for _ in range(n_values):
            n = rng.integers(a.shape[0]); k = rng.integers(w.shape[0])
            i = rng.integers(out.shape[2]); j = rng.integers(out.shape[3])
            windows = [a[n, c, i:i + 3, j:j + 3].ravel() for c in range(a.shape[1])]
            weights = [w[k, c].ravel() for c in range(a.shape[1])]
            val, _, _ = rm.output_value(windows, weights, int(b[k]), int(sh[k]))
            if val != out[n, k, i, j]:
                bad += 1
                if bad <= 5:
                    print(f"  mismatch {layer} n={n} k={k} ({i},{j}): scalar {val}, layer {out[n, k, i, j]}")
    return bad


def report(y, pred):
    labels = list(range(len(CLASS_NAMES)))
    r = classification_report(y, pred, labels=labels, target_names=CLASS_NAMES,
                              output_dict=True, zero_division=0)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="training run folder with model_float.pt")
    ap.add_argument("--data", required=True, help="the .npz the model was trained on")
    ap.add_argument("--calib", type=int, default=10000, help="training maps used for calibration")
    ap.add_argument("--pct", type=float, default=99.99, help="activation percentile mapped to 255")
    ap.add_argument("--check", type=int, default=2000, help="random values checked one COMPUTE at a time, per layer")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    run = Path(args.run)
    ck = torch.load(run / "model_float.pt", map_location="cpu")
    model = WaferNet(ck["n1"], ck["n2"])
    model.load_state_dict(ck["state_dict"])
    model.eval()
    d = np.load(args.data)
    in_scale = float(d["input_scale"]) if "input_scale" in d.files else 1.0
    if in_scale not in (1.0, 255.0):
        raise SystemExit(f"unexpected input_scale {in_scale}")
    X_te, y_te = d["X_test"], d["y_test"]

    # Calibrate on training maps
    cal = d["X_train"][rng.choice(len(d["X_train"]), min(args.calib, len(d["X_train"])), replace=False)]
    with torch.no_grad():
        xc = torch.from_numpy(cal).float()[:, None] / in_scale
        z1 = model.conv1(xc)
        z2 = model.conv2(F.max_pool2d(F.relu(z1), 2))
    peaks1, peaks2 = calibrate_peaks(z1, args.pct), calibrate_peaks(z2, args.pct)

    w1 = model.conv1.weight.detach().numpy().astype(np.float64)
    b1 = model.conv1.bias.detach().numpy().astype(np.float64)
    w2 = model.conv2.weight.detach().numpy().astype(np.float64)
    b2 = model.conv2.bias.detach().numpy().astype(np.float64)

    wq1, bq1, sh1, s_out1, notes1 = quantize_conv(w1, b1, np.array([1.0 / in_scale]), peaks1)
    wq2, bq2, sh2, s_out2, notes2 = quantize_conv(w2, b2, s_out1, peaks2)
    q = {"w1": wq1, "b1": bq1, "sh1": sh1, "s_out1": s_out1,
         "w2": wq2, "b2": bq2, "sh2": sh2, "s_out2": s_out2,
         "fc_w": model.fc.weight.detach().numpy().astype(np.float64),
         "fc_b": model.fc.bias.detach().numpy().astype(np.float64),
         "input_scale": np.array(in_scale)}

    worst = (rm.worst_case_accumulator(wq1, bq1), rm.worst_case_accumulator(wq2, bq2))

    # Float model on the test set
    with torch.no_grad():
        logits_f = torch.cat([model(torch.from_numpy(X_te[s:s + 4096]).float()[:, None] / in_scale)
                              for s in range(0, len(X_te), 4096)]).numpy()
    pred_f = logits_f.argmax(1)

    # 8-bit model on the test set, through the reference model
    logits_q, mid = rm.run_network(X_te, q, return_intermediate=True)
    pred_q = logits_q.argmax(1)
    rf, rq = report(y_te, pred_f), report(y_te, pred_q)

    sk1 = rm.skip_counts(mid["conv1_in"], wq1)
    sk2 = rm.skip_counts(mid["conv2_in"], wq2)

    print(f"Checking {args.check} random values per layer one COMPUTE at a time...")
    mismatches = scalar_check(X_te[:200], q, args.check, rng)

    out = run / "quant"
    out.mkdir(exist_ok=True)
    np.savez(out / "quant_params.npz", **q)
    cm_q = confusion_matrix(y_te, pred_q, labels=list(range(len(CLASS_NAMES))))

    def share(s, key):
        return s[key] / s["taps"]

    metrics = {
        "float": {"accuracy": rf["accuracy"], "macro_f1": rf["macro avg"]["f1-score"]},
        "int8": {"accuracy": rq["accuracy"], "macro_f1": rq["macro avg"]["f1-score"]},
        "prediction_agreement": float((pred_f == pred_q).mean()),
        "per_class_f1": {n: {"float": rf[n]["f1-score"], "int8": rq[n]["f1-score"]} for n in CLASS_NAMES},
        "int8_confusion_matrix": cm_q.tolist(),
        "skip": {name: {"taps": s["taps"], "activation_zero": share(s, "activation_zero"),
                        "weight_zero_only": share(s, "weight_zero_only"), "total": share(s, "skipped")}
                 for name, s in (("conv1", sk1), ("conv2", sk2))},
        "zero_weights": {"conv1": float((wq1 == 0).mean()), "conv2": float((wq2 == 0).mean())},
        "shifts": {"conv1": sh1.tolist(), "conv2": sh2.tolist()},
        "accumulator": {"observed_peak": list(mid["acc_peak"]), "worst_case": list(worst),
                        "limit": rm.ACC_MAX},
        "scalar_check": {"values_per_layer": args.check, "mismatches": mismatches},
        "notes": notes1 + notes2,
        "args": vars(args),
    }
    (out / "quant_metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"\n{'Class':<11}{'Float F1':>10}{'8-bit F1':>10}")
    for n in CLASS_NAMES:
        print(f"{n:<11}{rf[n]['f1-score']:>10.3f}{rq[n]['f1-score']:>10.3f}")
    print(f"{'Macro F1':<11}{metrics['float']['macro_f1']:>10.3f}{metrics['int8']['macro_f1']:>10.3f}")
    print(f"{'Accuracy':<11}{rf['accuracy']:>10.3f}{rq['accuracy']:>10.3f}")
    print(f"Predictions identical for {metrics['prediction_agreement']:.1%} of test maps")
    print(f"\n{'Layer':<7}{'Zero act':>10}{'Zero wt':>10}{'Skipped':>10}{'Zero weights':>14}")
    for name, s in (("conv1", sk1), ("conv2", sk2)):
        print(f"{name:<7}{share(s, 'activation_zero'):>10.1%}{share(s, 'weight_zero_only'):>10.1%}"
              f"{share(s, 'skipped'):>10.1%}{metrics['zero_weights'][name]:>14.1%}")
    tot = (sk1["skipped"] + sk2["skipped"]) / (sk1["taps"] + sk2["taps"])
    print(f"Both layers: {tot:.1%} of multiply-accumulate taps skipped")
    print(f"\nShifts  conv1 {sh1.tolist()}\n        conv2 {sh2.tolist()}")
    print(f"Accumulator peak: conv1 {mid['acc_peak'][0]:,}  conv2 {mid['acc_peak'][1]:,}  "
          f"(worst case {worst[0]:,} / {worst[1]:,}, limit {rm.ACC_MAX:,})")
    print(f"Scalar check: {mismatches} mismatches in {2 * args.check} values")
    for n in notes1 + notes2:
        print("Note:", n)
    print(f"Saved {out}/")


if __name__ == "__main__":
    main()
