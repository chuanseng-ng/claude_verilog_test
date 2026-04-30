// rv32i_hazard_unit.sv
// RV32I Pipeline Hazard Detection Unit (Phase 3)
//
// Phase 3 changes vs Phase 2:
//   - if_axi_stall  → if_cache_stall  (I-cache miss signal)
//   - mem_axi_stall → mem_cache_stall (D-cache miss signal)
//   - Stall propagation logic unchanged
//
// Purely combinational. Detects data and control hazards and generates
// stall, flush, and forwarding-select signals for the 5-stage pipeline.
//
// Priority (highest → lowest):
//   1. mem_cache_stall → global freeze (stall all stages)
//   2. ex_pc_redirect  → flush IF/ID and ID/EX
//   3. id_jal_taken    → flush IF/ID only
//   4. load-use hazard → stall PC+IF/ID; flush ID/EX (insert bubble)
//   5. if_cache_stall  → stall PC+IF/ID

module rv32i_hazard_unit (
    // From ID/EX register (instruction currently in EX)
    input  logic [4:0]  id_ex_rs1_addr,
    input  logic [4:0]  id_ex_rs2_addr,
    input  logic [4:0]  id_ex_rd_addr,
    input  logic        id_ex_mem_rd,
    input  logic        id_ex_reg_wr_en,

    // From EX/MEM register (instruction currently in MEM)
    input  logic [4:0]  ex_mem_rd_addr,
    input  logic        ex_mem_reg_wr_en,
    input  logic        ex_mem_mem_rd,

    // From MEM/WB register (instruction currently in WB)
    input  logic [4:0]  mem_wb_rd_addr,
    input  logic        mem_wb_reg_wr_en,

    // From IF/ID register (instruction currently in ID — for load-use detection)
    input  logic [4:0]  if_id_rs1_addr,
    input  logic [4:0]  if_id_rs2_addr,

    // Cache stall indicators (Phase 3: renamed from axi_stall)
    input  logic        if_cache_stall,    // IF stage: I-cache miss
    input  logic        mem_cache_stall,   // MEM stage: D-cache miss

    // Branch/jump/trap flush (from EX stage)
    input  logic        ex_pc_redirect,    // Flush needed: taken branch/jump/trap

    // Misaligned trap flush (from MEM stage — higher priority than EX redirect)
    input  logic        mem_trap_redirect, // MEM-stage misalign: flush EX+ID+IF

    // JAL flush (from ID stage)
    input  logic        id_jal_taken,      // JAL detected in ID → flush IF only

    // Outputs — pipeline register control
    output logic        stall_pc,          // Hold PC register
    output logic        stall_if_id,       // Hold IF/ID register
    output logic        stall_id_ex,       // Hold ID/EX register
    output logic        stall_ex_mem,      // Hold EX/MEM register
    output logic        flush_if_id,       // Clear IF/ID (insert NOP)
    output logic        flush_id_ex,       // Clear ID/EX (insert NOP)
    output logic        flush_ex_mem,      // Clear EX/MEM (squash EX instruction)

    // Outputs — forwarding mux selects (for instruction in EX stage)
    // Encoding: 2'b00=regfile, 2'b01=EX/MEM (EX→EX), 2'b10=MEM/WB (MEM→EX)
    output logic [1:0]  fwd_a_sel,         // ALU operand A forwarding select
    output logic [1:0]  fwd_b_sel,         // ALU operand B forwarding select
    output logic [1:0]  fwd_store_sel      // Store data (rs2) forwarding select
);

    // =========================================================================
    // Load-use hazard detection
    // =========================================================================
    logic load_use_hazard;
    assign load_use_hazard = id_ex_mem_rd
                           && (id_ex_rd_addr != 5'h0)
                           && ((id_ex_rd_addr == if_id_rs1_addr)
                             || (id_ex_rd_addr == if_id_rs2_addr));

    // =========================================================================
    // Forwarding selects
    // =========================================================================

    // ALU operand A (rs1)
    always_comb begin
        if (ex_mem_reg_wr_en && (ex_mem_rd_addr != 5'h0)
                              && (ex_mem_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b01;   // EX→EX: forward from EX/MEM
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b10;   // MEM→EX: forward from MEM/WB
        end else begin
            fwd_a_sel = 2'b00;   // No forwarding
        end
    end

    // ALU operand B (rs2)
    always_comb begin
        if (ex_mem_reg_wr_en && (ex_mem_rd_addr != 5'h0)
                              && (ex_mem_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b01;   // EX→EX
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b10;   // MEM→EX
        end else begin
            fwd_b_sel = 2'b00;
        end
    end

    // Store data forwarding (same as operand B)
    assign fwd_store_sel = fwd_b_sel;

    // =========================================================================
    // Stall / flush priority logic
    // =========================================================================
    always_comb begin
        stall_pc     = 1'b0;
        stall_if_id  = 1'b0;
        stall_id_ex  = 1'b0;
        stall_ex_mem = 1'b0;
        flush_if_id  = 1'b0;
        flush_id_ex  = 1'b0;
        flush_ex_mem = 1'b0;

        if (mem_trap_redirect) begin
            // Priority 0: MEM-stage misaligned trap — flush EX, ID, IF; redirect PC
            flush_if_id  = 1'b1;
            flush_id_ex  = 1'b1;
            flush_ex_mem = 1'b1;

        end else if (mem_cache_stall) begin
            // Priority 1: D-cache miss — global pipeline freeze
            stall_pc     = 1'b1;
            stall_if_id  = 1'b1;
            stall_id_ex  = 1'b1;
            stall_ex_mem = 1'b1;

        end else if (ex_pc_redirect) begin
            // Priority 2: PC redirect (registered) — flush EX ghost + ID + IF
            flush_if_id  = 1'b1;
            flush_id_ex  = 1'b1;
            flush_ex_mem = 1'b1;

        end else if (id_jal_taken) begin
            // Priority 3: JAL resolved in ID — flush IF only
            flush_if_id  = 1'b1;

        end else if (load_use_hazard) begin
            // Priority 4: Load-use hazard — stall IF and ID, insert NOP into EX
            stall_pc     = 1'b1;
            stall_if_id  = 1'b1;
            flush_id_ex  = 1'b1;

        end else if (if_cache_stall) begin
            // Priority 5: I-cache miss — stall PC only.
            // DO NOT stall IF/ID: when stall_if_id=0 and ic_stall_i=1, the IF
            // stage's else-branch naturally inserts a bubble, so the instruction
            // already in IF/ID is issued once into ID and then replaced by NOPs
            // until the miss resolves.  Holding IF/ID would re-issue the same
            // instruction into ID every stall cycle, causing spurious commits.
            stall_pc     = 1'b1;
        end
    end

endmodule
