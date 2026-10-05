run_id:      pd_20261004_164726_gateb
design_name: soc_top
pdk:         sky130A
tool:        LibreLane 2.4.13 (nix-shell, ~/Downloads/Github/librelane), make -C pnr librelane-sky130-soc-noklayout
start_time:  2026-10-04T16:47:26+07:00
last_stage:  signoff FAIL (ss setup); escalated

Task: bead claude_verilog_test-f7vs.15 -- Phase 6 Gate B batched Sky130 SoC harden (PWM/WDT/TRNG/I2C/CRYPTO/NPU).
Baseline: RUN_2026-09-26_19-25-08 (config.json == its resolved.json knobs; antenna 20/50, repair 30/30/40/40, hold margins 0.3).
Branch feat/phase6-gateb-f7vs15. No commits. Config/cfg/doc edits left in working tree.
Prior archived state: run_state.archived_pd_20260919_ma7_cpu_reharden.md (ASAP7 ma7, shelved, unrelated).

FINAL 2026-10-04T20:59:57+07:00: harden complete, signoff_achieved=false (ss setup, antenna, Magic, KLayout skipped). Run dir pnr/sky130/soc/runs/RUN_2026-10-04_17-02-18; probe run GATEB_NPU_SRAM_PROBE.
