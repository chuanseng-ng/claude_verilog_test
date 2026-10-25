# tools/eda/pd_env.sh -- source me (bash/sh/zsh):  source tools/eda/pd_env.sh
#
# Physical-design environment for the Sky130 commercial-vs-open comparison
# (DC->ICC2, Genus->Innovus, OpenROAD; StarRC->PrimeTime judge; Formality/Conformal
# LEC; RedHawk IR; Magic/KLayout/Netgen DRC/LVS).  Twin of sim_env.sh.
#
# Exports PDK_ROOT / PDK / STD_CELL_LIBRARY and one variable per key PDK view,
# puts the ciel venv on PATH (for `ciel`), checks licence variables and defines
# `pd_env_check`, which runs each binary's licence-free version probe.
# Warnings go to stderr; nothing here aborts the caller's shell.
#
# Optional: PD_ENV_QUIET=1 silences the OK lines.
#           PD_ENV_PROBE_TIMEOUT=<s> per-tool probe timeout for pd_env_check (default 120).

_pe_info() { [ -n "${PD_ENV_QUIET:-}" ] || echo "pd_env: $*"; }
_pe_warn() { echo "pd_env: WARNING: $*" >&2; }

# --- PDK (open_pdks 0fe599b2..., the rev LibreLane 2.4.13 pins; fetched with ciel) --------
export PDK_ROOT="${PDK_ROOT:-$HOME/pdk}"
export PDK="${PDK:-sky130A}"
export STD_CELL_LIBRARY="${STD_CELL_LIBRARY:-sky130_fd_sc_hd}"
export PDK_VERSION_EXPECTED="0fe599b2afb6708d281543108caf8310912f54af"

export PDK_DIR="$PDK_ROOT/$PDK"
export SKY130_REF="$PDK_DIR/libs.ref"
export SKY130_TECH="$PDK_DIR/libs.tech"
export SKY130_HD="$SKY130_REF/$STD_CELL_LIBRARY"
export SKY130_HD_LIB="$SKY130_HD/lib"                      # *.lib, e.g. sky130_fd_sc_hd__tt_025C_1v80.lib
export SKY130_HD_LIB_TT="$SKY130_HD_LIB/${STD_CELL_LIBRARY}__tt_025C_1v80.lib"
export SKY130_HD_LIB_SS="$SKY130_HD_LIB/${STD_CELL_LIBRARY}__ss_100C_1v60.lib"
export SKY130_HD_LIB_FF="$SKY130_HD_LIB/${STD_CELL_LIBRARY}__ff_n40C_1v95.lib"
export SKY130_HD_LEF="$SKY130_HD/lef/${STD_CELL_LIBRARY}.lef"
export SKY130_HD_TLEF="$SKY130_HD/techlef/${STD_CELL_LIBRARY}__nom.tlef"
export SKY130_HD_TLEF_MIN="$SKY130_HD/techlef/${STD_CELL_LIBRARY}__min.tlef"
export SKY130_HD_TLEF_MAX="$SKY130_HD/techlef/${STD_CELL_LIBRARY}__max.tlef"
export SKY130_HD_GDS="$SKY130_HD/gds/${STD_CELL_LIBRARY}.gds"
export SKY130_HD_VERILOG="$SKY130_HD/verilog/${STD_CELL_LIBRARY}.v"
export SKY130_HD_PRIMITIVES="$SKY130_HD/verilog/primitives.v"
export SKY130_HD_CDL="$SKY130_HD/cdl/${STD_CELL_LIBRARY}.cdl"
export SKY130_HD_SPICE="$SKY130_HD/spice"
export SKY130_SRAM="$SKY130_REF/sky130_sram_macros"        # lef/ gds/ lib/ verilog/ spice/ mag/ maglef/
export SKY130_SRAM_1K_NAME="sky130_sram_1kbyte_1rw1r_32x256_8"
export SKY130_SRAM_1K_LEF="$SKY130_SRAM/lef/$SKY130_SRAM_1K_NAME.lef"
export SKY130_SRAM_1K_GDS="$SKY130_SRAM/gds/$SKY130_SRAM_1K_NAME.gds"
export SKY130_SRAM_1K_LIB="$SKY130_SRAM/lib/${SKY130_SRAM_1K_NAME}_TT_1p8V_25C.lib"
export SKY130_SRAM_1K_SPICE="$SKY130_SRAM/spice/$SKY130_SRAM_1K_NAME.spice"
# extraction / sign-off decks shipped in the PDK (ITF/ICT for StarRC/Quantus are NOT shipped; author later)
export SKY130_OPENRCX_NOM="$SKY130_TECH/openlane/rules.openrcx.${PDK}.nom.spef_extractor"
export SKY130_OPENRCX_MIN="$SKY130_TECH/openlane/rules.openrcx.${PDK}.min.spef_extractor"
export SKY130_OPENRCX_MAX="$SKY130_TECH/openlane/rules.openrcx.${PDK}.max.spef_extractor"
export SKY130_MAGIC_TECH="$SKY130_TECH/magic/${PDK}.tech"
export SKY130_MAGICRC="$SKY130_TECH/magic/${PDK}.magicrc"
export SKY130_NETGEN_SETUP="$SKY130_TECH/netgen/${PDK}_setup.tcl"
export SKY130_KLAYOUT_DRC="$SKY130_TECH/klayout/drc/${PDK}_mr.drc"
export SKY130_KLAYOUT_LVS="$SKY130_TECH/klayout/lvs/sky130.lvs"
export SKY130_KLAYOUT_TECH="$SKY130_TECH/klayout/tech/${PDK}.lyt"
export SKY130_OPENLANE_HD_CFG="$SKY130_TECH/openlane/$STD_CELL_LIBRARY/config.tcl"

