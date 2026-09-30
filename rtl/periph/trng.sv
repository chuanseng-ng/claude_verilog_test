// trng.sv
// Phase 6a-4 -- True-random-number-generator peripheral, APB4 slave (bead
// claude_verilog_test-f7vs.8, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-4 -- TRNG"). Written to
// the contract in tb/cocotb/soc/test_trng.py (its module docstring is authoritative; this header
// summarises it) and tb/models/trng_lfsr_model.py (bit-exact entropy datapath).
//
// Register map (word indices into the apb4_register_bank, N_REGS=8; 0x014-0x01C reserved, read 0):
//   0  TRNG_CTRL     RW  [0] enable, [1] IRQ enable, [5:2] FIFO threshold; [31:6] reserved
//   1  TRNG_STATUS   RO  [0] data ready (level>=1), [1] FIFO full (level==4),
//                        [2] health_fail (sticky), [3] INSECURE (constant 1, LFSR build)
//   2  TRNG_DATA     RO  head of the 4-deep FIFO; an APB READ pops it (read-snoop, SPI_RX idiom)
//   3  TRNG_SEED     RW  LFSR seed, reset 0xACE1_2345; sampled at the CTRL.EN 0->1 edge
//   4  TRNG_IRQ_CLR  WO  W1C against STATUS[2] (health_fail); reads 0
//
// Entropy source is an `ifdef sub-module, not a port: TRNG_RO_SKY130 selects
// trng_ro_sky130.sv (Sky130 ring oscillator), otherwise trng_lfsr_entropy.sv. Both share one
// port contract, so this file has zero top-level pins beyond the bus and irq_o, sits in every
// file list and PD flow, and needs no conditional instantiation in soc_top. Only the entropy-
// QUALITY claim is Sky130-exclusive, not the RTL.
//
// INSECURE: the default arm is a deterministic LFSR/von-Neumann generator, NOT cryptographic.
// STATUS[3] reads 1 in that build and cannot be cleared or masked; it is the one thing that
// distinguishes it from real entropy behind a register named TRNG. Under TRNG_RO_SKY130 it
// reads 0.
//
// FIFO / pop-on-read: 4 words deep. A read ACCESS phase (psel & penable & !pwrite) at TRNG_DATA
// pops one word. Reading an EMPTY FIFO returns 0 with pslverr 0, sets no status and does not
// underflow; STATUS.data_ready is the only validity indicator. Backpressure is a stall, not a
// drop: while the FIFO is full the entropy arm is not clocked, so the popped sequence is a
// function of the seed alone. Disabling retains the FIFO; the next CTRL.EN 0->1 edge starts a
// fresh session (LFSRs loaded from TRNG_SEED, FIFO/assembler/health run-length cleared).
//
// Health test: NIST SP 800-90B repetition-count test on the RAW (pre-debias) samples, cutoff
// C = 21 (H = 1 bit/sample, alpha = 2^-20); a run of 21 identical consecutive samples, counting
// the first, trips. A trip sets sticky STATUS[2], flushes the FIFO and HALTS production; a W1C
// of IRQ_CLR bit 2 clears it and resumes from the current LFSR state with the run length
// restarted. Adaptive-proportion is a documented non-goal. Seed 0 is not rescued: it trips.
//
// IRQ: irq_o = CTRL[1] & ((fifo_level >= max(CTRL[5:2],1)) | health_fail). LEVEL-HELD, never a
// pulse -- every IRQ source crosses core_clk -> cpu_core_clk through a plain 2-FF cdc_2ff_sync in
// soc_top.sv, which can miss a pulse. Threshold 0 behaves as 1; 5..15 never fire on the level.
//   health_fail next = (health_fail & ~clr) | trip   -- SET WINS over a same-cycle clear.
//
// RO-register hazard (bead 6o8w): apb4_register_bank lets a SW write win over a same-cycle HW
// write even when WMASK == 0 (it writes the old value back). STATUS and DATA are HW-owned every
// cycle, so a stray APB store would swallow a FIFO update or a health set. Stores to those two
// words are therefore presented to the bank as reads (bank_pwrite_w), as in watchdog_timer.sv.
//
// Reset: synchronous, active-low throughout (no `negedge rst_n`), matching the other periph/.
// No CDC: single clock domain (core_clk), no asynchronous inputs.
//
// APB4 interface (ARM IHI0024C): clk/rst_n map to pclk/presetn. ADDR_W = 12 (byte address, [1:0]
// unused). Zero wait states (pready is the bank's constant 1). Writes commit on the ACCESS phase
// (psel & penable); the DATA pop and IRQ_CLR snoops decode that same phase.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module trng
#(
    parameter int unsigned ADDR_W = 12    // APB4 local address width
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // APB4 slave -- control/status registers
    // SETUP  phase: psel=1, penable=0 (one cycle).
    // ACCESS phase: psel=1, penable=1; transfer complete when pready=1.
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

    // Interrupt -- level-held, never a pulse
    output logic irq_o
);

    if (ADDR_W < 5 || ADDR_W > 32) begin : g_addr_w_check
        $fatal(1, "trng: ADDR_W (%0d) must be in [5, 32]", ADDR_W);
    end

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_TRNG_CTRL    = 0;
    localparam int unsigned REG_TRNG_STATUS  = 1;
    localparam int unsigned REG_TRNG_DATA    = 2;
    localparam int unsigned REG_TRNG_SEED    = 3;
    localparam int unsigned REG_TRNG_IRQ_CLR = 4;
    localparam int unsigned N_REGS           = 8;

    localparam int unsigned FIFO_DEPTH = 4;
    localparam int unsigned RC_CUTOFF  = 21;   // NIST SP 800-90B RCT cutoff, H=1, alpha=2^-20

    localparam logic [31:0] SEED_RESET = 32'hACE1_2345;

