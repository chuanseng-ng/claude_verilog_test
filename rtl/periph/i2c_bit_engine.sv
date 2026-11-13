// i2c_bit_engine - I2C master bit, byte and command engine used by i2c_controller.
//
// Function: The engine is the protocol core: the command FSM, the SCL tick and phase generator, arbitration detection
//   and the stuck-wait timeout. It has no APB, no FIFO storage and no clock-domain crossing.
//   The parent i2c_controller owns the register bank, the FIFOs, the pad synchronisers, the sticky flags and the interrupt.
//   Let N = CLKDIV_eff + 1 and K = floor(N / 8). The bus period is 4*N clk, so f_scl = f_clk / (4*N).
//   SCL low lasts 2N + K clk. SCL high lasts 2N - K clk. The SCL-release wait counts inside the high phase.
//   A START or STOP condition phase lasts 2 ticks (2N clk). S_RS_HI and S_STP_HI add the 3 clk SCL-release latency.
//   The bus-free time tBUF lasts 3 ticks (3N clk). It applies only after this master's own STOP.
//   The bus-free interval S_STP_FREE is inside STATUS.busy. DONE of a STOP command is raised at its end.
// Parameters: SYNC_STAGES (pad-synchroniser depth that the parent uses, default 2).
// Ports (all synchronous to clk):
//   en_i = 0 aborts at once: lines released, transaction cleared, no event pulse.
//   div_eff_i is the prescaler, already clamped to CLKDIV_MIN by the parent. It must be at least SYNC_STAGES + 1.
//   timeout_i is the stuck-wait limit in ticks. 0 disables it.
//   cmd_wr_i marks a write to I2C_CMD. The c_*_i fields are valid only while cmd_wr_i = 1. The engine decides acceptance.
//   scl_s_i and sda_s_i are the synchronised sensed line levels. addr_i is sampled when a START command is accepted.
//   tx_empty_i, rx_full_i and tx_head_i are FIFO status. The engine reads them only in S_DATA_WAIT, where it holds SCL low.
//   tx_pop_o and rx_push_o are one-cycle combinational strobes. Both are low on abort, timeout, arbitration loss or en_i = 0.
//   scl_oe_o and sda_oe_o are registered open-drain controls: 1 drives the line low, 0 releases it.
//   done_set_o, nack_set_o, arb_set_o and tout_set_o are one-cycle combinational pulses. Nothing here is sticky.
//   busy_d_o and txn_d_o are next-state mirrors for the parent's STATUS writeback.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous.
// Caller rules:
//   - Synchronise scl_s_i and sda_s_i in the parent, or drive the loopback wired-AND. The engine has no synchroniser.
//   - Clamp div_eff_i in the parent. A value below SYNC_STAGES + 1 makes the S_BIT_HI1 reload negative.
//   - The parent owns the sticky flops and the W1C. The engine ignores an illegal or busy-time command silently.
//   - Fast-mode tLOW at exactly 400 kHz is missed for N in 4..7 and 13..15. Run the bus slower there.
//   - A slow pad rise or a slave clock stretch lengthens the period. Loopback has a 1 clk wait: its period is 4*N - 2 clk.
// Doc: ds:mod:i2c-bit-engine, tm:mod:i2c-bit-engine, cr:mod:i2c-bit-engine

