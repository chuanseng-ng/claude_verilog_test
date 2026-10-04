"""
test_soc_npu.py — Phase 6c-5 SoC-level NPU FABRIC test (bead claude_verilog_test-f7vs.11,
docs/PHASE6_IP_EXPANSION_PLAN.md §7 "6c -- NPU", L2 testability).

`test_npu` (tb_npu.sv / Makefile `npu` target) owns every behaviour of npu_top — arithmetic,
requantiser corners, FIFO depths, weight-write rejection, sticky-IRQ and hang-free paths — driving
the APB4 face directly. It has never exercised the peripheral through the real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 13 (APB_NPU, 0x2001_0000)

nor its IRQ into interrupt_controller bit 11. This suite proves exactly that and nothing more: it
re-proves NONE of the L1 behaviour (three small inferences are enough to show the weight, AIN, AOUT
and control paths are intact end to end). Firmware comes from a committed pure-Python
hand-assembler (npu_fw/gen_npu_hex.py, sharing trng_fw's assembler) — no riscv32 cross toolchain,
so the suite is CI-safe. Synchronisation and scoring are by commit_pc_o marker PCs, the technique
test_soc_crypto.py / test_soc_trng.py / test_soc_i2c.py use.

One test, one image, three phases (see the generator header for the firmware side).

PHASE 1 — polled, KLEN = 1, TILEBASE = 8, SCALE (5 >> 0), IRQ_EN = 0
  Firmware loads a 12-word weight tile through WADDR/WDATA, pushes one AIN word, starts, polls
  STATUS.done, pops AOUT. Scored here:
    * the stored AOUT against tb/models/npu_model.py (recomputed here from int8 element lists);
    * STATUS / IRQ_STAT / WADDR auto-increment / write-only WDATA, as read by the CPU over the bus;
    * the IE gate: `done` is pending for a long stretch and npu_irq / irq_src_i[11] / ext_irq stay
      LOW the whole time.

PHASE 2 — interrupt driven, KLEN = 2, TILEBASE = 0, SCALE (3 >> 1), ReLU, IRQ_EN = 1
  `done` -> npu_irq -> interrupt_controller.irq_src_i[11] -> ext_irq -> CPU MEIP. Scored here:
    * irq_src_i of the interrupt controller equals EXACTLY `npu_irq << 11` on EVERY cycle of the
      run (bit 11, and no other bit, is the NPU source) and npu_irq rises with done set — a level
      source, not a pulse — after the start was committed, never before phase 2 was armed;
    * the CPU vectors (ISR_PC commits) with npu_irq AND ext_irq asserted — EXACTLY ONE trap, because
      the ISR drops the level source with a single IRQ_CLR[0] write;
    * after the ISR both lines deassert and stay low;
    * backdoor SRAM: ISR_COUNT == 1, the ISR saw STATUS.done and IRQ_STAT, the interrupt
      controller's PENDING_MASKED bit 11 was set, and the AOUT word read after the trap equals the
      model (the ISR itself does not pop AOUT).

PHASE 3 — illegal START (KLEN = 0), polled, IRQ_EN = 0
  The 2-cycle zero-length path: `done` sets with STATUS[6] cfg_rejected, nothing hangs, no AOUT
  word is pushed; the interrupt lines stay LOW while done is pending (the IE gate again).

GOLDEN-MODEL NOTE (same as test_soc_gpio / test_soc_trng / test_soc_i2c / test_soc_crypto): SoCModel
cannot be used here since it rejects 0x2000_xxxx MMIO. The firmware is self-checking against
hand-computed literals (pinned in npu_model's selftest), and this test independently recomputes the
expected values from tb/models/npu_model.py and compares what the firmware stored.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge
from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.npu_fw.npu_fw_addrs import (  # noqa: E402
    FAIL_PC,
    IRQ_READY_PC,
    ISR_PC,
    P1_DONE_PC,
    P1_START_PC,
    P2_ARMED_PC,
    P2_DONE_PC,
    P3_DONE_PC,
    P3_GATE_PC,
    PASS_PC,
    RES_BASE_WI,
    RES_ISR_COUNT,
    RES_ISR_IRQ_STAT,
    RES_ISR_IRQC_PEND,
    RES_ISR_STATUS,
    RES_P1_AOUT,
    RES_P1_IRQ_STAT,
    RES_P1_STATUS_ARMED,
    RES_P1_STATUS_CLR,
    RES_P1_STATUS_DONE,
    RES_P1_STATUS_POP,
    RES_P1_TILEBASE_RB,
    RES_P2_AOUT,
    RES_P2_AOUT_EMPTY,
    RES_P2_CTRL_RB,
    RES_P2_SCALE_RB,
    RES_P2_STATUS_ARMED,
    RES_P2_STATUS_POP,
    RES_P2_STATUS_PRE,
    RES_P3_AOUT_EMPTY,
    RES_P3_IRQ_STAT,
    RES_P3_STATUS_CLR,
    RES_P3_STATUS_DONE,
    RES_RESERVED_READ,
    RES_STATUS_RESET,
    RES_WADDR_RB,
    RES_WDATA_READ,
)
from tb.models import npu_model  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_HEX = str(Path(__file__).parent / "npu_fw" / "npu_fw.hex")

# Measured PASS_PC at cycle 32,891 (the NPU runs themselves are a few tens of clk each; the cost
# is the ~60 fabric MMIO accesses, the 600-iteration settle and the 2000-iteration D-cache-flush
# delay loop, each iteration 13-24 clk). Set to ~2x the measured run: a firmware that hangs in a
# bounded poll still ends in FAIL_PC well inside this budget.
NPU_TEST_TIMEOUT_CYCLES = 66_000

# Cycles after the ISR entry before checking that the IRQ lines have deasserted: the ISR issues
# three reads, an IRQ_CLR write, SRAM stores and a read-back before MRET; comfortably larger.
DEASSERT_CHECK_DELAY_CYCLES = 400

# Minimum number of cycles `done` must be pending with the IRQ armed-but-gated (per gated phase),
# for the "IE gate" observation to be non-vacuous.
MIN_GATED_PENDING_CYCLES = 50

# Independent stimulus, as int8 element lists (NOT the firmware's packed constants): the dense tile,
# the identity tile and a second copy of the dense tile, one row per weight word, lane j = column j.
DENSE = [[1, 2, 3, 4], [5, 6, 7, 8], [-1, -2, -3, -4], [10, 0, -10, 5]]
IDENT = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
WEIGHT_ROWS = DENSE + IDENT + DENSE


def _expected_mem() -> list:
    mem = npu_model.blank_weight_mem()
    for i, row in enumerate(WEIGHT_ROWS):
        mem[i] = npu_model.pack_word(row)
    return mem


MEM = _expected_mem()
P1_AIN = [npu_model.pack_word([1, 2, 3, 4])]
P2_AIN = [npu_model.pack_word([1, 2, 3, 4]), npu_model.pack_word([1, -2, 3, -4])]
P1_SCALE = npu_model.make_scale(5, 0)
P2_SCALE = npu_model.make_scale(3, 1)
P1_EXPECT = npu_model.infer(MEM, 8, P1_AIN, P1_SCALE, False)
P2_EXPECT = npu_model.infer(MEM, 0, P2_AIN, P2_SCALE, True)
# Pin the model's answer to hand-computed literals so a model regression cannot move the contract.
assert npu_model.unpack_word(P1_EXPECT) == (127, 40, -128, 127), "phase 1 literal vs model"
assert npu_model.unpack_word(P2_EXPECT) == (73, 9, 0, 36), "phase 2 literal vs model"

_MARKER_NAMES = {
    IRQ_READY_PC: "IRQ_READY",
    P1_START_PC: "P1_START",
    P1_DONE_PC: "P1_DONE",
    P2_ARMED_PC: "P2_ARMED",
    ISR_PC: "ISR",
    P2_DONE_PC: "P2_DONE",
    P3_GATE_PC: "P3_GATE",
    P3_DONE_PC: "P3_DONE",
    PASS_PC: "PASS",
}

# STATUS: [0] busy [1] done [2] ain_full [3] ain_empty [4] aout_valid [5] aout_full [6] cfg_rejected
ST_RESET = 0x08
ST_AIN_PUSHED_1 = 0x00
ST_DONE_AOUT = 0x1A
ST_DONE_POPPED = 0x0A
ST_AOUT_ONLY = 0x18
ST_ILLEGAL = 0x4A
IRQC_BIT_NPU = 0x800
NPU_IRQ_SHIFT = 11

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _read_hex(path: str) -> list:
    words: list = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, hex_path: str) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    words = _read_hex(hex_path)
    assert len(words) <= len(mem), (
        f"Firmware image {hex_path} ({len(words)} words) exceeds boot ROM capacity "
        f"({len(mem)} words) — regenerate with npu_fw/gen_npu_hex.py"
    )
    for i, word in enumerate(words):
        mem[i].value = word


async def _setup(dut, hex_path: str) -> None:
    """Start clocks, idle inputs, backdoor-load firmware, apply + release reset."""
    _kill_active_tasks()

    clk_task, cpu_clk_task = start_soc_clocks(dut, CLK_PERIOD_NS)
    _active_tasks.append(clk_task)
    _active_tasks.append(cpu_clk_task)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0
    dut.gpio_in_i.value = 0
    dut.i2c_scl_i.value = 1  # external pull-ups: a released bus reads high
    dut.i2c_sda_i.value = 1

    _load_rom(dut, hex_path)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


def _i(sig) -> int:
    return int(sig.value)


@cocotb.test()
async def test_soc_npu(dut):
    """Reach npu_top through the real fabric at 0x2001_0000: weights in, inference results read back
    over the bus, an illegal START that cannot hang, and the done IRQ taken through
    interrupt_controller[11] to the CPU."""
    await _setup(dut, _FW_HEX)

    seen = {
        "irq_ready": False,
        "p1_start": False,
        "p1_done": False,
        "p2_armed": False,
        "p2_done": False,
        "p3_gate": False,
        "p3_done": False,
    }
    phase = 0  # 0 = between phases, 1/2/3 = the phases above
    isr_entries: list = []  # (cycle, npu_irq, ext_irq) at each ISR_PC commit
    deassert_checked = False
    saw_pass = False
    prev_irq = 0
    irq_rise_cycle = None
    irq_rise_done = None
    gated_pending = {1: 0, 3: 0}  # done pending with the IRQ armed but gated off, per phase
    post_isr_irq_high = 0
    wiring_mismatch: list = []  # any cycle: irq_src_i != npu_irq << 11
    irq_cycles_total = 0

    last_pc = 0
    recent: list = []
    pass_cycle = None

    for cycle_idx in range(NPU_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        npu_irq = _i(dut.u_soc.npu_irq)
        ext_irq = _i(dut.u_soc.ext_irq)
        src_vec = _i(dut.u_soc.u_irq_ctrl.irq_src_i)
        done_q = _i(dut.u_soc.u_npu.g_on.done_q)

        # Boundary edge, independent of commit_pc_o.
        if npu_irq and not prev_irq and irq_rise_cycle is None:
            irq_rise_cycle = cycle_idx
            irq_rise_done = done_q
        prev_irq = npu_irq
        irq_cycles_total += npu_irq

        # The interrupt controller's source vector is EXACTLY the NPU line in bit 11, every cycle:
        # no other source is high, and the NPU is not wired to any other bit.
        if src_vec != (npu_irq << NPU_IRQ_SHIFT):
            wiring_mismatch.append((cycle_idx, npu_irq, src_vec))

        # Phases 1 and 3 (IRQ path armed, CTRL[3] == 0): nothing may fire, however pending `done`.
        if phase in (1, 3):
            assert npu_irq == 0, (
                f"npu_irq asserted at cycle {cycle_idx} in phase {phase} with CTRL[3] == 0 "
                f"(done_q={done_q}) — the IRQ-enable gate is broken"
            )
            assert (src_vec >> NPU_IRQ_SHIFT) & 1 == 0 and ext_irq == 0, (
                f"irq_src_i[11]/ext_irq asserted at cycle {cycle_idx} in phase {phase}"
            )
            if done_q:
                gated_pending[phase] += 1

        if phase == 2 and deassert_checked and (npu_irq or ext_irq):
            post_isr_irq_high += 1

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — an NPU SoC-level check failed "
                f"(reset value / WADDR / WDATA / STATUS / AOUT / interrupt-controller pending, "
                f"or a bounded poll / the IRQ wait timed out)"
            )

            if pc in _MARKER_NAMES:
                dut._log.info(f"marker {_MARKER_NAMES[pc]} committed at cycle {cycle_idx}")

            if pc == IRQ_READY_PC and not seen["irq_ready"]:
                seen["irq_ready"] = True
                phase = 1
            if pc == P1_START_PC and not seen["p1_start"]:
                seen["p1_start"] = True
            if pc == P1_DONE_PC and not seen["p1_done"]:
                seen["p1_done"] = True
            if pc == P2_ARMED_PC and not seen["p2_armed"]:
                seen["p2_armed"] = True
                phase = 2
                assert irq_rise_cycle is None, (
                    f"npu_irq rose at cycle {irq_rise_cycle}, before phase 2 was armed"
                )
            if pc == P2_DONE_PC and not seen["p2_done"]:
                seen["p2_done"] = True
                phase = 0
            if pc == P3_GATE_PC and not seen["p3_gate"]:
                seen["p3_gate"] = True
                phase = 3
            if pc == P3_DONE_PC and not seen["p3_done"]:
                seen["p3_done"] = True
                phase = 0

            if pc == ISR_PC:
                assert len(isr_entries) < 1, (
                    f"CPU took a SECOND trap (ISR_PC committed at cycle {cycle_idx}) — a stale "
                    f"level-held npu/ext IRQ re-vectored after MRET, or IRQ_CLR did not drop it"
                )
                isr_entries.append((cycle_idx, npu_irq, ext_irq))
                assert phase == 2, "CPU vectored to the ISR outside phase 2"
                assert npu_irq == 1, "trap: CPU vectored but u_soc.npu_irq is not asserted"
                assert ext_irq == 1, "trap: CPU vectored but u_soc.ext_irq is not asserted"

            if pc == PASS_PC:
                saw_pass = True
                pass_cycle = cycle_idx
                break

        if (
            isr_entries
            and not deassert_checked
            and cycle_idx >= isr_entries[0][0] + DEASSERT_CHECK_DELAY_CYCLES
        ):
            deassert_checked = True
            assert npu_irq == 0, (
                f"u_soc.npu_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the "
                f"ISR — the IRQ_CLR[0] write did not drop the level source"
            )
            assert ext_irq == 0, (
                f"u_soc.ext_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the ISR"
            )

    if not saw_pass:
        dut._log.info(
            "last_pc=0x%08x; recent committed PCs: %s",
            last_pc,
            " ".join(f"0x{p:08x}" for p in recent),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within {NPU_TEST_TIMEOUT_CYCLES} cycles"
    )
    dut._log.info(f"MEASURED: PASS_PC committed at cycle {pass_cycle}")
    for name, ok in seen.items():
        assert ok, f"marker {name} was never committed"
    assert len(isr_entries) == 1, f"expected exactly 1 trap, got {len(isr_entries)}"
    assert deassert_checked, "deassert window never reached"
    assert post_isr_irq_high == 0, (
        f"npu_irq/ext_irq re-asserted {post_isr_irq_high} cycle(s) after the ISR cleared done"
    )
    assert not wiring_mismatch, (
        f"interrupt_controller.irq_src_i != (npu_irq << 11): {wiring_mismatch[:5]}"
    )

    # ---- boundary: the done IRQ ------------------------------------------------------------
    assert irq_rise_cycle is not None, "npu_irq never rose in phase 2"
    assert irq_rise_done == 1, "npu_irq rose without the done flag set"
    assert irq_cycles_total > 0, "npu_irq was never high (the wiring check would be vacuous)"
    dut._log.info(
        f"timing: irq_rise={irq_rise_cycle} isr={isr_entries[0][0]} "
        f"irq_high_cycles={irq_cycles_total}; "
        f"gated_pending_cycles phase1={gated_pending[1]} phase3={gated_pending[3]}"
    )
    for ph in (1, 3):
        assert gated_pending[ph] >= MIN_GATED_PENDING_CYCLES, (
            f"only {gated_pending[ph]} phase-{ph} cycles had `done` pending with the IRQ armed — "
            f"the IE-gate observation is too thin to mean anything"
        )

    # ---- backdoor SRAM: firmware-visible values ---------------------------------------------
    sram = dut.u_soc.u_sram.mem

    def res(idx: int) -> int:
        return int(sram[RES_BASE_WI + idx].value)

    assert res(RES_ISR_COUNT) == 1, f"backdoor SRAM: ISR_COUNT = {res(RES_ISR_COUNT)}, expected 1"
    assert res(RES_ISR_STATUS) & 0x2, (
        f"ISR saw NPU_STATUS=0x{res(RES_ISR_STATUS):x}: done clear at the trap"
    )
    assert res(RES_ISR_IRQ_STAT) & 0x1, (
        f"ISR saw NPU_IRQ_STAT=0x{res(RES_ISR_IRQ_STAT):x}: done clear at the trap"
    )
    assert res(RES_ISR_IRQC_PEND) & IRQC_BIT_NPU, (
        f"interrupt controller PENDING_MASKED=0x{res(RES_ISR_IRQC_PEND):x}: bit 11 (NPU) was "
        f"never pending — irq_src_i[11] did not reach the controller"
    )

    exact = {
        "STATUS reset": (RES_STATUS_RESET, ST_RESET),
        "reserved word": (RES_RESERVED_READ, 0x0),
        "WADDR after 12 WDATA writes": (RES_WADDR_RB, len(WEIGHT_ROWS)),
        "WDATA read (write-only)": (RES_WDATA_READ, 0x0),
        "TILEBASE read-back": (RES_P1_TILEBASE_RB, 8),
        "P1 STATUS after AIN push": (RES_P1_STATUS_ARMED, ST_AIN_PUSHED_1),
        "P1 STATUS at done": (RES_P1_STATUS_DONE, ST_DONE_AOUT),
        "P1 IRQ_STAT": (RES_P1_IRQ_STAT, 0x1),
        "P1 STATUS after AOUT pop": (RES_P1_STATUS_POP, ST_DONE_POPPED),
        "P1 STATUS after IRQ_CLR": (RES_P1_STATUS_CLR, ST_RESET),
        "P2 SCALE read-back": (RES_P2_SCALE_RB, P2_SCALE),
        "P2 CTRL read-back (START not stored)": (RES_P2_CTRL_RB, 0x9),
        "P2 STATUS after 2 AIN pushes": (RES_P2_STATUS_ARMED, ST_AIN_PUSHED_1),
        "P2 STATUS after the ISR's IRQ_CLR": (RES_P2_STATUS_PRE, ST_AOUT_ONLY),
        "P2 STATUS after AOUT pop": (RES_P2_STATUS_POP, ST_RESET),
        "P2 AOUT read of an empty FIFO": (RES_P2_AOUT_EMPTY, 0x0),
        "P3 STATUS after illegal START": (RES_P3_STATUS_DONE, ST_ILLEGAL),
        "P3 IRQ_STAT": (RES_P3_IRQ_STAT, 0x1),
        "P3 AOUT (illegal START pushes nothing)": (RES_P3_AOUT_EMPTY, 0x0),
        "P3 STATUS after IRQ_CLR[1:0]": (RES_P3_STATUS_CLR, ST_RESET),
    }
    for what, (idx, want) in exact.items():
        got = res(idx)
        assert got == want, f"{what}: read 0x{got:x} over the bus, expected 0x{want:x}"

    # ---- scoreboard: stored AOUT words against the golden model ------------------------------
    got_p1 = res(RES_P1_AOUT)
    got_p2 = res(RES_P2_AOUT)
    assert got_p1 == P1_EXPECT, (
        f"phase 1 AOUT {npu_model.unpack_word(got_p1)} (0x{got_p1:08x}), model "
        f"{npu_model.unpack_word(P1_EXPECT)} (0x{P1_EXPECT:08x})"
    )
    assert got_p2 == P2_EXPECT, (
        f"phase 2 AOUT {npu_model.unpack_word(got_p2)} (0x{got_p2:08x}), model "
        f"{npu_model.unpack_word(P2_EXPECT)} (0x{P2_EXPECT:08x})"
    )
