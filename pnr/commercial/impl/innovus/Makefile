# Step B5b: Cadence Innovus place-and-route of the Sky130 CPU macro rv32i_cpu_top from the Conformal-proven Genus netlist (b3b_genus_tt_r2).
#   make -C pnr/commercial/impl/innovus all [TAG=b5b_innovus]     run stages 01..06 in order (each under safe_run.sh: <=7 GB, load gate)
#   make -C pnr/commercial/impl/innovus stage S=03_place          run one stage; each restoreDesign's the previous runs/<TAG>/dbs/<label>.enc
#   make -C pnr/commercial/impl/innovus captbl                    stop-gap capTable from the authored ICT (used for post-route extraction only)
#   make -C pnr/commercial/impl/innovus reports                   copy the key native reports to reports/ as .txt (runs/ is gitignored; *.rpt is ignored by pnr/.gitignore)
TAG ?= b5b_innovus
S   ?= 01_floorplan
STAGES := 01_floorplan 02_pdn 03_place 04_cts 05a_route 05_route 06_finish   # 05_route restores FROM_LABEL (default 05b_repair); the run used FROM_LABEL=05a_routed (05b ecoRoute repair did not converge)
.PHONY: all stage captbl reports
all:
	@set -e; for s in 01_floorplan 02_pdn 03_place 04_cts 05a_route; do scripts/run_stage.sh $$s $(TAG); done; FROM_LABEL=05a_routed scripts/run_stage.sh 05_route $(TAG); FROM_LABEL=05_route scripts/run_stage.sh 06_finish $(TAG)
stage:
	scripts/run_stage.sh $(S) $(TAG)
captbl:
	scripts/run_captbl.sh
reports:
	@mkdir -p reports; R=runs/$(TAG)/reports; \
	for f in final_summary final_power final_route_summary final_area final_violators final_timing_setup final_timing_hold final_clock_trees final_skew_groups final_cellcount \
	         final_drc final_antenna final_connectivity final_pg_connectivity final_powervia final_checkPlace drc_after_route antenna_after_route streamOut; do \
	  [ -f $$R/$$f.txt ] && cp $$R/$$f.txt reports/$$f.txt; [ -f $$R/$$f.rpt ] && cp $$R/$$f.rpt reports/$$f.txt; done; \
	for d in final_setup final_hold timing_postRoute timing_postRoute_hold; do \
	  for g in $$R/$$d/*.summary.gz; do [ -f $$g ] && zcat $$g > reports/$$d.summary.txt; done; done; \
	for l in runs/$(TAG)/logs/*.time; do echo "$$l"; grep -E "Elapsed|Maximum resident" $$l; done > reports/runtime_rss.txt; ls reports
