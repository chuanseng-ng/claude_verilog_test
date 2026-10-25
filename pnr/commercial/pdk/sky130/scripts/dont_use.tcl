# dont_use.tcl -- cells synthesis / optimisation must not pick, for sky130_fd_sc_hd.  Source it AFTER the libraries are read.
#   Synopsys (dc_shell / icc2_shell / pt_shell):  set_dont_use   Cadence (genus / innovus):  set_dont_use  (same name, same lib/cell syntax)
#
# EVIDENCE (lc_shell read_lib warnings, build/logs/lc_*.log -- identical in tt/ss/ff):
#   LIBG-10  "Failed to recognize the functionality": decap_{3,4,6,8,12}, diode_2, lpflow_bleeder_1, lpflow_decapkapwr_{3,4,6,8,12}
#            -> filler / protection cells with no logic function: physical-only, never synthesis targets.
#   LIBG-243 "missing nextstate_type for some input pin(s) in next_state": edfxbp_1, edfxtp_1, sedfxbp_{1,2}, sedfxtp_{1,2,4},
#            sdfbbn_{1,2}, sdfbbp_1  -> DC/Genus cannot map enable/scan-enable flops reliably -> keep out of synthesis.
# NOT derived from the repo flow: pnr/sky130/cpu/config.json sets no DONT_USE_CELLS; LibreLane's own sky130A default list
# (probe_p_8, probec_p_8, lpflow_*) lives in the container image and is NOT verified here -> part-2 task: diff against it.
set _pdk_dont_use {
  sky130_fd_sc_hd__decap_3 sky130_fd_sc_hd__decap_4 sky130_fd_sc_hd__decap_6 sky130_fd_sc_hd__decap_8 sky130_fd_sc_hd__decap_12
  sky130_fd_sc_hd__diode_2 sky130_fd_sc_hd__lpflow_bleeder_1
  sky130_fd_sc_hd__lpflow_decapkapwr_3 sky130_fd_sc_hd__lpflow_decapkapwr_4 sky130_fd_sc_hd__lpflow_decapkapwr_6
  sky130_fd_sc_hd__lpflow_decapkapwr_8 sky130_fd_sc_hd__lpflow_decapkapwr_12
  sky130_fd_sc_hd__edfxbp_1 sky130_fd_sc_hd__edfxtp_1 sky130_fd_sc_hd__sedfxbp_1 sky130_fd_sc_hd__sedfxbp_2
  sky130_fd_sc_hd__sedfxtp_1 sky130_fd_sc_hd__sedfxtp_2 sky130_fd_sc_hd__sedfxtp_4
  sky130_fd_sc_hd__sdfbbn_1 sky130_fd_sc_hd__sdfbbn_2 sky130_fd_sc_hd__sdfbbp_1
}
foreach c $_pdk_dont_use { catch { set_dont_use */$c } }
