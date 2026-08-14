// uart_controller.sv
// Phase 5 (M4) — UART peripheral, 8N1, APB4 slave.
// APB migration PR-2: converted from AXI4-Lite slave to APB4 slave.
//
// Register map (word indices into apb4_register_bank):
//   0  UART_TX     WO [7:0]  write pushes byte to TX FIFO (via APB access snoop)
//   1  UART_RX     RO [7:0]  RX FIFO head; read pops via snoop
//   2  UART_STATUS RO        [0]=tx_busy [1]=tx_full [2]=tx_empty
//                            [3]=rx_empty [4]=rx_full [5]=rx_valid(!rx_empty)
//                            [6]=framing_error (sticky; read-to-clear on UART_RX read)
//   3  UART_CTRL   RW [4:0]  [0]=tx_en [1]=rx_en [2]=irq_tx_empty_en
//                            [3]=irq_rx_valid_en [4]=loopback
//   4  UART_BAUD   RW [15:0] oversample-period divisor D:
//                            1 oversample tick = (D+1) clocks;
//                            1 serial bit      = 16 oversample ticks = 16*(D+1) clocks.
//                            TX and RX share this generator so loopback stays aligned.
//
// TX engine: IDLE → START(0) → DATA[0..7] LSB-first → STOP(1) → IDLE
//            advances one state per bit_tick (= 16 oversample ticks).
// RX engine (A4 — 16x oversample):
//   2-FF synchroniser on uart_rx_i (loopback bypasses it).
//   START detect: synchronised line low at any os_tick → align os_phase to 0.
//   Bits sampled at os_phase==8 (mid-bit); majority-vote of phases 7, 8, 9.
//   STOP bit sampled at mid-bit; if not 1 → framing_error sticky set (A3).
//   Byte is always pushed regardless of framing error (flag-only, no drop).
// Loopback: RX receives internal tx_serial (same clock domain); shared os_tick
//           generator keeps TX and RX exactly bit-aligned.
//
// IRQ: irq_o = (irq_tx_empty_en & tx_empty & tx_was_nonempty_q)  [A2]
//            | (irq_rx_valid_en & rx_valid)
//      tx-empty term gated by tx_was_nonempty_q to suppress false IRQ at reset.
//
// APB snoop (replaces AXI snoop):
//   TX push: psel & penable & pwrite  & pready at UART_TX word address.
//   RX pop:  psel & penable & !pwrite & pready at UART_RX word address.
//   APB transfers are single-beat and the access phase completes in one cycle
//   when pready=1, so the pulse is exactly one cycle — cleaner than the
//   two-channel AXI-Lite snoop.  No capture registers needed.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module uart_controller #(
    parameter int unsigned ADDR_W = 12   // APB4 local address width
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // APB4 slave — control/status registers
    // pclk / presetn are mapped to clk / rst_n above.
    // =========================================================================
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] paddr,   // byte address; [1:0] unused (word-aligned)
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // =========================================================================
    // UART I/O
    // =========================================================================
    output logic uart_tx_o,
    input  logic uart_rx_i,

    // =========================================================================
    // Interrupt output
    // =========================================================================
    output logic irq_o
);

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_UART_TX     = 0;
    localparam int unsigned REG_UART_RX     = 1;
    localparam int unsigned REG_UART_STATUS = 2;
    localparam int unsigned REG_UART_CTRL   = 3;
    localparam int unsigned REG_UART_BAUD   = 4;
    localparam int unsigned N_REGS          = 5;

    // CTRL bit positions
    localparam int unsigned CTRL_TX_EN_BIT         = 0;
    localparam int unsigned CTRL_RX_EN_BIT         = 1;
    localparam int unsigned CTRL_IRQ_TX_EMPTY_BIT  = 2;
    localparam int unsigned CTRL_IRQ_RX_VALID_BIT  = 3;
    localparam int unsigned CTRL_LOOPBACK_BIT      = 4;

    // Word address width (ADDR_W - 2 because word = 4 bytes)
    localparam int unsigned WORDW = ADDR_W - 2;

    // FIFO parameters
    localparam int unsigned FIFO_DEPTH    = 4;
    localparam int unsigned FIFO_DEPTH_LG = 2;  // log2(4)
    localparam int unsigned PTR_W         = FIFO_DEPTH_LG + 1;  // 3 bits

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 UART_TX     WO  (captured via snoop)
        32'h0000_0000,  // 1 UART_RX     RO  (HW-written: RX FIFO head)
        32'h0000_0000,  // 2 UART_STATUS RO  (HW-written: FIFO flags)
        32'h0000_0000,  // 3 UART_CTRL   RW  (all disabled at reset)
        32'h0000_0000   // 4 UART_BAUD   RW  (D=0 → 1 clock/bit at reset)
    };

    // WMASK: TX/RX/STATUS are RO (0x0); CTRL is [4:0]; BAUD is [15:0]
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0000,  // 0 UART_TX     WO (not stored; snoop captures)
        32'h0000_0000,  // 1 UART_RX     RO
        32'h0000_0000,  // 2 UART_STATUS RO
        32'h0000_001F,  // 3 UART_CTRL   RW [4:0]
        32'h0000_FFFF   // 4 UART_BAUD   RW [15:0]
    };

    logic [31:0] regs_o    [N_REGS];
    logic        hw_wen_i  [N_REGS];
    logic [31:0] hw_wdata_i[N_REGS];

    apb4_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .pclk       (clk),
        .presetn    (rst_n),
        .psel       (psel),
        .penable    (penable),
        .pwrite     (pwrite),
        .paddr      (paddr),
        .pwdata     (pwdata),
        .pstrb      (pstrb),
        .prdata     (prdata),
        .pready     (pready),
        .pslverr    (pslverr),
        .regs_o     (regs_o),
        .hw_wen_i   (hw_wen_i),
        .hw_wdata_i (hw_wdata_i)
    );

    // =========================================================================
    // Control register aliases
    // =========================================================================
    logic tx_en, rx_en, irq_tx_empty_en, irq_rx_valid_en, loopback;

    assign tx_en           = regs_o[REG_UART_CTRL][CTRL_TX_EN_BIT];
    assign rx_en           = regs_o[REG_UART_CTRL][CTRL_RX_EN_BIT];
    assign irq_tx_empty_en = regs_o[REG_UART_CTRL][CTRL_IRQ_TX_EMPTY_BIT];
    assign irq_rx_valid_en = regs_o[REG_UART_CTRL][CTRL_IRQ_RX_VALID_BIT];
    assign loopback        = regs_o[REG_UART_CTRL][CTRL_LOOPBACK_BIT];

    // =========================================================================
    // APB access-phase snoop — detect UART_TX write and UART_RX read commits.
    //
    // APB4 access phase completes when psel & penable & pready are all 1.
    // pready is driven 1'b1 combinatorially by apb4_register_bank (zero wait
    // states), so the access phase is always exactly one cycle wide.  No capture
    // registers are needed — the word address, pwrite, and pstrb are all stable
    // during the setup and access phases by APB4 protocol.
    //
    // Word address from the byte address:
    //   addr_word = paddr[ADDR_W-1:2]
    //
    // TX push: APB write ACCESS to UART_TX with >=1 strobe asserted.
    //   A zero-strobe write (pstrb==4'h0) is a legal APB no-op and must not push.
    //
    // RX pop:  APB read ACCESS completing at UART_RX word address.
    //   APB is single-transfer; the access pulse is one cycle → no double-pop risk.
    // =========================================================================
    logic [WORDW-1:0] apb_word_addr;
    assign apb_word_addr = paddr[ADDR_W-1:2];

    // Access-phase commit pulse: psel & penable & pready (pready=1 always here)
    wire apb_access = psel & penable;   // pready=1 always from the register bank

    // A1: PSTRB byte-lane priority mux.
    // Select the byte from pwdata corresponding to the lowest active strobe lane,
    // matching the AXI-Lite snoop behaviour so TX byte extraction is equivalent.
    // When pstrb==4'h0 the value is don't-care: tx_push is gated out.
    logic [7:0] pstrb_sel_byte;
    always_comb begin
        unique casez (pstrb)
            4'b???1: pstrb_sel_byte = pwdata[ 7: 0];
            4'b??10: pstrb_sel_byte = pwdata[15: 8];
            4'b?100: pstrb_sel_byte = pwdata[23:16];
            4'b1000: pstrb_sel_byte = pwdata[31:24];
            default: pstrb_sel_byte = pwdata[ 7: 0];  // pstrb==0: don't-care
        endcase
    end

    // TX FIFO push: APB write ACCESS to UART_TX with at least one strobe set.
    wire tx_push = apb_access && pwrite &&
                   (apb_word_addr == WORDW'(REG_UART_TX)) &&
                   (|pstrb);

    // RX FIFO pop: APB read ACCESS completing at UART_RX word address.
    wire rx_pop  = apb_access && !pwrite &&
                   (apb_word_addr == WORDW'(REG_UART_RX));

    // =========================================================================
    // TX FIFO (depth=4, 8-bit wide, synchronous)
    // Pointer scheme: PTR_W=3; bit[2] is the wrap bit; bits[1:0] are the index.
    // empty = (wptr == rptr); full = (wptr[2] != rptr[2]) && (wptr[1:0] == rptr[1:0])
    // =========================================================================
    logic [7:0]       tx_fifo_q  [FIFO_DEPTH];
    logic [PTR_W-1:0] tx_wptr_q, tx_rptr_q;

    wire tx_empty = (tx_wptr_q == tx_rptr_q);
    wire tx_full  = (tx_wptr_q[PTR_W-1] != tx_rptr_q[PTR_W-1]) &&
                    (tx_wptr_q[PTR_W-2:0] == tx_rptr_q[PTR_W-2:0]);
    wire [7:0] tx_head = tx_fifo_q[tx_rptr_q[FIFO_DEPTH_LG-1:0]];

    // TX FIFO pop signal: asserted by TX FSM at load transition
    logic tx_pop;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tx_wptr_q <= '0;
            tx_rptr_q <= '0;
            for (int unsigned i = 0; i < FIFO_DEPTH; i++)
                tx_fifo_q[i] <= 8'h0;
        end else begin
            if (tx_push && !tx_full) begin
                tx_fifo_q[tx_wptr_q[FIFO_DEPTH_LG-1:0]] <= pstrb_sel_byte;
                tx_wptr_q <= tx_wptr_q + PTR_W'(1);
            end
            if (tx_pop && !tx_empty)
                tx_rptr_q <= tx_rptr_q + PTR_W'(1);
        end
    end

    // =========================================================================
    // RX FIFO (depth=4, 8-bit wide, synchronous)
    // =========================================================================
    logic [7:0]       rx_fifo_q  [FIFO_DEPTH];
    logic [PTR_W-1:0] rx_wptr_q, rx_rptr_q;

    wire rx_empty = (rx_wptr_q == rx_rptr_q);
    wire rx_full  = (rx_wptr_q[PTR_W-1] != rx_rptr_q[PTR_W-1]) &&
                    (rx_wptr_q[PTR_W-2:0] == rx_rptr_q[PTR_W-2:0]);
    wire rx_valid = !rx_empty;
    wire [7:0] rx_head = rx_fifo_q[rx_rptr_q[FIFO_DEPTH_LG-1:0]];

    // RX FIFO push signal: asserted by RX engine on byte completion
    logic       rx_push;
    logic [7:0] rx_push_data;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rx_wptr_q <= '0;
            rx_rptr_q <= '0;
            for (int unsigned i = 0; i < FIFO_DEPTH; i++)
                rx_fifo_q[i] <= 8'h0;
        end else begin
            if (rx_push && !rx_full) begin
                rx_fifo_q[rx_wptr_q[FIFO_DEPTH_LG-1:0]] <= rx_push_data;
                rx_wptr_q <= rx_wptr_q + PTR_W'(1);
            end
            if (rx_pop && !rx_empty)
                rx_rptr_q <= rx_rptr_q + PTR_W'(1);
        end
    end

    // =========================================================================
    // A4 — 16x oversample tick generator (shared by TX and RX engines)
    //
    // UART_BAUD register (D = regs_o[REG_UART_BAUD][15:0]) sets the oversample
    // period: 1 os_tick = (D+1) system clocks.
    // 1 serial bit = 16 os_ticks = 16*(D+1) system clocks.
    // When D=0 → os_tick every clock; bit period = 16 clocks.
    //
    // os_phase counts 0..15; wraps every 16 os_ticks → one bit_tick per wrap.
    // TX FSM uses bit_tick; RX FSM uses os_tick + os_phase for mid-bit sampling.
    // TX and RX share this generator so loopback stays exactly bit-aligned.
    // =========================================================================
    logic [15:0] baud_cnt_q;   // oversample period down-counter
    logic        os_tick;      // one pulse per oversample period (every D+1 clks)
    logic [3:0]  os_phase_q;   // oversample phase 0..15 within one bit period
    logic        bit_tick;     // one pulse per bit period (every 16 os_ticks)

    assign os_tick  = (baud_cnt_q == 16'h0);
    assign bit_tick = os_tick && (os_phase_q == 4'd15);

    // rx_align_phase: asserted by RX FSM on START detection to reset os_phase
    // to 0 so that mid-bit sampling falls at phase 8 of each subsequent bit.
    // Declared here; driven combinationally below after RX FSM declaration.
    logic rx_align_phase;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            baud_cnt_q <= 16'h0;
            os_phase_q <= 4'h0;
        end else begin
            if (rx_align_phase) begin
                // Align: reset phase to 0 so next bit samples at phase 8.
                // Also reload the period counter.
                baud_cnt_q <= regs_o[REG_UART_BAUD][15:0];
                os_phase_q <= 4'h0;
            end else if (os_tick) begin
                baud_cnt_q <= regs_o[REG_UART_BAUD][15:0];
                os_phase_q <= os_phase_q + 4'h1;  // wraps 15→0 naturally
            end else begin
                baud_cnt_q <= baud_cnt_q - 16'h1;
            end
        end
    end

    // =========================================================================
    // TX engine FSM — 8N1 serial transmitter
    // States: TX_IDLE → TX_START → TX_DATA[0..7] → TX_STOP → TX_IDLE
    // uart_tx_o is 1 (idle high) at all times except START (forced 0).
    // =========================================================================
    typedef enum logic [1:0] {
        TX_IDLE  = 2'd0,
        TX_START = 2'd1,
        TX_DATA  = 2'd2,
        TX_STOP  = 2'd3
    } tx_state_e;

    tx_state_e   tx_state_q;
    logic [7:0]  tx_shift_q;  // shift register: LSB first
    logic [2:0]  tx_bit_q;    // bit counter 0..7
    logic        tx_serial;   // combinational serial output

    // tx_pop: pop TX FIFO at the IDLE→LOAD transition (A4: uses bit_tick)
    always_comb begin
        tx_pop   = 1'b0;
        tx_serial = 1'b1;  // idle high
        unique case (tx_state_q)
            TX_IDLE: begin
                tx_serial = 1'b1;
                tx_pop    = tx_en && !tx_empty && bit_tick;
            end
            TX_START: tx_serial = 1'b0;
            TX_DATA:  tx_serial = tx_shift_q[0];
            TX_STOP:  tx_serial = 1'b1;
            default: begin
                tx_serial = 1'b1;
                tx_pop    = 1'b0;
            end
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tx_state_q <= TX_IDLE;
            tx_shift_q <= 8'h0;
            tx_bit_q   <= 3'h0;
        end else begin
            unique case (tx_state_q)
                TX_IDLE: begin
                    // A4: TX advances on bit_tick (= every 16 oversample ticks)
                    if (tx_en && !tx_empty && bit_tick) begin
                        tx_shift_q <= tx_head;
                        tx_state_q <= TX_START;
                    end
                end
                TX_START: begin
                    if (bit_tick) begin
                        tx_bit_q   <= 3'h0;
                        tx_state_q <= TX_DATA;
                    end
                end
                TX_DATA: begin
                    if (bit_tick) begin
                        tx_shift_q <= {1'b0, tx_shift_q[7:1]};
                        if (tx_bit_q == 3'd7) begin
                            tx_state_q <= TX_STOP;
                        end else begin
                            tx_bit_q <= tx_bit_q + 3'h1;
                        end
                    end
                end
                TX_STOP: begin
                    if (bit_tick)
                        tx_state_q <= TX_IDLE;
                end
                default: tx_state_q <= TX_IDLE;
            endcase
        end
    end

    assign uart_tx_o = tx_serial;

    // =========================================================================
    // A4 — RX engine (16x oversample, 8N1 serial receiver)
    //
    // Receives from uart_rx_i (through 2-FF synchroniser) or from internal
    // tx_serial when loopback is enabled (same clock domain — no synchroniser
    // needed).
    //
    // Alignment on START detect:
    //   In IDLE, any os_tick on which the synchronised line is low is treated as
    //   the start of the START bit.  os_phase is reset to 0 at that moment.
    //   This means mid-bit sampling occurs at os_phase==8 regardless of when
    //   within the bit period the edge was detected — worst-case 0.5-bit-period
    //   misalignment, well within the 3-tick majority-vote window.
    //
    // Mid-bit sampling with majority vote (A3-integrated):
    //   Data bits: majority of rx_serial at os_phase 7, 8, 9 → 2-of-3.
    //   Stop bit:  majority of rx_serial at os_phase 7, 8, 9.
    //              If stop-bit majority is 0 → framing error (A3).
    //
    // Loopback alignment:
    //   TX advances on bit_tick (os_phase wraps from 15→0).
    //   In loopback, RX_IDLE sees START from TX_START which is asserted starting
    //   at a bit_tick (TX_IDLE→TX_START on bit_tick).  RX detects the low level
    //   at the next os_tick after the TX flip (phase 1 of that bit period).
    //   os_phase is then reset to 0 → mid-bit sample at phase 8 of the START
    //   period, which is the exact mid-point.  TX_START→TX_DATA happens 15
    //   more os_ticks later (one full bit after start of START period).  RX
    //   moves from RX_START to RX_DATA at os_phase==15 of the START period
    //   (= bit_tick), and samples bit0 at os_phase 8 of the next period.
    //   TX drives bit0 for the full bit period starting at that same bit_tick.
    //   Sampling is therefore aligned in loopback.
    // =========================================================================
    typedef enum logic [2:0] {
        RX_IDLE  = 3'd0,
        RX_START = 3'd1,   // absorbing the START bit period; verify mid-bit low
        RX_DATA  = 3'd2,   // collecting 8 data bits
        RX_STOP  = 3'd3,   // sampling STOP bit (A3 framing-error check)
        RX_DONE  = 3'd4,   // push byte to FIFO
        RX_RSV0  = 3'd5,   // unused
        RX_RSV1  = 3'd6,   // unused
        RX_RSV2  = 3'd7    // unused; needed for 3-bit enum completeness
    } rx_state_e;

    rx_state_e   rx_state_q;
    logic [7:0]  rx_byte_q;    // assembled receive byte, bit-indexed
    logic [2:0]  rx_bit_q;     // data bit counter 0..7
    logic        rx_serial;    // mux: loopback selects tx_serial

    // Majority-vote sample registers for phases 7, 8, 9.
    logic        rx_s7_q, rx_s8_q, rx_s9_q;
    logic        rx_maj;   // 2-of-3 majority of phases 7, 8, 9

    assign rx_maj = (rx_s7_q & rx_s8_q) | (rx_s8_q & rx_s9_q) | (rx_s7_q & rx_s9_q);

    // A3: framing-error sticky bit.
    // Set when a framing error is detected (STOP bit sampled as 0).
    // Cleared by rx_pop (read of UART_RX — read-to-clear) or by reset.
    logic framing_error_q;

    // 2-FF synchroniser on the asynchronous uart_rx_i pad (CDC hardening).
    // Idle line is high (8N1).  Loopback path uses the internal tx_serial
    // (same clock domain) and bypasses this synchroniser.
    logic uart_rx_sync0_q;
    logic uart_rx_sync1_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            uart_rx_sync0_q <= 1'b1;
            uart_rx_sync1_q <= 1'b1;
        end else begin
            uart_rx_sync0_q <= uart_rx_i;
            uart_rx_sync1_q <= uart_rx_sync0_q;
        end
    end

    assign rx_serial = loopback ? tx_serial : uart_rx_sync1_q;

    // Framing-error sticky FF (A3): set on framing error, cleared on rx_pop.
    // Triggered at os_phase==10 in RX_STOP so that rx_s7/s8/s9 are all stable
    // (they were written at phases 7, 8, 9 in the RX FSM always_ff; at phase 10
    // they reflect those values and rx_maj gives the correct 2-of-3 result).
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            framing_error_q <= 1'b0;
        end else begin
            if (rx_pop)
                framing_error_q <= 1'b0;        // read-to-clear
            else if (rx_state_q == RX_STOP && os_tick && os_phase_q == 4'd10)
                framing_error_q <= framing_error_q | !rx_maj;  // A3: set on bad stop
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rx_state_q   <= RX_IDLE;
            rx_byte_q    <= 8'h0;
            rx_bit_q     <= 3'h0;
            rx_push      <= 1'b0;
            rx_push_data <= 8'h0;
            rx_s7_q      <= 1'b0;
            rx_s8_q      <= 1'b0;
            rx_s9_q      <= 1'b0;
        end else begin
            rx_push <= 1'b0;  // default: no push this cycle

            unique case (rx_state_q)
                // -----------------------------------------------------------------
                // RX_IDLE: wait for START bit (line low at any os_tick).
                // -----------------------------------------------------------------
                RX_IDLE: begin
                    if (rx_en && !rx_serial && os_tick) begin
                        // Start detected: align phase to 0 so mid-bit = phase 8.
                        // os_phase_q is reset in the os_tick always_ff block via
                        // the rx_align_phase signal asserted here.
                        rx_bit_q   <= 3'h0;
                        rx_byte_q  <= 8'h0;
                        rx_s7_q    <= 1'b0;
                        rx_s8_q    <= 1'b0;
                        rx_s9_q    <= 1'b0;
                        rx_state_q <= RX_START;
                    end
                end

                // -----------------------------------------------------------------
                // RX_START: absorb the START bit period; mid-bit sample at phase 8
                // just verifies the line is still low (noise guard).  Advance to
                // RX_DATA on bit_tick (phase 15 wrap).
                // -----------------------------------------------------------------
                RX_START: begin
                    if (os_tick) begin
                        // Capture majority-vote samples for START verification
                        if (os_phase_q == 4'd7) rx_s7_q <= rx_serial;
                        if (os_phase_q == 4'd8) rx_s8_q <= rx_serial;
                        if (os_phase_q == 4'd9) rx_s9_q <= rx_serial;
                    end
                    if (bit_tick) begin
                        // START period complete.  Reject a false start (noise
                        // glitch): a valid START is majority-LOW across phases
                        // 7/8/9 (rx_maj==0).  If rx_maj==1 the line was not
                        // genuinely low mid-bit, so abandon and return to IDLE
                        // without collecting a bogus byte.
                        rx_s7_q    <= 1'b0;
                        rx_s8_q    <= 1'b0;
                        rx_s9_q    <= 1'b0;
                        rx_state_q <= rx_maj ? RX_IDLE : RX_DATA;
                    end
                end

                // -----------------------------------------------------------------
                // RX_DATA: collect 8 data bits LSB-first using majority vote at
                // os_phases 7, 8, 9 of each bit period.
                // -----------------------------------------------------------------
                RX_DATA: begin
                    if (os_tick) begin
                        if (os_phase_q == 4'd7) rx_s7_q <= rx_serial;
                        if (os_phase_q == 4'd8) rx_s8_q <= rx_serial;
                        if (os_phase_q == 4'd9) rx_s9_q <= rx_serial;
                    end
                    if (bit_tick) begin
                        // Latch majority-voted bit (rx_s9_q already captured this
                        // cycle: bit_tick == os_tick && os_phase_q==15, so phase 9
                        // was captured 6 os_ticks ago — rx_s9_q is valid).
                        rx_byte_q[rx_bit_q] <= rx_maj;
                        rx_s7_q <= 1'b0;
                        rx_s8_q <= 1'b0;
                        rx_s9_q <= 1'b0;
                        if (rx_bit_q == 3'd7) begin
                            rx_state_q <= RX_STOP;
                        end else begin
                            rx_bit_q <= rx_bit_q + 3'h1;
                        end
                    end
                end

                // -----------------------------------------------------------------
                // RX_STOP: sample the STOP bit (A3 framing-error detection).
                // The framing_error_q FF is set by its own always_ff block above
                // when it observes os_phase==9 in this state.  We advance to DONE
                // on bit_tick regardless (byte is always pushed).
                // -----------------------------------------------------------------
                RX_STOP: begin
                    if (os_tick) begin
                        if (os_phase_q == 4'd7) rx_s7_q <= rx_serial;
                        if (os_phase_q == 4'd8) rx_s8_q <= rx_serial;
                        if (os_phase_q == 4'd9) rx_s9_q <= rx_serial;
                    end
                    if (bit_tick) begin
                        rx_state_q <= RX_DONE;
                    end
                end

                // -----------------------------------------------------------------
                // RX_DONE: push assembled byte to RX FIFO (with or without error).
                // -----------------------------------------------------------------
                RX_DONE: begin
                    rx_push      <= 1'b1;
                    rx_push_data <= rx_byte_q;
                    rx_state_q   <= RX_IDLE;
                end

                default: rx_state_q <= RX_IDLE;
            endcase
        end
    end

    // rx_align_phase: asserted combinationally when RX_IDLE detects START.
    // Resets os_phase to 0 so mid-bit sampling lands at phase 8.
    assign rx_align_phase = rx_en && !rx_serial && os_tick &&
                            (rx_state_q == RX_IDLE);

    // =========================================================================
    // STATUS flags (combinational)
    // =========================================================================
    wire tx_busy = (tx_state_q != TX_IDLE);

    // =========================================================================
    // HW-writeback — combinational mirrors driven every cycle
    // =========================================================================
    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // UART_RX: RX FIFO head (RO — HW owns this)
        hw_wen_i  [REG_UART_RX] = 1'b1;
        hw_wdata_i[REG_UART_RX] = {24'h0, rx_head};

        // UART_STATUS: live FIFO flags (RO — HW owns this)
        // A3: bit [6] = framing_error_q (sticky; read-to-clear on UART_RX read)
        hw_wen_i  [REG_UART_STATUS] = 1'b1;
        hw_wdata_i[REG_UART_STATUS] = {
            25'h0,
            framing_error_q, // [6] framing_error (A3)
            rx_valid,        // [5] rx_valid
            rx_full,         // [4] rx_full
            rx_empty,        // [3] rx_empty
            tx_empty,        // [2] tx_empty
            tx_full,         // [1] tx_full
            tx_busy          // [0] tx_busy
        };
    end

    // =========================================================================
    // A2 — Sticky "TX FIFO was non-empty" register.
    // Prevents a spurious tx-empty IRQ at reset when tx_empty=1 but no byte
    // has ever been pushed.  Set whenever the TX FIFO becomes non-empty
    // (tx_push into a non-full FIFO, or equivalently !tx_empty after push).
    // Never cleared except by reset.
    // =========================================================================
    logic tx_was_nonempty_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tx_was_nonempty_q <= 1'b0;
        end else begin
            if (tx_push && !tx_full)
                tx_was_nonempty_q <= 1'b1;
        end
    end

    // =========================================================================
    // IRQ output
    // irq_tx_empty gated by tx_was_nonempty_q to suppress false fire at reset.
    // =========================================================================
    assign irq_o = (irq_tx_empty_en & tx_empty & tx_was_nonempty_q) |
                   (irq_rx_valid_en & rx_valid);

endmodule : uart_controller

