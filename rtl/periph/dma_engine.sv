// dma_engine.sv
// Phase 5 (M5) — Descriptor-queue DMA engine.
//
// AXI4 burst master for data movement + AXI4-Lite control slave + IRQ output.
//
// Register map (word indices into the axi_lite_register_bank):
//   0  SRC_ADDR    RW  source byte address
//   1  DST_ADDR    RW  destination byte address
//   2  LENGTH      RW  transfer length in bytes (must be word-multiple)
//   3  CTRL        RW  [0]=start(pulse/edge), [1]=irq_en, [2]=soft_reset(pulse/edge)
//   4  STATUS      RO  [0]=busy, [1]=done(sticky), [2]=error(sticky),
//                      [3]=q_full, [4]=q_empty, [10:8]=q_count
//   5  IRQ_STATUS  RO  [0]=done_irq(sticky), [1]=err_irq(sticky)
//   6  ERR_INFO    RO  [1:0]=last_axi_resp, [2]=err_on_read
//   7  RSVD        RO  reserved, reads 0
//
// CTRL.start and CTRL.soft_reset are edge-detected (0→1); the bit is
// HW-cleared immediately after consume to prevent double-enqueue.
// done/error sticky bits cleared only by soft_reset.
// NOTE: "true per-bit W1C deferred" — the register bank's WMASK prevents SW
// from directly clearing STATUS/IRQ_STATUS; only soft_reset clears them.
//
// Burst-split rule: each burst is limited to min(words_rem, MAX_BURST_BEATS,
// src_to_4k_words, dst_to_4k_words) to respect the AXI4 4 KB boundary rule
// on both source and destination addresses simultaneously.
//
// Flat per-channel AXI ports (no SV interfaces) per Phase 5 RTL convention.
// Lint target: verilator -Wall 0 errors 0 warnings.

module dma_engine
    import axi_pkg::*;
