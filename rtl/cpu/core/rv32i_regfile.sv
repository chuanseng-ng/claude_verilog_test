// rv32i_regfile.sv
// RV32I Register File
// 32x32-bit general purpose registers with synchronous reads
//
// Specification: PHASE0_ARCHITECTURE_SPEC.md, PHASE1_ARCHITECTURE_SPEC.md
// - x0 hardwired to zero (per RV32I specification)
// - x1-x31 initialized to zero on reset
// - 2 read ports (synchronous)
// - 1 write port
// - Write-enable gating

module rv32i_regfile (
  // Clock and reset
  input  logic        clk,
  input  logic        rst_n,

  // Write port
  input  logic        wr_en,
  input  logic [4:0]  wr_addr,
  input  logic [31:0] wr_data,

  // Read port 1
  input  logic [4:0]  rd_addr1,
  output logic [31:0] rd_data1,

  // Read port 2
  input  logic [4:0]  rd_addr2,
  output logic [31:0] rd_data2,

  // Debug port (for APB3 access when halted)
  input  logic        dbg_wr_en,
  input  logic [4:0]  dbg_wr_addr,
  input  logic [31:0] dbg_wr_data,
  input  logic [4:0]  dbg_rd_addr,
  output logic [31:0] dbg_rd_data
);

  // Register file array
  // x0 is handled specially (hardwired to zero)
  logic [31:0] regs [1:31];

  // Synchronous write
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      // Reset all registers to zero
      for (int i = 1; i < 32; i++) begin
        regs[i] <= 32'h0;
      end
    end else begin
      // Debug write has priority (should only be active when halted)
      if (dbg_wr_en && (dbg_wr_addr != 5'h0)) begin
        regs[dbg_wr_addr] <= dbg_wr_data;
      // Normal write to register if enabled and not x0
      end else if (wr_en && (wr_addr != 5'h0)) begin
        regs[wr_addr] <= wr_data;
      end
    end
  end

  // Synchronous read port 1
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rd_data1 <= 32'h0;
    end else begin
      // x0 always reads as zero
      if (rd_addr1 == 5'h0) begin
        rd_data1 <= 32'h0;
      end else begin
        rd_data1 <= regs[rd_addr1];
      end
    end
  end

  // Synchronous read port 2
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rd_data2 <= 32'h0;
    end else begin
      // x0 always reads as zero
      if (rd_addr2 == 5'h0) begin
        rd_data2 <= 32'h0;
      end else begin
        rd_data2 <= regs[rd_addr2];
      end
    end
  end

  // Debug read port (combinational for APB read)
  always_comb begin
    // x0 always reads as zero
    if (dbg_rd_addr == 5'h0) begin
      dbg_rd_data = 32'h0;
    end else begin
      dbg_rd_data = regs[dbg_rd_addr];
    end
  end

endmodule
