"""
test_soc_integration.py -- SoC-level directed tests for the soc_top integration gaps
found by the GH #216 coverage run (bead claude_verilog_test-oez2).

DUT: tb_soc_top (the whole SoC, one Vtop build shared by every test below).

Each gap is exercised end to end with a BEHAVIOURAL check, not just a toggle:

  test_soc_irq_traps_and_spi_miso   firmware (integ_fw irq_spi.hex) programs timer / UART /
      SPI / DMA so each raises its IRQ; interrupt_controller routes it (timer bypasses it
      and goes to MTIP); the CPU takes the trap (ISR_PC committed, mcause / pending logged
      and checked by firmware, the RTL nets sampled at trap entry and again after the
      handler); the handler clears the source.  The SPI phase is NON-loopback against a
      testbench slave model, so spi_miso_i is driven and the received byte is checked
      (firmware: 0xA6), and the slave checks the MOSI byte and CS framing.
  test_soc_pll_register_programming  firmware (pll_prog.hex) writes both PLLs' CONTROL
      dividers through the fabric (PLL1 via u_apb_pll_cdc, PLL2 via u_apb_pll2_cdc); the
      testbench reads pll_fb_div / pll_post_div of BOTH instances after every write and
      proves the other instance was untouched.  pll_clkgen_stub is a pass-through by design
      (it accepts but ignores the dividers, see its header), so the observable
      "PLL output" is the divider ports at pll_clkgen plus the lock flag staying asserted.
  test_soc_gpu_isolation_via_pmu    firmware (gpu_iso.hex) leaves gpu_irq_o level-high, the
      PMU powers the GPU domain off then on; the testbench checks the PMU sequence order,
      the isolation clamp (gpu_irq_o == gpu_irq_raw & !gpu_iso_en on EVERY cycle, with
      raw=1 / out=0 in the iso-before-reset window), that the GPU loses its state (async
      reset flops -- see the FINDING in gen_integ_hex.py) and that a relaunch works.
  test_soc_debug_apb_halt_gpr_step  the external APB debug master (tb_soc_top apb_* ports)
      halts the CPU, reads / writes GPRs, the PC and breakpoint registers, single-steps and
      resumes, all through u_apb_dbg_cdc.
  test_soc_debug_apb_ro_write_pslverr  a write to each read-only CSR debug register
      (0x200-0x214) returns PSLVERR at the SoC port (CPU debug pslverr carried through the
      bridge); legal writes and the gap above the range do not.
  test_soc_debug_apb_dest_reset_pslverr  the bridge's force-complete path: the CPU-domain
      reset (the bridge's destination) is held low, the debug access must COMPLETE with
      PSLVERR instead of hanging; also with the reset asserted while a request is in flight.

GOLDEN-MODEL NOTE: as in test_soc_gpio / test_periph_loopback, SoCModel rejects 0x2000_xxxx
MMIO, so firmware is self-checking and the testbench scoreboards commit_pc_o.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sim.riscv_encoder import ADDI, JAL  # noqa: E402
from tb.cocotb.soc.integ_fw import integ_fw_addrs as A  # noqa: E402

CLK_PERIOD_NS = 2
_FW_DIR = Path(__file__).parent / "integ_fw"
NOP = 0x00000013

# Debug register map (rtl/cpu/rv32i_cpu_top.sv)
DBG_CTRL, DBG_STATUS, DBG_PC = 0x000, 0x004, 0x008
DBG_BP0_ADDR, DBG_BP0_CTRL = 0x100, 0x104
CSR_DBG_REGS = (0x200, 0x204, 0x208, 0x20C, 0x210, 0x214)
CTRL_HALT, CTRL_RESUME, CTRL_STEP = 1, 2, 4


def _gpr_addr(n: int) -> int:
    return 0x010 + 4 * n


_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _read_hex(path: Path) -> list:
    words = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if tok and not tok.startswith("//") and not tok.startswith("@"):
                words.append(int(tok, 16))
    return words


def _load_words(dut, words: list) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    assert len(words) <= len(mem)
    for i, w in enumerate(words):
        mem[i].value = w


async def _setup(dut, words: list) -> None:
    """Clocks, idle inputs, backdoor-load the ROM image, reset."""
    _kill_active_tasks()
    clk_task, cpu_clk_task = start_soc_clocks(dut, CLK_PERIOD_NS)
    _active_tasks.extend([clk_task, cpu_clk_task])

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0
    dut.gpio_in_i.value = 0
    dut.i2c_scl_i.value = 1
    dut.i2c_sda_i.value = 1

    _load_words(dut, words)
    for _ in range(5):
        await RisingEdge(dut.clk_i)
    drive_soc_reset(dut, False)
    for _ in range(2):
        await RisingEdge(dut.clk_i)


# ---------------------------------------------------------------------------
# Test 1: interrupt lines + SPI MISO
# ---------------------------------------------------------------------------
class SpiSlave:
    """Mode-0 (CPOL=0, CPHA=0) SPI slave, MSB first, byte-at-a-time.

    MISO is held at the next response byte's MSB while idle and advances on each falling
    SCLK edge, so it is stable for half an SCLK period (8 fabric clocks at CLK_DIV=7)
    before every sampling edge -- comfortably over the 2-FF synchroniser latency.
    MOSI is captured on each rising edge.  CS framing is observed from spi_cs_n_o.
    """

    def __init__(self, dut, responses):
        self.dut = dut
        self.responses = list(responses)
        self.resp_idx = 0
        self.bit_idx = 0
        self.mosi_bits = []
        self.mosi_bytes = []
        self.rises = 0
        self.cs_low_cycles = 0
        self.saw_cs_low = False
        self.cs_high_after_low = False
        dut.spi_miso_i.value = (self.responses[0] >> 7) & 1

    async def run(self):
        dut = self.dut
        prev = int(dut.spi_sclk_o.value)
        while True:
            await RisingEdge(dut.clk_i)
            sclk = int(dut.spi_sclk_o.value)
            cs_n = int(dut.spi_cs_n_o.value)
            if cs_n == 0:
                self.saw_cs_low = True
                self.cs_low_cycles += 1
            elif self.saw_cs_low:
                self.cs_high_after_low = True
            if sclk and not prev:                      # rising: master samples MISO
                self.rises += 1
                self.mosi_bits.append(int(dut.spi_mosi_o.value))
                self.bit_idx += 1
                if len(self.mosi_bits) == 8:
                    self.mosi_bytes.append(int("".join(map(str, self.mosi_bits)), 2))
                    self.mosi_bits = []
            elif prev and not sclk:                    # falling: present the next bit
                if self.bit_idx >= 8:
                    self.bit_idx = 0
                    self.resp_idx = min(self.resp_idx + 1, len(self.responses) - 1)
                    dut.spi_miso_i.value = (self.responses[self.resp_idx] >> 7) & 1
                else:
                    cur = self.responses[self.resp_idx]
                    dut.spi_miso_i.value = (cur >> (7 - self.bit_idx)) & 1
            prev = sclk


@cocotb.test()
async def test_soc_irq_traps_and_spi_miso(dut):
    """Timer / UART / SPI / DMA each raise their IRQ, the CPU traps, the handler clears it."""
    await _setup(dut, _read_hex(_FW_DIR / "irq_spi.hex"))
    slave = SpiSlave(dut, [A.SPI_SLAVE_RESP, 0x00])
    _active_tasks.append(cocotb.start_soon(slave.run()))

    pass_pc, fail_pc, isr_pc = A.IRQ_SPI_PASS, A.IRQ_SPI_FAIL, A.IRQ_SPI_ISR
    soc = dut.u_soc
    # phase -> (source net, via interrupt_controller?)
    phases = [("timer_irq", False), ("uart_irq", True), ("spi_irq", True), ("dma_irq", True)]
    DEASSERT_DELAY = 600
    entries = 0
    checks = []            # (due_cycle, net_name)
    seen_high = {n: False for n, _ in phases}
    seen_low_after = {n: False for n, _ in phases}
    saw_pass = False
    recent = []

    for cycle in range(400_000):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        for n, _ in phases:
            if int(getattr(soc, n).value):
                seen_high[n] = True
        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            recent = (recent + [pc])[-16:]
            assert pc != fail_pc, (
                f"firmware reached FAIL_PC after {entries} trap(s); recent PCs "
                + " ".join(f"0x{p:08x}" for p in recent))
            if pc == isr_pc:
                assert entries < len(phases), "more traps than interrupt phases (stuck line)"
                net, via_ctrl = phases[entries]
                assert int(getattr(soc, net).value) == 1, (
                    f"trap {entries + 1} taken but {net} is not asserted")
                assert int(soc.ext_irq.value) == int(via_ctrl), (
                    f"{net}: ext_irq={int(soc.ext_irq.value)} at trap entry, expected "
                    f"{int(via_ctrl)} ({'routed by interrupt_controller' if via_ctrl else 'MTIP direct, bypasses it'})")
                if not via_ctrl:
                    assert int(soc.timer_irq_cpu_sync.value) == 1
                checks.append((cycle + DEASSERT_DELAY, net))
                entries += 1
            if pc == pass_pc:
                saw_pass = True
                break
        for due, net in list(checks):
            if cycle >= due:
                checks.remove((due, net))
                assert int(getattr(soc, net).value) == 0, (
                    f"{net} still asserted {DEASSERT_DELAY} cycles after its handler ran")
                if net != "timer_irq":
                    assert int(soc.ext_irq.value) == 0, "ext_irq stuck after the handler"
                seen_low_after[net] = True

    assert saw_pass, f"PASS_PC never committed; recent PCs " + " ".join(f"0x{p:08x}" for p in recent)
    assert entries == len(phases), f"expected {len(phases)} traps, saw {entries}"
    # let the last deassert window elapse (DMA handler is the last trap)
    for _ in range(DEASSERT_DELAY + 5):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        for due, net in list(checks):
            checks.remove((due, net))
            assert int(getattr(soc, net).value) == 0, f"{net} still asserted after its handler"
            seen_low_after[net] = True
    for n, _ in phases:
        assert seen_high[n], f"{n} never asserted"
        assert seen_low_after[n], f"{n} deassertion was never checked"

    # SPI slave view: MOSI byte, framing, and the firmware already proved RX == 0xA6.
    assert slave.mosi_bytes == [A.SPI_TX_BYTE], (
        f"slave captured MOSI bytes {[hex(b) for b in slave.mosi_bytes]}, expected "
        f"[{hex(A.SPI_TX_BYTE)}]")
    assert slave.rises == 8, f"{slave.rises} SCLK rising edges, expected 8"
    assert slave.saw_cs_low and slave.cs_high_after_low, "spi_cs_n_o was not framed low then high"


# ---------------------------------------------------------------------------
# Test 2: PLL programming
# ---------------------------------------------------------------------------
def _pll_fields(sub):
    return int(sub.pll_fb_div.value), int(sub.pll_post_div.value)


@cocotb.test()
async def test_soc_pll_register_programming(dut):
    """Firmware programs both PLLs' dividers; the divider ports follow, independently."""
    await _setup(dut, _read_hex(_FW_DIR / "pll_prog.hex"))
    p1, p2 = dut.u_soc.u_pll_sub, dut.u_soc.u_cpu_pll_sub
    fields = lambda v: ((v >> 4) & 0xF, (v >> 8) & 0x3)  # noqa: E731
    markers = {
        A.PLL_PROG_PLL_RESET_OK: ((0, 0), (0, 0)),
        A.PLL_PROG_PLL1_A: (fields(A.PLL1_VAL_A), (0, 0)),
        A.PLL_PROG_PLL2_PROGRAMMED: (fields(A.PLL1_VAL_A), fields(A.PLL2_VAL)),
        A.PLL_PROG_PLL1_B: (fields(A.PLL1_VAL_B), fields(A.PLL2_VAL)),
    }
    seen = set()
    saw_pass = False
    for _ in range(100_000):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if not dut.commit_valid_o.value:
            continue
        pc = int(dut.commit_pc_o.value)
        assert pc != A.PLL_PROG_FAIL, "firmware reached FAIL_PC (CONTROL readback / lock check)"
        if pc in markers and pc not in seen:
            seen.add(pc)
            want1, want2 = markers[pc]
            got1, got2 = _pll_fields(p1), _pll_fields(p2)
            assert got1 == want1, f"PLL1 (fb_div, post_div) = {got1}, expected {want1} at 0x{pc:08x}"
            assert got2 == want2, f"PLL2 (fb_div, post_div) = {got2}, expected {want2} at 0x{pc:08x}"
            assert int(dut.pll_locked_o.value) == 1, "system PLL lost lock after a divider write"
            assert int(p1.pll_locked.value) == 1 and int(p2.pll_locked.value) == 1
            # the value reaches the PLL core (pll_clkgen) inputs, not just the register file
            assert int(p1.u_pll.feedback_div.value) == want1[0]
            assert int(p1.u_pll.post_div_sel.value) == want1[1]
            assert int(p2.u_pll.feedback_div.value) == want2[0]
            assert int(p2.u_pll.post_div_sel.value) == want2[1]
        if pc == A.PLL_PROG_PASS:
            saw_pass = True
            break
    assert saw_pass, "PASS_PC never committed"
    assert seen == set(markers), f"markers not all hit: {[hex(m) for m in set(markers) - seen]}"


