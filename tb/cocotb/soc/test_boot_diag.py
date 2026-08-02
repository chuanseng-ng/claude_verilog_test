"""
test_boot_diag.py — M9 boot fetch diagnostic.

Monitors key internal signals for 300 cycles after reset release and dumps
any cycle where interesting activity occurs:
  - icache state_q / ar_pending_q / arvalid / arready / rvalid / rlast
  - crossbar master M0 arvalid / arready
  - crossbar slave S0 (boot_rom) arvalid / arready / rvalid / rlast
  - boot_rom r_state_q
  - CPU PC (u_if.pc_q)
  - commit_valid_o

Run with:
  make MODULE=test_boot_diag TOPLEVEL=tb_soc_top VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" ...
"""

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

CLK_PERIOD_NS = 2   # 500 MHz

ICACHE = "tb_soc_top.u_soc.u_cpu.u_core.u_icache"
BOOT_ROM = "tb_soc_top.u_soc.u_boot_rom"
CPU_IF = "tb_soc_top.u_soc.u_cpu.u_core.u_if"

# xbar internal nets - Verilator uses packed single-letter suffixes for arrays.
# xbar_m_arvalid[0] lives under u_soc as xbar_m_arv[0], but because it's an
# unpacked array, cocotb exposes it per-element. Try both naming conventions.
SOC = "tb_soc_top.u_soc"


def _get(dut, dotted):
    """Walk dotted hierarchy to reach a signal handle, return None on failure."""
    parts = dotted.split(".")
    obj = dut
    for p in parts:
        try:
            obj = getattr(obj, p)
        except AttributeError:
            return None
    return obj


