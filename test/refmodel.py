"""Bit-exact integer reference model of the accelerator.

This file is the definition of what the hardware computes. The RTL testbenches
import it, and the quantized network calls the same functions, so the model
that sets accuracy is the model that checks the hardware.

Only NumPy, no PyTorch, so it runs anywhere (including inside cocotb).

Number formats (spec section "Fixed-point format"):
    activation  unsigned 8-bit   0..255
    weight      signed 8-bit     -127..127
    product     signed 17-bit    255 * 127 = 32,385 at most
    bias        signed 24-bit    preloaded into the accumulator
    accumulator signed 24-bit    -8,388,608..8,388,607
    output      unsigned 8-bit   arithmetic shift right, then ReLU, then saturate

A tap is "skipped" when its activation or its weight is zero. Skipping never
changes the result; it only means the multiplier and accumulator did not switch.
"""
import numpy as np

ACT_MAX = 255
W_MAX = 127
ACC_BITS = 24
ACC_MIN = -(1 << (ACC_BITS - 1))
ACC_MAX = (1 << (ACC_BITS - 1)) - 1
SHIFT_MAX = 15  # 4-bit shift field


class AccumulatorOverflow(ArithmeticError):
    pass


# --------------------------------------------------------------------------
# Single-operation model: what one COMPUTE command does. Testbenches use these.
# --------------------------------------------------------------------------

def mac9(pixels, weights, acc: int = 0):
    """One COMPUTE: add nine products to the accumulator.

    Returns (new_acc, skips), where skips counts taps with a zero operand.
    The result is identical whether gating is on or off.
    """
    if len(pixels) != 9 or len(weights) != 9:
        raise ValueError("COMPUTE takes exactly nine pixels and nine weights")
    skips = 0
    for p, w in zip(pixels, weights):
        p, w = int(p), int(w)
        if not 0 <= p <= ACT_MAX:
            raise ValueError(f"pixel {p} out of range")
        if not -W_MAX <= w <= W_MAX:
            raise ValueError(f"weight {w} out of range")
        if p == 0 or w == 0:
            skips += 1
            continue  # gated: accumulator unchanged, which is also what p*w adds
        acc += p * w
        if not ACC_MIN <= acc <= ACC_MAX:
            raise AccumulatorOverflow(f"accumulator {acc} exceeds {ACC_BITS} bits")
    return acc, skips


def output_stage(acc: int, shift: int, relu: bool = True) -> int:
    """READ_RESULT: arithmetic shift right (rounds toward -inf), ReLU, saturate."""
    if not 0 <= shift <= SHIFT_MAX:
        raise ValueError(f"shift {shift} out of range")
    v = int(acc) >> shift
    if relu and v < 0:
        v = 0
    return min(max(v, 0), ACT_MAX)


def output_value(windows, weights, bias: int, shift: int):
    """One full output value, exactly as the host drives the chip.

    windows: one 9-pixel window per input channel. weights: matching 9-weight
    groups. Returns (output byte, raw accumulator, total skips).
    """
    acc, skips = int(bias), 0
    for win, w in zip(windows, weights):
        acc, s = mac9(win, w, acc)
        skips += s
    return output_stage(acc, shift), acc, skips


# --------------------------------------------------------------------------
# Whole-layer model: same arithmetic, vectorized. Used for accuracy runs.
# --------------------------------------------------------------------------

def _windows(a: np.ndarray) -> np.ndarray:
    """(N, C, H, W) -> (N, H-2, W-2, C*9), taps ordered channel-major, then
    row-major within the 3x3 window. This is the order the host sends them."""
    n, c, h, w = a.shape
    s = np.lib.stride_tricks.sliding_window_view(a, (3, 3), axis=(2, 3))  # N,C,H-2,W-2,3,3
    return s.transpose(0, 2, 3, 1, 4, 5).reshape(n, h - 2, w - 2, c * 9)


def conv_layer(a: np.ndarray, wq: np.ndarray, bq: np.ndarray, shift: np.ndarray,
               batch: int = 512, check_overflow: bool = True):
    """Integer 3x3 valid convolution with the hardware output stage.

    a:     uint8   (N, C, H, W)
    wq:    int8    (K, C, 3, 3)
    bq:    int     (K,)       accumulator preload
    shift: int     (K,)       per-kernel shift
    Returns (out uint8 (N, K, H-2, W-2), max |accumulator| seen).
    """
    a = np.asarray(a)
    if a.dtype != np.uint8:
        raise TypeError("activations must be uint8")
    k = wq.shape[0]
    wmat = wq.reshape(k, -1).astype(np.int64).T  # (C*9, K)
    sh = np.asarray(shift, dtype=np.int64)
    out = np.empty((a.shape[0], k, a.shape[2] - 2, a.shape[3] - 2), dtype=np.uint8)
    acc_peak = 0
    for s in range(0, a.shape[0], batch):
        win = _windows(a[s:s + batch].astype(np.int64))
        acc = win @ wmat + np.asarray(bq, dtype=np.int64)  # (n, H-2, W-2, K)
        peak = int(np.abs(acc).max()) if acc.size else 0
        acc_peak = max(acc_peak, peak)
        if check_overflow and (acc.max() > ACC_MAX or acc.min() < ACC_MIN):
            raise AccumulatorOverflow(f"accumulator reached {peak}, limit {ACC_MAX}")
        # Partial sums can't overflow if the final sum is in range and every
        # product fits; worst_case_accumulator() bounds the partial sums.
        v = np.clip(acc >> sh, 0, ACT_MAX)  # >> on int64 is arithmetic; clip = ReLU + saturate
        out[s:s + batch] = v.transpose(0, 3, 1, 2).astype(np.uint8)
    return out, acc_peak