#(
    parameter int unsigned QDEPTH         = 4,    // descriptor FIFO depth
    parameter int unsigned ADDR_W         = 12,   // AXI-Lite local address width
    parameter int unsigned MAX_BURST_BEATS = 256  // max AXI4 burst length in beats
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // AXI4-Lite slave — control/status registers
    // Port names match axi_lite_register_bank.sv exactly so the sub-module
    // connection is positional-free.
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
    // AXI4 master — data movement (burst-capable)
    // =========================================================================
    // Write address channel
    output logic [AXI_ID_WIDTH-1:0]  m_awid,
    output logic [31:0]              m_awaddr,
    output logic [AXI_LEN_WIDTH-1:0] m_awlen,
    output logic [2:0]               m_awsize,
    output logic [1:0]               m_awburst,
    output logic                     m_awvalid,
    input  logic                     m_awready,
    // Write data channel
    output logic [31:0]              m_wdata,
    output logic [3:0]               m_wstrb,
    output logic                     m_wlast,
    output logic                     m_wvalid,
    input  logic                     m_wready,
    // Write response channel
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [AXI_ID_WIDTH-1:0]  m_bid,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [1:0]               m_bresp,
    input  logic                     m_bvalid,
    output logic                     m_bready,
    // Read address channel
    output logic [AXI_ID_WIDTH-1:0]  m_arid,
    output logic [31:0]              m_araddr,
    output logic [AXI_LEN_WIDTH-1:0] m_arlen,
    output logic [2:0]               m_arsize,
    output logic [1:0]               m_arburst,
    output logic                     m_arvalid,
    input  logic                     m_arready,
    // Read data channel
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [AXI_ID_WIDTH-1:0]  m_rid,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [31:0]              m_rdata,
    input  logic [1:0]               m_rresp,
    input  logic                     m_rlast,
    input  logic                     m_rvalid,
    output logic                     m_rready,

    // =========================================================================
    // Interrupt output
    // =========================================================================
    output logic irq_o
);

    // =========================================================================
    // Local constants
    // =========================================================================
    // AXI master ID is always 0 (single-channel DMA)
    localparam logic [AXI_ID_WIDTH-1:0] DMA_ID    = '0;
    // AXI master always uses 4-byte beats, INCR bursts
    localparam logic [2:0]              DMA_SIZE  = AXI_SIZE_4B;
    localparam logic [1:0]              DMA_BURST = AXI_BURST_INCR;

    // Register indices
    localparam int unsigned REG_SRC_ADDR   = 0;
    localparam int unsigned REG_DST_ADDR   = 1;
    localparam int unsigned REG_LENGTH     = 2;
    localparam int unsigned REG_CTRL       = 3;
    localparam int unsigned REG_STATUS     = 4;
    localparam int unsigned REG_IRQ_STATUS = 5;
    localparam int unsigned REG_ERR_INFO   = 6;
    localparam int unsigned REG_RSVD       = 7;
    localparam int unsigned N_REGS         = 8;

    // CTRL bit positions
    localparam int unsigned CTRL_START_BIT  = 0;
    localparam int unsigned CTRL_IRQEN_BIT  = 1;
    localparam int unsigned CTRL_SRST_BIT   = 2;

    // =========================================================================
    // Register bank instantiation
    // =========================================================================
    // RESET_VAL: all zero; q_empty=1 comes from STATUS mirror
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 SRC_ADDR
        32'h0000_0000,  // 1 DST_ADDR
        32'h0000_0000,  // 2 LENGTH
        32'h0000_0000,  // 3 CTRL
        32'h0000_0010,  // 4 STATUS (q_empty=1 at reset)
        32'h0000_0000,  // 5 IRQ_STATUS
        32'h0000_0000,  // 6 ERR_INFO
        32'h0000_0000   // 7 RSVD
    };

    // WMASK: only CTRL and the two address/length regs are SW-writable
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'hFFFF_FFFF,  // 0 SRC_ADDR
        32'hFFFF_FFFF,  // 1 DST_ADDR
        32'hFFFF_FFFF,  // 2 LENGTH
        32'h0000_0007,  // 3 CTRL  [2:0] only
        32'h0000_0000,  // 4 STATUS  RO
        32'h0000_0000,  // 5 IRQ_STATUS  RO
        32'h0000_0000,  // 6 ERR_INFO  RO
        32'h0000_0000   // 7 RSVD  RO
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
    // Control register readback helpers
    // =========================================================================
    logic [31:0] ctrl_reg;
    logic [31:0] src_addr_reg;
    logic [31:0] dst_addr_reg;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] length_reg;   // [1:0] intentionally discarded (word-aligned input)
    /* verilator lint_on  UNUSEDSIGNAL */
    logic        irq_en;

    assign ctrl_reg     = regs_o[REG_CTRL];
    assign src_addr_reg = regs_o[REG_SRC_ADDR];
    assign dst_addr_reg = regs_o[REG_DST_ADDR];
    assign length_reg   = regs_o[REG_LENGTH];
    assign irq_en       = ctrl_reg[CTRL_IRQEN_BIT];

    // =========================================================================
    // CTRL edge detection — start / soft_reset (0→1 rising edge)
    // =========================================================================
    logic ctrl_prev_start_q;
    logic ctrl_prev_srst_q;
    logic start_pulse;
    logic srst_pulse;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            ctrl_prev_start_q <= 1'b0;
            ctrl_prev_srst_q  <= 1'b0;
        end else begin
            ctrl_prev_start_q <= ctrl_reg[CTRL_START_BIT];
            ctrl_prev_srst_q  <= ctrl_reg[CTRL_SRST_BIT];
        end
    end

    assign start_pulse = ctrl_reg[CTRL_START_BIT] & ~ctrl_prev_start_q;
    assign srst_pulse  = ctrl_reg[CTRL_SRST_BIT]  & ~ctrl_prev_srst_q;

    // =========================================================================
    // Descriptor FIFO
    // =========================================================================
    // Each entry: {src[31:0], dst[31:0], len_words[31:0]}
    typedef struct packed {
        logic [31:0] src;
        logic [31:0] dst;
        logic [31:0] len_words;  // LENGTH >> 2
    } desc_t;

    desc_t                           q_mem [QDEPTH];
    logic [$clog2(QDEPTH)-1:0]       q_head, q_tail;
    logic [$clog2(QDEPTH+1)-1:0]     q_count;
    logic                            q_full, q_empty;

    assign q_full  = (q_count == $clog2(QDEPTH+1)'(QDEPTH));
    assign q_empty = (q_count == '0);

    // =========================================================================
    // Burst-split FSM states
    // =========================================================================
    typedef enum logic [3:0] {
        S_IDLE      = 4'd0,
        S_CALC      = 4'd1,
        S_AR        = 4'd2,
        S_R         = 4'd3,
        S_AW        = 4'd4,
        S_W         = 4'd5,
        S_B         = 4'd6,
        S_DESC_DONE = 4'd7,
        S_ERR       = 4'd8
    } dma_state_t;

    dma_state_t state_q;

    // =========================================================================
    // Datapath registers
    // =========================================================================
    logic [31:0]  src_q;          // current burst source address
    logic [31:0]  dst_q;          // current burst destination address
    logic [31:0]  words_rem_q;    // words remaining in current descriptor
    logic [8:0]   beats_q;        // beats in current burst (1..MAX_BURST_BEATS)
    logic [8:0]   rd_idx_q;       // read data beat index into linebuf
    logic [8:0]   wr_idx_q;       // write data beat index from linebuf
    logic [1:0]   last_resp_q;    // last AXI response captured
    logic         err_on_read_q;  // 1=error occurred on read, 0=on write
    logic         done_sticky_q;  // STATUS.done sticky
    logic         err_sticky_q;   // STATUS.error sticky
    logic         done_pending_q; // IRQ_STATUS.done_irq
    logic         err_pending_q;  // IRQ_STATUS.err_irq
    logic         halted_q;       // halt until soft_reset after S_ERR

    // =========================================================================
    // Line buffer: MAX_BURST_BEATS words
    // =========================================================================
    // Unpacked to avoid memory blowup in synthesis
    logic [31:0] linebuf [MAX_BURST_BEATS];

    // =========================================================================
    // Burst beat calculation (combinational)
    // Limit: min(words_rem, MAX_BURST_BEATS, src_to_4k, dst_to_4k)
    // 4K boundary rule: words until next 4 KB page = (4096 - (addr & 12'hFFF)) >> 2
    // =========================================================================
    logic [31:0] src_to_4k;   // words from src_q to its 4K boundary
    logic [31:0] dst_to_4k;   // words from dst_q to its 4K boundary
    logic [31:0] beats_raw;   // uncapped
    logic [8:0]  beats_next;  // capped to [1..MAX_BURST_BEATS], 9-bit

    // (4096 - (addr & 12'hFFF)) / 4  =>  (13'h1000 - {1'b0,addr[11:0]}) >> 2
    // 4096 needs 13 bits; use 13-bit intermediate, then zero-extend to 32.
    // When addr is perfectly 4K-aligned, addr[11:0]=0 → result=1024.
    // Capped to MAX_BURST_BEATS anyway.
    assign src_to_4k  = {19'h0, ((13'h1000 - {1'b0, src_q[11:0]}) >> 2)};
    assign dst_to_4k  = {19'h0, ((13'h1000 - {1'b0, dst_q[11:0]}) >> 2)};

    // min4: use intermediate comparisons to avoid deep chain
    function automatic logic [31:0] min2(input logic [31:0] a, input logic [31:0] b);
        return (a < b) ? a : b;
    endfunction

    always_comb begin
        beats_raw  = min2(min2(words_rem_q, 32'(MAX_BURST_BEATS)),
                          min2(src_to_4k,   dst_to_4k));
        if (beats_raw == 32'h0) beats_raw = 32'h1; // guard: never issue 0-beat burst
        // Saturate to 9 bits (MAX_BURST_BEATS can be up to 256 which is 9 bits wide)
        if (beats_raw > 32'(MAX_BURST_BEATS))
            beats_next = 9'(MAX_BURST_BEATS);
        else
            beats_next = 9'(beats_raw);
    end

    // =========================================================================
    // AXI4 output mux — combinational, keyed on state (coalescer style)
    // =========================================================================
    always_comb begin
        // Defaults: all outputs de-asserted
        m_awid    = DMA_ID;
        m_awaddr  = src_q;      // overridden below
        m_awlen   = '0;
        m_awsize  = DMA_SIZE;
        m_awburst = DMA_BURST;
        m_awvalid = 1'b0;

        m_wdata   = '0;
        m_wstrb   = 4'hF;
        m_wlast   = 1'b0;
        m_wvalid  = 1'b0;

        m_bready  = 1'b0;

        m_arid    = DMA_ID;
        m_araddr  = src_q;
        m_arlen   = '0;
        m_arsize  = DMA_SIZE;
        m_arburst = DMA_BURST;
        m_arvalid = 1'b0;

        m_rready  = 1'b0;

        unique case (state_q)
            S_AR: begin
                m_araddr  = src_q;
                m_arlen   = AXI_LEN_WIDTH'(beats_q - 9'h1);
                m_arvalid = 1'b1;
            end
            S_R: begin
                m_rready = 1'b1;
            end
            S_AW: begin
                m_awaddr  = dst_q;
                m_awlen   = AXI_LEN_WIDTH'(beats_q - 9'h1);
                m_awvalid = 1'b1;
            end
            S_W: begin
                m_wdata  = linebuf[8'(wr_idx_q)];
                m_wlast  = (wr_idx_q == 9'(beats_q - 9'h1));
                m_wvalid = 1'b1;
            end
            S_B: begin
                m_bready = 1'b1;
            end
            // S_IDLE, S_CALC, S_DESC_DONE, S_ERR — all AXI outputs stay at defaults
            default: ;
        endcase
    end

    // =========================================================================
    // FSM sequencer
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q        <= S_IDLE;
            src_q          <= '0;
            dst_q          <= '0;
            words_rem_q    <= '0;
            beats_q        <= '0;
            rd_idx_q       <= '0;
            wr_idx_q       <= '0;
            last_resp_q    <= '0;
            err_on_read_q  <= 1'b0;
            done_sticky_q  <= 1'b0;
            err_sticky_q   <= 1'b0;
            done_pending_q <= 1'b0;
            err_pending_q  <= 1'b0;
            halted_q       <= 1'b0;
            q_head         <= '0;
            q_tail         <= '0;
            q_count        <= '0;
        end else begin

            // ------------------------------------------------------------------
            // CTRL edge: enqueue descriptor on start_pulse (if not full / halted)
            // ------------------------------------------------------------------
            if (start_pulse && !q_full && !halted_q) begin
                q_mem[q_tail].src       <= src_addr_reg;
                q_mem[q_tail].dst       <= dst_addr_reg;
                q_mem[q_tail].len_words <= {2'b00, length_reg[31:2]};
                q_tail                  <= q_tail + $clog2(QDEPTH)'(1);
                q_count                 <= q_count + $clog2(QDEPTH+1)'(1);
            end

            // ------------------------------------------------------------------
            // soft_reset: clear sticky bits and halt state
            // ------------------------------------------------------------------
            if (srst_pulse) begin
                done_sticky_q  <= 1'b0;
                err_sticky_q   <= 1'b0;
                done_pending_q <= 1'b0;
                err_pending_q  <= 1'b0;
                halted_q       <= 1'b0;
                // Flush the queue
                q_head  <= '0;
                q_tail  <= '0;
                q_count <= '0;
                // Return FSM to idle (safe even if mid-transfer — behavioral model)
                state_q <= S_IDLE;
            end else begin

                // Main FSM (only advances when not being soft-reset this cycle)
                unique case (state_q)

                    // --------------------------------------------------------
                    S_IDLE: begin
                        if (!q_empty && !halted_q) begin
                            // Pop descriptor
                            src_q       <= q_mem[q_head].src;
                            dst_q       <= q_mem[q_head].dst;
                            words_rem_q <= q_mem[q_head].len_words;
                            q_head      <= q_head + $clog2(QDEPTH)'(1);
                            q_count     <= q_count - $clog2(QDEPTH+1)'(1);
                            state_q     <= S_CALC;
                        end
                    end

                    // --------------------------------------------------------
                    S_CALC: begin
                        beats_q  <= beats_next;
                        rd_idx_q <= '0;
                        wr_idx_q <= '0;
                        state_q  <= S_AR;
                    end

                    // --------------------------------------------------------
                    S_AR: begin
                        if (m_arready) state_q <= S_R;
                    end

                    // --------------------------------------------------------
                    S_R: begin
                        if (m_rvalid) begin
                            linebuf[8'(rd_idx_q)] <= m_rdata;
                            rd_idx_q          <= rd_idx_q + 9'h1;
                            last_resp_q       <= m_rresp;
                            if (m_rresp != AXI_RESP_OKAY) begin
                                err_on_read_q <= 1'b1;
                                state_q       <= S_ERR;
                            end else if (m_rlast) begin
                                state_q <= S_AW;
                            end
                        end
                    end

                    // --------------------------------------------------------
                    S_AW: begin
                        if (m_awready) begin
                            wr_idx_q <= '0;
                            state_q  <= S_W;
                        end
                    end

                    // --------------------------------------------------------
                    S_W: begin
                        if (m_wready) begin
                            wr_idx_q <= wr_idx_q + 9'h1;
                            if (wr_idx_q == 9'(beats_q - 9'h1)) begin
                                state_q <= S_B;
                            end
                        end
                    end

                    // --------------------------------------------------------
                    S_B: begin
                        if (m_bvalid) begin
                            last_resp_q <= m_bresp;
                            if (m_bresp != AXI_RESP_OKAY) begin
                                err_on_read_q <= 1'b0;
                                state_q       <= S_ERR;
                            end else begin
                                // Advance addresses (beats_q in words → *4 for bytes)
                                src_q       <= src_q + (32'(beats_q) << 2);
                                dst_q       <= dst_q + (32'(beats_q) << 2);
                                words_rem_q <= words_rem_q - 32'(beats_q);
                                if (words_rem_q == 32'(beats_q)) begin
                                    // words_rem - beats == 0 → descriptor complete
                                    state_q <= S_DESC_DONE;
                                end else begin
                                    state_q <= S_CALC;
                                end
                            end
                        end
                    end

                    // --------------------------------------------------------
                    S_DESC_DONE: begin
                        done_sticky_q  <= 1'b1;
                        done_pending_q <= 1'b1;
                        state_q        <= S_IDLE;
                    end

                    // --------------------------------------------------------
                    S_ERR: begin
                        err_sticky_q  <= 1'b1;
                        err_pending_q <= 1'b1;
                        halted_q      <= 1'b1;
                        state_q       <= S_IDLE;
                    end

                    // --------------------------------------------------------
                    default: state_q <= S_IDLE;

                endcase
            end // !srst_pulse

            // ------------------------------------------------------------------
            // HW-clear start/soft_reset bits in CTRL immediately after edge
            // (clear-after-consume prevents double-enqueue / double-reset)
            // ------------------------------------------------------------------
            hw_wen_i  [REG_CTRL]   <= 1'b0;
            hw_wdata_i[REG_CTRL]   <= '0;
            if (start_pulse) begin
                hw_wen_i  [REG_CTRL] <= 1'b1;
                hw_wdata_i[REG_CTRL] <= ctrl_reg & ~32'h1;  // clear bit0
            end
            if (srst_pulse) begin
                hw_wen_i  [REG_CTRL] <= 1'b1;
                hw_wdata_i[REG_CTRL] <= 32'h0;  // clear all CTRL bits
            end

        end // !rst_n
    end

    // =========================================================================
    // STATUS / IRQ_STATUS / ERR_INFO — combinational mirrors driven every cycle
    // =========================================================================
    logic busy;
    assign busy = (state_q != S_IDLE) || !q_empty;

    // STATUS[10:8] = q_count (3 bits); max QDEPTH=4 so 3 bits is sufficient for
    // default param. Use a 3-bit slice to keep the field consistent.
    always_comb begin
        // STATUS
        hw_wen_i  [REG_STATUS] = 1'b1;
        hw_wdata_i[REG_STATUS] = {
            21'h0,
            q_count[2:0],       // [10:8] q_count (3-bit slice)
            3'h0,               // [7:5]  unused
            q_empty,            // [4]
            q_full,             // [3]
            err_sticky_q,       // [2]
            done_sticky_q,      // [1]
            busy                // [0]
        };

        // IRQ_STATUS
        hw_wen_i  [REG_IRQ_STATUS] = 1'b1;
        hw_wdata_i[REG_IRQ_STATUS] = {30'h0, err_pending_q, done_pending_q};

        // ERR_INFO
        hw_wen_i  [REG_ERR_INFO] = 1'b1;
        hw_wdata_i[REG_ERR_INFO] = {29'h0, err_on_read_q, last_resp_q};

        // Registers not driven by HW (SRC_ADDR, DST_ADDR, LENGTH, RSVD, CTRL default)
        hw_wen_i  [REG_SRC_ADDR] = 1'b0;
        hw_wdata_i[REG_SRC_ADDR] = '0;
        hw_wen_i  [REG_DST_ADDR] = 1'b0;
        hw_wdata_i[REG_DST_ADDR] = '0;
        hw_wen_i  [REG_LENGTH]   = 1'b0;
        hw_wdata_i[REG_LENGTH]   = '0;
        hw_wen_i  [REG_RSVD]     = 1'b0;
        hw_wdata_i[REG_RSVD]     = '0;
    end

    // =========================================================================
    // IRQ output
    // =========================================================================
    assign irq_o = irq_en & (done_pending_q | err_pending_q);

endmodule : dma_engine