# ---------------------------------------------------------------------------
# Test 3: GPU isolation through the PMU
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_soc_gpu_isolation_via_pmu(dut):
    """PMU GPU_OFF / NORMAL: sequence order, isolation clamp on gpu_irq_o, state survives."""
    await _setup(dut, _read_hex(_FW_DIR / "gpu_iso.hex"))
    soc = dut.u_soc
    sig = ("pmu_gpu_ret_save", "pmu_gpu_iso_en", "pmu_gpu_clk_en", "pmu_gpu_rst_n",
           "pmu_gpu_ret_restore")
    events = []            # (cycle, name, value)
    prev = {n: int(getattr(soc, n).value) for n in sig}
    markers_seen = {}
    clamped_cycles = 0
    saw_pass = False
    for cycle in range(600_000):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        cur = {n: int(getattr(soc, n).value) for n in sig}
        for n in sig:
            if cur[n] != prev[n]:
                events.append((cycle, n, cur[n]))
        prev = cur
        raw, out, iso = int(soc.gpu_irq_raw.value), int(dut.gpu_irq_o.value), cur["pmu_gpu_iso_en"]
        assert out == (raw & (1 - iso)), (
            f"cycle {cycle}: gpu_irq_o={out} but gpu_irq_raw={raw} gpu_iso_en={iso}")
        if iso and raw:
            clamped_cycles += 1
        if not dut.commit_valid_o.value:
            continue
        pc = int(dut.commit_pc_o.value)
        assert pc != A.GPU_ISO_FAIL, "firmware reached FAIL_PC"
        if pc == A.GPU_ISO_GPU_DONE:
            markers_seen["done"] = (raw, out, iso)
            assert (raw, out, iso) == (1, 1, 0), "after the kernel: gpu_irq must be high, un-isolated"
        elif pc == A.GPU_ISO_GPU_OFF:
            markers_seen["off"] = (raw, out, iso, cur["pmu_gpu_clk_en"], cur["pmu_gpu_rst_n"])
            assert markers_seen["off"] == (0, 0, 1, 0, 0), (
                "GPU domain off: expected iso=1, clk_en=0, rst_n=0 and (state lost to the async "
                f"domain reset) raw irq 0, got {markers_seen['off']}")
        elif pc == A.GPU_ISO_GPU_ON:
            markers_seen["on"] = (raw, out, iso)
            assert (raw, out, iso) == (0, 0, 0), (
                "GPU back on: un-isolated and (reset state) irq low")
        elif pc == A.GPU_ISO_GPU_RELAUNCHED:
            markers_seen["relaunched"] = (raw, out, iso)
            assert (raw, out, iso) == (1, 1, 0), (
                "second kernel after the power cycle: irq must reach gpu_irq_o through the "
                "released isolation")
        elif pc == A.GPU_ISO_IRQ_CLR:
            markers_seen["clr"] = cycle
        elif pc == A.GPU_ISO_PASS:
            saw_pass = True
            break
    assert saw_pass, f"PASS_PC never committed; markers {markers_seen}"
    assert set(markers_seen) == {"done", "off", "on", "relaunched", "clr"}, markers_seen
    # The clamp is only observable between iso_en rising and the reset asserting (the GPU's
    # async-reset flops then drop the level-held irq): require it actually acted.
    assert clamped_cycles >= 1, "gpu_irq_raw=1 with iso_en=1 was never observed: clamp never acted"

    # Power-down order: ret_save -> iso_en -> clk gate -> reset.  Power-up: the reverse
    # (reset release -> clk ungate -> ret_restore -> iso release).  (pmu.sv header.)
    def first(name, val, after=-1):
        for c, n, v in events:
            if n == name and v == val and c > after:
                return c
        raise AssertionError(f"no {name}->{val} event after cycle {after}: {events}")

    t_save = first("pmu_gpu_ret_save", 1)
    t_iso = first("pmu_gpu_iso_en", 1)
    t_gate = first("pmu_gpu_clk_en", 0)
    t_rst = first("pmu_gpu_rst_n", 0)
    assert t_save < t_iso < t_gate < t_rst, f"power-down order wrong: {events}"
    t_rst_up = first("pmu_gpu_rst_n", 1, t_rst)
    t_clk_up = first("pmu_gpu_clk_en", 1, t_gate)
    t_restore = first("pmu_gpu_ret_restore", 1, t_rst)
    t_iso_off = first("pmu_gpu_iso_en", 0, t_iso)
    assert t_rst_up < t_clk_up < t_restore < t_iso_off, f"power-up order wrong: {events}"

    # The irq cleared after IRQ_CLR, and the GPU's DMA-visible result survived intact.
    for _ in range(100):
        await RisingEdge(dut.clk_i)
    assert int(dut.gpu_irq_o.value) == 0, "gpu_irq_o still high after GPU_IRQ_CLR"
    sram = dut.u_soc.u_sram.mem
    for lane in range(8):
        got = int(sram[112 + lane].value)
        assert got == (lane + 1) * 0x20 + 1, f"GPU result lane {lane}: 0x{got:x}"


