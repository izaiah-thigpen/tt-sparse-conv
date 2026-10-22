"""Train the floating-point WaferNet and report the accuracy baseline.

Usage:
    python train_float.py --data data/wm811k_32.npz --out runs/float

Writes to --out:
    model_float.pt          best weights (by validation macro F1)
    metrics.json            per-class results, confusion matrix, input sparsity
    confusion_matrix.png    row-normalized test confusion matrix
    history.csv             loss and validation scores per epoch

Class imbalance is handled two ways (spec: "undersample 'none' or weight the
loss"): "none" is capped in the training set only, and the loss is weighted by
inverse class frequency raised to --weight-power. Validation and test sets keep
the real distribution, so their scores reflect real use.
"""
import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from net import CLASS_NAMES, WaferNet, count_parameters


def augment(x: torch.Tensor) -> torch.Tensor:
    """Random 90-degree rotations and mirror flips. Wafer defect patterns keep
    their class under both, and the maps stay binary."""
    k = torch.randint(0, 4, (x.size(0),), device=x.device)
    out = x.clone()
    for r in (1, 2, 3):
        m = k == r
        if m.any():
            out[m] = torch.rot90(x[m], r, dims=(2, 3))
    flip = torch.rand(x.size(0), device=x.device) < 0.5
    out[flip] = out[flip].flip(3)
    return out


def cap_class(X, y, cls: int, cap: int, rng):
    idx = np.flatnonzero(y == cls)
    if cap <= 0 or len(idx) <= cap:
        return X, y
    drop = rng.choice(idx, len(idx) - cap, replace=False)
    keep = np.setdiff1d(np.arange(len(y)), drop)
    return X[keep], y[keep]


@torch.no_grad()
def predict(model, X, device, scale, batch=2048):
    model.eval()
    out = []
    for s in range(0, len(X), batch):
        xb = torch.from_numpy(X[s:s + batch]).float()[:, None].to(device) / scale
        out.append(model(xb).argmax(1).cpu())
    return torch.cat(out).numpy()


@torch.no_grad()
def input_sparsity(model, X, device, scale, batch=2048):
    """Share of zero values in each hardware layer's 3x3 windows.

    A zero pixel in a window is a tap the zero-skip logic will skip. Float
    weights are almost never exactly zero, so weight-side skips show up only
    after quantization (week 2).
    """
    model.eval()
    zeros = {"conv1": 0, "conv2": 0}
    total = {"conv1": 0, "conv2": 0}
    for s in range(0, len(X), batch):
        xb = torch.from_numpy(X[s:s + batch]).float()[:, None].to(device) / scale
        _, layer_in = model(xb, return_layer_inputs=True)
        for name, t in layer_in.items():
            windows = F.unfold(t, kernel_size=3)  # every tap the hardware sees
            zeros[name] += int((windows == 0).sum())
            total[name] += windows.numel()
    return {name: zeros[name] / total[name] for name in zeros}


