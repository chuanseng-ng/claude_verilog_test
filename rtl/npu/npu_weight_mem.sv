// npu_weight_mem - NPU weight memory: one 4 KB (1024 x 32) store, four ifdef arms.
//
// Function: Four arms. The file has no behavioural array.
//   `ifdef SRAM_SKY130: 1 x sky130_sram_4kbyte_1rw1r_32x1024_8, port 0 only, port 1 tied off.
//   Otherwise four banks (bank = addr[9:8]) of one of: `ifdef SRAM_ASAP7: 4 x sram_1rw_256x32_asap7, each clocked
//   through rv32i_clock_gate. `elsif FPGA: 4 x fpga_sram_1rw (block-RAM inferable, not a hard macro).
//   `else: 4 x sram_1rw_256x32_freepdk45, the cocotb and Verilator default. SRAM_SKY130 wins if it is defined with FPGA.
//   The banked arms read through a 4:1 mux built as a tree of 2:1 ternaries on the registered bank select.
//   The file has no runtime-indexed mux.
//   The read latency is 2 cycles on every arm. A request in cycle c gives rd_data_o in cycle c+2.
//   One capture flop on rd_data_o makes this independent of the macro model.
// Parameters: WEIGHT_WORDS (must be 1024; any other value is an elaboration $fatal).
// Ports: write port wr_en_i, wr_addr_i, wr_data_i (full 32-bit word). Read port rd_en_i, rd_addr_i, rd_data_o.
//   mb_* is the MBIST collar bus. It is active only in the SRAM_SKY130 arm. mb_dout0_o is 0 in the other arms.
// Clocks and resets: clk is the only clock. There is no reset. The array is not resettable.
//   rd_data_o and the bank select are datapath, qualified by the consumer.
// Caller rules:
//   - Do not assert wr_en_i and rd_en_i together. If both are asserted, the write wins. npu_top never does this.
//   - Name the macro instance u_sram_macro in every arm. The banked arms use gen_bank[b].u_sram_macro.
//     The Sky130 PDN_MACRO_CONNECTIONS regex ".*u_sram_macro.*" matches that name.
//     Any other name leaves vccd1 and vssd1 unconnected.
//   - Never define USE_POWER_PINS. Power comes from the LEF and PDN_MACRO_CONNECTIONS, so the RTL has no power ports.
//   - Do not copy the two-way shape of sram_controller.sv (macro or flat array). Its flat arm is a 32,768-flop
//     structure that made the ASAP7 post-CTS resizer non-terminating.
// Doc: ds:mod:npu-weight-mem, tm:mod:npu-weight-mem

module npu_weight_mem #(
    parameter int unsigned WEIGHT_WORDS = 1024
) (
    input  logic        clk,

    // Write port (one 32-bit word, full-word write)
    input  logic        wr_en_i,
    input  logic [9:0]  wr_addr_i,
    input  logic [31:0] wr_data_i,

    // Read port (request in cycle c, data in rd_data_o during cycle c+2)
    input  logic        rd_en_i,
    input  logic [9:0]  rd_addr_i,
    output logic [31:0] rd_data_o,

    // MBIST (DFT Stage 4, Doc: tm:ch:dft-architecture:16-stage-4-specification-beads-j41m14-mbist-j41m10-control-word-crossing): active only in the SRAM_SKY130 arm.
    input  logic        mb_en_i,
    input  logic        mb_ce_i,
    input  logic        mb_we_i,
    input  logic [3:0]  mb_wmask_i,
    input  logic [9:0]  mb_addr_i,
    input  logic [31:0] mb_din_i,
    output logic [31:0] mb_dout0_o
);

    if (WEIGHT_WORDS != 1024) begin : g_weight_words_check
        $fatal(1, "npu_weight_mem: WEIGHT_WORDS (%0d) must be 1024 (one 4 KB macro; a parameter sweep must not fall back to flops)", WEIGHT_WORDS);
    end

    // ── Port-0 request, shared by every arm ──────────────────────────────────
    logic        mem_en_w;     // any access this cycle
    logic        mem_web_w;    // active-low write enable: 0 = write, 1 = read
    logic [9:0]  mem_addr_w;
    logic [31:0] mux_dout_w;   // macro output, post bank-mux, pre capture flop

    assign mem_en_w   = wr_en_i | rd_en_i;
    assign mem_web_w  = ~wr_en_i;
    assign mem_addr_w = wr_en_i ? wr_addr_i : rd_addr_i;