if [ -d "$PDK_DIR/libs.ref" ]; then
  _pe_real="$(readlink -f "$PDK_DIR" 2>/dev/null)"
  case "$_pe_real" in
    *"$PDK_VERSION_EXPECTED"*) _pe_info "PDK $PDK at $PDK_DIR (open_pdks $PDK_VERSION_EXPECTED)" ;;
    *) _pe_warn "PDK $PDK_DIR resolves to $_pe_real, expected open_pdks $PDK_VERSION_EXPECTED" ;;
  esac
else
  _pe_warn "$PDK_DIR/libs.ref missing -- fetch with: ciel enable --pdk-family sky130 --pdk-root $PDK_ROOT -l sky130_fd_sc_hd -l sky130_fd_pr -l sky130_sram_macros $PDK_VERSION_EXPECTED"
fi

# --- ciel venv (python3.11; NOT Calibre's bundled python3.8) ------------------------------
_pe_venv="${PD_PDK_VENV:-$HOME/.venvs/pdk}"
if [ -x "$_pe_venv/bin/ciel" ]; then
  case ":$PATH:" in *":$_pe_venv/bin:"*) ;; *) export PATH="$_pe_venv/bin:$PATH" ;; esac
else
  _pe_warn "$_pe_venv/bin/ciel missing -- /bin/python3.11 -m venv $_pe_venv && $_pe_venv/bin/pip install ciel"
fi

# --- LibreLane container (podman, rootless) and sv2v ------------------------------------------
# The repo's pinned flow is LibreLane 2.4.13-2-g3562a8d (patched live install, not on this host);
# the nearest image is ghcr.io/librelane/librelane:2.4.13 (nix-built: librelane, yosys 0.46, openroad,
# magic 8.3.489, netgen 1.5.278, klayout 0.29.4, opensta; NO sv2v).  sv2v needs glibc>=2.34, so
# SV2V points at a wrapper that runs it inside that image (pnr/Makefile honours `SV2V=`).
export LIBRELANE_IMAGE="${LIBRELANE_IMAGE:-ghcr.io/librelane/librelane:2.4.13}"
[ -x "$HOME/tools/sv2v-0.0.13/sv2v-podman" ] && export SV2V="${SV2V:-$HOME/tools/sv2v-0.0.13/sv2v-podman}"
# librelane_run <librelane args...>   e.g. librelane_run --pdk-root $PDK_ROOT --pdk sky130A pnr/sky130/cpu/config.json
librelane_run() {
  podman run --rm -i -v "$HOME:$HOME" -v "$PDK_ROOT:$PDK_ROOT" -e PDK_ROOT="$PDK_ROOT" -e PDK="$PDK" \
    -e STD_CELL_LIBRARY="$STD_CELL_LIBRARY" -w "$PWD" "$LIBRELANE_IMAGE" librelane "$@"
}

