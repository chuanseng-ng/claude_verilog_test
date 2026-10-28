# gds_abs_extract.tcl -- Magic extraction of a layout GDS for LVS, std cells + SRAM as LEF abstracts (black boxes with pins),
# routing / vias / pins read from the GDS. Run through in_container/magic_step.sh with an env file like LibreLane's.
# Differences from librelane/scripts/magic/extract_spice.tcl: geometry source is the GDS (not DEF); cells keep their LEF abstract
# (gds noduplicates true); PG labels from a file, because an ICC2 GDS has no VPWR/VGND text; "port makeall" turns labels into ports.
source $::env(SCRIPTS_DIR)/magic/common/read.tcl
set f [open $::env(STEP_DIR)/cif_scale.txt "w"]; puts $f "[magic::i2u 1]"; close $f
read_tech_lef
read_pdk_lef
read_extra_lef
gds noduplicates true
gds rescale true
puts "> gds read $::env(CURRENT_GDS)"
gds read $::env(CURRENT_GDS)
load $::env(DESIGN_NAME)
select top cell
# Magic does not flag GDS text as ports (`port makeall` does nothing for it), and a top subckt without port-flagged labels has no pins.
# pin_ports.tcl (scripts/gds_pin_ports.py, from the GDS text) does `findlabel NAME; port make` for every pin text.
if {[info exists ::env(PIN_PORTS)] && [file exists $::env(PIN_PORTS)]} { source $::env(PIN_PORTS) }
if {[info exists ::env(PG_LABELS)] && [file exists $::env(PG_LABELS)]} {
    source $::env(PG_LABELS)
    foreach {net x y} $::pg_labels {
        box ${x}um ${y}um ${x}um ${y}um
        label $net center m4
        puts "pg label $net at $x $y um (met4)"
    }
}
select top cell
port makeall
set backup $::env(PWD)
set extdir $::env(STEP_DIR)/extraction
file mkdir $extdir
cd $extdir
extract do local
extract no capacitance
extract no coupling
extract no resistance
extract no adjust
extract unique
extract
ext2spice lvs
ext2spice -o $::env(SAVE_SPICE) $::env(DESIGN_NAME).ext
cd $backup
feedback save $::env(STEP_DIR)/feedback.txt