# ---------------------------------------------------------------------------
# Debug APB master (tb_soc_top apb_* ports, clk_i domain)
# ---------------------------------------------------------------------------
async def dbg_xfer(dut, addr, write=False, data=0, max_wait=600):
    """One APB3 transfer.  Returns (rdata, pslverr, completed)."""
    dut.apb_paddr_i.value = addr
    dut.apb_pwrite_i.value = 1 if write else 0
    dut.apb_pwdata_i.value = data
    dut.apb_psel_i.value = 1
    dut.apb_penable_i.value = 0
    await RisingEdge(dut.clk_i)
    dut.apb_penable_i.value = 1
    await RisingEdge(dut.clk_i)
    waited = 0
    while not int(dut.apb_pready_o.value):
        waited += 1
        if waited > max_wait:
            dut.apb_psel_i.value = 0
            dut.apb_penable_i.value = 0
            dut.apb_pwrite_i.value = 0
            return 0, False, False
        await RisingEdge(dut.clk_i)
    rdata = int(dut.apb_prdata_o.value)
    err = bool(int(dut.apb_pslverr_o.value))
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    return rdata, err, True


async def dbg_read(dut, addr):
    rd, err, ok = await dbg_xfer(dut, addr)
    assert ok, f"debug read 0x{addr:03x} never completed"
    return rd, err


