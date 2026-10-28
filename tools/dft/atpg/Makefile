# DFT Stage 3 ATPG spike (bead j41m.15): Quaigh ladder npu -> crypto -> dma -> fabric.
# Heavy outputs: $(W) (default /nobackup/claude_sim_build/j41m15), never in git.  See README.md.
#   make ladder        every rung in order; STOP at the first rung that breaks the box (12 GB / 24 h), per the user decision
#   make rung-<name>   one rung (npu crypto dma fabric)
#   make timer-known   Stage 0 known answer: 4336/4692 = 92.41 % on the committed Stage 0 BLIF
#   make test          pytest of the scripts
#   make metrics       print each rung's metrics.json and coverage report
W ?= /nobackup/claude_sim_build/j41m15
export W
RUNGS := npu crypto dma fabric

.PHONY: ladder test metrics timer-known $(addprefix rung-,$(RUNGS))

ladder:
	@set -e; for r in $(RUNGS); do \
	  $(MAKE) --no-print-directory rung-$$r; \
	  ok=$$(python3 -c "import json;print(int(json.load(open('$(W)/'+'$$r'+'/q/metrics.json'))['completed']))"); \
	  if [ "$$ok" != 1 ]; then echo "rung $$r broke the box: stop (see $(W)/$$r/q/metrics.json)"; exit 1; fi; \
	done

rung-%:
	./run_rung.sh $*

timer-known:
	mkdir -p $(W)/timer_s0
	./run_capped.sh $(W)/timer_s0 -- $(W)/bin/quaigh atpg /nobackup/claude_sim_build/dft_stage0/q1/timer_cut.blif -o $(W)/timer_s0/timer.test
	python3 coverage_report.py $(W)/timer_s0/run.log --metrics $(W)/timer_s0/metrics.json --label timer_stage0 --md

test:
	python3 -m pytest ../../../tb/tests/test_dft_atpg_hold_mask.py ../../../tb/tests/test_dft_atpg_coverage.py \
	    ../../../tb/tests/test_dft_atpg_regrade.py -q

metrics:
	@for r in $(RUNGS); do echo "== $$r"; cat $(W)/$$r/q/metrics.json 2>/dev/null | python3 -c "import json,sys;m=json.load(sys.stdin);print({k:m[k] for k in ('rc','wall_s','maxrss_kb','cgroup_peak_bytes','completed','timed_out','killed_by_cap')})" || echo "not run"; done
