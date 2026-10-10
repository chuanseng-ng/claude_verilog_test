// i2c_bit_engine.sv
// Phase 6a-5 -- I2C master bit/byte/command engine, split out of i2c_controller.sv (bead
// claude_verilog_test-f7vs.9; refactor of fix_request fr_609b42790e0f_20261003_015343_00's
// four-phase fix, behaviour-preserving). i2c_controller.sv keeps everything that is bus-facing
// software: the APB register bank, the TX/RX FIFOs, the pad synchronisers, the loopback slave, the
// sticky event flags and the interrupt. THIS module is the protocol core: the command FSM, the SCL
// tick/phase generator, arbitration detection and the stuck-wait timeout. It contains no APB, no
// FIFO storage and no clock-domain crossing.
//
// Bit timing. Let N = CLKDIV_eff + 1 (clk per tick) and K = floor(N / 8). One SCL bit is FOUR timed
// phases plus the SCL-release wait, and the bus period is 4*N clk, so f_scl = f_clk / (4*N):
//     S_BIT_L1    SCL low,  SDA held after the falling edge          N       clk
//     S_BIT_L2    SCL low,  SDA at the new value (setup)             N + K   clk
//     S_BIT_WAIT  SCL released, wait for the SYNCHRONISED SCL high   3       clk  (SYNC_STAGES + 1)
//     S_BIT_HI1   SCL high, first half                               N - 3 - K  clk
//     S_BIT_HI    SCL high, second half; SDA sampled / arbitration   N       clk
//   SCL low  = L1 + L2          = 2N + K  clk      SCL high = WAIT + HI1 + HI = 2N - K  clk
//   * The release wait is not extra time on top of four ticks: the 3 clk it takes the released SCL
//     to come back through the 2-FF synchroniser (2 flops + the state register) are COUNTED INSIDE
//     the high phase, by shortening HI1 by that latency (an uncompensated fourth tick would give a
//     4N + 3 period -- 3 clk slow). HI1 >= 1 clk needs CLKDIV_eff >= SYNC_STAGES + 1, which is
//     exactly the CLKDIV_MIN elaboration guard in i2c_controller.sv.
//   * The K skew moves floor(N/8) clk from the high phase into the SCL-low phase WITHOUT changing the
//     period. A symmetric 2N / 2N split cannot meet the Fast-mode tLOW (1.3 us) at 400 kHz: two ticks
//     of 0.625 us give 1.25 us. Each phase length is checked EXHAUSTIVELY for every CLKDIV_eff
//     3..65535 at the exact maximum-rate clock of each mode (f_clk = 4*N*f_max; a slower bus at the
//     same f_clk only lengthens both phases). Standard mode (tLOW 4.7 / tHIGH 4.0 us at <= 100 kHz)
//     is met for every N. Fast mode (1.3 / 0.6 us at <= 400 kHz) is met for every N EXCEPT
//     N = 4..7 (K = 0) and N = 13..15 (K = 1): there floor(N/8) is too small and tLOW lands at
//     1.25..1.30 us -- i.e. only when f_clk is 6.4..11.2 MHz or 20.8..24 MHz AND the bus is run at
//     exactly 400 kHz. None of this SoC's clocks (40 MHz Sky130, 571 MHz ASAP7, 100 MHz test) hits
//     it; at those N run the bus a little slower. For N >= 16 the low time is >= 0.52 * T and the
//     high time >= 0.46 * T. (ceil(N/8) would shrink the failing set to N = 4 alone; it changes the
//     CLKDIV 4 low time and so needs test_i2c_clkdiv_clamp_to_min's "+2" assertion updated.)
//   KNOWN LIMITATION (bead claude_verilog_test-cd15, deferred by the user as a latent IP limit):
//     with K = floor(N / 8) the Fast-mode tLOW minimum (1.3 us) at EXACTLY 400 kHz is missed for
//     N = CLKDIV + 1 in 4..7 and 13..15, i.e. f_clk 6.4..11.2 MHz or 20.8..24 MHz. No clock in this
//     SoC is in either range (40 MHz Sky130, 571 MHz ASAP7, 1282 MHz CPU domain), so it is
//     unreachable here; it only matters if this IP is reused in a design clocked in those ranges
//     (run the bus slower there). The fix, K = ceil(N / 8), is recorded in the bead.
//   RESIDUAL ERROR (the period is exactly 4*N clk except where noted; all are clk-granular):
//   * Pad rise time. The 3 clk allowance assumes SCL, once oe_o is released, reaches the pad's logic
//     threshold less than ~1 clk later (the first synchroniser flop then catches it on the very next
//     edge). A slower rise -- a weak pull-up on a heavy bus -- is waited out, one clk at a time, and
//     LENGTHENS the period by that excess. That is clock stretching by the bus capacitance and is
//     deliberately not compensated: the master must not start its high interval before SCL IS high.
//   * Slave clock stretching adds the stretch, by definition (bounded by I2C_TIMEOUT).
//   * Loopback (CTRL.LOOPBACK) has no synchroniser (the mux sits after it, in the parent): the wait
//     is 1 clk, not 3, so the loopback period is 4*N - 2 clk. Loopback is a fabric-test aid, not a
//     rate reference.
//   * The skew uses an integer floor(N / 8): the duty cycle is a step function of N, not exact.
//   * Only the BIT clock is a spec-met quantity. Bus-free time between a STOP and the next START is
//     S_STP_FREE (one tick) plus software latency; it is MEASURED by
//     test_i2c_stop_to_start_bus_free_time_meets_spec (bead pnfw) and falls below the I2C minimum
//     (4.7 us Standard / 1.3 us Fast) at the standard divisors -- bug bead claude_verilog_test-gecv.
//
// Port contract with i2c_controller.sv (the parent). Every port is single-clock (clk), synchronous
// to the parent; there is NO clock-domain crossing in this module -- scl_s_i / sda_s_i must already
// be SYNCHRONISED (or the loopback wired-AND), which is the parent's job.
//   en_i          1 = engine enabled. 0 aborts at once: lines released, txn cleared, no event pulse.
//   div_eff_i     prescaler, ALREADY CLAMPED to CLKDIV_MIN by the parent. PRECONDITION:
//                 div_eff_i >= SYNC_STAGES + 1 (the parent's g_clkdiv_min_check + clamp guarantee
//                 it); below that the S_BIT_HI1 reload would go negative.
//   timeout_i     stuck-wait limit in ticks; 0 disables.
//   cmd_wr_i      a write ACCESS to I2C_CMD this cycle. c_*_i are the decoded CMD fields and are
//                 only meaningful while cmd_wr_i = 1. The ENGINE decides acceptance (en_i, idle,
//                 legal START / txn_active rule) and latches the command context; an illegal or
//                 busy-time command is ignored here, silently, exactly as documented in the parent.
//   addr_i        {ADDR[6:0], R/W} register value; sampled when a START command is accepted.
//   scl_s_i /     synchronised sensed line levels (1 = high).
//   sda_s_i
//   tx_empty_i /  FIFO status, in-domain flop outputs. tx_head_i is the TX FIFO head (valid when
//   rx_full_i /   !tx_empty_i). The engine only reads these in S_DATA_WAIT, where it holds SCL low.
//   tx_head_i
//   tx_pop_o      one-cycle COMBINATIONAL strobe: pop the TX FIFO this clock (byte taken into the
//                 shift register). rx_push_o: push rx_byte_o into the RX FIFO this clock. Both are
//                 forced low by an abort/timeout/arbitration-loss/EN=0 in the same cycle.
//   scl_oe_o /    REGISTERED open-drain controls, 1 = drive the line low, 0 = release. The parent
//   sda_oe_o      gates them with its loopback select before they reach the pad.
//   done_set_o /  one-cycle COMBINATIONAL event pulses (after the abort / EN=0 overrides). The
//   nack_set_o /  parent owns the sticky flops and the W1C: nothing here is sticky.
//   arb_set_o /
//   tout_set_o
//   busy_d_o /    NEXT-state mirrors for the parent's read-only STATUS writeback (so a read one
//   txn_d_o       transfer after an event cannot see stale data): busy_d_o = next state != S_IDLE,
//                 txn_d_o = next "this master holds the bus".
//
// Reset: synchronous, active-low, matching the other periph/. Single clock domain.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

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
        S_RS_HI     = 5'd4,    // T: SCL high, SDA high (setup); SDA sensed low = arbitration lost
        S_ST_LO     = 5'd5,    // T: START condition, SDA low with SCL high
        S_BIT_L1    = 5'd6,    // T: SCL low, SDA held (hold time after SCL fall)
        S_BIT_L2    = 5'd7,    // T: SCL low, SDA at the new bit value
        S_BIT_WAIT  = 5'd8,    // wait: SCL released, synchronised SCL not yet high (stretch)
        S_BIT_HI    = 5'd9,    // T: SCL high; sample SDA / arbitration check at the end
        S_DATA_WAIT = 5'd10,  // wait: SCL low until TX FIFO has a byte / RX FIFO has room
        S_STP_HOLD  = 5'd11,  // T: SCL low, SDA held
        S_STP_LO    = 5'd12,  // T: SCL low, SDA low
        S_STP_WAIT  = 5'd13,  // wait: SCL released, synchronised SCL not yet high (stretch)
        S_STP_HI    = 5'd14,  // T: SCL high, SDA low
        S_STP_FREE  = 5'd15,  // T: SDA released with SCL high = STOP; bus-free time
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
    logic [16:0] tick_q;                   // engine tick down-counter (17 b: the S_BIT_L2 reload is
                                           // CLKDIV_eff + K, which exceeds 16 b at CLKDIV = 0xFFFF)
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
    assign tick_w = (tick_q == 17'h0);

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
    // Every interval state lasts one tick (CLKDIV_eff+1 clk) except S_BIT_L2 (+K) and S_BIT_HI1
    // (-3-K), whose lengths are set by the tick reload below; the `_WAIT` states and
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

    // Tick counter: reloaded on every state change and on every tick, so each interval state lasts
    // reload+1 clk from entry. In the wait states it free-runs at one tick per CLKDIV_eff+1 clk,
    // clocking the timeout (the wait states always reload the plain CLKDIV_eff, so I2C_TIMEOUT stays
    // in whole ticks). The reload value is chosen by the state being ENTERED:
    //   S_BIT_L2  : CLKDIV_eff + K              (SCL-low phase carries the duty-cycle skew)
    //   S_BIT_HI1 : CLKDIV_eff - (SYNC_STAGES+1) - K   (the sync wait + skew come out of the high phase)
    //   otherwise : CLKDIV_eff
    // K = floor(N / 8), N = CLKDIV_eff + 1. All three are >= 0 for CLKDIV_eff >= SYNC_STAGES + 1
    // (the CLKDIV_MIN guard); 17 b arithmetic cannot overflow (max 0xFFFF + 0x2000).
    localparam int unsigned SYNC_LAT = SYNC_STAGES + 1;   // clk from SCL release to engine sees it high

    logic [16:0] div_ext_w, lo_skew_w, tick_ld_w;
    assign div_ext_w = {1'b0, div_eff_i};
    assign lo_skew_w = (div_ext_w + 17'd1) >> 3;          // K

    always_comb begin
        if      (state_d == S_BIT_L2)  tick_ld_w = div_ext_w + lo_skew_w;
        else if (state_d == S_BIT_HI1) tick_ld_w = div_ext_w - 17'(SYNC_LAT) - lo_skew_w;
        else                           tick_ld_w = div_ext_w;
    end

    always_ff @(posedge clk) begin
        if (!rst_n)                            tick_q <= 17'h0;
        else if (state_d != state_q || tick_w) tick_q <= tick_ld_w;
        else                                   tick_q <= tick_q - 17'h1;
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
