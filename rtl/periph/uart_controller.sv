// uart_controller.sv
// Phase 5 (M4) — UART peripheral, 8N1, AXI4-Lite slave.
//
// Register map (word indices into axi_lite_register_bank):
//   0  UART_TX     WO [7:0]  write pushes byte to TX FIFO (via AXI snoop)
//   1  UART_RX     RO [7:0]  RX FIFO head; read pops via snoop
//   2  UART_STATUS RO        [0]=tx_busy [1]=tx_full [2]=tx_empty
//                            [3]=rx_empty [4]=rx_full [5]=rx_valid(!rx_empty)
//   3  UART_CTRL   RW [4:0]  [0]=tx_en [1]=rx_en [2]=irq_tx_empty_en
//                            [3]=irq_rx_valid_en [4]=loopback
//   4  UART_BAUD   RW [15:0] bit-period divisor D: 1 serial bit = (D+1) clocks
//
// TX engine: IDLE → START(0) → DATA[0..7] LSB-first → STOP(1) → IDLE
// RX engine: detect START (line low), sample 8 data bits at baud ticks,
//            push assembled byte to RX FIFO.
// Loopback: RX engine receives uart_tx_o (internal serial line) instead of
//           uart_rx_i; shared baud tick keeps sampling exactly aligned.
//
// IRQ: irq_o = (irq_tx_empty_en & tx_empty) | (irq_rx_valid_en & rx_valid)
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module uart_controller
    import axi_pkg::*;
