// rv32i_hazard_unit.sv
// RV32I Pipeline Hazard Detection Unit (EX2 retiming)
//
// Extended for 8-stage view:
//   IF / ID / EX1a / EX1c(reg) / EX1b / EX1b2(reg) / EX2(reg) / MEM / WB
// Run-20: EX1c inserted between ex1a_ex1b_reg_q and ex1c_ex1b_reg_q.
// Run-23: EX1b2 register (ex1b_ex2_reg_q) inserted between EX1b and EX2.
//
// Forwarding encoding (fwd_*_sel):
//   2'b00 = register file (no forwarding)
//   2'b01 = EX2 result (ex_mem_reg, 4 cycles behind EX1a after Run-23 split)
//   2'b10 = WB  result (mem_wb_reg)
//   2'b11 = EX1b result (ex1a_ex1b_reg, 1 cycle behind EX1a) — highest priority
//   (EX1c result, 2 cycles behind EX1a, handled by separate ex1c forwarding tier)
//   (EX1b2 result, 3 cycles behind EX1a, handled by separate ex1b2 forwarding tier)
//
// Priority (highest → lowest):
//   1. mem_trap_redirect  → flush EX2, EX1b2, EX1b, EX1c, EX1a, ID, IF
//   2. mem_cache_stall    → global freeze
//   3. ex_pc_redirect     → flush EX2, EX1b2, EX1b, EX1c, EX1a, ID, IF
//   4. id_jal_taken       → flush IF only
//   5. load_use_ex1       → stall IF,ID; flush ID→EX1a; load in EX1a    (stall 1)
//   6. load_use_ex1c      → stall IF,ID; flush ID→EX1a; load in EX1c    (stall 2)
//   7. load_use_ex1b      → stall IF,ID; flush ID→EX1a; load in EX1b    (stall 3)
//   8. load_use_ex2       → stall IF,ID; flush ID→EX1a; load in EX1b2   (stall 4)
//   9. if_cache_stall     → stall PC only

