"""Sparse-conv host board, rev A: the full design as data.

Run: python design.py  ->  ../sparse-conv-host/*.kicad_sch

Parts copied from the Tiny Tapeout demo board v3.2 (Apache 2.0, Psychogenic
Technologies) keep its values and part numbers; the power monitor is new.
"""
import os
import sys

import symlib as L
from schgen import Part, Project

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.environ.get('TT_DEMO', os.path.join(HERE, 'tt-demo-pcb'))  # optional clone of TinyTapeout/tt-demo-pcb
OUT = os.path.join(HERE, '..', 'sparse-conv-host')

TTLIB = os.path.join(OUT, 'libs', 'TinyTapeout.kicad_sym')
if os.path.exists(f'{DEMO}/rp2350.kicad_sch'):
    # first build: take the symbols from the Tiny Tapeout demo board (KiCad 9) schematics
    RP2350 = L.embedded(f'{DEMO}/rp2350.kicad_sch', 'TinyTapeout:RP2350b-QFN80-LOGICAL', 'TinyTapeout:RP2350B')
    CARRIER = L.embedded(f'{DEMO}/tinytapeout-demo.kicad_sch', 'TinyTapeout:TT_HRS_BREAKOUT_REVB')
    PMOD = L.embedded(f'{DEMO}/tinytapeout-demo.kicad_sch', 'TinyTapeout:PMOD_HOST_2x6')
else:
    # later builds: the copies saved in the project's own library
    RP2350 = L.from_lib(TTLIB, 'RP2350B', 'TinyTapeout:RP2350B')
    CARRIER = L.from_lib(TTLIB, 'TT_HRS_BREAKOUT_REVB', 'TinyTapeout:TT_HRS_BREAKOUT_REVB')
    PMOD = L.from_lib(TTLIB, 'PMOD_HOST_2x6', 'TinyTapeout:PMOD_HOST_2x6')

# ------------------------------------------------------------------ footprints
R0402 = 'Resistor_SMD:R_0402_1005Metric'
R0805 = 'Resistor_SMD:R_0805_2012Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
LED = 'LED_SMD:LED_0603_1608Metric'
BTN = 'TinyTapeout:434121025816'
TP = 'TestPoint:TestPoint_Pad_D1.5mm'

# ------------------------------------------------------------------ part helpers
_n = {}


def ref(prefix):
    _n[prefix] = _n.get(prefix, 0) + 1
    return f"{prefix}{_n[prefix]}"


def R(value, a, b, fp=R0402, **f):
    return Part(ref('R'), 'Device:R_Small', value, {'1': a, '2': b}, fp, f)


def C(value, a, b='GND', fp=C0402, **f):
    return Part(ref('C'), 'Device:C_Small', value, {'1': a, '2': b}, fp, f)


def led(anode, cathode, value='Yellow'):
    return Part(ref('D'), 'Device:LED_Small', value, {'2': anode, '1': cathode}, LED,
                {'MPN': 'CSL1901YW1', 'LCSC': 'C72038'})


def button(a, b, value):
    return Part(ref('SW'), 'Switch:SW_Push', value, {'1': a, '2': b}, BTN,
                {'MPN': '434121025816', 'LCSC': 'C329185'})


def testpoint(net):
    return Part(ref('TP'), 'Connector:TestPoint', net, {'1': net}, TP)


LCSC_100N = {'MPN': 'CL05A104KA5NNNC', 'LCSC': 'C100072'}
LCSC_1U = {'MPN': 'GRM188D72A105KE01D', 'LCSC': 'C5673'}
LCSC_10U = {'MPN': 'GRM21BR71C106KE51L', 'LCSC': 'C408142'}
LCSC_1K = {'MPN': 'CR0402-FX-1001GLF', 'LCSC': 'C202394'}
LCSC_10K = {'MPN': 'RC0402FR-0710KL', 'LCSC': 'C471764'}
LCSC_5K1 = {'MPN': 'AC0402FR-135K1L', 'LCSC': 'C138073'}

