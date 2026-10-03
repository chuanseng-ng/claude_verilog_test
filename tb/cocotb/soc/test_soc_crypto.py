"""
test_soc_crypto.py — Phase 6b-6 SoC-level CRYPTO FABRIC test (bead claude_verilog_test-f7vs.10,
docs/PHASE6_IP_EXPANSION_PLAN.md §9 step 6, L2 testability).

`test_crypto` (tb_crypto.sv / Makefile `crypto` target) owns every behaviour of crypto_accel —
FIPS-197 / FIPS-180-4 vectors, CTR, multi-block SHA, the sticky-IRQ and hang-free paths and the
fault-mutation campaign — driving the APB4 face directly. It has never exercised the peripheral
through the real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 12 (APB_CRYPTO, 0x2000_F000)

nor its IRQ into interrupt_controller bit 10. This suite proves exactly that and nothing more: it
re-proves NONE of the L1 behaviour (a handful of known-answer blocks is enough to show the data path
is intact end to end). Firmware comes from a committed pure-Python hand-assembler
(crypto_fw/gen_crypto_hex.py, sharing trng_fw's assembler) — no riscv32 cross toolchain, so the
suite is CI-safe. Synchronisation and scoring are by commit_pc_o marker PCs, the technique
test_soc_trng.py and test_soc_i2c.py use.

One test, one image, three phases (see the generator header for the firmware side).

PHASE 1 — polled ECB, FIPS-197 Appendix B, CTRL[3] (IRQ enable) = 0
  Firmware reads reset values through the fabric, writes IV0 and reads it back (the RW word that a
  mis-decoded slave index cannot return), loads key + block, starts, polls STATUS.done and compares
  DOUT0-3 with the FIPS ciphertext. Scored here:
    * the ciphertext, STATUS (key_valid -> done|key_valid -> key_valid after IRQ_CLR), IRQ_STAT, and
      the read-as-zero KEY / DIN windows, all as read by the CPU over the bus;
    * the IE gate: `done` is pending for a long stretch of phase 1 (done_q), and crypto_irq /
      interrupt_controller.irq_src_i / ext_irq stay LOW the whole time.

PHASE 2 — interrupt driven ECB, FIPS-197 Appendix C.1, CTRL[3] = 1
  A different key, rewritten over the fabric with key_valid already set, and a different block.
  `done` -> crypto_irq -> interrupt_controller.irq_src_i[10] -> ext_irq -> CPU MEIP. Scored here:
    * irq_src_i of the interrupt controller equals EXACTLY `crypto_irq << 10` on every phase-2 cycle
      (bit 10, and no other bit, is the crypto source) and crypto_irq rises with done_q set — a
      level source, not a pulse — after the start was committed, never before;
    * the CPU vectors (ISR_PC commits) with crypto_irq AND ext_irq asserted — EXACTLY ONE trap,
      because the ISR drops the level source with a single IRQ_CLR[0] write;
    * after the ISR both lines deassert and stay low (the 2-FF core_clk -> cpu_core_clk synchroniser
      has drained; allowed for by DEASSERT_CHECK_DELAY_CYCLES, nothing here expects a pulse);
    * backdoor SRAM: ISR_COUNT == 1, the ISR saw STATUS.done and IRQ_STAT, the interrupt
      controller's PENDING_MASKED bit 10 was set (the controller really received the source), and
      the App. C.1 ciphertext reads back through the fabric.

PHASE 3 — one SHA-256 block (FIPS 180-4 "abc"), polled, CTRL[3] = 0 again
  16 words through the DIN aperture (all four addresses), digest compared word by word, and the same
  interrupt-gate observation as phase 1 for the SHA path.

GOLDEN-MODEL NOTE (same as test_soc_gpio / test_soc_trng / test_soc_i2c): SoCModel cannot be used
here since it rejects 0x2000_xxxx MMIO. The firmware is self-checking against the standards'
literal vectors, and this test independently recomputes the expected values from tb/models/
aes128_model.py and hashlib and compares what the firmware stored.
"""

