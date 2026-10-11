// npu_weight_mem.sv
// Phase 6c -- NPU weight memory: one 4 KB (1024 x 32) store, ALL HARD MACRO, 3-way ifdef
// (bead claude_verilog_test-f7vs.11, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6c -- NPU",
// "Weight-SRAM instantiation").
//
//   `ifdef SRAM_SKY130   1 x sky130_sram_4kbyte_1rw1r_32x1024_8   (port 0 only, port 1 tied off)
//   `elsif SRAM_ASAP7    4 x sram_1rw_256x32_asap7, each clocked through rv32i_clock_gate
//   `else                4 x sram_1rw_256x32_freepdk45            (the cocotb / Verilator default)
//
// THERE IS NO BEHAVIOURAL ARRAY IN THIS FILE, so no define can ever infer flops. The
// sram_controller.sv two-way shape (macro / flat `logic [31:0] mem [..]`) is deliberately NOT
// copied: its flat arm is the 32,768-flop structure bead rvb proved non-terminating in the ASAP7
// post-CTS resizer, and the NPU would have been a second one.
//
// THE MACRO INSTANCE IS NAMED u_sram_macro IN EVERY ARM (banked arms: gen_bank[b].u_sram_macro).
// pnr/sky130/soc/config.json PDN_MACRO_CONNECTIONS matches the leaf instance name with the regex
// ".*u_sram_macro.*"; any other name silently leaves vccd1/vssd1 unconnected (the PSM-0069 class).
// Do not rename. USE_POWER_PINS is deliberately never defined: PG comes from the LEF plus
// PDN_MACRO_CONNECTIONS, so no power ports exist at RTL level.
//
// DECLARED READ LATENCY: 2 CYCLES, IDENTICAL ON EVERY ARM.
//   The three macro models disagree. sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv registers its inputs
//   at posedge and launches dout at the following NEGEDGE; sim/sram_1rw_256x32_verilator.v (the
//   FreePDK45 model every default build uses) launches dout at the posedge itself. Their dout is
//   therefore valid at different instants inside the cycle after the request, but in BOTH it is
//   stable well before the next posedge. This wrapper captures the (muxed) macro output into
//   rd_data_o with one more flop, so the contract presented to npu_top is arm-independent:
//
//       rd_en_i / rd_addr_i sampled by the macro at edge E0   (request cycle = the cycle before E0)
//       rd_data_o valid during the cycle that ENDS at edge E0+2, i.e. captured by a consumer at E0+2.
//
//   npu_top depends only on this ("request in cycle c -> data in cycle c+2"), never on a macro.
//   The extra flop also keeps the 4:1 bank mux and the Sky130 macro's clk-to-dout delay off the
//   consumer's path. Write data reaches the array no later than the negedge after the request edge
//   on every arm, which is before any read could be requested (npu_top rejects weight writes while
//   busy and only reads while busy, so a read request is never issued the cycle after a write).
//
// NO RUNTIME-INDEXED MUX (bead ma7). The weight address goes to a macro, not to a mux. The only
// selector is the 4:1 bank read mux of the two banked arms, written as a tree of 2:1 ternaries on
// the REGISTERED bank select with constant bank indices -- never bank_dout[sel_q]. Bank decode for
// csb0 is a constant compare per generate instance.
//
// wr_en_i and rd_en_i MUST NOT be asserted together (npu_top guarantees it: a weight write is
// accepted only while idle, a read is issued only while busy). If both were, the write wins.
// Single clock domain, no reset: the array is not resettable and rd_data_o / the bank select are
// pure datapath, qualified by the consumer.
//
// Elaboration guard: a bare $fatal in a generate scope (fires under verilator --lint-only, unlike
// `initial $error`) unless WEIGHT_WORDS == 1024, so a parameter sweep cannot silently truncate onto
// the macro geometry.
//
// Lint target: verilator --lint-only -Wall -Wno-IMPORTSTAR 0 errors 0 warnings (default,
// +define+SRAM_SKY130 and +define+SRAM_ASAP7 builds).

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
    output logic [31:0] rd_data_o
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

    sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro (
        .clk0   (clk),
        .csb0   (~mem_en_w),
        .web0   (mem_web_w),
        .wmask0 (4'b1111),
        .addr0  (mem_addr_w),
        .din0   (wr_data_i),
        .dout0  (mux_dout_w),
        .clk1   (clk),
        .csb1   (1'b1),
        .addr1  (10'b0),
        .dout1  (dout1_unused_w)
    );

    logic unused_dout1_w;
    assign unused_dout1_w = &{1'b0, dout1_unused_w};
`else
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
