// rv32i_pipeline_mem.sv
// RV32I Pipeline — Memory (MEM) Stage (Phase 2)
//
// Responsibilities:
//   - Issue AXI-MEM load/store transactions via arbiter
//   - Generate byte write strobes for stores
//   - Extract and sign-extend loaded bytes/halfwords/words
//   - Skip AXI if a trap was taken in EX (trap_valid)
//   - Load the MEM/WB pipeline register

import rv32i_pipeline_pkg::*;

module rv32i_pipeline_mem (
    input  logic        clk,
    input  logic        rst_n,

    // ── EX/MEM pipeline register input ───────────────────────────────────────
    input  ex_mem_reg_t ex_mem_reg_i,

    // ── AXI-MEM channels (to arbiter) ────────────────────────────────────────
    // Read (loads)
    output logic [31:0] mem_araddr_o,
    output logic        mem_arvalid_o,
    input  logic        mem_arready_i,

    input  logic [31:0] mem_rdata_i,
    input  logic [1:0]  mem_rresp_i,
    input  logic        mem_rvalid_i,
    output logic        mem_rready_o,

    // Write (stores)
    output logic [31:0] mem_awaddr_o,
    output logic        mem_awvalid_o,
    input  logic        mem_awready_i,

    output logic [31:0] mem_wdata_o,
    output logic [3:0]  mem_wstrb_o,
    output logic        mem_wvalid_o,
    input  logic        mem_wready_i,

    input  logic        mem_bvalid_i,
    input  logic [1:0]  mem_bresp_i,
    output logic        mem_bready_o,

    // ── AXI stall to hazard unit ──────────────────────────────────────────────
    output logic        mem_axi_stall_o,

    // ── MEM/WB pipeline register output ──────────────────────────────────────
    output mem_wb_reg_t mem_wb_reg_o
);

    // =========================================================================
    // Internal transaction tracking
    // =========================================================================
    // We track whether a memory transaction is in flight.
    // 'mem_pending_q' is set when the AR (or AW+W) request is issued,
    // cleared when the response (rvalid or bvalid) is received.
    logic mem_pending_q;
    logic mem_is_write_q;      // 1=store in flight, 0=load in flight

    // For stores: track AW and W acceptance independently
    logic aw_done_q;           // AW channel accepted
    logic w_done_q;            // W channel accepted

    // Latch EX/MEM data needed after response
    logic [31:0] mem_addr_q;
    logic [2:0]  mem_size_q;
    logic        mem_unsigned_q;

    // =========================================================================
    // Byte-strobe generation (for stores)
    // =========================================================================
    logic [31:0] store_addr;
    logic [2:0]  store_size;
    logic [3:0]  wstrb;
    logic [31:0] wdata_aligned;

    assign store_addr = ex_mem_reg_i.alu_result;
    assign store_size = ex_mem_reg_i.mem_size;

    always_comb begin
        wstrb         = 4'b1111;
        wdata_aligned = ex_mem_reg_i.rs2_data;

        case (store_size)
            3'b000: begin  // Byte store
                case (store_addr[1:0])
                    2'b00: begin wstrb = 4'b0001; wdata_aligned = {24'h0, ex_mem_reg_i.rs2_data[7:0]}; end
                    2'b01: begin wstrb = 4'b0010; wdata_aligned = {16'h0, ex_mem_reg_i.rs2_data[7:0], 8'h0}; end
                    2'b10: begin wstrb = 4'b0100; wdata_aligned = {8'h0,  ex_mem_reg_i.rs2_data[7:0], 16'h0}; end
                    2'b11: begin wstrb = 4'b1000; wdata_aligned = {ex_mem_reg_i.rs2_data[7:0], 24'h0}; end
                endcase
            end
            3'b001: begin  // Halfword store
                case (store_addr[1])
                    1'b0: begin wstrb = 4'b0011; wdata_aligned = {16'h0, ex_mem_reg_i.rs2_data[15:0]}; end
                    1'b1: begin wstrb = 4'b1100; wdata_aligned = {ex_mem_reg_i.rs2_data[15:0], 16'h0}; end
                endcase
            end
            3'b010: begin  // Word store
                wstrb         = 4'b1111;
                wdata_aligned = ex_mem_reg_i.rs2_data;
            end
            default: begin
                wstrb         = 4'b0000;
                wdata_aligned = 32'h0;
            end
        endcase
    end

    // =========================================================================
    // Load data extraction and sign extension
    // =========================================================================
    logic [31:0] mem_rdata_extracted;

    always_comb begin
        mem_rdata_extracted = 32'h0;

        case (mem_size_q)
            3'b000: begin  // Byte load
                case (mem_addr_q[1:0])
                    2'b00: mem_rdata_extracted = mem_unsigned_q ? {24'h0, mem_rdata_i[7:0]}   : {{24{mem_rdata_i[7]}},   mem_rdata_i[7:0]};
                    2'b01: mem_rdata_extracted = mem_unsigned_q ? {24'h0, mem_rdata_i[15:8]}  : {{24{mem_rdata_i[15]}},  mem_rdata_i[15:8]};
                    2'b10: mem_rdata_extracted = mem_unsigned_q ? {24'h0, mem_rdata_i[23:16]} : {{24{mem_rdata_i[23]}},  mem_rdata_i[23:16]};
                    2'b11: mem_rdata_extracted = mem_unsigned_q ? {24'h0, mem_rdata_i[31:24]} : {{24{mem_rdata_i[31]}},  mem_rdata_i[31:24]};
                endcase
            end
            3'b001: begin  // Halfword load
                case (mem_addr_q[1])
                    1'b0: mem_rdata_extracted = mem_unsigned_q ? {16'h0, mem_rdata_i[15:0]}  : {{16{mem_rdata_i[15]}},  mem_rdata_i[15:0]};
                    1'b1: mem_rdata_extracted = mem_unsigned_q ? {16'h0, mem_rdata_i[31:16]} : {{16{mem_rdata_i[31]}},  mem_rdata_i[31:16]};
                endcase
            end
            3'b010: begin  // Word load
                mem_rdata_extracted = mem_rdata_i;
            end
            default: mem_rdata_extracted = 32'h0;
        endcase
    end

    // =========================================================================
    // AXI-MEM channel control
    // =========================================================================
    // Determine if this stage needs a memory transaction
    logic need_mem_txn;
    assign need_mem_txn = ex_mem_reg_i.valid
                        && !ex_mem_reg_i.trap_valid
                        && (ex_mem_reg_i.mem_rd || ex_mem_reg_i.mem_wr);

    // mem_axi_stall: high as soon as a memory transaction is needed until the
    // response arrives.  Using mem_pending_q alone was too late: pending_q is
    // only set on the posedge *after* the AR/AW handshake, so in the cycle
    // that arvalid && arready fires the stall was 0 and the hazard unit
    // allowed EX/MEM to advance — discarding the load/store before rvalid/bvalid.
    assign mem_axi_stall_o = need_mem_txn
                           && !((ex_mem_reg_i.mem_rd && mem_rvalid_i && mem_rready_o)
                              || (ex_mem_reg_i.mem_wr && mem_bvalid_i && mem_bready_o));

    // AXI outputs
    assign mem_araddr_o  = ex_mem_reg_i.alu_result;
    assign mem_arvalid_o = need_mem_txn && ex_mem_reg_i.mem_rd && !mem_pending_q;
    assign mem_rready_o  = 1'b1;

    assign mem_awaddr_o  = ex_mem_reg_i.alu_result;
    assign mem_awvalid_o = need_mem_txn && ex_mem_reg_i.mem_wr && !mem_pending_q && !aw_done_q;
    assign mem_wdata_o   = wdata_aligned;
    assign mem_wstrb_o   = wstrb;
    // mem_wvalid_o: assert until W handshake completes, independent of mem_pending_q
    assign mem_wvalid_o  = need_mem_txn && ex_mem_reg_i.mem_wr && !w_done_q;
    assign mem_bready_o  = 1'b1;

    // =========================================================================
    // Pending transaction register
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mem_pending_q   <= 1'b0;
            mem_is_write_q  <= 1'b0;
            aw_done_q       <= 1'b0;
            w_done_q        <= 1'b0;
            mem_addr_q      <= 32'h0;
            mem_size_q      <= 3'h0;
            mem_unsigned_q  <= 1'b0;
        end else begin
            if (!mem_pending_q && need_mem_txn) begin
                // Start new transaction
                if (ex_mem_reg_i.mem_rd && mem_arready_i) begin
                    mem_pending_q  <= 1'b1;
                    mem_is_write_q <= 1'b0;
                    aw_done_q      <= 1'b0;
                    w_done_q       <= 1'b0;
                    mem_addr_q     <= ex_mem_reg_i.alu_result;
                    mem_size_q     <= ex_mem_reg_i.mem_size;
                    mem_unsigned_q <= ex_mem_reg_i.mem_unsigned;
                end else if (ex_mem_reg_i.mem_wr && mem_awready_i && mem_wready_i) begin
                    // Both AW and W accepted in same cycle
                    mem_pending_q  <= 1'b1;
                    mem_is_write_q <= 1'b1;
                    aw_done_q      <= 1'b1;
                    w_done_q       <= 1'b1;
                    mem_addr_q     <= ex_mem_reg_i.alu_result;
                    mem_size_q     <= ex_mem_reg_i.mem_size;
                    mem_unsigned_q <= 1'b0;
                end else if (ex_mem_reg_i.mem_wr && (mem_awready_i || mem_wready_i)) begin
                    // Partial AW/W acceptance — track individually
                    mem_pending_q  <= 1'b1;
                    mem_is_write_q <= 1'b1;
                    aw_done_q      <= mem_awready_i;
                    w_done_q       <= mem_wready_i;
                    mem_addr_q     <= ex_mem_reg_i.alu_result;
                    mem_size_q     <= ex_mem_reg_i.mem_size;
                    mem_unsigned_q <= 1'b0;
                end
            end else if (mem_pending_q) begin
                // Track AW/W acceptance for writes in progress
                if (mem_is_write_q) begin
                    if (mem_awvalid_o && mem_awready_i) begin
                        aw_done_q <= 1'b1;
                    end
                    if (mem_wvalid_o && mem_wready_i) begin
                        w_done_q <= 1'b1;
                    end
                end
                // Clear when response received
                if (!mem_is_write_q && mem_rvalid_i && mem_rready_o) begin
                    mem_pending_q <= 1'b0;
                end else if (mem_is_write_q && mem_bvalid_i && mem_bready_o) begin
                    mem_pending_q <= 1'b0;
                    aw_done_q     <= 1'b0;
                    w_done_q      <= 1'b0;
                end
            end
        end
    end

    // =========================================================================
    // MEM/WB Pipeline Register
    // =========================================================================
    // We advance MEM/WB when:
    //   (a) No memory operation needed — pass through directly
    //   (b) Load response received (rvalid)
    //   (c) Store response received (bvalid)
    //   (d) Trap instruction — pass through with trap info (no AXI)

    logic mem_done;
    assign mem_done = !need_mem_txn                           // no AXI needed
                   || (ex_mem_reg_i.mem_rd && mem_rvalid_i && mem_rready_o)
                   || (ex_mem_reg_i.mem_wr && mem_bvalid_i && mem_bready_o)
                   || ex_mem_reg_i.trap_valid;

    // mem_rdata to capture: use combinational rdata when rvalid fires
    logic [31:0] captured_rdata;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            captured_rdata <= 32'h0;
        end else if (mem_rvalid_i && mem_rready_o) begin
            captured_rdata <= mem_rdata_extracted;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mem_wb_reg_o <= mem_wb_nop();
        end else if (mem_done) begin
            if (!ex_mem_reg_i.valid) begin
                mem_wb_reg_o <= mem_wb_nop();
            end else begin
                mem_wb_reg_o.pc          <= ex_mem_reg_i.pc;
                mem_wb_reg_o.instruction <= ex_mem_reg_i.instruction;
                mem_wb_reg_o.alu_result  <= ex_mem_reg_i.alu_result;
                // For loads: use mem_rdata_extracted if rvalid just arrived,
                // else use the previously captured value
                mem_wb_reg_o.mem_rdata   <= (mem_rvalid_i && mem_rready_o)
                                          ? mem_rdata_extracted
                                          : captured_rdata;
                mem_wb_reg_o.csr_rdata   <= ex_mem_reg_i.csr_rdata;
                mem_wb_reg_o.rd_addr     <= ex_mem_reg_i.rd_addr;
                mem_wb_reg_o.reg_wr_en   <= ex_mem_reg_i.reg_wr_en && !ex_mem_reg_i.trap_valid;
                mem_wb_reg_o.mem_rd      <= ex_mem_reg_i.mem_rd;
                mem_wb_reg_o.csr_access  <= ex_mem_reg_i.csr_access;
                mem_wb_reg_o.jump        <= ex_mem_reg_i.jump;
                mem_wb_reg_o.trap_valid  <= ex_mem_reg_i.trap_valid;
                mem_wb_reg_o.trap_cause  <= ex_mem_reg_i.trap_cause;
                mem_wb_reg_o.valid       <= 1'b1;
            end
        end
        // else: stalled waiting for AXI — hold current MEM/WB value
    end

endmodule