module rv32i_hazard_unit (
    // From ID/EX register (instruction currently in EX1a)
    input  logic [4:0]  id_ex_rs1_addr,
    input  logic [4:0]  id_ex_rs2_addr,
    input  logic [4:0]  id_ex_rd_addr,
    input  logic        id_ex_mem_rd,
    input  logic        id_ex_reg_wr_en,

    // From EX1b register (ex1a_ex1b_reg — instruction in EX1c, 1 cycle behind EX1a)
    // NOTE: port names keep "ex1b_" prefix for backward compatibility with rv32i_core.sv
    input  logic [4:0]  ex1b_rd_addr,
    input  logic        ex1b_reg_wr_en,
    input  logic        ex1b_mem_rd,

    // From EX1c register (ex1c_ex1b_reg — instruction in EX1b, 2 cycles behind EX1a)
    input  logic [4:0]  ex1c_rd_addr,
    input  logic        ex1c_reg_wr_en,
    input  logic        ex1c_mem_rd,

    // From EX1b2 register (ex1b_ex2_reg_q — instruction in EX2, 3 cycles behind EX1a; Run-23)
    input  logic [4:0]  ex1b2_rd_addr,
    input  logic        ex1b2_reg_wr_en,
    input  logic        ex1b2_mem_rd,

    // From EX/MEM register (instruction completing EX2 / entering MEM)
    input  logic [4:0]  ex_mem_rd_addr,
    input  logic        ex_mem_reg_wr_en,
    input  logic        ex_mem_mem_rd,

    // From MEM/WB register (instruction currently in WB)
    input  logic [4:0]  mem_wb_rd_addr,
    input  logic        mem_wb_reg_wr_en,

    // From IF/ID register (instruction currently in ID)
    input  logic [4:0]  if_id_rs1_addr,
    input  logic [4:0]  if_id_rs2_addr,

    // Cache stall indicators
    input  logic        if_cache_stall,
    input  logic        mem_cache_stall,

    // Branch/jump/trap flush (registered from EX1b stage)
    input  logic        ex_pc_redirect,

    // Misaligned trap flush (registered from MEM stage)
    input  logic        mem_trap_redirect,

    // JAL flush (from ID stage)
    input  logic        id_jal_taken,

    // Outputs — pipeline register control
    output logic        stall_pc,
    output logic        stall_if_id,
    output logic        stall_id_ex,
    output logic        stall_ex_mem,
    output logic        stall_ex1_ex2_o,
    output logic        stall_ex1a_ex1b_o,  // EX1a→EX1c FF stall (Run 17/20)
    output logic        stall_ex1c_ex1b_o,  // EX1c→EX1b FF stall (Run 20)
    output logic        flush_if_id,
    output logic        flush_id_ex,
    output logic        flush_ex_mem,
    output logic        flush_ex1_ex2_o,
    output logic        flush_ex1a_ex1b_o,  // EX1a→EX1c FF flush (Run 17/20)
    output logic        flush_ex1c_ex1b_o,  // EX1c→EX1b FF flush (Run 20)

    // Outputs — forwarding mux selects (for instruction in EX1a)
    // Encoding: 2'b00=regfile, 2'b01=EX2, 2'b10=WB, 2'b11=EX1c (highest non-load)
    // EX1b (ex1a_ex1b_reg) tier = 2'b11 (highest; re-used for EX1c source now)
    output logic [1:0]  fwd_a_sel,
    output logic [1:0]  fwd_b_sel,
    output logic [1:0]  fwd_store_sel,

    // EX1c forwarding tier (producer just completed EX1c / in EX1b now)
    // Encoding: 1'b1 = forward from ex1c_ex1b_reg; overrides EX2 but not EX1b tier
    output logic        fwd_a_ex1c,
    output logic        fwd_b_ex1c,
    output logic        fwd_store_ex1c,

    // EX1b2 forwarding tier (producer completed EX1b / in EX1b2 register now; Run-23)
    // Encoding: 1'b1 = forward from ex1b_ex2_reg_q; priority between EX1c and EX2 tiers
    output logic        fwd_a_ex1b2,
    output logic        fwd_b_ex1b2,
    output logic        fwd_store_ex1b2
);

    // =========================================================================
    // Load-use hazard detection
    //
    // Run-20: the pipeline has THREE register stages between EX1a and MEM
    // (ex1a_ex1b_reg_q → EX1c comb → ex1c_ex1b_reg_q → EX1b comb →
    //  ex1_ex2_reg FF → MEM).  Three stall conditions are required:
    //
    //   load_use_ex1   : load in EX1a (id_ex), consumer in ID (if_id)     → stall 1
    //   load_use_ex1c  : load in EX1c (ex1a_ex1b_reg_q, ex1b_ ports),
    //                    consumer still in ID                               → stall 2
    //   load_use_ex1b  : load in EX1b (ex1c_ex1b_reg_q, ex1c_ ports),
    //                    consumer still in ID                               → stall 3
    //
    // After 3 stalls the consumer enters EX1a while the load is in MEM.
    // The D-cache stall (3 cycles) then holds the consumer in id_ex until
    // the load data appears in mem_wb_reg, which WB→EX1a forwarding delivers.
    // =========================================================================
    logic load_use_ex1;
    logic load_use_ex1c;
    logic load_use_ex1b;
    logic load_use_ex2;

    assign load_use_ex1 = id_ex_mem_rd
                        && (id_ex_rd_addr != 5'h0)
                        && ((id_ex_rd_addr == if_id_rs1_addr)
                          || (id_ex_rd_addr == if_id_rs2_addr));

    // Load has advanced to EX1c (ex1a_ex1b_reg_q); consumer still in ID.
    assign load_use_ex1c = ex1b_mem_rd
                         && (ex1b_rd_addr != 5'h0)
                         && ((ex1b_rd_addr == if_id_rs1_addr)
                           || (ex1b_rd_addr == if_id_rs2_addr));

    // Load has advanced to EX1b (ex1c_ex1b_reg_q); consumer still in ID.
    // Run-20: third stall needed because there are 3 FFs from EX1a to MEM.
    assign load_use_ex1b = ex1c_mem_rd
                         && (ex1c_rd_addr != 5'h0)
                         && ((ex1c_rd_addr == if_id_rs1_addr)
                           || (ex1c_rd_addr == if_id_rs2_addr));

    // Load has advanced to EX1b2 (ex1b_ex2_reg_q); consumer still in ID.
    // Run-23: fourth stall needed because there are now 4 FFs from EX1a to MEM
    // (ex1a_ex1b_reg_q → ex1c_ex1b_reg_q → ex1b_ex2_reg_q → ex_mem_reg).
    assign load_use_ex2  = ex1b2_mem_rd
                         && (ex1b2_rd_addr != 5'h0)
                         && ((ex1b2_rd_addr == if_id_rs1_addr)
                           || (ex1b2_rd_addr == if_id_rs2_addr));

    // =========================================================================
    // Forwarding selects
    //
    // Tier priority (highest → lowest) for instruction consuming in EX1a:
    //   2'b11 = EX1b tier (ex1a_ex1b_reg — producer completed EX1a, now in EX1c)
    //           1 cycle behind consumer (highest priority non-load fwd)
    //   ex1c  = EX1c tier (ex1c_ex1b_reg — producer completed EX1c, now in EX1b)
    //           2 cycles behind consumer
    //   2'b01 = EX2  tier (ex_mem_reg — 3 cycles behind, entering MEM)
    //   2'b10 = WB   tier (mem_wb_reg — covers load-use after stall)
    //   2'b00 = regfile (no forwarding)
    //
    // The EX1c tier uses separate 1-bit outputs (fwd_a_ex1c / fwd_b_ex1c /
    // fwd_store_ex1c) because fwd_*_sel has only 4 encodings already in use.
    // The forwarding unit checks fwd_a_ex1c between the 2'b11 and 2'b01 cases.
    // =========================================================================

    // ALU operand A (rs1 in EX1a)
    // Priority (highest→lowest): EX1b(2'b11) > EX1c(fwd_a_ex1c) > EX1b2(fwd_a_ex1b2) >
    //                             EX2(2'b01) > WB(2'b10) > regfile(2'b00)
    always_comb begin
        if (ex1b_reg_wr_en && !ex1b_mem_rd && (ex1b_rd_addr != 5'h0)
                           && (ex1b_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel   = 2'b11;   // EX1c stage→EX1a (highest; ex1a_ex1b_reg)
            fwd_a_ex1c  = 1'b0;
            fwd_a_ex1b2 = 1'b0;
        end else if (ex1c_reg_wr_en && !ex1c_mem_rd && (ex1c_rd_addr != 5'h0)
                                    && (ex1c_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel   = 2'b00;   // placeholder — ex1c tier overrides via fwd_a_ex1c
            fwd_a_ex1c  = 1'b1;   // EX1b stage→EX1a (ex1c_ex1b_reg)
            fwd_a_ex1b2 = 1'b0;
        end else if (ex1b2_reg_wr_en && !ex1b2_mem_rd && (ex1b2_rd_addr != 5'h0)
                                      && (ex1b2_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel   = 2'b00;   // placeholder — ex1b2 tier overrides via fwd_a_ex1b2
            fwd_a_ex1c  = 1'b0;
            fwd_a_ex1b2 = 1'b1;   // EX1b2 stage→EX1a (ex1b_ex2_reg_q; Run-23)
        end else if (ex_mem_reg_wr_en && !ex_mem_mem_rd && (ex_mem_rd_addr != 5'h0)
                                      && (ex_mem_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel   = 2'b01;   // EX2→EX1a
            fwd_a_ex1c  = 1'b0;
            fwd_a_ex1b2 = 1'b0;
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel   = 2'b10;   // WB→EX1a
            fwd_a_ex1c  = 1'b0;
            fwd_a_ex1b2 = 1'b0;
        end else begin
            fwd_a_sel   = 2'b00;
            fwd_a_ex1c  = 1'b0;
            fwd_a_ex1b2 = 1'b0;
        end
    end

    // ALU operand B (rs2 in EX1a)
    always_comb begin
        if (ex1b_reg_wr_en && !ex1b_mem_rd && (ex1b_rd_addr != 5'h0)
                           && (ex1b_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel   = 2'b11;   // EX1c stage→EX1a
            fwd_b_ex1c  = 1'b0;
            fwd_b_ex1b2 = 1'b0;
        end else if (ex1c_reg_wr_en && !ex1c_mem_rd && (ex1c_rd_addr != 5'h0)
                                    && (ex1c_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel   = 2'b00;
            fwd_b_ex1c  = 1'b1;   // EX1b stage→EX1a (ex1c_ex1b_reg)
            fwd_b_ex1b2 = 1'b0;
        end else if (ex1b2_reg_wr_en && !ex1b2_mem_rd && (ex1b2_rd_addr != 5'h0)
                                      && (ex1b2_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel   = 2'b00;
            fwd_b_ex1c  = 1'b0;
            fwd_b_ex1b2 = 1'b1;   // EX1b2 stage→EX1a (ex1b_ex2_reg_q; Run-23)
        end else if (ex_mem_reg_wr_en && !ex_mem_mem_rd && (ex_mem_rd_addr != 5'h0)
                                      && (ex_mem_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel   = 2'b01;   // EX2→EX1a
            fwd_b_ex1c  = 1'b0;
            fwd_b_ex1b2 = 1'b0;
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel   = 2'b10;   // WB→EX1a
            fwd_b_ex1c  = 1'b0;
            fwd_b_ex1b2 = 1'b0;
        end else begin
            fwd_b_sel   = 2'b00;
            fwd_b_ex1c  = 1'b0;
            fwd_b_ex1b2 = 1'b0;
        end
    end

    assign fwd_store_sel   = fwd_b_sel;
    assign fwd_store_ex1c  = fwd_b_ex1c;
    assign fwd_store_ex1b2 = fwd_b_ex1b2;

    // =========================================================================
    // Stall / flush priority logic
    // =========================================================================
    always_comb begin
        stall_pc           = 1'b0;
        stall_if_id        = 1'b0;
        stall_id_ex        = 1'b0;
        stall_ex_mem       = 1'b0;
        stall_ex1_ex2_o    = 1'b0;
        stall_ex1a_ex1b_o  = 1'b0;
        stall_ex1c_ex1b_o  = 1'b0;
        flush_if_id        = 1'b0;
        flush_id_ex        = 1'b0;
        flush_ex_mem       = 1'b0;
        flush_ex1_ex2_o    = 1'b0;
        flush_ex1a_ex1b_o  = 1'b0;
        flush_ex1c_ex1b_o  = 1'b0;

        if (mem_trap_redirect) begin
            // Priority 0: MEM-stage misaligned trap — flush all EX stages
            flush_if_id        = 1'b1;
            flush_id_ex        = 1'b1;
            flush_ex1a_ex1b_o  = 1'b1;
            flush_ex1c_ex1b_o  = 1'b1;
            flush_ex1_ex2_o    = 1'b1;
            flush_ex_mem       = 1'b1;

        end else if (mem_cache_stall) begin
            // Priority 1: D-cache miss — global freeze
            stall_pc           = 1'b1;
            stall_if_id        = 1'b1;
            stall_id_ex        = 1'b1;
            stall_ex1a_ex1b_o  = 1'b1;
            stall_ex1c_ex1b_o  = 1'b1;
            stall_ex1_ex2_o    = 1'b1;
            stall_ex_mem       = 1'b1;

        end else if (ex_pc_redirect) begin
            // Priority 2: PC redirect — flush EX1c, EX1a, ID, IF
            // (EX1b and EX2 continue — they hold the redirecting instruction)
            flush_if_id        = 1'b1;
            flush_id_ex        = 1'b1;
            flush_ex1a_ex1b_o  = 1'b1;
            flush_ex1c_ex1b_o  = 1'b1;
            flush_ex1_ex2_o    = 1'b1;
            flush_ex_mem       = 1'b1;

        end else if (id_jal_taken) begin
            // Priority 3: JAL resolved in ID — flush IF only
            flush_if_id        = 1'b1;

        end else if (load_use_ex1) begin
            // Priority 4: Load in EX1a, consumer in ID — stall front-end, bubble into EX1a
            stall_pc           = 1'b1;
            stall_if_id        = 1'b1;
            flush_id_ex        = 1'b1;

        end else if (load_use_ex1c) begin
            // Priority 5: Load in EX1c (ex1a_ex1b_reg_q), consumer still in ID → stall 2.
            stall_pc           = 1'b1;
            stall_if_id        = 1'b1;
            flush_id_ex        = 1'b1;

        end else if (load_use_ex1b) begin
            // Priority 7: Load in EX1b (ex1c_ex1b_reg_q), consumer still in ID → stall 3.
            stall_pc           = 1'b1;
            stall_if_id        = 1'b1;
            flush_id_ex        = 1'b1;

        end else if (load_use_ex2) begin
            // Priority 8: Load in EX1b2 (ex1b_ex2_reg_q), consumer still in ID → stall 4.
            // Run-23: fourth stall because ex1b_ex2_reg_q is a new FF between EX1b and EX2.
            stall_pc           = 1'b1;
            stall_if_id        = 1'b1;
            flush_id_ex        = 1'b1;

        end else if (if_cache_stall) begin
            // Priority 9: I-cache miss — stall PC only
            stall_pc           = 1'b1;
        end
    end

endmodule
