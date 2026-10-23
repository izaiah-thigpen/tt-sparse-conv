// conv_engine.sv
//
// FPGA convolution engine: one 3x3 kernel over one input channel per pass,
// one pixel per clock, with nine multiply units working in parallel.
//
// A layer with C input channels is C passes of the same kernel position:
//   pass 0         first=1: the sum starts from the bias
//   passes 1..C-2  partial sums are read from and written back to the
//                  accumulation buffer
//   pass C-1       last=1: shift, clamp, and stream the result out
// A single-channel layer is one pass with first=1 and last=1.
//
// Arithmetic is identical to the chip and to model/refmodel.py: unsigned
// 8-bit pixels, signed 8-bit weights, signed ACC_W-bit sums, output
// (sum >>> shift) clamped to 0..255.
//
// Zero-skip gating, per multiply unit: when a tap's pixel or weight is zero
// and gating is on, the unit's operand register and product register hold
// their values and a mask removes the product from the sum. The result is
// unchanged; the multiplier does not switch.
//
// Data flow: pixels arrive row-major on a valid/ready stream. Two line
// buffers hold the previous two rows, so every pixel completes a 3x3 window
// once row >= 2 and column >= 2. Results leave through a small FIFO. When
// the FIFO is full the whole pipeline pauses, including the stage that
// writes into it, so output backpressure of any length is safe.
//
// Pipeline:  S1 window   S2 operands   S3 products   S4 partial sums
//            S5 total    then FIFO (last pass) or accumulation buffer

