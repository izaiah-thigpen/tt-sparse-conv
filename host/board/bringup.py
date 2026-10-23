"""Bring-up and verification of the sparsity-aware convolution chip.

Runs on the Tiny Tapeout demo board or the host board in pcb/ (MicroPython).
Needs these files on the board: chip_protocol.py, tt_spi.py, bringup.py,
ina228.py (host board power monitor), and the folder vectors/ (model.bin,
map_NN.bin) made by make_vectors.py.

    mpremote run bringup.py                 quick check, about a minute
    >>> import bringup; bringup.main("full")   every output of every map
    >>> bringup.power_sweep()                  power measurement (automatic on the host board)

Every check prints PASS or FAIL; the last line is the overall result. The
same lines are appended to results.txt on the board.

Stages:
  1. Smoke tests: chip ID, accumulator read/write, hand-checked values,
     gating on/off by config and by the BYPASS pin, a 16-channel worst-case
     sum, pseudo-random values, and the DONE/BUSY pins. No files needed.
     Also activity-mode runs (the multiplier driven every clock from the
     chip's own generator), checked against the model, and RUN until STOP.
  2. Network tests: for each stored wafer map, layer 1 and layer 2 of the
     trained network on the chip, compared output by output with values from
     the reference model, plus skip counts. In "full" mode the chip's own
     layer-1 outputs feed layer 2 and the board reports the predicted class.
"""
import os
import time

import chip_protocol as cp
from tt_spi import Spi, DONE, BUSY

# Weights for activity runs: all nonzero, so the share of skipped taps is the
# generator's zero share, about threshold/256
SWEEP_WEIGHTS = [37, -88, 101, -15, 64, 127, -127, 9, -50]
SWEEP_THRESHOLDS = [0, 64, 128, 192, 230]

PROJECT = "tt_um_izaiah_thigpen_sparse_conv"
CLOCK_HZ = 10000000
VECTOR_DIR = "vectors"
QUICK_SAMPLES = 24        # output values per layer per map in quick mode
QUICK_MAPS = 2            # maps checked in quick mode
MAX_DETAILS = 5           # mismatches printed per check


def _ms():
    try:
        return time.ticks_ms()
    except AttributeError:
        return int(time.monotonic() * 1000)


def _elapsed_s(t0):
    try:
        return time.ticks_diff(time.ticks_ms(), t0) / 1000
    except AttributeError:
        return (_ms() - t0) / 1000


def _sleep_ms(n):
    try:
        time.sleep_ms(n)
    except AttributeError:
        time.sleep(n / 1000)


class Rng:
    """xorshift32, so the pseudo-random tests are identical on every platform."""

    def __init__(self, seed=0x2545F491):
        self.s = seed & 0xFFFFFFFF or 1

    def next(self):
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s
        return s

    def randint(self, lo, hi):
        return lo + self.next() % (hi - lo + 1)


class Report:
    def __init__(self, log_path=None):
        self.passed = 0
        self.failed = 0
        self.log_path = log_path
        self._lines = []

    def line(self, text):
        print(text)
        self._lines.append(text)

    def check(self, name, ok, detail=""):
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        self.line("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  " + detail) if detail else ""))
        return ok

    def save(self):
        if not self.log_path:
            return
        try:
            with open(self.log_path, "a") as f:
                for t in self._lines:
                    f.write(t + "\n")
        except OSError as e:
            print("could not write %s: %s" % (self.log_path, e))


# ----------------------------------------------------------------------
# Chip operations
# ----------------------------------------------------------------------

def value(spi, groups, bias, shift, gate=True):
    """One output value. Returns (result, accumulator, skip count)."""
    spi.frame(cp.write_config(shift, gate) + cp.clear_skips())
    res = cp.decode_result(spi.frame(cp.value_frame(groups, bias)))
    acc = cp.decode_acc(spi.frame(cp.read_acc()))
    skips = cp.decode_skips(spi.frame(cp.read_skips()))
    return res, acc, skips


