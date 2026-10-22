"""Copy a liberty file, keeping only cells a synthesis tool should use.

Drops low-power-flow, probe, spare, delay, fill, tap, decap and diode cells,
the same families OpenLane/LibreLane keep out of synthesis.

    python filter_lib.py in.lib out.lib
"""
import re
import sys

DROP = re.compile(r"sky130_fd_sc_hd__(lpflow_|probe|macro_|dlygate|dlymetal|clkdlybuf|clkdlyinv|"
                  r"fill|tap|decap|diode|lpflow|dlrbn|dlrbp|dlrtn|dlrtp|dlxbn|dlxbp|dlxtn|dlxtp|"
                  r"sdlclkp|dlclkp|einv|ebuf|clkinvlp|buf_16|bufbuf|bufinv)")


def main(src, dst):
    text = open(src).read()
    out, i, kept, dropped = [], 0, 0, 0
    for m in re.finditer(r'\n(\s*)cell \("([^"]+)"\)\s*\{', text):
        start = m.start()
        if start < i:
            continue
        depth, j = 0, m.end() - 1
        while True:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(text[i:start])
        if DROP.match(m.group(2)):
            dropped += 1
        else:
            out.append(text[start:j + 1])
            kept += 1
        i = j + 1
    out.append(text[i:])
    open(dst, "w").write("".join(out))
    print("kept %d cells, dropped %d" % (kept, dropped))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
