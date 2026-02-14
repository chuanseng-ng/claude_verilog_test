// rv32i_csr_file.sv
// RV32I M-mode CSR Register File (Phase 2)
//
// Implements the minimal M-mode CSR set required for interrupt support:
//   0x300  mstatus  - Machine status (MIE, MPIE, MPP)
//   0x304  mie      - Machine interrupt enable (MTIE, MEIE)
//   0x305  mtvec    - Trap vector base address (Direct mode only)
//   0x341  mepc     - Machine exception PC
//   0x342  mcause   - Machine trap cause
//   0x344  mip      - Machine interrupt pending (read-only from software)
//   0xF11  mvendorid- Vendor ID (read-only, 0)
//   0xF12  marchid  - Architecture ID (read-only, 0)
//   0xF13  mimpid   - Implementation ID (read-only, phase-specific)
//   0xF14  mhartid  - Hardware thread ID (read-only, 0)
//
// Write priority (highest first): reset > trap_entry > mret > csr instruction
//
// OQ-4: CSR write takes effect in EX (at the clock edge ending EX stage).
//        mstatus_mie_eff reflects what MIE will be AFTER the pending write,
//        so the interrupt controller sees the correct gating in the same cycle.

module rv32i_csr_file (
    input  logic        clk,
    input  logic        rst_n,

    // ── CSR instruction access (EX stage) ────────────────────────────────────
    input  logic        csr_access,      // CSR instruction is executing
    input  logic [11:0] csr_addr,        // CSR address
    input  logic [2:0]  csr_op,          // funct3: 001=RW, 010=RS, 011=RC, 101=RWI, 110=RSI, 111=RCI
    input  logic [31:0] csr_wdata,       // Write data (forwarded rs1 or zero-ext imm)
    input  logic [4:0]  rs1_addr,        // rs1 address (for write-suppression on RS/RC with x0)

    // ── Trap entry (from EX stage) ────────────────────────────────────────────
    input  logic        trap_entry,      // A trap is being taken this cycle
    input  logic [31:0] trap_pc,         // PC to save in mepc
    input  logic [31:0] trap_cause,      // Full 32-bit mcause value

    // ── MRET (from EX stage) ─────────────────────────────────────────────────
    input  logic        mret,            // MRET instruction executing

    // ── Hardware interrupt inputs (for mip) ───────────────────────────────────
    input  logic        ext_irq_i,       // External interrupt (drives mip.MEIP)
    input  logic        timer_irq_i,     // Timer interrupt (drives mip.MTIP)

    // ── CSR read output (combinational pre-write, atomic) ─────────────────────
    output logic [31:0] csr_rdata,       // CSR value before any write this cycle
    output logic        csr_illegal,     // 1 when csr_access but address not implemented

    // ── Trap / MRET redirect values ───────────────────────────────────────────
    output logic [31:0] mtvec_out,       // mtvec (trap handler base, MODE forced to 0)
    output logic [31:0] mret_pc,         // mepc value for MRET PC restore

    // ── Interrupt enable signals (to interrupt_ctrl) ──────────────────────────
    output logic        mstatus_mie,     // Registered MIE bit (current cycle)
    output logic        mstatus_mie_eff, // Effective MIE after pending CSR write (OQ-4)
    output logic        mie_mtie,        // Machine Timer Interrupt Enable
    output logic        mie_meie,        // Machine External Interrupt Enable

    // ── mip (combinational from hardware inputs) ──────────────────────────────
    output logic [31:0] mip,             // Interrupt pending bits (read-only)

    // ── Debug visibility (APB debug registers 0x200-0x210) ───────────────────
    output logic [31:0] dbg_mstatus_o,   // Full mstatus value
    output logic [31:0] dbg_mie_o,       // Full mie value
    output logic [31:0] dbg_mcause_o     // Full mcause value
);

    // =========================================================================
    // CSR registers
    // =========================================================================
    // mstatus: only MIE[3], MPIE[7], MPP[12:11] implemented; rest read as 0
    logic        mstatus_mie_q;   // bit 3
    logic        mstatus_mpie_q;  // bit 7
    // MPP hardwired to 2'b11 in Phase 2 (always M-mode)

    // mie: only MTIE[7] and MEIE[11] implemented
    logic        mie_mtie_q;   // bit 7
    logic        mie_meie_q;   // bit 11

    // mtvec: BASE[31:2] stored; MODE[1:0] forced to 0 (Direct only)
    logic [31:2] mtvec_base_q;

    // mepc: stores interrupted/excepting PC
    logic [31:0] mepc_q;

    // mcause: full 32-bit cause
    logic [31:0] mcause_q;

    // =========================================================================
    // mip (combinational — driven by hardware)
    // =========================================================================
    assign mip = {20'h0, ext_irq_i, 3'h0, timer_irq_i, 7'h0};

    // =========================================================================
    // Read outputs
    // =========================================================================
    assign mtvec_out    = {mtvec_base_q, 2'b00};
    assign mret_pc      = mepc_q;
    assign mstatus_mie  = mstatus_mie_q;
    assign mie_mtie     = mie_mtie_q;
    assign mie_meie     = mie_meie_q;

    // Debug visibility outputs (full register values for APB reads)
    assign dbg_mstatus_o = {19'h0, 2'b11, 3'h0, mstatus_mpie_q, 3'h0, mstatus_mie_q, 3'h0};
    assign dbg_mie_o     = {20'h0, mie_meie_q, 3'h0, mie_mtie_q, 7'h0};
    assign dbg_mcause_o  = mcause_q;

    // =========================================================================
    // Combinational pre-write CSR read (csr_rdata = value BEFORE this cycle's write)
    // =========================================================================
    always_comb begin
        csr_rdata   = 32'h0;
        csr_illegal = 1'b0;

        if (csr_access) begin
            case (csr_addr)
                12'h300: csr_rdata = {19'h0, 2'b11, 3'h0, mstatus_mpie_q, 3'h0, mstatus_mie_q, 3'h0};
                12'h304: csr_rdata = {20'h0, mie_meie_q, 3'h0, mie_mtie_q, 7'h0};
                12'h305: csr_rdata = {mtvec_base_q, 2'b00};
                12'h341: csr_rdata = mepc_q;
                12'h342: csr_rdata = mcause_q;
                12'h344: csr_rdata = mip;
                12'hF11: csr_rdata = 32'h0;          // mvendorid = 0
                12'hF12: csr_rdata = 32'h0;          // marchid = 0
                12'hF13: csr_rdata = 32'h0000_0002;  // mimpid = Phase 2
                12'hF14: csr_rdata = 32'h0;          // mhartid = 0
                default: begin
                    csr_rdata   = 32'h0;
                    csr_illegal = 1'b1;  // Unimplemented CSR
                end
            endcase
        end
    end

    // =========================================================================
    // OQ-4: Effective MIE after any pending CSR write this cycle
    // If a CSR instruction is writing mstatus in EX this cycle, compute
    // the new MIE so the interrupt controller sees it immediately.
    // =========================================================================
    logic [31:0] mstatus_after_write;
    // Variables declared at module scope to avoid IMPLICITSTATIC in always_comb
    logic [31:0] mst_cur;
    logic [31:0] mst_wdat;
    logic        mst_do_write;

    always_comb begin
        mst_cur         = {19'h0, 2'b11, 3'h0, mstatus_mpie_q, 3'h0, mstatus_mie_q, 3'h0};
        mst_wdat        = csr_wdata;
        mst_do_write    = 1'b0;
        mstatus_after_write = mst_cur;

        if (csr_access && !csr_illegal && csr_addr == 12'h300) begin
            case (csr_op)
                3'b001: mst_do_write = 1'b1;
                3'b010: mst_do_write = (rs1_addr != 5'h0);
                3'b011: mst_do_write = (rs1_addr != 5'h0);
                3'b101: mst_do_write = 1'b1;
                3'b110: mst_do_write = (mst_wdat[4:0] != 5'h0);
                3'b111: mst_do_write = (mst_wdat[4:0] != 5'h0);
                default: ;
            endcase

            if (mst_do_write) begin
                case (csr_op)
                    3'b001, 3'b101: mstatus_after_write = mst_wdat & 32'h0000_1888;
                    3'b010, 3'b110: mstatus_after_write = (mst_cur | mst_wdat) & 32'h0000_1888;
                    3'b011, 3'b111: mstatus_after_write = (mst_cur & ~mst_wdat) & 32'h0000_1888;
                    default: ;
                endcase
            end
        end
    end

    assign mstatus_mie_eff = mstatus_after_write[3];

    // =========================================================================
    // Compute CSR write value for each register (used in clocked update below)
    // Helper function: apply csr_op to current value with new write data
    // =========================================================================
    function automatic logic [31:0] apply_csr_op(
        input logic [31:0] cur,
        input logic [31:0] wdat,
        input logic [2:0]  op,
        input logic [4:0]  rs1_a,
        input logic        suppress_if_zero  // 1=CSRRS/CSRRC suppress on rs1=x0 / imm=0
    );
        logic do_write;
        case (op)
            3'b001: do_write = 1'b1;
            3'b010: do_write = !suppress_if_zero || (rs1_a != 5'h0);
            3'b011: do_write = !suppress_if_zero || (rs1_a != 5'h0);
            3'b101: do_write = 1'b1;
            3'b110: do_write = !suppress_if_zero || (wdat != 32'h0);
            3'b111: do_write = !suppress_if_zero || (wdat != 32'h0);
            default: do_write = 1'b0;
        endcase

        if (!do_write) return cur;

        case (op)
            3'b001, 3'b101: return wdat;
            3'b010, 3'b110: return cur | wdat;
            3'b011, 3'b111: return cur & ~wdat;
            default:        return cur;
        endcase
    endfunction

    // =========================================================================
    // Synchronous CSR register updates
    // Priority: reset > trap_entry > mret > csr instruction write
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mstatus_mie_q  <= 1'b0;
            mstatus_mpie_q <= 1'b0;
            mie_mtie_q     <= 1'b0;
            mie_meie_q     <= 1'b0;
            mtvec_base_q   <= 30'h0;  // Default: trap handler at 0x0000_0000
            mepc_q         <= 32'h0;
            mcause_q       <= 32'h0;

        end else if (trap_entry) begin
            // Trap entry: save MIE→MPIE, disable MIE, update mepc and mcause
            mepc_q         <= trap_pc;
            mcause_q       <= trap_cause;
            mstatus_mpie_q <= mstatus_mie_q;  // MPIE ← MIE
            mstatus_mie_q  <= 1'b0;           // MIE ← 0 (disable interrupts)
            // MPP hardwired to 2'b11 (M-mode only)

        end else if (mret) begin
            // MRET: restore MIE from MPIE, set MPIE=1
            mstatus_mie_q  <= mstatus_mpie_q; // MIE ← MPIE
            mstatus_mpie_q <= 1'b1;           // MPIE ← 1

        end else if (csr_access && !csr_illegal) begin
            // CSR instruction write
            // Local blocking vars (no initializers — assigned explicitly to avoid IMPLICITSTATIC)
            logic [31:0] csr_cur;
            logic [31:0] csr_nxt;
            case (csr_addr)
                12'h300: begin  // mstatus
                    csr_cur = {19'h0, 2'b11, 3'h0, mstatus_mpie_q, 3'h0, mstatus_mie_q, 3'h0};
                    csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                    // Only update implemented bits [7] MPIE and [3] MIE
                    mstatus_mie_q  <= csr_nxt[3];
                    mstatus_mpie_q <= csr_nxt[7];
                end
                12'h304: begin  // mie
                    csr_cur = {20'h0, mie_meie_q, 3'h0, mie_mtie_q, 7'h0};
                    csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                    mie_mtie_q  <= csr_nxt[7];
                    mie_meie_q  <= csr_nxt[11];
                end
                12'h305: begin  // mtvec (MODE bits [1:0] forced to 0)
                    csr_cur = {mtvec_base_q, 2'b00};
                    csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                    mtvec_base_q <= csr_nxt[31:2];
                end
                12'h341: begin  // mepc
                    csr_cur = mepc_q;
                    csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                    mepc_q <= csr_nxt;
                end
                12'h342: begin  // mcause
                    csr_cur = mcause_q;
                    csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                    mcause_q <= csr_nxt;
                end
                // mip (0x344), mvendorid/marchid/mimpid/mhartid (0xF1x): read-only, writes ignored
                default: ; // Illegal already flagged combinatorially; no state change
            endcase
        end
    end

endmodule