@cocotb.test()
async def test_diag_boot_fetch(dut):
    """Dump 300 cycles of fetch-path signals after reset release."""
    start_soc_clocks(dut, CLK_PERIOD_NS)

    drive_soc_reset(dut, True)
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0

    for _ in range(8):
        await RisingEdge(dut.clk_i)
    drive_soc_reset(dut, False)
    for _ in range(2):
        await RisingEdge(dut.clk_i)

    dut._log.info("=== DIAG: reset released, monitoring 300 cycles ===")

    # Probe handles
    ic_state    = _get(dut, f"{ICACHE}.state_q")
    ic_arvalid  = _get(dut, f"{ICACHE}.axi_arvalid_o")
    ic_arready  = _get(dut, f"{ICACHE}.axi_arready_i")
    ic_rvalid   = _get(dut, f"{ICACHE}.axi_rvalid_i")
    ic_rlast    = _get(dut, f"{ICACHE}.axi_rlast_i")
    ic_ar_pend  = _get(dut, f"{ICACHE}.ar_pending_q")
    ic_cancel_d = _get(dut, f"{ICACHE}.cancel_draining")
    ic_valid_i  = _get(dut, f"{ICACHE}.ic_valid_i")

    rom_arvalid = _get(dut, f"{BOOT_ROM}.s_arvalid")
    rom_arready = _get(dut, f"{BOOT_ROM}.s_arready")
    rom_rvalid  = _get(dut, f"{BOOT_ROM}.s_rvalid")
    rom_rlast   = _get(dut, f"{BOOT_ROM}.s_rlast")
    rom_araddr  = _get(dut, f"{BOOT_ROM}.s_araddr")
    rom_rstate  = _get(dut, f"{BOOT_ROM}.r_state_q")
    rom_arlen   = _get(dut, f"{BOOT_ROM}.s_arlen")
    rom_mem0    = _get(dut, f"{BOOT_ROM}.mem")

    cpu_pc      = _get(dut, f"{CPU_IF}.pc_q")
    commit_v    = dut.commit_valid_o

    # Report rom mem[0] once to confirm load
    if rom_mem0 is not None:
        try:
            dut._log.info(f"  boot_rom.mem[0] = 0x{int(rom_mem0[0].value):08x}")
            dut._log.info(f"  boot_rom.mem[1] = 0x{int(rom_mem0[1].value):08x}")
        except Exception as e:
            dut._log.info(f"  boot_rom.mem read error: {e}")

    def _v(sig, fmt="d"):
        """Read a signal value; return formatted string or '?' on error."""
        if sig is None:
            return "?"
        try:
            v = sig.value
            # Try integer conversion
            i = int(v)
            if fmt == "x":
                return f"0x{i:08x}"
            return str(i)
        except Exception:
            return "X"

    def _get_id(root, path):
        """Use cocotb _id() to walk a dot-separated internal path."""
        try:
            return root._id(path, extended=False)
        except Exception:
            return None

    # Try _id() approach for all internal signals
    root = dut
    ic_state2   = _get_id(root, "u_soc.u_cpu.u_core.u_icache.state_q")
    ic_arvalid2 = _get_id(root, "u_soc.u_cpu.u_core.u_icache.axi_arvalid_o")
    ic_arready2 = _get_id(root, "u_soc.u_cpu.u_core.u_icache.axi_arready_i")
    ic_rvalid2  = _get_id(root, "u_soc.u_cpu.u_core.u_icache.axi_rvalid_i")
    ic_rlast2   = _get_id(root, "u_soc.u_cpu.u_core.u_icache.axi_rlast_i")
    ic_arpend2  = _get_id(root, "u_soc.u_cpu.u_core.u_icache.ar_pending_q")
    ic_cdrn2    = _get_id(root, "u_soc.u_cpu.u_core.u_icache.cancel_draining")
    ic_valid2   = _get_id(root, "u_soc.u_cpu.u_core.u_icache.ic_valid_i")
    rom_arvalid2= _get_id(root, "u_soc.u_boot_rom.s_arvalid")
    rom_arready2= _get_id(root, "u_soc.u_boot_rom.s_arready")
    rom_rvalid2 = _get_id(root, "u_soc.u_boot_rom.s_rvalid")
    rom_rlast2  = _get_id(root, "u_soc.u_boot_rom.s_rlast")
    rom_araddr2 = _get_id(root, "u_soc.u_boot_rom.s_araddr")
    rom_rstate2 = _get_id(root, "u_soc.u_boot_rom.r_state_q")
    rom_arlen2  = _get_id(root, "u_soc.u_boot_rom.s_arlen")
    cpu_pc2     = _get_id(root, "u_soc.u_cpu.u_core.u_if.pc_q")
    trap_redir2 = _get_id(root, "u_soc.u_cpu.u_core.mem_trap_redirect")
    trap_tgt2   = _get_id(root, "u_soc.u_cpu.u_core.mem_trap_target")
    trap_cause2 = _get_id(root, "u_soc.u_cpu.u_core.mem_trap_cause_val")
    mtvec2      = _get_id(root, "u_soc.u_cpu.u_core.dbg_csr_mtvec_o")
    ex_redir2   = _get_id(root, "u_soc.u_cpu.u_core.ex_pc_redirect")
    jal_redir2  = _get_id(root, "u_soc.u_cpu.u_core.jal_redirect")
    commit_v2   = _get_id(root, "u_soc.u_cpu.u_core.commit_valid")
    commit_pc2  = _get_id(root, "u_soc.u_cpu.u_core.commit_pc")

    # Use whichever set resolved (prefer _id, fall back to getattr)
    def _pick(a, b):
        return a if a is not None else b

    ic_state    = _pick(ic_state2,   ic_state)
    ic_arvalid  = _pick(ic_arvalid2, ic_arvalid)
    ic_arready  = _pick(ic_arready2, ic_arready)
    ic_rvalid   = _pick(ic_rvalid2,  ic_rvalid)
    ic_rlast    = _pick(ic_rlast2,   ic_rlast)
    ic_ar_pend  = _pick(ic_arpend2,  ic_ar_pend)
    ic_cancel_d = _pick(ic_cdrn2,    ic_cancel_d)
    ic_valid_i  = _pick(ic_valid2,   ic_valid_i)
    rom_arvalid = _pick(rom_arvalid2, rom_arvalid)
    rom_arready = _pick(rom_arready2, rom_arready)
    rom_rvalid  = _pick(rom_rvalid2,  rom_rvalid)
    rom_rlast   = _pick(rom_rlast2,   rom_rlast)
    rom_araddr  = _pick(rom_araddr2,  rom_araddr)
    rom_rstate  = _pick(rom_rstate2,  rom_rstate)
    rom_arlen   = _pick(rom_arlen2,   rom_arlen)
    cpu_pc      = _pick(cpu_pc2,      cpu_pc)
    trap_redir  = trap_redir2
    trap_tgt    = trap_tgt2
    trap_cause  = trap_cause2
    mtvec       = mtvec2
    ex_redir    = ex_redir2
    jal_redir   = jal_redir2
    commit_v    = _pick(commit_v2, commit_v)
    commit_pc_int = commit_pc2
    c_irq2  = _get_id(root, "u_soc.u_cpu.u_core.u_ex1c.c_irq")
    c_ill2  = _get_id(root, "u_soc.u_cpu.u_core.u_ex1c.c_ill")
    c_bch2  = _get_id(root, "u_soc.u_cpu.u_core.u_ex1c.c_bch")
    ex1c_sel2 = _get_id(root, "u_soc.u_cpu.u_core.u_ex1c.sel")
    # Also probe the instruction word in EX1a (the registered stage input to EX1b)
    ex1a_insn2 = _get_id(root, "u_soc.u_cpu.u_core.u_ex1a.ex1a_o.instruction")
    ex1a_valid2 = _get_id(root, "u_soc.u_cpu.u_core.u_ex1a.ex1a_o.valid")
    irq_valid_r2 = _get_id(root, "u_soc.u_cpu.u_core.irq_valid")
    timer_irq2 = _get_id(root, "u_soc.u_cpu.timer_irq_i")
    ext_irq2   = _get_id(root, "u_soc.u_cpu.ext_irq_i")
    c_irq  = c_irq2
    c_ill  = c_ill2
    c_bch  = c_bch2
    ex1c_sel = ex1c_sel2

    # Log which handles resolved
    resolved = {
        "ic_state": ic_state, "ic_arvalid": ic_arvalid,
        "ic_arready": ic_arready, "ic_rvalid": ic_rvalid,
        "rom_arvalid": rom_arvalid, "rom_arready": rom_arready,
        "rom_rstate": rom_rstate, "cpu_pc": cpu_pc,
    }
    for name, h in resolved.items():
        dut._log.info(f"  handle {name}: {'OK' if h is not None else 'NONE'}")

    prev_ic_state = None
    prev_rom_rstate = None

    for cyc in range(300):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        ic_st   = _v(ic_state)
        rom_st  = _v(rom_rstate)
        cv      = _v(commit_v)
        arv     = _v(ic_arvalid)
        arr     = _v(ic_arready)
        rv      = _v(ic_rvalid)
        rl      = _v(ic_rlast)
        pend    = _v(ic_ar_pend)
        cdrn    = _v(ic_cancel_d)
        ic_vi   = _v(ic_valid_i)
        pc      = _v(cpu_pc, "x")
        rom_arv = _v(rom_arvalid)
        rom_arr = _v(rom_arready)
        rom_rv  = _v(rom_rvalid)
        rom_rl  = _v(rom_rlast)
        rom_aa  = _v(rom_araddr, "x")
        rom_al  = _v(rom_arlen)

        tr    = _v(trap_redir)
        tt    = _v(trap_tgt,   "x")
        tc    = _v(trap_cause)
        mv    = _v(mtvec,      "x")
        er    = _v(ex_redir)
        jr    = _v(jal_redir)
        cpc   = _v(commit_pc_int, "x")
        cirq  = _v(c_irq)
        cill  = _v(c_ill)
        cbch  = _v(c_bch)
        csel  = _v(ex1c_sel)

        interesting = (
            ic_st != prev_ic_state or
            rom_st != prev_rom_rstate or
            arv == "1" or arr == "1" or
            rv  == "1" or rl  == "1" or
            rom_arv == "1" or rom_rv == "1" or
            cv  == "1" or
            tr  == "1" or er  == "1" or jr == "1" or
            cirq == "1" or cill == "1" or cbch == "1" or
            cyc < 20 or cyc % 50 == 0
        )
        if interesting:
            dut._log.info(
                f"  cyc={cyc:3d} PC={pc} "
                f"ic_vi={ic_vi} ic_st={ic_st} arv={arv} arr={arr} rv={rv} rl={rl} | "
                f"er={er} jr={jr} trap={tr} mtvec={mv} | "
                f"c_irq={cirq} c_ill={cill} c_bch={cbch} sel={csel} | "
                f"commit={cv} cpc={cpc}"
            )
        prev_ic_state   = ic_st
        prev_rom_rstate = rom_st

        if cv == "1":
            dut._log.info(f"  *** FIRST COMMIT at cyc={cyc}, PC={cpc}")
            # Don't break — keep tracing to see if it commits more
    else:
        dut._log.warning("DIAG: no commit in 300 cycles — fetch stalled somewhere")
