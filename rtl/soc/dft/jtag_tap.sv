// jtag_tap.sv
// DFT Stage 1b (bead claude_verilog_test-j41m.3, GH #244).
//
// IEEE 1149.1-style TAP controller, instruction register and test-data
// registers, entirely in the TCK domain. Specification:
// docs/design/DFT_ARCHITECTURE.md section 15 (instruction map 15.3, output
// timing 15.2, deviations 15.6). Compliant minus the boundary register: EXTEST
// and SAMPLE/PRELOAD are not implemented and decode to BYPASS (no pad ring).
//
// Registers (IR = 4 bits, capture value 4'b0001):
//   4'h1 IDCODE      32 bit, 32'h15C0_1001 (version 1, part 16'h5C01, manufacturer
//                    11'h000 = NOT a JEDEC id, on purpose), reset default
//   4'h3 SCAN_SEL     3 bit [0] PARALLEL, [2:1] CHAIN_GRP; update register, reset 0
//   4'h4 SCAN         1 bit stub; selecting it is the ONLY way into TAP scan mode
//   4'h5 SCAN_RST     1 bit level, update register, reset 0; effective in SCAN only
//   4'hF BYPASS       1 bit
//   4'h6 MBIST_CTRL   29 bit update register (docs/design/DFT_ARCHITECTURE.md section 16.5), reset 0;
//                    Capture-DR reads it back. Update-DR (and entry to Test-Logic-Reset, with the default
//                    word 0) raises mbist_wr_o for exactly one TCK rising edge: the write strobe of the
//                    control-word crossing (mbist_xing).
//   4'h7 MBIST_STATUS 140 bit read-only: [0] sticky control-word overflow, [139:1] mbist_status_i
//   everything else (EXTEST 0, SAMPLE 2, reserved, unknown) -> BYPASS
//
// Clocking and reset
//   * Everything is clocked by tck_i only; nothing here sees a functional clock.
//   * trst_ni asserts every TAP flop asynchronously; its release goes through one
//     cdc_reset_sync in the TCK domain (scanmode_i=0, scan_rst_ni=1: the TAP is
//     reset by nothing else, not by rst_n_i, a PLL, the PMU or the WDT). Five TCK
//     rising edges with TMS=1 also reach Test-Logic-Reset from any state.
//   * FSM state, IR shift register and the DR shift registers are rising-edge
//     flops. The IR update register, the DR update registers, TDO and EVERY
//     SoC-facing output are FALLING-edge flops: their D input is a function of
//     the rising-edge flops (stable for half a TCK period) and of the next-state
//     values ir_d / scan_sel_d / scan_rst_d computed in the same falling-edge
//     step, so no output is a combinational decode of an update register and none
//     can glitch. They feed asynchronous resets, clock-mux selects and a
//     clock-gate latch downstream.
//   * Test-Logic-Reset returns IR to IDCODE and every update register and output
//     to its default at the next falling edge.
//
// What selecting SCAN does (see dft_ctrl for the combiner):
//   tap_scan = (IR == SCAN); serial = tap_scan & ~PARALLEL; parallel = tap_scan & PARALLEL.
//   scan_mode_o     = tap_scan
//   serial_o        = tap_scan & ~SCAN_SEL[0]  (TAP drives scan_en and the test clock)
//   parallel_o      = tap_scan &  SCAN_SEL[0]  (pins drive scan_en/scan_clk/scan_in)
//   chain_grp_o     = tap_scan ? SCAN_SEL[2:1] : 0   (no consumer until Stage 2)
//   rst_assert_o    = tap_scan & SCAN_RST[0]
//   scan_en_o       = (state == Shift-DR) & serial
//   shift_clk_en_o  = (state in {Capture-DR, Shift-DR}) & serial_o. COMBINATIONAL,
//                     deliberately: it is the D side of a clock-gate latch (in
//                     dft_ctrl) that is transparent while TCK is low. It changes
//                     only just after a TCK rising edge (state flops) or on the
//                     falling edge in an Update state, where the state term is 0.
//
// STAGE2_CHAIN: the SCAN data register below is a 1-bit stub with BYPASS timing.
// Stage 2 replaces this one register with the serial path through the stitched
// scan chains (capture = chain outputs, shift = chain shift, scan_out -> TDO).
//
// No inout, no tristate: the chip top builds the TDO tristate from tdo_oe_o.
// No runtime-indexed array reads: IR/TDRs are shift registers, DR select is a
// one-hot AND-OR of registered decodes.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module jtag_tap (
    // ── JTAG pins ────────────────────────────────────────────────────────────
    input  logic       tck_i,
    input  logic       tms_i,
    input  logic       tdi_i,
    input  logic       trst_ni,         // async assert, TCK-synchronous release
    output logic       tdo_o,           // falling-edge flop, 0 outside Shift-IR/DR
    output logic       tdo_oe_o,        // falling-edge flop, 1 exactly in Shift-IR/DR

    // ── Observability (tests) ────────────────────────────────────────────────
    output logic [3:0] state_o,         // TAP state, rising-edge flop (standard codes)

    // ── Controls to dft_ctrl (all falling-edge flops except shift_clk_en_o) ──
    output logic       scan_mode_o,     // tap_scan
    output logic       serial_o,        // tap_scan & ~PARALLEL
    output logic       parallel_o,      // tap_scan & PARALLEL
    output logic       rst_assert_o,    // tap_scan & SCAN_RST[0]
    output logic       scan_en_o,       // (state == Shift-DR) & serial
    output logic       shift_clk_en_o,  // combinational: clock-gate enable for TCK
    output logic [1:0] chain_grp_o,     // SCAN_SEL[2:1] while in SCAN, else 0

    // ── MBIST (Stage 4, section 16.5) ────────────────────────────────────────
    output logic [28:0]  mbist_ctl_o,       // MBIST_CTRL update register (falling-edge flops)
    output logic         mbist_wr_o,        // write strobe, falling-edge flop: ONE rising TCK edge per Update-DR
    output logic         mbist_force_o,     // run & dom_cpu, falling-edge flop: forces the CPU clock gate open
    input  logic         mbist_wr_ready_i,  // every enabled control-word FIFO can accept (1 when absent)
    input  logic [138:0] mbist_status_i     // {cpu block, core block, cpu_present}, TCK-domain synchronised
);

    // ── TAP states (IEEE 1149.1 standard encodings) ──────────────────────────
    typedef enum logic [3:0] {
        S_TLR   = 4'hF,
        S_RTI   = 4'hC,
        S_SELDR = 4'h7,
        S_CAPDR = 4'h6,
        S_SHDR  = 4'h2,
        S_EX1DR = 4'h1,
        S_PAUDR = 4'h3,
        S_EX2DR = 4'h0,
        S_UPDR  = 4'h5,
        S_SELIR = 4'h4,
        S_CAPIR = 4'hE,
        S_SHIR  = 4'hA,
        S_EX1IR = 4'h9,
        S_PAUIR = 4'hB,
        S_EX2IR = 4'h8,
        S_UPIR  = 4'hD
    } tap_state_e;

    // ── Instruction opcodes (private codes, section 15.3) ────────────────────
    localparam logic [3:0] OP_IDCODE   = 4'h1;
    localparam logic [3:0] OP_SCAN_SEL = 4'h3;
    localparam logic [3:0] OP_SCAN     = 4'h4;
    localparam logic [3:0] OP_SCAN_RST = 4'h5;
    localparam logic [3:0] OP_MBIST_CTL = 4'h6;
    localparam logic [3:0] OP_MBIST_ST  = 4'h7;
    localparam logic [3:0] IR_CAPTURE  = 4'b0001;   // mandatory ...01 pattern
    localparam logic [31:0] IDCODE_VAL = 32'h15C0_1001;

    // ── Reset: one cdc_reset_sync in the TCK domain ──────────────────────────
    logic rst_tck_n;

    cdc_reset_sync #(
        .STAGES(2)
    ) u_trst_sync (
        .clk_i       (tck_i),
        .rst_n_i     (trst_ni),
        .scanmode_i  (1'b0),
        .scan_rst_ni (1'b1),
        .rst_n_o     (rst_tck_n)
    );

    // ── State machine (rising edge) ──────────────────────────────────────────
    tap_state_e state_q;
    tap_state_e state_d;

    always_comb begin
        state_d = S_TLR;
        unique case (state_q)
            S_TLR:   state_d = tms_i ? S_TLR   : S_RTI;
            S_RTI:   state_d = tms_i ? S_SELDR : S_RTI;
            S_SELDR: state_d = tms_i ? S_SELIR : S_CAPDR;
            S_CAPDR: state_d = tms_i ? S_EX1DR : S_SHDR;
            S_SHDR:  state_d = tms_i ? S_EX1DR : S_SHDR;
            S_EX1DR: state_d = tms_i ? S_UPDR  : S_PAUDR;
            S_PAUDR: state_d = tms_i ? S_EX2DR : S_PAUDR;
            S_EX2DR: state_d = tms_i ? S_UPDR  : S_SHDR;
            S_UPDR:  state_d = tms_i ? S_SELDR : S_RTI;
            S_SELIR: state_d = tms_i ? S_TLR   : S_CAPIR;
            S_CAPIR: state_d = tms_i ? S_EX1IR : S_SHIR;
            S_SHIR:  state_d = tms_i ? S_EX1IR : S_SHIR;
            S_EX1IR: state_d = tms_i ? S_UPIR  : S_PAUIR;
            S_PAUIR: state_d = tms_i ? S_EX2IR : S_PAUIR;
            S_EX2IR: state_d = tms_i ? S_UPIR  : S_SHIR;
            S_UPIR:  state_d = tms_i ? S_SELDR : S_RTI;
            default: state_d = S_TLR;
        endcase
    end

    always_ff @(posedge tck_i or negedge rst_tck_n) begin
        if (!rst_tck_n) begin
            state_q <= S_TLR;
        end else begin
            state_q <= state_d;
        end
    end

    assign state_o = state_q;

    logic st_tlr;
    logic st_capir;
    logic st_shir;
    logic st_upir;
    logic st_capdr;
    logic st_shdr;
    logic st_updr;

    assign st_tlr   = (state_q == S_TLR);
    assign st_capir = (state_q == S_CAPIR);
    assign st_shir  = (state_q == S_SHIR);
    assign st_upir  = (state_q == S_UPIR);
    assign st_capdr = (state_q == S_CAPDR);
    assign st_shdr  = (state_q == S_SHDR);
    assign st_updr  = (state_q == S_UPDR);

    // ── Instruction register ─────────────────────────────────────────────────
    // Shift stage (rising edge): loaded with ...01 in Capture-IR, shifts LSB
    // first with TDI entering the MSB in Shift-IR.
    logic [3:0] ir_shift_q;

    always_ff @(posedge tck_i or negedge rst_tck_n) begin
        if (!rst_tck_n) begin
            ir_shift_q <= IR_CAPTURE;
        end else if (st_capir) begin
            ir_shift_q <= IR_CAPTURE;
        end else if (st_shir) begin
            ir_shift_q <= {tdi_i, ir_shift_q[3:1]};
        end
    end

    // Update stage and registered decodes (falling edge), from the next value ir_d.
    logic [3:0] ir_q;
    logic [3:0] ir_d;
    logic       dec_idcode_d;
    logic       dec_scan_sel_d;
    logic       dec_scan_d;
    logic       dec_scan_rst_d;
    logic       dec_mb_ctl_d;
    logic       dec_mb_st_d;
    logic       dec_bypass_d;
    logic       dec_idcode_q;
    logic       dec_scan_sel_q;
    logic       dec_scan_q;        // == tap_scan
    logic       dec_scan_rst_q;
    logic       dec_mb_ctl_q;
    logic       dec_mb_st_q;
    logic       dec_bypass_q;

    always_comb begin
        ir_d = ir_q;
        if (st_tlr) begin
            ir_d = OP_IDCODE;
        end else if (st_upir) begin
            ir_d = ir_shift_q;
        end
    end

    assign dec_idcode_d   = (ir_d == OP_IDCODE);
    assign dec_scan_sel_d = (ir_d == OP_SCAN_SEL);
    assign dec_scan_d     = (ir_d == OP_SCAN);
    assign dec_scan_rst_d = (ir_d == OP_SCAN_RST);
    assign dec_mb_ctl_d   = (ir_d == OP_MBIST_CTL);
    assign dec_mb_st_d    = (ir_d == OP_MBIST_ST);
    assign dec_bypass_d   = ~(dec_idcode_d | dec_scan_sel_d | dec_scan_d | dec_scan_rst_d
                              | dec_mb_ctl_d | dec_mb_st_d);

    always_ff @(negedge tck_i or negedge rst_tck_n) begin
        if (!rst_tck_n) begin
            ir_q           <= OP_IDCODE;
            dec_idcode_q   <= 1'b1;
            dec_scan_sel_q <= 1'b0;
            dec_scan_q     <= 1'b0;
            dec_scan_rst_q <= 1'b0;
            dec_mb_ctl_q   <= 1'b0;
            dec_mb_st_q    <= 1'b0;
            dec_bypass_q   <= 1'b0;
        end else begin
            ir_q           <= ir_d;
            dec_idcode_q   <= dec_idcode_d;
            dec_scan_sel_q <= dec_scan_sel_d;
            dec_scan_q     <= dec_scan_d;
            dec_scan_rst_q <= dec_scan_rst_d;
            dec_mb_ctl_q   <= dec_mb_ctl_d;
            dec_mb_st_q    <= dec_mb_st_d;
            dec_bypass_q   <= dec_bypass_d;
        end
    end

    // ── Test-data registers: shift stages (rising edge) ──────────────────────
    // Each loads in Capture-DR and shifts in Shift-DR only while selected.
    logic [31:0] idcode_sh_q;
    logic [2:0]  scan_sel_sh_q;
    logic        scan_sh_q;        // STAGE2_CHAIN: 1-bit stub, BYPASS timing
    logic        scan_rst_sh_q;
    logic [28:0] mb_ctl_sh_q;
    logic [139:0] mb_st_sh_q;
    logic        mb_ovf_q;
    logic        bypass_q;

    // Update registers (falling edge), declared here for the capture paths.
    logic [2:0]  scan_sel_q;
    logic [2:0]  scan_sel_d;
    logic        scan_rst_q;
    logic        scan_rst_d;
    logic [28:0] mb_ctl_q;
    logic [28:0] mb_ctl_d;

    always_ff @(posedge tck_i or negedge rst_tck_n) begin
        if (!rst_tck_n) begin
            idcode_sh_q   <= '0;
            scan_sel_sh_q <= '0;
            scan_sh_q     <= 1'b0;
            scan_rst_sh_q <= 1'b0;
            mb_ctl_sh_q   <= '0;
            mb_st_sh_q    <= '0;
            bypass_q      <= 1'b0;
        end else begin
            if (dec_idcode_q) begin
                if (st_capdr) begin
                    idcode_sh_q <= IDCODE_VAL;
                end else if (st_shdr) begin
                    idcode_sh_q <= {tdi_i, idcode_sh_q[31:1]};
                end
            end
            if (dec_scan_sel_q) begin
                if (st_capdr) begin
                    scan_sel_sh_q <= scan_sel_q;
                end else if (st_shdr) begin
                    scan_sel_sh_q <= {tdi_i, scan_sel_sh_q[2:1]};
                end
            end
            // STAGE2_CHAIN: replace this register with the serial chain path.
            if (dec_scan_q) begin
                if (st_capdr) begin
                    scan_sh_q <= 1'b0;
                end else if (st_shdr) begin
                    scan_sh_q <= tdi_i;
                end
            end
            if (dec_scan_rst_q) begin
                if (st_capdr) begin
                    scan_rst_sh_q <= scan_rst_q;
                end else if (st_shdr) begin
                    scan_rst_sh_q <= tdi_i;
                end
            end
            if (dec_mb_ctl_q) begin
                if (st_capdr) begin
                    mb_ctl_sh_q <= mb_ctl_q;
                end else if (st_shdr) begin
                    mb_ctl_sh_q <= {tdi_i, mb_ctl_sh_q[28:1]};
                end
            end
            if (dec_mb_st_q) begin
                if (st_capdr) begin
                    mb_st_sh_q <= {mbist_status_i, mb_ovf_q};
                end else if (st_shdr) begin
                    mb_st_sh_q <= {tdi_i, mb_st_sh_q[139:1]};
                end
            end
            if (dec_bypass_q) begin
                if (st_capdr) begin
                    bypass_q <= 1'b0;
                end else if (st_shdr) begin
                    bypass_q <= tdi_i;
                end
            end
        end
    end

    // ── Update-stage next values (falling edge) ──────────────────────────────
    always_comb begin
        scan_sel_d = scan_sel_q;
        if (st_tlr) begin
            scan_sel_d = '0;
        end else if (st_updr && dec_scan_sel_q) begin
            scan_sel_d = scan_sel_sh_q;
        end
    end

    always_comb begin
        scan_rst_d = scan_rst_q;
        if (st_tlr) begin
            scan_rst_d = 1'b0;
        end else if (st_updr && dec_scan_rst_q) begin
            scan_rst_d = scan_rst_sh_q;
        end
    end

    // MBIST_CTRL update value, and the write strobe: Update-DR of MBIST_CTRL, or the FIRST falling edge in
    // Test-Logic-Reset (default word 0 written once, so five TMS-high clocks abort a running MBIST).
    logic st_tlr_prev_q;
    logic mb_wr_d;
    logic mb_force_d;

    always_comb begin
        mb_ctl_d = mb_ctl_q;
        if (st_tlr) begin
            mb_ctl_d = '0;
        end else if (st_updr && dec_mb_ctl_q) begin
            mb_ctl_d = mb_ctl_sh_q;
        end
    end

    assign mb_wr_d    = (st_updr && dec_mb_ctl_q) || (st_tlr && !st_tlr_prev_q);
    assign mb_force_d = mb_ctl_d[0] & mb_ctl_d[28];

    // Sticky overflow: a strobe while the FIFO cannot accept loses the word. Cleared only by TRST or by
    // an ACCEPTED run = 0 word (which includes the Test-Logic-Reset default write).
    always_ff @(posedge tck_i or negedge rst_tck_n) begin
        if (!rst_tck_n) begin
            mb_ovf_q <= 1'b0;
        end else if (mbist_wr_o && !mbist_wr_ready_i) begin
            mb_ovf_q <= 1'b1;
        end else if (mbist_wr_o && !mb_ctl_q[0]) begin
            mb_ovf_q <= 1'b0;
        end
    end

    // ── TDO: one-hot AND-OR over the selected register's LSB ─────────────────
    logic dr_lsb;
    logic tdo_d;
    logic tdo_oe_d;
    logic st_shdr_or_shir;

    assign dr_lsb = (dec_idcode_q   & idcode_sh_q[0])
                  | (dec_scan_sel_q & scan_sel_sh_q[0])
                  | (dec_scan_q     & scan_sh_q)
                  | (dec_scan_rst_q & scan_rst_sh_q)
                  | (dec_mb_ctl_q   & mb_ctl_sh_q[0])
                  | (dec_mb_st_q    & mb_st_sh_q[0])
                  | (dec_bypass_q   & bypass_q);

    assign st_shdr_or_shir = st_shdr | st_shir;

    always_comb begin
        tdo_d = 1'b0;
        if (st_shir) begin
            tdo_d = ir_shift_q[0];
        end else if (st_shdr) begin
            tdo_d = dr_lsb;
        end
    end

    assign tdo_oe_d = st_shdr_or_shir;

    // ── SoC-facing outputs: falling-edge flops from next-state values ────────
    logic       serial_d;
    logic       parallel_d;

    assign serial_d   = dec_scan_d & ~scan_sel_d[0];
    assign parallel_d = dec_scan_d &  scan_sel_d[0];

    always_ff @(negedge tck_i or negedge rst_tck_n) begin
        if (!rst_tck_n) begin
            scan_sel_q   <= '0;
            scan_rst_q   <= 1'b0;
            tdo_o        <= 1'b0;
            tdo_oe_o     <= 1'b0;
            scan_mode_o  <= 1'b0;
            serial_o     <= 1'b0;
            parallel_o   <= 1'b0;
            rst_assert_o <= 1'b0;
            scan_en_o    <= 1'b0;
            chain_grp_o  <= 2'b00;
            mb_ctl_q       <= '0;
            mbist_wr_o     <= 1'b0;
            mbist_force_o  <= 1'b0;
            st_tlr_prev_q  <= 1'b0;
        end else begin
            scan_sel_q   <= scan_sel_d;
            scan_rst_q   <= scan_rst_d;
            tdo_o        <= tdo_d;
            tdo_oe_o     <= tdo_oe_d;
            scan_mode_o  <= dec_scan_d;
            serial_o     <= serial_d;
            parallel_o   <= parallel_d;
            rst_assert_o <= dec_scan_d & scan_rst_d;
            scan_en_o    <= st_shdr & serial_d;
            chain_grp_o  <= dec_scan_d ? scan_sel_d[2:1] : 2'b00;
            mb_ctl_q       <= mb_ctl_d;
            mbist_wr_o     <= mb_wr_d;
            mbist_force_o  <= mb_force_d;
            st_tlr_prev_q  <= st_tlr;
        end
    end

    // Clock-gate enable for the TCK scan clock (dft_ctrl): capture and shift
    // cycles only, so there is no edge in Run-Test/Idle, Pause or Update.
    assign shift_clk_en_o = serial_o & (st_capdr | st_shdr);

    assign mbist_ctl_o = mb_ctl_q;

endmodule : jtag_tap
