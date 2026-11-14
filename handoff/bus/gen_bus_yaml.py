"""Write docs/manual/common/facts/bus.yaml (scratch helper for the PR-A author)."""
from pathlib import Path

OUT = Path(r"<repo>\docs\manual\common\facts\bus.yaml")

lines = []


def add(s=""):
    lines.append(s)


def port(name, desc, domain="clk"):
    add(f"      {name}:")
    add(f"        domain: {domain}")
    add(f'        description: "{desc}"')


add("# Words for the generated signal and parameter tables of the bus fabric.")
add("# The RTL gives the names, directions, widths and defaults. This file gives the rest.")
add("# Run: python tools/docs/gen_fact_tables.py")
add("# A description in backticks is set as code. Every port and parameter needs an entry.")
add("# domain: the name of a clock port of the same module, or clock, async or quasi-static.")
add("family: bus")
add("modules:")

# ---------------------------------------------------------------- axi4_crossbar
add("  axi4_crossbar:")
add("    rtl: rtl/soc/axi4_crossbar.sv")
add("    deps: [rtl/soc/axi_pkg.sv]")
add("    label: tm:mod:axi4-crossbar")
add("    params:")
P = {
    "N_MASTERS": ("1 or more; 4 in the SoC", "Number of master ports. The tables show the module default. The SoC sets 4."),
    "N_SLAVES": ("1 or more; 3 in the SoC", "Number of slave ports. The tables show the module default. The SoC sets 3."),
    "AW": ("32 in the SoC", "Width of an address."),
    "DW": ("32 in the SoC", "Width of a data word."),
    "SW": ("`DW`/8", "Width of the write strobes. One bit for each byte of a data word."),
    "IW": ("enough bits for the index of `N_MASTERS` masters; 4 in the SoC", "Width of the ID that the crossbar drives to a slave. The ID is the index of the master. A narrower value drops the upper bits of the index without a message."),
    "LENW": ("8 in the SoC", "Width of the burst length fields `AxLEN`."),
    "SLV_BASE": ("one inclusive base address for each slave", "Base address of each slave window. It has one 32-bit field for each slave, and the lowest field is slave 0. The SoC passes `SOC_SLV_BASE`."),
    "SLV_LIMIT": ("one inclusive limit address for each slave", "Last address of each slave window. The SoC passes `SOC_SLV_LIMIT`. The crossbar keeps the last matching slave when windows overlap."),
}
for k, (legal, desc) in P.items():
    add(f"      {k}:")
    add(f'        legal: "{legal}"')
    add(f'        description: "{desc}"')
add("    ports:")
port("clk", "Clock of the crossbar. In the SoC it is `core_clk`.", "clock")
port("rst_n", "Active-low synchronous reset. In the SoC it is `core_rst_n`.")
M = {
    "awaddr": "Write address of master `m`. The crossbar decodes it in the cycle that the engine accepts the address.",
    "awlen": "Burst length minus 1 of the write of master `m`. The crossbar passes it to the slave.",
    "awsize": "Size code of a beat of the write of master `m`. The crossbar passes it to the slave.",
    "awburst": "Burst type of the write of master `m`. The crossbar passes it to the slave.",
    "awvalid": "The master `m` offers a write address.",
    "awready": "The crossbar takes the write address of master `m`. See the text about the second ready window.",
    "wdata": "Write data of master `m`.",
    "wstrb": "Write strobes of master `m`.",
    "wlast": "The beat is the last beat of the write of master `m`. The crossbar ends the data phase on this bit.",
    "wvalid": "The master `m` offers a write data beat.",
    "wready": "The crossbar takes the write data beat of master `m`. It is high only while the write engine of the granted slave is in its data phase, or while the decode-error engine of the master sinks data.",
    "bresp": "Write response to master `m`. The response of the slave, or DECERR from the decode-error engine.",
    "bvalid": "The crossbar offers the write response to master `m`.",
    "bready": "The master `m` takes the write response.",
    "araddr": "Read address of master `m`. The crossbar decodes it in the cycle that the engine accepts the address.",
    "arlen": "Burst length minus 1 of the read of master `m`. The crossbar passes it to the slave.",
    "arsize": "Size code of a beat of the read of master `m`. The crossbar passes it to the slave.",
    "arburst": "Burst type of the read of master `m`. The crossbar passes it to the slave.",
    "arvalid": "The master `m` offers a read address.",
    "arready": "The crossbar takes the read address of master `m`. See the text about the second ready window.",
    "rdata": "Read data to master `m`. It is 0 for a decode-error beat.",
    "rresp": "Read response to master `m`. The response of the slave, or DECERR from the decode-error engine.",
    "rlast": "The beat is the last beat of the read to master `m`.",
    "rvalid": "The crossbar offers a read data beat to master `m`.",
    "rready": "The master `m` takes the read data beat.",
}
for k, v in M.items():
    port("m_" + k, v)
