#!/usr/bin/env python3
"""uart_load.py -- host-side loader for the SoC UART boot-ROM bootloader (bead hlrm.2).

Sends an ELF or a flat binary to the bootloader in ``sw/bootloader`` over a serial port,
verifies it with the target-side CRC command, and jumps to it.  Protocol: see
``sw/bootloader/uart_boot_proto.h`` and ``sw/bootloader/README.md``.

    uart_load.py /dev/ttyUSB1 firmware.elf
    uart_load.py /dev/ttyUSB1 firmware.bin --addr 0x2000
    uart_load.py /dev/ttyUSB1 --info                  # just ping the bootloader

The framing/CRC layer (:func:`build_frame`, :func:`crc32`, :class:`Bootloader`) works over
any object with ``write(bytes)``, ``read(n) -> bytes`` (short read = timeout) and
``reset_input_buffer()``; pyserial's ``Serial`` is only imported by the CLI.
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# ---- protocol constants (parsed against uart_boot_proto.h by tb/tests/test_uart_load.py) ----
PROTO_VERSION = 1
SOF = 0x7E
ACK = 0x06
NAK = 0x15
CMD_INFO = 0x01
CMD_WRITE = 0x02
CMD_CRC = 0x03
CMD_JUMP = 0x04
ERR_CRC = 0x01
ERR_CMD = 0x02
ERR_LEN = 0x03
ERR_ADDR = 0x04
ERR_TIMEOUT = 0x05
BANNER = b"\nUBL1\n"

ERR_NAMES = {
    ERR_CRC: "bad CRC",
    ERR_CMD: "unknown command",
    ERR_LEN: "bad length",
    ERR_ADDR: "address outside the SRAM load region",
    ERR_TIMEOUT: "target timed out mid-frame",
}
# Errors after which the target may be mid-frame or desynchronised: wait out its idle timeout
# (BL_IDLE_MS, 20 ms by default) before re-sending.  A bad address/command is a clean refusal.
RETRYABLE = {ERR_CRC, ERR_LEN, ERR_TIMEOUT}

DEFAULT_ADDR = 0x2000
DEFAULT_RESYNC_GAP = 0.06  # seconds; must exceed the target's BL_IDLE_MS (20 ms)


class BootloaderError(RuntimeError):
    """The target refused a command, or never answered."""


class Link(Protocol):
    """The serial-port subset the protocol layer needs (pyserial ``Serial`` satisfies it)."""

    def write(self, data: bytes, /) -> object: ...
    def read(self, size: int, /) -> bytes: ...
    def reset_input_buffer(self) -> None: ...


def crc32(data: bytes, crc: int = 0) -> int:
    """IEEE 802.3 CRC-32 (reflected, init/xorout 0xFFFFFFFF) -- identical to ``zlib.crc32``."""
    return zlib.crc32(data, crc) & 0xFFFFFFFF


def build_frame(cmd: int, payload: bytes = b"") -> bytes:
    """``SOF CMD LEN_LO LEN_HI PAYLOAD CRC32`` with the CRC over everything after SOF."""
    if not 0 <= len(payload) <= 0xFFFF:
        raise ValueError("payload too long")
    body = bytes([cmd]) + struct.pack("<H", len(payload)) + payload
    return bytes([SOF]) + body + struct.pack("<I", crc32(body))


@dataclass(frozen=True)
class Response:
    """One decoded target reply: ACK with payload, or NAK with an error code."""

    ok: bool
    payload: bytes = b""  # ACK payload
    error: int = 0  # NAK error code


def read_response(link: Link) -> Response | None:
    """Read one ACK/NAK response; ``None`` if the target stays silent (timeout)."""
    head = link.read(2)
    if len(head) < 2:
        return None
    status, arg = head
    if status == NAK:
        return Response(False, error=arg)
    if status != ACK:
        return Response(False, error=-1)  # line noise: treat as a failed, retryable exchange
    body = link.read(arg) if arg else b""
    if len(body) < arg:
        return None
    return Response(True, payload=body)


@dataclass(frozen=True)
class Info:
    """Contents of the INFO reply."""

    version: int
    max_data: int
    load_lo: int
    load_hi: int


def parse_info(payload: bytes) -> Info:
    """Decode the 11-byte INFO payload."""
    if len(payload) != 11:
        raise BootloaderError(f"INFO payload is {len(payload)} bytes, expected 11")
    ver, max_data, lo, hi = struct.unpack("<BHII", payload)
    return Info(ver, max_data, lo, hi)


class Bootloader:
    """Command layer over a serial-like link."""

    def __init__(
        self,
        link: Link,
        *,
        retries: int = 3,
        resync_gap: float = DEFAULT_RESYNC_GAP,
        sleep=time.sleep,
        log=lambda msg: None,
    ) -> None:
        self.link = link
        self.retries = retries
        self.resync_gap = resync_gap
        self._sleep = sleep
        self._log = log

    def _resync(self) -> None:
        # Stay silent past the target's inter-byte timeout so it abandons any half frame,
        # then discard whatever it said (a stray NAK TIMEOUT) before re-sending.
        self._sleep(self.resync_gap)
        self.link.reset_input_buffer()

    def transact(self, cmd: int, payload: bytes = b"") -> bytes:
        """Send one command, return the ACK payload. Retries CRC/timeout/noise failures."""
        frame = build_frame(cmd, payload)
        last = "no response"
        for attempt in range(self.retries + 1):
            self.link.write(frame)
            resp = read_response(self.link)
            if resp is not None and resp.ok:
                return resp.payload
            if resp is not None and resp.error not in RETRYABLE and resp.error != -1:
                name = ERR_NAMES.get(resp.error, f"error 0x{resp.error:02x}")
                raise BootloaderError(f"target refused command 0x{cmd:02x}: {name}")
            last = "no response" if resp is None else ERR_NAMES.get(resp.error, "line noise")
            self._log(f"cmd 0x{cmd:02x} attempt {attempt + 1} failed ({last}); resyncing")
            self._resync()
        raise BootloaderError(f"command 0x{cmd:02x} failed after {self.retries + 1} tries: {last}")

    def info(self) -> Info:
        """Query protocol version, block size and the load window."""
        return parse_info(self.transact(CMD_INFO))

    def write(self, addr: int, data: bytes) -> None:
        """Store ``data`` at ``addr`` in target SRAM (at most the INFO block size)."""
        self.transact(CMD_WRITE, struct.pack("<I", addr) + data)

    def remote_crc(self, addr: int, nbytes: int) -> int:
        """CRC32 of target SRAM as the target reads it back (after a D$ flush)."""
        return struct.unpack("<I", self.transact(CMD_CRC, struct.pack("<II", addr, nbytes)))[0]

    def jump(self, entry: int) -> None:
        """Start the image at ``entry`` (the target flushes the D$ and runs FENCE.I first)."""
        self.transact(CMD_JUMP, struct.pack("<I", entry))


# ---- images ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """A contiguous block of image bytes and its target address."""

    addr: int
    data: bytes


def load_bin(path: Path, addr: int) -> list[Segment]:
    """A flat binary is one segment at ``addr``."""
    return [Segment(addr, path.read_bytes())]


def load_elf(data: bytes) -> tuple[list[Segment], int]:
    """Minimal ELF32-LE reader: PT_LOAD segments (by physical address) and the entry point."""
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise ValueError("not a 32-bit little-endian ELF")
    (e_entry,) = struct.unpack_from("<I", data, 24)
    (e_phoff,) = struct.unpack_from("<I", data, 28)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
    segs: list[Segment] = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_offset, _vaddr, p_paddr, p_filesz, _memsz = struct.unpack_from("<6I", data, off)
        if p_type == 1 and p_filesz:  # PT_LOAD with file content (zero-fill .bss is not sent)
            segs.append(Segment(p_paddr, data[p_offset : p_offset + p_filesz]))
    if not segs:
        raise ValueError("ELF has no loadable segments")
    return segs, e_entry


def chunks(seg: Segment, size: int) -> Iterator[Segment]:
    """Split a segment into WRITE-sized pieces."""
    for off in range(0, len(seg.data), size):
        yield Segment(seg.addr + off, seg.data[off : off + size])


def check_fits(segs: Iterable[Segment], info: Info) -> None:
    """Refuse images that fall outside the target load window before sending anything."""
    for s in segs:
        if s.addr < info.load_lo or s.addr + len(s.data) > info.load_hi:
            raise BootloaderError(
                f"segment 0x{s.addr:08x}..0x{s.addr + len(s.data):08x} is outside the "
                f"target load region 0x{info.load_lo:08x}..0x{info.load_hi:08x}"
            )


def load_image(
    bl: Bootloader,
    segs: list[Segment],
    *,
    verify: bool = True,
    chunk: int | None = None,
    progress=lambda done, total: None,
) -> Info:
    """Write every segment, then CRC-verify each against the target's own SRAM contents."""
    info = bl.info()
    if info.version != PROTO_VERSION:
        raise BootloaderError(f"bootloader protocol v{info.version}, tool speaks v{PROTO_VERSION}")
    check_fits(segs, info)
    size = min(chunk or info.max_data, info.max_data)
    total = sum(len(s.data) for s in segs)
    done = 0
    for seg in segs:
        for piece in chunks(seg, size):
            bl.write(piece.addr, piece.data)
            done += len(piece.data)
            progress(done, total)
    if verify:
        for seg in segs:
            got = bl.remote_crc(seg.addr, len(seg.data))
            want = crc32(seg.data)
            if got != want:
                raise BootloaderError(
                    f"verify failed at 0x{seg.addr:08x}: "
                    f"target CRC 0x{got:08x}, expected 0x{want:08x}"
                )
    return info


