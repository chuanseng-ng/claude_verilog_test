# ip.tcl -- vendor IP for the Nexys Video prototype, generated at build time (bead hlrm.2, decision #3).
# No .xci / .dcp / generated sources are checked in: this script is the only description of the IP.
# Sourced by build.tcl inside an in-memory project (create_project -in_memory -part ...).
#
#   jtag_axi_0  Xilinx JTAG-to-AXI Master, AXI4-Lite, 32-bit address and data  (PROTOCOL 2 = AXI4LITE)
#   ila_sys_0   ILA on the 50 MHz system clock: 4 probes, 12 + 32 + 32 + 11 bits, 2048 samples
#   ila_cpu_0   ILA on the 75 MHz CPU clock:    3 probes, 1 + 32 + 32 bits, 2048 samples
# The probe widths MUST match fpga/nexys_video/nexys_video_dbg.sv.

proc nv_create_ips {ipdir} {
    file mkdir $ipdir
    create_ip -name jtag_axi -vendor xilinx.com -library ip -module_name jtag_axi_0 -dir $ipdir
    set_property -dict [list \
        CONFIG.PROTOCOL {2} \
        CONFIG.M_AXI_ADDR_WIDTH {32} \
        CONFIG.M_AXI_DATA_WIDTH {32} \
    ] [get_ips jtag_axi_0]

    create_ip -name ila -vendor xilinx.com -library ip -module_name ila_sys_0 -dir $ipdir
    set_property -dict [list \
        CONFIG.C_NUM_OF_PROBES {4} \
        CONFIG.C_DATA_DEPTH {2048} \
        CONFIG.C_PROBE0_WIDTH {12} \
        CONFIG.C_PROBE1_WIDTH {32} \
        CONFIG.C_PROBE2_WIDTH {32} \
        CONFIG.C_PROBE3_WIDTH {11} \
    ] [get_ips ila_sys_0]

    create_ip -name ila -vendor xilinx.com -library ip -module_name ila_cpu_0 -dir $ipdir
    set_property -dict [list \
        CONFIG.C_NUM_OF_PROBES {3} \
        CONFIG.C_DATA_DEPTH {2048} \
        CONFIG.C_PROBE0_WIDTH {1} \
        CONFIG.C_PROBE1_WIDTH {32} \
        CONFIG.C_PROBE2_WIDTH {32} \
    ] [get_ips ila_cpu_0]

    generate_target all [get_ips]
    synth_ip [get_ips]
}
