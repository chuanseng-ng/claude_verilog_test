// memory_coalescer_hls.sv
// GH #119 — hand-written RTL vs Bambu HLS core PPA/QoR comparison shim.
//
// Purpose:
//   Adapts the port names/shapes of the Bambu-generated `memory_coalescer`
//   HLS core (/nobackup/hls/out/memory_coalescer/memory_coalescer.v) to the
//   hand-written RTL interface defined in rtl/gpu/memory_coalescer.sv, so
//   that BOTH implementations can be driven by the exact same, unmodified
//   cocotb testbench (tb/cocotb/gpu/test_memory_coalescer.py). This
//   module's port list is byte-identical to the hand-written RTL's (module
//   name aside) so TOPLEVEL can select either implementation.
//
//   This shim is combinational wiring ONLY — no registers, no FSM, no
//   logic beyond slicing/concatenation/tie-offs. Shim area is reported as
//   a separate line in the PPA comparison and must stay zero-register.
//
// Coding rules:
//   * No #delays, no initial blocks, no real types
//   * Wire-only: zero registers, zero always blocks
//   * No `default_nettype` directive (Spyglass IND, CODING_GUIDELINES.md §1.3)
//
// Lint target: verilator -Wall -Wno-DECLFILENAME 0 errors 0 warnings on
//              this file (the wrapped HLS core is machine-generated and is
//              linted/waived separately — see GH #119).

module memory_coalescer_hls
    import gpu_pkg::*;
