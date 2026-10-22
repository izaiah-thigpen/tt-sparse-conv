"""Gate-level power estimate across sparsity, gated vs BYPASS.

Flow: the chip synthesized to SkyWater sky130_fd_sc_hd cells (synth_hier.tcl, typical
corner tt_025C_1v80), simulated with the cells' functional models, one VCD per
condition, then OpenSTA report_power with that activity at 50 MHz.

    python run_power.py            # all conditions -> results/power.csv, power.md

Environment: LIB (liberty), NETLIST, MODELS (flattened cell models), STA (OpenSTA
binary), TT_TEST (tt-repo/test, for test.py and refmodel.py).
"""
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = os.environ.get("LIB", "/tmp/claude-0/pdk/lib/sky130_fd_sc_hd__tt_025C_1v80.lib")
NETLIST = os.environ.get("NETLIST", "/tmp/claude-0/pw/netlist_hier.v")
MODELS = os.environ.get("MODELS", "/tmp/claude-0/pw/models_hier.v")
STA = os.environ.get("STA", "/tmp/claude-0/OpenSTA/build/sta")
TT_TEST = Path(os.environ.get("TT_TEST", HERE.parent / "test"))  # test.py and refmodel.py
OUT = HERE / os.environ.get("POWER_OUT", "results")
WORK = OUT / "work"      # VCDs, simulator build, STA scripts (large; not kept)
MAC_INST = "u_chip/u_mac"  # mac_core inside conv_chip (reported when the netlist keeps hierarchy)
THRESHOLDS = [0, 64, 128, 192, 230]
CLK_NS = 20

sys.path.insert(0, str(TT_TEST))
sys.path.insert(0, str(HERE))
from cocotb_tools.runner import get_runner  # noqa: E402


def simulate(conds):
    WORK.mkdir(parents=True, exist_ok=True)
    build = WORK / "sim_build"
    r = get_runner("icarus")
    # The runner passes -none (no dumps) unless waves are on, and waves means FST;
    # OpenSTA reads VCD, so swap the flag.
    base = r._test_command
    r._test_command = lambda: [[("-vcd" if a == "-none" else a) for a in cmd] for cmd in base()]
    r.build(sources=[MODELS, NETLIST, str(HERE / "tb_power.v")], hdl_toplevel="tb_power",
            build_args=["-g2012", "-DFUNCTIONAL", "-DUNIT_DELAY=#1"], build_dir=build,
            timescale=("1ns", "1ps"))
    env_path = os.pathsep.join([str(HERE), str(TT_TEST), os.environ.get("PYTHONPATH", "")])
    for c in conds:
        vcd = WORK / f"{c}.vcd"
        r.test(hdl_toplevel="tb_power", test_module="test_power", test_dir=str(HERE), build_dir=build,
               results_xml=str(WORK / f"{c}.xml"), plusargs=[f"+vcd={vcd}"],
               extra_env={"POWER_COND": c, "GATES": "yes", "PYTHONPATH": env_path})
        if 'failures="0"' not in (WORK / f"{c}.xml").read_text() or not vcd.exists():
            raise SystemExit(f"simulation failed for {c}")


def power(cond):
    tcl = WORK / f"{cond}.tcl"
    tcl.write_text(f"""read_liberty {LIB}
read_verilog {NETLIST}
link_design tt_um_izaiah_thigpen_sparse_conv
create_clock -name clk -period {CLK_NS} [get_ports clk]
read_vcd -scope tb_power/dut {WORK / (cond + '.vcd')}
report_power -digits 6
if {{[llength [get_cells -quiet {MAC_INST}]]}} {{ puts "MAC_BEGIN"; report_power -digits 6 -instances [get_cells {MAC_INST}] }}
exit
""")
    out = subprocess.run([STA, "-no_init", "-no_splash", "-exit", str(tcl)],
                         capture_output=True, text=True).stdout
    (OUT / "reports").mkdir(parents=True, exist_ok=True)
    (OUT / "reports" / f"{cond}.power.txt").write_text(out)
    rows = {}
    for name in ("Sequential", "Combinational", "Clock", "Macro", "Pad", "Total"):
        m = re.search(rf"^{name}\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", out, re.M)
        if m:
            rows[name] = [float(x) for x in m.groups()]  # internal, switching, leakage, total (W)
    m = re.search(r"MAC_BEGIN.*?^\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+\S*u_mac", out, re.M | re.S)
    if m:
        rows["MAC"] = [float(x) for x in m.groups()]
    if "Total" not in rows:
        raise SystemExit(f"no power report for {cond}:\n{out}")
    return rows


def main():
    conds = ["idle"] + [f"T{t}_{m}" for t in THRESHOLDS for m in ("gated", "bypass")]
    if "--no-sim" not in sys.argv:
        simulate(conds)
    res = {c: power(c) for c in conds}
    uw = lambda c, k="Total": res[c][k][3] * 1e6  # noqa: E731
    with open(OUT / "power.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition", "zero_share", "total_uW", "sequential_uW", "combinational_uW", "leakage_uW", "mac_uW"])
        for c in conds:
            share = "" if c == "idle" else int(c[1:].split("_")[0]) / 256
            w.writerow([c, share, f"{uw(c):.2f}", f"{uw(c, 'Sequential'):.2f}",
                        f"{uw(c, 'Combinational'):.2f}", f"{res[c]['Total'][2] * 1e6:.4f}",
                        f"{uw(c, 'MAC'):.2f}" if "MAC" in res[c] else ""])
    idle = uw("idle")
    mac = "MAC" in res["idle"]
    lines = ["| Zero share | Chip gated (µW) | Chip BYPASS (µW) | Chip saving | Saving above idle |"
             + (" MAC gated (µW) | MAC BYPASS (µW) | MAC saving | MAC dynamic saving |" if mac else ""),
             "| --- | --- | --- | --- | --- |" + (" --- | --- | --- | --- |" if mac else "")]
    for t in THRESHOLDS:
        g, b = uw(f"T{t}_gated"), uw(f"T{t}_bypass")
        row = f"| {t / 256:.0%} | {g:.1f} | {b:.1f} | {(b - g) / b:.1%} | {(b - g) / (b - idle):.1%} |"
        if mac:
            mg, mb = uw(f"T{t}_gated", "MAC"), uw(f"T{t}_bypass", "MAC")
            mi = uw("idle", "MAC")
            row += f" {mg:.1f} | {mb:.1f} | {(mb - mg) / mb:.1%} | {(mb - mg) / (mb - mi):.1%} |"
        lines.append(row)
    lines.append(f"\nIdle (clock running, no computation): chip {idle:.1f} µW"
                 + (f", MAC {uw('idle', 'MAC'):.1f} µW" if mac else ""))
    (OUT / "power.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