prj = Project('sparse-conv-host', 'Sparse Convolution Chip Host Board', 'A', 'Izaiah Thigpen', '2026-10-22')
prj.root_note = ('Host board for the sparsity-aware convolution chip (Tiny Tapeout, SkyWater 130 nm).\n'
                 'Keeps the Tiny Tapeout demo board v3 RP2350B pin map, so its firmware and the host/ test kit run unchanged,\n'
                 'and adds an INA228 power monitor on the chip core supply. Demo board design (c) 2025 Pat Deegan, Apache 2.0.')

# ================================================================== sheet 1: USB and power
pw = prj.sheet('Power', 'power.kicad_sch', 'USB-C input and 3.3 V supply', paper='A3')
pw.add(
    Part(ref('J'), 'Connector:USB_C_Receptacle_USB2.0_16P', 'USB_C',
         {'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND',
          'A4': 'VBUS_RAW', 'A9': 'VBUS_RAW', 'B4': 'VBUS_RAW', 'B9': 'VBUS_RAW',
          'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP', 'A7': 'USB_DM', 'B7': 'USB_DM',
          'A8': None, 'B8': None, 'S1': 'USB_SHIELD'},
         'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', {'MPN': 'USB-TYPE-C-019', 'LCSC': 'C2927039'}),
    R('5.1k', 'CC1', 'GND', **LCSC_5K1),
    R('5.1k', 'CC2', 'GND', **LCSC_5K1),
    Part(ref('D'), 'Device:D_TVS', 'ESD', {'1': 'USB_DP', '2': 'GND'}, 'Diode_SMD:D_0603_1608Metric',
         {'MPN': '0603ESDA-AEC1', 'LCSC': 'C6961594'}),
    Part(ref('D'), 'Device:D_TVS', 'ESD', {'1': 'USB_DM', '2': 'GND'}, 'Diode_SMD:D_0603_1608Metric',
         {'MPN': '0603ESDA-AEC1', 'LCSC': 'C6961594'}),
    R('1M', 'USB_SHIELD', 'GND', 'Resistor_SMD:R_0603_1608Metric', LCSC='C858907'),
    C('6800p', 'USB_SHIELD', 'GND', C0603, MPN='GCM188R72A682KA37D'),
    Part(ref('F'), 'Device:Polyfuse_Small', '350mA', {'1': 'VBUS_RAW', '2': 'VBUS_F'}, 'Fuse:Fuse_0805_2012Metric',
         {'MPN': '0ZCK0035FF2G', 'LCSC': 'C1884490'}),
    Part(ref('FB'), 'Device:FerriteBead_Small', '120R', {'1': 'VBUS_F', '2': '+5V'}, 'Inductor_SMD:L_0603_1608Metric',
         {'MPN': 'MFBM1V1608-121-R', 'LCSC': 'C2649119'}),
    C('10u', '+5V', fp=C0805, **LCSC_10U),
    C('1u', '+5V', fp=C0603, **LCSC_1U),
    Part(ref('U'), 'Regulator_Linear:AMS1117-3.3', 'TLV1117LV33', {'1': 'GND', '2': '+3V3', '3': '+5V'},
         'Package_TO_SOT_SMD:SOT-223-3_TabPin2', {'MPN': 'TLV1117LV33DCYR', 'LCSC': 'C15578'}),
    C('22u', '+3V3', fp=C0805, MPN='GRT21BR61E226ME13L', LCSC='C86816'),
    C('100n', '+3V3', **LCSC_100N),
    R('1.2k', '+5V', 'LED_USB', MPN='RC0402FR-071K2L', LCSC='C138040'),
    led('LED_USB', 'GND'),
    R('510', '+3V3', 'LED_3V3', MPN='RC0402FR-07510RL', LCSC='C276273'),
    led('LED_3V3', 'GND'),
    Part('#FLG01', 'power:PWR_FLAG', 'PWR_FLAG', {'1': '+5V'}),
    Part('#FLG02', 'power:PWR_FLAG', 'PWR_FLAG', {'1': 'GND'}),
)
pw.note('USB-C, polyfuse, ESD and the 3.3 V LDO are as on the Tiny Tapeout demo board v3.\n'
        'The LDO also feeds the breakout (which makes the chip 1.8 V core) and the power monitor.')

