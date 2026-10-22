# Test vectors

`model.bin` holds the trained model's quantized weights; each `map_NN.bin` holds one 32x32 wafer map from the
WM-811K test set with every output the chip must produce for it (computed by `test/refmodel.py`).

**Current contents: the trained model** (`model/`, 16 + 16 kernels, test macro F1 0.82) and one test map per
class. The model classifies 7 of these 9 correctly:

| File | True class | Model predicts |
| --- | --- | --- |
| map_00.bin | Center | Center |
| map_01.bin | Donut | Donut |
| map_02.bin | Edge-Loc | Loc |
| map_03.bin | Edge-Ring | Edge-Ring |
| map_04.bin | Loc | Loc |
| map_05.bin | Near-full | Near-full |
| map_06.bin | Random | Random |
| map_07.bin | Scratch | none |
| map_08.bin | none | none |

The chip test checks that the chip reproduces the model output by output, so a PASS means the chip's answer
equals the model's, including the two the model gets wrong. Regenerate with `model/README.md`, "From trained
model to chip test vectors".
