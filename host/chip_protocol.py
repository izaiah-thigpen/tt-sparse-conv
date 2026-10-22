"""The data <-> SPI converter for the sparsity-aware convolution chip.

Runs unchanged on a PC (CPython) and on the Tiny Tapeout demo board's
RP2040 (MicroPython), so it avoids numpy, type annotations and newer
built-ins.

Three parts:
  1. Encoders: data -> the SPI bytes for each command.
  2. Decoders: the SPI bytes the chip returns -> numbers.
  3. A small integer reference (mac9, output_stage) for the smoke tests,
     identical in arithmetic to test/refmodel.py, plus readers for the
     vector files written by make_vectors.py.

SPI: mode 0, most significant bit first. A read returns its answer during
the dummy 0x00 bytes sent after the opcode. Several commands may share one
chip-select frame.
"""
import struct

# Opcodes (src/conv_chip.sv)
WRITE_WEIGHTS = 0x01
LOAD_ACC = 0x02
WRITE_CONFIG = 0x03
COMPUTE = 0x10
READ_RESULT = 0x20
READ_ACC = 0x21
READ_SKIPS = 0x22
CLEAR_SKIPS = 0x23
READ_ID = 0x7F
CHIP_ID = 0xA5

ACC_BITS = 24
ACC_MIN = -(1 << (ACC_BITS - 1))
ACC_MAX = (1 << (ACC_BITS - 1)) - 1


# ----------------------------------------------------------------------
# 1. Encoders: each returns the bytes to send, including any dummy bytes
# ----------------------------------------------------------------------

def write_weights(w9):
    """Nine signed weights (-127..127), row-major."""
    w9 = list(w9)
    if len(w9) != 9:
        raise ValueError("WRITE_WEIGHTS takes nine weights")
    for w in w9:
        if not -127 <= w <= 127:
            raise ValueError("weight out of range: %d" % w)
    return bytes([WRITE_WEIGHTS] + [w & 0xFF for w in w9])


def load_acc(value):
    """Accumulator preload (the bias), signed 24-bit, sent MSB first."""
    if not ACC_MIN <= value <= ACC_MAX:
        raise ValueError("accumulator value out of range: %d" % value)
    v = value & 0xFFFFFF
    return bytes([LOAD_ACC, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])


def write_config(shift, gate=True):
    """Output shift (0-15) and the zero-skip gating enable."""
    if not 0 <= shift <= 15:
        raise ValueError("shift out of range: %d" % shift)
    return bytes([WRITE_CONFIG, (shift & 0x0F) | (0x10 if gate else 0)])


def compute(p9):
    """Nine unsigned pixels (0-255): adds nine products to the accumulator."""
    p9 = list(p9)
    if len(p9) != 9:
        raise ValueError("COMPUTE takes nine pixels")
    for p in p9:
        if not 0 <= p <= 255:
            raise ValueError("pixel out of range: %d" % p)
    return bytes([COMPUTE] + p9)


def read_result():
    return bytes([READ_RESULT, 0])


def read_acc():
    return bytes([READ_ACC, 0, 0, 0])


def read_skips():
    return bytes([READ_SKIPS, 0, 0])


def clear_skips():
    return bytes([CLEAR_SKIPS])


def read_id():
    return bytes([READ_ID, 0])


def value_frame(groups, bias):
    """One output value in one frame: LOAD_ACC, then WRITE_WEIGHTS + COMPUTE
    per input channel, then READ_RESULT. groups = [(pixels9, weights9), ...].
    Skips WRITE_WEIGHTS when weights=None (already loaded). The result is the
    last byte returned."""
    out = bytearray(load_acc(bias))
    for pix, wts in groups:
        if wts is not None:
            out += write_weights(wts)
        out += compute(pix)
    out += read_result()
    return bytes(out)


# ----------------------------------------------------------------------
# 2. Decoders: the bytes received in a frame -> numbers
# ----------------------------------------------------------------------

def decode_result(rx):
    return rx[-1]


def decode_acc(rx):
    v = (rx[-3] << 16) | (rx[-2] << 8) | rx[-1]
    return v - (1 << 24) if v & 0x800000 else v


def decode_skips(rx):
    return (rx[-2] << 8) | rx[-1]


def decode_id(rx):
    return rx[-1]


# ----------------------------------------------------------------------
# 3a. Integer reference (same arithmetic as test/refmodel.py)
# ----------------------------------------------------------------------

def mac9(pixels, weights, acc=0):
    """Returns (accumulator, skipped taps). A tap is skipped when its pixel
    or weight is zero; skipping never changes the sum."""
    skips = 0
    for p, w in zip(pixels, weights):
        if p == 0 or w == 0:
            skips += 1
        else:
            acc += p * w
    return acc, skips


def output_stage(acc, shift):
    """Arithmetic shift right (rounds toward -infinity), then clamp to 0..255."""
    v = acc >> shift
    return 0 if v < 0 else (255 if v > 255 else v)