`ifdef TRNG_RO_SKY130
    localparam logic INSECURE = 1'b0;   // real (ring-oscillator) entropy
`else
    localparam logic INSECURE = 1'b1;   // deterministic LFSR: advertise it
`endif

    // Word address width (mirrors apb4_register_bank's own WORDW).
    localparam int unsigned WORDW = ADDR_W - 2;

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,                    // 0 TRNG_CTRL
        32'(INSECURE) << 3,            // 1 TRNG_STATUS   RO (HW-written)
        32'h0000_0000,                    // 2 TRNG_DATA     RO (HW-written)
        SEED_RESET,                       // 3 TRNG_SEED     RW
        32'h0000_0000,                    // 4 TRNG_IRQ_CLR  WO (snoop-only, reads 0)
        32'h0000_0000,                    // 5 reserved
        32'h0000_0000,                    // 6 reserved
        32'h0000_0000                     // 7 reserved
    };

    // WMASK: RO / WO / reserved words get 32'h0 (drop writes, read back reset value).
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_003F,  // 0 TRNG_CTRL   [5:0] defined
        32'h0000_0000,  // 1 TRNG_STATUS
        32'h0000_0000,  // 2 TRNG_DATA
        32'hFFFF_FFFF,  // 3 TRNG_SEED
        32'h0000_0000,  // 4 TRNG_IRQ_CLR
        32'h0000_0000,  // 5
        32'h0000_0000,  // 6
        32'h0000_0000   // 7
    };

    logic [31:0] regs_o    [N_REGS];
    logic        hw_wen_i  [N_REGS];
    logic [31:0] hw_wdata_i[N_REGS];

    // -------------------------------------------------------------------------
    // APB address decode (zero-extended to 32 b before comparing -- GH #87-safe idiom).
    // -------------------------------------------------------------------------
    logic [WORDW-1:0] addr_word_w;
    assign addr_word_w = paddr[ADDR_W-1:2];

    logic access_w;
    assign access_w = psel & penable;  // pready is a constant 1 from the bank

    logic is_status_addr_w, is_data_addr_w, is_irq_clr_addr_w;
    assign is_status_addr_w  = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_TRNG_STATUS));
    assign is_data_addr_w    = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_TRNG_DATA));
    assign is_irq_clr_addr_w = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_TRNG_IRQ_CLR));

    // Stores to the two HW-owned words are shown to the bank as reads (bead 6o8w, see header).
    logic bank_pwrite_w;
    assign bank_pwrite_w = pwrite & ~(is_status_addr_w | is_data_addr_w);

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
        .pwrite     (bank_pwrite_w),
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
    // Register views
    // =========================================================================
    logic        en_w, ie_w;
    logic [3:0]  thr_w;
    logic [31:0] seed_w;
    logic        health_q_w;   // STATUS[2], the sticky health_fail state (lives in the bank)

    assign en_w       = regs_o[REG_TRNG_CTRL][0];
    assign ie_w       = regs_o[REG_TRNG_CTRL][1];
    assign thr_w      = regs_o[REG_TRNG_CTRL][5:2];
    assign seed_w     = regs_o[REG_TRNG_SEED];
    assign health_q_w = regs_o[REG_TRNG_STATUS][2];

    // Unused register bits (reserved CTRL/STATUS/IRQ_CLR words are storage-free by WMASK; the
    // HW-owned words are read through the bank).
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_regs_w;
    assign unused_regs_w = ^{regs_o[REG_TRNG_CTRL][31:6], regs_o[REG_TRNG_STATUS][31:3],
                             regs_o[REG_TRNG_STATUS][1:0], regs_o[REG_TRNG_DATA],
                             regs_o[REG_TRNG_IRQ_CLR], regs_o[5], regs_o[6], regs_o[7]};
    /* verilator lint_on  UNUSEDSIGNAL */

    // =========================================================================
    // Session control
    // =========================================================================
    logic en_q;             // CTRL[0] one cycle ago: enable-edge detect
    logic load_w;           // session start: first edge after the CTRL.EN 0->1 commit
    assign load_w = en_w & ~en_q;

    always_ff @(posedge clk) begin
        if (!rst_n) en_q <= 1'b0;
        else        en_q <= en_w;
    end

    // =========================================================================
    // FIFO state (shift register, head at [0]; entries above `level` are always zero)
    // =========================================================================
    logic [31:0] fifo_q      [FIFO_DEPTH];
    logic [31:0] fifo_next_w [FIFO_DEPTH];
    logic [2:0]  level_q, level_next_w;

    logic fifo_full_w;
    assign fifo_full_w = (level_q == 3'(FIFO_DEPTH));

    // Entropy arm is clocked only while enabled, past the session-load edge, healthy and not
    // backpressured (stall, not drop).
    logic run_w;
    assign run_w = en_w & en_q & ~health_q_w & ~fifo_full_w;

    logic        sample_valid_w, sample_w, word_valid_w;
    logic [31:0] word_w;
    logic        trip_w;

`ifdef TRNG_RO_SKY130
    trng_ro_sky130 u_entropy (
`else
    trng_lfsr_entropy u_entropy (
`endif
        .clk            (clk),
        .rst_n          (rst_n),
        .load_i         (load_w),
        .seed_i         (seed_w),
        .flush_i        (trip_w),
        .run_i          (run_w),
        .sample_valid_o (sample_valid_w),
        .sample_o       (sample_w),
        .word_valid_o   (word_valid_w),
        .word_o         (word_w)
    );

    // =========================================================================
    // Repetition-count health test (raw samples)
    // =========================================================================
    logic       run_bit_q;
    logic [4:0] run_len_q, run_len_next_w;

    always_comb begin
        if (run_len_q != 5'd0 && sample_w == run_bit_q) run_len_next_w = run_len_q + 5'd1;
        else                                             run_len_next_w = 5'd1;
    end

    assign trip_w = sample_valid_w & (run_len_next_w >= 5'(RC_CUTOFF));

    always_ff @(posedge clk) begin
        if (!rst_n || load_w || trip_w) begin
            run_bit_q <= 1'b0;
            run_len_q <= 5'd0;
        end else if (sample_valid_w) begin
            run_bit_q <= sample_w;
            run_len_q <= run_len_next_w;
        end
    end

    // =========================================================================
    // TRNG_IRQ_CLR write-snoop -- one-cycle clear of health_fail (honours pstrb)
    // =========================================================================
    function automatic logic [31:0] strb_expand(input logic [3:0] strb);
        for (int unsigned b = 0; b < 4; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    // The expanded strobe MUST land in a named net before being sliced. A part-select applied
    // directly to a function-call result is legal SystemVerilog and accepted by Verilator but
    // NOT legal Verilog-2005: sv2v passes it through verbatim and yosys rejects the generated
    // file. See pwm_controller.sv (fixed in 2c5f351) for the full story.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] strb_mask_w;
    /* verilator lint_on  UNUSEDSIGNAL */
    assign strb_mask_w = strb_expand(pstrb);

    logic clr_health_w;
    assign clr_health_w = access_w & pwrite & is_irq_clr_addr_w & pwdata[2] & strb_mask_w[2];

    // health_fail next-state: sticky, SET WINS over a same-cycle clear.
    logic health_next_w;
    assign health_next_w = (health_q_w & ~clr_health_w) | trip_w;

    // =========================================================================
    // FIFO next-state: flush > (pop, push). Pop = read ACCESS at TRNG_DATA on a non-empty FIFO.
    // =========================================================================
    logic pop_w, flush_w, push_w;
    assign pop_w   = access_w & ~pwrite & is_data_addr_w & (level_q != 3'd0);
    assign flush_w = load_w | trip_w;
    assign push_w  = word_valid_w & ~flush_w;

    logic [2:0] wr_idx_w;   // slot a pushed word lands in, after the pop shift
    assign wr_idx_w = pop_w ? (level_q - 3'd1) : level_q;

    always_comb begin
        for (int unsigned i = 0; i < FIFO_DEPTH; i++) begin
            if (pop_w) fifo_next_w[i] = (i + 1 < FIFO_DEPTH) ? fifo_q[(i + 1) % FIFO_DEPTH] : 32'h0;
            else       fifo_next_w[i] = fifo_q[i];
            if (push_w && wr_idx_w == 3'(i)) fifo_next_w[i] = word_w;
            if (flush_w)                     fifo_next_w[i] = 32'h0;
        end
        level_next_w = level_q;
        if (flush_w)                level_next_w = 3'd0;
        else if (push_w && !pop_w)  level_next_w = level_q + 3'd1;
        else if (pop_w && !push_w)  level_next_w = level_q - 3'd1;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            level_q <= 3'd0;
            for (int unsigned i = 0; i < FIFO_DEPTH; i++) fifo_q[i] <= 32'h0;
        end else begin
            level_q <= level_next_w;
            for (int unsigned i = 0; i < FIFO_DEPTH; i++) fifo_q[i] <= fifo_next_w[i];
        end
    end

    // =========================================================================
    // HW-writeback -- combinational mirror of the NEXT state, driven every cycle
    // =========================================================================
    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // TRNG_STATUS: {INSECURE, health_fail, full, ready}. RO -- HW owns it.
        hw_wen_i  [REG_TRNG_STATUS] = 1'b1;
        hw_wdata_i[REG_TRNG_STATUS] = {28'h0, INSECURE, health_next_w,
                                       level_next_w == 3'(FIFO_DEPTH), level_next_w != 3'd0};

        // TRNG_DATA: FIFO head (0 when empty -- entries above `level` are zero by construction).
        hw_wen_i  [REG_TRNG_DATA] = 1'b1;
        hw_wdata_i[REG_TRNG_DATA] = fifo_next_w[0];
    end

    // =========================================================================
    // Interrupt -- level-held (see header). Threshold 0 behaves as 1.
    // =========================================================================
    logic [3:0] eff_thr_w;
    assign eff_thr_w = (thr_w == 4'd0) ? 4'd1 : thr_w;

    logic lvl_hit_w;
    assign lvl_hit_w = ({1'b0, level_q} >= eff_thr_w);

    assign irq_o = ie_w & (lvl_hit_w | health_q_w);

endmodule : trng
