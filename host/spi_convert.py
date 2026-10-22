"""Print the exact SPI bytes for one output value, and the reply to expect.

For testing with any SPI adapter or for reading a logic-analyzer capture:

    python spi_convert.py vectors/model.bin vectors/map_00.bin conv1 --kernel 3 --row 10 --col 12
    python spi_convert.py vectors/model.bin vectors/map_00.bin conv2 --kernel 0 --row 5 --col 5

Shows each command with its bytes (hex) and meaning, then the byte the chip
must return for READ_RESULT. Layer-2 inputs are the 2x2 maxpooled layer-1
outputs, taken from the expected values in the map file.
"""
import argparse

import chip_protocol as cp


def hexs(b):
    return " ".join("%02X" % x for x in b)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("map")
    ap.add_argument("layer", choices=["conv1", "conv2"])
    ap.add_argument("--kernel", type=int, default=0)
    ap.add_argument("--row", type=int, default=0)
    ap.add_argument("--col", type=int, default=0)
    args = ap.parse_args()

    m = cp.Model(open(args.model, "rb").read())
    v = cp.WaferVector(open(args.map, "rb").read(), m.n1, m.n2)
    k, r, c = args.kernel, args.row, args.col

    if args.layer == "conv1":
        if not (0 <= k < m.n1 and 0 <= r < v.h1 and 0 <= c < v.w1):
            ap.error("kernel/row/col out of range")
        bias, shift = m.b1[k], m.sh1[k]
        groups = [(cp.window(v.x, v.h, v.w, r, c), list(m.kernel1(k)))]
        expected = v.conv1[(k * v.h1 + r) * v.w1 + c]
    else:
        if not (0 <= k < m.n2 and 0 <= r < v.h2 and 0 <= c < v.w2):
            ap.error("kernel/row/col out of range")
        bias, shift = m.b2[k], m.sh2[k]
        hp, wp = v.h1 // 2, v.w1 // 2
        groups = []
        for ch in range(m.n1):
            chan = v.conv1[ch * v.h1 * v.w1:(ch + 1) * v.h1 * v.w1]
            pooled = cp.maxpool2(chan, v.h1, v.w1)
            groups.append((cp.window(pooled, hp, wp, r, c), list(m.kernel2(k, ch))))
        expected = v.conv2[(k * v.h2 + r) * v.w2 + c]

    print("%s kernel %d, output (%d, %d): bias %d, shift %d, %d input channel(s)\n"
          % (args.layer, k, r, c, bias, shift, len(groups)))
    print("Frame 1  " + hexs(cp.write_config(shift, True)) + "   WRITE_CONFIG shift=%d, gating on" % shift)
    print("Frame 2  " + hexs(cp.load_acc(bias)) + "   LOAD_ACC %d" % bias)
    acc = bias
    for i, (pix, wts) in enumerate(groups):
        print("         " + hexs(cp.write_weights(wts)) + "   WRITE_WEIGHTS ch %d: %s" % (i, wts))
        print("         " + hexs(cp.compute(pix)) + "   COMPUTE ch %d: %s" % (i, pix))
        acc, _ = cp.mac9(pix, wts, acc)
    print("         " + hexs(cp.read_result()) + "   READ_RESULT")
    print("\nAccumulator after the last COMPUTE: %d" % acc)
    print("Expected reply: the last byte of frame 2 = 0x%02X (%d)" % (expected, expected))
    assert cp.output_stage(acc, shift) == expected, "map file and recomputation disagree"


if __name__ == "__main__":
    main()
