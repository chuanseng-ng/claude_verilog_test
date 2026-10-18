#!/usr/bin/env python3
"""boot_image.py -- reproducible boot-ROM image for the Nexys Video prototype (bead hlrm.4).

The committed image fpga/nexys_video/boot_uart.hex is the UART bootloader of sw/bootloader built for the board
(64 KB SRAM, 75 MHz CPU clock for the mcycle timeouts, 50 MHz / 115200 UART). A manifest next to it records the sha256 of every
source file that can change the image, the build parameters, the toolchain and the sha256 of the hex itself.

  write   copy a freshly built hex + bin into the repo and write the manifest   (used by `make -C fpga/nexys_video bootimg`)
  check   stdlib only, no RISC-V toolchain, runs in CI: the sources still hash to the manifest, the hex hashes to the manifest,
          and the hex is a well-formed $readmemh image of the recorded size.  Fails if firmware sources changed without
          `make bootimg`, or if the hex was edited by hand.
  verify  check + compare the committed hex byte for byte with a fresh build (needs the riscv32 toolchain; the Makefile
          target `bootimg-check` provides it through the nix `bench` devShell).

Exit 0 = pass, 1 = stale / malformed, 2 = usage or missing file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEX = ROOT / "fpga/nexys_video/boot_uart.hex"
MANIFEST = ROOT / "fpga/nexys_video/boot_uart.manifest.json"
# Everything that can change the image. A new input to the bootloader build must be added here.
SOURCES = (
    "sw/bootloader/uart_boot.c",
    "sw/bootloader/crt0.S",
    "sw/bootloader/bootloader.ld.in",
    "sw/bootloader/bl_config.h",
    "sw/bootloader/uart_boot_proto.h",
    "sw/bootloader/Makefile",
    "sw/bench/bin2hex.py",
)
# The board parameters; the Makefile passes exactly these to sw/bootloader's make.
PARAMS = {
    "variant": "default",
    "SRAM_BYTES": "65536",  # nexys_video_top SRAM_WORDS = 16384
    "EXTRA_DEFS": "-DBL_CPU_HZ=75000000u",  # mcycle counts the 75 MHz CPU clock (the default assumes 50 MHz)
}
ROM_WORDS = 1024  # boot_rom MEM_WORDS
WORD = re.compile(r"^[0-9a-f]{8}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    return {p: sha256(ROOT / p) for p in SOURCES}


def check_hex(path: Path) -> tuple[int, list[str]]:
    errs: list[str] = []
    lines = path.read_text().splitlines()
    for i, ln in enumerate(lines, 1):
        if not WORD.match(ln):
            errs.append(f"{path.name}:{i}: not an 8-digit lowercase hex word: {ln!r}")
            break
    if not 0 < len(lines) <= ROM_WORDS:
        errs.append(f"{path.name}: {len(lines)} words, boot ROM holds 1..{ROM_WORDS}")
    return len(lines), errs


def cmd_check(_: argparse.Namespace) -> int:
    for p in (HEX, MANIFEST):
        if not p.is_file():
            print(f"missing {p.relative_to(ROOT)}: run `make -C fpga/nexys_video bootimg`")
            return 2
    man = json.loads(MANIFEST.read_text())
    bad: list[str] = []
    cur = source_hashes()
    for p, h in cur.items():
        if man["sources"].get(p) != h:
            bad.append(f"source changed since the image was built: {p}")
    for p in set(man["sources"]) - set(cur):
        bad.append(f"manifest lists a source no longer tracked here: {p}")
    if man["params"] != PARAMS:
        bad.append(f"manifest params {man['params']} != {PARAMS}")
    if man["hex_sha256"] != sha256(HEX):
        bad.append("boot_uart.hex does not match the manifest hash (edited by hand?)")
    words, errs = check_hex(HEX)
    bad += errs
    if words != man["words"]:
        bad.append(f"hex has {words} words, manifest says {man['words']}")
    if bad:
        print("boot image is STALE or malformed:")
        for b in bad:
            print("  -", b)
        print("fix: nix develop .#bench --command make -C fpga/nexys_video bootimg   (then commit both files)")
        return 1
    print(f"boot image OK: {words} words ({words * 4} of {ROM_WORDS * 4} bytes), "
          f"hex sha256 {man['hex_sha256'][:16]}..., {len(cur)} sources match the manifest")
    return 0


def cmd_write(a: argparse.Namespace) -> int:
    hexp, binp = Path(a.hex), Path(a.bin)
    words, errs = check_hex(hexp)
    if errs:
        print("\n".join(errs))
        return 1
    if (binp.stat().st_size + 3) // 4 != words:
        print(f"{binp} is {binp.stat().st_size} bytes but the hex has {words} words")
        return 1
    HEX.write_bytes(hexp.read_bytes())
    tool = subprocess.run(["riscv32-none-elf-gcc", "--version"], capture_output=True, text=True, check=False)
    man = {
        "image": "fpga/nexys_video/boot_uart.hex",
        "generator": "make -C fpga/nexys_video bootimg   (tools/fpga/boot_image.py write)",
        "params": PARAMS,
        "sources": source_hashes(),
        "bin_bytes": binp.stat().st_size,
        "words": words,
        "hex_sha256": sha256(HEX),
        "toolchain": (tool.stdout.splitlines() or ["unknown"])[0],
    }
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n")
    print(f"wrote {HEX.relative_to(ROOT)} ({words} words, {binp.stat().st_size} bytes) and {MANIFEST.relative_to(ROOT)}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    rc = cmd_check(a)
    if rc:
        return rc
    fresh = Path(a.hex)
    if fresh.read_bytes() != HEX.read_bytes():
        print(f"committed boot_uart.hex differs from a fresh build ({fresh}): run `make bootimg` and commit")
        return 1
    print("committed boot_uart.hex == fresh build")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    w = sub.add_parser("write")
    w.add_argument("--hex", required=True)
    w.add_argument("--bin", required=True)
    w.set_defaults(fn=cmd_write)
    v = sub.add_parser("verify")
    v.add_argument("--hex", required=True, help="freshly built uart_boot.hex")
    v.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
