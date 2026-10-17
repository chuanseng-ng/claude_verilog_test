# ip.tcl -- vendor IP for the Nexys Video prototype, generated at build time (bead hlrm.2, decision #3).
# No .xci / .dcp / generated sources are checked in: this script is the only description of the IP.
# Sourced by build.tcl inside an in-memory project (create_project -in_memory -part ...).
#
#   jtag_axi_0  Xilinx JTAG-to-AXI Master, AXI4-Lite, 32-bit address and data  (PROTOCOL 2 = AXI4LITE)
#   ila_0       the ONLY ILA (BASIC licence), 75 MHz CPU clock, 5 probes: 24 (paddr, APB/flags, commit_valid) / 32 pwdata / 32 prdata / 32 commit_pc / 32 commit_insn
# The probe widths MUST match fpga/nexys_video/nexys_video_dbg.sv.

proc nv_create_ips {ipdir} {
    file mkdir $ipdir
    create_ip -name jtag_axi -vendor xilinx.com -library ip -module_name jtag_axi_0 -dir $ipdir
    set_property -dict [list \
        CONFIG.PROTOCOL {2} \
        CONFIG.M_AXI_ADDR_WIDTH {32} \
        CONFIG.M_AXI_DATA_WIDTH {32} \
    ] [get_ips jtag_axi_0]

    # ONE ILA, at most 5 probes: the free (BASIC) Vivado licence rejects more ([Chipscope 16-620]).
    create_ip -name ila -vendor xilinx.com -library ip -module_name ila_0 -dir $ipdir
    set_property -dict [list \
        CONFIG.C_NUM_OF_PROBES {5} \
        CONFIG.C_DATA_DEPTH {2048} \
        CONFIG.C_PROBE0_WIDTH {24} \
        CONFIG.C_PROBE1_WIDTH {32} \
        CONFIG.C_PROBE2_WIDTH {32} \
        CONFIG.C_PROBE3_WIDTH {32} \
        CONFIG.C_PROBE4_WIDTH {32} \
    ] [get_ips ila_0]

    generate_target all [get_ips]
    synth_ip [get_ips]
}