S = {
    "awid": "ID of the write: the index of the granted master.",
    "awaddr": "Address of the write, taken from the register that captured it.",
    "awlen": "Burst length minus 1 of the write.",
    "awsize": "Size code of a beat of the write.",
    "awburst": "Burst type of the write.",
    "awvalid": "The crossbar offers the write address to slave `s`. It is high in the address state of the write engine.",
    "awready": "Slave `s` takes the write address.",
    "wdata": "Write data of the granted master. It is 0 outside the data state.",
    "wstrb": "Write strobes of the granted master. They are 0 outside the data state.",
    "wlast": "Last-beat flag of the granted master. It is 0 outside the data state.",
    "wvalid": "The write data of the granted master is valid. It is 0 outside the data state.",
    "wready": "Slave `s` takes the write data beat.",
    "bid": "Write response ID from slave `s`. The crossbar does not use it.",
    "bresp": "Write response of slave `s`.",
    "bvalid": "Slave `s` offers the write response.",
    "bready": "The crossbar takes the write response. It follows `m_bready` of the granted master in the response state.",
    "arid": "ID of the read: the index of the granted master.",
    "araddr": "Address of the read, taken from the register that captured it.",
    "arlen": "Burst length minus 1 of the read.",
    "arsize": "Size code of a beat of the read.",
    "arburst": "Burst type of the read.",
    "arvalid": "The crossbar offers the read address to slave `s`. It is high in the address state of the read engine.",
    "arready": "Slave `s` takes the read address.",
    "rid": "Read data ID from slave `s`. The crossbar does not use it.",
    "rdata": "Read data of slave `s`.",
    "rresp": "Read response of slave `s`.",
    "rlast": "Slave `s` marks the last read beat. The read engine ends on this bit.",
    "rvalid": "Slave `s` offers a read data beat.",
    "rready": "The crossbar takes the read data beat. It follows `m_rready` of the granted master in the data state.",
}
for k, v in S.items():
    port("s_" + k, v)

# ---------------------------------------------------------------- soc_bus
add("  soc_bus:")
add("    rtl: rtl/soc/soc_bus.sv")
add("    deps: [rtl/soc/axi_pkg.sv, rtl/soc/soc_addr_map_pkg.sv, rtl/soc/soc_periph_map_pkg.sv, rtl/soc/axi4_crossbar.sv, rtl/soc/axi4_to_axilite.sv, rtl/soc/axi_lite_interconnect.sv, rtl/soc/axil_to_apb.sv, rtl/soc/apb_interconnect.sv]")
add("    label: tm:mod:soc-bus")
add("    params:")
add("      N_MASTERS:")
add('        legal: "4 in the SoC"')
add('        description: "Number of master ports of the crossbar. The value has to equal `N_MASTERS` of `soc_top`. The sizes of the three levels below come from the address-map packages."')
add("    ports:")
port("clk", "Clock of the fabric. In the SoC it is `core_clk`.", "clock")
port("rst_n", "Active-low synchronous reset of the fabric. In the SoC it is `core_rst_n`.")
for k, v in M.items():
    port("m_" + k, v.replace("master `m`", "each master").replace("of master", "of each master"))
