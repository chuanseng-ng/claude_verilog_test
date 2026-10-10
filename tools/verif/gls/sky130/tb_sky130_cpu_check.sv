// tb_sky130_cpu_check.sv -- bead dud4: Sky130 rv32i_cpu_top macro, gate netlist
// vs RTL differential testbench.
//
// ONE testbench, UNMODIFIED, drives both arms (the arm is chosen at compile
// time purely by which sources are on the Verilator command line):
//   * gate arm: pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz + sky130_fd_sc_hd
//               functional cell models + the project's SRAM behavioural model
//   * RTL arm : the RTL the netlist was synthesised from (+define SRAM_SKY130)
//               + the same SRAM behavioural model
//
// Why this is not simply tb_cpu_macro_check.v (the ma7/u99 harness): that one
// is built for yosys `sim -clock/-resetn` and only observes (a) the commit
// trace and (b) ONE hard-coded debug read (DBG_GPR[4]). The dud4 question is
// wider (every register, every read port), so this bench adds:
//   1. a real AXI4 write slave (MMIO stores bypass the D$ and appear at the
//      macro boundary as AW/W beats -- the observation channel for ID-stage
//      rs1/rs2 reads, see gen_regsweep_rom.py);
//   2. an APB master that halts the core and reads GPR x0..x31 through the
//      debug port (the u99 channel) for every register, not just x4;
//   3. a per-cycle trace of ALL macro output ports, so the two arms can be
//      compared cycle-exactly (a much stronger check than commit order).
//
// Race discipline (needed because the gate arm's flops are UDPs that update in
// the active region, unlike RTL non-blocking assignments): the bench never
// reads a DUT output directly at a clock edge. Outputs are snapshotted 1 ns
// BEFORE each posedge (everything has settled -- zero-delay sim), the bench
// state machines run at posedge on the snapshots and update through
// non-blocking assignments, so inputs change only after the DUT's flops have
// sampled them.
//
// Plusargs:  +rom=<hex file>  +haltcyc=<N>  +trace=<file>  +maxcyc=<N>
`timescale 1ns/1ps

module tb_sky130_cpu_check;
  localparam ROM_WORDS = 1024;

  reg clk_i = 1'b0;
  reg rst_n_i = 1'b0;
  always #5 clk_i = ~clk_i;

  reg [31:0] rom [0:ROM_WORDS-1];
  string romfile;
  string tracefile;
  integer haltcyc;
  integer maxcyc;
  integer trace_fd;
  integer cyc;

  initial begin
    integer i;
    for (i = 0; i < ROM_WORDS; i = i + 1) rom[i] = 32'h0000006f; // JAL x0,0
    if (!$value$plusargs("rom=%s", romfile)) begin
      $display("FATAL no +rom=");
      $finish;
    end
    $readmemh(romfile, rom);
    if (!$value$plusargs("haltcyc=%d", haltcyc)) haltcyc = 3000;
    if (!$value$plusargs("maxcyc=%d", maxcyc)) maxcyc = haltcyc + 2000;
    trace_fd = 0;
    if ($value$plusargs("trace=%s", tracefile)) trace_fd = $fopen(tracefile, "w");
    cyc = 0;
    #57 rst_n_i = 1'b1;
  end

  // ---------------------------------------------------------------- DUT I/O
  reg ext_irq_i = 1'b0;
  reg timer_irq_i = 1'b0;

  reg         apb_psel_i = 1'b0;
  reg         apb_penable_i = 1'b0;
  reg         apb_pwrite_i = 1'b0;
  reg  [11:0] apb_paddr_i = 12'b0;
  reg  [31:0] apb_pwdata_i = 32'b0;
  wire        apb_pready_o;
  wire        apb_pslverr_o;
  wire [31:0] apb_prdata_o;

  wire        axi_arvalid_o;
  wire [31:0] axi_araddr_o;
  wire [7:0]  axi_arlen_o;
  wire [2:0]  axi_arsize_o;
  wire [1:0]  axi_arburst_o;
  wire        axi_arready_i;
  wire        axi_rready_o;
  reg         axi_rvalid_i = 1'b0;
  wire [31:0] axi_rdata_i;
  wire [1:0]  axi_rresp_i;
  wire        axi_rlast_i;

  wire        axi_awvalid_o;
  wire [31:0] axi_awaddr_o;
  wire [7:0]  axi_awlen_o;
  wire [2:0]  axi_awsize_o;
  wire [1:0]  axi_awburst_o;
  wire        axi_awready_i;
  wire        axi_wvalid_o;
  wire [31:0] axi_wdata_o;
  wire [3:0]  axi_wstrb_o;
  wire        axi_wlast_o;
  wire        axi_wready_i;
  wire        axi_bready_o;
  reg         axi_bvalid_i = 1'b0;
  wire [1:0]  axi_bresp_i = 2'b00;

  wire        commit_valid_o;
  wire [31:0] commit_insn_o;
  wire [31:0] commit_pc_o;
  wire [31:0] debug_rs1_data_o;
  wire [31:0] debug_rs2_data_o;
  wire [3:0]  debug_state_o;
  wire        trap_taken_o;
  wire [3:0]  trap_cause_o;
  wire        debug_branch_taken_o;
  wire        debug_ebreak_o;
  wire        debug_pc_src_o;
  wire        debug_take_branch_jump_o;

  rv32i_cpu_top dut (
    .apb_penable_i(apb_penable_i), .apb_pready_o(apb_pready_o), .apb_psel_i(apb_psel_i),
    .apb_pslverr_o(apb_pslverr_o), .apb_pwrite_i(apb_pwrite_i),
    .axi_arready_i(axi_arready_i), .axi_arvalid_o(axi_arvalid_o),
    .axi_awready_i(axi_awready_i), .axi_awvalid_o(axi_awvalid_o),
    .axi_bready_o(axi_bready_o), .axi_bvalid_i(axi_bvalid_i), .axi_rlast_i(axi_rlast_i),
    .axi_rready_o(axi_rready_o), .axi_rvalid_i(axi_rvalid_i), .axi_wlast_o(axi_wlast_o),
    .axi_wready_i(axi_wready_i), .axi_wvalid_o(axi_wvalid_o), .clk_i(clk_i),
    .commit_valid_o(commit_valid_o), .debug_branch_taken_o(debug_branch_taken_o),
    .debug_ebreak_o(debug_ebreak_o), .debug_pc_src_o(debug_pc_src_o),
    .debug_take_branch_jump_o(debug_take_branch_jump_o), .ext_irq_i(ext_irq_i),
    .rst_n_i(rst_n_i), .timer_irq_i(timer_irq_i), .trap_taken_o(trap_taken_o),
    .apb_paddr_i(apb_paddr_i), .apb_prdata_o(apb_prdata_o), .apb_pwdata_i(apb_pwdata_i),
    .axi_araddr_o(axi_araddr_o), .axi_arburst_o(axi_arburst_o), .axi_arlen_o(axi_arlen_o),
    .axi_arsize_o(axi_arsize_o), .axi_awaddr_o(axi_awaddr_o), .axi_awburst_o(axi_awburst_o),
    .axi_awlen_o(axi_awlen_o), .axi_awsize_o(axi_awsize_o), .axi_bresp_i(axi_bresp_i),
    .axi_rdata_i(axi_rdata_i), .axi_rresp_i(axi_rresp_i), .axi_wdata_o(axi_wdata_o),
    .axi_wstrb_o(axi_wstrb_o), .commit_insn_o(commit_insn_o), .commit_pc_o(commit_pc_o),
    .debug_rs1_data_o(debug_rs1_data_o), .debug_rs2_data_o(debug_rs2_data_o),
    .debug_state_o(debug_state_o), .trap_cause_o(trap_cause_o)
  );

  // ----------------------------------------------- pre-posedge output snapshot
  reg        s_arvalid, s_rready, s_awvalid, s_wvalid, s_wlast, s_bready;
  reg [31:0] s_araddr, s_awaddr, s_wdata;
  reg [7:0]  s_arlen, s_awlen;
  reg [3:0]  s_wstrb;
  reg        s_commit_valid, s_trap;
  reg [31:0] s_commit_pc, s_commit_insn, s_prdata, s_dbg_rs1, s_dbg_rs2;
  reg        s_pready, s_pslverr;
  reg [3:0]  s_trap_cause, s_dbg_state;
  reg        s_dbg_bt, s_dbg_eb, s_dbg_pcsrc, s_dbg_tbj;
  reg [2:0]  s_arsize, s_awsize;
  reg [1:0]  s_arburst, s_awburst;

  always @(negedge clk_i) begin
    #4;
    s_arvalid = axi_arvalid_o; s_rready = axi_rready_o; s_awvalid = axi_awvalid_o;
    s_wvalid = axi_wvalid_o; s_wlast = axi_wlast_o; s_bready = axi_bready_o;
    s_araddr = axi_araddr_o; s_awaddr = axi_awaddr_o; s_wdata = axi_wdata_o;
    s_arlen = axi_arlen_o; s_awlen = axi_awlen_o; s_wstrb = axi_wstrb_o;
    s_commit_valid = commit_valid_o; s_trap = trap_taken_o;
    s_commit_pc = commit_pc_o; s_commit_insn = commit_insn_o; s_prdata = apb_prdata_o;
    s_dbg_rs1 = debug_rs1_data_o; s_dbg_rs2 = debug_rs2_data_o;
    s_pready = apb_pready_o; s_pslverr = apb_pslverr_o;
    s_trap_cause = trap_cause_o; s_dbg_state = debug_state_o;
    s_dbg_bt = debug_branch_taken_o; s_dbg_eb = debug_ebreak_o;
    s_dbg_pcsrc = debug_pc_src_o; s_dbg_tbj = debug_take_branch_jump_o;
    s_arsize = axi_arsize_o; s_awsize = axi_awsize_o;
    s_arburst = axi_arburst_o; s_awburst = axi_awburst_o;
  end

  // ------------------------------------------------ optional hierarchical probes
  // (-DPROBE_FILE=\"<gen_probes.py output>\"): ID/EX register + regfile storage,
  // snapshotted pre-posedge like every other observation.
`ifdef PROBE_FILE
`include `PROBE_FILE
  reg [216:0]  s_idex;
  reg [1023:0] s_regs;
  reg [4:0]    s_fwd;
  integer pfd;
  string probefile;
  initial begin
    pfd = 0;
    if ($value$plusargs("probe=%s", probefile)) pfd = $fopen(probefile, "w");
  end
  always @(negedge clk_i) begin
    #4;
    s_idex = p_idex;
    s_regs = p_regs;
    s_fwd = p_fwd;
  end
  // probe line: cyc valid rs1_addr rs2_addr rs1_data rs2_data instr pc
  always @(posedge clk_i)
    if (pfd != 0 && rst_n_i)
      $fwrite(pfd, "%0d %b %0d %0d %08x %08x %08x %08x | %08x %08x %08x %08x %08x %08x %b\n", cyc, s_idex[0],
              s_idex[56:52], s_idex[51:47], s_idex[152:121], s_idex[120:89], s_idex[184:153], s_idex[216:185],
              s_regs[32*0 +: 32], s_regs[32*1 +: 32], s_regs[32*2 +: 32], s_regs[32*3 +: 32],
              s_regs[32*4 +: 32], s_regs[32*5 +: 32], s_fwd);
