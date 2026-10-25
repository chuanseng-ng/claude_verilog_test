# load_innovus.tcl -- Innovus load check: init_design (MMMC, tech+cell+SRAM LEF, trivial netlist), small floorplan,
# then verify rows / sites / tracks / PG nets.      innovus -nowin -files load_innovus.tcl   (env HERE, PDK_ROOT, SDC)
set HERE $::env(HERE)
set PDKR $::env(PDK_ROOT)/sky130A/libs.ref
setMultiCpuUsage -localCpu 1
set init_lef_file [list $PDKR/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef \
                        $PDKR/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef \
                        $PDKR/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef]
set init_verilog   $HERE/tests/link_trivial.v
set init_top_cell  link_trivial
set init_mmmc_file $HERE/scripts/mmmc.tcl
# hd cells use VPWR/VGND; the SRAM macro uses vccd1/vssd1 -> both pairs are declared global and tied to the same nets
set init_pwr_net   {VPWR vccd1}
set init_gnd_net   {VGND vssd1}
init_design
puts "=== init_design done"
floorPlan -site unithd -d 700 600 10 10 10 10
puts "=== floorplan"
puts "rows: [llength [dbGet top.fPlan.rows]]  site: [dbGet top.fPlan.rows.site.name -u]"
puts "core box: [dbGet top.fPlan.coreBox]"
puts "die box: [dbGet top.fPlan.box]"
puts "=== tech"
puts "sites: [dbGet head.sites.name]"
foreach l [dbGet -p head.layers.type routing] { puts "layer [dbGet $l.name] dir=[dbGet $l.direction] pitchX=[dbGet $l.pitchX] pitchY=[dbGet $l.pitchY] offX=[dbGet $l.offsetX] offY=[dbGet $l.offsetY]" }
puts "=== tracks (created by floorPlan from the LEF pitches/offsets)"
puts "track patterns: [llength [get_db track_patterns]]"
foreach t [get_db track_patterns] { puts "track [get_db $t .layers] [get_db $t .direction] start=[get_db $t .start] step=[get_db $t .step] num=[get_db $t .num_tracks]" }
puts "=== tracks after explicit LEF pitches (build/ndm/sky130_tracks_innovus.tcl)"
source $HERE/build/ndm/sky130_tracks_innovus.tcl
foreach t [get_db track_patterns] { puts "track2 [get_db $t .layers] [get_db $t .direction] start=[get_db $t .start] step=[get_db $t .step] num=[get_db $t .num_tracks]" }
puts "=== rows"
puts "row sites: [dbGet top.fPlan.rows.site.name -u]  orients: [dbGet top.fPlan.rows.orient -u]  count: [llength [dbGet top.fPlan.rows]]"
puts "=== PG nets"
foreach n [dbGet top.pgNets.name] { puts "pgnet $n" }
globalNetConnect VPWR -type pgpin -pin VPWR -all -override
globalNetConnect VGND -type pgpin -pin VGND -all -override
globalNetConnect VPWR -type pgpin -pin vccd1 -all -override
globalNetConnect VGND -type pgpin -pin vssd1 -all -override
puts "=== check_design"
check_design -type {all}
puts "=== analysis views"
puts "setup views: [all_setup_analysis_views]  hold views: [all_hold_analysis_views]"
puts "=== SRAM macro cell"
puts "sram class: [dbGet [dbGet -p head.allCells.name sky130_sram_1kbyte_1rw1r_32x256_8].subClass]  size: [dbGet [dbGet -p head.allCells.name sky130_sram_1kbyte_1rw1r_32x256_8].size]"
puts "=== write DEF for the RedHawk load test"
placeInstance u_sram 50 50 R0 -fixed
placeInstance u_ff 600 500 R0
defOut -floorplan -netlist $HERE/build/work/innovus/link_trivial_fp.def
exit
