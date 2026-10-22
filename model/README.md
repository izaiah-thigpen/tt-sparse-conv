# The neural network: training and weights

The chip runs the two convolution layers of WaferNet, a small CNN that classifies wafer-map defect patterns.
This folder trains it on a PC and turns it into the 8-bit integers the chip uses. The chip itself never trains
and stores no weights: the host sends them with every computation (see `host/README.md`).

## The model

| | |
| --- | --- |
| Data | WM-811K: 811,457 production wafer maps, 172,950 labeled with 9 classes (8 defect patterns and "none") |
| Input | 32×32 map, each cell = share of failing dies in that area × 255 ("density" resize) |
| Network | conv 3×3, 16 kernels → 2×2 max pool → conv 3×3, 16 kernels → 2×2 max pool → dense, 9 classes; 7,673 parameters |
| On the chip | both convolutions; pooling and the dense layer run on the host |
| Split | by production lot (no lot in both training and test) |
| Accuracy | test macro F1 0.819 (floating point), 0.820 (8-bit integer, as the chip computes) |
| Sparsity | 77% of the chip's multiplies have a zero operand |

`net.py` defines the network. `test/refmodel.py` is the bit-exact integer model of the chip; the quantizer, the
chip tests and the board's test vectors all use it, so the model that sets accuracy is the model that checks
the hardware.

## Reproducing it

Needs Python 3 with `torch numpy pandas scikit-learn matplotlib`, and `LSWMD.pkl` from the WM-811K dataset.
From this folder:

```
python prepare_data.py --pkl LSWMD.pkl --out data/wm811k_32_density.npz --resize density --split lot
python train_float.py --data data/wm811k_32_density.npz --out runs/d_k16_all --n1 16 --n2 16 --none-cap 0
python quantize.py --run runs/d_k16_all --data data/wm811k_32_density.npz
```

1. **prepare_data.py** resizes every labeled map to 32×32 and splits by lot into training, validation and test.
2. **train_float.py** trains in floating point. Class imbalance is handled by weighting the loss by inverse
   class frequency to the power 0.5, with every "none" map kept (`--none-cap 0`). Writes the best model by
   validation macro F1, per-class results and a confusion matrix.
3. **quantize.py** converts weights to signed 8-bit, biases to 24-bit and picks a power-of-two output shift
   per kernel, then checks the integer network against the chip model value by value and reports its accuracy.
   Writes `runs/d_k16_all/quant/quant_params.npz`.

## From trained model to chip test vectors

```
python export_demo_data.py --data data/wm811k_32_density.npz --run runs/d_k16_all --out demo_data.npz
python ../host/make_vectors.py --demo demo_data.npz --out ../host/vectors --per-class 1
```

`export_demo_data.py` bundles the quantized weights and a few test maps per class; `make_vectors.py` writes
`model.bin` and one `map_NN.bin` per map, with every output the chip must produce. A different trained model
needs only new vector files, not a new chip.