def save_confusion_png(cm, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    norm = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES, rotation=45, ha="right")
    ax.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Test set, row-normalized (counts in brackets)")
    for i in range(len(CLASS_NAMES)):
        for j in range(len(CLASS_NAMES)):
            if cm[i, j]:
                ax.text(j, i, f"{norm[i, j]:.2f}\n({cm[i, j]})", ha="center", va="center",
                        fontsize=6.5, color="white" if norm[i, j] > 0.5 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/wm811k_32.npz")
    ap.add_argument("--out", default="runs/float")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--patience", type=int, default=8, help="stop after this many epochs without improvement")
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--none-cap", type=int, default=8000, help="max 'none' maps in training; 0 keeps all")
    ap.add_argument("--weight-power", type=float, default=0.5, help="0 = no weighting, 1 = full inverse frequency")
    ap.add_argument("--n1", type=int, default=8, help="conv1 kernels")
    ap.add_argument("--n2", type=int, default=8, help="conv2 kernels")
    ap.add_argument("--no-augment", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    d = np.load(args.data)
    scale = float(d["input_scale"]) if "input_scale" in d.files else 1.0
    X_tr, y_tr = cap_class(d["X_train"], d["y_train"], CLASS_NAMES.index("none"), args.none_cap, rng)
    X_va, y_va, X_te, y_te = d["X_val"], d["y_val"], d["X_test"], d["y_test"]

    counts = np.bincount(y_tr, minlength=len(CLASS_NAMES)).astype(np.float64)
    if (counts == 0).any():
        missing = [CLASS_NAMES[k] for k in np.flatnonzero(counts == 0)]
        raise SystemExit(f"No training examples for: {missing}")
    weights = (counts.sum() / (len(counts) * counts)) ** args.weight_power
    weights = torch.tensor(weights / weights.mean(), dtype=torch.float32, device=device)

    model = WaferNet(args.n1, args.n2).to(device)
    params = count_parameters(model)
    print(f"Device: {device}   parameters: {params} = {sum(params.values()):,}")
    print(f"Training maps: {len(y_tr):,} (none capped at {args.none_cap:,})   val: {len(y_va):,}   test: {len(y_te):,}")

    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    Xt = torch.from_numpy(X_tr).float()[:, None] / scale
    yt = torch.from_numpy(y_tr)

    best_f1, best_epoch, history = -1.0, 0, []
    print(f"\n{'Epoch':>5}{'Loss':>9}{'Val acc':>9}{'Val F1':>9}{'Time':>7}")
    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        model.train()
        perm = torch.randperm(len(yt))
        total = 0.0
        for s in range(0, len(perm), args.batch):
            b = perm[s:s + args.batch]
            xb, yb = Xt[b].to(device), yt[b].to(device)
            if not args.no_augment:
                xb = augment(xb)
            loss = loss_fn(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        sched.step()

        pred = predict(model, X_va, device, scale)
        acc = float((pred == y_va).mean())
        f1 = float(f1_score(y_va, pred, average="macro", labels=range(len(CLASS_NAMES)), zero_division=0))
        history.append({"epoch": epoch, "loss": total / len(yt), "val_acc": acc, "val_macro_f1": f1})
        mark = ""
        if f1 > best_f1:
            best_f1, best_epoch, mark = f1, epoch, "  *"
            torch.save({"state_dict": model.state_dict(), "n1": args.n1, "n2": args.n2,
                        "class_names": CLASS_NAMES, "input_scale": scale}, out / "model_float.pt")
        print(f"{epoch:>5}{total / len(yt):>9.4f}{acc:>9.3f}{f1:>9.3f}{time.time() - t0:>6.1f}s{mark}")
        if epoch - best_epoch >= args.patience:
            print(f"No improvement for {args.patience} epochs; stopping.")
            break

    with open(out / "history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0]))
        w.writeheader()
        w.writerows(history)

    model.load_state_dict(torch.load(out / "model_float.pt", map_location=device)["state_dict"])
    pred = predict(model, X_te, device, scale)
    labels = list(range(len(CLASS_NAMES)))
    report = classification_report(y_te, pred, labels=labels, target_names=CLASS_NAMES,
                                   output_dict=True, zero_division=0)
    cm = confusion_matrix(y_te, pred, labels=labels)
    sparsity = input_sparsity(model, X_te, device, scale)

    metrics = {
        "best_epoch": best_epoch,
        "val_macro_f1": best_f1,
        "test_accuracy": report["accuracy"],
        "test_macro_f1": report["macro avg"]["f1-score"],
        "per_class": {n: {k: report[n][k] for k in ("precision", "recall", "f1-score", "support")}
                      for n in CLASS_NAMES},
        "confusion_matrix": cm.tolist(),
        "input_zero_fraction": sparsity,
        "parameters": params,
        "args": vars(args),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    save_confusion_png(cm, out / "confusion_matrix.png")

    print(f"\nTest results (best epoch {best_epoch})")
    print(f"{'Class':<11}{'Recall':>8}{'Precision':>11}{'F1':>7}{'Support':>9}")
    for n in CLASS_NAMES:
        r = report[n]
        print(f"{n:<11}{r['recall']:>8.3f}{r['precision']:>11.3f}{r['f1-score']:>7.3f}{int(r['support']):>9,}")
    print(f"\nAccuracy {report['accuracy']:.3f}   macro F1 {metrics['test_macro_f1']:.3f}")
    print(f"Zero taps in the hardware layers' inputs: conv1 {sparsity['conv1']:.1%}, conv2 {sparsity['conv2']:.1%}")
    print(f"Saved results to {out}/")


if __name__ == "__main__":
    main()