# ---- CLI ---------------------------------------------------------------------------------


def _int(s: str) -> int:
    """argparse type: decimal or 0x-prefixed integer."""
    return int(s, 0)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; returns the process exit status."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    ap.add_argument("port", help="serial port, e.g. /dev/ttyUSB1 or COM5")
    ap.add_argument("image", nargs="?", type=Path, help="ELF (detected by magic) or flat binary")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--stopbits",
        type=int,
        choices=(1, 2),
        default=2,
        help="stop bits per byte; 2 (default, 8N2) keeps one bit time of idle margin per byte, "
        "1 (8N1) also works since the SoC UART receiver re-syncs on every START edge "
        "(bead shm5, see sw/bootloader/README.md); 8N2 costs ~10%% throughput",
    )
    ap.add_argument("--addr", type=_int, default=DEFAULT_ADDR, help="load address of a flat binary")
    ap.add_argument("--entry", type=_int, help="jump address (default: ELF entry, or --addr)")
    ap.add_argument("--chunk", type=int, help="WRITE block size (default: target max)")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=1.0, help="per-response timeout, seconds")
    ap.add_argument("--no-verify", action="store_true", help="skip the CRC read-back")
    ap.add_argument("--no-jump", action="store_true", help="load only; do not start the image")
    ap.add_argument("--info", action="store_true", help="only query the bootloader and exit")
    args = ap.parse_args(argv)

    try:
        import serial  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel
    except ImportError:
        print("pyserial is required: pip install pyserial", file=sys.stderr)
        return 2

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    stop = serial.STOPBITS_TWO if args.stopbits == 2 else serial.STOPBITS_ONE
    with serial.Serial(args.port, args.baud, stopbits=stop, timeout=args.timeout) as ser:
        bl = Bootloader(ser, retries=args.retries, log=log)
        ser.reset_input_buffer()
        try:
            if args.info or args.image is None:
                info = bl.info()
                print(
                    f"bootloader v{info.version}, max block {info.max_data} B, "
                    f"load region 0x{info.load_lo:08x}..0x{info.load_hi:08x}"
                )
                return 0
            raw = args.image.read_bytes()
            if raw[:4] == b"\x7fELF":
                segs, entry = load_elf(raw)
            else:
                segs, entry = [Segment(args.addr, raw)], args.addr
            if args.entry is not None:
                entry = args.entry

            def progress(done: int, total: int) -> None:
                print(f"\r{done}/{total} bytes", end="", file=sys.stderr, flush=True)

            load_image(bl, segs, verify=not args.no_verify, chunk=args.chunk, progress=progress)
            print(file=sys.stderr)
            if not args.no_jump:
                bl.jump(entry)
                print(f"jumped to 0x{entry:08x}", file=sys.stderr)
        except BootloaderError as exc:
            print(f"\nerror: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
