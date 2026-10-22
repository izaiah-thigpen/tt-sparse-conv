// conv_chip.sv
//
// The chip: an SPI command interface wrapped around mac_core.
//
// SPI: mode 0 (SCLK idles low, MOSI sampled on the rising edge, MISO changes on
// the falling edge), most significant bit first. The SPI pins are sampled with
// the system clock through two-flop synchronizers, so clk must run at least
// 8x faster than SCLK.
//
// Commands (one opcode byte, then its payload; several commands may share one
// chip-select frame; bytes that are not a known opcode are ignored, so 0x00
// works as a no-op):
//
//   0x01 WRITE_WEIGHTS  9 bytes in    nine signed weights, row-major
//   0x02 LOAD_ACC       3 bytes in    accumulator preload (bias), MSB first
//   0x03 WRITE_CONFIG   1 byte in     [3:0] shift, [4] gating enable
//   0x10 COMPUTE        9 bytes in    nine pixels; each tap is issued as its
//                                     byte arrives, so no pixel buffer is needed
//   0x20 READ_RESULT    1 byte out    shift, ReLU, saturate of the accumulator
//   0x21 READ_ACC       3 bytes out   raw accumulator, MSB first
//   0x22 READ_SKIPS     2 bytes out   skip counter, MSB first
//   0x23 CLEAR_SKIPS    none
//   0x30 SET_ACTIVITY   1 byte in     zero threshold T for activity mode (0-255)
//   0x31 RUN            3 bytes in    activity mode: N taps, MSB first; N = 0 runs until STOP
//   0x32 STOP           none          ends an activity run
//   0x7F READ_ID        1 byte out    0xA5
//
// Activity mode (for measuring the gating's energy saving on silicon): the
// multiplier takes one tap every clock, with no SPI traffic. Pixels come from
// an xorshift32 generator seeded with 0x2545F491 at each RUN: a pixel is 0 when
// the state's top byte is below T (a share of about T/256), otherwise
// {state[7:1], 1}. Weights cycle through the nine loaded weights, starting at
// weight 0. The generator advances after every tap. Load the accumulator and
// clear the skip counter first; BUSY is high while running and DONE rises when
// it ends. Gating and BYPASS apply as usual, so the same run can be measured
// gated and ungated. Do not send COMPUTE during a run.
//
// For a read, the response comes out on MISO during the bytes that follow the
// opcode; the host sends dummy bytes (0x00) to clock it out.
//
// Raising chip select mid-command stops the command. LOAD_ACC and WRITE_CONFIG
// take effect only when complete. WRITE_WEIGHTS and COMPUTE act byte by byte,
// so bytes already received have taken effect (this avoids 144 flip-flops of
// shadow storage, which matters on a Tiny Tapeout tile).
//
// Gating is active when the config gating bit is 1 and the BYPASS pin is low.

