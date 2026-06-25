run_id:      pd_20260623_110021
design_name: soc_top
pdk:         asap7
tool:        LibreLane
start_time:  2026-06-23T18:05:30+07:00
last_stage:  signoff

run_dir:     /nobackup/asap7_soc_runs/RUN_2026-06-24_05-23-19
log:         /nobackup/asap7_soc_run15.log

STATUS (2026-06-24 05:25 WIB):
  Run 15 ACTIVE — launched to fix macro PDN connectivity.
  tmux session: soc_pd_run15
  
  FIX APPLIED (commit c1f7bbd):
  - rv32i_cpu_top.lef: PIN VDD PORT/RECT M7 perimeter at y=0.50-0.66 (inner)
  - rv32i_cpu_top.lef: PIN VSS PORT/RECT M7 perimeter at y=0.82-0.98 (outer)
  - gpu_top.lef: same geometry scaled to 340x340 um footprint
  - .gitignore: added !asap7/*/macro/*.lef exceptions
  
  Run 14 metrics preserved (to be reproduced):
    WNS=0, TNS=0, DRC=0, Antenna=0, Power=62.9mW, Util=65.6%
  Target: PDN violations → ~0.
  
  Monitor: ls /nobackup/asap7_soc_runs/RUN_2026-06-24_05-23-19/