async def dbg_write(dut, addr, data):
    _, err, ok = await dbg_xfer(dut, addr, True, data)
    assert ok, f"debug write 0x{addr:03x} never completed"
    return err


async def _wait_status(dut, bit, want=1, tries=60):
    for _ in range(tries):
        st, _ = await dbg_read(dut, DBG_STATUS)
        if ((st >> bit) & 1) == want:
            return st
    raise AssertionError(f"DBG_STATUS bit {bit} never became {want}")


def _spin_rom() -> list:
    """x5++ ; x6 = 0x55 ; loop.  Never terminates, never traps."""
    words = [ADDI(5, 5, 1), ADDI(6, 0, 0x55), JAL(0, -8)]
    return words + [NOP] * (1024 - len(words))


async def _boot_spin(dut) -> None:
    await _setup(dut, _spin_rom())
    for _ in range(300):
        await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_soc_debug_apb_halt_gpr_step(dut):
    """External debug master: halt, read/write GPRs, PC, breakpoint regs; step; resume."""
    await _boot_spin(dut)
    ctrl, _ = await dbg_read(dut, DBG_CTRL)
    assert ctrl == 0
    st, err = await dbg_read(dut, DBG_STATUS)
    assert not err and (st & 3) == 2, f"CPU should be running before halt, DBG_STATUS=0x{st:x}"

    assert not await dbg_write(dut, DBG_CTRL, CTRL_HALT)
    st = await _wait_status(dut, 0)
    assert (st & 3) == 1
    pc, _ = await dbg_read(dut, DBG_PC)
    assert 0x1000 <= pc <= 0x1008, f"halted PC 0x{pc:08x} not inside the spin loop"
    x5a, _ = await dbg_read(dut, _gpr_addr(5))
    x5b, _ = await dbg_read(dut, _gpr_addr(5))
    assert x5a == x5b and x5a > 0, f"x5 must be frozen and non-zero while halted ({x5a}, {x5b})"
    x6, _ = await dbg_read(dut, _gpr_addr(6))
    assert x6 == 0x55

    # GPR write/readback; x0 is hard-wired
    assert not await dbg_write(dut, _gpr_addr(7), 0xDEADBEEF)
    for _ in range(4):
        await RisingEdge(dut.clk_i)
    x7, _ = await dbg_read(dut, _gpr_addr(7))
    assert x7 == 0xDEADBEEF, f"x7 readback 0x{x7:08x}"
    assert not await dbg_write(dut, _gpr_addr(0), 0x1234)
    x0, _ = await dbg_read(dut, _gpr_addr(0))
    assert x0 == 0, "x0 must stay 0 after a debug write"

    # full-width data patterns survive the CDC bridge both ways
    for reg, pat in ((8, 0xAAAA_AAAA), (9, 0x5555_5555), (10, 0xFFFF_FFFF), (11, 0)):
        assert not await dbg_write(dut, _gpr_addr(reg), pat)
        for _ in range(4):
            await RisingEdge(dut.clk_i)
        got, _ = await dbg_read(dut, _gpr_addr(reg))
        assert got == pat, f"x{reg}: wrote 0x{pat:08x}, read 0x{got:08x}"

    # breakpoint registers read back what was written (halted), then are cleared again
    assert not await dbg_write(dut, DBG_BP0_ADDR, 0x1234_5678)
    bp, _ = await dbg_read(dut, DBG_BP0_ADDR)
    assert bp == 0x1234_5678
    assert not await dbg_write(dut, DBG_BP0_ADDR, 0)

    # PC write + single step: one instruction, then halted again
    assert not await dbg_write(dut, DBG_PC, 0x1000)
    for _ in range(8):
        await RisingEdge(dut.clk_i)
    pc, _ = await dbg_read(dut, DBG_PC)
    assert pc == 0x1000, f"PC write did not take: 0x{pc:08x}"
    x5_before, _ = await dbg_read(dut, _gpr_addr(5))
    assert not await dbg_write(dut, DBG_CTRL, CTRL_STEP)
    await _wait_status(dut, 0)
    pc, _ = await dbg_read(dut, DBG_PC)
    assert pc == 0x1004, f"single step from 0x1000 should land on 0x1004, got 0x{pc:08x}"
    x5_after, _ = await dbg_read(dut, _gpr_addr(5))
    assert x5_after == x5_before + 1, "the stepped ADDI x5,x5,1 did not retire exactly once"

    # resume: the loop runs again (x5 keeps counting), then halt again to prove it
    assert not await dbg_write(dut, DBG_CTRL, CTRL_RESUME)
    await _wait_status(dut, 1)
    commits = 0
    for _ in range(60):
        await RisingEdge(dut.clk_i)
        commits += int(dut.commit_valid_o.value)
    assert commits > 10, "CPU not retiring instructions after resume"
    assert not await dbg_write(dut, DBG_CTRL, CTRL_HALT)
    await _wait_status(dut, 0)
    x5_end, _ = await dbg_read(dut, _gpr_addr(5))
    assert x5_end > x5_after + 5


