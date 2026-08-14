// spi_controller.sv
// Phase 5 (M4) — SPI master peripheral, MSB-first, 8-bit, APB4 slave.
// APB migration PR-3: converted from AXI4-Lite slave to APB4 slave.
//
// Register map (word indices into apb4_register_bank):
//   0  SPI_TX      WO [7:0]  write pushes byte to TX FIFO (via APB access snoop)
//   1  SPI_RX      RO [7:0]  RX FIFO head; read pops via snoop
//   2  SPI_STATUS  RO        [0]=busy [1]=tx_full [2]=tx_empty
//                            [3]=rx_empty [4]=rx_valid(!rx_empty) [5]=rx_full
//   3  SPI_CTRL    RW [4:0]  [0]=enable [1]=CPOL [2]=CPHA
//                            [3]=irq_done_en [4]=loopback
//   4  SPI_CLK_DIV RW [15:0] sclk half-period = (DIV+1) clocks
//   5  SPI_CS_CTRL RW [0]    manual cs_n level (0=assert/active-low)
//
// Shift engine: MSB-first, 8 bits per transfer.
//   CPOL: idle SCLK level (0=low, 1=high)
//   CPHA=0: sample leading edge, shift trailing edge
//   CPHA=1: shift leading edge, sample trailing edge
//
// Loopback: spi_miso sample comes from spi_mosi_o instead of spi_miso_i.
//
// LIMITATION (external slaves): in CPHA=0 the internal MISO sample on the
// leading edge precedes the spi_sclk_o pin transition by 1 system clock
// (sclk_q toggles via NBA; the pin shows the old level that cycle).  This is
// harmless in loopback (MISO sourced from internal regs).  For a real external
// slave use SPI_CLK_DIV >= 7 so the 1-clock offset is a negligible fraction of
// the SCLK half-period and setup margin is preserved.
//
// spi_miso_i is routed through a cdc_2ff_sync (bead claude_verilog_test-a2g)
// before reaching the shift engine, adding 2 fabric clocks of latency on top
// of the above. SPI_CLK_DIV >= 7 keeps this well inside the settled window;
// SPI_CLK_DIV == 0 or 1 is NOT safe for a real external slave (loopback is
// unaffected -- see the miso_in mux below).
//
// APB snoop (replaces AXI snoop):
//   TX push: psel & penable & pwrite  & pready at SPI_TX word address with |pstrb.
//   RX pop:  psel & penable & !pwrite & pready at SPI_RX word address.
//   APB transfers are single-beat and the access phase completes in one cycle
//   when pready=1, so the pulse is exactly one cycle — cleaner than the
//   two-channel AXI-Lite snoop.  No capture registers needed.
//
// IRQ: irq_o = irq_done_en & rx_valid
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module spi_controller #(
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
    // SPI I/O
    // =========================================================================
    output logic spi_sclk_o,
    output logic spi_mosi_o,
    input  logic spi_miso_i,
    output logic spi_cs_n_o,

    // =========================================================================
    // Interrupt output
    // =========================================================================
    output logic irq_o
);

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_SPI_TX      = 0;
    localparam int unsigned REG_SPI_RX      = 1;
    localparam int unsigned REG_SPI_STATUS  = 2;
    localparam int unsigned REG_SPI_CTRL    = 3;
    localparam int unsigned REG_SPI_CLK_DIV = 4;
    localparam int unsigned REG_SPI_CS_CTRL = 5;
    localparam int unsigned N_REGS          = 6;

    // CTRL bit positions
    localparam int unsigned CTRL_ENABLE_BIT   = 0;
    localparam int unsigned CTRL_CPOL_BIT     = 1;
    localparam int unsigned CTRL_CPHA_BIT     = 2;
    localparam int unsigned CTRL_IRQ_DONE_BIT = 3;
    localparam int unsigned CTRL_LOOPBACK_BIT = 4;

    // Word address width
    localparam int unsigned WORDW = ADDR_W - 2;

    // FIFO parameters
    localparam int unsigned FIFO_DEPTH    = 4;
    localparam int unsigned FIFO_DEPTH_LG = 2;
    localparam int unsigned PTR_W         = FIFO_DEPTH_LG + 1;  // 3 bits

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 SPI_TX      WO
        32'h0000_0000,  // 1 SPI_RX      RO (HW-written)
        32'h0000_0000,  // 2 SPI_STATUS  RO (HW-written)
        32'h0000_0000,  // 3 SPI_CTRL    RW (disabled at reset)
        32'h0000_0000,  // 4 SPI_CLK_DIV RW (half-period=1 clk at reset)
        32'h0000_0001   // 5 SPI_CS_CTRL RW (cs_n=1 = deasserted at reset)
    };

    // WMASK: TX/RX/STATUS RO; CTRL[4:0]; CLK_DIV[15:0]; CS_CTRL[0]
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0000,  // 0 SPI_TX      WO (not stored)
        32'h0000_0000,  // 1 SPI_RX      RO
        32'h0000_0000,  // 2 SPI_STATUS  RO
        32'h0000_001F,  // 3 SPI_CTRL    RW [4:0]
        32'h0000_FFFF,  // 4 SPI_CLK_DIV RW [15:0]
        32'h0000_0001   // 5 SPI_CS_CTRL RW [0]
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
    logic spi_enable, cpol, cpha, irq_done_en, loopback;

    assign spi_enable  = regs_o[REG_SPI_CTRL][CTRL_ENABLE_BIT];
    assign cpol        = regs_o[REG_SPI_CTRL][CTRL_CPOL_BIT];
    assign cpha        = regs_o[REG_SPI_CTRL][CTRL_CPHA_BIT];
    assign irq_done_en = regs_o[REG_SPI_CTRL][CTRL_IRQ_DONE_BIT];
    assign loopback    = regs_o[REG_SPI_CTRL][CTRL_LOOPBACK_BIT];

    // =========================================================================
    // APB word address decode
    // =========================================================================
    logic [WORDW-1:0] apb_word_addr;
    assign apb_word_addr = paddr[ADDR_W-1:2];

    // Access-phase commit pulse: psel & penable & pready (pready=1 always here)
    wire apb_access = psel & penable;

    // =========================================================================
    // A1: PSTRB byte-lane priority mux.
    // Select the byte from pwdata corresponding to the lowest active strobe lane,
    // matching the AXI-Lite snoop behaviour so TX byte extraction is equivalent.
    // When pstrb==4'h0 the value is don't-care: tx_push is gated out.
    // =========================================================================
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

    // TX FIFO push: APB write ACCESS to SPI_TX with at least one strobe set.
    wire tx_push = apb_access && pwrite &&
                   (apb_word_addr == WORDW'(REG_SPI_TX)) &&
                   (|pstrb);

    // RX FIFO pop: APB read ACCESS completing at SPI_RX word address.
    wire rx_pop  = apb_access && !pwrite &&
                   (apb_word_addr == WORDW'(REG_SPI_RX));

    // =========================================================================
    // TX FIFO (depth=4, 8-bit wide, synchronous)
    // =========================================================================
    logic [7:0]       tx_fifo_q  [FIFO_DEPTH];
    logic [PTR_W-1:0] tx_wptr_q, tx_rptr_q;

    wire tx_empty = (tx_wptr_q == tx_rptr_q);
    wire tx_full  = (tx_wptr_q[PTR_W-1] != tx_rptr_q[PTR_W-1]) &&
                    (tx_wptr_q[PTR_W-2:0] == tx_rptr_q[PTR_W-2:0]);
    wire [7:0] tx_head = tx_fifo_q[tx_rptr_q[FIFO_DEPTH_LG-1:0]];

    logic tx_pop;  // driven by shift engine

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
    // SPI clock divider — generates sclk_edge pulse every (DIV+1) clocks
    // Half-period = (DIV+1) clocks.  Toggle sclk_q on each sclk_edge.
    // Only active during transfer (spi_active).
    // =========================================================================
    logic [15:0] sclk_div_cnt_q;
    logic        sclk_edge;

    assign sclk_edge = (sclk_div_cnt_q == 16'h0);

    logic spi_active;  // forward declaration; driven by state machine below

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sclk_div_cnt_q <= 16'h0;
        end else begin
            if (!spi_active) begin
                sclk_div_cnt_q <= regs_o[REG_SPI_CLK_DIV][15:0];
            end else if (sclk_edge) begin
                sclk_div_cnt_q <= regs_o[REG_SPI_CLK_DIV][15:0];
            end else begin
                sclk_div_cnt_q <= sclk_div_cnt_q - 16'h1;
            end
        end
    end

    // =========================================================================
    // SPI shift engine FSM
    //
    // Mode table (CPOL, CPHA):
    //   CPOL=0, CPHA=0: idle SCLK=0; sample rising, shift falling  (Mode 0)
    //   CPOL=0, CPHA=1: idle SCLK=0; shift rising,  sample falling (Mode 1)
    //   CPOL=1, CPHA=0: idle SCLK=1; sample falling, shift rising  (Mode 2)
    //   CPOL=1, CPHA=1: idle SCLK=1; shift falling,  sample rising (Mode 3)
    //
    // In all modes: the "leading edge" is the first toggle of SCLK.
    //   CPHA=0: sample on leading edge (active-to-idle direction for CPOL=1,
    //           idle-to-active for CPOL=0), shift on trailing edge.
    //   CPHA=1: shift on leading edge, sample on trailing edge.
    //
    // We track edge count (0..15 for 8 full cycles = 16 edges).
    // sclk_q toggles on each sclk_edge; we derive sample/shift events from
    // whether it's an odd or even edge count, combined with CPHA.
    // =========================================================================
    typedef enum logic [0:0] {
        SPI_IDLE   = 1'b0,
        SPI_ACTIVE = 1'b1
    } spi_state_e;

    spi_state_e  spi_state_q;
    logic        sclk_q;
    // tx_shift_q: MSB-first shift register.  spi_mosi_o is driven from
    // tx_shift_q[7] combinationally so every bit [7:0] is consumed on the
    // shift edge (left-shift exposes each successive bit at position [7]).
    logic [7:0]  tx_shift_q;
    logic [7:0]  rx_shift_q;
    logic [3:0]  edge_cnt_q;   // counts 0..15 (16 edges = 8 full cycles)
    // mosi_hold_q: registered copy of tx_shift_q[7] captured at each shift
    // edge.  Used as the loopback MISO source so that CPHA=1 modes sample the
    // bit that was valid BEFORE the shift (not the post-shift value).
    // For CPHA=0 the shift follows the sample, so the pre-shift value is also
    // what tx_shift_q[7] shows at sample time — both sources agree.
    logic        mosi_hold_q;

    assign spi_active = (spi_state_q == SPI_ACTIVE);

    // MOSI comes directly from the MSB of the shift register (combinational).
    // spi_sclk_o: idle at cpol when not active.
    assign spi_mosi_o = tx_shift_q[7];
    assign spi_sclk_o = spi_active ? sclk_q : cpol;
    assign spi_cs_n_o = regs_o[REG_SPI_CS_CTRL][0];

    // Determine sample and shift events based on CPOL/CPHA and edge direction.
    // edge_cnt_q[0]==0 → leading edge of each SCLK cycle (odd toggle index 0,2,4…)
    // edge_cnt_q[0]==1 → trailing edge
    // CPHA=0: sample leading (even edge_cnt), shift trailing (odd edge_cnt)
    // CPHA=1: shift leading (even edge_cnt), sample trailing (odd edge_cnt)
    wire sample_now = sclk_edge && spi_active &&
                      (cpha ? edge_cnt_q[0] : !edge_cnt_q[0]);
    wire shift_now  = sclk_edge && spi_active &&
                      (cpha ? !edge_cnt_q[0] : edge_cnt_q[0]);

    // MISO input mux for loopback:
    //   CPHA=0: sample on leading edge, shift on trailing. At sample time
    //           tx_shift_q[7] still holds the current bit (not yet shifted),
    //           so use tx_shift_q[7] directly.
    //   CPHA=1: shift on leading edge, sample on trailing. By sample time
    //           tx_shift_q[7] already shows the NEXT bit (post-shift).  Use
    //           mosi_hold_q which was captured just before the shift.
    wire miso_loopback = cpha ? mosi_hold_q : tx_shift_q[7];

    // spi_miso_i CDC synchroniser (bead claude_verilog_test-a2g, GH #95
    // cdc_snitch finding spi-miso-unsynchronised-sample). spi_miso_i is a
    // board-level asynchronous pin; sampling it directly into rx_shift_q /
    // rx_push_data was benign only by construction (SPI master mode drives
    // SCLK itself), not clean by inspection. Route it through the standard
    // 2-FF synchroniser instead of hand-rolling flops.
    //
    // Timing impact: cdc_2ff_sync adds 2 fabric-clock cycles of latency
    // between a spi_miso_i transition and its visibility to the shift
    // engine. This is transparent as long as the external slave's MISO has
    // already been stable for >= 2 cycles by the sample edge -- true for any
    // half-period (SPI_CLK_DIV+1) comfortably larger than 2, which is what
    // this module's own external-slave guidance already requires (see the
    // SPI_CLK_DIV >= 7 recommendation above). Loopback mode is unaffected:
    // miso_loopback never routes through spi_miso_i/spi_miso_sync_q.
    // KNOWN GAP: SPI_CLK_DIV == 0 (half-period = 1 clock) and SPI_CLK_DIV == 1
    // (half-period = 2 clocks) are NOT safe for a real external slave with
    // this synchroniser in place -- the 2-cycle sync latency meets or exceeds
    // the half-period, so the sampled bit can be stale by a full bit
    // position. Flagged, not silently retimed; see bead
    // claude_verilog_test-a2g close-out notes.
    logic spi_miso_sync_q;

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (2)
    ) u_spi_miso_sync (
        .clk_i   (clk),
        .rst_n_i (rst_n),
        .d_i     (spi_miso_i),
        .q_o     (spi_miso_sync_q)
    );

    wire miso_in = loopback ? miso_loopback : spi_miso_sync_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            spi_state_q  <= SPI_IDLE;
            sclk_q       <= 1'b0;
            tx_shift_q   <= 8'h0;
            rx_shift_q   <= 8'h0;
            edge_cnt_q   <= 4'h0;
            mosi_hold_q  <= 1'b0;
            tx_pop       <= 1'b0;
            rx_push      <= 1'b0;
            rx_push_data <= 8'h0;
        end else begin
            tx_pop  <= 1'b0;
            rx_push <= 1'b0;

            unique case (spi_state_q)
                SPI_IDLE: begin
                    sclk_q <= cpol;  // idle clock level
                    if (spi_enable && !tx_empty) begin
                        // Load TX byte MSB-first; bit[7] drives spi_mosi_o.
                        // Capture MSB into mosi_hold_q so CPHA=0 loopback
                        // samples the correct bit on the first leading edge.
                        tx_shift_q  <= tx_head;
                        mosi_hold_q <= tx_head[7];
                        tx_pop      <= 1'b1;
                        edge_cnt_q  <= 4'h0;
                        rx_shift_q  <= 8'h0;
                        spi_state_q <= SPI_ACTIVE;
                    end
                end

                SPI_ACTIVE: begin
                    if (sclk_edge) begin
                        // Toggle SCLK
                        sclk_q <= ~sclk_q;

                        // Sample MISO on sample edges; shift into LSB of rx register
                        if (sample_now)
                            rx_shift_q <= {rx_shift_q[6:0], miso_in};

                        // Shift TX register left on shift edges: next bit → [7].
                        // Update mosi_hold_q BEFORE the shift so it holds the
                        // value that was valid during this half-cycle (for
                        // loopback sampling on the following sample edge).
                        if (shift_now) begin
                            mosi_hold_q <= tx_shift_q[7];
                            tx_shift_q  <= {tx_shift_q[6:0], 1'b0};
                        end

                        edge_cnt_q <= edge_cnt_q + 4'h1;

                        // After 16 edges (8 full cycles), transfer complete.
                        // rx_shift_q holds the 8 received bits (MSB received first,
                        // so the final byte is {rx_shift_q[6:0], last_miso}).
                        if (edge_cnt_q == 4'd15) begin
                            spi_state_q <= SPI_IDLE;
                            rx_push     <= 1'b1;
                            // If the final edge is a sample edge the new bit is in
                            // miso_in (not yet written to rx_shift_q this cycle);
                            // otherwise rx_shift_q already holds all 8 bits.
                            if (sample_now)
                                rx_push_data <= {rx_shift_q[6:0], miso_in};
                            else
                                rx_push_data <= rx_shift_q;
                        end
                    end
                end

                default: spi_state_q <= SPI_IDLE;
            endcase
        end
    end

    // =========================================================================
    // STATUS flags (combinational)
    // =========================================================================
    wire spi_busy = spi_active;

    // =========================================================================
    // HW-writeback — combinational mirrors driven every cycle
    // =========================================================================
    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // SPI_RX: RX FIFO head (RO)
        hw_wen_i  [REG_SPI_RX] = 1'b1;
        hw_wdata_i[REG_SPI_RX] = {24'h0, rx_head};

        // SPI_STATUS: live FIFO and engine flags (RO)
        hw_wen_i  [REG_SPI_STATUS] = 1'b1;
        hw_wdata_i[REG_SPI_STATUS] = {
            26'h0,
            rx_full,     // [5] rx_full (RX FIFO full → overflow imminent)
            rx_valid,    // [4] rx_valid
            rx_empty,    // [3] rx_empty
            tx_empty,    // [2] tx_empty
            tx_full,     // [1] tx_full
            spi_busy     // [0] busy
        };
    end

    // =========================================================================
    // IRQ output
    // =========================================================================
    assign irq_o = irq_done_en & rx_valid;

endmodule : spi_controller

`default_nettype wire
