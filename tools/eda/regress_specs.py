#!/usr/bin/env python3
"""Print job specs for tools/eda/run_cocotb_targets.py covering the full regression.

  regress_specs.py soc   -- every SOC_CI_SUITES entry (read from the Makefile via `make print-soc-ci-suites`,
                            never a forked list); suites sharing the tb_soc_top elaboration are chained
                            (3 balanced chains) so they share one compile; heaviest jobs first.
  regress_specs.py cpu   -- the CPU / Phase 3 cache / Phase 4 GPU rollup that soc_coverage.yml counts toward
                            CPU_PASS_FLOOR (`make -C sim coverage_cpu_gpu` = `test` + `gpu_all`), expanded to
                            its leaf targets so every build point writes its own results xml.
All jobs of `cpu` run in sim/ and must be run with --jobs 1 (sim/Makefile cannot relocate results.xml).
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TB_SOC_TOP = {"soc_boot", "soc_periph", "soc_coherency", "soc_cpu_gpu", "soc_gpio", "soc_pwm", "soc_wdt",
              "soc_trng", "soc_i2c", "soc_crypto", "soc_npu", "soc_uart_boot", "soc_multiclock",
              "soc_multiclock_reset", "soc_pll_multiclock", "soc_pmu_multiclock", "soc_pmu_iso_ack",
              "soc_integration"}


def soc():
    out = subprocess.run(["make", "-C", str(REPO / "tb/cocotb/soc"), "-s", "SIM=vcs", "print-soc-ci-suites"],
                         capture_output=True, text=True, check=True).stdout.split()
    w = json.load(open(REPO / "tools/verif/soc_shard_weights_plain.json"))
    ws = {k: v["run_s"] for k, v in w["suites"].items() if ":" not in k}
    ws["soc_uart_boot"] = sum(v["run_s"] for k, v in w["suites"].items() if k.startswith("soc_uart_boot:"))
    single, top = [], []
    for s in out:
        (top if s in TB_SOC_TOP else single).append(s)
    chains = [[], [], []]
    load = [0, 0, 0]
    for s in sorted(top, key=lambda s: -ws.get(s, 10.0)):
        i = load.index(min(load))
        chains[i].append(s)
        load[i] += ws.get(s, 10.0)
    jobs = [("+".join("soc:" + s for s in c), sum(ws.get(s, 10.0) for s in c)) for c in chains if c]
    jobs += [("soc:" + s, ws.get(s, 10.0)) for s in single]
    jobs.sort(key=lambda j: -j[1])
    return [j[0] for j in jobs]


def cpu():
    mods = ["test_smoke", "test_c_programs", "test_axi_protocol", "test_debug_if", "test_isa_uvm",
            "test_fault_injection", "test_pipeline_hazards", "test_interrupts", "test_perf_counters",
            "test_csr_access", "test_minstret_write", "test_decode_corners"]
    j = [f"sim:sim:MODULE=tb.cocotb.cpu.{m}" for m in mods]
    j += [f"sim:{t}" for t in ("icache", "dcache", "cache_integration")]           # phase3_all
    j += [f"sim:{t}" for t in ("gpu_regfile", "gpu_alu", "gpu_diverge", "gpu_sched", "gpu_cmdq",
                               "gpu_coalescer", "gpu_memunit", "gpu_shmem", "gpu_top_smoke")]  # gpu_unit
    ks = ["kernel_vector_add", "kernel_dot_product", "kernel_divergence_basic", "kernel_memory_coalesce",
          "kernel_shared_mem_pingpong", "kernel_sync", "kernel_block_warps", "kernel_control_paths"]
    j += [f"sim:sim:MODULE=tb.cocotb.gpu.kernels.{k},TOPLEVEL=gpu_top" for k in ks]   # gpu_kernels (+SIM_BUILD/VERILOG_SOURCES below)
    j += ["sim:gpu_handoff", "sim:gpu_random_smoke"]
    return j


if __name__ == "__main__":
    print("\n".join(soc() if sys.argv[1] == "soc" else cpu()))
