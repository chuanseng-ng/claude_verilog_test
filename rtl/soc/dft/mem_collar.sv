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
// Specification: docs/design/DFT_ARCHITECTURE.md section 16.4.
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module mem_collar #(
    parameter int unsigned AW     = 10,
    parameter bit          HAS_P1 = 1'b1
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

endmodule : mem_collar
