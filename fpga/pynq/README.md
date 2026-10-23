# Running the classifier on the PYNQ-Z1

The FPGA runs both convolution layers through the engine in `fpga/rtl/`; the board's ARM processor does
pooling and the dense layer in Python. The notebook checks every hardware result against `refmodel.py`.

## 1. Build the overlay (on your PC, with Vivado)

Any recent Vivado works; Vivado ML Standard (the free edition) supports the Zynq-7020.

```
cd fpga/pynq
vivado -mode batch -source build_overlay.tcl
```

It takes 10 to 20 minutes and writes `fpga/pynq/overlay/wafer_accel.bit`, `overlay/wafer_accel.hwh`, and timing and
utilization reports. The last line printed is the worst negative slack: positive means 100 MHz timing is met.

If a step fails, the Vivado project is left in `fpga/pynq/build/`; open it in the Vivado GUI to see the block design.
The script uses the PYNQ-Z1 board files if installed, and works without them.

## 2. Make the demo data (on your PC)

```
cd model
python export_demo_data.py --data data/wm811k_32_density.npz --run runs/d_k16_all --out ../fpga/pynq/demo_data.npz
```

This bundles 20 test maps per class (fewer for rare classes) with the quantized model.

## 3. Copy to the board

Boot the PYNQ-Z1 with a current PYNQ image, connect it by Ethernet, and open Jupyter at `http://pynq:9090`
(password `xilinx`). Make a folder and upload:

| File | From |
| --- | --- |
| `wafer_accel.bit`, `wafer_accel.hwh` | `fpga/pynq/overlay/` |
| `wafer_accel.py`, `demo.ipynb`, `demo_data.npz` | `fpga/pynq/` |
| `refmodel.py` | `test/` |

The `.bit` and `.hwh` files must keep the same name.

## 4. Run

Open `demo.ipynb` and run all cells. It classifies one wafer map with feature-map plots, then the whole
demo set, and reports accuracy, agreement with the reference model, the share of skipped
multiply-accumulates, and time per map.

## If something goes wrong

| Symptom | Likely cause |
| --- | --- |
| `engine ID 0x... expected 0x5C0E0001` | The `.bit` and `.hwh` are from different builds, or a different bitstream loaded |
| `AttributeError: ... axi_dma` or `engine` | Block design cell names changed; they must be `axi_dma` and `engine` |
| DMA `wait()` never returns | Check the build's timing report, and that the DMA stream widths are 8 bits |
| Results differ from the reference model | Send me the map index and the first differing values |

## Recorded run

`demo.ipynb` is saved with the outputs of the first hardware run (PYNQ-Z1, October 22, 2026):

| Result | |
| --- | --- |
| Maps | 180 test maps, 20 per class |
| Agreement with the reference model | bit-exact on every convolution output; 180 of 180 predictions match |
| Accuracy | 75.6% (the demo set is class-balanced, so this is lower than the full test set's) |
| Multiply-accumulates skipped | 68.1% |
| Time per map | 302 ms, mostly Python on the ARM processor |
| Gating on vs off | identical results |
| Overlay timing | 100 MHz met, worst slack +1.81 ns |

## Connecting the board directly to a PC

With no router, the board gets no address. Over the USB serial console (115200 baud, user and password
`xilinx`):

```
sudo pkill dhclient; sudo pkill dhcpcd
sudo ip addr flush dev eth0
sudo ip addr add 192.168.2.99/24 dev eth0
```

Give the PC's Ethernet adapter the fixed address 192.168.2.1, mask 255.255.255.0, then open
`http://192.168.2.99:9090`. The setting lasts until the board reboots.