# ================================================================== sheet 2: RP2350B
mcu = prj.sheet('MCU', 'mcu.kicad_sch', 'RP2350B microcontroller', paper='A2')
gpio = {i: None for i in range(48)}
gpio.update({0: 'CTRL_ENA', 1: 'CTRL_SEL_RST_N', 2: 'CTRL_SEL_INC', 11: 'RP_LED',
             12: 'I2C_SDA', 13: 'I2C_SCL', 14: 'PROJ_RST_RP', 15: 'PM_ALERT', 16: 'PROJ_CLK_RP'})
gpio.update({3 + k: f'MNG{k}' for k in range(8)})
gpio.update({17 + k: f'UI_IN{k}' for k in range(8)})
gpio.update({25 + k: f'UIO{k}' for k in range(8)})
gpio.update({33 + k: f'UO_OUT{k}' for k in range(8)})
rp_nets = {}
for (u, num, name, *_rest) in L.pins(RP2350):
    if name in ('IOVDD', 'ADC_AVDD', 'USB_OTP_VDD', 'QSPI_IOVDD', 'VREG_VIN'):
        rp_nets[num] = '+3V3'
    elif name in ('DVDD', 'VREG_FB'):
        rp_nets[num] = '+1V1'
    elif name in ('GND', 'VREG_PGND'):
        rp_nets[num] = 'GND'
    elif name.startswith('GPIO'):
        rp_nets[num] = gpio[int(name[4:].split('_')[0])]
    else:
        rp_nets[num] = {'VREG_AVDD': 'VREG_AVDD', 'VREG_LX': 'VREG_LX', 'XIN': 'XIN', 'XOUT': 'XOUT',
                        'SWCLK': 'SWCLK', 'SWDIO': 'SWDIO', 'RUN': 'RUN', 'USB_DM': 'USB_DM_MCU',
                        'USB_DP': 'USB_DP_MCU', 'QSPI_SD0': 'QSPI_SD0', 'QSPI_SD1': 'QSPI_SD1',
                        'QSPI_SD2': 'QSPI_SD2', 'QSPI_SD3': 'QSPI_SD3', 'QSPI_SCLK': 'QSPI_SCLK',
                        'QSPI_SS': 'QSPI_SS'}[name]
mcu.add(Part(ref('U'), 'TinyTapeout:RP2350B', 'RP2350B', rp_nets,
             'Package_DFN_QFN:QFN-80-1EP_10x10mm_P0.4mm_EP3.4x3.4mm', {'MPN': 'RP2350B'}, sym=RP2350))
