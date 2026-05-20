// rv32i_pipeline_mem.sv
// RV32I Pipeline — Memory (MEM) Stage (Phase 3)
//
// Phase 3 changes vs Phase 2:
//   - AXI4-Lite channels replaced by D-cache interface
//   - mem_axi_stall_o replaced by mem_cache_stall_o
//   (FENCE.I is handled entirely in the EX stage; no MEM-stage changes needed)
//
// Responsibilities:
//   - Forward load/store operations to D-cache
//   - Generate write strobe (byte/halfword/word) for stores
//   - Extract and sign-extend loaded data from D-cache
//   - Skip memory access if a trap was taken in EX (trap_valid)
//   - Load the MEM/WB pipeline register


import rv32i_pipeline_pkg::*;
module rv32i_pipeline_mem(
    input  logic        clk,
    input  logic        rst_n,

    // ── EX/MEM pipeline register input ───────────────────────────────────────
    input  ex_mem_reg_t ex_mem_reg_i,

    // ── Trap handler base address (for misalign redirect) ────────────────────
    input  logic [31:0] mtvec_i,

    // ── D-Cache interface ─────────────────────────────────────────────────────
    output logic [31:0] dc_addr_o,     // Memory address
    output logic        dc_valid_o,    // Access valid
    output logic        dc_we_o,       // Write enable (1=store, 0=load)
    output logic [31:0] dc_wdata_o,    // Write data (byte-aligned by this stage)
    output logic [3:0]  dc_wstrb_o,    // Write byte strobes
    input  logic [31:0] dc_rdata_i,    // Read data from D-cache
    input  logic        dc_stall_i,    // D-cache miss — stall

    // ── Cache stall output to hazard unit ─────────────────────────────────────
    output logic        mem_cache_stall_o,

    // ── MEM-stage misaligned trap outputs ────────────────────────────────────
    output logic        mem_trap_redirect_o,   // 1 = flush IF+ID+EX, redirect PC
    output logic [31:0] mem_trap_target_o,     // Redirect target (mtvec)
    output logic        mem_trap_entry_o,      // Update CSR file this cycle
    output logic [31:0] mem_trap_pc_o,         // mepc value
    output logic [31:0] mem_trap_cause_o,      // mcause value

    // ── MEM/WB pipeline register output ──────────────────────────────────────
    output mem_wb_reg_t mem_wb_reg_o
);

    // =========================================================================
    // Load data extraction and sign extension
    // =========================================================================
    logic [31:0] mem_rdata_extracted;
    logic [31:0] load_addr;
    logic [2:0]  load_size;
    logic        load_unsigned;

    assign load_addr     = ex_mem_reg_i.alu_result;
    assign load_size     = ex_mem_reg_i.mem_size;
    assign load_unsigned = ex_mem_reg_i.mem_unsigned;

    always_comb begin
        mem_rdata_extracted = 32'h0;

        case (load_size)
            3'b000: begin  // Byte load
                case (load_addr[1:0])
                    2'b00: mem_rdata_extracted = load_unsigned ? {24'h0, dc_rdata_i[7:0]}   : {{24{dc_rdata_i[7]}},   dc_rdata_i[7:0]};
                    2'b01: mem_rdata_extracted = load_unsigned ? {24'h0, dc_rdata_i[15:8]}  : {{24{dc_rdata_i[15]}},  dc_rdata_i[15:8]};
                    2'b10: mem_rdata_extracted = load_unsigned ? {24'h0, dc_rdata_i[23:16]} : {{24{dc_rdata_i[23]}},  dc_rdata_i[23:16]};
                    2'b11: mem_rdata_extracted = load_unsigned ? {24'h0, dc_rdata_i[31:24]} : {{24{dc_rdata_i[31]}},  dc_rdata_i[31:24]};
                endcase
            end
            3'b001: begin  // Halfword load
                case (load_addr[1])
                    1'b0: mem_rdata_extracted = load_unsigned ? {16'h0, dc_rdata_i[15:0]}  : {{16{dc_rdata_i[15]}},  dc_rdata_i[15:0]};
                    1'b1: mem_rdata_extracted = load_unsigned ? {16'h0, dc_rdata_i[31:16]} : {{16{dc_rdata_i[31]}},  dc_rdata_i[31:16]};
                endcase
            end
            3'b010: begin  // Word load
                mem_rdata_extracted = dc_rdata_i;
            end
            default: mem_rdata_extracted = 32'h0;
        endcase
    end

    // =========================================================================
    // Misalignment detection (moved from EX to break alu_result data dependency
    // on the EX-stage setup critical path)
    // =========================================================================
    logic        mem_misaligned_load, mem_misaligned_store, mem_misaligned;
    logic [31:0] mem_trap_cause_d;

    always_comb begin
        mem_misaligned_load  = 1'b0;
        mem_misaligned_store = 1'b0;

        if (ex_mem_reg_i.mem_rd) begin
            case (ex_mem_reg_i.mem_size)
                3'b001: mem_misaligned_load = ex_mem_reg_i.alu_result[0];
                3'b010: mem_misaligned_load = |ex_mem_reg_i.alu_result[1:0];
                default: mem_misaligned_load = 1'b0;
            endcase
        end

        if (ex_mem_reg_i.mem_wr) begin
            case (ex_mem_reg_i.mem_size)
                3'b001: mem_misaligned_store = ex_mem_reg_i.alu_result[0];
                3'b010: mem_misaligned_store = |ex_mem_reg_i.alu_result[1:0];
                default: mem_misaligned_store = 1'b0;
            endcase
        end
    end

    assign mem_misaligned  = ex_mem_reg_i.valid && !ex_mem_reg_i.trap_valid
                           && (mem_misaligned_load || mem_misaligned_store);
    assign mem_trap_cause_d = mem_misaligned_load ? 32'h0000_0004   // mcause=4: load misaligned
                                                  : 32'h0000_0006;  // mcause=6: store misaligned

    // MEM-stage trap outputs (to hazard unit, IF stage, and CSR file)
    assign mem_trap_redirect_o = mem_misaligned;
    assign mem_trap_target_o   = mtvec_i;
    assign mem_trap_entry_o    = mem_misaligned;
    assign mem_trap_pc_o       = ex_mem_reg_i.pc;
    assign mem_trap_cause_o    = mem_trap_cause_d;

    // =========================================================================
    // D-Cache interface
    // =========================================================================
    logic need_mem_access;
    assign need_mem_access = ex_mem_reg_i.valid
                           && !ex_mem_reg_i.trap_valid
                           && !mem_misaligned
                           && (ex_mem_reg_i.mem_rd || ex_mem_reg_i.mem_wr);

    assign dc_addr_o  = ex_mem_reg_i.alu_result;
    assign dc_valid_o = need_mem_access;
    assign dc_we_o    = ex_mem_reg_i.mem_wr;
    assign dc_wdata_o = ex_mem_reg_i.mem_wdata_aligned;
    assign dc_wstrb_o = ex_mem_reg_i.mem_wstrb;

    // Stall: D-cache miss when a memory access is needed
    assign mem_cache_stall_o = need_mem_access && dc_stall_i;

    // =========================================================================
    // MEM/WB Pipeline Register
    // =========================================================================
    // Advance MEM/WB when:
    //   (a) No memory operation needed — pass through
    //   (b) D-cache returns data (dc_stall_i=0)
    //   (c) Trap taken — pass through without memory access

    logic mem_done;
    assign mem_done = !need_mem_access     // No D-cache access needed
                   || !dc_stall_i          // D-cache hit (data available)
                   || ex_mem_reg_i.trap_valid; // Trap bypasses memory

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            mem_wb_reg_o <= mem_wb_nop();
        end else if (mem_done) begin
            if (!ex_mem_reg_i.valid) begin
                mem_wb_reg_o <= mem_wb_nop();
            end else begin
                mem_wb_reg_o.pc          <= ex_mem_reg_i.pc;
                mem_wb_reg_o.instruction <= ex_mem_reg_i.instruction;
                mem_wb_reg_o.alu_result  <= ex_mem_reg_i.alu_result;
                mem_wb_reg_o.mem_rdata   <= mem_rdata_extracted;
                mem_wb_reg_o.csr_rdata   <= ex_mem_reg_i.csr_rdata;
                mem_wb_reg_o.rd_addr     <= ex_mem_reg_i.rd_addr;
                mem_wb_reg_o.reg_wr_en   <= ex_mem_reg_i.reg_wr_en
                                           && !ex_mem_reg_i.trap_valid && !mem_misaligned;
                mem_wb_reg_o.mem_rd      <= ex_mem_reg_i.mem_rd && !mem_misaligned;
                mem_wb_reg_o.csr_access  <= ex_mem_reg_i.csr_access;
                mem_wb_reg_o.jump        <= ex_mem_reg_i.jump;
                mem_wb_reg_o.trap_valid  <= ex_mem_reg_i.trap_valid || mem_misaligned;
                mem_wb_reg_o.trap_cause  <= mem_misaligned ? mem_trap_cause_d
                                                           : ex_mem_reg_i.trap_cause;
                mem_wb_reg_o.valid       <= 1'b1;
            end
        end else begin
            // D-cache miss — insert bubble into WB so WB does not re-commit the
            // previous instruction on every stall cycle (spurious commit_valid_o).
            // The load/store instruction will enter MEM/WB on the cycle mem_done fires.
            mem_wb_reg_o <= mem_wb_nop();
        end
    end

endmodule
