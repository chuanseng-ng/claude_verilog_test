#!/usr/bin/env python3
"""
gen_soc_top_hjson.py — Generate soc_top.h.json manually.

soc_top.sv has these ports (after __pnr__ substitution):
  clk_i         input  1
  rst_n_i       input  1
  apb_paddr_i   input  12
  apb_psel_i    input  1
  apb_penable_i input  1
  apb_pwrite_i  input  1
  apb_pwdata_i  input  32
  apb_prdata_o  output 32
  apb_pready_o  output 1
  apb_pslverr_o output 1
  uart_tx_o     output 1
  uart_rx_i     input  1
  spi_sclk_o    output 1
  spi_mosi_o    output 1
  spi_miso_i    input  1
  spi_cs_n_o    output 1
  commit_valid_o output 1
  commit_pc_o    output 32
  commit_insn_o  output 32
  gpu_irq_o      output 1
  pll_locked_o   output 1

Format: same as Yosys json output. Bit numbers are sequential from 2.
"""

import json, sys, os

creator = "Yosys 0.46 (git sha1 e97731b9dda91fa5fa53ed87df7c34163ba59a41, clang++ 17.0.6 -fPIC -O3)"

# Port definitions: (name, direction, width)
PORTS = [
    ("clk_i",          "input",  1),
    ("rst_n_i",        "input",  1),
    ("apb_paddr_i",    "input",  12),
    ("apb_psel_i",     "input",  1),
    ("apb_penable_i",  "input",  1),
    ("apb_pwrite_i",   "input",  1),
    ("apb_pwdata_i",   "input",  32),
    ("apb_prdata_o",   "output", 32),
    ("apb_pready_o",   "output", 1),
    ("apb_pslverr_o",  "output", 1),
    ("uart_tx_o",      "output", 1),
    ("uart_rx_i",      "input",  1),
    ("spi_sclk_o",     "output", 1),
    ("spi_mosi_o",     "output", 1),
    ("spi_miso_i",     "input",  1),
    ("spi_cs_n_o",     "output", 1),
    ("commit_valid_o", "output", 1),
    ("commit_pc_o",    "output", 32),
    ("commit_insn_o",  "output", 32),
    ("gpu_irq_o",      "output", 1),
    ("pll_locked_o",   "output", 1),
]

def make_ports():
    result = {}
    bit_idx = 2  # Yosys starts from 2
    for name, direction, width in PORTS:
        bits = list(range(bit_idx, bit_idx + width))
        bit_idx += width
        result[name] = {"direction": direction, "bits": bits}
    return result

doc = {
    "creator": creator,
    "modules": {
        "soc_top": {
            "attributes": {
                "top": "00000000000000000000000000000001",
                "src": "/home/neuromorphic/Downloads/Github/claude_verilog_test/rtl/soc/soc_top.sv:39.1-1099.10"
            },
            "parameter_default_values": {
                "MEM_INIT_FILE":  "00000000000000000000000000000000",
                "PLL_IMPL":       "00000000000000000000000000000000",
                "SRAM_MEM_WORDS": "00000000000000000000010000000000",  # 1024 in binary
            },
            "ports": make_ports(),
            "cells": {},
            "netnames": {}
        }
    }
}

output_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/soc_top.h.json"
with open(output_path, "w") as f:
    json.dump(doc, f, indent=4)

print(f"Written {output_path} ({os.path.getsize(output_path)} bytes)", file=sys.stderr)