import hashlib
import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge
from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.crypto_fw.crypto_fw_addrs import (  # noqa: E402
    FAIL_PC,
    IRQ_READY_PC,
    ISR_PC,
    IV_PROBE,
    P1_DONE_PC,
    P1_START_PC,
    P2_ARMED_PC,
    P2_DONE_PC,
    P3_DONE_PC,
    P3_GATE_PC,
    PASS_PC,
    RES_BASE_WI,
    RES_CTRL_RESET,
    RES_DIN_READ,
    RES_ISR_COUNT,
    RES_ISR_IRQ_STAT,
    RES_ISR_IRQC_PEND,
    RES_ISR_STATUS,
    RES_IV_READBACK,
    RES_KEY_READ,
    RES_P1_DOUT0,
    RES_P1_IRQ_STAT,
    RES_P1_STATUS_ARMED,
    RES_P1_STATUS_CLR,
    RES_P1_STATUS_DONE,
    RES_P2_DOUT0,
    RES_P2_STATUS,
    RES_P3_DIGEST0,
    RES_P3_STATUS,
    RES_RESERVED_READ,
    RES_STATUS_RESET,
)
from tb.models import aes128_model  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_HEX = str(Path(__file__).parent / "crypto_fw" / "crypto_fw.hex")

# Three operations (11 clk AES, 66 clk SHA) are nothing next to the ~60 MMIO writes and the polling
# loops over the fabric, the 600-iteration settle and the 2000-iteration D-cache-flush delay loop
# (each iteration costs 13-24 clk: measured PASS at ~59.9k cycles). Generous headroom on purpose: a
# firmware that hangs in a bounded poll still ends in FAIL_PC well inside this budget.
CRYPTO_TEST_TIMEOUT_CYCLES = 120_000

# Cycles after the ISR entry before checking that the IRQ lines have deasserted: the ISR issues
# three reads, an IRQ_CLR write, SRAM stores and a read-back before MRET; comfortably larger.
DEASSERT_CHECK_DELAY_CYCLES = 400

# Minimum number of cycles `done` must be pending with the IRQ armed-but-gated (per gated phase),
# for the "IE gate" observation to be non-vacuous.
MIN_GATED_PENDING_CYCLES = 50

# Independent golden values: FIPS literal text, cross-checked against the AES model and hashlib.
KEY_B = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
PT_B = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
CT_B = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")
KEY_C1 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
PT_C1 = bytes.fromhex("00112233445566778899aabbccddeeff")
CT_C1 = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
assert aes128_model.encrypt_block(KEY_B, PT_B) == CT_B, "FIPS-197 App. B literal vs model"
assert aes128_model.encrypt_block(KEY_C1, PT_C1) == CT_C1, "FIPS-197 App. C.1 literal vs model"
DIGEST_ABC = hashlib.sha256(b"abc").digest()

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

ST_KEYV = 0x4
ST_DONE_KEYV = 0x6
IRQC_BIT_CRYPTO = 0x400

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
        f"({len(mem)} words) — regenerate with crypto_fw/gen_crypto_hex.py"
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


def _words(b: bytes) -> list:
    return [int.from_bytes(b[i : i + 4], "big") for i in range(0, len(b), 4)]