mcu.add(*[C('100n', '+3V3', **LCSC_100N) for _ in range(10)])
mcu.add(C('4.7u', '+3V3', fp=C0603, MPN='GRM188C71C475KE21D'),          # VREG_VIN bulk
        R('33', '+3V3', 'VREG_AVDD', MPN='RCS040233R0FKED'),
        C('4.7u', 'VREG_AVDD', MPN='GRM155R61E475ME15D'),
        Part(ref('L'), 'Device:L_Small', '3.3u', {'1': '+1V1', '2': 'VREG_LX'}, 'Inductor_SMD:L_2016X120N',
             {'MPN': 'AOTA-B201610S3R3-101-T'}),
        C('100n', '+1V1', **LCSC_100N), C('100n', '+1V1', **LCSC_100N),
        C('4.7u', '+1V1', MPN='GRM155R61E475ME15D'), C('4.7u', '+1V1', fp=C0603, MPN='GRM188C71C475KE21D'),
        Part('#FLG03', 'power:PWR_FLAG', 'PWR_FLAG', {'1': '+1V1'}),
        Part('#FLG05', 'power:PWR_FLAG', 'PWR_FLAG', {'1': 'VREG_AVDD'}),
        Part(ref('Y'), 'Device:Crystal_GND24_Small', '12MHz', {'1': 'XIN', '2': 'GND', '3': 'XOUT_R', '4': 'GND'},
             'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm', {'MPN': 'FC3BAEBGI12.0-T1', 'LCSC': 'C1985523'}),
        R('1k', 'XOUT', 'XOUT_R', **LCSC_1K),
        C('14p', 'XIN', MPN='CC0402CRNPO9BN4R0', LCSC='C325455'),
        C('14p', 'XOUT_R', MPN='CC0402CRNPO9BN4R0', LCSC='C325455'),
        Part(ref('U'), 'Memory_Flash:W25Q32JVSS', 'W25Q32JVSS',
             {'1': 'QSPI_SS', '2': 'QSPI_SD1', '3': 'QSPI_SD2', '4': 'GND', '5': 'QSPI_SD0',
              '6': 'QSPI_SCLK', '7': 'QSPI_SD3', '8': '+3V3'},
             'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm', {'MPN': 'W25Q32JVSSIQ'}),
        C('100n', '+3V3', **LCSC_100N),
        R('10k', '+3V3', 'QSPI_SS', **LCSC_10K),
        R('1k', 'QSPI_SS', 'BOOT_SW', **LCSC_1K),
        button('BOOT_SW', 'GND', 'BOOT'),
        R('10k', '+3V3', 'RUN', **LCSC_10K),
        button('RUN', 'GND', 'RESET'),
        R('27', 'USB_DP', 'USB_DP_MCU', MPN='AF0402FR-0727RL'),
        R('27', 'USB_DM', 'USB_DM_MCU', MPN='AF0402FR-0727RL'),
        Part(ref('J'), 'Connector_Generic:Conn_01x03', 'SWD', {'1': 'SWCLK', '2': 'GND', '3': 'SWDIO'},
             'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical'),
        R('510', 'RP_LED', 'RP_LED_A', MPN='RC0402FR-07510RL', LCSC='C276273'),
        led('RP_LED_A', 'GND'))
mcu.note('Copied from the Tiny Tapeout demo board v3 RP2350B sheet. GPIO map (unchanged, so the TT firmware runs as is):\n'
         'GPIO0 ctrl_ena, GPIO1 ctrl_sel_rst_n, GPIO2 ctrl_sel_inc, GPIO3-10 management (breakout ID EEPROM on GPIO4/5),\n'
         'GPIO11 LED, GPIO14 project reset, GPIO16 project clock, GPIO17-24 ui_in, GPIO25-32 uio, GPIO33-40 uo_out.\n'
         'New: GPIO12/13 I2C to the INA228 power monitor, GPIO15 its ALERT.')

# ================================================================== sheet 3: breakout and I/O
bo = prj.sheet('Breakout', 'breakout.kicad_sch', 'Chip breakout sockets and I/O', paper='A2', cols=5)
cn = {}
for (u, num, name, *_rest) in L.pins(CARRIER):
    if name == 'GND':
        cn[num] = 'GND'
    elif name == '3v3':
        cn[num] = '+3V3'
    elif name == 'VBUS':
        cn[num] = '+5V'
    elif name.startswith('an'):
        cn[num] = 'AN' + name[2:]
    elif name.startswith('RES'):
        cn[num] = None
    elif name.startswith('mng0'):
        cn[num] = 'MNG' + name[4:]
    elif name.startswith('ui_in['):
        cn[num] = 'UI_IN' + name[6:-1]
    elif name.startswith('uio['):
        cn[num] = 'UIO' + name[4:-1]
    elif name.startswith('uo_out['):
        cn[num] = 'UO_OUT' + name[7:-1]
    else:
        cn[num] = {'proj_~{rst}': 'PROJ_RST_N', 'proj_clk': 'PROJ_CLK', 'ctrl_~{rst}': 'CTRL_SEL_RST_N',
                   'ctrl_ena': 'CTRL_ENA', 'ctrl_inc': 'CTRL_SEL_INC'}[name]