@cocotb.test()
async def test_soc_debug_apb_ro_write_pslverr(dut):
    """Writes to the read-only CSR debug registers return PSLVERR at the SoC port."""
    await _boot_spin(dut)
    before = {}
    for a in CSR_DBG_REGS:
        v, err = await dbg_read(dut, a)
        assert not err, f"read of 0x{a:03x} must not error"
        before[a] = v
    for a in CSR_DBG_REGS:
        err = await dbg_write(dut, a, 0xA5A5_5A5A)
        assert err, f"write to RO debug register 0x{a:03x} must return PSLVERR"
    for a in CSR_DBG_REGS:                       # ... and must not have changed it
        v, _ = await dbg_read(dut, a)
        assert v == before[a], f"RO register 0x{a:03x} changed: 0x{before[a]:x} -> 0x{v:x}"
    # address / data walking sweep with the CPU running (writes to PC / GPR / breakpoint
    # registers are dropped when not halted): only the RO CSR window may raise PSLVERR.
    for k in range(12):
        a = 1 << k
        for pat in (0xFFFF_FFFF, 0xAAAA_AAAA, 0x5555_5555, 0):
            err = await dbg_write(dut, a, pat)
            assert err == (0x200 <= a <= 0x214 and a % 4 == 0), (
                f"write 0x{a:03x}: pslverr={err}")
        await dbg_read(dut, a)
    # negative controls: legal writes and addresses outside 0x200-0x214 do not error
    assert not await dbg_write(dut, DBG_CTRL, 0)
    assert not await dbg_write(dut, 0x218, 0x1)
    assert not await dbg_write(dut, DBG_BP0_ADDR, 0)
    # and a read of an RO register right after an errored write is clean
    _, err = await dbg_read(dut, 0x200)
    assert not err


