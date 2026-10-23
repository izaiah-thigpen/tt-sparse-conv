"""PYNQ-Z1 driver for the convolution engine overlay.

Runs the wafer-map classifier with both convolution layers on the FPGA and
pooling plus the dense layer on the ARM processor:

    from wafer_accel import WaferAccel
    acc = WaferAccel("wafer_accel.bit")
    logits, info = acc.run_network(wafer_map_32x32, quant_params)

Needs on the board, in the same folder: wafer_accel.bit, wafer_accel.hwh,
refmodel.py, and a quantized model (quant_params.npz or demo_data.npz).

Register map: see rtl/fpga/engine_regs.sv.
"""
import time

import numpy as np

import refmodel as rm

CTRL, DIMS, BIAS, W03, W47, W8, SKIPS, STATUS, START, ID = range(0, 40, 4)
ENGINE_ID = 0x5C0E0001
MAX_DIM = 63
MAX_OUT = 1024


def _pack_weights(w):
    b = [int(x) & 0xFF for x in np.asarray(w).ravel()]
    if len(b) != 9:
        raise ValueError("a kernel needs nine weights")
    return (b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24,
            b[4] | b[5] << 8 | b[6] << 16 | b[7] << 24,
            b[8])


class WaferAccel:
    def __init__(self, bitfile="wafer_accel.bit", overlay=None, allocate=None):
        """overlay/allocate can be supplied for testing off the board."""
        if overlay is None:
            from pynq import Overlay, allocate as pynq_allocate
            overlay = Overlay(bitfile)
            allocate = pynq_allocate
        self.ol = overlay
        self.dma = overlay.axi_dma
        self.eng = overlay.engine
        got = self.eng.read(ID)
        if got != ENGINE_ID:
            raise RuntimeError(f"engine ID 0x{got:08X}, expected 0x{ENGINE_ID:08X}: wrong bitstream?")
        self.in_buf = allocate(shape=(MAX_DIM * MAX_DIM,), dtype=np.uint8)
        self.out_buf = allocate(shape=(MAX_OUT,), dtype=np.uint8)
        self.gate = True

    # ------------------------------------------------------------------
    def _wait_idle(self, timeout_s=1.0):
        t0 = time.perf_counter()
        while not self.eng.read(STATUS) & 1:
            if time.perf_counter() - t0 > timeout_s:
                raise TimeoutError("engine did not go idle")

    def _pass(self, channel, weights, bias, shift, first, last):
        """One input channel through one kernel. Returns results on the last pass."""
        h, w = channel.shape
        n_pix, n_out = h * w, (h - 2) * (w - 2)
        w03, w47, w8 = _pack_weights(weights)
        self.eng.write(W03, w03)
        self.eng.write(W47, w47)
        self.eng.write(W8, w8)
        self.eng.write(BIAS, int(bias) & 0xFFFFFF)
        self.eng.write(DIMS, w | h << 8)
        self.eng.write(CTRL, int(first) | int(last) << 1 | int(self.gate) << 2 | (int(shift) & 0xF) << 8)

        self.in_buf[:n_pix] = channel.ravel()
        self.in_buf.flush()
        self.eng.write(START, 1)
        if last:
            self.dma.recvchannel.transfer(self.out_buf, nbytes=n_out)
        self.dma.sendchannel.transfer(self.in_buf, nbytes=n_pix)
        self.dma.sendchannel.wait()
        if last:
            self.dma.recvchannel.wait()
        self._wait_idle()
        if last:
            self.out_buf.invalidate()
            return np.array(self.out_buf[:n_out], dtype=np.uint8).reshape(h - 2, w - 2)
        return None

    def conv_kernel(self, image, weights, bias, shift):
        """All channels of image (C, H, W) through one kernel (C, 3, 3).
        Returns the (H-2, W-2) output and the number of skipped taps."""
        image = np.asarray(image, dtype=np.uint8)
        c, h, w = image.shape
        if not (3 <= h <= MAX_DIM and 3 <= w <= MAX_DIM and (h - 2) * (w - 2) <= MAX_OUT):
            raise ValueError(f"image {h}x{w} is outside the engine's limits")
        self.eng.write(SKIPS, 0)
        out = None
        for ch in range(c):
            out = self._pass(image[ch], weights[ch], bias, shift, ch == 0, ch == c - 1)
        return out, self.eng.read(SKIPS)

    def conv_layer(self, image, wq, bq, shifts):
        """A whole convolution layer: returns (K, H-2, W-2) and total skipped taps."""
        outs, skipped = [], 0
        for k in range(wq.shape[0]):
            o, s = self.conv_kernel(image, wq[k], int(bq[k]), int(shifts[k]))
            outs.append(o)
            skipped += s
        return np.stack(outs), skipped

    def run_network(self, wafer_map, q):
        """Classify one 32x32 wafer map (uint8 density, 0-255).
        Returns logits and a dict with feature maps, skip counts and timing."""
        t0 = time.perf_counter()
        a0 = np.asarray(wafer_map, dtype=np.uint8)[None]
        c1, s1 = self.conv_layer(a0, q["w1"], q["b1"], q["sh1"])
        p1 = rm.maxpool2(c1[None])[0]
        c2, s2 = self.conv_layer(p1, q["w2"], q["b2"], q["sh2"])
        p2 = rm.maxpool2(c2[None])[0]
        feats = p2.astype(np.float64) * q["s_out2"][:, None, None]
        logits = feats.ravel() @ q["fc_w"].T.astype(np.float64) + q["fc_b"]
        taps1 = c1.size * 9 * a0.shape[0]
        taps2 = c2.size * 9 * p1.shape[0]
        return logits, {
            "conv1": c1, "conv2": c2,
            "skipped": (s1, s2), "taps": (taps1, taps2),
            "seconds": time.perf_counter() - t0,
        }