module i2c_bit_engine
#(
    parameter int unsigned SYNC_STAGES = 2    // pad-synchroniser depth the parent uses (see header)
) (
    input  logic        clk,
    input  logic        rst_n,

    // Control
    input  logic        en_i,
    input  logic [15:0] div_eff_i,
    input  logic [15:0] timeout_i,

    // Command (decoded by the parent from the APB write to I2C_CMD)
    input  logic        cmd_wr_i,
    input  logic        c_start_i,
    input  logic        c_write_i,
    input  logic        c_read_i,
    input  logic        c_stop_i,
    input  logic        c_nack_last_i,
    input  logic [7:0]  c_count_i,
    input  logic [7:0]  addr_i,

    // Synchronised sensed lines
    input  logic        scl_s_i,
    input  logic        sda_s_i,

    // FIFO side
    input  logic        tx_empty_i,
    input  logic        rx_full_i,
    input  logic [7:0]  tx_head_i,
    output logic        tx_pop_o,
    output logic        rx_push_o,
    output logic [7:0]  rx_byte_o,

    // Open-drain controls (registered)
    output logic        scl_oe_o,
    output logic        sda_oe_o,

    // Event pulses (combinational, one clock)
    output logic        done_set_o,
    output logic        nack_set_o,
    output logic        arb_set_o,
    output logic        tout_set_o,

    // Next-state mirrors for the parent's STATUS writeback
    output logic        busy_d_o,
    output logic        txn_d_o
);

    // =========================================================================
    // Engine state
    // =========================================================================
    typedef enum logic [4:0] {
        S_IDLE      = 5'd0,    // lines released, or SCL held low while txn_active
        S_BUSWAIT   = 5'd1,    // wait: both synchronised lines high before START
        S_RS_REL    = 5'd2,    // T: repeated START, SCL low, SDA released
        S_RS_WAIT   = 5'd3,    // wait: SCL released, synchronised SCL not yet high (stretch)
        S_RS_HI     = 5'd4,    // T: SCL high, SDA high (setup, tSU;STA = 2 ticks); SDA sensed low =
                               //    arbitration lost
        S_ST_LO     = 5'd5,    // T: START condition, SDA low with SCL high (tHD;STA = 2 ticks)
        S_BIT_L1    = 5'd6,    // T: SCL low, SDA held (hold time after SCL fall)
        S_BIT_L2    = 5'd7,    // T: SCL low, SDA at the new bit value
        S_BIT_WAIT  = 5'd8,    // wait: SCL released, synchronised SCL not yet high (stretch)
        S_BIT_HI    = 5'd9,    // T: SCL high; sample SDA / arbitration check at the end
        S_DATA_WAIT = 5'd10,  // wait: SCL low until TX FIFO has a byte / RX FIFO has room
        S_STP_HOLD  = 5'd11,  // T: SCL low, SDA held
        S_STP_LO    = 5'd12,  // T: SCL low, SDA low
        S_STP_WAIT  = 5'd13,  // wait: SCL released, synchronised SCL not yet high (stretch)
        S_STP_HI    = 5'd14,  // T: SCL high, SDA low (tSU;STO = 2 ticks)
        S_STP_FREE  = 5'd15,  // T: SDA released with SCL high = STOP; bus-free time tBUF (3 ticks)
        S_BIT_HI1   = 5'd16   // T: SCL high, first half, shortened by the sync latency (appended so
                              //    the 16 original encodings above are unchanged)
    } state_e;

    // FSM case policy (stated per FSM, skill rtl_coding rule 7): plain `case` with a `default` arm
    // that releases both lines and returns to S_IDLE. 17 of the 32 encodings are named; the other
    // 15 are reachable only by an upset / X, which is exactly what `default` recovers from.
    state_e      state_q, state_d;
    logic        scl_oe_q, scl_oe_d;       // 1 = SCL driven low
    logic        sda_oe_q, sda_oe_d;       // 1 = SDA driven low
    logic [7:0]  shreg_q, shreg_d;         // tx: MSB-first out; rx: shifted in
    logic [3:0]  bitcnt_q, bitcnt_d;       // 0..7 data bits, 8 = ACK slot
    logic [7:0]  cnt_q, cnt_d;             // data bytes remaining in this command (incl. current)
    logic        ph_data_q, ph_data_d;     // 0 = address byte, 1 = data byte
    logic        txn_q, txn_d;             // this master holds the bus (START sent, no STOP yet)
    logic [17:0] tick_q;                   // engine tick down-counter (18 b: the S_STP_FREE reload is
                                           // 3*CLKDIV_eff + 2 = 0x2FFFF at CLKDIV = 0xFFFF; the 2-tick
                                           // condition reload is 0x1FFFF, S_BIT_L2's is CLKDIV_eff + K)
    logic [15:0] to_q;                     // stuck-wait counter, in ticks

    // Latched command context (loaded on accept)
    logic        stop_q, nack_last_q, do_data_q, rd_cmd_q;

    // =========================================================================
    // Command accept
    // =========================================================================
    logic busy_q_w;
    assign busy_q_w = (state_q != S_IDLE);

    logic c_any_op_w, c_legal_w, cmd_accept_w;
    assign c_any_op_w   = c_start_i | c_write_i | c_read_i | c_stop_i;
    assign c_legal_w    = c_start_i | txn_q;   // non-START commands need the bus held
    assign cmd_accept_w = cmd_wr_i & c_any_op_w & c_legal_w & en_i & ~busy_q_w;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            stop_q      <= 1'b0;
            nack_last_q <= 1'b0;
            do_data_q   <= 1'b0;
            rd_cmd_q    <= 1'b0;
        end else if (cmd_accept_w) begin
            stop_q      <= c_stop_i;
            nack_last_q <= c_nack_last_i;
            do_data_q   <= c_write_i | c_read_i;
            rd_cmd_q    <= c_read_i & ~c_write_i;   // WRITE wins if both are set
        end
    end

    // =========================================================================
    // Bit-level helpers
    // =========================================================================
    logic tick_w;
    assign tick_w = (tick_q == 18'h0);

    logic rd_byte_w;                       // current byte is received (read data phase)
    assign rd_byte_w = ph_data_q & rd_cmd_q;

    logic ack_n_w;                         // read ACK slot: 1 = NACK (only the last byte, on request)
    assign ack_n_w = nack_last_q & (cnt_q == 8'd1);

    // SDA drive value for the current bit, 1 = release. Applied at S_BIT_L1 -> S_BIT_L2.
    logic bit_drv_w;
    always_comb begin
        if (bitcnt_q != 4'd8) bit_drv_w = rd_byte_w ? 1'b1 : shreg_q[7];
        else                  bit_drv_w = rd_byte_w ? ack_n_w : 1'b1;
    end

    // Arbitration is checked where this master alone is meant to control SDA: transmitted data and
    // address bits, and the ACK slot of a read. Not on received bits, nor on a write's ACK slot.
    logic chk_arb_w;
    assign chk_arb_w = ((bitcnt_q != 4'd8) & ~rd_byte_w) | ((bitcnt_q == 4'd8) & rd_byte_w);

    // Waits in which the stuck-wait (timeout) counter runs.
    logic in_wait_w;
    assign in_wait_w = (state_q == S_BUSWAIT) | (state_q == S_RS_WAIT) | (state_q == S_BIT_WAIT) |
                       (state_q == S_DATA_WAIT) | (state_q == S_STP_WAIT);

    logic tout_hit_w;
    assign tout_hit_w = in_wait_w & (timeout_i != 16'h0) & (to_q >= timeout_i);

    // =========================================================================
    // Engine FSM -- next-state logic. Outputs are registered by the always_ff below.
    // Every interval state lasts one tick (CLKDIV_eff+1 clk) except S_BIT_L2 (+K), S_BIT_HI1 (-3-K),
    // S_ST_LO / S_RS_HI / S_STP_HI (2 ticks) and S_STP_FREE (3 ticks), whose lengths are set by the
    // tick reload below; the `_WAIT` states and
    // S_BUSWAIT/S_DATA_WAIT instead leave on their condition and are bounded by the timeout.
    // =========================================================================
    logic fin_w;                           // command finished its bytes (ACK or NACK path)

    always_comb begin
        state_d   = state_q;
        scl_oe_d  = scl_oe_q;
        sda_oe_d  = sda_oe_q;
        shreg_d   = shreg_q;
        bitcnt_d  = bitcnt_q;
        cnt_d     = cnt_q;
        ph_data_d = ph_data_q;
        txn_d     = txn_q;

        tx_pop_o    = 1'b0;
        rx_push_o   = 1'b0;
        done_set_o  = 1'b0;
        nack_set_o  = 1'b0;
        arb_set_o   = 1'b0;
        fin_w       = 1'b0;

        case (state_q)
            S_IDLE: begin
                if (cmd_accept_w) begin
                    cnt_d = (c_count_i == 8'h0) ? 8'd1 : c_count_i;
                    if (c_start_i) begin
                        shreg_d   = {addr_i[6:0], addr_i[7]};
                        bitcnt_d  = 4'd0;
                        ph_data_d = 1'b0;
                        if (txn_q) begin
                            // Repeated START: SCL is held low; release SDA first.
                            sda_oe_d = 1'b0;
                            state_d  = S_RS_REL;
                        end else begin
                            state_d  = S_BUSWAIT;
                        end
                    end else if (c_write_i | c_read_i) begin
                        ph_data_d = 1'b1;
                        state_d   = S_DATA_WAIT;
                    end else begin
                        state_d   = S_STP_HOLD;
                    end
                end
            end

            S_BUSWAIT: begin
                // Bus free (both synchronised lines high) -> START: SDA falls while SCL is high.
                if (scl_s_i && sda_s_i) begin
                    sda_oe_d = 1'b1;
                    state_d  = S_ST_LO;
                end
            end

            S_RS_REL: begin
                if (tick_w) begin
                    scl_oe_d = 1'b0;
                    state_d  = S_RS_WAIT;
                end
            end

            S_RS_WAIT: begin
                // Clock stretching: do not proceed until the synchronised SCL reads high.
                if (scl_s_i) state_d = S_RS_HI;
            end

            S_RS_HI: begin
                if (tick_w) begin
                    if (!sda_s_i) begin
                        arb_set_o = 1'b1;       // SDA held low by someone else: arbitration lost
                    end else begin
                        sda_oe_d = 1'b1;
                        state_d  = S_ST_LO;
                    end
                end
            end

            S_ST_LO: begin
                if (tick_w) begin
                    scl_oe_d = 1'b1;
                    txn_d    = 1'b1;
                    state_d  = S_BIT_L1;
                end
            end

            S_BIT_L1: begin
                if (tick_w) begin
                    sda_oe_d = ~bit_drv_w;
                    state_d  = S_BIT_L2;
                end
            end

            S_BIT_L2: begin
                if (tick_w) begin
                    scl_oe_d = 1'b0;
                    state_d  = S_BIT_WAIT;
                end
            end

            S_BIT_WAIT: begin
                // Clock stretching: SCL-high interval starts only when SCL actually reads high.
                if (scl_s_i) state_d = S_BIT_HI1;
            end

            S_BIT_HI1: begin
                // First half of the SCL-high interval; its length already has the synchroniser
                // latency taken out (see tick reload), so L1 + L2 + WAIT + HI1 + HI = 4 ticks.
                if (tick_w) state_d = S_BIT_HI;
            end

            S_BIT_HI: begin
                if (tick_w) begin
                    scl_oe_d = 1'b1;
                    if (chk_arb_w && bit_drv_w && !sda_s_i) begin
                        arb_set_o = 1'b1;       // released SDA to send a 1 but it reads 0
                    end else if (bitcnt_q != 4'd8) begin
                        shreg_d  = rd_byte_w ? {shreg_q[6:0], sda_s_i} : {shreg_q[6:0], 1'b0};
                        bitcnt_d = bitcnt_q + 4'd1;
                        state_d  = S_BIT_L1;
                    end else begin
                        // ACK slot complete: a byte is done.
                        bitcnt_d = 4'd0;
                        if (!ph_data_q) begin
                            if (!sda_s_i && do_data_q) begin
                                ph_data_d = 1'b1;
                                state_d   = S_DATA_WAIT;
                            end else begin
                                fin_w      = 1'b1;
                                nack_set_o = sda_s_i;   // address byte: tx, SDA high = NACK
                            end
                        end else begin
                            cnt_d = cnt_q - 8'd1;
                            if (rd_byte_w) rx_push_o = 1'b1;   // pushes shreg_q
                            if (!rd_byte_w && sda_s_i) begin
                                fin_w      = 1'b1;          // NACK on write data: abandon the rest
                                nack_set_o = 1'b1;
                            end else if (cnt_q > 8'd1) begin
                                state_d    = S_DATA_WAIT;
                            end else begin
                                fin_w      = 1'b1;
                            end
                        end
                        if (fin_w) begin
                            if (stop_q) begin
                                state_d    = S_STP_HOLD;
                            end else begin
                                done_set_o = 1'b1;          // bus held (txn_active stays 1)
                                state_d    = S_IDLE;
                            end
                        end
                    end
                end
            end

            S_DATA_WAIT: begin
                // SCL is low: a master may legally pause here. Bounded by the timeout.
                if (rd_cmd_q) begin
                    if (!rx_full_i) begin
                        shreg_d  = 8'h00;
                        bitcnt_d = 4'd0;
                        state_d  = S_BIT_L1;
                    end
                end else begin
                    if (!tx_empty_i) begin
                        shreg_d  = tx_head_i;
                        tx_pop_o = 1'b1;
                        bitcnt_d = 4'd0;
                        state_d  = S_BIT_L1;
                    end
                end
            end

            S_STP_HOLD: begin
                if (tick_w) begin
                    sda_oe_d = 1'b1;
                    state_d  = S_STP_LO;
                end
            end

            S_STP_LO: begin
                if (tick_w) begin
                    scl_oe_d = 1'b0;
                    state_d  = S_STP_WAIT;
                end
            end

            S_STP_WAIT: begin
                if (scl_s_i) state_d = S_STP_HI;
            end

            S_STP_HI: begin
                if (tick_w) begin
                    sda_oe_d = 1'b0;            // SDA rises while SCL is high: STOP
                    state_d  = S_STP_FREE;
                end
            end

            S_STP_FREE: begin
                if (tick_w) begin
                    txn_d      = 1'b0;
                    done_set_o = 1'b1;
                    state_d    = S_IDLE;
                end
            end

            default: begin
                scl_oe_d = 1'b0;
                sda_oe_d = 1'b0;
                txn_d    = 1'b0;
                state_d  = S_IDLE;
            end
        endcase

        // Overrides, highest priority last. tout_set_o and arb_set_o release the bus and drop the
        // command; neither sets `done`. EN = 0 aborts silently and cancels every side effect.
        tout_set_o = tout_hit_w;
        if (tout_set_o || arb_set_o) begin
            scl_oe_d   = 1'b0;
            sda_oe_d   = 1'b0;
            txn_d      = 1'b0;
            state_d    = S_IDLE;
            done_set_o = 1'b0;
            nack_set_o = 1'b0;
            tx_pop_o   = 1'b0;
            rx_push_o  = 1'b0;
        end
        if (!en_i) begin
            scl_oe_d   = 1'b0;
            sda_oe_d   = 1'b0;
            txn_d      = 1'b0;
            state_d    = S_IDLE;
            done_set_o = 1'b0;
            nack_set_o = 1'b0;
            arb_set_o  = 1'b0;
            tout_set_o = 1'b0;
            tx_pop_o   = 1'b0;
            rx_push_o  = 1'b0;
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q   <= S_IDLE;
            scl_oe_q  <= 1'b0;
            sda_oe_q  <= 1'b0;
            shreg_q   <= 8'h00;
            bitcnt_q  <= 4'd0;
            cnt_q     <= 8'd0;
            ph_data_q <= 1'b0;
            txn_q     <= 1'b0;
        end else begin
            state_q   <= state_d;
            scl_oe_q  <= scl_oe_d;
            sda_oe_q  <= sda_oe_d;
            shreg_q   <= shreg_d;
            bitcnt_q  <= bitcnt_d;
            cnt_q     <= cnt_d;
            ph_data_q <= ph_data_d;
            txn_q     <= txn_d;
        end
    end

    // Tick counter: reloaded on every state change and on every tick. The reload value depends on the state being ENTERED.
    // S_BIT_L2: CLKDIV_eff + K. S_BIT_HI1: CLKDIV_eff - (SYNC_STAGES+1) - K. S_ST_LO, S_RS_HI, S_STP_HI: 2*N - 1.
    // S_STP_FREE: 3*N - 1. Otherwise CLKDIV_eff. K = floor(N / 8) and N = CLKDIV_eff + 1.
    localparam int unsigned SYNC_LAT   = SYNC_STAGES + 1;   // clk from SCL release to engine sees it high
    localparam int unsigned TICKS_COND = 2;   // tHD;STA, tSU;STA, tSU;STO -- see the header table
    localparam int unsigned TICKS_FREE = 3;   // tBUF

    logic [17:0] div_ext_w, lo_skew_w, tick_ld_w;
    assign div_ext_w = {2'b00, div_eff_i};
    assign lo_skew_w = (div_ext_w + 18'd1) >> 3;          // K

    always_comb begin
        if      (state_d == S_BIT_L2)  tick_ld_w = div_ext_w + lo_skew_w;
        else if (state_d == S_BIT_HI1) tick_ld_w = div_ext_w - 18'(SYNC_LAT) - lo_skew_w;
        else if ((state_d == S_ST_LO) || (state_d == S_RS_HI) || (state_d == S_STP_HI))
                                       tick_ld_w = div_ext_w * 18'(TICKS_COND) + 18'(TICKS_COND - 1);
        else if (state_d == S_STP_FREE) tick_ld_w = div_ext_w * 18'(TICKS_FREE) + 18'(TICKS_FREE - 1);
        else                           tick_ld_w = div_ext_w;
    end

    always_ff @(posedge clk) begin
        if (!rst_n)                            tick_q <= 18'h0;
        else if (state_d != state_q || tick_w) tick_q <= tick_ld_w;
        else                                   tick_q <= tick_q - 18'h1;
    end

    // Stuck-wait counter, in ticks. Cleared on any state change; runs only inside a wait state.
    always_ff @(posedge clk) begin
        if (!rst_n || state_d != state_q)                  to_q <= 16'h0;
        else if (in_wait_w && tick_w && to_q != 16'hFFFF)  to_q <= to_q + 16'h1;
    end

    // =========================================================================
    // Port assignments
    // =========================================================================
    assign rx_byte_o = shreg_q;
    assign scl_oe_o  = scl_oe_q;
    assign sda_oe_o  = sda_oe_q;
    assign busy_d_o  = (state_d != S_IDLE);
    assign txn_d_o   = txn_d;

endmodule : i2c_bit_engine
