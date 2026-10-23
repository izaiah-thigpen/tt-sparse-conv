// engine_glue.sv
//
// Connects the AXI-Lite registers to the convolution engine. Kept separate
// from conv_engine_axi.v because the weight array cannot cross a plain
// Verilog port.

module engine_glue (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [5:0]  awaddr,
    input  logic        awvalid,
    output logic        awready,
    input  logic [31:0] wdata,
    input  logic [3:0]  wstrb,
    input  logic        wvalid,
    output logic        wready,
    output logic [1:0]  bresp,
    output logic        bvalid,
    input  logic        bready,
    input  logic [5:0]  araddr,
    input  logic        arvalid,
    output logic        arready,
    output logic [31:0] rdata,
    output logic [1:0]  rresp,
    output logic        rvalid,
    input  logic        rready,

    input  logic [7:0]  s_tdata,
    input  logic        s_tvalid,
    output logic        s_tready,
    output logic [7:0]  m_tdata,
    output logic        m_tvalid,
    input  logic        m_tready,
    output logic        m_tlast
);

    logic               cfg_first, cfg_last, cfg_gate, start, clear_skips, idle, active;
    logic [3:0]         cfg_shift;
    logic [5:0]         cfg_width, cfg_height;
    logic signed [23:0] cfg_bias;
    logic [71:0]        cfg_w_flat;
    logic [31:0]        skip_count;

    engine_regs #(.ACC_W(24), .DIM_W(6)) u_regs (
        .clk, .rst_n,
        .awaddr, .awvalid, .awready, .wdata, .wstrb, .wvalid, .wready,
        .bresp, .bvalid, .bready, .araddr, .arvalid, .arready,
        .rdata, .rresp, .rvalid, .rready,
        .cfg_first, .cfg_last, .cfg_gate, .cfg_shift, .cfg_width, .cfg_height,
        .cfg_bias, .cfg_w_flat, .start, .clear_skips, .skip_count, .idle, .active
    );

    conv_engine #(.ACC_W(24), .DIM_W(6), .ACC_ADDR_W(10), .FIFO_AW(4)) u_engine (
        .clk, .rst_n,
        .cfg_first, .cfg_last, .cfg_gate, .cfg_shift, .cfg_width, .cfg_height,
        .cfg_bias, .cfg_w_flat, .start, .clear_skips,
        .s_tdata, .s_tvalid, .s_tready,
        .m_tdata, .m_tvalid, .m_tready, .m_tlast,
        .skip_count, .idle, .active
    );

endmodule
