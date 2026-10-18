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
    parameter int unsigned ADDR_W      = 12,  // APB4 local address width
    parameter int unsigned SYNC_STAGES = 2    // uart_rx_i synchroniser depth (>= 2, bead xtaa)
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

    // The shared phase counter free-runs: it times the TX engine only.  The RX
    // engine keeps its own phase counter (rx_phase_q, below) that it re-aligns on
    // every START edge, so receiving never disturbs the transmitted bit timing
    // and TX stays exactly 16 os_ticks per bit (bead shm5).
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            baud_cnt_q <= 16'h0;
            os_phase_q <= 4'h0;
        end else if (os_tick) begin
            baud_cnt_q <= regs_o[REG_UART_BAUD][15:0];
            os_phase_q <= os_phase_q + 4'h1;  // wraps 15→0 naturally
        end else begin
            baud_cnt_q <= baud_cnt_q - 16'h1;
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
    // A4 — RX engine (16x oversample, serial receiver; re-syncs every frame)
    //
    // Receives from uart_rx_i (through the cdc_sync synchroniser) or from the
    // internal tx_serial when loopback is enabled (same clock domain — no
    // synchroniser needed).
    //
    // Own phase counter (bead shm5):
    //   rx_phase_q counts os_ticks 0..15 and is reset to 0 on the os_tick at
    //   which RX_IDLE sees the line low (the START falling edge, seen up to one
    //   os_tick late).  It is independent of the TX phase counter os_phase_q, so
    //   re-aligning the receiver never stretches or shortens a transmitted bit.
    //   Every frame therefore starts from a fresh alignment and a baud error
    //   cannot accumulate from one byte to the next.
    //
    // Mid-bit sampling with majority vote (A3-integrated):
    //   Each bit is voted 2-of-3 on rx_phase_q = 6, 7, 8.  Because the phase
    //   counter restarts AT the detection os_tick, rx_phase_q == k is seen k+1
    //   os_ticks after it; phases 6/7/8 are therefore 7/8/9 os_ticks after the
    //   detected edge, centred on 8 ticks, the bit mid-point (the true edge is
    //   0..1 os_tick before the detected one).
    //   START bit: a majority-high vote (not genuinely low mid-bit) is a noise
    //              glitch; it is rejected one os_tick after the vote completes.
    //   Data bits: voted values are latched at the end of the bit (phase 15).
    //   STOP bit:  voted on phases 6, 7 and the live line at phase 8; the frame
    //              is closed AT that mid-point: framing error if the vote is 0,
    //              byte pushed, RX_IDLE re-armed.  The next START may be
    //              accepted from there on, so frames sent back-to-back with a
    //              single stop bit and a bit-clock error of a few percent keep
    //              their framing.  The os_ticks between that mid-point and the
    //              nominal end of the stop bit absorb the error: the receiver
    //              is back in IDLE before even a fast sender's next START.
    //
    // Loopback alignment:
    //   TX advances on bit_tick; the START it drives is seen by RX one os_tick
    //   later and the receiver aligns to it.  The shared os_tick generator keeps
    //   the two engines on the same tick grid.
    // =========================================================================
    typedef enum logic [2:0] {
        RX_IDLE  = 3'd0,
        RX_START = 3'd1,   // absorbing the START bit period; verify mid-bit low
        RX_DATA  = 3'd2,   // collecting 8 data bits
        RX_STOP  = 3'd3,   // voting the STOP bit; closes the frame at its mid-point
        RX_RSV0  = 3'd4,   // unused
        RX_RSV1  = 3'd5,   // unused
        RX_RSV2  = 3'd6,   // unused
        RX_RSV3  = 3'd7    // unused; needed for 3-bit enum completeness
    } rx_state_e;

    // Vote phases (rx_phase_q values), the phase at which the START vote is
    // evaluated (one os_tick after the last vote) and the last phase of a bit.
    localparam logic [3:0] RX_VOTE_A    = 4'd6;
    localparam logic [3:0] RX_VOTE_B    = 4'd7;
    localparam logic [3:0] RX_VOTE_C    = 4'd8;
    localparam logic [3:0] RX_START_CHK = 4'd9;
    localparam logic [3:0] RX_PHASE_END = 4'd15;

    rx_state_e   rx_state_q;
    logic [7:0]  rx_byte_q;    // assembled receive byte, bit-indexed
    logic [2:0]  rx_bit_q;     // data bit counter 0..7
    logic        rx_serial;    // mux: loopback selects tx_serial
    logic [3:0]  rx_phase_q;   // RX oversample phase, re-aligned on every START
    logic        rx_start_detect;   // RX_IDLE sees the line low on an os_tick
    logic        rx_bit_tick;       // end of an RX bit period (phase 15 os_tick)
    logic        rx_stop_close;     // STOP-bit mid-point os_tick: frame closes here

    // Majority-vote sample registers for phases RX_VOTE_A / _B / _C.
    logic        rx_sa_q, rx_sb_q, rx_sc_q;
    logic        rx_maj;        // 2-of-3 majority of the registered votes
    logic        rx_stop_maj;   // STOP vote: registered A, B and the live line

    assign rx_maj      = (rx_sa_q & rx_sb_q) | (rx_sb_q & rx_sc_q) | (rx_sa_q & rx_sc_q);
    assign rx_stop_maj = (rx_sa_q & rx_sb_q) | (rx_sb_q & rx_serial) | (rx_sa_q & rx_serial);

    // A3: framing-error sticky bit.
    // Set when a framing error is detected (STOP bit voted 0).
    // Cleared by rx_pop (read of UART_RX — read-to-clear) or by reset.
    logic framing_error_q;

    // 2-FF synchroniser on the asynchronous uart_rx_i pad (CDC hardening).
    // Idle line is high (8N1), so the synchroniser must reset to 1: a reset
    // value of 0 would present a false START bit to the receiver FSM.
    // cdc_sync with RESET_VAL = 1 resets both stages to 1 (no inverters).
    // Loopback path uses the internal tx_serial (same clock domain) and
    // bypasses this synchroniser. Same 2-cycle latency as the previous
    // hand-written chain; the reset is now asserted asynchronously by the
    // primitive (see the cdc_sync header) where it was synchronous here.
    // SYNC_STAGES > 2 is safe for the receiver: the RX FSM aligns its
    // oversample phase to the *synchronised* start edge and every later data
    // edge is delayed by the same constant, so the sample points keep their
    // position relative to the bits; only the data-valid latency grows.
    logic uart_rx_sync_q;

    cdc_sync #(
        .WIDTH     (1),
        .STAGES    (SYNC_STAGES),
        .RESET_VAL (1'b1)
    ) u_uart_rx_sync (
        .clk_i   (clk),
        .rst_n_i (rst_n),
        .d_i     (uart_rx_i),
        .q_o     (uart_rx_sync_q)
    );

    assign rx_serial = loopback ? tx_serial : uart_rx_sync_q;

    // RX_IDLE: any os_tick on which the line is low is the START edge.
    assign rx_start_detect = rx_en && !rx_serial && os_tick && (rx_state_q == RX_IDLE);
    assign rx_bit_tick     = os_tick && (rx_phase_q == RX_PHASE_END);
    assign rx_stop_close   = os_tick && (rx_state_q == RX_STOP) && (rx_phase_q == RX_VOTE_C);

    // RX phase counter: free-runs on os_tick, restarts at the START edge.
    always_ff @(posedge clk) begin
        if (!rst_n)               rx_phase_q <= 4'h0;
        else if (rx_start_detect) rx_phase_q <= 4'h0;
        else if (os_tick)         rx_phase_q <= rx_phase_q + 4'h1;  // wraps 15→0
    end

    // Framing-error sticky FF (A3): set when the STOP vote (taken at the STOP
    // bit's mid-point) is 0, cleared on rx_pop.  A pop on the same clock wins,
    // as before.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            framing_error_q <= 1'b0;
        end else begin
            if (rx_pop)
                framing_error_q <= 1'b0;        // read-to-clear
            else if (rx_stop_close)
                framing_error_q <= framing_error_q | !rx_stop_maj;  // A3: set on bad stop
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rx_state_q   <= RX_IDLE;
            rx_byte_q    <= 8'h0;
            rx_bit_q     <= 3'h0;
            rx_push      <= 1'b0;
            rx_push_data <= 8'h0;
            rx_sa_q      <= 1'b0;
            rx_sb_q      <= 1'b0;
            rx_sc_q      <= 1'b0;
        end else begin
            rx_push <= 1'b0;  // default: no push this cycle

            unique case (rx_state_q)
                // -----------------------------------------------------------------
                // RX_IDLE: wait for START bit (line low at any os_tick).  Also the
                // state the receiver is in from the STOP bit's mid-point on, so the
                // next frame's START is accepted without waiting for the stop bit
                // to end.  rx_phase_q restarts via rx_start_detect.
                // -----------------------------------------------------------------
                RX_IDLE: begin
                    if (rx_start_detect) begin
                        rx_bit_q   <= 3'h0;
                        rx_byte_q  <= 8'h0;
                        rx_sa_q    <= 1'b0;
                        rx_sb_q    <= 1'b0;
                        rx_sc_q    <= 1'b0;
                        rx_state_q <= RX_START;
                    end
                end

                // -----------------------------------------------------------------
                // RX_START: absorb the START bit period; mid-bit votes verify the
                // line is low (noise guard).  Advance to RX_DATA at the end of the
                // bit period.  A false start is rejected as soon as the vote is
                // complete so a genuine START edge in the rest of the bit period
                // is not missed.
                // -----------------------------------------------------------------
                RX_START: begin
                    if (os_tick) begin
                        if (rx_phase_q == RX_VOTE_A) rx_sa_q <= rx_serial;
                        if (rx_phase_q == RX_VOTE_B) rx_sb_q <= rx_serial;
                        if (rx_phase_q == RX_VOTE_C) rx_sc_q <= rx_serial;
                        // A valid START is majority-LOW (rx_maj==0).  If rx_maj==1
                        // the line was not genuinely low mid-bit, so return to IDLE
                        // now (bead rqvo) and re-arm START detection without
                        // collecting a bogus byte.  rx_sc_q was captured one
                        // os_tick ago, so rx_maj is valid here.
                        if (rx_phase_q == RX_START_CHK && rx_maj) begin
                            rx_sa_q    <= 1'b0;
                            rx_sb_q    <= 1'b0;
                            rx_sc_q    <= 1'b0;
                            rx_state_q <= RX_IDLE;
                        end
                    end
                    if (rx_bit_tick) begin
                        // START period complete; rx_maj==0 here (a majority-HIGH
                        // vote was already rejected at RX_START_CHK).
                        rx_sa_q    <= 1'b0;
                        rx_sb_q    <= 1'b0;
                        rx_sc_q    <= 1'b0;
                        rx_state_q <= RX_DATA;
                    end
                end

                // -----------------------------------------------------------------
                // RX_DATA: collect 8 data bits LSB-first using the 2-of-3 vote at
                // rx_phase_q 6/7/8 of each bit period.
                // -----------------------------------------------------------------
                RX_DATA: begin
                    if (os_tick) begin
                        if (rx_phase_q == RX_VOTE_A) rx_sa_q <= rx_serial;
                        if (rx_phase_q == RX_VOTE_B) rx_sb_q <= rx_serial;
                        if (rx_phase_q == RX_VOTE_C) rx_sc_q <= rx_serial;
                    end
                    if (rx_bit_tick) begin
                        // Latch the majority-voted bit (all three votes were
                        // captured at least 6 os_ticks ago).
                        rx_byte_q[rx_bit_q] <= rx_maj;
                        rx_sa_q <= 1'b0;
                        rx_sb_q <= 1'b0;
                        rx_sc_q <= 1'b0;
                        if (rx_bit_q == 3'd7) begin
                            rx_state_q <= RX_STOP;
                        end else begin
                            rx_bit_q <= rx_bit_q + 3'h1;
                        end
                    end
                end

                // -----------------------------------------------------------------
                // RX_STOP: vote the STOP bit (A3 framing-error detection) and close
                // the frame at its mid-point: push the assembled byte (with or
                // without a framing error; framing_error_q is set by its own
                // always_ff via rx_stop_close) and go back to RX_IDLE so the next
                // START can be accepted from here on.
                // -----------------------------------------------------------------
                RX_STOP: begin
                    if (os_tick) begin
                        if (rx_phase_q == RX_VOTE_A) rx_sa_q <= rx_serial;
                        if (rx_phase_q == RX_VOTE_B) rx_sb_q <= rx_serial;
                    end
                    if (rx_stop_close) begin
                        rx_push      <= 1'b1;
                        rx_push_data <= rx_byte_q;
                        rx_sa_q      <= 1'b0;
                        rx_sb_q      <= 1'b0;
                        rx_state_q   <= RX_IDLE;
                    end
                end

                default: rx_state_q <= RX_IDLE;
            endcase
        end
    end

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

