// npu_top - INT8 NPU, APB4 slave: 4 x 4 weight-stationary MAC grid, 4 KB weight SRAM, shared requantiser.
//
// Function: The block is npu_mac_array, npu_weight_mem and a requantiser behind one APB4 slot and one interrupt.
//   y[j] = requant( SUM over chunks and rows i of W[chunk][i][j] * a[chunk][i] ). One chunk is one AIN word
//   and the four weight words SRAM[TILEBASE + 4c + i]. The engine repeats the chunk KLEN times.
//   The accumulators are zeroed at START. The requantiser then drains the four lanes, one per cycle.
//   It multiplies by SCALE[15:0] (unsigned, 49-bit product), shifts right arithmetically by SCALE[20:16] (floor),
//   saturates to INT8, then applies ReLU if RELU_EN. It packs four bytes into one AOUT word, pushed as done is set.
//   Lanes are little-endian: element 0 is bits [7:0]. AIN and AOUT are depth-4 positional shift registers.
// Registers (word index, N_REGS = 16; words 11 to 15 read 0; the full map is in ds:mod):
//   0 CTRL (RW: [0] RELU_EN, [3] IRQ_EN; [2] START is W1P and reads 0), 1 STATUS (RO, reset 0x08),
//   2 WADDR (RW, [9:0], auto-increments on every accepted WDATA), 3 WDATA (WO, 4 packed INT8 weights, reads 0),
//   4 TILEBASE (RW), 5 KLEN (RW [5:0], 1 to 63), 6 SCALE (RW), 7 AIN (WO, reads 0), 8 AOUT (RO, a read pops it),
//   9 IRQ_STAT (RO, [0] sticky done, the same flop as STATUS[1]), 10 IRQ_CLR (WO, W1C: [0] done, [1] cfg_rejected).
//   STATUS: [0] busy, [1] done, [2] ain_full, [3] ain_empty, [4] aout_valid, [5] aout_full, [6] cfg_rejected (sticky).
// Parameters: ADDR_W (APB address width, default 12), WEIGHT_WORDS (must be 1024), GRID (must be 4),
//   EN_NPU (0 is the SoC tie-off: the APB terminates and irq_o = 0).
// Ports: mb_en_i, mb_ce_i, mb_we_i, mb_wmask_i, mb_addr_i, mb_din_i and mb_dout0_o are the weight-memory MBIST collar bus.
//   The block ignores them when EN_NPU = 0.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous. The block has no CDC.
//   The weight SRAM and the datapath flops have no reset. Reset-cleared valid and state bits qualify them.
// Caller rules:
//   - Write RELU_EN and IRQ_EN first. Write START in a later transfer. START while busy is ignored.
//   - Do not change SCALE or RELU_EN while STATUS.busy. The drain samples them live.
//   - KLEN = 0 or TILEBASE + 4*KLEN > 1024 is illegal. An illegal START takes a 2-cycle path and sets STATUS[6].
//     done does not imply valid data.
//   - A START with fewer than KLEN AIN words queued is starved, not illegal. The engine stays busy.
//   - WADDR and WDATA writes while busy are rejected and latch STATUS[6]. Partial-strobe WDATA and AIN writes are dropped.
//   - STATUS[6] clears on reset, on IRQ_CLR[1] and on an accepted WDATA write.
//   - An AIN write into a full FIFO is dropped. An empty AOUT reads 0 and a read pops nothing.
//   - A result that finishes into a full AOUT FIFO is dropped and the older results stay. Pop AOUT before the fifth run.
//   - The weight SRAM has no readback.
//   - irq_o = done_q & CTRL[3]. It is level-held. done clears on IRQ_CLR[0] or reset. A new done beats a same-cycle clear.
// Doc: ds:mod:npu-top, tm:mod:npu-top