bo.add(Part(ref('J'), 'TinyTapeout:TT_HRS_BREAKOUT_REVB', 'TT breakout (DF12 60+50)', cn,
            'TinyTapeout:TT_HRS_CARRIER_REVC',
            {'MPN': 'DF12NB(5.0)-60DP-0.5V(51) + DF12NB(5.0)-50DP-0.5V(51)', 'Manufacturer': 'Hirose'}, sym=CARRIER))
bo.add(R('10k', '+3V3', 'CTRL_ENA', **LCSC_10K),
       R('5.1k', '+3V3', 'CTRL_SEL_INC', **LCSC_5K1),
       R('10k', '+3V3', 'CTRL_SEL_RST_N', **LCSC_10K),
       R('1k', 'PROJ_RST_RP', 'PROJ_RST_N', **LCSC_1K),
       R('10k', '+3V3', 'PROJ_RST_N', **LCSC_10K),
       button('PROJ_RST_N', 'GND', 'PROJ RESET'),
       R('33', 'PROJ_CLK_RP', 'PROJ_CLK', MPN='RCS040233R0FKED'),
       testpoint('PROJ_CLK'))
bo.add(*[R('10M', f'AN{k}', 'GND') for k in range(22)])
for name, base in (('PMOD in (ui_in)', 'UI_IN'), ('PMOD bidir (uio)', 'UIO'), ('PMOD out (uo_out)', 'UO_OUT')):
    nets = {'5': 'GND', '11': 'GND', '6': '+3V3', '12': '+3V3'}
    for i, pin in enumerate(['1', '2', '3', '4', '7', '8', '9', '10']):
        nets[pin] = f'{base}{i}'
    bo.add(Part(ref('J'), 'TinyTapeout:PMOD_HOST_2x6', name, nets, 'TinyTapeout:PinSocket_2x06_P2.54mm_PMODHost1A',
                {'MPN': 'PPTC062LJBN-RC', 'LCSC': 'C6147817'}, sym=PMOD),
           C('100n', '+3V3', **LCSC_100N), C('1u', '+3V3', fp=C0603, **LCSC_1U))
la = {'1': 'UI_IN0', '2': 'UO_OUT0', '3': 'UI_IN1', '4': 'UO_OUT1', '5': 'UI_IN2', '6': 'UO_OUT2',
      '7': 'UI_IN3', '8': 'UO_OUT3', '9': 'PROJ_CLK', '10': 'UO_OUT4', '11': 'PROJ_RST_N', '12': 'UO_OUT5',
      '13': 'GND', '14': 'UO_OUT6', '15': 'GND', '16': 'UO_OUT7'}
bo.add(Part(ref('J'), 'Connector_Generic:Conn_02x08_Odd_Even', 'Logic analyzer', la,
            'Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical'))
for k in range(4):
    bo.add(Part(ref('H'), 'Mechanical:MountingHole_Pad', 'M3', {'1': 'GND'}, 'MountingHole:MountingHole_3.2mm_M3_Pad_Via'))
bo.note('The breakout socket, pull-ups and PMODs follow the Tiny Tapeout demo board v3 exactly.\n'
        'Logic-analyzer header for this design: ui_in[0..3] = SCLK, CS_N, MOSI, BYPASS;\n'
        'uo_out[0..3] = MISO, DONE, SKIP, BUSY; uo_out[4..7] = TAP[0..3].\n'
        'Analog pins: 10 Mohm pull-downs only, as on the demo board. RES pins left open.')