@cocotb.test()
async def test_soc_crypto(dut):
    """Reach crypto_accel through the real fabric at 0x2000_F000: ECB and SHA-256 known answers
    read back over the bus, and the done IRQ taken through interrupt_controller[10] to the CPU."""
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
    isr_entries: list = []  # (cycle, crypto_irq, ext_irq) at each ISR_PC commit
    deassert_checked = False
    saw_pass = False
    prev_irq = 0
    irq_rise_cycle = None
    irq_rise_done = None
    gated_pending = {1: 0, 3: 0}  # done pending with the IRQ armed but gated off, per phase
    post_isr_irq_high = 0
    wiring_mismatch: list = []  # phase 2: irq_src_i != crypto_irq << 10

    last_pc = 0
    recent: list = []

    for cycle_idx in range(CRYPTO_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        crypto_irq = _i(dut.u_soc.crypto_irq)
        ext_irq = _i(dut.u_soc.ext_irq)
        src_vec = _i(dut.u_soc.u_irq_ctrl.irq_src_i)
        done_q = _i(dut.u_soc.u_crypto.done_q)

        # Boundary edge, independent of commit_pc_o.
        if crypto_irq and not prev_irq and irq_rise_cycle is None:
            irq_rise_cycle = cycle_idx
            irq_rise_done = done_q
        prev_irq = crypto_irq

        # Phases 1 and 3 (IRQ path armed, CTRL[3] == 0): nothing may fire, however pending `done`.
        if phase in (1, 3):
            assert crypto_irq == 0, (
                f"crypto_irq asserted at cycle {cycle_idx} in phase {phase} with CTRL[3] == 0 "
                f"(done_q={done_q}) — the IRQ-enable gate is broken"
            )
            assert (src_vec >> 10) & 1 == 0 and ext_irq == 0, (
                f"irq_src_i[10]/ext_irq asserted at cycle {cycle_idx} in phase {phase}"
            )
            if done_q:
                gated_pending[phase] += 1

        if phase == 2:
            if src_vec != (crypto_irq << 10):
                wiring_mismatch.append((cycle_idx, crypto_irq, src_vec))
            if deassert_checked and (crypto_irq or ext_irq):
                post_isr_irq_high += 1

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — a CRYPTO SoC-level check failed "
                f"(reset value / IV or key/DIN window read / STATUS / ciphertext / digest / "
                f"interrupt-controller pending, or a bounded poll timed out)"
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
                    f"crypto_irq rose at cycle {irq_rise_cycle}, before phase 2 was armed"
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
                    f"level-held crypto/ext IRQ re-vectored after MRET, or IRQ_CLR did not drop it"
                )
                isr_entries.append((cycle_idx, crypto_irq, ext_irq))
                assert phase == 2, "CPU vectored to the ISR outside phase 2"
                assert crypto_irq == 1, "trap: CPU vectored but u_soc.crypto_irq is not asserted"
                assert ext_irq == 1, "trap: CPU vectored but u_soc.ext_irq is not asserted"

            if pc == PASS_PC:
                saw_pass = True
                break

        if (
            isr_entries
            and not deassert_checked
            and cycle_idx >= isr_entries[0][0] + DEASSERT_CHECK_DELAY_CYCLES
        ):
            deassert_checked = True
            assert crypto_irq == 0, (
                f"u_soc.crypto_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the "
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
        f"PASS_PC (0x{PASS_PC:08x}) never committed within {CRYPTO_TEST_TIMEOUT_CYCLES} cycles"
    )
    for name, ok in seen.items():
        assert ok, f"marker {name} was never committed"
    assert len(isr_entries) == 1, f"expected exactly 1 trap, got {len(isr_entries)}"
    assert deassert_checked, "deassert window never reached"
    assert post_isr_irq_high == 0, (
        f"crypto_irq/ext_irq re-asserted {post_isr_irq_high} cycle(s) after the ISR cleared done"
    )
    assert not wiring_mismatch, (
        f"interrupt_controller.irq_src_i != (crypto_irq << 10) in phase 2: {wiring_mismatch[:5]}"
    )

    # ---- boundary: the done IRQ ------------------------------------------------------------
    assert irq_rise_cycle is not None, "crypto_irq never rose in phase 2"
    assert irq_rise_done == 1, "crypto_irq rose without the done flag set"
    dut._log.info(
        f"timing: irq_rise={irq_rise_cycle} isr={isr_entries[0][0]}; "
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

    def res_words(idx: int, n: int) -> list:
        return [res(idx + k) for k in range(n)]

    assert res(RES_ISR_COUNT) == 1, f"backdoor SRAM: ISR_COUNT = {res(RES_ISR_COUNT)}, expected 1"
    assert res(RES_ISR_STATUS) & 0x2, (
        f"ISR saw CRYPTO_STATUS=0x{res(RES_ISR_STATUS):x}: done clear at the trap"
    )
    assert res(RES_ISR_IRQ_STAT) & 0x1, (
        f"ISR saw CRYPTO_IRQ_STAT=0x{res(RES_ISR_IRQ_STAT):x}: done clear at the trap"
    )
    assert res(RES_ISR_IRQC_PEND) & IRQC_BIT_CRYPTO, (
        f"interrupt controller PENDING_MASKED=0x{res(RES_ISR_IRQC_PEND):x}: bit 10 (CRYPTO) was "
        f"never pending — irq_src_i[10] did not reach the controller"
    )

    assert res(RES_CTRL_RESET) == 0x0, f"CTRL reset read 0x{res(RES_CTRL_RESET):x}"
    assert res(RES_STATUS_RESET) == 0x0, f"STATUS reset read 0x{res(RES_STATUS_RESET):x}"
    assert res(RES_RESERVED_READ) == 0x0, f"reserved word read 0x{res(RES_RESERVED_READ):x}"
    assert res(RES_IV_READBACK) == IV_PROBE, (
        f"IV0 read-back 0x{res(RES_IV_READBACK):08x}, expected 0x{IV_PROBE:08x}"
    )
    assert res(RES_KEY_READ) == 0x0, f"KEY0 read 0x{res(RES_KEY_READ):x} — must read 0"
    assert res(RES_DIN_READ) == 0x0, f"DIN0 read 0x{res(RES_DIN_READ):x} — must read 0"

    assert res(RES_P1_STATUS_ARMED) == ST_KEYV, (
        f"STATUS after key+block load 0x{res(RES_P1_STATUS_ARMED):x}, expected 0x{ST_KEYV:x}"
    )
    assert res(RES_P1_STATUS_DONE) == ST_DONE_KEYV, (
        f"STATUS after ECB done 0x{res(RES_P1_STATUS_DONE):x}, expected 0x{ST_DONE_KEYV:x}"
    )
    assert res(RES_P1_IRQ_STAT) == 0x1, f"IRQ_STAT after ECB done 0x{res(RES_P1_IRQ_STAT):x}"
    assert res(RES_P1_STATUS_CLR) == ST_KEYV, (
        f"STATUS after IRQ_CLR 0x{res(RES_P1_STATUS_CLR):x}, expected 0x{ST_KEYV:x}"
    )
    assert res(RES_P2_STATUS) == ST_KEYV, (
        f"STATUS after the ISR's IRQ_CLR 0x{res(RES_P2_STATUS):x}, expected 0x{ST_KEYV:x}"
    )
    assert res(RES_P3_STATUS) == ST_DONE_KEYV, (
        f"STATUS after SHA done 0x{res(RES_P3_STATUS):x}, expected 0x{ST_DONE_KEYV:x}"
    )

    got_b = res_words(RES_P1_DOUT0, 4)
    got_c1 = res_words(RES_P2_DOUT0, 4)
    got_sha = res_words(RES_P3_DIGEST0, 8)
    assert got_b == _words(CT_B), (
        f"FIPS-197 App. B ciphertext read over the bus: {[hex(w) for w in got_b]}, expected "
        f"{[hex(w) for w in _words(CT_B)]}"
    )
    assert got_c1 == _words(CT_C1), (
        f"FIPS-197 App. C.1 ciphertext read over the bus: {[hex(w) for w in got_c1]}, expected "
        f"{[hex(w) for w in _words(CT_C1)]}"
    )
    assert got_sha == _words(DIGEST_ABC), (
        f"SHA-256('abc') read over the bus: {[hex(w) for w in got_sha]}, expected "
        f"{[hex(w) for w in _words(DIGEST_ABC)]}"
    )