# --- licences -------------------------------------------------------------------------------
[ -n "${SNPSLMD_LICENSE_FILE:-}${LM_LICENSE_FILE:-}" ] && _pe_info "Synopsys licence: ${SNPSLMD_LICENSE_FILE:-$LM_LICENSE_FILE}" || _pe_warn "no SNPSLMD_LICENSE_FILE/LM_LICENSE_FILE (Synopsys DC/ICC2/PT/StarRC/FM)"
[ -n "${CDS_LIC_FILE:-}${LM_LICENSE_FILE:-}" ] && _pe_info "Cadence licence: ${CDS_LIC_FILE:-$LM_LICENSE_FILE}" || _pe_warn "no CDS_LIC_FILE/LM_LICENSE_FILE (Genus/Innovus/Quantus/Conformal)"
[ -n "${ANSYSLMD_LICENSE_FILE:-}${ANSYS_LICENSE_FILE:-}${APACHEDA_LICENSE_FILE:-}" ] && _pe_info "Ansys licence: ${ANSYSLMD_LICENSE_FILE:-${ANSYS_LICENSE_FILE:-$APACHEDA_LICENSE_FILE}}" || _pe_warn "no ANSYSLMD_LICENSE_FILE/APACHEDA_LICENSE_FILE (RedHawk)"

# --- pd_env_check: licence-free version probe of every tool ----------------------------------
# Usage: pd_env_check            (all tools)      pd_env_check dc_shell genus   (subset)
# Each probe runs under `timeout` with stdin from /dev/null; a launcher can take >60 s cold
# (first start after a reboot), hence the 120 s default.  Prints one line per tool:
#   OK/SLOW/MISSING <tool> <first line of version output>.  Never leaves a process behind.
pd_env_check() {
  local t="${PD_ENV_PROBE_TIMEOUT:-120}" spec tool args out want rcode=0
  local -a specs=(
    "dc_shell|-version"   "icc2_shell|-version"  "pt_shell|-version"  "fm_shell|-version"
    "lc_shell|-version"   "fc_shell|-version"    "StarXtract|-v"
    "genus|-version"      "innovus|-version"     "quantus|-version"   "lec|-version"
    "redhawk|-version"
    "magic|--version"     "netgen|-batch"        "klayout|-v"
    "yosys|-V"            "openroad|-version"    "sta|-version"       "sv2v|--version"
    "podman|--version"    "ciel|--version"
  )
  [ "$#" -gt 0 ] && want=" $* " || want=""
  for spec in "${specs[@]}"; do
    tool="${spec%%|*}"; args="${spec#*|}"
    [ -n "$want" ] && case "$want" in *" $tool "*) ;; *) continue ;; esac
    if ! command -v "$tool" >/dev/null 2>&1; then printf '%-8s %-11s %s\n' MISSING "$tool" "(not on PATH)"; continue; fi
    out="$(timeout "$t" "$tool" $args </dev/null 2>&1 | grep -v '^[-[:space:]]*$' | head -1 | cut -c1-110)"
    if [ -n "$out" ]; then printf '%-8s %-11s %s\n' OK "$tool" "$out"
    else printf '%-8s %-11s %s\n' SLOW "$tool" "(no output in ${t}s)"; rcode=1; fi
  done
  return $rcode
}
_pe_info "run pd_env_check to probe tool versions (licence-free)"
unset _pe_venv _pe_real