`ifdef SRAM_SKY130
    // ── Sky130: ONE 1024 x 32 macro. Port 1 is tied off exactly as rv32i_icache.sv does. ───────
    logic [31:0] dout1_unused_w;

    // DFT Stage 4: mem_collar between the wrapper and the macro. Port 1 stays tied off (HAS_P1 = 0).
    logic        mb_csb0_m;
    logic        mb_web0_m;
    logic [3:0]  mb_wmask0_m;
    logic [9:0]  mb_addr0_m;
    logic [31:0] mb_din0_m;
    logic        mb_csb1_m;
    logic [9:0]  mb_addr1_m;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        mb_cmp_f0_unused;   // LOCAL_CMP = 0: the collar compare is not built, strobes are constant 0
    logic        mb_cmp_f1_unused;
    /* verilator lint_on  UNUSEDSIGNAL */

    mem_collar #(
        .AW     (10),
        .HAS_P1 (1'b0)
    ) u_mbist_collar (
        .bist_en_i  (mb_en_i),
        .b_ce_i     (mb_ce_i),
        .b_we_i     (mb_we_i),
        .b_wmask_i  (mb_wmask_i),
        .b_addr_i   (mb_addr_i),
        .b_din_i    (mb_din_i),
        .csb0_f_i   (~mem_en_w),
        .web0_f_i   (mem_web_w),
        .wmask0_f_i (4'b1111),
        .addr0_f_i  (mem_addr_w),
        .din0_f_i   (wr_data_i),
        .csb1_f_i   (1'b1),
        .addr1_f_i  (10'b0),
        .clk_i       (clk),
        .x_rd_i      (1'b0),
        .x_xm_i      (4'b0),
        .x_bg_i      (3'b0),
        .dout0_i     (32'd0),
        .dout1_i     (32'd0),
        .cmp_fail0_o (mb_cmp_f0_unused),
        .cmp_fail1_o (mb_cmp_f1_unused),
        .csb0_m_o   (mb_csb0_m),
        .web0_m_o   (mb_web0_m),
        .wmask0_m_o (mb_wmask0_m),
        .addr0_m_o  (mb_addr0_m),
        .din0_m_o   (mb_din0_m),
        .csb1_m_o   (mb_csb1_m),
        .addr1_m_o  (mb_addr1_m)
    );

    sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro (
        .clk0   (clk),
        .csb0   (mb_csb0_m),
        .web0   (mb_web0_m),
        .wmask0 (mb_wmask0_m),
        .addr0  (mb_addr0_m),
        .din0   (mb_din0_m),
        .dout0  (mux_dout_w),
        .clk1   (clk),
        .csb1   (mb_csb1_m),
        .addr1  (mb_addr1_m),
        .dout1  (dout1_unused_w)
    );

    assign mb_dout0_o = mux_dout_w;

    logic unused_dout1_w;
    assign unused_dout1_w = &{1'b0, dout1_unused_w};
`else
    // No Sky130 macro in the banked / FPGA arms: the MBIST collar does not exist here.
    assign mb_dout0_o = 32'd0;
    logic unused_mb_w;
    assign unused_mb_w = &{1'b0, mb_en_i, mb_ce_i, mb_we_i, mb_wmask_i, mb_addr_i, mb_din_i};

    // ── Banked arms: 4 x 256 x 32, bank = addr[9:8], offset = addr[7:0] ───────────────────────
    logic [31:0] bank_dout_w [4];
    logic [1:0]  bank_sel_q;   // registered bank select: the bank whose dout is valid next cycle

    always_ff @(posedge clk) begin
        if (mem_en_w) bank_sel_q <= mem_addr_w[9:8];
    end

    genvar b;
    generate
        for (b = 0; b < 4; b++) begin : gen_bank
            logic bank_csb_w;
            assign bank_csb_w = ~(mem_en_w & (mem_addr_w[9:8] == 2'(b)));
`ifdef SRAM_ASAP7
            logic bank_gclk_w;
            // j41m.2: test_en tied 0 -- this gate clocks an SRAM macro only (no scannable flop behind it).
            rv32i_clock_gate u_cg (.en(~bank_csb_w), .test_en(1'b0), .clk(clk), .gclk(bank_gclk_w));
            sram_1rw_256x32_asap7 u_sram_macro (
                .clk0   (bank_gclk_w),
                .csb0   (bank_csb_w),
                .web0   (mem_web_w),
                .addr0  (mem_addr_w[7:0]),
                .din0   (wr_data_i),
                .dout0  (bank_dout_w[b])
            );
`elsif FPGA
            fpga_sram_1rw #(.AW(8)) u_sram_macro (
                .clk0   (clk),
                .csb0   (bank_csb_w),
                .web0   (mem_web_w),
                .addr0  (mem_addr_w[7:0]),
                .din0   (wr_data_i),
                .dout0  (bank_dout_w[b])
            );
`else
            sram_1rw_256x32_freepdk45 u_sram_macro (
                .clk0   (clk),
                .csb0   (bank_csb_w),
                .web0   (mem_web_w),
                .addr0  (mem_addr_w[7:0]),
                .din0   (wr_data_i),
                .dout0  (bank_dout_w[b])
            );
`endif
        end
    endgenerate

    // 4:1 read mux: a tree of 2:1 ternaries on the registered select, constant bank indices.
    assign mux_dout_w = bank_sel_q[1] ? (bank_sel_q[0] ? bank_dout_w[3] : bank_dout_w[2])
                                      : (bank_sel_q[0] ? bank_dout_w[1] : bank_dout_w[0]);
`endif

    // ── Latency normalisation: one more flop, identical on every arm ───────────────────────────
    always_ff @(posedge clk) begin
        rd_data_o <= mux_dout_w;
    end

endmodule : npu_weight_mem
