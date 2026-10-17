"""Unit tests for the UART bootloader host tool (tools/fw/uart_load.py, bead hlrm.2).

No serial port and no RISC-V toolchain needed: the target is a small Python model of the
bootloader's frame handling.  The RTL-level behaviour of the real ROM image is covered by
tb/cocotb/soc/test_uart_boot.py; here we pin the framing, the CRC convention (including the
fixed residue the C code compares against) and the protocol constants shared with
sw/bootloader/uart_boot_proto.h.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name

import re
import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "fw"))

import uart_load as ul  # noqa: E402

PROTO_H = ROOT / "sw" / "bootloader" / "uart_boot_proto.h"
BOOT_C = ROOT / "sw" / "bootloader" / "uart_boot.c"
PREBUILT_ELF = ROOT / "sw" / "bootloader" / "prebuilt" / "testprog.elf"


def target_crc_register(data: bytes) -> int:
    """The bootloader's CRC loop (uart_boot.c crc32_byte), raw register, init 0xFFFFFFFF."""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & (0 - (crc & 1)))
    return crc


# ---- protocol constants stay in sync with the C header -----------------------------------


def _header_defines() -> dict[str, int]:
    out = {}
    for m in re.finditer(r"#define\s+(BL_\w+)\s+(0x[0-9A-Fa-f]+|\d+)\b", PROTO_H.read_text()):
        out[m.group(1)] = int(m.group(2), 0)
    return out


@pytest.mark.parametrize(
    ("c_name", "py_name"),
    [
        ("BL_PROTO_VERSION", "PROTO_VERSION"),
        ("BL_SOF", "SOF"),
        ("BL_ACK", "ACK"),
        ("BL_NAK", "NAK"),
        ("BL_CMD_INFO", "CMD_INFO"),
        ("BL_CMD_WRITE", "CMD_WRITE"),
        ("BL_CMD_CRC", "CMD_CRC"),
        ("BL_CMD_JUMP", "CMD_JUMP"),
        ("BL_ERR_CRC", "ERR_CRC"),
        ("BL_ERR_CMD", "ERR_CMD"),
        ("BL_ERR_LEN", "ERR_LEN"),
        ("BL_ERR_ADDR", "ERR_ADDR"),
        ("BL_ERR_TIMEOUT", "ERR_TIMEOUT"),
    ],
)
def test_constants_match_c_header(c_name, py_name):
    assert _header_defines()[c_name] == getattr(ul, py_name)


def test_banner_matches_c_header():
    m = re.search(r'#define\s+BL_BANNER\s+"((?:[^"\\]|\\.)*)"', PROTO_H.read_text())
    assert m is not None
    assert m.group(1).encode().decode("unicode_escape").encode() == ul.BANNER


# ---- CRC and framing ----------------------------------------------------------------------


def test_crc32_check_value():
    assert ul.crc32(b"123456789") == 0xCBF43926


def test_crc32_is_zlib():
    data = bytes(range(256)) * 3
    assert ul.crc32(data) == zlib.crc32(data)


def test_frame_layout():
    f = ul.build_frame(ul.CMD_WRITE, b"\x00\x20\x00\x00\xaa\xbb")
    assert f[0] == ul.SOF
    assert f[1] == ul.CMD_WRITE
    assert f[2:4] == b"\x06\x00"  # little-endian payload length
    assert f[4:10] == b"\x00\x20\x00\x00\xaa\xbb"
    assert struct.unpack("<I", f[10:])[0] == zlib.crc32(f[1:10])
    assert len(f) == 1 + 3 + 6 + 4


def test_empty_payload_frame():
    f = ul.build_frame(ul.CMD_INFO)
    assert len(f) == 8
    assert f[2:4] == b"\x00\x00"


def test_payload_too_long_rejected():
    with pytest.raises(ValueError):
        ul.build_frame(ul.CMD_WRITE, bytes(0x10000))


@pytest.mark.parametrize("payload", [b"", b"\x01", bytes(range(132)), b"\xff" * 64])
def test_good_frame_leaves_fixed_crc_residue(payload):
    """uart_boot.c folds the received CRC bytes into the register and compares to this."""
    f = ul.build_frame(ul.CMD_WRITE, payload)
    assert target_crc_register(f[1:]) == 0xDEBB20E3
    assert "0xDEBB20E3u" in BOOT_C.read_text()


def test_any_single_bit_flip_breaks_the_residue():
    f = bytearray(ul.build_frame(ul.CMD_WRITE, bytes(range(40))))
    for byte in range(1, len(f)):  # SOF itself is not covered by the CRC
        for bit in range(8):
            f[byte] ^= 1 << bit
            assert target_crc_register(bytes(f[1:])) != 0xDEBB20E3
            f[byte] ^= 1 << bit


# ---- a Python model of the target, to drive the host logic ---------------------------------


