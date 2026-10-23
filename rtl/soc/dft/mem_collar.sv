// mem_collar.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.14, GH #244).
//
// Input-side BIST collar for ONE Sky130 OpenRAM macro (1RW + 1R). A pure combinational 2:1 mux on every
// macro input, selected by bist_en_i (a FLOP output of mbist_ctrl, so no select can glitch). With
// bist_en_i = 0 every output equals its functional input: the collar is a pass-through and the design
// is bit-identical to one without it. Macro read data is NOT muxed (it goes to the functional logic
// unchanged and, separately, to mbist_ctrl), so the read path carries no extra delay.
//
// Port 1 (HAS_P1 = 1): the BIST read element reads port 0 AND port 1 at the same address; the controller
// compares both. HAS_P1 = 0 is for macros whose port 1 is tied off in the functional design (the caches,
// the NPU weight memory): the port-1 outputs are then constant tie-offs, exactly as the wrapper had them.
//
// Local compare (LOCAL_CMP = 1, bead claude_verilog_test-c54a, section 16.7 / 16.12): the collar also owns the
// read-data comparator of its macro. The controller no longer receives 32 (64 with port 1) read-data wires per
// memory; it broadcasts a compact expected-data tag instead (x_rd_i, x_xm_i, x_bg_i; 8 nets, shared by all
// collars) and gets back ONE registered mismatch strobe per read port (cmp_fail0_o / cmp_fail1_o). The expected
// word is rebuilt locally, exactly as mbist_ctrl builds it: bg_pat(x_bg_i) ^ expand4(x_xm_i).
//
// Timing (the Sky130 macro launches dout0/dout1 on the FALLING edge, the cache samples them half a cycle later):
//   * dout -> XOR2 per bit -> reduce -> flop on the FALLING edge of clk_i. The flop captures one FULL cycle
//     after the macro launched the data, not the half cycle the cache's own capture gets. The load on dout is
//     still one XOR2 input per bit, no flop on dout.
//   * The expected-data tag is launched by the controller on the same falling edge (it holds the tag of the
//     read whose data the macro launched on that edge), so both operands of the XOR have the same full cycle.
//   * falling-edge flop -> rising-edge flop (no logic, adjacent, half a cycle) -> the route to the controller,
//     which is a full-cycle flop-to-flop path. cmp_fail*_o is therefore two clocks after the sample cycle;
//     mbist_ctrl (LOCAL_CMP = 1) accounts for that.
// With LOCAL_CMP = 0 (SoC fabric instances) the compare ports are unused: tie the inputs, ignore the outputs.
//
// Specification: docs/design/DFT_ARCHITECTURE.md section 16.4.
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module mem_collar #(
    parameter int unsigned AW     = 10,
    parameter bit          HAS_P1 = 1'b1,
    parameter bit          LOCAL_CMP = 1'b0
) (
    // ── BIST select and broadcast bus (from mbist_ctrl) ──────────────────────
    input  logic          bist_en_i,
    input  logic          b_ce_i,
    input  logic          b_we_i,
    input  logic [3:0]    b_wmask_i,
    input  logic [AW-1:0] b_addr_i,
    input  logic [31:0]   b_din_i,

    // ── Functional side (what the wrapper drove into the macro before) ───────
    input  logic          csb0_f_i,
    input  logic          web0_f_i,
    input  logic [3:0]    wmask0_f_i,
    input  logic [AW-1:0] addr0_f_i,
    input  logic [31:0]   din0_f_i,
    input  logic          csb1_f_i,
    input  logic [AW-1:0] addr1_f_i,

    // ── Local compare (LOCAL_CMP = 1; otherwise unused) ───────────────────────
    input  logic          clk_i,
    input  logic          x_rd_i,        // this cycle samples the data of a read: compare
    input  logic [3:0]    x_xm_i,        // byte-lane inversion of the expected word
    input  logic [2:0]    x_bg_i,        // background index of the expected word
    input  logic [31:0]   dout0_i,       // macro port-0 read data (the same net the functional logic reads)
    input  logic [31:0]   dout1_i,       // macro port-1 read data (HAS_P1 = 1 only)
    output logic          cmp_fail0_o,   // registered: port-0 data differed from the expected word
    output logic          cmp_fail1_o,   // registered: port-1 data differed (0 when HAS_P1 = 0)

    // ── Macro side ───────────────────────────────────────────────────────────
    output logic          csb0_m_o,
    output logic          web0_m_o,
    output logic [3:0]    wmask0_m_o,
    output logic [AW-1:0] addr0_m_o,
    output logic [31:0]   din0_m_o,
    output logic          csb1_m_o,
    output logic [AW-1:0] addr1_m_o
);

    assign csb0_m_o   = bist_en_i ? ~b_ce_i   : csb0_f_i;
    assign web0_m_o   = bist_en_i ? ~b_we_i   : web0_f_i;
    assign wmask0_m_o = bist_en_i ? b_wmask_i : wmask0_f_i;
    assign addr0_m_o  = bist_en_i ? b_addr_i  : addr0_f_i;
    assign din0_m_o   = bist_en_i ? b_din_i   : din0_f_i;

    if (HAS_P1) begin : g_p1
        // Port 1 reads whenever the BIST op is a read.
        assign csb1_m_o  = bist_en_i ? ~(b_ce_i & ~b_we_i) : csb1_f_i;
        assign addr1_m_o = bist_en_i ? b_addr_i            : addr1_f_i;
    end else begin : g_nop1
        // Functional port 1 is tied off in the wrapper: keep the tie-off values it passes in.
        assign csb1_m_o  = csb1_f_i;
        assign addr1_m_o = addr1_f_i;
    end

    // ── Local read-data comparator ───────────────────────────────────────────
    // Constant-label case function and a replication: no runtime-indexed mux. The pattern table duplicates
    // bg_pat() in mbist_ctrl.sv; a drift shows up as false fails on every all-pass run of the sweep test.
    function automatic logic [31:0] bg_pat(input logic [2:0] b);
        logic [31:0] r;
        unique case (b)
            3'd0:    r = 32'h0000_0000;
            3'd1:    r = 32'h5555_5555;
            3'd2:    r = 32'h3333_3333;
            3'd3:    r = 32'h0F0F_0F0F;
            3'd4:    r = 32'h00FF_00FF;
            3'd5:    r = 32'h0000_FFFF;
            default: r = 32'h0000_0000;
        endcase
        return r;
    endfunction

    if (LOCAL_CMP) begin : g_cmp
        logic [31:0] exp_w;
        logic        ev0_w;
        logic        ev1_w;
        logic        fail0_n_q;   // falling-edge capture, full cycle after the macro launched dout
        logic        fail1_n_q;
        logic        fail0_q;     // rising-edge retime, drives the route to the controller
        logic        fail1_q;

        assign exp_w = bg_pat(x_bg_i) ^ {{8{x_xm_i[3]}}, {8{x_xm_i[2]}}, {8{x_xm_i[1]}}, {8{x_xm_i[0]}}};
        assign ev0_w = x_rd_i && (|(dout0_i ^ exp_w));
        assign ev1_w = HAS_P1 && x_rd_i && (|(dout1_i ^ exp_w));

        // No reset pin (same contract as the reset-free mbist_ctrl): x_rd_i falls within RD_LAT clocks of
        // run = 0, so both strobe stages are flushed to 0 within two more clocks.
        always_ff @(negedge clk_i) begin
            fail0_n_q <= ev0_w;
            fail1_n_q <= ev1_w;
        end

        always_ff @(posedge clk_i) begin
            fail0_q <= fail0_n_q;
            fail1_q <= fail1_n_q;
        end

        assign cmp_fail0_o = fail0_q;
        assign cmp_fail1_o = fail1_q;
    end else begin : g_nocmp
        /* verilator lint_off UNUSEDSIGNAL */
        logic unused_cmp_w;
        assign unused_cmp_w = &{1'b0, clk_i, x_rd_i, x_xm_i, x_bg_i, dout0_i, dout1_i};
        /* verilator lint_on  UNUSEDSIGNAL */
        assign cmp_fail0_o = 1'b0;
        assign cmp_fail1_o = 1'b0;
    end

endmodule : mem_collar
