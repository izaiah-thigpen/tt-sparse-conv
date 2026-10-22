`default_nettype none
`timescale 1ns / 1ps

// Power testbench: the chip with a switching-activity dump that cocotb opens
// only for the measurement window. VCD path from +vcd=<file>.
module tb_power ();
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;
  reg dump_on = 1'b0;

  reg [1023:0] vcd_path;
  initial begin
    if (!$value$plusargs("vcd=%s", vcd_path)) vcd_path = "power.vcd";
    wait (dump_on);
    $dumpfile(vcd_path);
    $dumpvars(0, dut);
  end

  tt_um_izaiah_thigpen_sparse_conv dut (
      .ui_in  (ui_in),
      .uo_out (uo_out),
      .uio_in (uio_in),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (ena),
      .clk    (clk),
      .rst_n  (rst_n)
  );
endmodule