class FakeTarget:
    """Frame-level model of uart_boot.c (same checks, same replies), as a ``Link``."""

    LOAD_LO, LOAD_HI, MAX_DATA = 0x2000, 0x2E00, 128

    def __init__(self):
        self.mem = {}
        self.rx = bytearray()  # bytes the host will read
        self.jumped = None
        self.corrupt_next = 0  # number of upcoming frames to damage in flight
        self.drop_next = 0  # number of upcoming frames to swallow (no reply)
        self.frames_seen = 0
        self.resets = 0

    def _ok(self, addr, n):
        return self.LOAD_LO <= addr <= self.LOAD_HI and n <= self.LOAD_HI - addr

    def write(self, data):
        frame = bytes(data)
        self.frames_seen += 1
        if self.drop_next:
            self.drop_next -= 1
            return
        if self.corrupt_next:
            self.corrupt_next -= 1
            frame = frame[:-1] + bytes([frame[-1] ^ 0x40])
        cmd, ln = frame[1], struct.unpack("<H", frame[2:4])[0]
        payload = frame[4 : 4 + ln]
        if target_crc_register(frame[1:]) != 0xDEBB20E3:
            self.rx += bytes([ul.NAK, ul.ERR_CRC])
        elif cmd == ul.CMD_INFO:
            self.rx += bytes([ul.ACK, 11, 1]) + struct.pack(
                "<HII", self.MAX_DATA, self.LOAD_LO, self.LOAD_HI
            )
        elif cmd == ul.CMD_WRITE:
            addr, blob = struct.unpack("<I", payload[:4])[0], payload[4:]
            if not self._ok(addr, len(blob)):
                self.rx += bytes([ul.NAK, ul.ERR_ADDR])
            else:
                for i, b in enumerate(blob):
                    self.mem[addr + i] = b
                self.rx += bytes([ul.ACK, 0])
        elif cmd == ul.CMD_CRC:
            addr, n = struct.unpack("<II", payload)
            if not self._ok(addr, n):
                self.rx += bytes([ul.NAK, ul.ERR_ADDR])
            else:
                blob = bytes(self.mem.get(addr + i, 0) for i in range(n))
                self.rx += bytes([ul.ACK, 4]) + struct.pack("<I", zlib.crc32(blob))
        elif cmd == ul.CMD_JUMP:
            (entry,) = struct.unpack("<I", payload)
            if entry & 3 or not self._ok(entry, 0) or entry == self.LOAD_HI:
                self.rx += bytes([ul.NAK, ul.ERR_ADDR])
            else:
                self.jumped = entry
                self.rx += bytes([ul.ACK, 0])
        else:
            self.rx += bytes([ul.NAK, ul.ERR_CMD])

    def read(self, size):
        out, self.rx = bytes(self.rx[:size]), self.rx[size:]
        return out

    def reset_input_buffer(self):
        self.rx.clear()
        self.resets += 1


def make_bl(target, **kw):
    return ul.Bootloader(target, sleep=lambda s: None, **kw)


def test_info_roundtrip():
    info = make_bl(FakeTarget()).info()
    assert info == ul.Info(1, 128, 0x2000, 0x2E00)


def test_load_image_chunks_writes_and_verifies():
    t = FakeTarget()
    image = bytes(i * 7 & 0xFF for i in range(300))
    ul.load_image(make_bl(t), [ul.Segment(0x2000, image)])
    assert bytes(t.mem[0x2000 + i] for i in range(300)) == image
    # INFO + ceil(300/128)=3 WRITEs + 1 CRC
    assert t.frames_seen == 1 + 3 + 1


def test_chunk_size_is_clamped_to_target_max():
    t = FakeTarget()
    ul.load_image(make_bl(t), [ul.Segment(0x2000, bytes(256))], chunk=4096, verify=False)
    assert t.frames_seen == 1 + 2


def test_unaligned_segment_and_multiple_segments():
    t = FakeTarget()
    segs = [ul.Segment(0x2003, b"abc"), ul.Segment(0x2100, bytes(range(200)))]
    ul.load_image(make_bl(t), segs)
    assert t.mem[0x2003] == ord("a")
    assert t.mem[0x2100 + 199] == 199


def test_corrupted_frame_is_retried_after_resync():
    t = FakeTarget()
    bl = make_bl(t)
    bl.info()
    t.corrupt_next = 1
    bl.write(0x2000, b"\x01\x02\x03\x04")
    assert t.mem[0x2000] == 1
    assert t.resets == 1  # one resync between the NAK and the resend


def test_silent_target_raises_after_retries():
    t = FakeTarget()
    t.drop_next = 99
    with pytest.raises(ul.BootloaderError, match="no response"):
        make_bl(t, retries=2).info()
    assert t.frames_seen == 3


def test_persistent_crc_error_raises():
    t = FakeTarget()
    t.corrupt_next = 99
    with pytest.raises(ul.BootloaderError, match="bad CRC"):
        make_bl(t, retries=1).write(0x2000, b"\x00")