def maxpool2(a: np.ndarray) -> np.ndarray:
    """2x2 max pooling, stride 2, dropping an odd last row or column (host side)."""
    n, c, h, w = a.shape
    h2, w2 = h // 2, w // 2
    return a[:, :, :h2 * 2, :w2 * 2].reshape(n, c, h2, 2, w2, 2).max(axis=(3, 5))


def worst_case_accumulator(wq: np.ndarray, bq: np.ndarray) -> int:
    """Largest |accumulator| any input could produce, including partial sums."""
    k = wq.shape[0]
    pos = np.clip(wq.reshape(k, -1).astype(np.int64), 0, None).sum(1) * ACT_MAX
    neg = np.clip(-wq.reshape(k, -1).astype(np.int64), 0, None).sum(1) * ACT_MAX
    b = np.asarray(bq, dtype=np.int64)
    return int(max((np.abs(b) + np.maximum(pos, neg)).max(), 0))


def skip_counts(a: np.ndarray, wq: np.ndarray, batch: int = 512):
    """Count taps over a whole layer for every kernel.

    Returns dict with total taps, taps with a zero activation, taps with a zero
    weight (and nonzero activation), and all skipped taps.
    """
    k = wq.shape[0]
    wz = (wq.reshape(k, -1) == 0)  # (K, C*9)
    total = act_zero = weight_only = 0
    for s in range(0, a.shape[0], batch):
        win = _windows(a[s:s + batch])
        az = win == 0  # (n, H, W, C*9)
        nz_per_tap = (~az).reshape(-1, az.shape[-1]).sum(0)  # nonzero activations per tap
        total += az.size * k
        act_zero += int(az.sum()) * k
        weight_only += int((wz * nz_per_tap).sum())
    return {"taps": total, "activation_zero": act_zero, "weight_zero_only": weight_only,
            "skipped": act_zero + weight_only}


# --------------------------------------------------------------------------
# Whole network
# --------------------------------------------------------------------------

def run_network(x: np.ndarray, q: dict, return_intermediate: bool = False):
    """Full inference from 32x32 uint8 wafer maps.

    Hardware: conv1 and conv2 (integer, bit exact).
    Host:     max pooling (integer) and the dense layer (float).
    q holds the arrays written by quantize.py.
    """
    a0 = np.asarray(x, dtype=np.uint8)[:, None]
    c1, peak1 = conv_layer(a0, q["w1"], q["b1"], q["sh1"])
    p1 = maxpool2(c1)
    c2, peak2 = conv_layer(p1, q["w2"], q["b2"], q["sh2"])
    p2 = maxpool2(c2)
    feats = p2.astype(np.float64) * q["s_out2"][None, :, None, None]
    logits = feats.reshape(len(feats), -1) @ q["fc_w"].T.astype(np.float64) + q["fc_b"]
    if return_intermediate:
        return logits, {"conv1_in": a0, "conv1_out": c1, "conv2_in": p1, "conv2_out": c2,
                        "acc_peak": (peak1, peak2)}
    return logits

# --------------------------------------------------------------------------
# Activity mode (SET_ACTIVITY / RUN): one generated tap per clock
# --------------------------------------------------------------------------

ACT_SEED = 0x2545F491


def xorshift32(s):
    s ^= (s << 13) & 0xFFFFFFFF
    s ^= s >> 17
    s ^= (s << 5) & 0xFFFFFFFF
    return s


def activity_pixel(state, threshold):
    """Pixel for one activity tap: 0 when the top byte is below the threshold,
    otherwise the low byte with its lowest bit forced to 1."""
    return 0 if (state >> 24) < threshold else ((state & 0xFE) | 1)


def activity_run(weights9, n_taps, threshold, acc=0, skips=0):
    """The chip's state after an activity run of n_taps from a fresh RUN.
    The accumulator wraps at 24 bits and the skip counter saturates at 65,535,
    as in the hardware. Returns (accumulator, skip count)."""
    w = [int(x) for x in weights9]
    s = ACT_SEED
    for k in range(n_taps):
        p, wk = activity_pixel(s, threshold), w[k % 9]
        if p == 0 or wk == 0:
            skips = min(skips + 1, 0xFFFF)
        else:
            acc = ((acc + p * wk + (1 << (ACC_BITS - 1))) % (1 << ACC_BITS)) - (1 << (ACC_BITS - 1))
        s = xorshift32(s)
    return acc, skips