#(
    /* verilator lint_off UNUSEDPARAM */
    parameter logic GPU_ENABLE_COALESCE = 1'b0  // Phase 4: serial only by default
    /* verilator lint_on UNUSEDPARAM */
)(
    input  logic clk,
    input  logic rst_n,

    // -----------------------------------------------------------------------
    // Request/response — from/to gpu_memory_unit
    // -----------------------------------------------------------------------
    input  logic                          start_i,   // single-cycle pulse
    input  logic                          we_i,      // 1=store, 0=load
    input  logic [N_LANES-1:0][31:0]      addr_i,
    input  logic [N_LANES-1:0][31:0]      wdata_i,
    input  logic [N_LANES-1:0]            mask_i,

    output logic                          done_o,    // single-cycle pulse on completion
    output logic [N_LANES-1:0][31:0]      rdata_o,   // per-lane read results

    // -----------------------------------------------------------------------
    // AXI4 master (32-bit addr/data, single beat)
    // -----------------------------------------------------------------------
    // AR channel
    output logic [31:0]  m_araddr_o,
    output logic         m_arvalid_o,
    input  logic         m_arready_i,
    // R channel
    input  logic [31:0]  m_rdata_i,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]   m_rresp_i,     // accepted, not checked (Phase 4)
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic         m_rvalid_i,
    output logic         m_rready_o,
    // AW channel
    output logic [31:0]  m_awaddr_o,
    output logic         m_awvalid_o,
    input  logic         m_awready_i,
    // W channel
    output logic [31:0]  m_wdata_o,
    output logic [3:0]   m_wstrb_o,
    output logic         m_wvalid_o,
    input  logic         m_wready_i,
    // B channel
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]   m_bresp_i,     // accepted, not checked (Phase 4)
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic         m_bvalid_i,
    output logic         m_bready_o
);

  // ---------------------------------------------------------------------
  // Bambu HLS core instance — plain-Verilog, machine-generated.
  // ---------------------------------------------------------------------
  memory_coalescer u_core (
      .clock       (clk),
      .reset       (rst_n),   // both async active-low — direct, no inversion

      .start_port  (start_i),

      // Tie inactive: cache_reset is threaded through every hierarchy
      // level of the generated netlist (top -> _memory_coalescer ->
      // gmem_bambu_artificial_ParmMgr_modgen) as a bare input but is never
      // read by any always/assign statement anywhere in
      // memory_coalescer.v (confirmed by exhaustive grep — every match is
      // a port-list entry, an `input` declaration, or a straight
      // pass-through instance connection). It is a vestigial port left
      // over from Bambu's generic AXI4-master IP and is unrelated to this
      // cache-less, single-beat coalescer. 1'b0 is chosen to match the
      // "active-high strobe" reading of the name, i.e. "never asserted";
      // functionally it is inert either way.
      .cache_reset (1'b0),

      // gmem base address = 0. Bambu emits `mem[addr >> 2]` against this
      // base (offset = direct), so a zero base makes the AXI byte address
      // the core drives equal to addr_i[i] exactly.
      .mem         (32'd0),

      .a0 (addr_i[0]), .a1 (addr_i[1]), .a2 (addr_i[2]), .a3 (addr_i[3]),
      .a4 (addr_i[4]), .a5 (addr_i[5]), .a6 (addr_i[6]), .a7 (addr_i[7]),

      .w0 (wdata_i[0]), .w1 (wdata_i[1]), .w2 (wdata_i[2]), .w3 (wdata_i[3]),
      .w4 (wdata_i[4]), .w5 (wdata_i[5]), .w6 (wdata_i[6]), .w7 (wdata_i[7]),

      .mask ({24'd0, mask_i}),  // zero-extend 8b mask_i -> 32b mask
      .we   ({31'd0, we_i}),    // zero-extend 1b we_i   -> 32b we

      .done_port (done_o),

      .r0 (rdata_o[0]), .r1 (rdata_o[1]), .r2 (rdata_o[2]), .r3 (rdata_o[3]),
      .r4 (rdata_o[4]), .r5 (rdata_o[5]), .r6 (rdata_o[6]), .r7 (rdata_o[7]),

      // AR channel
      .m_axi_gmem_araddr  (m_araddr_o),
      .m_axi_gmem_arvalid (m_arvalid_o),
      .m_axi_gmem_arready (m_arready_i),
      // R channel
      .m_axi_gmem_rdata   (m_rdata_i),
      .m_axi_gmem_rresp   (m_rresp_i),
      .m_axi_gmem_rvalid  (m_rvalid_i),
      .m_axi_gmem_rready  (m_rready_o),
      // The repo interface has no rlast; the core is single-beat (arlen
      // hardwired 0 by the core itself), so every response beat IS the
      // last beat — tie the core's rlast input high to reflect that.
      .m_axi_gmem_rlast   (1'b1),
      // No counterpart on the repo interface; core does not check the
      // returned id/user sideband fields on this channel.
      .m_axi_gmem_rid     (6'd0),
      .m_axi_gmem_ruser   (1'b0),
      // AW channel
      .m_axi_gmem_awaddr  (m_awaddr_o),
      .m_axi_gmem_awvalid (m_awvalid_o),
      .m_axi_gmem_awready (m_awready_i),
      // W channel
      .m_axi_gmem_wdata   (m_wdata_o),
      .m_axi_gmem_wstrb   (m_wstrb_o),
      .m_axi_gmem_wvalid  (m_wvalid_o),
      .m_axi_gmem_wready  (m_wready_i),
      // B channel
      .m_axi_gmem_bresp   (m_bresp_i),
      .m_axi_gmem_bvalid  (m_bvalid_i),
      .m_axi_gmem_bready  (m_bready_o),
      // No counterpart on the repo interface; core does not check the
      // returned id/user sideband fields on this channel.
      .m_axi_gmem_bid     (6'd0),
      .m_axi_gmem_buser   (1'b0),

      // Core AXI outputs with no counterpart on the repo interface — the
      // repo's single-beat interface has no id/burst/protection/qos/
      // region/user fields, so these are intentionally left unconnected.
      /* verilator lint_off PINCONNECTEMPTY */
      .m_axi_gmem_awid     (),
      .m_axi_gmem_awlen    (),
      .m_axi_gmem_awsize   (),
      .m_axi_gmem_awburst  (),
      .m_axi_gmem_awlock   (),
      .m_axi_gmem_awcache  (),
      .m_axi_gmem_awprot   (),
      .m_axi_gmem_awqos    (),
      .m_axi_gmem_awregion (),
      .m_axi_gmem_awuser   (),
      .m_axi_gmem_wlast    (),
      .m_axi_gmem_wuser    (),
      .m_axi_gmem_arid     (),
      .m_axi_gmem_arlen    (),
      .m_axi_gmem_arsize   (),
      .m_axi_gmem_arburst  (),
      .m_axi_gmem_arlock   (),
      .m_axi_gmem_arcache  (),
      .m_axi_gmem_arprot   (),
      .m_axi_gmem_arqos    (),
      .m_axi_gmem_arregion (),
      .m_axi_gmem_aruser   ()
      /* verilator lint_on PINCONNECTEMPTY */
  );

endmodule
