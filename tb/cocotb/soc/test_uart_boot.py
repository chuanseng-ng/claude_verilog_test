"""
test_uart_boot.py -- SoC-level test of the UART boot-ROM bootloader (bead hlrm.2).

The real bootloader image (sw/bootloader/prebuilt/*.hex, built from uart_boot.c) is
backdoor-loaded into tb_soc_top.u_soc.u_boot_rom.mem, the SoC is reset, and a bit-level UART
model drives `uart_rx_i` with framed protocol traffic (tools/fw/uart_load.py is the single
source of the framing/CRC).  A second bit-level model decodes `uart_tx_o`.  What is checked:

  * banner + INFO handshake, at the shipped default divisor (50 MHz / 115200 -> D=26) and at
    the shortened simulation divisor;
  * a multi-packet load of a real RV32I program (testprog.c) into SRAM, target-side CRC verify,
    JUMP, and that the program then *runs* (UART signature + commit-PC trace in SRAM).  The
    loaded code sits in the write-back D$ until the bootloader's CSRW dcache_flush, and the
    I$ only sees it after FENCE.I, so a program that runs at all proves the cache hand-off;
  * negative cases: bad CRC, bad address / command / length, misaligned entry, truncated
    frame (idle timeout) -- each must NAK, leave SRAM untouched and leave the bootloader usable;
  * the auto-boot fallback (jump to a pre-loaded image when no host shows up, and refuse to
    jump into empty SRAM).

The CPU, UART, crossbar, SRAM and boot ROM are the real RTL; nothing is mocked.
"""

import struct
import sys
import zlib
from pathlib import Path

import cocotb
from cocotb.clock import Clock  # noqa: F401  (start_soc_clocks owns the clocks; kept for parity)
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "tools" / "fw"))

import uart_load as ul  # noqa: E402
from soc_clocks import drive_soc_reset, start_soc_clocks  # noqa: E402
from sram_backdoor import sram_mem  # noqa: E402

CLK_PERIOD_NS = 2
SRAM_BASE = 0x0000_2000
LOAD_HI = 0x0000_2E00  # SRAM 4 KB, top 512 B are bootloader .bss/stack
PREBUILT = _ROOT / "sw" / "bootloader" / "prebuilt"

SIM_DIV = 5  # must match DEFS_sim in sw/bootloader/Makefile
DEFAULT_DIV = 26  # 50 MHz / 115200, bl_config.h default
IDLE_CYCLES_SIM = 20_000  # BL_IDLE_MS(20) * BL_CPU_HZ(1 MHz)/1000

TESTPROG = (PREBUILT / "testprog.bin").read_bytes()
TABLE_SUM = 0x106B0960  # sum32 of testprog_table.inc, re-derived in test_table_sum_is_independent

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _bit_cycles(div: int) -> int:
    return 16 * (div + 1)


def _hex_words(path: Path) -> list[int]:
    words = []
    for line in path.read_text().splitlines():
        tok = line.strip()
        if tok and not tok.startswith(("//", "@")):
            words.append(int(tok, 16))
    return words


