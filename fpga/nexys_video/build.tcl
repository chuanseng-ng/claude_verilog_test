# build.tcl -- Vivado batch flow for nexys_video_top (bead hlrm.2). Driven by build.sh through NV_* environment variables.
# In-memory project (so create_ip works), then the usual synth -> opt -> place -> phys_opt -> route -> bitstream steps.
# Not for CI: Vivado is not available there and not in nix.
#
#   NV_ROOT     repo root                       NV_OUT   output directory (reports, dcp, bit)
#   NV_PHASE    synth | all                     NV_TAG   run tag
#   NV_BOOT_HEX absolute path of the boot ROM image ($readmemh text); build.sh defaults it to boot_uart.hex (UART bootloader)
#   NV_THREADS  general.maxThreads (default 4)  NV_PART  device (default xc7a200tsbg484-1)
#   NV_NOCLKFIX 1 = skip clkfix.tcl (BUFG -> BUFGCE cascade) to measure the parallel arrangement against it

proc env_or {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}
set root  $::env(NV_ROOT)
set out   $::env(NV_OUT)
set phase [env_or NV_PHASE all]
set tag   [env_or NV_TAG run]
set part  [env_or NV_PART xc7a200tsbg484-1]
set boot  [env_or NV_BOOT_HEX $root/fpga/nexys_video/boot_uart.hex]
# the boot ROM is 1024 words; $readmemh of a longer file would silently truncate in the ROM init
set bfh [open $boot r]
set bwords [llength [split [string trim [read $bfh]] "\n"]]
close $bfh
if {$bwords < 1 || $bwords > 1024} { error "boot image $boot has $bwords words (boot ROM holds 1..1024)" }
puts "NV-BOOT image $boot: $bwords words, sha256 [lindex [exec sha256sum $boot] 0]"
set here  $root/fpga/nexys_video
set rdir  $out/$tag
file mkdir $rdir
set t0 [clock seconds]
proc stamp {msg} { puts "NV-STAMP [expr {[clock seconds] - $::t0}]s: $msg"; flush stdout }

set_param general.maxThreads [env_or NV_THREADS 4]
create_project -in_memory -part $part
source $here/ip.tcl
source $here/clkfix.tcl
stamp "ip generation"
nv_create_ips $out/ip
stamp "ip done"

# file list = the Stage 0 list for the real GPU (cocotb PLL_SOURCES + rv32i_clock_gate + rtl/fpga/*.sv) + board files.
# rtl/fpga/sim/ (the BUFGCE simulation stub) is deliberately NOT here: Vivado must bind BUFGCE to the primitive.
set fl [open "|bash $root/tools/fpga/stage0_filelist.sh $root gpu fpga" r]
set files [split [string trim [read $fl]] "\n"]
close $fl
lappend files $here/nexys_video_dbg.sv $here/nexys_video_top.sv
# one read_verilog per file: a `default_nettype left open by one file must not leak into the next
foreach f $files { read_verilog -sv $f }
stamp "read [llength $files] files"

synth_design -top nexys_video_top -part $part \
    -verilog_define FPGA -verilog_define __pnr__ -verilog_define FPGA_BUFGCE \
    -generic [list BOOT_HEX=\"$boot\"]
stamp "synth_design done"
read_xdc $here/nexys_video.xdc
if {[env_or NV_NOCLKFIX 0] eq "1"} {
    puts "NV-CLKFIX disabled (NV_NOCLKFIX=1): BUFG -> BUFGCE cascade, for the skew comparison only"
} else {
    nv_bufgce_parallel_fix
}
# -unmanaged: the CDC file uses if/foreach, which a managed XDC rejects ([Designutils 20-1307])
read_xdc -unmanaged $here/nexys_video_cdc.xdc
write_checkpoint -force $rdir/synth.dcp
report_utilization -file $rdir/synth.utilization.rpt
report_clock_networks -file $rdir/synth.clock_networks.rpt
report_drc -file $rdir/synth.drc.rpt
check_timing -verbose -file $rdir/synth.check_timing.rpt
stamp "synth reports"
if {$phase eq "synth"} { exit 0 }

opt_design
stamp "opt_design"
place_design
stamp "place_design"
phys_opt_design
stamp "phys_opt_design"
route_design
stamp "route_design"
phys_opt_design
stamp "post-route phys_opt_design"
write_checkpoint -force $rdir/routed.dcp

report_timing_summary -max_paths 10 -report_unconstrained -file $rdir/timing_summary.rpt
report_utilization -file $rdir/utilization.rpt
report_utilization -hierarchical -hierarchical_depth 3 -file $rdir/utilization_hier.rpt
report_clock_utilization -file $rdir/clock_utilization.rpt
report_clock_interaction -delay_type min_max -file $rdir/clock_interaction.rpt
report_methodology -file $rdir/methodology.rpt
report_drc -file $rdir/drc.rpt
report_io -file $rdir/io.rpt
report_exceptions -file $rdir/exceptions.rpt
# CDC (bead hlrm.3): cdc.rpt = with the documented waivers (the gate input, tools/fpga/cdc_gate.py), cdc_raw.rpt = no waivers
source $here/nexys_video_cdc_waivers.tcl
nv_cdc_waivers
report_cdc -details -file $rdir/cdc.rpt
report_cdc -details -show_waiver -file $rdir/cdc_waived.rpt
report_cdc -details -no_waiver -file $rdir/cdc_raw.rpt
report_waivers -file $rdir/waivers.rpt
report_bus_skew -file $rdir/bus_skew.rpt
report_high_fanout_nets -timing -max_nets 15 -file $rdir/high_fanout.rpt
report_timing -delay_type min -max_paths 10 -nworst 1 -input_pins -file $rdir/paths_hold_worst.rpt
# Gated-vs-ungated skew evidence: ungated-domain flop -> flop behind the GPU / CPU BUFGCE (min = hold, max = setup).
set gpu_ff [get_cells -hierarchical -quiet -filter {NAME =~ u_soc/u_gpu/* && IS_SEQUENTIAL}]
if {[llength $gpu_ff] > 0} {
    report_timing -delay_type min -max_paths 5 -nworst 1 -input_pins -to $gpu_ff -file $rdir/paths_hold_to_gpu.rpt
    report_timing -delay_type max -max_paths 5 -nworst 1 -input_pins -to $gpu_ff -file $rdir/paths_setup_to_gpu.rpt
}
report_timing -delay_type max -max_paths 3 -nworst 1 -input_pins -file $rdir/paths_setup_worst.rpt
stamp "impl reports written"

write_bitstream -force $rdir/nexys_video_top.bit
stamp "bitstream written"
