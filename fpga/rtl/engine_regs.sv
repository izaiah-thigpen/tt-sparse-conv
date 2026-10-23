// engine_regs.sv
//
// AXI4-Lite control registers for conv_engine. One outstanding transaction
// at a time, which is all the Zynq's general-purpose port needs.
//
// Offset  Name    Access  Contents
// 0x00    CTRL    RW      [0] first  [1] last  [2] gate enable  [11:8] shift
// 0x04    DIMS    RW      [5:0] width  [13:8] height
// 0x08    BIAS    RW      [23:0] signed bias
// 0x0C    W0_3    RW      weights 0..3, one byte each, w0 in [7:0]
// 0x10    W4_7    RW      weights 4..7
// 0x14    W8      RW      [7:0] weight 8
// 0x18    SKIPS   RO/W    zero-operand tap count; any write clears it
// 0x1C    STATUS  RO      [0] idle  [1] active
// 0x20    START   WO      any write starts a pass with the current settings
// 0x24    ID      RO      0x5C0E0001
//
// Reset values: gating on, shift 0, first = last = 1, 32 x 32.

module engine_regs #(
    parameter int ACC_W = 24,
    parameter int DIM_W = 6
) (
    input  logic                    clk,
    input  logic                    rst_n,

    // AXI4-Lite slave
    input  logic [5:0]              awaddr,
    input  logic                    awvalid,
    output logic                    awready,
    input  logic [31:0]             wdata,
    input  logic [3:0]              wstrb,
    input  logic                    wvalid,
    output logic                    wready,
    output logic [1:0]              bresp,
    output logic                    bvalid,
    input  logic                    bready,
    input  logic [5:0]              araddr,
    input  logic                    arvalid,
    output logic                    arready,
    output logic [31:0]             rdata,
    output logic [1:0]              rresp,
    output logic                    rvalid,
    input  logic                    rready,

    // To and from the engine
    output logic                    cfg_first,
    output logic                    cfg_last,
    output logic                    cfg_gate,
    output logic [3:0]              cfg_shift,
    output logic [DIM_W-1:0]        cfg_width,
    output logic [DIM_W-1:0]        cfg_height,
    output logic signed [ACC_W-1:0] cfg_bias,
    output logic [71:0]             cfg_w_flat,     // w0 in [7:0]
    output logic                    start,
    output logic                    clear_skips,
    input  logic [31:0]             skip_count,
    input  logic                    idle,
    input  logic                    active
);

    localparam logic [31:0] ID = 32'h5C0E_0001;

    // ------------------------------------------------------------------
    // Writes: take address and data in either order, then respond
    // ------------------------------------------------------------------
    logic [5:0]  wr_addr;
    logic [31:0] wr_data;
    logic        have_aw, have_w;

    assign awready = !have_aw && !bvalid;
    assign wready  = !have_w && !bvalid;
    assign bresp   = 2'b00;

    // Byte-enable merge of new data into an existing register
    function automatic logic [31:0] merge(input logic [31:0] old, input logic [31:0] d,
                                          input logic [3:0] s);
        for (int b = 0; b < 4; b++) merge[8*b +: 8] = s[b] ? d[8*b +: 8] : old[8*b +: 8];
    endfunction

    logic [3:0]  wr_strb;
    logic [31:0] ctrl_q, dims_q, bias_q, w03_q, w47_q, w8_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            have_aw <= 1'b0; have_w <= 1'b0; bvalid <= 1'b0;
            wr_addr <= '0; wr_data <= '0; wr_strb <= '0;
            ctrl_q  <= 32'h0000_0007;            // first, last, gate on
            dims_q  <= {16'd0, 2'd0, 6'd32, 2'd0, 6'd32};   // height [13:8], width [5:0]
            bias_q  <= '0; w03_q <= '0; w47_q <= '0; w8_q <= '0;
            start   <= 1'b0; clear_skips <= 1'b0;
        end else begin
            start       <= 1'b0;
            clear_skips <= 1'b0;
            if (awvalid && awready) begin wr_addr <= awaddr; have_aw <= 1'b1; end
            if (wvalid && wready)   begin wr_data <= wdata; wr_strb <= wstrb; have_w <= 1'b1; end

            if (have_aw && have_w) begin
                case (wr_addr[5:2])
                    4'h0: ctrl_q <= merge(ctrl_q, wr_data, wr_strb);
                    4'h1: dims_q <= merge(dims_q, wr_data, wr_strb);
                    4'h2: bias_q <= merge(bias_q, wr_data, wr_strb);
                    4'h3: w03_q  <= merge(w03_q,  wr_data, wr_strb);
                    4'h4: w47_q  <= merge(w47_q,  wr_data, wr_strb);
                    4'h5: w8_q   <= merge(w8_q,   wr_data, wr_strb);
                    4'h6: clear_skips <= 1'b1;
                    4'h8: start <= 1'b1;
                    default: ;
                endcase
                have_aw <= 1'b0;
                have_w  <= 1'b0;
                bvalid  <= 1'b1;
            end else if (bvalid && bready) begin
                bvalid <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------------
    // Reads
    // ------------------------------------------------------------------
    assign arready = !rvalid;
    assign rresp   = 2'b00;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rvalid <= 1'b0; rdata <= '0;
        end else if (arvalid && arready) begin
            rvalid <= 1'b1;
            case (araddr[5:2])
                4'h0: rdata <= ctrl_q;
                4'h1: rdata <= dims_q;
                4'h2: rdata <= bias_q;
                4'h3: rdata <= w03_q;
                4'h4: rdata <= w47_q;
                4'h5: rdata <= w8_q;
                4'h6: rdata <= skip_count;
                4'h7: rdata <= {30'd0, active, idle};
                4'h9: rdata <= ID;
                default: rdata <= '0;
            endcase
        end else if (rvalid && rready) begin
            rvalid <= 1'b0;
        end
    end

    // ------------------------------------------------------------------
    // Decoded configuration
    // ------------------------------------------------------------------
    assign cfg_first  = ctrl_q[0];
    assign cfg_last   = ctrl_q[1];
    assign cfg_gate   = ctrl_q[2];
    assign cfg_shift  = ctrl_q[11:8];
    assign cfg_width  = dims_q[DIM_W-1:0];
    assign cfg_height = dims_q[8 +: DIM_W];
    assign cfg_bias   = ACC_W'($signed(bias_q[23:0]));
    assign cfg_w_flat = {w8_q[7:0], w47_q, w03_q};

    // Registers are word-aligned; the byte-offset bits are ignored
    logic unused_ok;
    assign unused_ok = &{1'b0, araddr[1:0], wr_addr[1:0]};

endmodule
