// replay_tb.sv -- scan replay of Quaigh patterns and chain flush on the gate-level scan netlist (bead j41m.19).
//
// Unmodified netlist text inside replay_top (replay_netlist.py); this bench only drives pins:
//   pin mode  (+tap=0): scan_mode_i=1, TAP held in reset (trst_ni=0) = the conditions of the ATPG cut
//   TAP entry (+tap=1): scan_mode_i=0; TRST released, IR=SCAN_SEL, DR=PARALLEL, IR=SCAN (scan_mode from the TAP), pins shift
// The TAP serial data path (TDI -> chains -> TDO) is a 1-bit stub in the RTL (STAGE2_CHAIN, jtag_tap.sv), so chain data always
// moves on scan_in_i / scan_out_o.
// Scan-entry (crypto wipe, TM 14.14): 3 test-clock edges with scan_en=0, one spare, then scan_en=1.
// Race discipline: inputs change just after the falling edge, outputs are sampled 1 ns before the rising edge.
//
// Plusargs: +dir=<vector dir> +mode=pat|flush +tap=0|1 +fault=<k> +stop=1 +npat=<n>
`timescale 1ns/1ps
`include "params.svh"

module tb_replay;
  reg scan_clk_i = 0, scan_en_i = 0, scan_mode_i = 0, scan_rst_ni = 1, trst_ni = 0, tck_i = 0, clk_i = 0, cpu_clk_i = 0;
  reg tms_i = 0, tdi_i = 0;
  reg [N_PI-1:0] pi_vec = 0;
  wire [N_PO-1:0] po_vec;
  reg [NFAULT>0 ? NFAULT-1 : 0:0] fsel = 0;
  reg [7:0] scan_in_i = 0;
  wire [7:0] scan_out_o;
  wire tdo_o;

  replay_top dut(.pi_vec(pi_vec), .po_vec(po_vec), .scan_clk_i(scan_clk_i), .scan_en_i(scan_en_i), .scan_mode_i(scan_mode_i),
                 .scan_rst_ni(scan_rst_ni), .trst_ni(trst_ni), .tck_i(tck_i), .clk_i(clk_i), .cpu_clk_i(cpu_clk_i),
                 .tms_i(tms_i), .tdi_i(tdi_i), .fsel(fsel), .scan_in_i(scan_in_i), .scan_out_o(scan_out_o), .tdo_o(tdo_o));

  reg [31:0] pi_mem [0:NPAT*PIW-1];
  reg [31:0] po_mem [0:NPAT*POW-1];
  reg [7:0] ld_mem [0:NPAT*L-1];
  reg [7:0] ex_mem [0:NPAT*L-1];
  reg [7:0] mk_mem [0:NPAT*L-1];

  string dir, mode;
  integer tap, fault, stop, npat;
  integer mism_so, mism_po, first_so_pat, first_po_pat, first_so_chain;
  integer i, c, w;
  reg [N_PO-1:0] expo;
  reg [N_PI-1:0] pivec;
  reg [7:0] d;

  task tick;  // one test-clock period: sample point is 1 ns before the rising edge
    begin
      #4; #1 scan_clk_i = 1; #5 scan_clk_i = 0;
    end
  endtask

  task tck_cycle(input tms, input tdi);
    begin
      tms_i = tms; tdi_i = tdi; #10 tck_i = 1; #10 tck_i = 0;
    end
  endtask

  task tap_ir(input [3:0] v);
    integer b;
    begin
      tck_cycle(1, 0); tck_cycle(1, 0); tck_cycle(0, 0); tck_cycle(0, 0);  // Select-DR, Select-IR, Capture-IR, Shift-IR
      for (b = 0; b < 4; b = b + 1) tck_cycle(b == 3, v[b]);
      tck_cycle(1, 0); tck_cycle(0, 0);  // Update-IR, Run-Test/Idle
    end
  endtask

  task tap_dr3(input [2:0] v);
    integer b;
    begin
      tck_cycle(1, 0); tck_cycle(0, 0); tck_cycle(0, 0);  // Select-DR, Capture-DR, Shift-DR
      for (b = 0; b < 3; b = b + 1) tck_cycle(b == 2, v[b]);
      tck_cycle(1, 0); tck_cycle(0, 0);
    end
  endtask

  task enter_scan;
    integer b;
    begin
      scan_en_i = 0;
      if (tap) begin
        scan_mode_i = 0; trst_ni = 0;
        repeat (3) tck_cycle(1, 0);
        trst_ni = 1;
        repeat (5) tck_cycle(1, 0);
        tck_cycle(0, 0);
        tap_ir(4'h3); tap_dr3(3'b001);  // SCAN_SEL: PARALLEL=1, CHAIN_GRP=0
        tap_ir(4'h4);                   // SCAN: scan_mode from the TAP, shift control from the pins
        repeat (12) tick;
      end else begin
        trst_ni = 0; scan_mode_i = 1;
        #10;
        repeat (5) tick;  // edges 1..3 wipe, 4 spare, 5 margin
      end
    end
  endtask

  integer dbg;
  task show(input integer t);
    begin
      if (dbg) $display("DBG t=%0d en=%b si=%h so=%h scan_mode=%b dft_en=%b wipe_done=%b test_clk=%b", t, scan_en_i, scan_in_i, scan_out_o,
                        dut.u_dut.dft_scan_mode, dut.u_dut.dft_scan_en, dut.u_dut.crypto_wipe_done, dut.u_dut.dft_test_clk);
    end
  endtask

  task cmp_so(input integer pat, input integer cyc);
    reg [7:0] exp8, m8, diff;
    begin
      if (pat >= 0) begin
        exp8 = ex_mem[pat*L + cyc]; m8 = mk_mem[pat*L + cyc];
        diff = (scan_out_o ^ exp8) & m8;
        if (diff != 0) begin
          if (mism_so == 0) begin first_so_pat = pat; first_so_chain = diff; end
          mism_so = mism_so + 1;
        end
      end
    end
  endtask

  task shift_phase(input integer load_pat, input integer unload_pat);
    integer cyc;
    begin
      for (cyc = 0; cyc < L; cyc = cyc + 1) begin
        scan_in_i = (load_pat >= 0) ? ld_mem[load_pat*L + cyc] : 8'h00;
        #4; cmp_so(unload_pat, cyc);
        #1 scan_clk_i = 1; #5 scan_clk_i = 0;
      end
    end
  endtask

  task do_patterns;
    integer p, k;
    begin
      for (p = 0; p < npat; p = p + 1) begin
        scan_en_i = 1;
        shift_phase(p, p - 1);
        scan_en_i = 0;
        for (w = 0; w < PIW; w = w + 1) for (k = 0; k < 32; k = k + 1) if (w*32 + k < N_PI) pivec[w*32 + k] = pi_mem[p*PIW + w][k];
        pi_vec = pivec;
        #4;
        for (w = 0; w < POW; w = w + 1) for (k = 0; k < 32; k = k + 1) if (w*32 + k < N_PO) expo[w*32 + k] = po_mem[p*POW + w][k];
        if (po_vec !== expo) begin
          if (mism_po == 0) first_po_pat = p;
          mism_po = mism_po + 1;
        end
        #1 scan_clk_i = 1; #5 scan_clk_i = 0;
      end
      scan_en_i = 1;
      shift_phase(-1, npat - 1);
    end
  endtask

  // flush: shift 0011... into every chain, expect the same stream L_k edges later at scan_out
  task do_flush;
    integer t, k, tot, bad_chains;
    reg bit_in;
    reg [7:0] hist [0:L+64];
    begin
      tot = L + 40;
      scan_en_i = 1;
      mism_so = 0;
      bad_chains = 0;
      for (t = 0; t < tot; t = t + 1) begin
        bit_in = (t >> 1) & 1;
        scan_in_i = {8{bit_in}};
        hist[t] = scan_in_i;
        #4;
        if (t < 8 || (t >= L - 3 && t < L + 8)) show(t);
        for (k = 0; k < 6; k = k + 1)
          if (t >= CHLEN[k] && scan_out_o[k] !== hist[t - CHLEN[k]][k]) begin
            if ((first_so_chain & (1 << k)) == 0) bad_chains = bad_chains + 1;
            first_so_chain = first_so_chain | (1 << k);
            mism_so = mism_so + 1;
          end
        #1 scan_clk_i = 1; #5 scan_clk_i = 0;
      end
      $display("FLUSH edges=%0d bad_chain_mask=0x%0h bad_chains=%0d mism=%0d", tot, first_so_chain, bad_chains, mism_so);
    end
  endtask

  initial begin
    if (!$value$plusargs("dir=%s", dir)) dir = ".";
    if (!$value$plusargs("mode=%s", mode)) mode = "pat";
    if (!$value$plusargs("dbg=%d", dbg)) dbg = 0;
    if (!$value$plusargs("tap=%d", tap)) tap = 0;
    if (!$value$plusargs("fault=%d", fault)) fault = -1;
    if (!$value$plusargs("npat=%d", npat)) npat = NPAT;
    mism_so = 0; mism_po = 0; first_so_pat = -1; first_po_pat = -1; first_so_chain = 0;
    if (mode == "pat") begin
      $readmemh({dir, "/pi.hex"}, pi_mem); $readmemh({dir, "/po.hex"}, po_mem);
      $readmemh({dir, "/ld.hex"}, ld_mem); $readmemh({dir, "/ex.hex"}, ex_mem); $readmemh({dir, "/mk.hex"}, mk_mem);
    end
    if (NFAULT > 0 && fault >= 0) fsel = 1 << fault;
    #20;
    enter_scan;
    if (mode == "flush") do_flush; else do_patterns;
    $display("RESULT mode=%s tap=%0d fault=%0d npat=%0d so_mismatch=%0d first_so_pat=%0d first_so_chains=0x%0h po_mismatch=%0d first_po_pat=%0d",
             mode, tap, fault, npat, mism_so, first_so_pat, first_so_chain, mism_po, first_po_pat);
    $finish;
  end
endmodule
