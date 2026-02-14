// rv32i_hazard_unit.sv
// RV32I Pipeline Hazard Detection Unit (Phase 2)
//
// Purely combinational. Detects data and control hazards and generates
// stall, flush, and forwarding-select signals for the 5-stage pipeline.
//
// Priority (highest → lowest):
//   1. mem_axi_stall  → global freeze (stall all stages)
//   2. ex_pc_redirect → flush IF/ID and ID/EX
//   3. id_jal_taken   → flush IF/ID only
//   4. load-use hazard→ stall PC+IF/ID; flush ID/EX (insert bubble)
//   5. if_axi_stall   → stall PC+IF/ID

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

    // AXI stall indicators (from pipeline stages / arbiter)
    input  logic        if_axi_stall,    // IF stage is waiting for instruction fetch
    input  logic        mem_axi_stall,   // MEM stage is waiting for load/store

    // Branch/jump/trap flush (from EX stage)
    input  logic        ex_pc_redirect,  // Flush needed: taken branch / jump / trap

    // JAL flush (from ID stage)
    input  logic        id_jal_taken,    // JAL detected in ID → flush IF only

    // Outputs — pipeline register control
    output logic        stall_pc,        // Hold PC register
    output logic        stall_if_id,     // Hold IF/ID register
    output logic        stall_id_ex,     // Hold ID/EX register
    output logic        stall_ex_mem,    // Hold EX/MEM register
    output logic        flush_if_id,     // Clear IF/ID (insert NOP)
    output logic        flush_id_ex,     // Clear ID/EX (insert NOP)

    // Outputs — forwarding mux selects (for instruction in EX stage)
    // Encoding: 2'b00=regfile, 2'b01=EX/MEM (EX→EX), 2'b10=MEM/WB (MEM→EX)
    output logic [1:0]  fwd_a_sel,       // ALU operand A forwarding select
    output logic [1:0]  fwd_b_sel,       // ALU operand B forwarding select
    output logic [1:0]  fwd_store_sel    // Store data (rs2) forwarding select
);

    // =========================================================================
    // Load-use hazard detection
    // Triggered when the instruction in EX is a load AND the instruction
    // currently in ID reads the load's destination register.
    // =========================================================================
    logic load_use_hazard;
    assign load_use_hazard = id_ex_mem_rd
                           && (id_ex_rd_addr != 5'h0)
                           && ((id_ex_rd_addr == if_id_rs1_addr)
                             || (id_ex_rd_addr == if_id_rs2_addr));

    // =========================================================================
    // Forwarding selects
    // Compare the EX-stage instruction's source registers (id_ex_rs*_addr)
    // against the destination registers of instructions ahead in the pipeline.
    // EX/MEM takes priority over MEM/WB when both match (more recent write wins).
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
            fwd_a_sel = 2'b00;   // No forwarding — use register file output
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

    // Store data (rs2 as write data) — same forwarding condition as fwd_b_sel
    assign fwd_store_sel = fwd_b_sel;

    // =========================================================================
    // Stall / flush priority logic
    // =========================================================================
    always_comb begin
        // Defaults: no stalls, no flushes
        stall_pc    = 1'b0;
        stall_if_id = 1'b0;
        stall_id_ex = 1'b0;
        stall_ex_mem = 1'b0;
        flush_if_id = 1'b0;
        flush_id_ex = 1'b0;

        if (mem_axi_stall) begin
            // Priority 1: MEM AXI stall — global pipeline freeze
            // All stages hold their current values; no flushes
            stall_pc     = 1'b1;
            stall_if_id  = 1'b1;
            stall_id_ex  = 1'b1;
            stall_ex_mem = 1'b1;

        end else if (ex_pc_redirect) begin
            // Priority 2: PC redirect (taken branch, JALR, trap, interrupt, MRET)
            // Flush the two instructions that were speculatively fetched/decoded
            flush_if_id  = 1'b1;
            flush_id_ex  = 1'b1;

        end else if (id_jal_taken) begin
            // Priority 3: JAL resolved in ID stage
            // Flush only the speculatively fetched instruction in IF
            flush_if_id  = 1'b1;

        end else if (load_use_hazard) begin
            // Priority 4: Load-use hazard — stall IF and ID, insert NOP into EX
            stall_pc     = 1'b1;
            stall_if_id  = 1'b1;
            // flush_id_ex inserts a bubble so EX sees a NOP next cycle
            flush_id_ex  = 1'b1;

        end else if (if_axi_stall) begin
            // Priority 5: IF AXI stall — instruction fetch in progress
            stall_pc     = 1'b1;
            stall_if_id  = 1'b1;
        end
    end

endmodule