`endif

  // ------------------------------------------------- AXI read slave (ROM BFM)
  reg        ar_busy = 1'b0;
  reg [31:0] araddr_lat = 32'd0;
  reg [7:0]  arlen_lat = 8'd0;
  reg [7:0]  beat_cnt = 8'd0;

  assign axi_arready_i = !ar_busy;
  assign axi_rresp_i = 2'b00;
  assign axi_rlast_i = (beat_cnt == arlen_lat);
  assign axi_rdata_i = rom[(araddr_lat[31:2] + {24'd0, beat_cnt}) % ROM_WORDS];

  always @(posedge clk_i) begin
    if (!rst_n_i) begin
      ar_busy <= 1'b0; axi_rvalid_i <= 1'b0; beat_cnt <= 8'd0;
      araddr_lat <= 32'd0; arlen_lat <= 8'd0;
    end else if (!ar_busy) begin
      if (s_arvalid) begin
        araddr_lat <= s_araddr; arlen_lat <= s_arlen; beat_cnt <= 8'd0;
        ar_busy <= 1'b1; axi_rvalid_i <= 1'b1;
      end
    end else if (axi_rvalid_i && s_rready) begin
      if (beat_cnt == arlen_lat) begin
        axi_rvalid_i <= 1'b0; ar_busy <= 1'b0;
      end else begin
        beat_cnt <= beat_cnt + 8'd1;
      end
    end
  end

  // ------------------------------------------------ AXI write slave (logger)
  reg        aw_got = 1'b0;
  reg        w_got = 1'b0;
  reg [31:0] aw_a = 32'd0;
  reg [31:0] w_d = 32'd0;
  reg [3:0]  w_s = 4'd0;
  reg [7:0]  aw_l = 8'd0;

  assign axi_awready_i = !aw_got;
  assign axi_wready_i = !w_got;

  always @(posedge clk_i) begin
    if (!rst_n_i) begin
      aw_got <= 1'b0; w_got <= 1'b0; axi_bvalid_i <= 1'b0;
    end else begin
      if (s_awvalid && !aw_got) begin aw_got <= 1'b1; aw_a <= s_awaddr; aw_l <= s_awlen; end
      if (s_wvalid && !w_got) begin w_got <= 1'b1; w_d <= s_wdata; w_s <= s_wstrb; end
      if (aw_got && w_got && !axi_bvalid_i) begin
        axi_bvalid_i <= 1'b1;
        $display("AXIW cyc=%0d addr=%08x data=%08x strb=%x len=%0d", cyc, aw_a, w_d, w_s, aw_l);
      end else if (axi_bvalid_i && s_bready) begin
        axi_bvalid_i <= 1'b0; aw_got <= 1'b0; w_got <= 1'b0;
      end
    end
  end

  // -------------------------------------------------- commit log + cycle count
  always @(posedge clk_i) begin
    cyc <= cyc + 1;
    if (rst_n_i && s_commit_valid)
      $display("COMMIT cyc=%0d pc=%08x insn=%08x trap=%b", cyc, s_commit_pc, s_commit_insn, s_trap);
  end

  // ------------------------------------------- per-cycle boundary-output trace
  always @(posedge clk_i) begin
    if (trace_fd != 0 && rst_n_i)
      $fwrite(trace_fd, "%0d %h\n", cyc,
        {s_arvalid, s_rready, s_awvalid, s_wvalid, s_wlast, s_bready,
         s_commit_valid, s_trap, s_dbg_bt, s_dbg_eb, s_dbg_pcsrc, s_dbg_tbj, s_pready, s_pslverr,
         s_arsize, s_awsize, s_arburst, s_awburst, s_trap_cause, s_dbg_state,
         s_arlen, s_awlen, s_wstrb,
         s_araddr, s_awaddr, s_wdata, s_commit_pc, s_commit_insn, s_dbg_rs1, s_dbg_rs2, s_prdata});
  end

  // ------------------------------------------------ APB debug master sequencer
  reg [31:0] rd_val;

  // APB master tasks. Inputs are driven 1 ns AFTER the clock edge with blocking assignments
  // (not NBAs at the edge): under Verilator --timing a testbench process resumed by a posedge
  // runs before the DUT's clocked logic of the same edge, so an NBA drive at the edge is already
  // visible to the DUT at that edge. That raced the registered pready (the dud4 Sky130 TB's
  // sequencer then saw pready one cycle early and never completed on main RTL).
  task automatic apb_wr(input [11:0] a, input [31:0] d);
    begin
      @(posedge clk_i); #1;
      apb_psel_i = 1'b1; apb_penable_i = 1'b0; apb_pwrite_i = 1'b1;
      apb_paddr_i = a; apb_pwdata_i = d;
      @(posedge clk_i); #1;
      apb_penable_i = 1'b1;
      @(posedge clk_i);
      while (!s_pready) @(posedge clk_i);
      #1;
      apb_psel_i = 1'b0; apb_penable_i = 1'b0; apb_pwrite_i = 1'b0;
    end
  endtask

  task automatic apb_rd(input [11:0] a, output [31:0] d);
    begin
      @(posedge clk_i); #1;
      apb_psel_i = 1'b1; apb_penable_i = 1'b0; apb_pwrite_i = 1'b0; apb_paddr_i = a;
      @(posedge clk_i); #1;
      apb_penable_i = 1'b1;
      @(posedge clk_i);          // ACCESS cycle 1 (pready still 0)
      while (!s_pready) @(posedge clk_i);   // pre-edge snapshot: pready=1 and registered prdata valid
      d = s_prdata;
      #1;
      apb_psel_i = 1'b0; apb_penable_i = 1'b0;
    end
  endtask

  initial begin
    integer r;
    wait (rst_n_i === 1'b1);
    repeat (haltcyc) @(posedge clk_i);
`ifdef PROBE_FILE
    for (r = 0; r < 32; r = r + 1) $display("STATE x%0d=%08x", r, s_regs[32*r +: 32]);
`endif
    apb_wr(12'h000, 32'h1);                 // DBG_CTRL[0] = halt request
    repeat (20) @(posedge clk_i);
    for (r = 0; r < 32; r = r + 1) begin
      apb_rd(12'h010 + 12'(r * 4), rd_val); // DBG_GPR[r]
      $display("APBR x%0d=%08x", r, rd_val);
    end
    repeat (10) @(posedge clk_i);
    $display("DONE cyc=%0d", cyc);
    if (trace_fd != 0) $fclose(trace_fd);
    $finish;
  end

  initial begin
    #1;
    forever begin
      @(posedge clk_i);
      if (cyc > maxcyc) begin
        $display("TIMEOUT cyc=%0d", cyc);
        $finish;
      end
    end
  end
endmodule
