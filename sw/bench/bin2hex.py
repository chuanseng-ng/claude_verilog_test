#!/usr/bin/env python3
"""bin2hex.py — flat binary -> one-word-per-line hex for $readmemh / cocotb backdoor.

The SoC behavioral memories (boot_rom.sv, sram_controller.sv) store 32-bit words
and the cocotb loaders assign mem[i] = int(line, 16), word i at byte address
base + i*4. objcopy -O binary gives a little-endian byte stream; we repack it into
little-endian 32-bit words and print 8 hex digits per line (zero-padding a short
final word). Usage: bin2hex.py in.bin > out.hex
"""
import sys


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: bin2hex.py <in.bin>\n")
        return 2
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    out = []
    for i in range(0, len(data), 4):
        word = int.from_bytes(data[i:i + 4], "little")
        out.append(f"{word:08x}")
    sys.stdout.write("\n".join(out) + ("\n" if out else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