AXI4_SLAVE = {
    "awid": ("o", "ID of the write: the index of the granted master."),
    "awaddr": ("o", "Address of the write."),
    "awlen": ("o", "Burst length minus 1 of the write."),
    "awsize": ("o", "Size code of a beat of the write."),
    "awburst": ("o", "Burst type of the write."),
    "awvalid": ("o", "The fabric offers the write address."),
    "awready": ("i", "The slave takes the write address."),
    "wdata": ("o", "Write data."),
    "wstrb": ("o", "Write strobes."),
    "wlast": ("o", "Last-beat flag of the write."),
    "wvalid": ("o", "The write data is valid."),
    "wready": ("i", "The slave takes the write data beat."),
    "bid": ("i", "Write response ID. The crossbar does not use it."),
    "bresp": ("i", "Write response of the slave."),
    "bvalid": ("i", "The slave offers the write response."),
    "bready": ("o", "The fabric takes the write response."),
    "arid": ("o", "ID of the read: the index of the granted master."),
    "araddr": ("o", "Address of the read."),
    "arlen": ("o", "Burst length minus 1 of the read."),
    "arsize": ("o", "Size code of a beat of the read."),
    "arburst": ("o", "Burst type of the read."),
    "arvalid": ("o", "The fabric offers the read address."),
    "arready": ("i", "The slave takes the read address."),
    "rid": ("i", "Read data ID. The crossbar does not use it."),
    "rdata": ("i", "Read data of the slave."),
    "rresp": ("i", "Read response of the slave."),
    "rlast": ("i", "The slave marks the last read beat."),
    "rvalid": ("i", "The slave offers a read data beat."),
    "rready": ("o", "The fabric takes the read data beat."),
}
for pre, who in (("rom", "Crossbar slave S0, the boot ROM"), ("mem", "Crossbar slave S1, the SRAM")):
    for k, (_, v) in AXI4_SLAVE.items():
        port(f"{pre}_{k}", f"{who}. {v}")
LITE = {
    "awaddr": "Address of the write.",
    "awprot": "Protection bits of the write.",
    "awvalid": "The fabric offers the write address.",
    "awready": "The slave takes the write address.",
    "wdata": "Write data.",
    "wstrb": "Write strobes.",
    "wvalid": "The write data is valid.",
    "wready": "The slave takes the write data.",
    "bresp": "Write response of the slave.",
    "bvalid": "The slave offers the write response.",
    "bready": "The fabric takes the write response.",
    "araddr": "Address of the read.",
    "arprot": "Protection bits of the read.",
    "arvalid": "The fabric offers the read address.",
    "arready": "The slave takes the read address.",
    "rdata": "Read data of the slave.",
    "rresp": "Read response of the slave.",
    "rvalid": "The slave offers the read data.",
    "rready": "The fabric takes the read data.",
}
for pre, who in (("axil_gpu", "AXI-Lite slot 0, the GPU control port"), ("axil_dma", "AXI-Lite slot 2, the DMA control port")):
    for k, v in LITE.items():
        port(f"{pre}_{k}", f"{who}. {v}")
APB = {
    "psel": "Select of each APB slot.",
    "penable": "Enable of each APB slot. It is high in the ACCESS phase.",
    "pwrite": "Direction of the transfer. High for a write.",
    "paddr": "Address of the transfer. Each slot uses bits `[11:0]` only.",
    "pwdata": "Write data.",
    "pstrb": "Write byte strobes.",
    "prdata": "Read data from each APB slot.",
    "pready": "Ready from each APB slot.",
    "pslverr": "Error from each APB slot.",
}
for k, v in APB.items():
    port("apb_" + k, v)

lines = [l.replace("master `m`", "the master of this index").replace("slave `s`", "the slave of this index") for l in lines]
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("written", len(lines), "lines")