def reference(groups, bias, shift):
    acc, skips = bias, 0
    for pix, wts in groups:
        acc, s = cp.mac9(pix, wts, acc)
        skips += s
    return cp.output_stage(acc, shift), acc, skips


# ----------------------------------------------------------------------
# 1. Smoke tests
# ----------------------------------------------------------------------

def smoke_tests(spi, rep, n_random=12):
    rep.line("--- Smoke tests")
    ids = [cp.decode_id(spi.frame(cp.read_id())) for _ in range(3)]
    if not rep.check("READ_ID returns 0xA5", ids == [cp.CHIP_ID] * 3, "got %s" % [hex(i) for i in ids]):
        rep.line("      The chip is not answering. Check that the project is enabled, the clock")
        rep.line("      is running, and reset was released. Stopping here.")
        return False

    bad = []
    for v in (0, 1, -1, 123456, -654321, cp.ACC_MAX, cp.ACC_MIN):
        spi.frame(cp.load_acc(v))
        got = cp.decode_acc(spi.frame(cp.read_acc()))
        if got != v:
            bad.append((v, got))
    rep.check("LOAD_ACC / READ_ACC round trip, 7 values", not bad, "(sent, got) %s" % bad[:MAX_DETAILS] if bad else "")

    res, acc, sk = value(spi, [(list(range(1, 10)), [1] * 9)], 0, 0)
    rep.check("weights all 1, pixels 1..9 gives 45", (res, acc, sk) == (45, 45, 0),
              "got result %d, acc %d, skips %d" % (res, acc, sk))

    cases = [
        ("zero pixels", [0] * 9, [5, -3, 7, 1, 2, -8, 9, 4, 6]),
        ("zero weights", [10, 20, 30, 40, 50, 60, 70, 80, 90], [0] * 9),
        ("mixed signs", [1, 2, 3, 4, 5, 6, 7, 8, 9], [9, -8, 7, -6, 5, -4, 3, -2, 1]),
        ("max positive", [255] * 9, [127] * 9),
        ("max negative", [255] * 9, [-127] * 9),
        ("some zeros", [3, 0, 5, 7, 0, 2, 9, 1, 4], [2, 4, -6, 8, 1, 0, -3, 5, 7]),
    ]
    for label, gate, bypass in (("gating on", True, False), ("gating off (config)", False, False),
                                ("gating off (BYPASS pin)", True, True)):
        spi.set_bypass(bypass)
        bad = []
        for name, pix, wts in cases:
            for bias, shift in ((0, 0), (-5000, 4), (300000, 11)):
                got = value(spi, [(pix, wts)], bias, shift, gate)
                want = reference([(pix, wts)], bias, shift)
                if got != want:
                    bad.append("%s bias %d shift %d: got %s want %s" % (name, bias, shift, got, want))
        rep.check("corner cases, %s (18 values)" % label, not bad, "; ".join(bad[:MAX_DETAILS]))
    spi.set_bypass(False)

    groups = [([255] * 9, [127] * 9)] * 16
    got = value(spi, groups, 0, 15)
    rep.check("16-channel worst case sums to 4,663,440", got == reference(groups, 0, 15), "got %s" % (got,))

    rng = Rng()
    bad = []
    for i in range(n_random):
        groups = []
        sparsity = rng.randint(0, 9)  # tenths
        for _ in range(rng.randint(1, 16)):
            pix = [0 if rng.randint(0, 9) < sparsity else rng.randint(1, 255) for _ in range(9)]
            groups.append((pix, [rng.randint(-127, 127) for _ in range(9)]))
        bias, shift, gate = rng.randint(-1000000, 1000000), rng.randint(0, 15), rng.randint(0, 1) == 1
        got, want = value(spi, groups, bias, shift, gate), reference(groups, bias, shift)
        if got != want:
            bad.append("value %d: got %s want %s" % (i, got, want))
    rep.check("%d pseudo-random chained values" % n_random, not bad, "; ".join(bad[:MAX_DETAILS]))

    activity_tests(spi, rep)

    spi.frame(cp.write_weights([1] * 9))
    idle = spi.pins()
    spi.frame(bytes([cp.COMPUTE, 1, 2, 3, 4]), keep_open=True)
    mid = spi.pins()
    spi.frame(bytes([5, 6, 7, 8, 9]))
    end = spi.pins()
    ok = (not idle & BUSY) and (mid & BUSY) and not (mid & DONE) and (end & DONE) and not (end & BUSY)
    rep.check("BUSY high during COMPUTE, DONE high after", bool(ok),
              "uo_out before 0x%02X, during 0x%02X, after 0x%02X" % (idle, mid, end))
    return True


