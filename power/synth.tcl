yosys -import
set lib $::env(LIB)
set rtl $::env(RTL)
read_verilog -sv $rtl/mac_core.sv $rtl/conv_chip.sv $rtl/project.v
synth -top tt_um_izaiah_thigpen_sparse_conv -flatten
dfflibmap -liberty $lib
abc -liberty $lib
opt_clean -purge
hilomap -singleton -hicell sky130_fd_sc_hd__conb_1 HI -locell sky130_fd_sc_hd__conb_1 LO
opt_clean -purge
tee -o $::env(OUT)/synth_stat.txt stat -liberty $lib
write_verilog -noattr -noexpr -nohex -nodec $::env(OUT)/netlist.v
