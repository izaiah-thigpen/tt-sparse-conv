# build_overlay.tcl
#
# Builds the PYNQ-Z1 overlay: Zynq PS + AXI DMA + the convolution engine.
#
# Run from a Vivado Tcl shell or the command line:
#     vivado -mode batch -source build_overlay.tcl
#
# Output (in pynq/overlay/):
#     wafer_accel.bit   bitstream
#     wafer_accel.hwh   hardware description PYNQ reads to find the IP
#     utilization.rpt, timing.rpt
#
# The block design:
#     ps7 (M_AXI_GP0) --> AXI-Lite --> axi_dma control, engine registers
#     axi_dma MM2S stream (8-bit) --> engine s_axis
#     engine m_axis (8-bit) --> axi_dma S2MM stream
#     axi_dma memory ports --> ps7 S_AXI_HP0 --> DDR
#     everything clocked by FCLK_CLK0 at 100 MHz

set script_dir [file dirname [file normalize [info script]]]
set root       [file normalize "$script_dir/.."]
set proj_dir   "$script_dir/build"
set out_dir    "$script_dir/overlay"
set part       xc7z020clg400-1

catch {close_project}   ;# in case a failed run left a project open
create_project wafer_accel $proj_dir -part $part -force

# Use the PYNQ-Z1 board files if they are installed (for the PS presets)
set board [lindex [get_board_parts -quiet *pynq-z1*] end]
if {$board ne ""} {
    set_property board_part $board [current_project]
    puts "Using board part $board"
} else {
    puts "PYNQ-Z1 board files not found; building for the part only."
    puts "That is fine for PYNQ: the board image has already configured the PS and DDR."
}

add_files [list \
    $root/rtl/conv_engine.sv \
    $root/rtl/engine_regs.sv \
    $root/rtl/engine_glue.sv \
    $root/rtl/conv_engine_axi.v ]
update_compile_order -fileset sources_1

# Latest installed version of an IP, so the script works across Vivado versions
proc latest_ip {name} {
    set defs [get_ipdefs -all -filter "NAME == $name"]
    if {[llength $defs] == 0} { error "IP $name not found in this Vivado installation" }
    return [lindex [lsort $defs] end]
}

create_bd_design wafer_accel

# ---------------------------------------------------------------- Zynq PS
set ps [create_bd_cell -type ip -vlnv [latest_ip processing_system7] ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config [list make_external "FIXED_IO, DDR" apply_board_preset [expr {$board ne "" ? 1 : 0}] \
                  Master "Disable" Slave "Disable"] $ps
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} ] $ps

# ---------------------------------------------------------------- DMA
set dma [create_bd_cell -type ip -vlnv [latest_ip axi_dma] axi_dma]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_length_width {26} \
    CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_m_axis_mm2s_tdata_width {8} \
    CONFIG.c_s_axis_s2mm_tdata_width {8} \
    CONFIG.c_mm2s_burst_size {16} \
    CONFIG.c_s2mm_burst_size {16} ] $dma

# ---------------------------------------------------------------- Engine
set eng [create_bd_cell -type module -reference conv_engine_axi engine]

connect_bd_intf_net [get_bd_intf_pins axi_dma/M_AXIS_MM2S] [get_bd_intf_pins engine/s_axis]
connect_bd_intf_net [get_bd_intf_pins engine/m_axis] [get_bd_intf_pins axi_dma/S_AXIS_S2MM]

# ---------------------------------------------------------------- AXI connections
# Control: PS GP0 -> DMA registers and engine registers
foreach slave {/axi_dma/S_AXI_LITE /engine/s_axil} {
    apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list \
        Clk_master {/ps7/FCLK_CLK0 (100 MHz)} Clk_slave {Auto} Clk_xbar {Auto} \
        Master {/ps7/M_AXI_GP0} Slave $slave ddr_seg {Auto} \
        intc_ip {New AXI Interconnect} master_apm {0}] [get_bd_intf_pins $slave]
}
# Data: DMA memory ports -> interconnect -> PS HP0 -> DDR. Wired by hand:
# the connection automation for this path fails on some Vivado versions.
set ic [create_bd_cell -type ip -vlnv [latest_ip axi_interconnect] hp0_ic]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $ic
connect_bd_intf_net [get_bd_intf_pins axi_dma/M_AXI_MM2S] [get_bd_intf_pins hp0_ic/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma/M_AXI_S2MM] [get_bd_intf_pins hp0_ic/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins hp0_ic/M00_AXI]    [get_bd_intf_pins ps7/S_AXI_HP0]

# Connect a pin to a source unless something already drives it
proc connect_if_open {src pin} {
    if {[llength [get_bd_nets -quiet -of_objects [get_bd_pins $pin]]] == 0} {
        connect_bd_net [get_bd_pins $src] [get_bd_pins $pin]
    }
}
set rst [lindex [get_bd_cells -filter {VLNV =~ "*proc_sys_reset*"}] 0]
foreach pin {hp0_ic/ACLK hp0_ic/S00_ACLK hp0_ic/S01_ACLK hp0_ic/M00_ACLK \
             ps7/S_AXI_HP0_ACLK axi_dma/m_axi_mm2s_aclk axi_dma/m_axi_s2mm_aclk} {
    connect_if_open ps7/FCLK_CLK0 $pin
}
connect_if_open $rst/interconnect_aresetn hp0_ic/ARESETN
foreach pin {hp0_ic/S00_ARESETN hp0_ic/S01_ARESETN hp0_ic/M00_ARESETN} {
    connect_if_open $rst/peripheral_aresetn $pin
}

# The engine's clock and reset, if the automation left them open
connect_if_open ps7/FCLK_CLK0 engine/aclk
connect_if_open $rst/peripheral_aresetn engine/aresetn

assign_bd_address
validate_bd_design
save_bd_design

# ---------------------------------------------------------------- Build
set wrapper [make_wrapper -files [get_files wafer_accel.bd] -top]
add_files -norecurse $wrapper
set_property top wafer_accel_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    error "Implementation did not finish; see $proj_dir/wafer_accel.runs/impl_1"
}

open_run impl_1
file mkdir $out_dir
report_utilization    -file $out_dir/utilization.rpt
report_timing_summary -file $out_dir/timing.rpt

file copy -force [lindex [glob $proj_dir/wafer_accel.runs/impl_1/*.bit] 0] $out_dir/wafer_accel.bit
# Vivado 2020.2+ keeps generated files in .gen; older versions in .srcs
set hwh [glob -nocomplain \
    $proj_dir/wafer_accel.gen/sources_1/bd/wafer_accel/hw_handoff/wafer_accel.hwh \
    $proj_dir/wafer_accel.srcs/sources_1/bd/wafer_accel/hw_handoff/wafer_accel.hwh]
file copy -force [lindex $hwh 0] $out_dir/wafer_accel.hwh

set wns [get_property STATS.WNS [get_runs impl_1]]
puts "Done. Worst negative slack: $wns ns (positive means timing met at 100 MHz)."
puts "Copy $out_dir/wafer_accel.bit and wafer_accel.hwh to the board."
