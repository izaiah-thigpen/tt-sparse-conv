"""Text of the SoutheastCon 2027 submissions: a 2-page extended abstract and a 6-page full paper.
Every number comes from the tt-sparse-conv repository (power/results/power.csv, the layout
reports, the FPGA run and the model metrics)."""
F = '/home/claude/figs/'

TITLE = 'A Zero-Skipping Convolution Core for|Wafer‑Map Defect Classification in|Open‑Source 130 nm CMOS'
KEYWORDS = 'wafer map, defect classification, CNN accelerator, sparsity, operand isolation, low-power design, open-source silicon'

REFS = [
    'M.-J. Wu, J.-S. R. Jang, and J.-L. Chen, “Wafer map failure pattern recognition and similarity ranking for large-scale data sets,” *IEEE Trans. Semicond. Manuf.*, vol. 28, no. 1, pp. 1–12, 2015.',
    'T. Nakazawa and D. V. Kulkarni, “Wafer map defect pattern classification and image retrieval using convolutional neural network,” *IEEE Trans. Semicond. Manuf.*, vol. 31, no. 2, pp. 309–314, 2018.',
    'N. Yu, Q. Xu, and H. Wang, “Wafer defect pattern recognition and analysis based on convolutional neural network,” *IEEE Trans. Semicond. Manuf.*, vol. 32, no. 4, pp. 566–573, 2019.',
    'S. Lafrance and S. Bernadin, “Evaluating visual transformers for wafer defect detection: A feasibility study,” in *Proc. IEEE SoutheastCon*, 2025, pp. 1288–1293.',
    'Y.-H. Chen, T. Krishna, J. S. Emer, and V. Sze, “Eyeriss: An energy-efficient reconfigurable accelerator for deep convolutional neural networks,” *IEEE J. Solid-State Circuits*, vol. 52, no. 1, pp. 127–138, 2017.',
    'J. Albericio, P. Judd, T. Hetherington, T. Aamodt, N. Enright Jerger, and A. Moshovos, “Cnvlutin: Ineffectual-neuron-free deep neural network computing,” in *Proc. ISCA*, 2016, pp. 1–13.',
    'A. Parashar *et al.*, “SCNN: An accelerator for compressed-sparse convolutional neural networks,” in *Proc. ISCA*, 2017, pp. 27–40.',
    'M. Münch, B. Wurth, R. Mehra, J. Sproch, and N. Wehn, “Automating RT-level operand isolation to minimize power consumption in datapaths,” in *Proc. DATE*, 2000, pp. 624–631.',
    'M. Venn, “Tiny Tapeout: A shared silicon tape out platform accessible to everyone,” *IEEE Solid-State Circuits Mag.*, vol. 16, no. 2, pp. 20–29, 2024.',
]
REF_KYEONG = 'K. Kyeong and H. Kim, “Classification of mixed-type defect patterns in wafer bin maps using convolutional neural networks,” *IEEE Trans. Semicond. Manuf.*, vol. 31, no. 3, pp. 395–402, 2018.'

FIG1 = 'The MAC core. On a zero tap, the zero-skip path (orange) holds the input registers, so the multiplier inputs do not toggle, keeps the accumulator from updating, and counts the tap. gate_en is low when BYPASS is set.'
FIG2 = 'Simulated power saving from zero-skipping against the share of zero pixels: the MAC’s dynamic power (power above idle) and the whole chip’s power, gated versus BYPASS.'

POWER_HDR_SHORT = ['Zero share', 'MAC gated (µW)', 'MAC BYPASS (µW)', 'MAC dynamic saving', 'Chip saving']
POWER_ROWS_SHORT = [['25%', '311.6', '333.4', '10.2%', '2.1%'],
                    ['50%', '258.1', '300.3', '23.3%', '4.2%'],
                    ['75%', '200.1', '260.3', '42.8%', '6.2%'],
                    ['90%', '156.1', '227.9', '66.3%', '7.7%']]