module conv_engine #(
    parameter int ACC_W      = 24,
    parameter int DIM_W      = 6,      // width and height up to 63
    parameter int ACC_ADDR_W = 10,     // accumulation buffer: 1024 outputs
    parameter int FIFO_AW    = 4       // output FIFO: 16 entries
) (
    input  logic                     clk,
    input  logic                     rst_n,

    // Configuration, held constant during a pass
    input  logic                     cfg_first,
    input  logic                     cfg_last,
    input  logic                     cfg_gate,
    input  logic        [3:0]        cfg_shift,
    input  logic        [DIM_W-1:0]  cfg_width,
    input  logic        [DIM_W-1:0]  cfg_height,
    input  logic signed [ACC_W-1:0]  cfg_bias,
    input  logic        [71:0]       cfg_w_flat,     // 3x3 kernel, w0 in [7:0], row-major

    input  logic                     start,          // pulse: begin a pass
    input  logic                     clear_skips,

    // Pixel stream in (row-major)
    input  logic        [7:0]        s_tdata,
    input  logic                     s_tvalid,
    output logic                     s_tready,

    // Result stream out (last pass only), row-major over valid positions
    output logic        [7:0]        m_tdata,
    output logic                     m_tvalid,
    input  logic                     m_tready,
    output logic                     m_tlast,

    output logic        [31:0]       skip_count,     // zero-operand taps
    output logic                     idle,           // pass finished, pipeline empty
    output logic                     active          // accepting a frame
);

    localparam int FIFO_DEPTH = 1 << FIFO_AW;

    // Weights arrive packed (array ports are not portable across tools)
    logic signed [7:0] cfg_w [9];
    for (genvar i = 0; i < 9; i++) begin : g_w
        assign cfg_w[i] = cfg_w_flat[8*i +: 8];
    end

    // ------------------------------------------------------------------
    // Pass control
    // ------------------------------------------------------------------
    logic [DIM_W-1:0]      col, row;
    logic [2*DIM_W-1:0]    pix_left;          // pixels still to accept
    logic [ACC_ADDR_W-1:0] out_idx;           // output index of the next window
    logic [2*DIM_W-1:0]    n_out;             // outputs in this pass
    logic [2*DIM_W-1:0]    out_cnt;           // outputs streamed so far

    // The pipeline advances whenever the output FIFO has room. Every stage,
    // including the FIFO write, uses this enable, so the FIFO cannot overflow.
    logic [FIFO_AW:0] fifo_count;
    logic             en;
    assign en = (fifo_count != (FIFO_AW+1)'(FIFO_DEPTH));

    logic accept;
    assign s_tready = en & active;
    assign accept   = s_tvalid & s_tready;

    // ------------------------------------------------------------------
    // Line buffers and the 3x3 window (stage 1)
    // ------------------------------------------------------------------
    logic [7:0] lb0 [1 << DIM_W];   // row r-1
    logic [7:0] lb1 [1 << DIM_W];   // row r-2
    logic [7:0] win [9];            // win[r*3+c], r=0 is the oldest row
    logic       v1;
    logic [ACC_ADDR_W-1:0] idx1;

    always_ff @(posedge clk) begin
        if (accept) begin
            lb1[col] <= lb0[col];
            lb0[col] <= s_tdata;
            for (int r = 0; r < 3; r++) begin
                win[r*3 + 0] <= win[r*3 + 1];
                win[r*3 + 1] <= win[r*3 + 2];
            end
            win[2] <= lb1[col];
            win[5] <= lb0[col];
            win[8] <= s_tdata;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            col <= '0; row <= '0; pix_left <= '0; out_idx <= '0;
            n_out <= '0; active <= 1'b0; v1 <= 1'b0; idx1 <= '0;
        end else begin
            if (start) begin
                col      <= '0;
                row      <= '0;
                out_idx  <= '0;
                pix_left <= cfg_width * cfg_height;
                n_out    <= {{DIM_W{1'b0}}, cfg_width - DIM_W'(2)}
                          * {{DIM_W{1'b0}}, cfg_height - DIM_W'(2)};
                active   <= 1'b1;
            end else if (en) begin
                v1 <= accept && (row >= DIM_W'(2)) && (col >= DIM_W'(2));
                if (accept) begin
                    idx1 <= out_idx;
                    if (row >= DIM_W'(2) && col >= DIM_W'(2)) out_idx <= out_idx + 1'b1;
                    if (col == cfg_width - 1'b1) begin
                        col <= '0;
                        row <= row + 1'b1;
                    end else begin
                        col <= col + 1'b1;
                    end
                    pix_left <= pix_left - 1'b1;
                    if (pix_left == 1) active <= 1'b0;
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // Stage 2: zero detect and operand isolation, per unit
    // ------------------------------------------------------------------
    logic [8:0]            zero1;
    logic [7:0]            pix_q [9];
    logic [8:0]            mask2;            // product counts toward the sum
    logic                  v2;
    logic [ACC_ADDR_W-1:0] idx2;
    logic [3:0]            zeros2;

    // Continuous assignments, not always_comb: some simulators do not
    // re-evaluate always_comb when an element of an array changes.
    for (genvar i = 0; i < 9; i++) begin : g_zero
        assign zero1[i] = (win[i] == 8'd0) || (cfg_w[i] == 8'sd0);
    end

    function automatic logic [3:0] popcount9(input logic [8:0] b);
        popcount9 = 4'd0;
        for (int i = 0; i < 9; i++) popcount9 = popcount9 + {3'd0, b[i]};
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < 9; i++) pix_q[i] <= '0;
            mask2 <= '0; v2 <= 1'b0; idx2 <= '0; zeros2 <= '0;
        end else if (en) begin
            v2     <= v1;
            idx2   <= idx1;
            zeros2 <= v1 ? popcount9(zero1) : 4'd0;
            for (int i = 0; i < 9; i++) begin
                // Gated: a valid zero tap leaves the operand register alone
                if (v1 && !(cfg_gate && zero1[i])) pix_q[i] <= win[i];
                mask2[i] <= v1 && !(cfg_gate && zero1[i]);
            end
        end
    end

    // ------------------------------------------------------------------
    // Stage 3: nine products; read the partial sum from the buffer
    // ------------------------------------------------------------------
    logic signed [16:0]     prod3 [9];
    logic [8:0]             mask3;
    logic                   v3;
    logic [ACC_ADDR_W-1:0]  idx3;
    logic signed [ACC_W-1:0] acc_mem [1 << ACC_ADDR_W];
    logic signed [ACC_W-1:0] acc_rd3;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < 9; i++) prod3[i] <= '0;
            mask3 <= '0; v3 <= 1'b0; idx3 <= '0;
        end else if (en) begin
            v3    <= v2;
            idx3  <= idx2;
            mask3 <= mask2;
            for (int i = 0; i < 9; i++)
                if (mask2[i]) prod3[i] <= $signed({1'b0, pix_q[i]}) * cfg_w[i];
        end
    end

    // Block RAM read port (registered output)
    always_ff @(posedge clk)
        if (en) acc_rd3 <= acc_mem[idx2];

    // ------------------------------------------------------------------
    // Stage 4: three partial sums of three products
    // ------------------------------------------------------------------
    logic signed [18:0]     part4 [3];
    logic signed [ACC_W-1:0] acc_rd4;
    logic                   v4;
    logic [ACC_ADDR_W-1:0]  idx4;

    function automatic logic signed [16:0] masked(input logic signed [16:0] p, input logic m);
        masked = m ? p : 17'sd0;
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int g = 0; g < 3; g++) part4[g] <= '0;
            acc_rd4 <= '0; v4 <= 1'b0; idx4 <= '0;
        end else if (en) begin
            v4      <= v3;
            idx4    <= idx3;
            acc_rd4 <= acc_rd3;
            for (int g = 0; g < 3; g++)
                part4[g] <= 19'(masked(prod3[3*g], mask3[3*g]))
                          + 19'(masked(prod3[3*g+1], mask3[3*g+1]))
                          + 19'(masked(prod3[3*g+2], mask3[3*g+2]));
        end
    end

    // ------------------------------------------------------------------
    // Stage 5: add the partial sums to the bias or the running total
    // ------------------------------------------------------------------
    logic signed [ACC_W-1:0] total5;
    logic                    v5;
    logic [ACC_ADDR_W-1:0]   idx5;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            total5 <= '0; v5 <= 1'b0; idx5 <= '0;
        end else if (en) begin
            v5     <= v4;
            idx5   <= idx4;
            total5 <= ACC_W'(part4[0]) + ACC_W'(part4[1]) + ACC_W'(part4[2])
                    + (cfg_first ? cfg_bias : acc_rd4);
        end
    end

    // Not the last pass: write the running total back
    always_ff @(posedge clk)
        if (en && v5 && !cfg_last) acc_mem[idx5] <= total5;

    // Last pass: shift, clamp, and queue the result
    logic signed [ACC_W-1:0] shifted5;
    logic        [7:0]       result5;
    assign shifted5 = total5 >>> cfg_shift;
    assign result5  = (shifted5 < 0) ? 8'd0 : (shifted5 > 255) ? 8'd255 : shifted5[7:0];

    // ------------------------------------------------------------------
    // Output FIFO
    // ------------------------------------------------------------------
    logic [8:0]          fifo_mem [FIFO_DEPTH];   // {last, data}
    logic [FIFO_AW-1:0]  wr_ptr, rd_ptr;
    logic                push, pop;

    assign push     = en && v5 && cfg_last;
    assign m_tvalid = (fifo_count != 0);
    assign pop      = m_tvalid && m_tready;
    assign {m_tlast, m_tdata} = fifo_mem[rd_ptr];

    always_ff @(posedge clk)
        if (push) fifo_mem[wr_ptr] <= {(out_cnt == n_out - 1'b1), result5};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0; rd_ptr <= '0; fifo_count <= '0; out_cnt <= '0;
        end else begin
            if (start) out_cnt <= '0;
            else if (push) out_cnt <= out_cnt + 1'b1;
            if (push) wr_ptr <= wr_ptr + 1'b1;
            if (pop)  rd_ptr <= rd_ptr + 1'b1;
            fifo_count <= fifo_count + {{FIFO_AW{1'b0}}, push} - {{FIFO_AW{1'b0}}, pop};
        end
    end

    // ------------------------------------------------------------------
    // Skip counter and status
    // ------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            skip_count <= '0;
        else if (clear_skips)
            skip_count <= '0;
        else if (en && v2)
            skip_count <= skip_count + {28'd0, zeros2};
    end

    assign idle = !active && !(v1 || v2 || v3 || v4 || v5) && (fifo_count == 0);

endmodule
