# Thin wrapper: the real ASAP7 PDN grid is shared by all blocks.
# Kept per-design because PDN_CFG's `dir::` prefix resolves against DESIGN_DIR,
# and a `dir::../` form has not been verified against LibreLane's preprocessor.
source [file join [file dirname [file normalize [info script]]] .. pdn_asap7_orfs.tcl]