module conv_chip #(
    parameter int ACC_W = 24
) (
    input  logic       clk,
    input  logic       rst_n,

    input  logic       spi_sclk,
    input  logic       spi_cs_n,
    input  logic       spi_mosi,
    output logic       spi_miso,

    input  logic       bypass,      // 1 = gating off, regardless of config

    output logic       done,        // high after a COMPUTE or activity run finishes, until the next starts
    output logic       busy,        // high during a COMPUTE or an activity run
    output logic       skip,        // high one cycle per zero tap (scope probe)
    output logic [3:0] tap          // tap index within the current COMPUTE (debug)
);

    localparam logic [7:0] OP_WRITE_WEIGHTS = 8'h01;
    localparam logic [7:0] OP_LOAD_ACC      = 8'h02;
    localparam logic [7:0] OP_WRITE_CONFIG  = 8'h03;
    localparam logic [7:0] OP_COMPUTE       = 8'h10;
    localparam logic [7:0] OP_READ_RESULT   = 8'h20;
    localparam logic [7:0] OP_READ_ACC      = 8'h21;
    localparam logic [7:0] OP_READ_SKIPS    = 8'h22;
    localparam logic [7:0] OP_CLEAR_SKIPS   = 8'h23;
    localparam logic [7:0] OP_SET_ACTIVITY  = 8'h30;
    localparam logic [7:0] OP_RUN           = 8'h31;
    localparam logic [7:0] OP_STOP          = 8'h32;
    localparam logic [7:0] OP_READ_ID       = 8'h7F;
    localparam logic [7:0] CHIP_ID          = 8'hA5;
    localparam logic [31:0] ACT_SEED        = 32'h2545F491;

    // ------------------------------------------------------------------
    // Input synchronizers (SPI pins and BYPASS are asynchronous to clk)
    // ------------------------------------------------------------------
    logic [2:0] sclk_r;
    logic [2:0] cs_r;
    logic [1:0] mosi_r;
    logic [1:0] bypass_r;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sclk_r   <= 3'b000;
            cs_r     <= 3'b111;
            mosi_r   <= 2'b00;
            bypass_r <= 2'b00;
        end else begin
            sclk_r   <= {sclk_r[1:0], spi_sclk};
            cs_r     <= {cs_r[1:0], spi_cs_n};
            mosi_r   <= {mosi_r[0], spi_mosi};
            bypass_r <= {bypass_r[0], bypass};
        end
    end

    logic sclk_rise, sclk_fall, cs_active, cs_end, mosi_s, bypass_s;
    assign sclk_rise = sclk_r[1] & ~sclk_r[2];
    assign sclk_fall = ~sclk_r[1] & sclk_r[2];
    assign cs_active = ~cs_r[1];
    assign cs_end    = cs_r[1] & ~cs_r[2];      // chip select just released
    assign mosi_s    = mosi_r[1];               // same delay as sclk_r[1]
    assign bypass_s  = bypass_r[1];

    // ------------------------------------------------------------------
    // SPI receive: shift in on SCLK rising edges, flag each complete byte
    // ------------------------------------------------------------------
    logic [2:0] bit_cnt;
    logic [6:0] rx_sh;
    logic       byte_done;
    logic [7:0] rx_byte;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bit_cnt   <= '0;
            rx_sh     <= '0;
            rx_byte   <= '0;
            byte_done <= 1'b0;
        end else begin
            byte_done <= 1'b0;
            if (!cs_active) begin
                bit_cnt <= '0;
            end else if (sclk_rise) begin
                rx_sh   <= {rx_sh[5:0], mosi_s};
                bit_cnt <= bit_cnt + 3'd1;
                if (bit_cnt == 3'd7) begin
                    rx_byte   <= {rx_sh, mosi_s};
                    byte_done <= 1'b1;
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // SPI transmit: on the falling edge that ends a byte, load the next
    // response byte; on other falling edges, shift
    // ------------------------------------------------------------------
    logic [7:0] tx_sh;
    logic [7:0] tx_next;   // set by the decoder after each received byte

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tx_sh <= '0;
        end else if (!cs_active) begin
            tx_sh <= '0;
        end else if (sclk_fall) begin
            if (bit_cnt == 3'd0)
                tx_sh <= tx_next;
            else
                tx_sh <= {tx_sh[6:0], 1'b0};
        end
    end

    assign spi_miso = cs_active & tx_sh[7];

    // ------------------------------------------------------------------
    // Command decoder
    // ------------------------------------------------------------------
    typedef enum logic [2:0] {
        S_IDLE, S_WEIGHTS, S_LOAD_ACC, S_CONFIG, S_COMPUTE, S_READ, S_ACT_CFG, S_RUN_CNT
    } state_t;

    state_t            state;
    logic        [3:0] idx;            // byte index within a payload
    logic signed [7:0] w [9];          // weight registers
    logic       [15:0] acc_buf;        // first two LOAD_ACC bytes
    logic        [3:0] cfg_shift;
    logic              cfg_gate;
    logic       [15:0] resp_buf;       // response bytes still to send
    logic        [1:0] resp_left;      // response bytes the host will clock

    // Activity mode
    logic        [7:0] act_thresh;     // pixel is zero when rng[31:24] < act_thresh
    logic              running;
    logic              run_forever;    // RUN with N = 0: until STOP
    logic       [23:0] run_left;       // taps still to issue
    logic       [31:0] rng;            // xorshift32 state
    logic        [3:0] widx;           // weight used by the next activity tap
    logic       [31:0] rng_a, rng_b, rng_next;
    logic        [7:0] act_pixel;
    logic              run_start;

    assign rng_a     = rng   ^ (rng   << 13);
    assign rng_b     = rng_a ^ (rng_a >> 17);
    assign rng_next  = rng_b ^ (rng_b << 5);
    assign act_pixel = (rng[31:24] < act_thresh) ? 8'd0 : {rng[7:1], 1'b1};
    assign run_start = byte_done && !cs_end && (state == S_RUN_CNT) && (idx == 4'd2);

    // Signals into mac_core, registered here
    logic                    mac_load;
    logic signed [ACC_W-1:0] mac_load_value;
    logic                    mac_tap_valid;
    logic              [7:0] mac_pixel;
    logic signed       [7:0] mac_weight;
    logic                    mac_clear_skips;
    logic                    last_tap;
    logic              [1:0] done_pipe;      // last_tap delayed to match the mac pipeline

    // Outputs from mac_core
    logic signed [ACC_W-1:0] mac_acc;
    logic              [7:0] mac_result;
    logic             [15:0] mac_skip_count;

    // Accumulator sign-extended to the 24-bit READ_ACC field
    logic signed [23:0] acc24;
    assign acc24 = 24'(mac_acc);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= S_IDLE;
            idx             <= '0;
            for (int i = 0; i < 9; i++) w[i] <= '0;
            acc_buf         <= '0;
            cfg_shift       <= '0;
            cfg_gate        <= 1'b1;
            resp_buf        <= '0;
            resp_left       <= '0;
            tx_next         <= '0;
            mac_load        <= 1'b0;
            mac_load_value  <= '0;
            mac_tap_valid   <= 1'b0;
            mac_pixel       <= '0;
            mac_weight      <= '0;
            mac_clear_skips <= 1'b0;
            last_tap        <= 1'b0;
            busy            <= 1'b0;
            act_thresh      <= '0;
            running         <= 1'b0;
            run_forever     <= 1'b0;
            run_left        <= '0;
            rng             <= ACT_SEED;
            widx            <= '0;
        end else begin
            // One-cycle strobes
            mac_load        <= 1'b0;
            mac_tap_valid   <= 1'b0;
            mac_clear_skips <= 1'b0;
            last_tap        <= 1'b0;

            if (cs_end) begin
                state   <= S_IDLE;     // abandon any unfinished command
                idx     <= '0;
                tx_next <= '0;
                if (state == S_COMPUTE) busy <= 1'b0;
            end else if (byte_done) begin
                tx_next <= 8'h00;      // default: nothing to say next byte
                case (state)
                    S_IDLE: begin
                        idx <= '0;
                        case (rx_byte)
                            OP_WRITE_WEIGHTS: state <= S_WEIGHTS;
                            OP_LOAD_ACC:      state <= S_LOAD_ACC;
                            OP_WRITE_CONFIG:  state <= S_CONFIG;
                            OP_COMPUTE: begin
                                state <= S_COMPUTE;
                                busy  <= 1'b1;
                            end
                            OP_CLEAR_SKIPS:   mac_clear_skips <= 1'b1;
                            OP_SET_ACTIVITY:  state <= S_ACT_CFG;
                            OP_RUN:           state <= S_RUN_CNT;
                            OP_STOP: begin
                                if (running) begin
                                    running  <= 1'b0;
                                    last_tap <= 1'b1;
                                end
                            end
                            OP_READ_RESULT: begin
                                tx_next   <= mac_result;
                                resp_left <= 2'd1;
                                state     <= S_READ;
                            end
                            OP_READ_ACC: begin
                                tx_next   <= acc24[23:16];
                                resp_buf  <= acc24[15:0];
                                resp_left <= 2'd3;
                                state     <= S_READ;
                            end
                            OP_READ_SKIPS: begin
                                tx_next   <= mac_skip_count[15:8];
                                resp_buf  <= {mac_skip_count[7:0], 8'h00};
                                resp_left <= 2'd2;
                                state     <= S_READ;
                            end
                            OP_READ_ID: begin
                                tx_next   <= CHIP_ID;
                                resp_left <= 2'd1;
                                state     <= S_READ;
                            end
                            default: ;  // unknown opcode: ignore
                        endcase
                    end

                    S_WEIGHTS: begin
                        w[idx] <= rx_byte;
                        idx    <= idx + 4'd1;
                        if (idx == 4'd8) state <= S_IDLE;
                    end

                    S_LOAD_ACC: begin
                        idx <= idx + 4'd1;
                        if (idx == 4'd2) begin
                            mac_load       <= 1'b1;
                            mac_load_value <= ACC_W'($signed({acc_buf, rx_byte}));
                            state          <= S_IDLE;
                        end else begin
                            acc_buf <= {acc_buf[7:0], rx_byte};
                        end
                    end

                    S_CONFIG: begin
                        cfg_shift <= rx_byte[3:0];
                        cfg_gate  <= rx_byte[4];
                        state     <= S_IDLE;
                    end

                    S_COMPUTE: begin
                        // Issue this pixel as a tap immediately
                        mac_tap_valid <= 1'b1;
                        mac_pixel     <= rx_byte;
                        mac_weight    <= w[idx];
                        idx           <= idx + 4'd1;
                        if (idx == 4'd8) begin
                            last_tap <= 1'b1;
                            state    <= S_IDLE;
                        end
                    end

                    S_ACT_CFG: begin
                        act_thresh <= rx_byte;
                        state      <= S_IDLE;
                    end

                    S_RUN_CNT: begin
                        idx <= idx + 4'd1;
                        if (idx == 4'd2) begin
                            run_left    <= {acc_buf, rx_byte};
                            run_forever <= ({acc_buf, rx_byte} == 24'd0);
                            running     <= 1'b1;
                            rng         <= ACT_SEED;
                            widx        <= '0;
                            busy        <= 1'b1;
                            state       <= S_IDLE;
                        end else begin
                            acc_buf <= {acc_buf[7:0], rx_byte};
                        end
                    end

                    S_READ: begin
                        // The byte just received was a dummy byte that clocked
                        // out one response byte; queue the next one
                        tx_next   <= resp_buf[15:8];
                        resp_buf  <= {resp_buf[7:0], 8'h00};
                        resp_left <= resp_left - 2'd1;
                        if (resp_left == 2'd1) begin
                            tx_next <= 8'h00;
                            state   <= S_IDLE;
                        end
                    end

                    default: state <= S_IDLE;
                endcase
            end

            // Activity mode: one generated tap per clock. Placed after the
            // command decoder so it takes priority over SPI taps.
            if (running) begin
                mac_tap_valid <= 1'b1;
                mac_pixel     <= act_pixel;
                mac_weight    <= w[widx];
                widx          <= (widx == 4'd8) ? 4'd0 : widx + 4'd1;
                rng           <= rng_next;
                if (!run_forever) begin
                    run_left <= run_left - 24'd1;
                    if (run_left == 24'd1) begin
                        running  <= 1'b0;
                        last_tap <= 1'b1;
                    end
                end
            end

            // DONE goes high once the last tap has reached the accumulator
            if (done_pipe[1]) busy <= 1'b0;
        end
    end

    // last_tap -> mac stage 1 -> accumulator: two cycles
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            done_pipe <= '0;
            done      <= 1'b0;
        end else begin
            done_pipe <= {done_pipe[0], last_tap};
            if ((state == S_IDLE && byte_done && rx_byte == OP_COMPUTE) || run_start)
                done <= 1'b0;
            else if (done_pipe[1])
                done <= 1'b1;
        end
    end

    assign tap = (state == S_COMPUTE) ? idx : (running ? widx : 4'd0);

    // ------------------------------------------------------------------
    // The multiply-accumulate core
    // ------------------------------------------------------------------
    mac_core #(.ACC_W(ACC_W)) u_mac (
        .clk         (clk),
        .rst_n       (rst_n),
        .load        (mac_load),
        .load_value  (mac_load_value),
        .tap_valid   (mac_tap_valid),
        .pixel       (mac_pixel),
        .weight      (mac_weight),
        .gate_en     (cfg_gate & ~bypass_s),
        .clear_skips (mac_clear_skips),
        .shift       (cfg_shift),
        .acc         (mac_acc),
        .result      (mac_result),
        .skip        (skip),
        .skip_count  (mac_skip_count)
    );

endmodule
