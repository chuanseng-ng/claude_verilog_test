# Synlig-frontend audit scripts (claude_verilog_test-b0t, part A)

Standalone Yosys scripts used to audit whether LibreLane 2.4.13's Synlig frontend
(`USE_SYNLIG:true`, used by `pnr/asap7/cpu/config.json` + `config_3014.json` and
`pnr/asap7/gpu/config.json` + `config_3014.json`) introduces functional corruption
analogous to the OPT_MUXTREE dead-mux-port defect proven on the Bambu HLS `vector_alu`
candidate (bead `gcd`). Run outside full LibreLane (Yosys-only, no P&R) to stay cheap.

Binaries used (hardcoded absolute nix-store paths, same GC-root rationale as
`tools/verif/equiv_sv2v_module.sh`):
- Independent reference frontend: yosys-slang plugin on yosys 0.62 —
  `/nix/store/4bmfi4470w0i3ixcaidfki18d3fyqvva-yosys-with-plugins-0.62/bin/yosys` +
  `/nix/store/07xn6zd11qvkp8h65gwycfisr3x9hk4f-yosys-slang/share/yosys/plugins/slang.so`.
- Real Synlig frontend, the SAME binary LibreLane 2.4.13 actually invokes (yosys 0.46,
  loaded via `plugin -i synlig-sv` which resolves through its plugin search path) —
  `/nix/store/y4lsl792fjahppq4xk68s5ckh7mwks70-yosys-with-plugins/bin/yosys`. The newer
  yosys 0.62 above CANNOT load `synlig-sv.so` (`undefined symbol:
  ...Yosys3AST16current_filename...` — ABI mismatch against a different yosys AST core),
  so the two frontends necessarily run on different yosys binaries; only the frontend
  (Synlig vs slang) is the intended variable, not the optimizer, since both scripts issue
  the identical `librelane_opt(nodffe=True, nosdff=True)` pass sequence transcribed from
  `librelane/scripts/pyosys/synthesize.py`.

## Scripts

- `audit_cpu_slang2.ys` — elaborates `rv32i_cpu_top` via slang, flattens (matches
  `SYNTH_HIERARCHY_MODE` default `flatten`, as used by the CPU macro), then runs
  `librelane_proc` + the exact `librelane_opt(nodffe=True, nosdff=True)` loop. Compare its
  `OPT_MUXTREE "Removed N multiplexer ports"` output against the real tracked Synlig run's
  log at `pnr/asap7/cpu/runs/bpp7_postgrt_set/05-yosys-synthesis/yosys-synthesis.log`.
- `audit_gpu_slang.ys` — same for `gpu_top`, WITHOUT flatten (`SYNTH_HIERARCHY_MODE:
  "keep"` for the GPU macro) — note `read_slang` needs `--best-effort-hierarchy` or it
  silently auto-inlines everything into one `gpu_top` scope regardless of the `keep`
  setting downstream, which would invalidate any per-module comparison.
- `audit_gpu_synlig.ys` — same RTL, real Synlig frontend (`plugin -i synlig-sv`,
  `read_systemverilog -sverilog`), run on the yosys 0.46 binary above. No tracked GPU
  Synlig run/log survives on this host, so this script is how the GPU-macro Synlig data
  point was generated fresh (Yosys-only, ~13s, well under the 8G cap).
- `synlig_shmem_gate.ys` — standalone Synlig synth+opt of `shared_memory` alone
  (reproduced the 1001-port removal found in the full `gpu_top` run, confirming it is
  local to this module), dumping the post-opt RTLIL as
  `/nobackup/b0t_audit/shared_memory_synlig_gate.v` for the EQY step below.
- `eqy_shmem.ys` — EQY (`equiv_make`/`equiv_simple -seq 5`/`equiv_induct -seq 20`)
  between `shared_memory` RTL (gold, via slang, proc+flatten+memory+async2sync only, no
  optimisation) and the Synlig-optimised netlist above (gate). Both sides keep the
  `sram_1rw_128x32_asap7` bank macros as unmodeled blackboxes (32 per side).

## Headline results (2026-09-18, see bead `claude_verilog_test-b0t` notes for the full writeup)

| Block | Method | Result |
|---|---|---|
| `rv32i_cpu_top` (CPU macro) | Structural differential, `librelane_opt(nodffe,nosdff)` post-flatten | Synlig (real run): 800 mux ports removed. Independent slang run: 1358 removed — MORE, not fewer, and the sampled dead branches match 1:1 by register name (`u_dcache.flush_mode_q`, `u_dcache/u_icache.ar_pending_q`). Opposite signature from the gcd corruption (which had Synlig deleting ~27x MORE than the alternative frontend). |
| `gpu_top` / `vector_alu` (GPU macro) | Structural differential, same opt sequence, hierarchy kept | `vector_alu`: 16 dead ports removed on BOTH frontends — exact match. |
| `gpu_top` / `shared_memory` | Structural differential + direct EQY | Synlig removed 1001 mux ports vs slang's 1 — large raw divergence, investigated directly. EQY (gold=un-optimised RTL, gate=Synlig-optimised netlist): 292 `$equiv` points found, 36 proven, 0 DISPROVEN, 256 unproven — and all 256 are exactly `sh_rdata_o[255:0]`, the SRAM-macro read-data bits blocked by "No SAT model available for cell ... (sram_1rw_128x32_asap7)" (expected black-box limitation, not a corruption signature). Every provable point proved equivalent. |
| `gpu_top` / `gpu_compute_unit`, `memory_coalescer`, `gpu_top` glue | Structural differential only, not individually EQY'd | slang found MORE dead ports than Synlig in all three (56 vs 0, 26 vs 2, 27 vs 0) — same reassuring "Synlig conservative" direction as the CPU result, but not confirmed by EQY. Flagged as unproven, not concerning by direction. |

Re-run: `systemd-run --user --scope -p MemoryMax=8G -p MemorySwapMax=0 -- <yosys-bin> -l <log> -s <script>.ys`.