module npu_top #(
    parameter int unsigned ADDR_W       = 12,   // APB4 local address width
    parameter int unsigned WEIGHT_WORDS = 1024, // must be 1024 (one 4 KB macro)
    parameter int unsigned GRID         = 4,    // must be 4
    parameter bit          EN_NPU       = 1     // 0 = tie-off: APB terminates, irq_o = 0
) (
    input  logic clk,
    input  logic rst_n,

    // APB4 slave. SETUP: psel=1, penable=0. ACCESS: psel=1, penable=1.
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] paddr,   // byte address; [1:0] unused (word-aligned)
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // Interrupt -- level-held, never a pulse
    output logic irq_o,

    // MBIST (DFT Stage 4, Doc: tm:ch:dft-architecture:16-stage-4-specification-beads-j41m14-mbist-j41m10-control-word-crossing): weight-memory collar bus; ignored when EN_NPU = 0.
    input  logic        mb_en_i,
    input  logic        mb_ce_i,
    input  logic        mb_we_i,
    input  logic [3:0]  mb_wmask_i,
    input  logic [9:0]  mb_addr_i,
    input  logic [31:0] mb_din_i,
    output logic [31:0] mb_dout0_o
);

    // Elaboration guards: generate-scope $fatal fires at ELABORATION time, under
    // `verilator --lint-only` too, and regardless of EN_NPU (a sweep must not pass silently).
    if (ADDR_W < 6 || ADDR_W > 32) begin : g_addr_w_check
        $fatal(1, "npu_top: ADDR_W (%0d) must be in [6, 32] (16 registers need 4 word-address bits)", ADDR_W);
    end
    if (WEIGHT_WORDS != 1024) begin : g_weight_words_check
        $fatal(1, "npu_top: WEIGHT_WORDS (%0d) must be 1024 (one 4 KB weight macro)", WEIGHT_WORDS);
    end
    if (GRID != 4) begin : g_grid_check
        $fatal(1, "npu_top: GRID (%0d) must be 4 (four INT8 lanes per 32-bit word)", GRID);
    end

    if (!EN_NPU) begin : g_off
        // Tie-off: the bus must still terminate or the SoC hangs.
        assign prdata  = 32'h0;
        assign pready  = 1'b1;
        assign pslverr = 1'b0;
        assign irq_o   = 1'b0;
        assign mb_dout0_o = 32'd0;

        /* verilator lint_off UNUSEDSIGNAL */
        logic unused_w;
        assign unused_w = ^{clk, rst_n, psel, penable, pwrite, paddr, pwdata, pstrb,
                            mb_en_i, mb_ce_i, mb_we_i, mb_wmask_i, mb_addr_i, mb_din_i};
        /* verilator lint_on  UNUSEDSIGNAL */
    end else begin : g_on

        // =====================================================================
        // Register map constants
        // =====================================================================
        localparam int unsigned REG_CTRL     = 0;
        localparam int unsigned REG_STATUS   = 1;
        localparam int unsigned REG_WADDR    = 2;
        localparam int unsigned REG_WDATA    = 3;
        localparam int unsigned REG_TILEBASE = 4;
        localparam int unsigned REG_KLEN     = 5;
        localparam int unsigned REG_SCALE    = 6;
        localparam int unsigned REG_AIN      = 7;
        localparam int unsigned REG_AOUT     = 8;
        localparam int unsigned REG_IRQ_STAT = 9;
        localparam int unsigned REG_IRQ_CLR  = 10;
        localparam int unsigned N_REGS       = 16;

        localparam int unsigned WORDW = ADDR_W - 2;

        localparam logic [31:0] RESET_VAL [N_REGS] = '{
            32'h0000_0000,  //  0 CTRL
            32'h0000_0008,  //  1 STATUS  (ain_empty)
            32'h0000_0000,  //  2 WADDR
            32'h0000_0000,  //  3 WDATA
            32'h0000_0000,  //  4 TILEBASE
            32'h0000_0000,  //  5 KLEN
            32'h0000_0000,  //  6 SCALE
            32'h0000_0000,  //  7 AIN
            32'h0000_0000,  //  8 AOUT
            32'h0000_0000,  //  9 IRQ_STAT
            32'h0000_0000,  // 10 IRQ_CLR
            32'h0000_0000,  // 11 reserved
            32'h0000_0000,  // 12 reserved
            32'h0000_0000,  // 13 reserved
            32'h0000_0000,  // 14 reserved
            32'h0000_0000   // 15 reserved
        };

        // WMASK: START (CTRL[2]) is NOT stored. WDATA / AIN / IRQ_CLR are WO-by-snoop (mask 0, never
        // hardware-written, so they read 0 forever). STATUS / AOUT / IRQ_STAT are hardware-owned.
        localparam logic [31:0] WMASK [N_REGS] = '{
            32'h0000_0009,  //  0 CTRL     bits 0 relu, 3 irq_en (2 masked out)
            32'h0000_0000,  //  1 STATUS   RO
            32'h0000_03FF,  //  2 WADDR    RW
            32'h0000_0000,  //  3 WDATA    WO (snoop)
            32'h0000_03FF,  //  4 TILEBASE RW
            32'h0000_003F,  //  5 KLEN     RW
            32'h001F_FFFF,  //  6 SCALE    RW
            32'h0000_0000,  //  7 AIN      WO (snoop)
            32'h0000_0000,  //  8 AOUT     RO
            32'h0000_0000,  //  9 IRQ_STAT RO
            32'h0000_0000,  // 10 IRQ_CLR  WO (snoop)
            32'h0000_0000,  // 11 reserved
            32'h0000_0000,  // 12 reserved
            32'h0000_0000,  // 13 reserved
            32'h0000_0000,  // 14 reserved
            32'h0000_0000   // 15 reserved
        };

        logic [31:0] regs_o    [N_REGS];
        logic        hw_wen_i  [N_REGS];
        logic [31:0] hw_wdata_i[N_REGS];

        // =====================================================================
        // APB decode and snoops (one transfer completes per cycle: no two snoops can coincide)
        // =====================================================================
        logic [WORDW-1:0] addr_word_w;
        logic [31:0]      addr_ext_w;
        assign addr_word_w = paddr[ADDR_W-1:2];
        assign addr_ext_w  = {{(32-WORDW){1'b0}}, addr_word_w};   // zero-extend: no index can wrap

        logic access_w, wr_acc_w, rd_acc_w;
        assign access_w = psel & penable;
        assign wr_acc_w = access_w & pwrite;
        assign rd_acc_w = access_w & ~pwrite;

        logic is_ctrl_w, is_waddr_w, is_wdata_w, is_ain_w, is_aout_w, is_irq_clr_w;
        assign is_ctrl_w    = (addr_ext_w == 32'(REG_CTRL));
        assign is_waddr_w   = (addr_ext_w == 32'(REG_WADDR));
        assign is_wdata_w   = (addr_ext_w == 32'(REG_WDATA));
        assign is_ain_w     = (addr_ext_w == 32'(REG_AIN));
        assign is_aout_w    = (addr_ext_w == 32'(REG_AOUT));
        assign is_irq_clr_w = (addr_ext_w == 32'(REG_IRQ_CLR));

        // CTRL START: W1P write-snoop, NOT stored.
        logic start_pulse_w;
        assign start_pulse_w = wr_acc_w & is_ctrl_w & pwdata[2] & pstrb[0];

        // IRQ_CLR: one-cycle W1C mask, honouring pstrb[0].
        logic [1:0] clr_w;
        assign clr_w[0] = wr_acc_w & is_irq_clr_w & pstrb[0] & pwdata[0];
        assign clr_w[1] = wr_acc_w & is_irq_clr_w & pstrb[0] & pwdata[1];

        // Engine state (declared up here: busy_q gates the weight-write snoops)
        logic busy_q, busy_d_w;

        // Weight-port writes: accepted only while idle with a full strobe; an attempt while busy is
        // rejected (STATUS[6]). A zero strobe selects no byte lane: not a write at all.
        logic wt_attempt_w, wt_reject_w, wdata_accept_w;
        assign wt_attempt_w   = wr_acc_w & (is_waddr_w | is_wdata_w) & (|pstrb);
        assign wt_reject_w    = wt_attempt_w & busy_q;
        assign wdata_accept_w = wr_acc_w & is_wdata_w & (pstrb == 4'hF) & ~busy_q;

        // The bank cannot protect WADDR dynamically (plan Sec.3): a WADDR write while busy is hidden
        // from it by dropping penable for that one transfer. prdata is independent of penable.
        logic bank_penable_w;
        assign bank_penable_w = penable & ~(wr_acc_w & is_waddr_w & busy_q);

        // AOUT read: pops the head (only if there is one).
        logic aout_rd_w;
        assign aout_rd_w = rd_acc_w & is_aout_w;

        // AIN push: full-strobe only (a partial push into a shift register has no meaning).
        logic ain_push_w;
        assign ain_push_w = wr_acc_w & is_ain_w & (pstrb == 4'hF);

        apb4_register_bank #(
            .N_REGS    (N_REGS),
            .ADDR_W    (ADDR_W),
            .RESET_VAL (RESET_VAL),
            .WMASK     (WMASK)
        ) u_regbank (
            .pclk       (clk),
            .presetn    (rst_n),
            .psel       (psel),
            .penable    (bank_penable_w),
            .pwrite     (pwrite),
            .paddr      (paddr),
            .pwdata     (pwdata),
            .pstrb      (pstrb),
            .prdata     (prdata),
            .pready     (pready),
            .pslverr    (pslverr),
            .regs_o     (regs_o),
            .hw_wen_i   (hw_wen_i),
            .hw_wdata_i (hw_wdata_i)
        );

        // Register views
        logic        relu_w, irq_en_w;
        logic [9:0]  tilebase_w, waddr_w;
        logic [5:0]  klen_w;
        logic [15:0] mult_w;
        logic [4:0]  shift_w;
        assign relu_w     = regs_o[REG_CTRL][0];
        assign irq_en_w   = regs_o[REG_CTRL][3];
        assign waddr_w    = regs_o[REG_WADDR][9:0];
        assign tilebase_w = regs_o[REG_TILEBASE][9:0];
        assign klen_w     = regs_o[REG_KLEN][5:0];
        assign mult_w     = regs_o[REG_SCALE][15:0];
        assign shift_w    = regs_o[REG_SCALE][20:16];

        // Fields the block never reads: reserved bits and the words the bank holds only for readback.
        /* verilator lint_off UNUSEDSIGNAL */
        logic unused_regs_w;
        assign unused_regs_w = ^{regs_o[REG_CTRL][31:4], regs_o[REG_CTRL][2:1],
                                 regs_o[REG_STATUS],
                                 regs_o[REG_WADDR][31:10],
                                 regs_o[REG_WDATA],
                                 regs_o[REG_TILEBASE][31:10],
                                 regs_o[REG_KLEN][31:6],
                                 regs_o[REG_SCALE][31:21],
                                 regs_o[REG_AIN], regs_o[REG_AOUT],
                                 regs_o[REG_IRQ_STAT], regs_o[REG_IRQ_CLR],
                                 regs_o[11], regs_o[12], regs_o[13], regs_o[14], regs_o[15]};
        /* verilator lint_on  UNUSEDSIGNAL */

        // =====================================================================
        // START legality: KLEN in 1..63 and TILEBASE + 4*KLEN <= WEIGHT_WORDS
        // =====================================================================
        logic [10:0] run_end_w;
        logic        legal_w;
        assign run_end_w = {1'b0, tilebase_w} + {3'b000, klen_w, 2'b00};
        assign legal_w   = (klen_w != 6'd0) && (run_end_w <= 11'(WEIGHT_WORDS));

        // =====================================================================
        // Engine: one-hot positional state, no enum / case
        //   f_q[5:0]  FETCH: f_q[0..3] issue the four row reads, f_q[2..5] receive rows 0..3
        //   mac_q     wait for an AIN word, then accumulate one chunk
        //   d_q[4:0]  DRAIN: stage 1 (acc x scale) on d_q[0..3], stage 2 (shift/sat/relu) on
        //             d_q[1..4]; d_q[4] packs, pushes AOUT and sets done
        //   ill_q     the 2-cycle illegal-START path
        // =====================================================================
        logic [5:0] f_q,  f_d_w;
        logic       mac_q, mac_d_w;
        logic [4:0] d_q,  d_d_w;
        logic       ill_q, ill_d_w;

        logic [5:0] kcnt_q;      // chunks left
        logic [9:0] wptr_q;      // next weight-word read address

        logic start_accept_w, start_ill_w, mac_fire_w, last_w;
        logic fetch_launch_w, drain_launch_w;
        logic [3:0] ain_v_q;     // AIN thermometer valid vector (declared with the FIFO below)

        assign start_accept_w = start_pulse_w & ~busy_q &  legal_w;
        assign start_ill_w    = start_pulse_w & ~busy_q & ~legal_w;
        assign mac_fire_w     = mac_q & ain_v_q[0];
        assign last_w         = (kcnt_q == 6'd1);
        assign fetch_launch_w = start_accept_w | (mac_fire_w & ~last_w);
        assign drain_launch_w = mac_fire_w & last_w;

        assign f_d_w    = {f_q[4:0], fetch_launch_w};
        assign mac_d_w  = (mac_q & ~mac_fire_w) | f_q[5];
        assign d_d_w    = {d_q[3:0], drain_launch_w};
        assign ill_d_w  = start_ill_w;
        assign busy_d_w = (|f_d_w) | mac_d_w | (|d_d_w) | ill_d_w;

        always_ff @(posedge clk) begin
            if (!rst_n) begin
                f_q    <= 6'h0;
                mac_q  <= 1'b0;
                d_q    <= 5'h0;
                ill_q  <= 1'b0;
                busy_q <= 1'b0;
            end else begin
                f_q    <= f_d_w;
                mac_q  <= mac_d_w;
                d_q    <= d_d_w;
                ill_q  <= ill_d_w;
                busy_q <= busy_d_w;
            end
        end

        // Chunk counter and weight-read address: counters, not indexed state.
        logic rd_en_w;
        assign rd_en_w = |f_q[3:0];

        always_ff @(posedge clk) begin
            if (!rst_n) begin
                kcnt_q <= 6'd0;
                wptr_q <= 10'd0;
            end else begin
                if (start_accept_w)    kcnt_q <= klen_w;
                else if (mac_fire_w)   kcnt_q <= kcnt_q - 6'd1;

                if (start_accept_w)    wptr_q <= tilebase_w;
                else if (rd_en_w)      wptr_q <= wptr_q + 10'd1;
            end
        end

        // =====================================================================
        // Weight memory + MAC grid
        // =====================================================================
        logic [31:0] wrow_w;       // weight word, valid 2 cycles after its request
        logic [127:0] acc_w;       // 4 x INT32 column accumulators, lane j in [32*j +: 32]

        npu_weight_mem #(
            .WEIGHT_WORDS (WEIGHT_WORDS)
        ) u_wmem (
            .clk       (clk),
            .wr_en_i   (wdata_accept_w),
            .wr_addr_i (waddr_w),
            .wr_data_i (pwdata),
            .rd_en_i   (rd_en_w),
            .rd_addr_i (wptr_q),
            .rd_data_o (wrow_w),
            .mb_en_i    (mb_en_i),
            .mb_ce_i    (mb_ce_i),
            .mb_we_i    (mb_we_i),
            .mb_wmask_i (mb_wmask_i),
            .mb_addr_i  (mb_addr_i),
            .mb_din_i   (mb_din_i),
            .mb_dout0_o (mb_dout0_o)
        );

        // ain_q[0] is the AIN FIFO head (declared below)
        logic [31:0] ain_q [4];

        npu_mac_array #(
            .GRID (GRID)
        ) u_mac (
            .clk        (clk),
            .rst_n      (rst_n),
            .w_row_we_i (f_q[5:2]),        // row i loads on f_q[i+2], the cycle its word arrives
            .w_word_i   (wrow_w),
            .a_i        (ain_q[0]),
            .acc_clr_i  (start_accept_w),
            .acc_en_i   (mac_fire_w),
            .acc_o      (acc_w)
        );

        // =====================================================================
        // AIN FIFO -- depth-4 positional shift register (head = entry 0)
        // =====================================================================
        logic [3:0]  ain_v_d_w, ain_vp_w, ain_wpos_w;
        logic [31:0] ain_dp_w  [4];
        logic [31:0] ain_nxt_w [4];

        genvar s;
        for (s = 0; s < 4; s++) begin : g_ain
            if (s < 3) begin : g_mid
                assign ain_vp_w[s] = mac_fire_w ? ain_v_q[s+1] : ain_v_q[s];
                assign ain_dp_w[s] = mac_fire_w ? ain_q[s+1]   : ain_q[s];
            end else begin : g_top
                assign ain_vp_w[s] = ain_v_q[s] & ~mac_fire_w;
                assign ain_dp_w[s] = ain_q[s];
            end
            if (s == 0) begin : g_first
                assign ain_wpos_w[s] = ain_push_w & ~ain_vp_w[s];
            end else begin : g_rest
                assign ain_wpos_w[s] = ain_push_w & ain_vp_w[s-1] & ~ain_vp_w[s];
            end
            assign ain_nxt_w[s] = ain_wpos_w[s] ? pwdata : ain_dp_w[s];
            assign ain_v_d_w[s] = ain_vp_w[s] | ain_wpos_w[s];

            always_ff @(posedge clk) begin
                ain_q[s] <= ain_nxt_w[s];
            end
        end

        always_ff @(posedge clk) begin
            if (!rst_n) ain_v_q <= 4'h0;
            else        ain_v_q <= ain_v_d_w;
        end

        // =====================================================================
        // Shared requantiser -- one lane per cycle, two pipeline stages
        // =====================================================================
        // Stage 1 (d_q[0..3]): lane k's accumulator via a one-hot AND-OR (no indexed mux) times the
        // UNSIGNED 16-bit multiplier, held at FULL 49-bit width.
        logic signed [31:0] acc_sel_w;
        logic signed [48:0] prod_d_w;
        logic signed [48:0] prod_q;

        assign acc_sel_w = ({32{d_q[0]}} & acc_w[ 31:  0])
                         | ({32{d_q[1]}} & acc_w[ 63: 32])
                         | ({32{d_q[2]}} & acc_w[ 95: 64])
                         | ({32{d_q[3]}} & acc_w[127: 96]);
        assign prod_d_w  = acc_sel_w * $signed({1'b0, mult_w});

        always_ff @(posedge clk) begin
            if (|d_q[3:0]) prod_q <= prod_d_w;
        end

        // Stage 2 (d_q[1..4]): ARITHMETIC right shift (floor), INT8 saturation on the full-width
        // shifted value, THEN ReLU. In range <=> bits [48:7] are all equal.
        logic signed [48:0] shifted_w;
        logic               sat_hi_w, sat_lo_w;
        logic [7:0]         y_sat_w, y_w;

        assign shifted_w = prod_q >>> shift_w;
        assign sat_hi_w  = ~shifted_w[48] & (|shifted_w[47:7]);
        assign sat_lo_w  =  shifted_w[48] & ~(&shifted_w[47:7]);
        assign y_sat_w   = sat_hi_w ? 8'h7F : (sat_lo_w ? 8'h80 : shifted_w[7:0]);
        assign y_w       = (relu_w & y_sat_w[7]) ? 8'h00 : y_sat_w;

        // Lanes 0..2 are held until lane 3 arrives; lane 3 goes straight from y_w into the push.
        logic [23:0] res_q;
        always_ff @(posedge clk) begin
            if (d_q[1]) res_q[ 7: 0] <= y_w;
            if (d_q[2]) res_q[15: 8] <= y_w;
            if (d_q[3]) res_q[23:16] <= y_w;
        end

        // =====================================================================
        // AOUT FIFO -- depth-4 positional shift register (head = entry 0)
        // =====================================================================
        logic [31:0] aout_q [4];
        logic [3:0]  aout_v_q, aout_v_d_w, aout_vp_w, aout_wpos_w;
        logic [31:0] aout_dp_w  [4];
        logic [31:0] aout_nxt_w [4];
        logic        aout_push_w, aout_pop_w;
        logic [31:0] aout_din_w;

        assign aout_push_w = d_q[4];
        assign aout_pop_w  = aout_rd_w & aout_v_q[0];
        assign aout_din_w  = {y_w, res_q};

        for (s = 0; s < 4; s++) begin : g_aout
            if (s < 3) begin : g_mid
                assign aout_vp_w[s] = aout_pop_w ? aout_v_q[s+1] : aout_v_q[s];
                assign aout_dp_w[s] = aout_pop_w ? aout_q[s+1]   : aout_q[s];
            end else begin : g_top
                assign aout_vp_w[s] = aout_v_q[s] & ~aout_pop_w;
                assign aout_dp_w[s] = aout_q[s];
            end
            if (s == 0) begin : g_first
                assign aout_wpos_w[s] = aout_push_w & ~aout_vp_w[s];
            end else begin : g_rest
                assign aout_wpos_w[s] = aout_push_w & aout_vp_w[s-1] & ~aout_vp_w[s];
            end
            assign aout_nxt_w[s] = aout_wpos_w[s] ? aout_din_w : aout_dp_w[s];
            assign aout_v_d_w[s] = aout_vp_w[s] | aout_wpos_w[s];

            always_ff @(posedge clk) begin
                aout_q[s] <= aout_nxt_w[s];
            end
        end

        always_ff @(posedge clk) begin
            if (!rst_n) aout_v_q <= 4'h0;
            else        aout_v_q <= aout_v_d_w;
        end

        // =====================================================================
        // Sticky done and cfg_rejected: SET WINS over a same-cycle clear
        // =====================================================================
        logic done_q, done_d_w, done_set_w;
        assign done_set_w = d_q[4] | ill_q;
        assign done_d_w   = (done_q & ~clr_w[0]) | done_set_w;

        logic rej_q, rej_d_w;
        assign rej_d_w = (rej_q & ~clr_w[1] & ~wdata_accept_w) | wt_reject_w | ill_q;

        always_ff @(posedge clk) begin
            if (!rst_n) begin
                done_q <= 1'b0;
                rej_q  <= 1'b0;
            end else begin
                done_q <= done_d_w;
                rej_q  <= rej_d_w;
            end
        end

        assign irq_o = done_q & irq_en_w;

        // =====================================================================
        // Hardware writeback into the bank: live mirrors written with NEXT-STATE values
        // =====================================================================
        always_comb begin
            for (int unsigned r = 0; r < N_REGS; r++) begin
                hw_wen_i  [r] = 1'b0;
                hw_wdata_i[r] = 32'h0;
            end

            // STATUS: {rej, aout_full, aout_valid, ain_empty, ain_full, done, busy}
            hw_wen_i  [REG_STATUS] = 1'b1;
            hw_wdata_i[REG_STATUS] = {25'h0, rej_d_w, aout_v_d_w[3], aout_v_d_w[0],
                                      ~ain_v_d_w[0], ain_v_d_w[3], done_d_w, busy_d_w};

            // WADDR: the bank word IS the address counter; auto-increment on an accepted WDATA
            // write, wrapping at 1023 (the HW write bypasses WMASK, so the +1 is 10 bits wide).
            hw_wen_i  [REG_WADDR] = wdata_accept_w;
            hw_wdata_i[REG_WADDR] = {22'h0, waddr_w + 10'd1};

            // AOUT: live mirror of the NEXT head; 0 when the FIFO will be empty.
            hw_wen_i  [REG_AOUT] = 1'b1;
            hw_wdata_i[REG_AOUT] = aout_v_d_w[0] ? aout_nxt_w[0] : 32'h0;

            // IRQ_STAT: {done}. The same flop as STATUS[1].
            hw_wen_i  [REG_IRQ_STAT] = 1'b1;
            hw_wdata_i[REG_IRQ_STAT] = {31'h0, done_d_w};
        end
    end

endmodule : npu_top