def wait_done(spi, tries=1000):
    for _ in range(tries):
        p = spi.pins()
        if (p & DONE) and not (p & BUSY):
            return True
    return False


def activity_value(spi, weights, bias, threshold, n_taps, gate=True):
    """Finite activity run. Returns (finished, accumulator, skip count)."""
    spi.frame(cp.write_weights(weights) + cp.write_config(0, gate) + cp.load_acc(bias)
              + cp.clear_skips() + cp.set_activity(threshold) + cp.run(n_taps))
    ok = wait_done(spi)
    acc = cp.decode_acc(spi.frame(cp.read_acc()))
    skips = cp.decode_skips(spi.frame(cp.read_skips()))
    return ok, acc, skips


def activity_tests(spi, rep):
    rng = Rng(777)
    bad = []
    for threshold in (0, 64, 128, 230, 255):
        weights = [rng.randint(-127, 127) for _ in range(9)]
        weights[rng.randint(0, 8)] = 0
        bias = rng.randint(-50000, 50000)
        for label, gate, bypass in (("gated", True, False), ("config off", False, False), ("BYPASS", True, True)):
            spi.set_bypass(bypass)
            ok, acc, skips = activity_value(spi, weights, bias, threshold, 900, gate)
            want = cp.activity_run(weights, 900, threshold, acc=bias)
            if not ok or (acc, skips) != want:
                bad.append("T=%d %s: done=%s got %s want %s" % (threshold, label, ok, (acc, skips), want))
    spi.set_bypass(False)
    rep.check("activity runs, 5 thresholds x 3 gating modes (900 taps each)", not bad,
              "; ".join(bad[:MAX_DETAILS]))

    spi.frame(cp.write_weights(SWEEP_WEIGHTS) + cp.write_config(0, True) + cp.load_acc(0)
              + cp.clear_skips() + cp.set_activity(128) + cp.run(0))
    running = spi.pins() & BUSY
    spi.frame(cp.stop())
    stopped = wait_done(spi)
    a1 = cp.decode_acc(spi.frame(cp.read_acc()))
    a2 = cp.decode_acc(spi.frame(cp.read_acc()))
    rep.check("RUN until STOP: runs, stops, stays stopped", bool(running) and stopped and a1 == a2,
              "busy while running %s, stopped %s, acc %d then %d" % (bool(running), stopped, a1, a2))


# ----------------------------------------------------------------------
# 2. Network tests
# ----------------------------------------------------------------------

def _positions(n_kernels, h, w, samples, rng):
    if samples is None:
        for k in range(n_kernels):
            for r in range(h):
                for c in range(w):
                    yield k, r, c
    else:
        for _ in range(samples):
            yield rng.randint(0, n_kernels - 1), rng.randint(0, h - 1), rng.randint(0, w - 1)


