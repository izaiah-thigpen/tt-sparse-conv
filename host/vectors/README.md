# Test vectors

`model.bin` holds the quantized weights; each `map_NN.bin` holds one 32x32 wafer map with the outputs the
chip must produce for it (computed by `test/refmodel.py`).

**Current contents: a random model on random maps.** That fully tests the chip: every output is still
checked against the reference model. It does not show meaningful defect classes. Replace these with
vectors from the trained model (see `host/README.md`, "Training and weights") for the classification demo.
