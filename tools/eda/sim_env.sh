# tools/eda/sim_env.sh -- source me (bash/sh/zsh):  source tools/eda/sim_env.sh
#
# Activates .venv-eda/ (python3.11 + cocotb 1.x; build it with `make eda-venv`),
# puts the Xcelium/IMC tool dirs on PATH, and sanity-checks the commercial
# simulator environment (VCS_HOME / XCELIUM_HOME / licence variables).
# Warnings go to stderr; nothing here aborts the caller's shell.
#
# Optional: SIM_ENV_QUIET=1 silences the OK lines (warnings still print).

_se_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_se_root="$(cd "$_se_here/../.." && pwd)"
_se_venv="${EDA_VENV:-$_se_root/.venv-eda}"
_se_info() { [ -n "${SIM_ENV_QUIET:-}" ] || echo "sim_env: $*"; }
_se_warn() { echo "sim_env: WARNING: $*" >&2; }

# --- python / cocotb venv ---------------------------------------------------
if [ -f "$_se_venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$_se_venv/bin/activate"
  _se_info "venv $_se_venv ($(python -V 2>&1); cocotb $(python -c 'import cocotb;print(cocotb.__version__)' 2>/dev/null || echo '?'))"
else
  _se_warn "$_se_venv missing -- run 'make eda-venv' in $_se_root"
fi

# cocotb's makefiles locate the interpreter via `which python3`; the venv one wins now.
# Tell this repo's Makefiles (SIM_PYTHON3 pattern from CI) to use it explicitly too.
export SIM_PYTHON3="${SIM_PYTHON3:-$(command -v python3 2>/dev/null)}"

# --- VCS --------------------------------------------------------------------
if [ -z "${VCS_HOME:-}" ]; then
  _se_warn "VCS_HOME is not set -- SIM=vcs will not work (cocotb's makefile needs \$VCS_HOME/include/vpi_user.h)"
elif [ ! -x "$VCS_HOME/bin/vcs" ]; then
  _se_warn "VCS_HOME=$VCS_HOME has no bin/vcs"
else
  command -v vcs >/dev/null 2>&1 || export PATH="$VCS_HOME/bin:$PATH"
  _se_info "VCS_HOME=$VCS_HOME"
fi
if [ -z "${SNPSLMD_LICENSE_FILE:-}${LM_LICENSE_FILE:-}" ]; then
  _se_warn "neither SNPSLMD_LICENSE_FILE nor LM_LICENSE_FILE is set -- VCS will fail to check out a licence"
else
  _se_info "Synopsys licence: ${SNPSLMD_LICENSE_FILE:-$LM_LICENSE_FILE}"
fi

# --- Xcelium (+ imc) ----------------------------------------------------------
if [ -z "${XCELIUM_HOME:-}" ]; then
  _se_warn "XCELIUM_HOME is not set -- SIM=xcelium will not work"
elif [ ! -x "$XCELIUM_HOME/tools/bin/xrun" ]; then
  _se_warn "XCELIUM_HOME=$XCELIUM_HOME has no tools/bin/xrun"
else
  for _d in "$XCELIUM_HOME/tools/bin" "$XCELIUM_HOME/tools/xcelium/bin" "$XCELIUM_HOME/bin"; do
    case ":$PATH:" in *":$_d:"*) ;; *) [ -d "$_d" ] && export PATH="$_d:$PATH" ;; esac
  done
  _se_info "XCELIUM_HOME=$XCELIUM_HOME"
  if ! command -v imc >/dev/null 2>&1; then
    _se_warn "imc not found under \$XCELIUM_HOME/tools/bin (IMC is a separate Cadence install on some sites) -- Xcelium coverage can be collected but not reported with imc"
  fi
fi
if [ -z "${CDS_LIC_FILE:-}${LM_LICENSE_FILE:-}" ]; then
  _se_warn "neither CDS_LIC_FILE nor LM_LICENSE_FILE is set -- Xcelium will fail to check out a licence"
else
  _se_info "Cadence licence: ${CDS_LIC_FILE:-$LM_LICENSE_FILE}"
fi

# --- coverage tools ---------------------------------------------------------
command -v urg >/dev/null 2>&1 || { [ -n "${VCS_HOME:-}" ] && [ -x "$VCS_HOME/bin/urg" ] && export PATH="$VCS_HOME/bin:$PATH"; }
command -v urg >/dev/null 2>&1 || _se_warn "urg not on PATH (VCS coverage reporting)"

# --- host compiler ------------------------------------------------------------
# cocotb 1.9 builds its VPI shim with the system g++ (here 8.5 -- fine, C++11/14).
_se_info "g++ $(g++ -dumpfullversion 2>/dev/null || echo '?')"
unset _se_here _se_root _se_venv _se_d