def run_layer(spi, rep, name, n_kernels, h, w, groups_at, weights_of, bias, shift,
              expected, expected_skips, samples, rng):
    """Runs one layer on the chip. groups_at(k, r, c) gives the (pixels, weights)
    groups for an output; with one input channel the weights are loaded once per
    kernel. Returns the chip's outputs (full mode) and the number of mismatches."""
    out = bytearray(n_kernels * h * w) if samples is None else None
    bad, details = 0, []
    skip_bad = []
    current_k = -1
    sampled_skips = {}
    for k, r, c in _positions(n_kernels, h, w, samples, rng):
        if k != current_k:
            if current_k >= 0 and samples is None:
                got = cp.decode_skips(spi.frame(cp.read_skips()))
                if got != expected_skips[current_k]:
                    skip_bad.append((current_k, got, expected_skips[current_k]))
            current_k = k
            setup = cp.write_config(shift[k], True) + cp.clear_skips()
            if weights_of is not None:
                setup += cp.write_weights(weights_of(k))
            spi.frame(setup)
        groups = groups_at(k, r, c)
        if samples is not None:
            spi.frame(cp.clear_skips())
        got = cp.decode_result(spi.frame(cp.value_frame(groups, bias[k])))
        if samples is not None:
            want_sk = reference([(p, w if w is not None else weights_of(k)) for p, w in groups], 0, 0)[2]
            got_sk = cp.decode_skips(spi.frame(cp.read_skips()))
            if got_sk != want_sk:
                skip_bad.append((k, got_sk, want_sk))
        want = expected[(k * h + r) * w + c]
        if out is not None:
            out[(k * h + r) * w + c] = got
        if got != want:
            bad += 1
            if len(details) < MAX_DETAILS:
                details.append("k%d (%d,%d) got %d want %d" % (k, r, c, got, want))
    if samples is None and current_k >= 0:
        got = cp.decode_skips(spi.frame(cp.read_skips()))
        if got != expected_skips[current_k]:
            skip_bad.append((current_k, got, expected_skips[current_k]))
    n = n_kernels * h * w if samples is None else samples
    rep.check("%s: %d outputs match the reference model" % (name, n), bad == 0,
              "%d mismatches: %s" % (bad, "; ".join(details)) if bad else "")
    rep.check("%s: skip counts match" % name, not skip_bad,
              "(kernel, got, want) %s" % skip_bad[:MAX_DETAILS] if skip_bad else "")
    return out, bad


def network_test(spi, rep, model, vec, name, samples, rng):
    rep.line("--- %s: true class %s, model predicts %s" % (
        name, model.class_names[vec.label], model.class_names[vec.expected_prediction]))
    t0 = _ms()
    sent0 = spi.bytes_sent
    n1, n2 = model.n1, model.n2
    h, w, h1, w1, h2, w2 = vec.h, vec.w, vec.h1, vec.w1, vec.h2, vec.w2

    c1, _ = run_layer(
        spi, rep, "layer 1", n1, h1, w1,
        lambda k, r, c: [(cp.window(vec.x, h, w, r, c), None)],
        model.kernel1, model.b1, model.sh1, vec.conv1, vec.skips1, samples, rng)

    # Layer-2 input: the chip's own layer-1 outputs in full mode, the expected ones otherwise
    src = c1 if c1 is not None else vec.conv1
    hp, wp = h1 // 2, w1 // 2
    pooled = [cp.maxpool2(src[ch * h1 * w1:(ch + 1) * h1 * w1], h1, w1) for ch in range(n1)]

    c2, _ = run_layer(
        spi, rep, "layer 2", n2, h2, w2,
        lambda k, r, c: [(cp.window(pooled[ch], hp, wp, r, c), list(model.kernel2(k, ch))) for ch in range(n1)],
        None, model.b2, model.sh2, vec.conv2, vec.skips2, samples, rng)

    if c2 is not None:
        feats = []
        for ch in range(n2):
            feats.extend(cp.maxpool2(c2[ch * h2 * w2:(ch + 1) * h2 * w2], h2, w2))
        scores = model.classify(feats)
        pred = max(range(len(scores)), key=lambda i: scores[i])
        rep.check("predicted class %s (reference model: %s, true: %s)" % (
            model.class_names[pred], model.class_names[vec.expected_prediction], model.class_names[vec.label]),
            pred == vec.expected_prediction)

    secs = _elapsed_s(t0)
    sent = spi.bytes_sent - sent0
    rate = sent / secs if secs > 0 else 0
    rep.line("      %d SPI bytes in %.1f s (%.0f bytes/s)" % (sent, secs, rate))
    return rate


