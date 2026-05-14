// rv32i_hazard_unit.sv
// RV32I Pipeline Hazard Detection Unit (EX2 retiming)
//
// Extended for 6-stage view: IF / ID / EX1 / EX2(reg) / MEM / WB
// EX2 is a registered pass-through; EX1 is purely combinational.
//
// Forwarding encoding (fwd_*_sel):
//   2'b00 = register file (no forwarding)
//   2'b01 = EX2 result (ex_mem_reg, 1 cycle behind EX1) — highest priority
//   2'b10 = WB  result (mem_wb_reg, 2 cycles behind EX1)
//
// Priority (highest → lowest):
//   1. mem_trap_redirect  → flush EX2, EX1, ID, IF
//   2. mem_cache_stall    → global freeze
//   3. ex_pc_redirect     → flush EX2, EX1, ID, IF
//   4. id_jal_taken       → flush IF only
//   5. load_use_ex1       → stall IF,ID; flush ID→EX1 (bubble); load advances normally
//   6. if_cache_stall     → stall PC only

module rv32i_hazard_unit (
    // From ID/EX register (instruction currently in EX1)
    input  logic [4:0]  id_ex_rs1_addr,
    input  logic [4:0]  id_ex_rs2_addr,
    input  logic [4:0]  id_ex_rd_addr,
    input  logic        id_ex_mem_rd,
    input  logic        id_ex_reg_wr_en,

    // From EX/MEM register (instruction in EX2 register / entering MEM)
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

    // Branch/jump/trap flush (registered from EX stage)
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
    output logic        flush_if_id,
    output logic        flush_id_ex,
    output logic        flush_ex_mem,
    output logic        flush_ex1_ex2_o,

    // Outputs — forwarding mux selects (for instruction in EX1)
    // Encoding: 2'b00=regfile, 2'b01=EX2, 2'b10=MEM, 2'b11=WB
    output logic [1:0]  fwd_a_sel,
    output logic [1:0]  fwd_b_sel,
    output logic [1:0]  fwd_store_sel
);

    // =========================================================================
    // Load-use hazard detection (load in EX1, consumer in ID — 1-cycle stall)
    // =========================================================================
    logic load_use_ex1;

    assign load_use_ex1 = id_ex_mem_rd
                        && (id_ex_rd_addr != 5'h0)
                        && ((id_ex_rd_addr == if_id_rs1_addr)
                          || (id_ex_rd_addr == if_id_rs2_addr));

    // =========================================================================
    // Forwarding selects (3-way: EX2 > WB > regfile)
    // EX2 source = ex_mem_reg (registered EX1 result, 1 cycle behind EX1)
    // WB  source = mem_wb_reg (2 cycles behind EX1; covers load-use after stall)
    // =========================================================================

    // ALU operand A (rs1 in EX1)
    always_comb begin
        if (ex_mem_reg_wr_en && !ex_mem_mem_rd && (ex_mem_rd_addr != 5'h0)
                             && (ex_mem_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b01;   // EX2→EX1 (registered result from last cycle)
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b10;   // WB→EX1
        end else begin
            fwd_a_sel = 2'b00;
        end
    end

    // ALU operand B (rs2 in EX1)
    always_comb begin
        if (ex_mem_reg_wr_en && !ex_mem_mem_rd && (ex_mem_rd_addr != 5'h0)
                             && (ex_mem_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b01;   // EX2→EX1
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b10;   // WB→EX1
        end else begin
            fwd_b_sel = 2'b00;
        end
    end

    assign fwd_store_sel = fwd_b_sel;

    // =========================================================================
    // Stall / flush priority logic
    // =========================================================================
    always_comb begin
        stall_pc        = 1'b0;
        stall_if_id     = 1'b0;
        stall_id_ex     = 1'b0;
        stall_ex_mem    = 1'b0;
        stall_ex1_ex2_o = 1'b0;
        flush_if_id     = 1'b0;
        flush_id_ex     = 1'b0;
        flush_ex_mem    = 1'b0;
        flush_ex1_ex2_o = 1'b0;

        if (mem_trap_redirect) begin
            // Priority 0: MEM-stage misaligned trap
            flush_if_id     = 1'b1;
            flush_id_ex     = 1'b1;
            flush_ex1_ex2_o = 1'b1;
            flush_ex_mem    = 1'b1;

        end else if (mem_cache_stall) begin
            // Priority 1: D-cache miss — global freeze
            stall_pc        = 1'b1;
            stall_if_id     = 1'b1;
            stall_id_ex     = 1'b1;
            stall_ex1_ex2_o = 1'b1;
            stall_ex_mem    = 1'b1;

        end else if (ex_pc_redirect) begin
            // Priority 2: PC redirect (registered) — flush ghost + ID + IF
            flush_if_id     = 1'b1;
            flush_id_ex     = 1'b1;
            flush_ex1_ex2_o = 1'b1;
            flush_ex_mem    = 1'b1;

        end else if (id_jal_taken) begin
            // Priority 3: JAL resolved in ID — flush IF only
            flush_if_id     = 1'b1;

        end else if (load_use_ex1) begin
            // Priority 4: Load in EX1, consumer in ID — stall front-end, bubble into EX1
            // Load advances normally (EX1→EX2→MEM); consumer waits 1 cycle in ID.
            // After stall: load data in mem_wb_reg when consumer reaches EX1 → WB fwd.
            stall_pc        = 1'b1;
            stall_if_id     = 1'b1;
            flush_id_ex     = 1'b1;

        end else if (if_cache_stall) begin
            // Priority 6: I-cache miss — stall PC only
            stall_pc        = 1'b1;
        end
    end

endmodule