def abstract(d):
    d.title(TITLE)
    d.author_break()
    d.abstract('Wafer maps are mostly blank, so 77% of the multiplications in a compact convolutional neural network (CNN) that classifies WM-811K wafer-map defects have a zero operand. We present a single-MAC convolution core that detects zero operands and holds its multiplier inputs (operand isolation), fabricated through Tiny Tapeout in SkyWater 130 nm and validated on an FPGA. Gate-level simulation shows the gating cuts the MAC’s dynamic power by 23% at 50% zeros and 66% at 90%, but the whole chip’s power by at most 7.7%, because flip-flop clock power dominates.')
    d.keywords(KEYWORDS)

    d.h1('Introduction')
    d.body('Every fabricated wafer is tested die by die, and the spatial pattern of failing dies points to its cause in the process. The WM-811K dataset holds 811,457 production wafer maps [1], and CNNs classify their defect patterns well [2], [3]; at SoutheastCon 2025, vision transformers were evaluated for the same task [4]. These models run on servers. Classifying wafers at the tester or in an embedded instrument calls for small, low-power hardware.')
    d.body('Wafer maps suit such hardware because they are sparse: most of a map has no failing die, and ReLU activations add more zeros. A multiplication with a zero operand adds nothing to the sum, so its switching energy is wasted. Large accelerators already exploit this. Eyeriss gates its datapath on zero activations and reduces processing-element power by 45% [5]; Cnvlutin skips zero activations, about 44% of convolution inputs in the networks it studied [6]; SCNN skips zero weights and activations together [7]. The underlying circuit technique, operand isolation, is well established [8]. Less is known about what zero-skipping buys in a very small core, where the clock network and control logic are a large share of the power.')
    d.body('This work co-designs a compact wafer-map CNN with a zero-skipping multiply-accumulate (MAC) core, fabricates the core through Tiny Tapeout [9], and uses gate-level power analysis to show where the savings appear and where they do not.')

    d.h1('Design')
    d.h2('Network')
    d.body('Each wafer map is resized to a 32 × 32 grid whose cells hold the share of failing dies, scaled to 0–255. The network has two 3 × 3 convolution layers of 16 kernels, each followed by 2 × 2 max pooling, and a dense layer with nine outputs, for 7,673 parameters. Trained on WM-811K with training and test sets split by production lot, it reaches a macro F1 score of 0.819 in floating point and 0.820 in 8-bit integer arithmetic. The two convolutions perform 518,976 of the network’s 524,160 multiplications per wafer, and 77% of them have a zero operand over the test set.')
    d.h2('Zero-Skipping Core')
    d.body('Fig. 1 shows the MAC. A tap (one pixel and one weight) is a zero tap when either operand is zero. The input registers then keep their previous values, so the multiplier inputs do not toggle, and the 24-bit accumulator does not update; the result is the same as adding zero. A saturating 16-bit counter records zero taps, and a BYPASS input disables the gating for comparison. The output stage shifts the accumulator and clamps it to 0–255, which also implements ReLU. A host sends weights and pixels over SPI, so the core computes any 3 × 3 layer; pooling and the dense layer run on the host. An on-chip activity mode drives the MAC with pseudo-random pixels at a programmable share of zeros for power measurement.')
    d.figure(F + 'fig1_mac.png', FIG1)
    d.h2('Implementation')
    d.body('The core occupies two Tiny Tapeout tiles in SkyWater 130 nm with 2,690 standard cells, meets 50 MHz at all process corners with 1.77 ns of worst-case setup slack, and passes DRC and LVS. It has been submitted for fabrication.')

    d.h1('Experimental Setup')
    d.body('The synthesized gate-level netlist was simulated in Icarus Verilog in activity mode at 0, 25, 50, 75 and 90% zero pixels, once with the gating on and once with BYPASS. The recorded switching activity was annotated into OpenSTA to compute power at the typical corner (25 °C, 1.8 V, 50 MHz). Separately, a nine-MAC version of the datapath was implemented on a Zynq-7020 FPGA (PYNQ-Z1) at 100 MHz and compared against the integer reference model.')

    d.h1('Results and Discussion')
    d.body('Table I and Fig. 2 summarize the results. The gating reduces the MAC’s dynamic power (its power above idle) by 10.2% at 25% zeros, rising to 66.3% at 90%. At the chip level the saving is only 2.1% to 7.7%. The reason is the clock: running with no computation, the chip draws 709 µW of the 1,071 µW it draws at full activity, almost all of it clock power in its 344 flip-flops, which operand isolation leaves untouched. Zero-skipping removes most of the arithmetic’s switching, but at this scale the clock network sets the total, and gating the MAC registers’ clock on zero taps is the natural next step. On the FPGA, all 180 test wafer maps matched the integer reference model bit for bit.')
    d.table('Simulated Power, Typical Corner, 50 MHz', POWER_HDR_SHORT, POWER_ROWS_SHORT, [42, 48, 52, 52, 49])
    d.figure(F + 'fig2_power.png', FIG2)
    d.body('Fig. 3 shows why. It splits the chip’s power into a fixed clock floor, the extra flip-flop power caused by changing data, and the combinational logic. Zero-skipping shrinks the two upper parts, the combinational logic most, but the 709 µW floor does not move, so the chip-level saving stays small however sparse the data. Per clock cycle, the MAC’s dynamic energy falls from 4.7 pJ per tap with no zeros to 0.73 pJ at 90% zeros, while the chip still spends 14.2 pJ per cycle on the clock floor.')
    d.figure(F + 'fig4_breakdown.png', 'Simulated chip power by component for BYPASS (B) and gated (G) operation at each share of zero pixels. The clock floor, drawn by the flip-flops with the clock running and no computation, does not change.')
    d.body('Clock gating is the natural next step. The MAC accounts for 119.6 µW of the idle floor; if gating also stopped the clock to the MAC’s registers on every zero tap, and that share fell in proportion to the zero share, the chip-level saving would rise to at most about 10% at 50% zeros and 19% at 90%. The rest of the floor belongs mostly to the SPI interface and control logic, which a larger MAC array would share.')
    d.body('The fabricated chips are expected in mid-2027. A host board with a current monitor on the 1.8 V core supply will measure the activity-mode sweep on silicon to test these predictions.')

    d.h5('Acknowledgment')
    d.body('The authors thank Tiny Tapeout and San José State University for supporting the fabrication of this design.')
    d.h5('References')
    d.refs(REFS)


