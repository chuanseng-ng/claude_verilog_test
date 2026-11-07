# tools/eda/pd_env.csh -- source me (csh/tcsh):  source tools/eda/pd_env.csh
#
# csh twin of pd_env.sh: PDK_ROOT / PDK / STD_CELL_LIBRARY, one variable per key
# Sky130 PDK view, the ciel venv on PATH, licence-variable sanity checks, and a
# `pd_env_check` alias (csh has no functions: the alias runs the bash function from
# pd_env.sh in a sub-shell, so it also works for a subset: `pd_env_check dc_shell genus`).
# Warnings go to stderr.  PD_ENV_QUIET=1 silences the OK lines.
#
# NOTE: csh cannot locate its own path reliably when sourced non-interactively;
# if $EDA_REPO is unset this falls back to `git rev-parse --show-toplevel`, then the cwd.

if ( $?EDA_REPO ) then
  set _pe_root = "$EDA_REPO"
else
  set _pe_root = "`git rev-parse --show-toplevel`"
  if ( "$_pe_root" == "" ) set _pe_root = "$cwd"
endif
set _pe_quiet = 0
if ( $?PD_ENV_QUIET ) set _pe_quiet = 1

# --- PDK (open_pdks 0fe599b2..., the rev LibreLane 2.4.13 pins; fetched with ciel) ---
if ( ! $?PDK_ROOT ) setenv PDK_ROOT "$HOME/pdk"
if ( ! $?PDK ) setenv PDK sky130A
if ( ! $?STD_CELL_LIBRARY ) setenv STD_CELL_LIBRARY sky130_fd_sc_hd
setenv PDK_VERSION_EXPECTED 0fe599b2afb6708d281543108caf8310912f54af

setenv PDK_DIR "${PDK_ROOT}/${PDK}"
setenv SKY130_REF "${PDK_DIR}/libs.ref"
setenv SKY130_TECH "${PDK_DIR}/libs.tech"
setenv SKY130_HD "${SKY130_REF}/${STD_CELL_LIBRARY}"
setenv SKY130_HD_LIB "${SKY130_HD}/lib"
setenv SKY130_HD_LIB_TT "${SKY130_HD_LIB}/${STD_CELL_LIBRARY}__tt_025C_1v80.lib"
setenv SKY130_HD_LIB_SS "${SKY130_HD_LIB}/${STD_CELL_LIBRARY}__ss_100C_1v60.lib"
setenv SKY130_HD_LIB_FF "${SKY130_HD_LIB}/${STD_CELL_LIBRARY}__ff_n40C_1v95.lib"
setenv SKY130_HD_LEF "${SKY130_HD}/lef/${STD_CELL_LIBRARY}.lef"
setenv SKY130_HD_TLEF "${SKY130_HD}/techlef/${STD_CELL_LIBRARY}__nom.tlef"
setenv SKY130_HD_TLEF_MIN "${SKY130_HD}/techlef/${STD_CELL_LIBRARY}__min.tlef"
setenv SKY130_HD_TLEF_MAX "${SKY130_HD}/techlef/${STD_CELL_LIBRARY}__max.tlef"
setenv SKY130_HD_GDS "${SKY130_HD}/gds/${STD_CELL_LIBRARY}.gds"
setenv SKY130_HD_VERILOG "${SKY130_HD}/verilog/${STD_CELL_LIBRARY}.v"
setenv SKY130_HD_PRIMITIVES "${SKY130_HD}/verilog/primitives.v"
setenv SKY130_HD_CDL "${SKY130_HD}/cdl/${STD_CELL_LIBRARY}.cdl"
setenv SKY130_HD_SPICE "${SKY130_HD}/spice"
setenv SKY130_SRAM "${SKY130_REF}/sky130_sram_macros"
setenv SKY130_SRAM_1K_NAME sky130_sram_1kbyte_1rw1r_32x256_8
setenv SKY130_SRAM_1K_LEF "${SKY130_SRAM}/lef/${SKY130_SRAM_1K_NAME}.lef"
setenv SKY130_SRAM_1K_GDS "${SKY130_SRAM}/gds/${SKY130_SRAM_1K_NAME}.gds"
setenv SKY130_SRAM_1K_LIB "${SKY130_SRAM}/lib/${SKY130_SRAM_1K_NAME}_TT_1p8V_25C.lib"
setenv SKY130_SRAM_1K_SPICE "${SKY130_SRAM}/spice/${SKY130_SRAM_1K_NAME}.spice"
setenv SKY130_OPENRCX_NOM "${SKY130_TECH}/openlane/rules.openrcx.${PDK}.nom.spef_extractor"
setenv SKY130_OPENRCX_MIN "${SKY130_TECH}/openlane/rules.openrcx.${PDK}.min.spef_extractor"
setenv SKY130_OPENRCX_MAX "${SKY130_TECH}/openlane/rules.openrcx.${PDK}.max.spef_extractor"
setenv SKY130_MAGIC_TECH "${SKY130_TECH}/magic/${PDK}.tech"
setenv SKY130_MAGICRC "${SKY130_TECH}/magic/${PDK}.magicrc"
setenv SKY130_NETGEN_SETUP "${SKY130_TECH}/netgen/${PDK}_setup.tcl"
setenv SKY130_KLAYOUT_DRC "${SKY130_TECH}/klayout/drc/${PDK}_mr.drc"
setenv SKY130_KLAYOUT_LVS "${SKY130_TECH}/klayout/lvs/sky130.lvs"
setenv SKY130_KLAYOUT_TECH "${SKY130_TECH}/klayout/tech/${PDK}.lyt"
setenv SKY130_OPENLANE_HD_CFG "${SKY130_TECH}/openlane/${STD_CELL_LIBRARY}/config.tcl"