#(
    parameter int unsigned ADDR_W = 12   // AXI-Lite local address width
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // AXI4-Lite slave — control/status registers
    // Port names match axi_lite_register_bank.sv exactly.
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    input  logic [31:0]       s_axil_wdata,
    input  logic [3:0]        s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    output logic [31:0]       s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,

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

    axi_lite_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .clk            (clk),
        .rst_n          (rst_n),
        .s_axil_awaddr  (s_axil_awaddr),
        .s_axil_awprot  (s_axil_awprot),
        .s_axil_awvalid (s_axil_awvalid),
        .s_axil_awready (s_axil_awready),
        .s_axil_wdata   (s_axil_wdata),
        .s_axil_wstrb   (s_axil_wstrb),
        .s_axil_wvalid  (s_axil_wvalid),
        .s_axil_wready  (s_axil_wready),
        .s_axil_bresp   (s_axil_bresp),
        .s_axil_bvalid  (s_axil_bvalid),
        .s_axil_bready  (s_axil_bready),
        .s_axil_araddr  (s_axil_araddr),
        .s_axil_arprot  (s_axil_arprot),
        .s_axil_arvalid (s_axil_arvalid),
        .s_axil_arready (s_axil_arready),
        .s_axil_rdata   (s_axil_rdata),
        .s_axil_rresp   (s_axil_rresp),
        .s_axil_rvalid  (s_axil_rvalid),
        .s_axil_rready  (s_axil_rready),
        .regs_o         (regs_o),
        .hw_wen_i       (hw_wen_i),
        .hw_wdata_i     (hw_wdata_i)
    );

    // =========================================================================
    // Control register aliases
    // =========================================================================
    logic tx_en, rx_en, irq_tx_empty_en, irq_rx_valid_en, loopback;

    assign tx_en          = regs_o[REG_UART_CTRL][CTRL_TX_EN_BIT];
    assign rx_en          = regs_o[REG_UART_CTRL][CTRL_RX_EN_BIT];
    assign irq_tx_empty_en = regs_o[REG_UART_CTRL][CTRL_IRQ_TX_EMPTY_BIT];
    assign irq_rx_valid_en = regs_o[REG_UART_CTRL][CTRL_IRQ_RX_VALID_BIT];
    assign loopback       = regs_o[REG_UART_CTRL][CTRL_LOOPBACK_BIT];

    // =========================================================================
    // AXI write/read snoop — capture addresses at handshake time
    // Used to detect writes to UART_TX (push TX FIFO) and reads of UART_RX
    // (pop RX FIFO). The register bank exposes no write-strobe, so we snoop
    // the AXI handshake signals directly.
    // =========================================================================
    logic [WORDW-1:0] snoop_waddr_q;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0]      snoop_wdata_full_q;  // full 32 bits captured; [7:0] used
    /* verilator lint_on  UNUSEDSIGNAL */
    logic [7:0]       snoop_wdata_q;
    logic [WORDW-1:0] snoop_raddr_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            snoop_waddr_q      <= '0;
            snoop_wdata_full_q <= '0;
            snoop_wdata_q      <= '0;
            snoop_raddr_q      <= '0;
        end else begin
            if (s_axil_awvalid && s_axil_awready)
                snoop_waddr_q <= s_axil_awaddr[ADDR_W-1:2];
            if (s_axil_wvalid && s_axil_wready) begin
                snoop_wdata_full_q <= s_axil_wdata;
                snoop_wdata_q      <= s_axil_wdata[7:0];
            end
            if (s_axil_arvalid && s_axil_arready)
                snoop_raddr_q <= s_axil_araddr[ADDR_W-1:2];
        end
    end

    // AXI transaction completion pulses
    wire wr_done = s_axil_bvalid && s_axil_bready;
    wire rd_done = s_axil_rvalid && s_axil_rready;

    // TX FIFO push: fired when a write to UART_TX completes
    wire tx_push = wr_done && (snoop_waddr_q == WORDW'(REG_UART_TX));
    // RX FIFO pop:  fired when a read of UART_RX completes
    wire rx_pop  = rd_done && (snoop_raddr_q == WORDW'(REG_UART_RX));

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
                tx_fifo_q[tx_wptr_q[FIFO_DEPTH_LG-1:0]] <= snoop_wdata_q;
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
    // Baud-rate generator — shared by TX and RX engines
    // Counts down from (BAUD_DIV) to 0; fires tick when counter reaches 0.
    // BAUD_DIV = regs_o[REG_UART_BAUD][15:0]; one bit = (BAUD_DIV+1) clocks.
    // When BAUD_DIV=0 the counter stays at 0 → tick every clock.
    // =========================================================================
    logic [15:0] baud_cnt_q;
    logic        baud_tick;

    assign baud_tick = (baud_cnt_q == 16'h0);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            baud_cnt_q <= 16'h0;
        end else begin
            if (baud_tick)
                baud_cnt_q <= regs_o[REG_UART_BAUD][15:0];
            else
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

    // tx_pop: pop TX FIFO at the IDLE→LOAD transition
    always_comb begin
        tx_pop   = 1'b0;
        tx_serial = 1'b1;  // idle high
        unique case (tx_state_q)
            TX_IDLE: begin
                tx_serial = 1'b1;
                tx_pop    = tx_en && !tx_empty && baud_tick;
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
                    if (tx_en && !tx_empty && baud_tick) begin
                        tx_shift_q <= tx_head;
                        tx_state_q <= TX_START;
                    end
                end
                TX_START: begin
                    if (baud_tick) begin
                        tx_bit_q   <= 3'h0;
                        tx_state_q <= TX_DATA;
                    end
                end
                TX_DATA: begin
                    if (baud_tick) begin
                        tx_shift_q <= {1'b0, tx_shift_q[7:1]};
                        if (tx_bit_q == 3'd7) begin
                            tx_state_q <= TX_STOP;
                        end else begin
                            tx_bit_q <= tx_bit_q + 3'h1;
                        end
                    end
                end
                TX_STOP: begin
                    if (baud_tick)
                        tx_state_q <= TX_IDLE;
                end
                default: tx_state_q <= TX_IDLE;
            endcase
        end
    end

    assign uart_tx_o = tx_serial;

    // =========================================================================
    // RX engine — 8N1 serial receiver
    // Receives from uart_rx_i or uart_tx_o (loopback).
    // Detects START (line low on baud_tick), samples 8 bits LSB-first, pushes
    // assembled byte to RX FIFO.
    // =========================================================================
    // RX engine uses 3 states: IDLE → DATA (8 bits) → DONE (push byte).
    // The START state is eliminated: on detecting the START bit (line low on
    // baud_tick) we move directly to DATA and count 8 data bit periods.
    // This keeps RX sampling aligned with TX because:
    //   - TX emits START on tick T (tx_state goes TX_IDLE→TX_START).
    //   - On the NEXT baud_tick (T+D+1) TX transitions TX_START→TX_DATA,
    //     putting bit0 on the wire.  That same tick, RX (in IDLE) sees the
    //     START (line=0 from TX_START period) and transitions to RX_DATA.
    //   - The tick after that (T+2*(D+1)) RX samples bit0 = what TX is
    //     currently driving.  TX also transitions bit0→bit1 on that tick,
    //     but the RX samples combinationally BEFORE the FF update, so it
    //     sees bit0 correctly.
    typedef enum logic [1:0] {
        RX_IDLE = 2'd0,
        RX_DATA = 2'd1,
        RX_DONE = 2'd2,
        RX_RSV  = 2'd3   // unused; needed for 2-bit enum completeness
    } rx_state_e;

    rx_state_e   rx_state_q;
    logic [7:0]  rx_byte_q;   // assembled receive byte, bit-indexed
    logic [2:0]  rx_bit_q;
    logic        rx_serial;   // mux: loopback selects tx_serial

    // 2-FF synchroniser on the asynchronous uart_rx_i pad (CDC hardening).
    // uart_rx_i may be asynchronous to clk; sample through two stages before
    // the RX FSM consumes it.  Idle line is high (8N1).  Loopback path uses the
    // internal tx_serial (same clock domain) and bypasses this synchroniser.
    logic        uart_rx_sync0_q;
    logic        uart_rx_sync1_q;

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

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rx_state_q   <= RX_IDLE;
            rx_byte_q    <= 8'h0;
            rx_bit_q     <= 3'h0;
            rx_push      <= 1'b0;
            rx_push_data <= 8'h0;
        end else begin
            rx_push <= 1'b0;  // default: no push this cycle

            unique case (rx_state_q)
                RX_IDLE: begin
                    // Detect START bit: line goes low on baud_tick.
                    // Immediately begin collecting data bits on the next tick.
                    if (rx_en && !rx_serial && baud_tick) begin
                        rx_bit_q   <= 3'h0;
                        rx_byte_q  <= 8'h0;
                        rx_state_q <= RX_DATA;
                    end
                end
                RX_DATA: begin
                    // Sample 8 data bits LSB-first at each baud tick.
                    if (baud_tick) begin
                        rx_byte_q[rx_bit_q] <= rx_serial;
                        if (rx_bit_q == 3'd7) begin
                            rx_state_q <= RX_DONE;
                        end else begin
                            rx_bit_q <= rx_bit_q + 3'h1;
                        end
                    end
                end
                RX_DONE: begin
                    // Push assembled byte immediately (no STOP-bit wait needed
                    // since we already spent 8 baud periods in RX_DATA).
                    rx_push      <= 1'b1;
                    rx_push_data <= rx_byte_q;
                    rx_state_q   <= RX_IDLE;
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
        hw_wen_i  [REG_UART_STATUS] = 1'b1;
        hw_wdata_i[REG_UART_STATUS] = {
            26'h0,
            rx_valid,    // [5] rx_valid
            rx_full,     // [4] rx_full
            rx_empty,    // [3] rx_empty
            tx_empty,    // [2] tx_empty
            tx_full,     // [1] tx_full
            tx_busy      // [0] tx_busy
        };
    end

    // =========================================================================
    // IRQ output
    // =========================================================================
    assign irq_o = (irq_tx_empty_en & tx_empty) | (irq_rx_valid_en & rx_valid);

endmodule : uart_controller
