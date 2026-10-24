# tools/eda/sim_env.csh -- source me (csh/tcsh):  source tools/eda/sim_env.csh
#
# csh twin of sim_env.sh.  Activates .venv-eda/ (python3.11 + cocotb 1.x; build
# it with `make eda-venv`), puts the Xcelium tool dirs on PATH and sanity-checks
# VCS_HOME / XCELIUM_HOME / licence variables.  Warnings go to stderr.
#
# NOTE: csh cannot locate its own path reliably when sourced non-interactively;
# if $EDA_REPO is unset this script falls back to `git rev-parse --show-toplevel`
# from the current directory, then to the cwd.

if ( $?EDA_REPO ) then
  set _se_root = "$EDA_REPO"
else
  set _se_root = "`git rev-parse --show-toplevel`"
  if ( "$_se_root" == "" ) set _se_root = "$cwd"
endif
if ( $?EDA_VENV ) then
  set _se_venv = "$EDA_VENV"
else
  set _se_venv = "$_se_root/.venv-eda"
endif
set _se_quiet = 0
if ( $?SIM_ENV_QUIET ) set _se_quiet = 1

# --- python / cocotb venv ---------------------------------------------------
if ( -f "$_se_venv/bin/activate.csh" ) then
  # activate.csh reads $prompt, which is unset in non-interactive shells
  if ( ! $?prompt ) set prompt = ""
  source "$_se_venv/bin/activate.csh"
  if ( ! $_se_quiet ) echo "sim_env: venv $_se_venv (`python -V |& cat`)"
else
  echo "sim_env: WARNING: $_se_venv missing -- run 'make eda-venv' in $_se_root" > /dev/stderr
endif
setenv SIM_PYTHON3 "`which python3`"
# cocotb logs non-ASCII test docstrings; an ASCII locale makes every such log line raise UnicodeEncodeError.
setenv PYTHONIOENCODING utf-8
setenv LC_ALL C.UTF-8

# --- VCS --------------------------------------------------------------------
if ( ! $?VCS_HOME ) then
  echo "sim_env: WARNING: VCS_HOME is not set -- SIM=vcs will not work" > /dev/stderr
else if ( ! -x "$VCS_HOME/bin/vcs" ) then
  echo "sim_env: WARNING: VCS_HOME=$VCS_HOME has no bin/vcs" > /dev/stderr
else
  which vcs >& /dev/null
  if ( $status != 0 ) setenv PATH "${VCS_HOME}/bin:${PATH}"
  if ( ! $_se_quiet ) echo "sim_env: VCS_HOME=$VCS_HOME"
endif
if ( ! $?SNPSLMD_LICENSE_FILE && ! $?LM_LICENSE_FILE ) then
  echo "sim_env: WARNING: neither SNPSLMD_LICENSE_FILE nor LM_LICENSE_FILE set -- VCS licence checkout will fail" > /dev/stderr
else if ( $?SNPSLMD_LICENSE_FILE ) then
  if ( ! $_se_quiet ) echo "sim_env: Synopsys licence: $SNPSLMD_LICENSE_FILE"
endif

# --- Xcelium (+ imc) ----------------------------------------------------------
if ( ! $?XCELIUM_HOME ) then
  echo "sim_env: WARNING: XCELIUM_HOME is not set -- SIM=xcelium will not work" > /dev/stderr
else if ( ! -x "$XCELIUM_HOME/tools/bin/xrun" ) then
  echo "sim_env: WARNING: XCELIUM_HOME=$XCELIUM_HOME has no tools/bin/xrun" > /dev/stderr
else
  foreach _d ( "$XCELIUM_HOME/tools/bin" "$XCELIUM_HOME/tools/xcelium/bin" "$XCELIUM_HOME/bin" )
    echo ":${PATH}:" | grep -qF ":${_d}:"
    if ( $status != 0 && -d "$_d" ) setenv PATH "${_d}:${PATH}"
  end
  if ( ! $_se_quiet ) echo "sim_env: XCELIUM_HOME=$XCELIUM_HOME"
  which imc >& /dev/null
  if ( $status != 0 ) echo "sim_env: WARNING: imc not found under XCELIUM_HOME/tools/bin (separate Cadence install on some sites)" > /dev/stderr
endif
if ( ! $?CDS_LIC_FILE && ! $?LM_LICENSE_FILE ) then
  echo "sim_env: WARNING: neither CDS_LIC_FILE nor LM_LICENSE_FILE set -- Xcelium licence checkout will fail" > /dev/stderr
else if ( $?CDS_LIC_FILE ) then
  if ( ! $_se_quiet ) echo "sim_env: Cadence licence: $CDS_LIC_FILE"
endif

which urg >& /dev/null
if ( $status != 0 ) echo "sim_env: WARNING: urg not on PATH (VCS coverage reporting)" > /dev/stderr

unset _se_root _se_venv _se_quiet _d
rehash