class Env:
    """Per-test handles: UART TX decoder, commit-PC trace, helpers."""

    def __init__(self, dut, div: int):
        self.dut = dut
        self.div = div
        self.bit = _bit_cycles(div)
        self.rx = bytearray()  # bytes the DUT transmitted (decoded from uart_tx_o)
        self.pcs: list[int] = []

    async def monitor_tx(self):
        d = self.dut
        while True:
            await FallingEdge(d.uart_tx_o)
            await ClockCycles(d.clk_i, self.bit + self.bit // 2)  # middle of data bit 0
            v = 0
            for i in range(8):
                v |= int(d.uart_tx_o.value) << i
                await ClockCycles(d.clk_i, self.bit)
            self.rx.append(v)  # now in the middle of the stop bit

    async def monitor_commits(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk_i)
            if int(d.commit_valid_o.value):
                pc = int(d.commit_pc_o.value)
                if not self.pcs or self.pcs[-1] != pc:
                    self.pcs.append(pc)

    async def send(self, data: bytes, gap_bits: int = 1):
        """Drive uart_rx_i: 8N1, LSB first, `1 + gap_bits` stop bits (default: 8N2).

        8N2 is deliberate and matches what tools/fw/uart_load.py configures: the
        uart_controller receiver returns to idle only at the END of the stop bit and re-arms on
        the next oversample tick, so it falls one oversample tick further behind on every
        back-to-back 8N1 byte and mis-frames after roughly 7 bytes (measured here: an 8-byte frame
        at gap 0 fails, the same frame with one extra stop bit passes). See README "UART RX note".
        """
        d = self.dut
        for byte in data:
            for bit in [0] + [(byte >> i) & 1 for i in range(8)] + [1]:
                d.uart_rx_i.value = bit
                await ClockCycles(d.clk_i, self.bit)
            if gap_bits:
                await ClockCycles(d.clk_i, gap_bits * self.bit)
        d.uart_rx_i.value = 1

    async def wait_rx(self, n: int, max_cycles: int, start: int = 0):
        """Wait until at least `n` bytes have been decoded after index `start`."""
        waited = 0
        while len(self.rx) - start < n:
            await ClockCycles(self.dut.clk_i, 256)
            waited += 256
            assert waited <= max_cycles, (
                f"timeout waiting for {n} UART bytes (got {bytes(self.rx[start:])!r})"
            )
        return bytes(self.rx[start : start + n])

    async def transact(self, frame: bytes, max_cycles: int = 400_000) -> ul.Response:
        """Send a frame, read the ACK/NAK response from the DUT."""
        mark = len(self.rx)
        await self.send(frame)
        head = await self.wait_rx(2, max_cycles, mark)
        if head[0] == ul.ACK and head[1]:
            body = await self.wait_rx(2 + head[1], max_cycles, mark)
            return ul.Response(True, payload=body[2:])
        return ul.Response(head[0] == ul.ACK, error=head[1] if head[0] == ul.NAK else 0)

    async def cmd(self, cmd: int, payload: bytes = b"") -> ul.Response:
        return await self.transact(ul.build_frame(cmd, payload))

    async def write(self, addr: int, data: bytes) -> ul.Response:
        return await self.cmd(ul.CMD_WRITE, struct.pack("<I", addr) + data)

    async def run_until(self, pred, max_cycles: int):
        waited = 0
        while not pred():
            await ClockCycles(self.dut.clk_i, 256)
            waited += 256
            assert waited <= max_cycles, "timeout in run_until"


def sram_bytes(dut, addr: int, n: int) -> bytes:
    mem = sram_mem(dut)
    out = bytearray()
    for a in range(addr, addr + n):
        word = int(mem[(a - SRAM_BASE) // 4].value)
        out.append((word >> (8 * (a & 3))) & 0xFF)
    return bytes(out)


async def setup(dut, hexname: str, div: int = SIM_DIV, sram_image: bytes = b"") -> Env:
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

    words = _hex_words(PREBUILT / hexname)
    rom = dut.u_soc.u_boot_rom.mem
    assert len(words) <= len(rom), "bootloader image exceeds the 4 KB boot ROM"
    for i, w in enumerate(words):
        rom[i].value = w
    for i in range(len(words), len(rom)):
        rom[i].value = 0  # SRAM/ROM arrays persist across tests in one simulation
    mem = sram_mem(dut)
    padded = sram_image + bytes(-len(sram_image) % 4)
    for i in range(len(mem)):
        chunk = padded[4 * i : 4 * i + 4]
        mem[i].value = int.from_bytes(chunk, "little") if chunk else 0

    env = Env(dut, div)
    _active_tasks.append(cocotb.start_soon(env.monitor_tx()))
    _active_tasks.append(cocotb.start_soon(env.monitor_commits()))
    for _ in range(5):
        await RisingEdge(dut.clk_i)
    drive_soc_reset(dut, False)
    return env


def good_info_payload(max_data: int = 128) -> bytes:
    return struct.pack("<BHII", 1, max_data, SRAM_BASE, LOAD_HI)


async def load_testprog(env: Env) -> None:
    for off in range(0, len(TESTPROG), 128):
        piece = TESTPROG[off : off + 128]
        resp = await env.write(SRAM_BASE + off, piece)
        assert resp.ok, f"WRITE at +0x{off:x} refused: err {resp.error}"


# ---------------------------------------------------------------------------------------------
@cocotb.test()
async def test_table_sum_is_independent(dut):
    """The expected payload signature is derived here from the table file, not copied from C."""
    inc = (_ROOT / "sw" / "bootloader" / "testprog_table.inc").read_text()
    vals = [int(tok.rstrip("u,"), 16) for tok in inc.split() if tok.startswith("0x")]
    assert len(vals) == 32
    assert sum(vals) & 0xFFFFFFFF == TABLE_SUM


@cocotb.test()
async def test_banner_and_info_sim_divisor(dut):
    env = await setup(dut, "uart_boot_sim.hex")
    banner = await env.wait_rx(len(ul.BANNER), 60_000)
    assert banner == ul.BANNER
    resp = await env.cmd(ul.CMD_INFO)
    assert resp.ok and resp.payload == good_info_payload()


@cocotb.test()
async def test_banner_and_info_default_115200_at_50mhz(dut):
    """The image intended for MEM_INIT_FILE: D=26 -> 432 clocks/bit (115741 baud at 50 MHz)."""
    env = await setup(dut, "uart_boot_default.hex", div=DEFAULT_DIV)
    banner = await env.wait_rx(len(ul.BANNER), 400_000)
    assert banner == ul.BANNER
    resp = await env.transact(ul.build_frame(ul.CMD_INFO), max_cycles=600_000)
    assert resp.ok and resp.payload == good_info_payload()


@cocotb.test()
async def test_load_verify_jump_and_run(dut):
    env = await setup(dut, "uart_boot_sim.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)
    assert TESTPROG and len(TESTPROG) > 2 * 128  # needs several packets, not one

    await load_testprog(env)

    resp = await env.cmd(ul.CMD_CRC, struct.pack("<II", SRAM_BASE, len(TESTPROG)))
    assert resp.ok and struct.unpack("<I", resp.payload)[0] == zlib.crc32(TESTPROG)

    mark = len(env.rx)
    resp = await env.cmd(ul.CMD_JUMP, struct.pack("<I", SRAM_BASE))
    assert resp.ok

    expected = b"PAYLOAD OK %08X\n" % TABLE_SUM
    got = await env.wait_rx(len(expected), 200_000, mark + 2)
    assert got == expected, got
    # The image bytes really reached SRAM (D$ flushed) and the CPU executed from SRAM.
    assert sram_bytes(dut, SRAM_BASE, len(TESTPROG)) == TESTPROG
    assert SRAM_BASE in env.pcs, "CPU never committed the payload entry PC"
    first_sram = next(i for i, pc in enumerate(env.pcs) if SRAM_BASE <= pc < LOAD_HI)
    assert all(0x1000 <= pc < 0x2000 for pc in env.pcs[:first_sram]), "ran from an unexpected PC"
    assert env.pcs[first_sram] == SRAM_BASE


@cocotb.test()
async def test_bad_crc_is_nakked_and_memory_untouched(dut):
    env = await setup(dut, "uart_boot_sim.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)
    data = bytes(range(1, 33))
    frame = bytearray(ul.build_frame(ul.CMD_WRITE, struct.pack("<I", SRAM_BASE) + data))
    frame[-2] ^= 0x10
    resp = await env.transact(bytes(frame))
    assert (resp.ok, resp.error) == (False, ul.ERR_CRC)
    assert sram_bytes(dut, SRAM_BASE, 32) == bytes(32), "NAKed frame must not touch SRAM"

    # Corruption in the payload rather than in the CRC field is caught the same way.
    frame = bytearray(ul.build_frame(ul.CMD_WRITE, struct.pack("<I", SRAM_BASE) + data))
    frame[10] ^= 0x01
    resp = await env.transact(bytes(frame))
    assert (resp.ok, resp.error) == (False, ul.ERR_CRC)
    assert sram_bytes(dut, SRAM_BASE, 32) == bytes(32)

    resp = await env.write(SRAM_BASE, data)  # same bytes, intact: accepted
    assert resp.ok
    # The accepted bytes sit in the write-back D$; the CRC command flushes them to SRAM.
    resp = await env.cmd(ul.CMD_CRC, struct.pack("<II", SRAM_BASE, len(data)))
    assert resp.ok and struct.unpack("<I", resp.payload)[0] == zlib.crc32(data)
    assert sram_bytes(dut, SRAM_BASE, 32) == data


@cocotb.test()
async def test_refusals_nak_with_the_right_code(dut):
    env = await setup(dut, "uart_boot_sim.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)

    async def expect_nak(resp_coro, code, what):
        r = await resp_coro
        assert (r.ok, r.error) == (False, code), f"{what}: {r}"

    await expect_nak(env.write(0x1000, b"\x00"), ul.ERR_ADDR, "write into boot ROM")
    await expect_nak(env.write(LOAD_HI, b"\x00"), ul.ERR_ADDR, "write over bootloader RAM")
    await expect_nak(env.write(LOAD_HI - 4, bytes(8)), ul.ERR_ADDR, "write straddling the limit")
    await expect_nak(env.write(0x2000_2000, b"\x00"), ul.ERR_ADDR, "write into MMIO")
    await expect_nak(env.write(0xFFFF_FFFE, bytes(4)), ul.ERR_ADDR, "address wrap-around")
    await expect_nak(env.cmd(0x7F), ul.ERR_CMD, "unknown command")
    await expect_nak(env.cmd(ul.CMD_INFO, b"\x00"), ul.ERR_LEN, "INFO with payload")
    await expect_nak(env.cmd(ul.CMD_WRITE, b"\x00\x20\x00\x00"), ul.ERR_LEN, "WRITE without data")
    await expect_nak(env.cmd(ul.CMD_JUMP, b"\x00\x20"), ul.ERR_LEN, "short JUMP")
    await expect_nak(
        env.cmd(ul.CMD_JUMP, struct.pack("<I", SRAM_BASE + 2)), ul.ERR_ADDR, "misaligned JUMP"
    )
    await expect_nak(
        env.cmd(ul.CMD_JUMP, struct.pack("<I", 0x1000)), ul.ERR_ADDR, "JUMP back into the ROM"
    )
    await expect_nak(
        env.cmd(ul.CMD_CRC, struct.pack("<II", SRAM_BASE, 0x10000)), ul.ERR_ADDR, "CRC too long"
    )
    assert sram_bytes(dut, SRAM_BASE, 64) == bytes(64)
    resp = await env.cmd(ul.CMD_INFO)  # still alive after all that
    assert resp.ok and resp.payload == good_info_payload()


@cocotb.test()
async def test_oversized_length_nak_then_resync(dut):
    """A length beyond the receive buffer is refused up front; the host resyncs by staying
    silent for longer than the target's idle timeout and then re-sends."""
    env = await setup(dut, "uart_boot_sim.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)
    bogus = bytes([ul.SOF, ul.CMD_WRITE]) + struct.pack("<H", 4000)
    resp = await env.transact(bogus)
    assert (resp.ok, resp.error) == (False, ul.ERR_LEN)
    await ClockCycles(dut.clk_i, IDLE_CYCLES_SIM + 5_000)
    resp = await env.cmd(ul.CMD_INFO)
    assert resp.ok


@cocotb.test()
async def test_truncated_frame_times_out_and_recovers(dut):
    env = await setup(dut, "uart_boot_sim.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)
    frame = ul.build_frame(ul.CMD_WRITE, struct.pack("<I", SRAM_BASE) + bytes(40))
    mark = len(env.rx)
    await env.send(frame[: len(frame) // 2])  # sender dies mid-frame
    got = await env.wait_rx(2, IDLE_CYCLES_SIM * 3, mark)
    assert got == bytes([ul.NAK, ul.ERR_TIMEOUT])
    assert sram_bytes(dut, SRAM_BASE, 44) == bytes(44)
    resp = await env.cmd(ul.CMD_INFO)
    assert resp.ok


@cocotb.test()
async def test_line_noise_before_sof_is_ignored(dut):
    env = await setup(dut, "uart_boot_sim.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)
    mark = len(env.rx)
    await env.send(b"\x00\xff\x55\x13\x37")
    resp = await env.cmd(ul.CMD_INFO)
    assert resp.ok
    assert len(env.rx) - mark == 2 + 11, "noise must not provoke any reply"


@cocotb.test()
async def test_autoboot_runs_preloaded_image(dut):
    """No host: after the auto-boot window the bootloader jumps to the image at 0x2000."""
    env = await setup(dut, "uart_boot_sim_auto.hex", sram_image=TESTPROG)
    expected = ul.BANNER + b"PAYLOAD OK %08X\n" % TABLE_SUM
    got = await env.wait_rx(len(expected), 300_000)
    assert got == expected, got
    assert SRAM_BASE in env.pcs


@cocotb.test()
async def test_autoboot_refuses_empty_sram_and_stays_serviceable(dut):
    env = await setup(dut, "uart_boot_sim_auto.hex")
    await env.wait_rx(len(ul.BANNER), 60_000)
    await ClockCycles(dut.clk_i, 30_000)  # well past the 5 ms (= 5000 cycle) window
    assert bytes(env.rx) == ul.BANNER
    assert not any(SRAM_BASE <= pc < LOAD_HI for pc in env.pcs), "jumped into empty SRAM"
    resp = await env.cmd(ul.CMD_INFO)
    assert resp.ok