def load_vectors(directory):
    model = cp.Model(open(directory + "/model.bin", "rb").read())
    names = sorted(n for n in os.listdir(directory) if n.startswith("map_") and n.endswith(".bin"))
    return model, names


# ----------------------------------------------------------------------
# Entry points
# ----------------------------------------------------------------------

def run(spi, mode="quick", vector_dir=VECTOR_DIR, log_path=None, n_random=12):
    """All tests on an already-connected chip. Returns True if everything passed."""
    if mode not in ("quick", "full", "smoke"):
        raise ValueError("mode is quick, full or smoke")
    rep = Report(log_path)
    rep.line("=== Sparsity-aware convolution chip, %s test" % mode)
    t0 = _ms()
    alive = smoke_tests(spi, rep, n_random)
    rate = 0
    if alive and mode != "smoke":
        try:
            model, names = load_vectors(vector_dir)
        except OSError:
            rep.check("vector files found in %s/" % vector_dir, False, "copy the vectors folder to the board")
            names = []
        if mode == "quick":
            names = names[:QUICK_MAPS]
        rng = Rng(12345)
        for n in names:
            vec = cp.WaferVector(open(vector_dir + "/" + n, "rb").read(), model.n1, model.n2)
            rate = network_test(spi, rep, model, vec, n, QUICK_SAMPLES if mode == "quick" else None, rng)
    total = rep.passed + rep.failed
    rep.line("=== RESULT: %s  (%d of %d checks passed, %.0f s)" % (
        "PASS" if rep.failed == 0 and alive else "FAIL", rep.passed, total, _elapsed_s(t0)))
    if mode == "quick" and rate > 0:
        rep.line("    A full map is about 1.1 MB of SPI traffic: about %.1f minutes each at this speed."
                 % (1111904 / rate / 60))
    rep.save()
    return rep.failed == 0 and alive


def connect(clock_hz=CLOCK_HZ):
    """Select the project on the demo board, start its clock, reset it."""
    from ttboard.demoboard import DemoBoard
    from ttboard.mode import RPMode
    import ttboard.util.platform as platform
    try:
        tt = DemoBoard.get()
    except Exception:
        # Not set up by the board's main.py (e.g. a custom boot): detect the board first
        from ttboard.boot.demoboard_detect import DemoboardDetect
        DemoboardDetect.probe()
        tt = DemoBoard.get()
    if not hasattr(tt.shuttle, PROJECT):
        raise RuntimeError("%s is not on this chip's shuttle; check the chip and the SDK's shuttle file" % PROJECT)
    getattr(tt.shuttle, PROJECT).enable()
    tt.mode = RPMode.ASIC_RP_CONTROL
    spi = Spi(platform.write_ui_in_byte, platform.read_uo_out_byte)
    tt.clock_project_PWM(clock_hz)
    tt.reset_project(True)
    _sleep_ms(20)
    tt.reset_project(False)
    _sleep_ms(20)
    return tt, spi


def _wait_user(prompt, hold_s):
    if hold_s:
        print("%s  (holding %d s)" % (prompt, hold_s))
        _sleep_ms(int(hold_s * 1000))
    else:
        input(prompt + "  Press Enter when the reading is recorded. ")


SWEEP_CLOCK_HZ = 50000000   # the chip's sign-off clock; the gating's saving scales with it


def _measure(ina, hold_s, settle_s=0.5):
    """Mean current (A), its spread, core voltage (V) and power from the energy
    accumulator (W) over hold_s seconds."""
    _sleep_ms(int(settle_s * 1000))
    ina.reset_accumulators()
    t0 = _ms()
    n, s1, s2, v = 0, 0.0, 0.0, 0.0
    while _elapsed_s(t0) < hold_s:
        _sleep_ms(max(1, int(ina.conversion_s * 1000)))
        i = ina.current()
        n += 1; s1 += i; s2 += i * i
        v += ina.bus_voltage()
    secs = _elapsed_s(t0)
    mean = s1 / n
    spread = max(0.0, s2 / n - mean * mean) ** 0.5
    return mean, spread, v / n, ina.energy() / secs if secs > 0 else 0.0


