// mbist_ctrl.sv
// DFT Stage 4 (beads claude_verilog_test-j41m.14 / j41m.10, GH #244).
//
// Memory BIST controller for ONE clock domain: a ROM-microcode March sequencer, a data-background
// generator, one comparator per memory (and per read port) and a per-memory sticky fail flag with a
// first-fail record. Specification: docs/design/DFT_ARCHITECTURE.md section 16.
//
// All N_MEM memories of a domain are tested in lock-step (same address, same data); they must have
// the same word count (2**AW). Each memory is reached through a mem_collar, which this module drives
// with ONE broadcast bus (registered outputs b_*) and whose bist_en_o select it owns.
//
// Control (level based; the holding register of mbist_xing drives it, nothing here sees a pulse):
//   run_i = 1   start the selected algorithm when idle; the run completes by itself and the status
//               (done, fail, records) is HELD until run_i returns to 0.
//   run_i = 0   abort and clear everything; bist_en_o drops, the collars become pass-through.
//   cfg_i       {rd_sel[3:0], mask_sel[3:0], pause_exp[2:0], pause_mant[7:0], bg_sel[2:0], bg_sweep, alg[2:0]}
//               alg, bg_sweep, bg_sel, pause_*, mask_sel are latched at start; rd_sel is live.
//
// Algorithms (alg): 0 MARCH_CM, 1 RETENTION, 2 MARCH_CM_RET, 3 CKBD, 4 LANE, 5 FULL; 6, 7 reserved ->
// done at once with cfg_err. Backgrounds (bg_sel): 0..5, 6/7 reserved -> cfg_err.
//
// Read latency (RD_LAT, default 2) is the Sky130 macro contract: the op registers load at edge Pk, the
// macro captures at P(k+1), executes at the following negedge, and the data is sampled at P(k+2).
//
// No runtime-indexed array reads: the microcode is a constant-label case function, every per-memory
// select is a one-hot AND-OR over a constant-bound loop, the op slot select is a ternary tree.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module mbist_ctrl #(
    parameter int unsigned        N_MEM   = 2,
    parameter int unsigned        AW      = 10,
    parameter int unsigned        RD_LAT  = 2,
    parameter logic [N_MEM-1:0]   P1_MASK = '0     // 1 = memory has a functional read port 1 (read and compared too)
) (
    input  logic          clk_i,
    input  logic          rst_n_i,

    // ── Control (level, from the holding register) ───────────────────────────
    input  logic          run_i,
    input  logic [25:0]   cfg_i,

    // ── Broadcast to every mem_collar ────────────────────────────────────────
    output logic          bist_en_o,
    output logic          b_ce_o,
    output logic          b_we_o,
    output logic [3:0]    b_wmask_o,
    output logic [AW-1:0] b_addr_o,
    output logic [31:0]   b_din_o,

    // ── Read data of every memory (macro outputs, flattened [i*32 +: 32]) ────
    input  logic [N_MEM*32-1:0] dout0_i,
    input  logic [N_MEM*32-1:0] dout1_i,

    // ── Status block (section 16.5) ──────────────────────────────────────────
    output logic [68:0]   status_o
);

    if (N_MEM < 1 || N_MEM > 10) begin : g_nmem_check
        $fatal(1, "mbist_ctrl: N_MEM (%0d) must be 1..10 (status block carries 10 fail bits)", N_MEM);
    end
    if (AW < 1 || AW > 10) begin : g_aw_check
        $fatal(1, "mbist_ctrl: AW (%0d) must be 1..10", AW);
    end
    if (RD_LAT < 1) begin : g_lat_check
        $fatal(1, "mbist_ctrl: RD_LAT (%0d) must be >= 1", RD_LAT);
    end

    // ── cfg_i fields ─────────────────────────────────────────────────────────
    logic [2:0] cfg_alg;
    logic       cfg_bg_sweep;
    logic [2:0] cfg_bg_sel;
    logic [7:0] cfg_pause_mant;
    logic [2:0] cfg_pause_exp;
    logic [3:0] cfg_mask_sel;
    logic [3:0] cfg_rd_sel;

    assign cfg_alg        = cfg_i[2:0];
    assign cfg_bg_sweep   = cfg_i[3];
    assign cfg_bg_sel     = cfg_i[6:4];
    assign cfg_pause_mant = cfg_i[14:7];
    assign cfg_pause_exp  = cfg_i[17:15];
    assign cfg_mask_sel   = cfg_i[21:18];
    assign cfg_rd_sel     = cfg_i[25:22];

    // ── Microcode ROM (constant case function; section 16.2) ─────────────────
    // word: [0] down  [1] ck  [2] pause_before  [3] lane  [5:4] nops-1  [7:6] op0  [9:8] op1  [11:10] op2
    // op = {rw, pol}: rw = 1 read; pol = data polarity (0 = background P, 1 = ~P).
    localparam logic [1:0] W0 = 2'b00;
    localparam logic [1:0] W1 = 2'b01;
    localparam logic [1:0] R0 = 2'b10;
    localparam logic [1:0] R1 = 2'b11;

    function automatic logic [11:0] mk(input logic down, input logic ck, input logic pause, input logic lane,
                                       input logic [1:0] nm1, input logic [1:0] o0, input logic [1:0] o1,
                                       input logic [1:0] o2);
        return {o2, o1, o0, nm1, lane, pause, ck, down};
    endfunction

    function automatic logic [11:0] urom(input logic [4:0] pc);
        logic [11:0] w;
        unique case (pc)
            // MARCH_CM (March C-): up(w0) up(r0,w1) up(r1,w0) down(r0,w1) down(r1,w0) down(r0)
            5'd0:  w = mk(1'b0, 1'b0, 1'b0, 1'b0, 2'd0, W0, W0, W0);
            5'd1:  w = mk(1'b0, 1'b0, 1'b0, 1'b0, 2'd1, R0, W1, W0);
            5'd2:  w = mk(1'b0, 1'b0, 1'b0, 1'b0, 2'd1, R1, W0, W0);
            5'd3:  w = mk(1'b1, 1'b0, 1'b0, 1'b0, 2'd1, R0, W1, W0);
            5'd4:  w = mk(1'b1, 1'b0, 1'b0, 1'b0, 2'd1, R1, W0, W0);
            5'd5:  w = mk(1'b1, 1'b0, 1'b0, 1'b0, 2'd0, R0, W0, W0);
            // RETENTION: up(w0); PAUSE up(r0,w1); PAUSE up(r1)
            5'd6:  w = mk(1'b0, 1'b0, 1'b0, 1'b0, 2'd0, W0, W0, W0);
            5'd7:  w = mk(1'b0, 1'b0, 1'b1, 1'b0, 2'd1, R0, W1, W0);
            5'd8:  w = mk(1'b0, 1'b0, 1'b1, 1'b0, 2'd0, R1, W0, W0);
            // CKBD: checkerboard up(wc) up(rc) up(w~c) up(r~c), then March C- on the checkerboard (ck = 1)
            5'd9:  w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd0, W0, W0, W0);
            5'd10: w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd0, R0, W0, W0);
            5'd11: w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd0, W1, W0, W0);
            5'd12: w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd0, R1, W0, W0);
            5'd13: w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd0, W0, W0, W0);
            5'd14: w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd1, R0, W1, W0);
            5'd15: w = mk(1'b0, 1'b1, 1'b0, 1'b0, 2'd1, R1, W0, W0);
            5'd16: w = mk(1'b1, 1'b1, 1'b0, 1'b0, 2'd1, R0, W1, W0);
            5'd17: w = mk(1'b1, 1'b1, 1'b0, 1'b0, 2'd1, R1, W0, W0);
            5'd18: w = mk(1'b1, 1'b1, 1'b0, 1'b0, 2'd0, R0, W0, W0);
            // LANE: up(w0); up(lane sequence, 8 slots, lanes 0..3, writes ~P); up(lane sequence, lanes 3..0,
            // writes P). The 8-slot lane sequences are handled by the lane generator; nm1[0] = 1 selects the
            // reverse sequence. Two orders are needed: a lane whose mask bit is stuck at 1 is only visible if
            // a lane is written BEFORE it (forward order exposes lanes 1..3, reverse order lanes 0..2).
            5'd19: w = mk(1'b0, 1'b0, 1'b0, 1'b0, 2'd0, W0, W0, W0);
            5'd20: w = mk(1'b0, 1'b0, 1'b0, 1'b1, 2'd0, W0, W0, W0);
            5'd21: w = mk(1'b0, 1'b0, 1'b0, 1'b1, 2'd1, W0, W0, W0);
            default: w = 12'h000;
        endcase
        return w;
    endfunction

    // First and last microcode address of each algorithm.
    function automatic logic [4:0] alg_start(input logic [2:0] a);
        logic [4:0] r;
        unique case (a)
            3'd0:    r = 5'd0;
            3'd1:    r = 5'd6;
            3'd2:    r = 5'd0;
            3'd3:    r = 5'd9;
            3'd4:    r = 5'd19;
            3'd5:    r = 5'd0;
            default: r = 5'd0;
        endcase
        return r;
    endfunction

    function automatic logic [4:0] alg_end(input logic [2:0] a);
        logic [4:0] r;
        unique case (a)
            3'd0:    r = 5'd5;
            3'd1:    r = 5'd8;
            3'd2:    r = 5'd8;
            3'd3:    r = 5'd18;
            3'd4:    r = 5'd21;
            3'd5:    r = 5'd21;
            default: r = 5'd0;
        endcase
        return r;
    endfunction

    // Background patterns (word-oriented memory: log2(32) + 1 = 6).
    function automatic logic [31:0] bg_pat(input logic [2:0] b);
        logic [31:0] r;
        unique case (b)
            3'd0:    r = 32'h0000_0000;
            3'd1:    r = 32'h5555_5555;
            3'd2:    r = 32'h3333_3333;
            3'd3:    r = 32'h0F0F_0F0F;
            3'd4:    r = 32'h00FF_00FF;
            3'd5:    r = 32'h0000_FFFF;
            default: r = 32'h0000_0000;
        endcase
        return r;
    endfunction

    function automatic logic [31:0] expand4(input logic [3:0] m);
        return {{8{m[3]}}, {8{m[2]}}, {8{m[1]}}, {8{m[0]}}};
    endfunction

    // ── State ────────────────────────────────────────────────────────────────
    typedef enum logic [2:0] {
        S_IDLE  = 3'd0,
        S_INIT  = 3'd1,
        S_PAUSE = 3'd2,
        S_SWEEP = 3'd3,
        S_DRAIN = 3'd4,
        S_DONE  = 3'd5
    } st_e;

    st_e          st_q;
    st_e          st_d;
    logic         bist_en_q;
    logic [2:0]   alg_q;
    logic         bg_sweep_q;
    logic [2:0]   bg_idx_q;
    logic [21:0]  pause_cycles_q;
    logic [3:0]   mask_sel_q;
    logic [4:0]   pc_q;
    logic [AW-1:0] addr_q;
    logic [2:0]   slot_q;
    logic [21:0]  pcnt_q;
    logic [$clog2(RD_LAT+1)-1:0] dcnt_q;
    logic         cfg_err_q;

    logic [11:0]  uw;
    logic         u_down;
    logic         u_ck;
    logic         u_pause;
    logic         u_lane;
    logic [1:0]   u_nm1;
    logic [1:0]   u_op0;
    logic [1:0]   u_op1;
    logic [1:0]   u_op2;

    assign uw      = urom(pc_q);
    assign u_down  = uw[0];
    assign u_ck    = uw[1];
    assign u_pause = uw[2];
    assign u_lane  = uw[3];
    assign u_nm1   = uw[5:4];
    assign u_op0   = uw[7:6];
    assign u_op1   = uw[9:8];
    assign u_op2   = uw[11:10];

    localparam logic [AW-1:0] ADDR_MAX = '1;

    logic addr_end;
    assign addr_end = u_down ? (addr_q == '0) : (addr_q == ADDR_MAX);

    // Current op (normal elements) / lane generator.
    logic [1:0] op_sel;
    logic       op_rd;
    logic       op_pol;
    logic       slot_last;
    logic       lane_rev;
    logic [1:0] lane_k;
    logic [3:0] lane_rd_xm;
    logic [3:0] lane_wm;

    assign op_sel = (slot_q[1:0] == 2'd0) ? u_op0 : ((slot_q[1:0] == 2'd1) ? u_op1 : u_op2);
    assign lane_rev = u_nm1[0];
    assign lane_k   = lane_rev ? ~slot_q[2:1] : slot_q[2:1];

    // Forward: write lane k with ~P, read expects lanes 0..k inverted. Reverse: write lane k with P, read
    // expects the lanes below k still inverted.
    always_comb begin
        unique case (lane_k)
            2'd0:    begin lane_rd_xm = lane_rev ? 4'b0000 : 4'b0001; lane_wm = 4'b0001; end
            2'd1:    begin lane_rd_xm = lane_rev ? 4'b0001 : 4'b0011; lane_wm = 4'b0010; end
            2'd2:    begin lane_rd_xm = lane_rev ? 4'b0011 : 4'b0111; lane_wm = 4'b0100; end
            default: begin lane_rd_xm = lane_rev ? 4'b0111 : 4'b1111; lane_wm = 4'b1000; end
        endcase
    end

    always_comb begin
        if (u_lane) begin
            op_rd     = slot_q[0];
            op_pol    = 1'b1;
            slot_last = (slot_q == 3'd7);
        end else begin
            op_rd     = op_sel[1];
            op_pol    = op_sel[0];
            slot_last = (slot_q[1:0] == u_nm1);
        end
    end

    // Effective polarity, byte-lane XOR mask, write mask for the op being issued.
    logic       pol_eff;
    logic [3:0] xm_now;
    logic [3:0] wm_now;
    logic [31:0] pat_now;

    assign pol_eff = op_pol ^ (u_ck & addr_q[0]);
    assign pat_now = bg_pat(bg_idx_q);

    always_comb begin
        if (u_lane) begin
            xm_now = op_rd ? lane_rd_xm : (lane_rev ? 4'h0 : 4'hF);
            wm_now = lane_wm;
        end else begin
            xm_now = {4{pol_eff}};
            wm_now = 4'hF;
        end
    end

    // ── Registered broadcast (the op registers) and the read-tag pipeline ─────
    logic          b_ce_q;
    logic          b_we_q;
    logic [3:0]    b_wmask_q;
    logic [AW-1:0] b_addr_q;
    logic [31:0]   b_din_q;

    logic          tg_rd_q   [RD_LAT];
    logic [AW-1:0] tg_addr_q [RD_LAT];
    logic [3:0]    tg_xm_q   [RD_LAT];
    logic [2:0]    tg_slot_q [RD_LAT];

    logic          issue;
    assign issue = (st_q == S_SWEEP);

    // ── Next-state logic ─────────────────────────────────────────────────────
    logic cfg_bad;
    logic last_pc;
    logic last_bg;

    assign cfg_bad = (cfg_alg > 3'd5) || (cfg_bg_sel > 3'd5);
    assign last_pc = (pc_q == alg_end(alg_q));
    assign last_bg = !bg_sweep_q || (bg_idx_q == 3'd5);

    always_comb begin
        st_d = st_q;
        if (!run_i) begin
            st_d = S_IDLE;
        end else begin
            unique case (st_q)
                S_IDLE:  st_d = cfg_bad ? S_DONE : S_INIT;
                S_INIT:  st_d = (u_pause && (pause_cycles_q != 22'd0)) ? S_PAUSE : S_SWEEP;
                S_PAUSE: st_d = (pcnt_q == 22'd1 || pcnt_q == 22'd0) ? S_SWEEP : S_PAUSE;
                S_SWEEP: st_d = (slot_last && addr_end) ? S_DRAIN : S_SWEEP;
                S_DRAIN: begin
                    if (dcnt_q == '0) begin
                        st_d = (last_pc && last_bg) ? S_DONE : S_INIT;
                    end
                end
                S_DONE:  st_d = S_DONE;
                default: st_d = S_IDLE;
            endcase
        end
    end

    // ── Sequencer registers ──────────────────────────────────────────────────
    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            st_q           <= S_IDLE;
            bist_en_q      <= 1'b0;
            alg_q          <= 3'd0;
            bg_sweep_q     <= 1'b0;
            bg_idx_q       <= 3'd0;
            pause_cycles_q <= 22'd0;
            mask_sel_q     <= 4'd0;
            pc_q           <= 5'd0;
            addr_q         <= '0;
            slot_q         <= 3'd0;
            pcnt_q         <= 22'd0;
            dcnt_q         <= '0;
            cfg_err_q      <= 1'b0;
        end else begin
            st_q      <= st_d;
            bist_en_q <= (st_d != S_IDLE);

            if (!run_i) begin
                cfg_err_q <= 1'b0;
            end else if (st_q == S_IDLE) begin
                // Latch the configuration at start.
                alg_q          <= cfg_alg;
                bg_sweep_q     <= cfg_bg_sweep;
                bg_idx_q       <= cfg_bg_sweep ? 3'd0 : cfg_bg_sel;
                pause_cycles_q <= 22'({14'd0, cfg_pause_mant} << {cfg_pause_exp, 1'b0});
                mask_sel_q     <= cfg_mask_sel;
                pc_q           <= alg_start(cfg_alg);
                cfg_err_q      <= cfg_bad;
            end

            if (run_i) begin
                unique case (st_q)
                    S_INIT: begin
                        slot_q <= 3'd0;
                        addr_q <= u_down ? ADDR_MAX : '0;
                        pcnt_q <= pause_cycles_q;
                    end
                    S_PAUSE: begin
                        pcnt_q <= pcnt_q - 22'd1;
                    end
                    S_SWEEP: begin
                        if (slot_last) begin
                            slot_q <= 3'd0;
                            addr_q <= u_down ? (addr_q - 1'b1) : (addr_q + 1'b1);
                            if (addr_end) begin
                                dcnt_q <= ($bits(dcnt_q))'(RD_LAT - 1);
                            end
                        end else begin
                            slot_q <= slot_q + 3'd1;
                        end
                    end
                    S_DRAIN: begin
                        if (dcnt_q != '0) begin
                            dcnt_q <= dcnt_q - 1'b1;
                        end else if (!(last_pc && last_bg)) begin
                            if (last_pc) begin
                                pc_q     <= alg_start(alg_q);
                                bg_idx_q <= bg_idx_q + 3'd1;
                            end else begin
                                pc_q <= pc_q + 5'd1;
                            end
                        end
                    end
                    default: ;
                endcase
            end
        end
    end

    // ── Op registers and read tags ───────────────────────────────────────────
    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            b_ce_q    <= 1'b0;
            b_we_q    <= 1'b0;
            b_wmask_q <= 4'hF;
            b_addr_q  <= '0;
            b_din_q   <= 32'd0;
        end else begin
            b_ce_q <= issue;
            if (issue) begin
                b_we_q    <= !op_rd;
                b_wmask_q <= wm_now;
                b_addr_q  <= addr_q;
                b_din_q   <= pat_now ^ expand4(xm_now);
            end
        end
    end

    genvar gl;
    generate
        for (gl = 0; gl < RD_LAT; gl++) begin : g_tag
            if (gl == 0) begin : g_first
                always_ff @(posedge clk_i or negedge rst_n_i) begin
                    if (!rst_n_i) begin
                        tg_rd_q[0]   <= 1'b0;
                        tg_addr_q[0] <= '0;
                        tg_xm_q[0]   <= 4'd0;
                        tg_slot_q[0] <= 3'd0;
                    end else begin
                        tg_rd_q[0]   <= issue && op_rd;
                        tg_addr_q[0] <= addr_q;
                        tg_xm_q[0]   <= xm_now;
                        tg_slot_q[0] <= slot_q;
                    end
                end
            end else begin : g_next
                always_ff @(posedge clk_i or negedge rst_n_i) begin
                    if (!rst_n_i) begin
                        tg_rd_q[gl]   <= 1'b0;
                        tg_addr_q[gl] <= '0;
                        tg_xm_q[gl]   <= 4'd0;
                        tg_slot_q[gl] <= 3'd0;
                    end else begin
                        tg_rd_q[gl]   <= tg_rd_q[gl-1];
                        tg_addr_q[gl] <= tg_addr_q[gl-1];
                        tg_xm_q[gl]   <= tg_xm_q[gl-1];
                        tg_slot_q[gl] <= tg_slot_q[gl-1];
                    end
                end
            end
        end
    endgenerate

    assign bist_en_o = bist_en_q;
    assign b_ce_o    = b_ce_q;
    assign b_we_o    = b_we_q;
    assign b_wmask_o = b_wmask_q;
    assign b_addr_o  = b_addr_q;
    assign b_din_o   = b_din_q;

    // ── Compare, per-memory sticky fail and first-fail record ────────────────
    logic          cmp_rd;
    logic [AW-1:0] cmp_addr;
    logic [3:0]    cmp_xm;
    logic [2:0]    cmp_slot;
    logic [31:0]   cmp_exp;

    assign cmp_rd   = tg_rd_q[RD_LAT-1];
    assign cmp_addr = tg_addr_q[RD_LAT-1];
    assign cmp_xm   = tg_xm_q[RD_LAT-1];
    assign cmp_slot = tg_slot_q[RD_LAT-1];
    assign cmp_exp  = bg_pat(bg_idx_q) ^ expand4(cmp_xm);

    logic [N_MEM-1:0] fail_q;
    logic [N_MEM-1:0] ev_w;
    logic [N_MEM-1:0] m0_w;
    logic [N_MEM-1:0] m1_w;
    logic [31:0]      err_w [N_MEM];
    logic [9:0]       rec_addr_q [N_MEM];
    logic [4:0]       rec_elem_q [N_MEM];
    logic [2:0]       rec_slot_q [N_MEM];
    logic [2:0]       rec_bg_q   [N_MEM];
    logic [1:0]       rec_port_q [N_MEM];
    logic [31:0]      mask_q;

    genvar gm;
    generate
        for (gm = 0; gm < N_MEM; gm++) begin : g_cmp
            logic [31:0] d0_w;
            logic [31:0] d1_w;
            assign d0_w = dout0_i[gm*32 +: 32];
            assign d1_w = dout1_i[gm*32 +: 32];
            assign m0_w[gm] = |(d0_w ^ cmp_exp);
            assign m1_w[gm] = P1_MASK[gm] && (|(d1_w ^ cmp_exp));
            assign ev_w[gm] = cmp_rd && (m0_w[gm] || m1_w[gm]);
            assign err_w[gm] = m0_w[gm] ? (d0_w ^ cmp_exp) : (d1_w ^ cmp_exp);

            always_ff @(posedge clk_i or negedge rst_n_i) begin
                if (!rst_n_i) begin
                    fail_q[gm]       <= 1'b0;
                    rec_addr_q[gm]   <= 10'd0;
                    rec_elem_q[gm]   <= 5'd0;
                    rec_slot_q[gm]   <= 3'd0;
                    rec_bg_q[gm]     <= 3'd0;
                    rec_port_q[gm]   <= 2'd0;
                end else if (!run_i) begin
                    fail_q[gm]       <= 1'b0;
                    rec_addr_q[gm]   <= 10'd0;
                    rec_elem_q[gm]   <= 5'd0;
                    rec_slot_q[gm]   <= 3'd0;
                    rec_bg_q[gm]     <= 3'd0;
                    rec_port_q[gm]   <= 2'd0;
                end else if (ev_w[gm] && !fail_q[gm]) begin
                    fail_q[gm]       <= 1'b1;
                    rec_addr_q[gm]   <= 10'(cmp_addr);
                    rec_elem_q[gm]   <= pc_q;
                    rec_slot_q[gm]   <= cmp_slot;
                    rec_bg_q[gm]     <= bg_idx_q;
                    rec_port_q[gm]   <= {m1_w[gm], m0_w[gm]};
                end
            end
        end
    endgenerate

    // Mask capture for the memory selected at start: one-hot AND-OR over constant-bound loops.
    logic        mask_ev;
    logic [31:0] mask_err;

    always_comb begin
        mask_ev  = 1'b0;
        mask_err = 32'd0;
        for (int i = 0; i < N_MEM; i++) begin
            if (mask_sel_q == 4'(i)) begin
                mask_ev  = ev_w[i] && !fail_q[i];
                mask_err = err_w[i];
            end
        end
    end

    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            mask_q <= 32'd0;
        end else if (!run_i) begin
            mask_q <= 32'd0;
        end else if (mask_ev) begin
            mask_q <= mask_err;
        end
    end

    // ── Status block ─────────────────────────────────────────────────────────
    logic [9:0]  r_addr;
    logic [4:0]  r_elem;
    logic [2:0]  r_slot;
    logic [2:0]  r_bg;
    logic [1:0]  r_port;
    logic [9:0]  fail_pad;

    always_comb begin
        r_addr = 10'd0;
        r_elem = 5'd0;
        r_slot = 3'd0;
        r_bg   = 3'd0;
        r_port = 2'd0;
        for (int i = 0; i < N_MEM; i++) begin
            if (cfg_rd_sel == 4'(i)) begin
                r_addr = rec_addr_q[i];
                r_elem = rec_elem_q[i];
                r_slot = rec_slot_q[i];
                r_bg   = rec_bg_q[i];
                r_port = rec_port_q[i];
            end
        end
    end

    always_comb begin
        fail_pad = 10'd0;
        for (int i = 0; i < N_MEM; i++) begin
            fail_pad[i] = fail_q[i];
        end
    end

    logic st_done;
    logic st_busy;
    assign st_done = (st_q == S_DONE);
    assign st_busy = (st_q != S_IDLE) && (st_q != S_DONE);

    assign status_o = {mask_q, r_port, r_bg, r_slot, r_elem, r_addr, fail_pad,
                       (|fail_q), cfg_err_q, st_busy, st_done};

endmodule : mbist_ctrl
