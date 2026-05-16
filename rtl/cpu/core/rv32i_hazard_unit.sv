// rv32i_hazard_unit.sv
// RV32I Pipeline Hazard Detection Unit (EX2 retiming)
//
// Extended for 6-stage view: IF / ID / EX1 / EX2(reg) / MEM / WB
// EX2 is a registered pass-through; EX1 is purely combinational.
//
// Forwarding encoding (fwd_*_sel):
//   2'b00 = register file (no forwarding)
//   2'b01 = EX2 result (ex_mem_reg, 2 cycles behind EX1a after Run-17 split)
//   2'b10 = WB  result (mem_wb_reg)
//   2'b11 = EX1b result (ex1a_ex1b_reg, 1 cycle behind EX1a) — highest priority
//
// Priority (highest → lowest):
//   1. mem_trap_redirect  → flush EX2, EX1b, EX1a, ID, IF
//   2. mem_cache_stall    → global freeze
//   3. ex_pc_redirect     → flush EX2, EX1b, EX1a, ID, IF
//   4. id_jal_taken       → flush IF only
//   5. load_use_ex1       → stall IF,ID; flush ID→EX1a (bubble); load advances
//   6. if_cache_stall     → stall PC only

module rv32i_hazard_unit (
    // From ID/EX register (instruction currently in EX1a)
    input  logic [4:0]  id_ex_rs1_addr,
    input  logic [4:0]  id_ex_rs2_addr,
    input  logic [4:0]  id_ex_rd_addr,
    input  logic        id_ex_mem_rd,
    input  logic        id_ex_reg_wr_en,

    // From EX1b register (ex1a_ex1b_reg — instruction in EX1b, 1 cycle behind EX1a)
    input  logic [4:0]  ex1b_rd_addr,
    input  logic        ex1b_reg_wr_en,
    input  logic        ex1b_mem_rd,

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
    output logic        stall_ex1a_ex1b_o,  // EX1a/EX1b FF stall (Run 17)
    output logic        flush_if_id,
    output logic        flush_id_ex,
    output logic        flush_ex_mem,
    output logic        flush_ex1_ex2_o,
    output logic        flush_ex1a_ex1b_o,  // EX1a/EX1b FF flush (Run 17)

    // Outputs — forwarding mux selects (for instruction in EX1a)
    // Encoding: 2'b00=regfile, 2'b01=EX2, 2'b10=WB, 2'b11=EX1b (highest)
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
    // Forwarding selects (4-way: EX1b > EX2 > WB > regfile)
    // EX1b source = ex1a_ex1b_reg (1 cycle behind EX1a — highest priority)
    // EX2  source = ex_mem_reg    (2 cycles behind EX1a)
    // WB   source = mem_wb_reg    (covers load-use after stall)
    // =========================================================================

    // ALU operand A (rs1 in EX1a)
    always_comb begin
        if (ex1b_reg_wr_en && !ex1b_mem_rd && (ex1b_rd_addr != 5'h0)
                           && (ex1b_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b11;   // EX1b→EX1a (highest priority)
        end else if (ex_mem_reg_wr_en && !ex_mem_mem_rd && (ex_mem_rd_addr != 5'h0)
                                      && (ex_mem_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b01;   // EX2→EX1a
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs1_addr)) begin
            fwd_a_sel = 2'b10;   // WB→EX1a
        end else begin
            fwd_a_sel = 2'b00;
        end
    end

    // ALU operand B (rs2 in EX1a)
    always_comb begin
        if (ex1b_reg_wr_en && !ex1b_mem_rd && (ex1b_rd_addr != 5'h0)
                           && (ex1b_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b11;   // EX1b→EX1a
        end else if (ex_mem_reg_wr_en && !ex_mem_mem_rd && (ex_mem_rd_addr != 5'h0)
                                      && (ex_mem_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b01;   // EX2→EX1a
        end else if (mem_wb_reg_wr_en && (mem_wb_rd_addr != 5'h0)
                                      && (mem_wb_rd_addr == id_ex_rs2_addr)) begin
            fwd_b_sel = 2'b10;   // WB→EX1a
        end else begin
            fwd_b_sel = 2'b00;
        end
    end

    assign fwd_store_sel = fwd_b_sel;

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
        flush_if_id        = 1'b0;
        flush_id_ex        = 1'b0;
        flush_ex_mem       = 1'b0;
        flush_ex1_ex2_o    = 1'b0;
        flush_ex1a_ex1b_o  = 1'b0;

        if (mem_trap_redirect) begin
            // Priority 0: MEM-stage misaligned trap
            flush_if_id        = 1'b1;
            flush_id_ex        = 1'b1;
            flush_ex1a_ex1b_o  = 1'b1;
            flush_ex1_ex2_o    = 1'b1;
            flush_ex_mem       = 1'b1;

        end else if (mem_cache_stall) begin
            // Priority 1: D-cache miss — global freeze
            stall_pc           = 1'b1;
            stall_if_id        = 1'b1;
            stall_id_ex        = 1'b1;
            stall_ex1a_ex1b_o  = 1'b1;
            stall_ex1_ex2_o    = 1'b1;
            stall_ex_mem       = 1'b1;

        end else if (ex_pc_redirect) begin
            // Priority 2: PC redirect (registered from EX1b) — flush EX1b, EX1a, ID, IF
            flush_if_id        = 1'b1;
            flush_id_ex        = 1'b1;
            flush_ex1a_ex1b_o  = 1'b1;
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

        end else if (if_cache_stall) begin
            // Priority 5: I-cache miss — stall PC only
            stall_pc           = 1'b1;
        end
    end

endmodule
