// RV32I Register File - 32 x 32-bit registers with x0 hardwired to zero
module rv32i_regfile
    import rv32i_pkg::*;
(
    input  logic                      clk,
    input  logic                      rst_n,

    // Read port 1 (rs1)
    input  logic [REG_ADDR_WIDTH-1:0] rs1_addr,
    output logic [XLEN-1:0]           rs1_data,

    // Read port 2 (rs2)
    input  logic [REG_ADDR_WIDTH-1:0] rs2_addr,
    output logic [XLEN-1:0]           rs2_data,

    // Write port (rd)
    input  logic [REG_ADDR_WIDTH-1:0] rd_addr,
    input  logic [XLEN-1:0]           rd_data,
    input  logic                      rd_we,

    // Debug interface - direct access to all registers
    input  logic [REG_ADDR_WIDTH-1:0] dbg_addr,
    input  logic [XLEN-1:0]           dbg_wdata,
    input  logic                      dbg_we,
    output logic [XLEN-1:0]           dbg_rdata
);

    // Register array
    logic [XLEN-1:0] regs [1:NUM_REGS-1];  // x1 to x31 (x0 is hardwired to 0)

    // Write logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset all registers to 0
            for (int i = 1; i < NUM_REGS; i++) begin
                regs[i] <= '0;
            end
        end else begin
            // Normal write port (priority over debug)
            if (rd_we && (rd_addr != '0)) begin
                regs[rd_addr] <= rd_data;
            end
            // Debug write port (lower priority)
            else if (dbg_we && (dbg_addr != '0)) begin
                regs[dbg_addr] <= dbg_wdata;
            end
        end
    end

    // Read port 1 (rs1) - combinational read
    assign rs1_data = (rs1_addr == '0) ? '0 : regs[rs1_addr];

    // Read port 2 (rs2) - combinational read
    assign rs2_data = (rs2_addr == '0) ? '0 : regs[rs2_addr];

    // Debug read port - combinational read
    assign dbg_rdata = (dbg_addr == '0) ? '0 : regs[dbg_addr];

endmodule