# ================================================================== sheet 4: power monitor
pm = prj.sheet('PowerMonitor', 'power_monitor.kicad_sch', 'Chip core power monitor', paper='A3')
pm.add(Part(ref('J'), 'Connector_Generic:Conn_01x03', 'CORE', {'1': 'VCORE_IN', '2': 'VCORE_OUT', '3': 'GND'},
            'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical'),
       R('0.499', 'VCORE_IN', 'SHUNT_MID', R0805, Tolerance='1%'),
       R('4.99', 'SHUNT_MID', 'VCORE_OUT', R0805, Tolerance='0.1%', TempCo='25ppm'),
       Part(ref('J'), 'Connector_Generic:Conn_01x02', 'RANGE', {'1': 'SHUNT_MID', '2': 'VCORE_OUT'},
            'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical'),
       Part(ref('U'), 'Sensor_Energy:INA226', 'INA228',
            {'10': 'VCORE_IN', '9': 'VCORE_OUT', '8': 'VCORE_OUT', '6': '+3V3', '7': 'GND',
             '1': 'GND', '2': 'GND', '3': 'PM_ALERT', '4': 'I2C_SDA', '5': 'I2C_SCL'},
            'Package_SO:VSSOP-10_3x3mm_P0.5mm',
            {'MPN': 'INA228AQDGSRQ1', 'LCSC': 'C5214669', 'Datasheet': 'https://www.ti.com/lit/ds/symlink/ina228.pdf'}),
       C('100n', '+3V3', **LCSC_100N),
       C('1u', '+3V3', fp=C0603, **LCSC_1U),
       R('4.7k', '+3V3', 'I2C_SDA'),
       R('4.7k', '+3V3', 'I2C_SCL'),
       R('10k', '+3V3', 'PM_ALERT', **LCSC_10K),
       testpoint('VCORE_IN'), testpoint('VCORE_OUT'))
pm.add(Part('#FLG04', 'power:PWR_FLAG', 'PWR_FLAG', {'1': 'VCORE_IN'}))
pm.note('Core current = V(shunt) / R. Normal range: 0.499 + 4.99 ohm = 5.49 ohm, 7.5 mA full scale (ADCRANGE=1).\n'
        'High range: fit a jumper on RANGE to short the 4.99 ohm -> 0.499 ohm, 82 mA full scale.\n'
        'Hook-up: on the TT breakout remove R14 (0 ohm, 0805), fit header J2, then wire\n'
        'J2 pin 5 (VCC_REG) -> CORE pin 1, J2 pin 6 (VCCD) -> CORE pin 2, ground -> CORE pin 3.\n'
        'Layout: Kelvin traces from the shunt pads to IN+/IN-; INA228 address 0x40 (A0 = A1 = GND).')

def package():
    """Project file, library tables, and the Tiny Tapeout symbol library."""
    import json
    from sexpr import Q, dump
    os.makedirs(os.path.join(OUT, 'libs'), exist_ok=True)
    lib = ['kicad_symbol_lib', ['version', 20220914], ['generator', 'kicad_symbol_editor']]
    for sym in (RP2350, CARRIER, PMOD):
        s = list(sym)
        s[1] = Q(sym[1].split(':')[1])
        lib.append(s)
    open(TTLIB, 'w').write(dump(lib) + '\n')
    open(os.path.join(OUT, 'sym-lib-table'), 'w').write(
        '(sym_lib_table\n  (version 7)\n  (lib (name "TinyTapeout")(type "KiCad")(uri "${KIPRJMOD}/libs/TinyTapeout.kicad_sym")'
        '(options "")(descr "RP2350B, TT breakout socket, PMOD host (Tiny Tapeout demo board, Apache 2.0)"))\n)\n')
    open(os.path.join(OUT, 'fp-lib-table'), 'w').write(
        '(fp_lib_table\n  (version 7)\n  (lib (name "TinyTapeout")(type "KiCad")(uri "${KIPRJMOD}/libs/TinyTapeout.pretty")'
        '(options "")(descr "Tiny Tapeout footprints (psychogenic/tinytapeout-kicad-libs, Apache 2.0)"))\n)\n')
    pro = {"meta": {"filename": "sparse-conv-host.kicad_pro", "version": 1},
           "sheets": [[str(prj.root_uuid), ""]] + [[str(s.uuid), s.title] for s in prj.sheets],
           "text_variables": {}}
    json.dump(pro, open(os.path.join(OUT, 'sparse-conv-host.kicad_pro'), 'w'), indent=2)


if __name__ == '__main__':
    nets = prj.write(OUT)
    package()
    print(f"wrote {len(prj.sheets)} sheets, {sum(len(s.parts) for s in prj.sheets)} parts, {len(nets)} named signal nets")
