run_id:      pd_20260623_070000
design_name: soc_top
pdk:         asap7
tool:        LibreLane
start_time:  2026-06-23T07:00:00+07:00
last_stage:  synthesis

run_dir:     /nobackup/asap7_soc_runs/RUN_2026-06-23_07-xx-xx (pending launch)

note:        M11 P&R run 12 — sv2v frontend breakthrough.

             Root cause discovered: SYNLIG (all modes) cannot elaborate this SoC:
               SYNLIG_DEFER=true  -> peripheral FSMs dropped (0 FFs, confirmed
                 by undriven output signals on DMA, UART, crossbar in log).
               SYNLIG_DEFER=false -> UHDM assert !wire->name.empty() rtlil.cc:2150
                 (crash in json_header BEFORE any hierarchy pass).
               USE_SYNLIG=false   -> yosys read_verilog -sv fails on `package`
                 keyword in soc_addr_map_pkg.sv (not plain Verilog-2005).

             Fix: sv2v 0.0.13.1 (nixpkgs haskellPackages) pre-converts all SoC
             SV → plain Verilog-2005. Output: pnr/asap7/soc/soc_top_sv2v.v.
             Verified: yosys read_verilog + proc + flatten -> 5500 cells, 0 errors.
             Config: USE_SYNLIG=false, SYNLIG_DEFER=false, SYNTH_HIERARCHY_MODE=flatten.
             VERILOG_FILES: [sram_stub.v, soc_top_sv2v.v] only.

             Makefile: asap7-soc-sv2v target prerequisite for librelane-asap7-soc.
             Committed: 6ee91b6.
             Log: /nobackup/asap7_soc_run12.log
