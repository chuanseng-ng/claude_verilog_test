// rv32i_csr_file.sv
// RV32I M-mode CSR Register File (Phase 5)
//
// Implements the minimal M-mode CSR set required for interrupt support:
//   0x300  mstatus      - Machine status (MIE, MPIE, MPP)
//   0x304  mie          - Machine interrupt enable (MTIE, MEIE)
//   0x305  mtvec        - Trap vector base address (Direct mode only)
//   0x320  mcountinhibit- Performance counter inhibit mask
//   0x341  mepc         - Machine exception PC
//   0x342  mcause       - Machine trap cause
//   0x344  mip          - Machine interrupt pending (read-only from software)
//   0xB00  mcycle       - Cycle counter low 32 bits
//   0xB02  minstret     - Retired-instruction counter low 32 bits
//   0xB03  mhpmcounter3 - I-cache miss counter
//   0xB04  mhpmcounter4 - D-cache miss counter
//   0xB05  mhpmcounter5 - Branch mispredict counter
//   0xB80  mcycleh      - Cycle counter high 32 bits
//   0xB82  minstreth    - Retired-instruction counter high 32 bits
//   0xF11  mvendorid    - Vendor ID (read-only, 0)
//   0xF12  marchid      - Architecture ID (read-only, 0)
//   0xF13  mimpid       - Implementation ID (read-only, phase-specific)
//   0xF14  mhartid      - Hardware thread ID (read-only, 0)
//
// Write priority (highest first): reset > trap_entry > mret > csr instruction
//
// OQ-4: CSR write takes effect in EX (at the clock edge ending EX stage).
//        mstatus_mie_eff reflects what MIE will be AFTER the pending write,
//        so the interrupt controller sees the correct gating in the same cycle.
//
// Performance counter increment priority: write wins over increment on same
// cycle (i.e. if a CSR write and counter event arrive simultaneously, the
// written value takes effect — the event increment is suppressed that cycle).

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

    // ── Performance counter event strobes (1-cycle pulses) ────────────────────
    input  logic        retire_i,        // 1 = instruction committed this cycle (minstret)
    input  logic        branch_mispred_i,// 1 = branch/JALR redirect this cycle (hpmcounter5)
    input  logic        icache_miss_i,   // 1 = I-cache miss this cycle (hpmcounter3)
    input  logic        dcache_miss_i,   // 1 = D-cache miss this cycle (hpmcounter4)

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
    // Performance monitoring CSRs (Phase 5 M7)
    // =========================================================================
    // mcountinhibit (0x320): per-counter inhibit mask.
    //   bit0 = mcycle inhibit, bit2 = minstret inhibit,
    //   bit3 = hpmcounter3 (icache_miss), bit4 = hpmcounter4 (dcache_miss),
    //   bit5 = hpmcounter5 (branch_mispred). bit1 reserved = 0.
    //   Reset value 0 (all counters run by default).
    logic [31:0] mcountinhibit_q;

    // mcycle / mcycleh (0xB00 / 0xB80): 64-bit cycle counter
    logic [63:0] mcycle_q;

    // minstret / minstreth (0xB02 / 0xB82): 64-bit retired-instruction counter
    logic [63:0] minstret_q;

    // mhpmcounter3..5 (0xB03..0xB05): 32-bit fixed-event counters
    logic [31:0] mhpmcounter3_q;   // I-cache misses
    logic [31:0] mhpmcounter4_q;   // D-cache misses
    logic [31:0] mhpmcounter5_q;   // Branch mispredictions

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
    //
    // Two-level decode to reduce synthesis mux depth and address-compare fan-in:
    //   Level 1: csr_addr[11:8] selects range group (3-bit one-hot: trap/ctr/id)
    //   Level 2: within each group decode lower bits (max 7 entries per group)
    //
    // This cuts the OR-reduction tree depth vs a flat 16-entry case, restoring
    // ASAP7 setup timing after M7 counter CSRs widened the original flat mux.
    // =========================================================================

    // --- Level-1 range pre-decode (one-hot, function of addr[11:8] only) -----
    // range_trap: 0x3xx  trap/control CSRs  (mstatus, mie, mtvec, mcountinhibit, mepc, mcause, mip)
    // range_ctr:  0xBxx  performance counter CSRs (mcycle, minstret, mhpmcounter3-5, mcycleh, minstreth)
    // range_id:   0xFxx  read-only ID CSRs  (mvendorid, marchid, mimpid, mhartid)
    logic range_trap, range_ctr, range_id;
    always_comb begin
        range_trap = (csr_addr[11:8] == 4'h3);
        range_ctr  = (csr_addr[11:8] == 4'hB);
        range_id   = (csr_addr[11:8] == 4'hF);
    end

    // --- Level-2 per-group sub-mux outputs -----------------------------------
    // Each sub-mux decodes only the low-order bits within its range group.
    // Outputs are 0 when the address is not in the group (range_xxx gates output).
    logic [31:0] rdata_trap, rdata_ctr, rdata_id;
    logic        illegal_trap, illegal_ctr, illegal_id;

    // Group A: 0x3xx  (7 entries: 0x300, 0x304, 0x305, 0x320, 0x341, 0x342, 0x344)
    always_comb begin
        rdata_trap   = 32'h0;
        illegal_trap = 1'b0;
        if (range_trap) begin
            case (csr_addr[7:0])
                8'h00: rdata_trap = {19'h0, 2'b11, 3'h0, mstatus_mpie_q, 3'h0, mstatus_mie_q, 3'h0}; // mstatus
                8'h04: rdata_trap = {20'h0, mie_meie_q, 3'h0, mie_mtie_q, 7'h0};                      // mie
                8'h05: rdata_trap = {mtvec_base_q, 2'b00};                                              // mtvec
                8'h20: rdata_trap = mcountinhibit_q & 32'h0000_003D; // bits[5:3,2,0]; bit1=0           // mcountinhibit
                8'h41: rdata_trap = mepc_q;                                                              // mepc
                8'h42: rdata_trap = mcause_q;                                                            // mcause
                8'h44: rdata_trap = mip;                                                                 // mip
                default: begin
                    rdata_trap   = 32'h0;
                    illegal_trap = 1'b1;
                end
            endcase
        end
    end

    // Group B: 0xBxx  (7 entries: 0xB00, 0xB02, 0xB03, 0xB04, 0xB05, 0xB80, 0xB82)
    always_comb begin
        rdata_ctr   = 32'h0;
        illegal_ctr = 1'b0;
        if (range_ctr) begin
            case (csr_addr[7:0])
                8'h00: rdata_ctr = mcycle_q[31:0];     // mcycle
                8'h02: rdata_ctr = minstret_q[31:0];   // minstret
                8'h03: rdata_ctr = mhpmcounter3_q;     // mhpmcounter3 (I$ miss)
                8'h04: rdata_ctr = mhpmcounter4_q;     // mhpmcounter4 (D$ miss)
                8'h05: rdata_ctr = mhpmcounter5_q;     // mhpmcounter5 (branch mispred)
                8'h80: rdata_ctr = mcycle_q[63:32];    // mcycleh
                8'h82: rdata_ctr = minstret_q[63:32];  // minstreth
                default: begin
                    rdata_ctr   = 32'h0;
                    illegal_ctr = 1'b1;
                end
            endcase
        end
    end

    // Group C: 0xFxx  (4 entries: 0xF11, 0xF12, 0xF13, 0xF14 — all return 0 except mimpid)
    always_comb begin
        rdata_id   = 32'h0;
        illegal_id = 1'b0;
        if (range_id) begin
            case (csr_addr[7:0])
                8'h11: rdata_id = 32'h0;          // mvendorid = 0
                8'h12: rdata_id = 32'h0;          // marchid = 0
                8'h13: rdata_id = 32'h0000_0005;  // mimpid = Phase 5
                8'h14: rdata_id = 32'h0;          // mhartid = 0
                default: begin
                    rdata_id   = 32'h0;
                    illegal_id = 1'b1;
                end
            endcase
        end
    end

    // --- Level-1 output combine: OR the three mutually-exclusive sub-mux outputs --
    // Final mux is a 3-input OR (3 entries, very shallow).
    // csr_illegal: address is valid range but unimplemented low bits, OR no range matched.
    always_comb begin
        csr_rdata   = 32'h0;
        csr_illegal = 1'b0;
        if (csr_access) begin
            csr_rdata   = rdata_trap | rdata_ctr | rdata_id;
            csr_illegal = (range_trap & illegal_trap) |
                          (range_ctr  & illegal_ctr)  |
                          (range_id   & illegal_id)   |
                          (!range_trap & !range_ctr & !range_id); // no range matched
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

        if (!do_write) begin
            apply_csr_op = cur;
        end else begin
            case (op)
                3'b001, 3'b101: apply_csr_op = wdat;
                3'b010, 3'b110: apply_csr_op = cur | wdat;
                3'b011, 3'b111: apply_csr_op = cur & ~wdat;
                default:        apply_csr_op = cur;
            endcase
        end
    endfunction

    // =========================================================================
    // Synchronous CSR register updates
    // Priority: reset > trap_entry > mret > csr instruction write
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            mstatus_mie_q  <= 1'b0;
            mstatus_mpie_q <= 1'b0;
            mie_mtie_q     <= 1'b0;
            mie_meie_q     <= 1'b0;
            mtvec_base_q   <= 30'h0;  // Default: trap handler at 0x0000_0000
            mepc_q         <= 32'h0;
            mcause_q       <= 32'h0;
            // Performance counters reset to 0 (all run by default)
            mcountinhibit_q <= 32'h0;
            mcycle_q        <= 64'h0;
            minstret_q      <= 64'h0;
            mhpmcounter3_q  <= 32'h0;
            mhpmcounter4_q  <= 32'h0;
            mhpmcounter5_q  <= 32'h0;

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

        end else begin
            // ---------------------------------------------------------------
            // CSR instruction write (when active, write wins over increment;
            // increment suppressed this cycle for the written register).
            // ---------------------------------------------------------------
            if (csr_access && !csr_illegal) begin
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
                    12'h320: begin  // mcountinhibit (bit1 RAZ/WI)
                        csr_cur = mcountinhibit_q & 32'h0000_003D;
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        mcountinhibit_q <= csr_nxt & 32'h0000_003D;  // mask bit1 always 0
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
                    12'hB00: begin  // mcycle low — write wins; carry suppressed this cycle
                        csr_cur = mcycle_q[31:0];
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        mcycle_q[31:0] <= csr_nxt;
                    end
                    12'hB02: begin  // minstret low — write wins
                        csr_cur = minstret_q[31:0];
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        minstret_q[31:0] <= csr_nxt;
                    end
                    12'hB03: begin  // mhpmcounter3 — write wins
                        csr_cur = mhpmcounter3_q;
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        mhpmcounter3_q <= csr_nxt;
                    end
                    12'hB04: begin  // mhpmcounter4 — write wins
                        csr_cur = mhpmcounter4_q;
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        mhpmcounter4_q <= csr_nxt;
                    end
                    12'hB05: begin  // mhpmcounter5 — write wins
                        csr_cur = mhpmcounter5_q;
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        mhpmcounter5_q <= csr_nxt;
                    end
                    12'hB80: begin  // mcycleh high — write wins
                        csr_cur = mcycle_q[63:32];
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        mcycle_q[63:32] <= csr_nxt;
                    end
                    12'hB82: begin  // minstreth high — write wins
                        csr_cur = minstret_q[63:32];
                        csr_nxt = apply_csr_op(csr_cur, csr_wdata, csr_op, rs1_addr, 1'b1);
                        minstret_q[63:32] <= csr_nxt;
                    end
                    // mip (0x344), mvendorid/marchid/mimpid/mhartid (0xF1x): read-only, writes ignored
                    default: ; // Illegal already flagged combinatorially; no state change
                endcase
            end else begin
                // ---------------------------------------------------------------
                // Performance counter increment (no CSR write this cycle).
                // mcountinhibit bit gates each counter. Carry from low→high word.
                // ---------------------------------------------------------------

                // mcycle: always-on event (increment=1), inhibited by bit0
                if (!mcountinhibit_q[0]) begin
                    mcycle_q <= mcycle_q + 64'h1;
                end

                // minstret: retire strobe, inhibited by bit2
                if (retire_i && !mcountinhibit_q[2]) begin
                    minstret_q <= minstret_q + 64'h1;
                end

                // mhpmcounter3: I-cache miss strobe, inhibited by bit3
                if (icache_miss_i && !mcountinhibit_q[3]) begin
                    mhpmcounter3_q <= mhpmcounter3_q + 32'h1;
                end

                // mhpmcounter4: D-cache miss strobe, inhibited by bit4
                if (dcache_miss_i && !mcountinhibit_q[4]) begin
                    mhpmcounter4_q <= mhpmcounter4_q + 32'h1;
                end

                // mhpmcounter5: branch mispredict strobe, inhibited by bit5
                if (branch_mispred_i && !mcountinhibit_q[5]) begin
                    mhpmcounter5_q <= mhpmcounter5_q + 32'h1;
                end
            end
        end
    end

endmodule
