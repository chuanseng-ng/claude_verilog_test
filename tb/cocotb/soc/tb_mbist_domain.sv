// tb_mbist_domain.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.14): mbist_ctrl + N mem_collar + N fault-injecting SRAM models
// (sram_fi_core, Sky130 macro timing). Parameters are set per build with -G (N_MEM, AW, P1_MASK).
// The functional-side ports let a test prove the collar is a pass-through when bist_en = 0.
module tb_mbist_domain #(
    parameter int unsigned      N_MEM   = 4,
    parameter int unsigned      AW      = 6,
    parameter logic [N_MEM-1:0] P1_MASK = 4'b0101
) (
    input  logic                 clk_i,
    input  logic                 rst_n_i,
    input  logic                 run_i,
    input  logic [25:0]          cfg_i,
    output logic [68:0]          status_o,
    output logic                 bist_en_o,

    input  logic [N_MEM-1:0]     f_csb0_i,
    input  logic [N_MEM-1:0]     f_web0_i,
    input  logic [N_MEM*4-1:0]   f_wmask0_i,
    input  logic [N_MEM*AW-1:0]  f_addr0_i,
    input  logic [N_MEM*32-1:0]  f_din0_i,
    input  logic [N_MEM-1:0]     f_csb1_i,
    input  logic [N_MEM*AW-1:0]  f_addr1_i,
    output logic [N_MEM*32-1:0]  f_dout0_o,
    output logic [N_MEM*32-1:0]  f_dout1_o
);

    logic          b_ce;
    logic          b_we;
    logic [3:0]    b_wmask;
    logic [AW-1:0] b_addr;
    logic [31:0]   b_din;

    mbist_ctrl #(
        .N_MEM   (N_MEM),
        .AW      (AW),
        .RD_LAT  (2),
        .P1_MASK (P1_MASK)
    ) u_ctrl (
        .clk_i     (clk_i),
        .rst_n_i   (rst_n_i),
        .run_i     (run_i),
        .cfg_i     (cfg_i),
        .bist_en_o (bist_en_o),
        .b_ce_o    (b_ce),
        .b_we_o    (b_we),
        .b_wmask_o (b_wmask),
        .b_addr_o  (b_addr),
        .b_din_o   (b_din),
        .dout0_i   (f_dout0_o),
        .dout1_i   (f_dout1_o),
        .status_o  (status_o)
    );

    genvar gi;
    generate
        for (gi = 0; gi < N_MEM; gi++) begin : g_mem
            logic          csb0_m;
            logic          web0_m;
            logic [3:0]    wmask0_m;
            logic [AW-1:0] addr0_m;
            logic [31:0]   din0_m;
            logic          csb1_m;
            logic [AW-1:0] addr1_m;

            mem_collar #(
                .AW     (AW),
                .HAS_P1 (P1_MASK[gi])
            ) u_collar (
                .bist_en_i  (bist_en_o),
                .b_ce_i     (b_ce),
                .b_we_i     (b_we),
                .b_wmask_i  (b_wmask),
                .b_addr_i   (b_addr),
                .b_din_i    (b_din),
                .csb0_f_i   (f_csb0_i[gi]),
                .web0_f_i   (f_web0_i[gi]),
                .wmask0_f_i (f_wmask0_i[gi*4 +: 4]),
                .addr0_f_i  (f_addr0_i[gi*AW +: AW]),
                .din0_f_i   (f_din0_i[gi*32 +: 32]),
                .csb1_f_i   (f_csb1_i[gi]),
                .addr1_f_i  (f_addr1_i[gi*AW +: AW]),
                .csb0_m_o   (csb0_m),
                .web0_m_o   (web0_m),
                .wmask0_m_o (wmask0_m),
                .addr0_m_o  (addr0_m),
                .din0_m_o   (din0_m),
                .csb1_m_o   (csb1_m),
                .addr1_m_o  (addr1_m)
            );

            sram_fi_core #(
                .AW (AW)
            ) u_mem (
                .clk0   (clk_i),
                .csb0   (csb0_m),
                .web0   (web0_m),
                .wmask0 (wmask0_m),
                .addr0  (addr0_m),
                .din0   (din0_m),
                .dout0  (f_dout0_o[gi*32 +: 32]),
                .clk1   (clk_i),
                .csb1   (csb1_m),
                .addr1  (addr1_m),
                .dout1  (f_dout1_o[gi*32 +: 32])
            );
        end
    endgenerate

endmodule : tb_mbist_domain