if ( -d "${PDK_DIR}/libs.ref" ) then
  set _pe_real = "`readlink -f ${PDK_DIR}`"
  echo "$_pe_real" | grep -qF "$PDK_VERSION_EXPECTED"
  if ( $status == 0 ) then
    if ( ! $_pe_quiet ) echo "pd_env: PDK $PDK at $PDK_DIR (open_pdks $PDK_VERSION_EXPECTED)"
  else
    echo "pd_env: WARNING: PDK $PDK_DIR resolves to $_pe_real, expected open_pdks $PDK_VERSION_EXPECTED" > /dev/stderr
  endif
else
  echo "pd_env: WARNING: ${PDK_DIR}/libs.ref missing -- ciel enable --pdk-family sky130 --pdk-root $PDK_ROOT -l sky130_fd_sc_hd -l sky130_fd_pr -l sky130_sram_macros $PDK_VERSION_EXPECTED" > /dev/stderr
endif

# --- ciel venv (python3.11; NOT Calibre's bundled python3.8) ---
if ( $?PD_PDK_VENV ) then
  set _pe_venv = "$PD_PDK_VENV"
else
  set _pe_venv = "$HOME/.venvs/pdk"
endif
if ( -x "$_pe_venv/bin/ciel" ) then
  echo ":${PATH}:" | grep -qF ":${_pe_venv}/bin:"
  if ( $status != 0 ) setenv PATH "${_pe_venv}/bin:${PATH}"
else
  echo "pd_env: WARNING: $_pe_venv/bin/ciel missing -- /bin/python3.11 -m venv $_pe_venv && $_pe_venv/bin/pip install ciel" > /dev/stderr
endif

# --- LibreLane container (podman, rootless) and sv2v (see pd_env.sh for rationale) ---
if ( ! $?LIBRELANE_IMAGE ) setenv LIBRELANE_IMAGE ghcr.io/librelane/librelane:2.4.13
if ( -x "$HOME/tools/sv2v-0.0.13/sv2v-podman" && ! $?SV2V ) setenv SV2V "$HOME/tools/sv2v-0.0.13/sv2v-podman"
alias librelane_run 'podman run --rm -i -v "$HOME":"$HOME" -v "$PDK_ROOT":"$PDK_ROOT" -e PDK_ROOT="$PDK_ROOT" -e PDK="$PDK" -e STD_CELL_LIBRARY="$STD_CELL_LIBRARY" -w "$cwd" "$LIBRELANE_IMAGE" librelane \!*'

# --- licences ---
if ( ! $?SNPSLMD_LICENSE_FILE && ! $?LM_LICENSE_FILE ) echo "pd_env: WARNING: no SNPSLMD_LICENSE_FILE/LM_LICENSE_FILE (Synopsys)" > /dev/stderr
if ( ! $?CDS_LIC_FILE && ! $?LM_LICENSE_FILE ) echo "pd_env: WARNING: no CDS_LIC_FILE/LM_LICENSE_FILE (Cadence)" > /dev/stderr
if ( ! $?ANSYSLMD_LICENSE_FILE && ! $?ANSYS_LICENSE_FILE && ! $?APACHEDA_LICENSE_FILE ) echo "pd_env: WARNING: no ANSYSLMD_LICENSE_FILE/APACHEDA_LICENSE_FILE (RedHawk)" > /dev/stderr
if ( $?SNPSLMD_LICENSE_FILE && ! $_pe_quiet ) echo "pd_env: Synopsys licence: $SNPSLMD_LICENSE_FILE"
if ( $?LM_LICENSE_FILE && ! $_pe_quiet ) echo "pd_env: Cadence licence: $LM_LICENSE_FILE"

# --- pd_env_check: licence-free version probe of every tool (runs the bash function) ---
setenv PD_ENV_SH "${_pe_root}/tools/eda/pd_env.sh"
alias pd_env_check 'bash -c "PD_ENV_QUIET=1 . $PD_ENV_SH 2>/dev/null; pd_env_check \!*"'
if ( ! $_pe_quiet ) echo "pd_env: run pd_env_check to probe tool versions (licence-free)"

unset _pe_root _pe_quiet _pe_real _pe_venv
rehash