def test_bad_address_is_a_hard_error_not_retried():
    t = FakeTarget()
    with pytest.raises(ul.BootloaderError, match="address"):
        make_bl(t).write(0x1000, b"\x00")  # the boot ROM itself
    assert t.frames_seen == 1


def test_write_over_bootloader_ram_refused():
    t = FakeTarget()
    with pytest.raises(ul.BootloaderError, match="address"):
        make_bl(t).write(0x2E00, b"\x00")


def test_check_fits_rejects_before_sending_anything():
    t = FakeTarget()
    with pytest.raises(ul.BootloaderError, match="outside the target load region"):
        ul.load_image(make_bl(t), [ul.Segment(0x2000, bytes(0xE01))])
    assert t.frames_seen == 1  # only the INFO query


def test_verify_detects_target_side_mismatch():
    t = FakeTarget()
    bl = make_bl(t)
    orig_write = t.write

    def flaky(data):
        orig_write(data)
        if data[1] == ul.CMD_WRITE:
            t.mem[0x2000] ^= 0xFF  # target memory corrupted after a good ACK

    t.write = flaky
    with pytest.raises(ul.BootloaderError, match="verify failed"):
        ul.load_image(bl, [ul.Segment(0x2000, bytes(range(16)))])


def test_jump_ok_and_misaligned_entry_refused():
    t = FakeTarget()
    bl = make_bl(t)
    bl.jump(0x2000)
    assert t.jumped == 0x2000
    with pytest.raises(ul.BootloaderError, match="address"):
        bl.jump(0x2002)


def test_unknown_command_refused():
    with pytest.raises(ul.BootloaderError, match="unknown command"):
        make_bl(FakeTarget()).transact(0x7F)


def test_protocol_version_mismatch_refused():
    t = FakeTarget()
    orig = t.write

    def v2(data):
        orig(data)
        if data[1] == ul.CMD_INFO:
            t.rx[2] = 2

    t.write = v2
    with pytest.raises(ul.BootloaderError, match="protocol v2"):
        ul.load_image(make_bl(t), [ul.Segment(0x2000, b"x")])


# ---- ELF / bin ----------------------------------------------------------------------------


def _make_elf(segments, entry):
    """Tiny ELF32-LE with one PT_LOAD per (paddr, data[, memsz])."""
    ehsize, phentsize = 52, 32
    phoff = ehsize
    data_off = phoff + phentsize * len(segments)
    hdr = bytearray(b"\x7fELF" + bytes([1, 1, 1]) + bytes(9))
    hdr += struct.pack(
        "<HHIIIIIHHHHHH", 2, 243, 1, entry, phoff, 0, 0, ehsize, phentsize, len(segments), 0, 0, 0
    )
    phs, body, off = bytearray(), bytearray(), data_off
    for seg in segments:
        paddr, blob = seg[0], seg[1]
        memsz = seg[2] if len(seg) > 2 else len(blob)
        phs += struct.pack("<8I", 1, off, paddr, paddr, len(blob), memsz, 7, 4)
        body += blob
        off += len(blob)
    return bytes(hdr + phs + body)


def test_load_elf_segments_and_entry():
    elf = _make_elf([(0x2000, b"\x11" * 8), (0x2100, b"\x22" * 4, 64)], entry=0x2004)
    segs, entry = ul.load_elf(elf)
    assert entry == 0x2004
    assert segs == [ul.Segment(0x2000, b"\x11" * 8), ul.Segment(0x2100, b"\x22" * 4)]


def test_elf_bss_only_segment_is_skipped():
    elf = _make_elf([(0x2000, b"\xaa" * 4), (0x2200, b"", 32)], entry=0x2000)
    segs, _ = ul.load_elf(elf)
    assert [s.addr for s in segs] == [0x2000]


def test_non_elf_rejected():
    with pytest.raises(ValueError):
        ul.load_elf(b"not an elf at all, just bytes")


@pytest.mark.skipif(not PREBUILT_ELF.exists(), reason="prebuilt testprog.elf not present")
def test_real_riscv_elf_parses():
    segs, entry = ul.load_elf(PREBUILT_ELF.read_bytes())
    assert entry == 0x2000
    assert segs[0].addr == 0x2000
    assert (
        sum(len(s.data) for s in segs)
        == (ROOT / "sw/bootloader/prebuilt/testprog.bin").stat().st_size
    )


def test_chunks_cover_segment_exactly():
    seg = ul.Segment(0x2000, bytes(range(250)))
    pieces = list(ul.chunks(seg, 128))
    assert [p.addr for p in pieces] == [0x2000, 0x2080]
    assert b"".join(p.data for p in pieces) == seg.data


def test_cli_without_pyserial_reports_cleanly(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)
    assert ul.main(["/dev/null", "--info"]) == 2
    assert "pyserial" in capsys.readouterr().err