@cocotb.test()
async def test_soc_debug_apb_dest_reset_pslverr(dut):
    """Bridge force-complete: destination (CPU-domain) in reset -> PSLVERR, never a hang."""
    await _boot_spin(dut)
    ok_val, err = await dbg_read(dut, DBG_STATUS)
    assert not err

    async def recover():
        dut.cpu_rst_n_i.value = 1
        for _ in range(150):                      # PLL lock window + synchronisers
            await RisingEdge(dut.clk_i)
        _, e = await dbg_read(dut, DBG_STATUS)
        assert not e, "debug access must be clean again once the CPU domain is out of reset"

    # (a) destination already observed in reset when the request arrives
    dut.cpu_rst_n_i.value = 0
    for _ in range(20):
        await RisingEdge(dut.clk_i)
    rd, err, ok = await dbg_xfer(dut, DBG_STATUS)
    assert ok, "debug read hung while the destination was in reset"
    assert err, "debug read with the destination in reset must complete with PSLVERR"
    _, err, ok = await dbg_xfer(dut, DBG_CTRL, True, CTRL_HALT)
    assert ok and err, "debug write with the destination in reset must complete with PSLVERR"
    await recover()

    # (b) destination reset asserted while the request is in flight
    forced = []
    for offset in (1, 2, 3, 4, 6, 9):
        dut.apb_paddr_i.value = DBG_STATUS
        dut.apb_pwrite_i.value = 0
        dut.apb_psel_i.value = 1
        dut.apb_penable_i.value = 0
        await RisingEdge(dut.clk_i)
        dut.apb_penable_i.value = 1
        for _ in range(offset):
            await RisingEdge(dut.clk_i)
        dut.cpu_rst_n_i.value = 0
        waited = 0
        while not int(dut.apb_pready_o.value):
            waited += 1
            assert waited < 200, f"offset {offset}: in-flight debug access hung across a destination reset"
            await RisingEdge(dut.clk_i)
        forced.append((offset, bool(int(dut.apb_pslverr_o.value))))
        dut.apb_psel_i.value = 0
        dut.apb_penable_i.value = 0
        await recover()
    dut._log.info("in-flight reset offset -> pslverr: %s", forced)
    assert forced[0][1] or forced[1][1], (
        f"reset 1-2 cycles into the request must force-complete with PSLVERR, got {forced}")
