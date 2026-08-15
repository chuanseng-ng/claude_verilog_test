// rv32i_pipeline_ex2.sv
// RV32I Pipeline — Execute Stage 2 (EX2)
//
// Owns the pipeline register between EX1 and MEM.
// EX1 is purely combinational; EX2 captures EX1 outputs at the clock edge
// and drives ex_mem_reg_o into the MEM stage.
// This splits the former single EX combinational cone into two independent
// timing windows, targeting ~200 ps WNS improvement on ASAP7.

import rv32i_pipeline_pkg::*;
module rv32i_pipeline_ex2 (
    input  logic          clk_i,
    input  logic          rst_n_i,

    input  logic          stall_ex1_ex2_i,
    input  logic          flush_ex1_ex2_i,

    input  ex1_ex2_reg_t  ex1_ex2_reg_i,

    output ex_mem_reg_t   ex_mem_reg_o
);

    always_ff @(posedge clk_i) begin
        if (!rst_n_i || flush_ex1_ex2_i) begin
            ex_mem_reg_o <= ex_mem_nop();
        end else if (!stall_ex1_ex2_i) begin
            ex_mem_reg_o.pc                <= ex1_ex2_reg_i.pc;
            ex_mem_reg_o.instruction       <= ex1_ex2_reg_i.instruction;
            ex_mem_reg_o.alu_result        <= ex1_ex2_reg_i.alu_result;
            ex_mem_reg_o.mem_wdata_aligned <= ex1_ex2_reg_i.mem_wdata_aligned;
            ex_mem_reg_o.mem_wstrb         <= ex1_ex2_reg_i.mem_wstrb;
            ex_mem_reg_o.csr_rdata         <= ex1_ex2_reg_i.csr_rdata;
            ex_mem_reg_o.rd_addr           <= ex1_ex2_reg_i.rd_addr;
            ex_mem_reg_o.reg_wr_en         <= ex1_ex2_reg_i.reg_wr_en;
            ex_mem_reg_o.mem_rd            <= ex1_ex2_reg_i.mem_rd;
            ex_mem_reg_o.mem_wr            <= ex1_ex2_reg_i.mem_wr;
            ex_mem_reg_o.mem_size          <= ex1_ex2_reg_i.mem_size;
            ex_mem_reg_o.mem_unsigned      <= ex1_ex2_reg_i.mem_unsigned;
            ex_mem_reg_o.csr_access        <= ex1_ex2_reg_i.csr_access;
            ex_mem_reg_o.csr_addr          <= ex1_ex2_reg_i.csr_addr;
            ex_mem_reg_o.csr_wdata         <= ex1_ex2_reg_i.csr_wdata;
            ex_mem_reg_o.jump              <= ex1_ex2_reg_i.jump;
            ex_mem_reg_o.jalr              <= ex1_ex2_reg_i.jalr;
            ex_mem_reg_o.pc_redirect       <= ex1_ex2_reg_i.pc_redirect;
            ex_mem_reg_o.pc_target         <= ex1_ex2_reg_i.pc_target;
            ex_mem_reg_o.trap_valid        <= ex1_ex2_reg_i.trap_valid;
            ex_mem_reg_o.trap_cause        <= ex1_ex2_reg_i.trap_cause;
            ex_mem_reg_o.valid             <= ex1_ex2_reg_i.valid;
        end
    end

endmodule

