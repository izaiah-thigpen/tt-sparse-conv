/*
 * Copyright (c) 2026 Izaiah Thigpen
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tiny Tapeout top level: maps conv_chip onto the standard pins.
 *
 *   ui_in[0]  SCLK        uo_out[0]  MISO
 *   ui_in[1]  CS_N        uo_out[1]  DONE
 *   ui_in[2]  MOSI        uo_out[2]  SKIP
 *   ui_in[3]  BYPASS      uo_out[3]  BUSY
 *   ui_in[7:4] unused     uo_out[7:4] TAP[3:0]
 *   uio[7:0]  unused (inputs)
 */
`default_nettype none

module tt_um_izaiah_thigpen_sparse_conv (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

    wire       miso, done, skip, busy;
    wire [3:0] tap;

    conv_chip #(.ACC_W(24)) u_chip (
        .clk      (clk),
        .rst_n    (rst_n),
        .spi_sclk (ui_in[0]),
        .spi_cs_n (ui_in[1]),
        .spi_mosi (ui_in[2]),
        .spi_miso (miso),
        .bypass   (ui_in[3]),
        .done     (done),
        .busy     (busy),
        .skip     (skip),
        .tap      (tap)
    );

    assign uo_out  = {tap, busy, skip, done, miso};
    assign uio_out = 8'h00;
    assign uio_oe  = 8'h00;

    // List all unused inputs to prevent warnings
    wire _unused = &{ena, ui_in[7:4], uio_in, 1'b0};

endmodule