def window(img, h, w, r, c):
    """The 3x3 window at (r, c) of one h x w channel stored row-major in img."""
    base = r * w + c
    return [img[base], img[base + 1], img[base + 2],
            img[base + w], img[base + w + 1], img[base + w + 2],
            img[base + 2 * w], img[base + 2 * w + 1], img[base + 2 * w + 2]]


def maxpool2(chan, h, w):
    """2x2 max pooling of one h x w channel; drops an odd last row/column."""
    h2, w2 = h // 2, w // 2
    out = bytearray(h2 * w2)
    for r in range(h2):
        for c in range(w2):
            i = 2 * r * w + 2 * c
            out[r * w2 + c] = max(chan[i], chan[i + 1], chan[i + w], chan[i + w + 1])
    return out


# ----------------------------------------------------------------------
# 3b. Vector files (written by make_vectors.py)
# ----------------------------------------------------------------------
#
# model.bin, little-endian:
#   "WAFM" u16 version u16 n1 u16 n2 u16 n_classes u16 fc_in
#   w1  n1*9 int8           b1 n1 int32     sh1 n1 uint8
#   w2  n2*n1*9 int8        b2 n2 int32     sh2 n2 uint8
#   s_out2 n2 float32       fc_w n_classes*fc_in float32    fc_b n_classes float32
#   u16 length + class names (UTF-8, newline separated)
#
# map_NN.bin, little-endian:
#   "WAFV" u16 version u8 label u8 expected_prediction u8 h u8 w
#   x       h*w uint8                         the wafer map
#   conv1   n1*(h-2)*(w-2) uint8              expected layer-1 outputs
#   conv2   n2*h2*w2 uint8                    expected layer-2 outputs
#   skips1  n1 uint32, skips2 n2 uint32       expected skipped taps per kernel

MODEL_MAGIC = b"WAFM"
MAP_MAGIC = b"WAFV"
VERSION = 1


class Model:
    def __init__(self, data):
        if data[:4] != MODEL_MAGIC:
            raise ValueError("not a model.bin file")
        ver, n1, n2, ncls, fc_in = struct.unpack_from("<HHHHH", data, 4)
        if ver != VERSION:
            raise ValueError("model.bin version %d, expected %d" % (ver, VERSION))
        self.n1, self.n2, self.n_classes, self.fc_in = n1, n2, ncls, fc_in
        o = 14
        self.w1 = struct.unpack_from("<%db" % (n1 * 9), data, o); o += n1 * 9
        self.b1 = struct.unpack_from("<%di" % n1, data, o); o += 4 * n1
        self.sh1 = struct.unpack_from("<%dB" % n1, data, o); o += n1
        self.w2 = struct.unpack_from("<%db" % (n2 * n1 * 9), data, o); o += n2 * n1 * 9
        self.b2 = struct.unpack_from("<%di" % n2, data, o); o += 4 * n2
        self.sh2 = struct.unpack_from("<%dB" % n2, data, o); o += n2
        self.s_out2 = struct.unpack_from("<%df" % n2, data, o); o += 4 * n2
        self._data = data
        self._fc_w = o; o += 4 * ncls * fc_in
        self.fc_b = struct.unpack_from("<%df" % ncls, data, o); o += 4 * ncls
        (n,) = struct.unpack_from("<H", data, o); o += 2
        self.class_names = bytes(data[o:o + n]).decode().split("\n")

    def kernel1(self, k):
        return self.w1[9 * k:9 * k + 9]

    def kernel2(self, k, c):
        i = (k * self.n1 + c) * 9
        return self.w2[i:i + 9]

    def classify(self, pooled2):
        """Dense layer on the host. pooled2 = per-channel 6x6 maxpooled conv2
        outputs, concatenated channel-major. Returns the scores per class."""
        per_ch = self.fc_in // self.n2
        scores = []
        for k in range(self.n_classes):
            s = self.fc_b[k]
            row = self._fc_w + 4 * k * self.fc_in
            for i in range(self.fc_in):
                v = pooled2[i]
                if v:
                    s += v * self.s_out2[i // per_ch] * struct.unpack_from("<f", self._data, row + 4 * i)[0]
            scores.append(s)
        return scores


class WaferVector:
    def __init__(self, data, n1, n2):
        if data[:4] != MAP_MAGIC:
            raise ValueError("not a map vector file")
        ver, self.label, self.expected_prediction, h, w = struct.unpack_from("<HBBBB", data, 4)
        if ver != VERSION:
            raise ValueError("map file version %d, expected %d" % (ver, VERSION))
        self.h, self.w = h, w
        self.h1, self.w1 = h - 2, w - 2
        self.h2, self.w2 = self.h1 // 2 - 2, self.w1 // 2 - 2
        o = 10
        n = h * w
        self.x = data[o:o + n]; o += n
        n = n1 * self.h1 * self.w1
        self.conv1 = data[o:o + n]; o += n
        n = n2 * self.h2 * self.w2
        self.conv2 = data[o:o + n]; o += n
        self.skips1 = struct.unpack_from("<%dI" % n1, data, o); o += 4 * n1
        self.skips2 = struct.unpack_from("<%dI" % n2, data, o)
