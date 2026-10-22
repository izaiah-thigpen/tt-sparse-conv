// mac_core.sv
//
// One multiply-accumulate unit with zero-skip gating and the output stage.
// This is the core of the Tiny Tapeout chip; the FPGA engine uses nine of them.
//
// Arithmetic matches model/refmodel.py exactly:
//   activation  unsigned 8-bit      weight  signed 8-bit (-127..127)
//   product     signed 17-bit       accumulator  signed ACC_W-bit
//   result      (acc >>> shift), then ReLU, then saturate to 0..255
//
// Pipeline (one tap accepted per cycle):
//   stage 1  operand registers pix_q / wt_q, plus control flags
//   stage 2  multiply and add into the accumulator
// A tap presented on clock edge N is in the accumulator after edge N+1.
//
// Zero-skip gating: a tap is a "zero tap" when its pixel or weight is zero.
// With gate_en high, a zero tap leaves the operand registers holding their old
// values (so the multiplier inputs do not toggle) and the accumulator does not
// update. With gate_en low, the zero operand goes through and adds zero. The
// accumulator value is identical either way; only switching activity differs.
//
// Clock gating: three clock gates stop the registers' clocks whenever they
// would not change: the operand registers on gated zero taps and when no tap
// arrives, the accumulator when it neither loads nor adds, and the skip counter
// when there is no zero tap and no clear. Most of a register's power is its
// clock, so this is where most of the zero-skip saving comes from. Every
// register keeps its load enable as well, so the logic is correct with or
// without the gates (the FPGA build has none). With gate_en low (BYPASS),
// zero taps clock the operand registers and accumulator like any other tap.
//
// Protocol: assert `load` only when no tap is in flight (one idle cycle after
// the last tap). `load` has priority over accumulation.

// Clock gate. ASIC: SkyWater's latch-based integrated clock gate (glitch-free:
// the enable is latched while the clock is low). Simulation defines
// BEHAVIORAL_CLOCK_GATE for an equivalent model; FPGA builds define
// NO_CLOCK_GATE and pass the clock through.
module mac_clock_gate (
    input  logic clk,
    input  logic en,
    output logic gclk
);
`ifdef NO_CLOCK_GATE
    assign gclk = clk;
`elsif BEHAVIORAL_CLOCK_GATE
    logic en_latched;
    always_latch if (!clk) en_latched = en;
    assign gclk = clk & en_latched;
`else
    sky130_fd_sc_hd__dlclkp_1 u_icg (.CLK(clk), .GATE(en), .GCLK(gclk));
`endif
endmodule


module mac_core #(
    parameter int ACC_W = 24
) (
    input  logic                    clk,
    input  logic                    rst_n,         // asynchronous, active low

    // Accumulator control
    input  logic                    load,          // acc <= load_value (bias, or 0 to clear)
    input  logic signed [ACC_W-1:0] load_value,

    // Taps, one per cycle
    input  logic                    tap_valid,
    input  logic        [7:0]       pixel,         // unsigned activation
    input  logic signed [7:0]       weight,        // signed weight
    input  logic                    gate_en,       // 1 = gating active

    // Skip counter
    input  logic                    clear_skips,

    // Output stage
    input  logic        [3:0]       shift,

    output logic signed [ACC_W-1:0] acc,
    output logic        [7:0]       result,        // combinational from acc and shift
    output logic                    skip,          // high one cycle per zero tap
    output logic        [15:0]      skip_count     // saturating count of zero taps
);

    // ------------------------------------------------------------------
    // Zero detection (combinational, on the incoming tap)
    // ------------------------------------------------------------------
    logic zero_tap;   // either operand is zero
    logic hold;       // gate this tap: freeze operands and accumulator

    assign zero_tap = (pixel == 8'd0) || (weight == 8'sd0);
    assign hold     = tap_valid && zero_tap && gate_en;

    // ------------------------------------------------------------------
    // Clock gates (enables match the registers' own load conditions)
    // ------------------------------------------------------------------
    logic acc_en_q;   // stage 2 should add this cycle's product
    logic clk_op, clk_acc, clk_skip;

    mac_clock_gate u_cg_op   (.clk(clk), .en(tap_valid && !hold),              .gclk(clk_op));
    mac_clock_gate u_cg_acc  (.clk(clk), .en(load || acc_en_q),                .gclk(clk_acc));
    mac_clock_gate u_cg_skip (.clk(clk), .en(clear_skips || (tap_valid && zero_tap)), .gclk(clk_skip));

    // ------------------------------------------------------------------
    // Stage 1: operand isolation registers
    // ------------------------------------------------------------------
    logic        [7:0] pix_q;
    logic signed [7:0] wt_q;

    // Load enable instead of a free-running register: when a zero tap is
    // gated, the multiplier sees the same inputs as last cycle.
    always_ff @(posedge clk_op or negedge rst_n) begin
        if (!rst_n) begin
            pix_q <= '0;
            wt_q  <= '0;
        end else if (tap_valid && !hold) begin
            pix_q <= pixel;
            wt_q  <= weight;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc_en_q <= 1'b0;
            skip     <= 1'b0;
        end else begin
            acc_en_q <= tap_valid && !hold;
            skip     <= tap_valid && zero_tap;   // reported whether or not gated
        end
    end

    // ------------------------------------------------------------------
    // Stage 2: multiply and accumulate
    // ------------------------------------------------------------------
    // Zero-extend the pixel to 9 bits so a signed multiply treats it as positive.
    // 9-bit x 8-bit signed fits in 17 bits: |255 * -127| = 32,385 < 65,536.
    logic signed [16:0] product;
    assign product = $signed({1'b0, pix_q}) * wt_q;

    always_ff @(posedge clk_acc or negedge rst_n) begin
        if (!rst_n)
            acc <= '0;
        else if (load)
            acc <= load_value;
        else if (acc_en_q)
            acc <= acc + {{(ACC_W-17){product[16]}}, product};   // sign-extend
    end

    // ------------------------------------------------------------------
    // Skip counter (counts zero taps in both modes, so gated and bypass runs
    // can be compared directly)
    // ------------------------------------------------------------------
    always_ff @(posedge clk_skip or negedge rst_n) begin
        if (!rst_n)
            skip_count <= '0;
        else if (clear_skips)
            skip_count <= '0;
        else if (tap_valid && zero_tap && skip_count != 16'hFFFF)
            skip_count <= skip_count + 16'd1;
    end

    // ------------------------------------------------------------------
    // Output stage: arithmetic shift (rounds toward -inf), ReLU, saturate.
    // The output is unsigned, so ReLU and the low clamp are the same step.
    // ------------------------------------------------------------------
    logic signed [ACC_W-1:0] shifted;
    assign shifted = acc >>> shift;

    assign result = (shifted < 0)   ? 8'd0   :
                    (shifted > 255) ? 8'd255 :
                                      shifted[7:0];

endmodule