def power_sweep(hold_s=None, thresholds=None, clock_hz=SWEEP_CLOCK_HZ, log_path="power_sweep.csv",
                spi=None, ina="auto"):
    """Supply-current measurement of the zero-skip gating.

    For each zero threshold, the chip runs continuously in activity mode, first
    gated and then with BYPASS high (gating off). The difference between the
    two is the power the gating saves at that share of zero inputs. An idle
    step (clock running, no activity) comes first as the baseline.

    On the host board (pcb/), the INA228 on the core supply is read
    automatically: each step records mean current, its spread, core voltage
    and power from the INA228's energy accumulator. hold_s defaults to 5 s.

    On a demo board, with an external meter: hold_s = 0 (the default there)
    waits for Enter at each step; hold_s > 0 holds each step that long for a
    logging meter. The CSV then has blank columns to fill in.
    """
    if spi is None:
        tt, spi = connect(clock_hz)
    if ina == "auto":
        import ina228
        ina = ina228.open_host_board()
    if hold_s is None:
        hold_s = 5 if ina else 0
    thresholds = thresholds or SWEEP_THRESHOLDS
    rows = ["step,threshold,expected_zero_share,gating,current_mA,current_spread_uA,vcore_V,energy_power_uW"]
    results = {}
    print("Power sweep: %.1f MHz project clock, weights %s, %s" % (
        clock_hz / 1e6, SWEEP_WEIGHTS, "INA228 on the core supply" if ina else "external meter"))

    def record(step, t, share, label, prompt):
        if ina:
            print(prompt)
            i, sd, v, p = _measure(ina, hold_s)
            print("    %.4f mA (spread %.2f uA), %.4f V, %.1f uW (energy register %.1f uW)"
                  % (i * 1e3, sd * 1e6, v, i * v * 1e6, p * 1e6))
            results[(t, label)] = i * v       # finer than the energy register over a few seconds
            rows.append("%d,%s,%s,%s,%.6f,%.3f,%.5f,%.3f" % (step, t, share, label, i * 1e3, sd * 1e6, v, p * 1e6))
        else:
            _wait_user(prompt + " Record the supply current.", hold_s)
            rows.append("%d,%s,%s,%s,,,," % (step, t, share, label))

    spi.frame(cp.write_weights(SWEEP_WEIGHTS) + cp.write_config(0, True) + cp.load_acc(0))
    record(0, "", "", "idle", "Step 0: idle, clock running, no activity.")
    step = 1
    for t in thresholds:
        share = cp.zero_share(SWEEP_WEIGHTS, t)
        for label, bypass in (("gated", False), ("ungated", True)):
            spi.set_bypass(bypass)
            spi.frame(cp.set_activity(t) + cp.run(0))
            record(step, t, "%.4f" % share, label, "Step %d: %s, threshold %d (about %.0f%% zero taps)."
                   % (step, "gated" if not bypass else "ungated (BYPASS)", t, 100 * share))
            spi.frame(cp.stop())
            step += 1
    spi.set_bypass(False)
    if results:
        print("Zeros   gated uW  ungated uW  saved uW  saved")
        for t in thresholds:
            g, u = results[(t, "gated")], results[(t, "ungated")]
            print("%4.0f%%  %9.1f  %10.1f  %8.1f  %5.1f%%" % (
                100 * cp.zero_share(SWEEP_WEIGHTS, t), g * 1e6, u * 1e6, (u - g) * 1e6,
                100 * (u - g) / u if u else 0))
    try:
        with open(log_path, "w") as f:
            f.write("\n".join(rows) + "\n")
        print("Steps written to %s%s." % (log_path, "" if ina else ": add the currents to its columns"))
    except OSError as e:
        print("could not write %s: %s" % (log_path, e))
    return rows


def main(mode="quick", clock_hz=CLOCK_HZ):
    tt, spi = connect(clock_hz)
    return run(spi, mode, log_path="results.txt")


if __name__ == "__main__":
    main()