def full(d):
    d.title(TITLE)
    d.author_break()
    d.abstract('Wafer maps are mostly blank, so most of the multiplications in a convolutional neural network (CNN) that classifies them have a zero operand: 77% in the compact network presented here, which classifies the nine WM-811K defect classes with a macro F1 score of 0.820 in 8-bit integer arithmetic. We present a single multiply-accumulate (MAC) convolution core that detects zero operands and holds its multiplier inputs (operand isolation), fabricated through Tiny Tapeout in SkyWater 130 nm, and a nine-MAC version on a Zynq FPGA that matches the integer reference model on all 180 test maps. Gate-level power simulation shows the gating cuts the MAC’s dynamic power by 23% at 50% zeros and 66% at 90%, but the whole chip’s power by at most 7.7%: two-thirds of the chip’s power is clock power in its flip-flops, which operand isolation does not touch. The results show where zero-skipping pays off in a very small accelerator and point to clock gating as the next step.')
    d.keywords(KEYWORDS)

    d.h1('Introduction')
    d.body('Every fabricated wafer is tested die by die, and the result is a map of which dies passed and which failed. The spatial pattern of the failures points to its cause in the process: a ring at the wafer edge, a cluster in the center and a scratch line come from different problems. Classifying these patterns automatically is a long-standing problem in semiconductor manufacturing. The WM-811K dataset, 811,457 maps from real production [1], made it a benchmark, and CNNs now classify its patterns well [2], [3]; vision transformers have also been evaluated for the task at SoutheastCon [4].')
    d.body('These models run on servers. Classifying wafers where the data is produced, at the tester or inside an embedded instrument, calls for small, low-power hardware, and wafer maps have a property that makes such hardware attractive: they are sparse. Most of a typical map has no failing die, and the ReLU activations inside the network add more zeros. A multiplication with a zero operand adds nothing to the result, so the energy spent switching the multiplier is wasted.')
    d.body('Large accelerators already exploit zeros [5]–[7], and the circuit technique that keeps a unit’s inputs still when its result is not needed, operand isolation, is decades old [8]. What is less clear is how much of that saving survives in a very small core, where a single MAC shares the chip with its clock network, control logic and interface. This paper answers that question with a design that has been taken from model training to a chip in fabrication. Its contributions are:')
    d.bullet_body(['a compact wafer-map CNN (7,673 parameters) co-designed with an 8-bit integer datapath, whose convolutions have 77% zero operands;',
                   'a zero-skipping MAC core with an on-chip activity mode for power measurement, fabricated through Tiny Tapeout [9] in SkyWater 130 nm, and a nine-MAC FPGA version validated on hardware;',
                   'a gate-level power analysis that separates the MAC from the rest of the chip and shows that the clock, not the arithmetic, sets the chip’s power at this scale.'])

    d.h1('Background and Related Work')
    d.h2('Wafer-Map Classification')
    d.body('Wu, Jang and Chen introduced WM-811K and recognized failure patterns and ranked similar wafers using hand-designed features [1]. CNNs then replaced the features: Nakazawa and Kulkarni classified wafer maps with a CNN and used it to retrieve similar maps [2], Yu, Xu and Wang combined defect detection with pattern recognition and similarity ranking for root-cause analysis [3], and Kyeong and Kim extended CNNs to wafers that carry several patterns at once [10]. Lafrance and Bernadin evaluated vision transformers for wafer defect detection [4]. Closer to the goal here, Shin and Yoo compared lightweight networks (EfficientNetV2, ShuffleNetV2, MobileNetV2 and MobileNetV3) for wafer bin maps, aiming for models that can run in a manufacturing line without high-performance hardware [11]. These works pursue accuracy with networks sized for servers; the network here is deliberately small so that it fits a single-MAC chip, and is compared with them on size rather than accuracy.')
    d.h2('Exploiting Zeros in Accelerators')
    d.body('Eyeriss, a 168-processing-element CNN accelerator, detects zero input activations and gates its datapath, reducing processing-element power by 45% [5]. Cnvlutin found that about 44% of convolution-layer inputs are zero in the networks it studied and skipped them for a 1.37× average speedup [6]. SCNN skips zero weights and zero activations together and reports 2.7× performance and 2.3× energy efficiency over a comparable dense design [7]. Recent edge designs carry the idea to lower power. Liu et al. skip zeros in whichever of the activations or weights is sparser, reaching 2.41 TOPS/W on VGG16 in 55 nm CMOS [12], and Qin et al. combine 50% sparsity with zero skipping in a 10.60 µW accelerator in 40 nm CMOS for arrhythmia detection [13]. These works report the efficiency of the whole design; they do not isolate how much of the zero-skipping saving survives the fixed clock and control overhead, which is the question for a very small core.')
    d.h2('Operand Isolation and Clock Power')
    d.body('Operand isolation blocks a unit’s inputs when its output will not be used, so the unit’s internal nodes stop switching; Münch et al. automated it at register-transfer level and reported power reductions of up to about 30% [8]. It reduces data switching only. The registers it controls are still clocked, so clock power is unchanged, which matters most when the datapath is small relative to the clocked logic around it.')
    d.h2('Open-Source Silicon')
    d.body('Tiny Tapeout places many small designs on one shared die in an open-source process, so a student design can be fabricated at low cost [9]. Designs use the open SkyWater 130 nm PDK and the OpenROAD-based LibreLane flow, and the platform has already been used for small research chips, for example a neural-signal modulation platform for IoT applications [14].')

    d.h1('Network Design')
    d.body('Each WM-811K map stores one value per die position: 0 for no die, 1 for a die that passed, 2 for one that failed. Because products differ in die size, the grids differ in size too. Each map is resized to a 32 × 32 grid of cells, and each cell holds the share of its dies that failed, scaled to 0–255 (Fig. 1). A cell with no failing die is exactly zero, which on a typical wafer is most cells; this “failure-density” encoding is what makes the input sparse.')
    d.figure(F + 'fig3_input.png', 'A wafer map (a generated Donut pattern in WM-811K’s format, shown because its full die grid fits) and the 32 × 32 network input made from it.')
    d.body('Engineers labeled 172,950 of the WM-811K maps with one of nine classes: eight defect patterns (Center, Donut, Edge-Loc, Edge-Ring, Loc, Near-full, Random and Scratch) and “none.” The classes are severely imbalanced: 147,431 labeled maps are “none,” while the rarest pattern, Near-full, has only 149 examples and Donut 555. Overall accuracy is therefore a poor measure, since a classifier that always answers “none” would score 85%; this work reports the macro F1 score, the unweighted mean of the nine per-class F1 scores, which weights the rare patterns equally. Fig. 2 shows one real test map from each class after the resize.')
    d.figure(F + 'fig5_classes.png', 'One real WM-811K test map per class after the 32 × 32 resize (darker cells have more failing dies), with the answer of the 8-bit integer network below each. Edge-Loc against Loc and faint Scratch patterns against none are the hardest distinctions.')
    d.body('Table I lists the network. Pooling and the dense layer run on the host; the chip computes the two convolutions, 518,976 of the 524,160 multiplications per wafer. The network was trained in PyTorch on the 172,950 labeled WM-811K maps with training and test sets split by production lot, so that no lot appears in both. It was then quantized to 8-bit weights and activations, with a power-of-two right shift per kernel in place of a rescaling multiply, which is what the chip’s output stage implements. Activation scales map the 99.99th percentile of each layer’s activations on the training set to 255, and biases are pre-scaled so that they can be loaded directly into the accumulator. The macro F1 score over the nine classes is 0.819 in floating point and 0.820 after quantization. Over the test set, 77% of the convolution multiplications have a zero pixel or a zero weight. The zeros come from the input encoding, where blank regions of the wafer stay blank, and from the ReLU after the first layer.')
    d.table('Network Layers', ['Layer', 'Output', 'Multiplies', 'Runs on'],
            [['Input', '1 × 32 × 32', '–', '–'],
             ['Conv 3 × 3, 16 kernels', '16 × 30 × 30', '129,600', 'chip'],
             ['Max pool 2 × 2', '16 × 15 × 15', '–', 'host'],
             ['Conv 3 × 3 × 16, 16 kernels', '16 × 13 × 13', '389,376', 'chip'],
             ['Max pool 2 × 2', '16 × 6 × 6', '–', 'host'],
             ['Dense, 576 → 9', '9 scores', '5,184', 'host']],
            [88, 62, 50, 40])

    d.h1('Hardware Architecture')
    d.h2('Zero-Skipping MAC')
    d.body('Fig. 3 shows the MAC, a two-stage pipeline that accepts one tap (a pixel and a weight) per clock. A tap is a zero tap when either operand is zero, detected combinationally on the incoming values. With gating enabled, a zero tap leaves the input registers holding their previous values, so the 9 × 8-bit signed multiplier sees unchanged inputs and does not switch, and the 24-bit accumulator is not updated in the next cycle. Because adding zero changes nothing, the accumulated result is identical with gating on or off; only the switching activity differs. A saturating 16-bit counter counts zero taps in both modes, so gated and ungated runs can be compared directly, and a BYPASS pin (or a configuration bit) turns the gating off. The output stage shifts the accumulator right by a per-kernel amount and clamps the result to 0–255; since the output is unsigned, the lower clamp is also the ReLU.')
    d.figure(F + 'fig1_mac.png', FIG1)
    d.body('Fig. 4 follows one output pixel of the first layer through the MAC, using a real window of the wafer in Fig. 1 and a real trained kernel. The host first loads the kernel\u2019s bias, \u221210,403, into the accumulator. Of the nine taps, three have a zero pixel; the MAC holds its inputs for those cycles and adds only the six nonzero products, which sum to 16,746. The accumulator ends at 6,343, and the output stage shifts it right by seven bits and clamps it, giving an output pixel of 49. The skip counter records three zero taps.')
    d.figure(F + 'fig7_pixel.png', 'One output pixel of the first layer, computed with a trained kernel on a window of the wafer in Fig. 1. Gray taps have a zero operand and are skipped: bias −10,403 + products 16,746 = 6,343; shifted right 7 bits and clamped, the output is 49.')
    d.h2('Interface and Activity Mode')
    d.body('A host drives the chip as an SPI mode-0 slave, with two-flop synchronizers on the SPI inputs. Commands load the bias into the accumulator, write the nine weights, stream nine pixels for one output (COMPUTE), and read back the result, the accumulator and the skip counter. Because weights are sent with every computation, the chip stores no model and can compute any 3 × 3 convolution layer; a multi-channel output is accumulated over several COMPUTE commands before it is read. Table II lists the commands. The system clock must be at least eight times the SPI clock for the synchronizers, so at a 50 MHz system clock the SPI link runs at up to about 6 MHz.')
    d.table('SPI Commands', ['Code', 'Command', 'Function'],
            [['01', 'WRITE_WEIGHTS', 'load nine signed 8-bit weights'],
             ['02', 'LOAD_ACC', 'load the bias into the accumulator'],
             ['03', 'WRITE_CONFIG', 'output shift, gating enable'],
             ['10', 'COMPUTE', 'stream nine pixels and accumulate'],
             ['20', 'READ_RESULT', 'shifted, clamped 8-bit output'],
             ['21 / 22', 'READ_ACC / READ_SKIPS', 'accumulator, skip counter'],
             ['23', 'CLEAR_SKIPS', 'reset the skip counter'],
             ['30 / 31 / 32', 'SET_ACTIVITY / RUN / STOP', 'activity-mode threshold and control'],
             ['7F', 'READ_ID', 'returns A5 (bring-up check)']],
            [40, 96, 107])
    d.body('For power measurement, an activity mode drives the MAC every clock from an on-chip xorshift32 generator. Each pseudo-random pixel is zero when the generator’s top byte is below a programmable threshold T, and nonzero otherwise, so the share of zero taps is set to T/256 without any SPI traffic. Nonzero pixels are forced odd, so they can never be zero by chance, and the generator starts from a fixed seed, so every run applies the same sequence of operands and gated and BYPASS runs differ only in the gating. Running the mode with and without BYPASS gives a direct, repeatable measurement of the gating’s effect at any zero share.')
    d.h2('ASIC Implementation')
    d.body('The design was written in SystemVerilog and implemented with LibreLane in SkyWater 130 nm in two Tiny Tapeout tiles: 2,690 standard cells at 83.6% utilization. It meets 50 MHz at every process corner, with 1.77 ns of worst-case setup slack and 0.11 ns of hold slack, and has no DRC or LVS errors. The chip has been submitted for fabrication.')
    d.h2('FPGA Implementation')
    d.body('To validate the datapath on hardware and at speed, the same MAC was replicated nine times on a Zynq-7020 FPGA (PYNQ-Z1), with line buffers that present a full 3 × 3 window per clock, an AXI-Lite control interface and AXI-Stream DMA from the ARM cores. A Python driver runs both convolution layers on the FPGA and pooling and the dense layer on the ARM core. The overlay meets 100 MHz with 1.81 ns of slack.')

    d.h1('Design Flow, Verification and Power Analysis')
    d.body('Fig. 5 shows the flow. Every step uses open-source tools, and every stage is checked against the one before it: the integer model against the quantized PyTorch network, the RTL and the post-layout netlist against the integer model, and the FPGA against the same model on hardware. Because the RTL, the reference model and the board test program share one set of test vectors, a failure at any stage points to the stage that introduced it.')
    d.figure(F + 'fig6_flow.png', 'The design flow, from training to fabrication. All tools are open source; each stage is verified against the integer reference model.')
    d.body('A Python model of the integer arithmetic, bit-exact with the chip, serves as the reference. cocotb testbenches in Icarus Verilog check the RTL and the post-layout gate-level netlist against it, covering the SPI protocol and command framing, extreme operand values, chained multi-channel accumulation, SPI-to-system clock ratios and the activity mode, plus the host test program running complete layers, and run in continuous integration on every change.')
    d.body('For power, the synthesized gate-level netlist in SkyWater standard cells was simulated in activity mode for 2,000-cycle windows at thresholds giving 0, 25, 50, 75 and 90% zero pixels, each with gating on and with BYPASS, using fixed nonzero weights. The switching activity of every net was recorded and annotated into OpenSTA, which computed power at the typical corner (25 °C, 1.8 V) with a 50 MHz clock. Keeping the design hierarchy through synthesis allows the MAC instance to be reported separately from the rest of the chip.')

    d.h1('Results and Discussion')
    d.h2('Power')
    d.body('Table III and Fig. 6 give the results. Measured above its idle power, the MAC’s dynamic power falls by 10.2% at 25% zeros and by 66.3% at 90%. Two checks confirm that the saving is real and confined to the MAC. With no zero operands, gated and BYPASS power are identical, as they must be. At every zero share, the chip’s gated-versus-BYPASS difference equals the MAC’s to within 0.1 µW (21.8, 42.2, 60.2 and 71.8 µW), so the gating changes nothing outside the MAC. BYPASS power also falls as zeros increase, because a zero operand already quiets much of the multiplier’s partial-product logic; the gating’s saving is in addition to that.')
    d.table('Simulated Power (µW), Typical Corner, 50 MHz',
            ['Zero share', 'Chip gated', 'Chip BYPASS', 'Chip saving', 'MAC gated', 'MAC BYPASS', 'MAC dyn. saving'],
            [['0%', '1070.8', '1070.8', '0.0%', '353.4', '353.4', '0.0%'],
             ['25%', '1029.6', '1051.5', '2.1%', '311.6', '333.4', '10.2%'],
             ['50%', '973.2', '1015.4', '4.2%', '258.1', '300.3', '23.3%'],
             ['75%', '910.9', '971.1', '6.2%', '200.1', '260.3', '42.8%'],
             ['90%', '864.5', '936.2', '7.7%', '156.1', '227.9', '66.3%']],
            [33, 35, 36, 33, 34, 36, 36])
    d.figure(F + 'fig2_power.png', FIG2)
    d.h2('Where the Power Goes')
    d.body('Fig. 7 splits the chip’s power into three parts. The largest is a fixed floor: with the clock running and no computation, the chip draws 709 µW, all of it in sequential cells. On top of it sit the extra flip-flop power caused by changing data and the combinational logic, almost all of which is in the MAC. Zero-skipping shrinks both upper parts, the combinational part most, but leaves the floor where it is.')
    d.figure(F + 'fig4_breakdown.png', 'Simulated chip power by component for BYPASS (B) and gated (G) operation at each share of zero pixels. The clock floor, the power drawn by the flip-flops with the clock running and no computation, does not change.')
    d.body('At the chip level the saving is only 2.1% to 7.7%. Running with the clock on and no computation, the chip draws 709 µW, two-thirds of the 1,071 µW it draws at full activity, and nearly all of that is clock power in its 344 flip-flops. Operand isolation removes data switching but leaves every register clocked, so it cannot reduce this floor. In Eyeriss, where the arithmetic dominates, gating saves 45% of processing-element power [5]; in a single-MAC chip, the same idea saves most of the MAC’s dynamic power but little of the total. Per clock cycle, the MAC’s dynamic energy falls from 4.7 pJ per tap with no zeros to 0.73 pJ per tap at 90% zeros with gating, while the whole chip still spends 17.3 pJ per cycle at 90% zeros, 14.2 pJ of it in the clock floor.')
    d.body('Two design directions follow. First, gating the clock of the MAC’s registers on zero taps would remove their clock power along with their data switching, attacking the floor directly. Second, a larger array of MACs sharing one clock tree and controller spreads the fixed overhead over more arithmetic, so the same zero-skipping recovers a larger share of the total. Wafer maps make both attractive, since their 77% zero share is well above the roughly 44% reported for natural-image networks [6].')
    d.body('Table IV places these results beside the zero-skipping accelerators reviewed in Section II. The comparison is qualitative, since the designs differ in scale, process and workload, but it shows the trend this paper measures: the same idea that saves a large share of power in an arithmetic-dominated array saves most of a single MAC’s dynamic power yet little of a small chip’s total.')
    d.table('Zero-Skipping Accelerators Compared', ['Design', 'Scale', 'Zeros skipped', 'Reported benefit'],
            [['Eyeriss [5]', '168 PEs', 'activations', '45% lower PE power'],
             ['Cnvlutin [6]', 'large array', 'activations (~44% of inputs)', '1.37× speedup'],
             ['SCNN [7]', 'large array', 'weights and activations', '2.7× performance, 2.3× energy efficiency'],
             ['Liu et al. [12]', '55 nm array', 'activations or weights (adaptive)', '2.41 TOPS/W on VGG16'],
             ['This work', '1 MAC, 2,690 cells', 'pixels or weights (77%)', '23–66% MAC dynamic power; ≤7.7% chip']],
            [46, 52, 66, 79])
    d.body('The simulation also bounds what clock gating could add. The MAC accounts for 119.6 \u00b5W of the idle floor. If gating also stopped the clock to the MAC\u2019s registers on every zero tap, and that share of the floor fell in proportion to the zero share, the chip-level saving would rise to at most about 10% at 50% zeros and 19% at 90%. The remaining floor belongs mostly to the SPI interface, the configuration registers and the activity-mode generator, which a larger array would share across many MACs.')
    d.h2('Functional Results')
    d.body('Table V summarizes the FPGA run. All 180 test wafer maps produced the same integer outputs as the reference model, with 68.1% of the multiply-accumulates skipped on that set. Quantization did not change accuracy: the integer network’s macro F1 score of 0.820 matches the floating-point model’s 0.819.')
    d.table('FPGA Validation on a Zynq-7020 (PYNQ-Z1)', ['Item', 'Result'],
            [['Parallel MACs', '9 (one 3 \u00d7 3 window per clock)'],
             ['Clock', '100 MHz, worst slack +1.81 ns'],
             ['Host interface', 'AXI-Lite control, AXI-Stream DMA'],
             ['Test wafer maps', '180'],
             ['Bit-exact with integer model', '180 of 180'],
             ['MACs skipped (zero taps)', '68.1%']],
            [110, 133])

    d.h2('Limitations')
    d.body('The power figures come from simulation at one process corner, with one weight set and with pseudo-random pixels at a controlled zero share rather than real wafer maps; real layers also contain zero weights, which the gating skips as well. They cover the core logic only, not the I/O pads or the SPI transfers. Throughput was not a design goal: one MAC at 50 MHz needs at least 10.4 ms of compute for the 518,976 convolution taps of one wafer, and in practice the SPI link, which carries every weight and pixel, sets the rate. The FPGA version, with nine MACs at 100 MHz and DMA, shows how the same datapath scales when bandwidth is available.')

    d.h2('Future Work')
    d.body('Three extensions follow directly. The first adds clock gating to the MAC’s registers, driven by the same zero detection, and measures how much of the 119.6 µW MAC floor it recovers. The second replaces the pseudo-random activity mode with real wafer-map layers in the power simulation, including zero weights, to check that the controlled sweep predicts real workloads. The third scales the core to an array of MACs sharing one controller, as in the FPGA version, and measures how the chip-level saving grows as the fixed overhead is spread across more arithmetic.')

    d.h1('Silicon Measurement Plan')
    d.body('The fabricated chips are expected in mid-2027. The standard Tiny Tapeout demonstration board can run the chip but cannot measure its core current, so a dedicated four-layer host board was designed for the measurement (Fig. 8). It keeps the demonstration board\u2019s RP2350B microcontroller and pin assignment, so the existing test software runs unchanged, and adds a TI INA228 power monitor on the chip\u2019s 1.8 V core supply.')
    d.figure(F + 'fig8_board.png', 'Host board for the silicon measurement. The INA228 senses the voltage across a series shunt in the 1.8 V core supply of the chip\u2019s breakout board.')
    d.body('The core supply passes through a series shunt of 0.499 \u03a9 and 4.99 \u03a9. Together they give a 7.5 mA full-scale range with a resolution of about 14 nA, fine enough to resolve the 21.8 \u00b5W gated-versus-BYPASS difference at 25% zeros, about 12 \u00b5A; a jumper shorts the larger resistor for an 82 mA range when the chip is first powered. The sense lines are Kelvin-connected at the shunt pads, and the monitor\u2019s energy accumulator integrates power over each run. The microcontroller runs the activity-mode sweep, gated and BYPASS at each zero share, and logs current, voltage and energy, giving a direct silicon measurement of the predictions in Table III.')

    d.h1('Conclusion')
    d.body('A compact wafer-map CNN has 77% zero operands, and a zero-skipping MAC turns that sparsity into a 23–66% reduction in the MAC’s dynamic power. In a single-MAC chip, however, clock power sets the total, and the chip-level saving is at most 7.7%. Zero-skipping is worth building into small accelerators for sparse data such as wafer maps, but it needs clock gating, or an array large enough to amortize the clock, to pay off at the chip level. Silicon measurements will follow when the chips return.')

    d.h5('Acknowledgment')
    d.body('The authors thank Tiny Tapeout and San José State University for supporting the fabrication of this design.')
    d.h5('References')
    d.refs(REFS + [REF_KYEONG,
        'E. Shin and C. D. Yoo, “Efficient convolutional neural networks for semiconductor wafer bin map classification,” *Sensors*, vol. 23, no. 4, Art. no. 1926, 2023.',
        'M. Liu, C. Zhou, S. Qiu, Y. He, and H. Jiao, “CNN accelerator at the edge with adaptive zero skipping and sparsity-driven data flow,” *IEEE Trans. Circuits Syst. Video Technol.*, vol. 33, no. 12, pp. 7084–7095, 2023.',
        'Y. Qin *et al.*, “A 10.60 µW 150 GOPS mixed-bit-width sparse CNN accelerator for life-threatening ventricular arrhythmia detection,” in *Proc. ASP-DAC*, 2025.',
        'A. Ghani, “A proof-of-concept open-source platform for neural signal modulation and its applications in IoT and cyber-physical systems,” *IoT*, vol. 5, no. 4, pp. 692–710, 2024.'])
