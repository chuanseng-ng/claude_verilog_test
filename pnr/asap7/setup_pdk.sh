#!/usr/bin/env bash
# setup_pdk.sh — Download and install the ASAP7 standard cell library for LibreLane.
#
# Sources:
#   https://github.com/The-OpenROAD-Project/asap7  (meta-repo with submodules)
#   https://github.com/The-OpenROAD-Project/asap7sc7p5t_28  (RVT cell library r28)
#   https://github.com/The-OpenROAD-Project/asap7_pdk_r1p7  (PDK tech files)
#
# Requires: python3, py7zr (pip3 install py7zr)
#
# Target layout required by ~/pdk/asap7/libs.tech/openlane/config.tcl:
#   ~/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lef/
#   ~/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/
#   ~/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/gds/
#
# Run once: bash pnr/asap7/setup_pdk.sh

set -euo pipefail

PDK_ROOT="${HOME}/pdk/asap7"
ASAP7_REF="${PDK_ROOT}/libs.ref/asap7sc7p5t_SIMPLE"
TMP_DIR="$(mktemp -d)"

echo "=== ASAP7 PDK Setup ==="
echo "Target: ${PDK_ROOT}"
echo ""

# ── Prerequisite: py7zr ─────────────────────────────────────────────────────
if ! python3 -c "import py7zr" 2>/dev/null; then
    echo "[prereq] Installing py7zr..."
    pip3 install py7zr --user
fi

# ── 1. Clone the ASAP7 meta-repo (shallow) ─────────────────────────────────
ASAP7_REPO="https://github.com/The-OpenROAD-Project/asap7.git"
echo "[1/5] Cloning ASAP7 meta-repository (shallow)..."
git clone --depth 1 "${ASAP7_REPO}" "${TMP_DIR}/asap7"

# ── 2. Fetch required submodules ────────────────────────────────────────────
echo "[2/5] Fetching submodules (asap7sc7p5t_28 + asap7_pdk_r1p7)..."
cd "${TMP_DIR}/asap7"
git submodule update --init --depth 1 asap7sc7p5t_28 asap7_pdk_r1p7
cd -

SC="${TMP_DIR}/asap7/asap7sc7p5t_28"

# ── 3. Install Technology LEF ───────────────────────────────────────────────
echo "[3/5] Installing technology LEF..."
mkdir -p "${ASAP7_REF}/lef"
cp "${SC}/techlef_misc/asap7_tech_1x_201209.lef" "${ASAP7_REF}/lef/"
# Cell abstract LEF — R = RVT
cp "${SC}/LEF/asap7sc7p5t_28_R_1x_220121a.lef" "${ASAP7_REF}/lef/asap7sc7p5t_SIMPLE_RVT_1x.lef"

# ── 4. Extract and install Liberty files (5 cell categories, RVT TT) ────────
echo "[4/5] Extracting Liberty files (RVT TT corner)..."
mkdir -p "${ASAP7_REF}/lib"
python3 << PYEOF
import py7zr, os, glob

nldm = "${SC}/LIB/NLDM"
out  = "${ASAP7_REF}/lib"
files = sorted(f for f in os.listdir(nldm) if "RVT_TT" in f and f.endswith(".7z"))
print(f"  Extracting {len(files)} files:")
for fname in files:
    fpath = os.path.join(nldm, fname)
    with py7zr.SevenZipFile(fpath, "r") as z:
        z.extractall(path=out)
    print(f"  + {fname[:-3]}")
PYEOF

# ── 5. Install GDS ──────────────────────────────────────────────────────────
echo "[5/5] Installing GDS..."
mkdir -p "${ASAP7_REF}/gds"
cp "${SC}/GDS/asap7sc7p5t_28_R_220121a.gds" "${ASAP7_REF}/gds/asap7sc7p5t_SIMPLE_RVT.gds"

# ── Cleanup ─────────────────────────────────────────────────────────────────
rm -rf "${TMP_DIR}"

# ── Verify ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Installed files ==="
echo "LEF:"
ls "${ASAP7_REF}/lef/"
echo "LIB:"
ls "${ASAP7_REF}/lib/"
echo "GDS:"
ls "${ASAP7_REF}/gds/"
echo ""

TECH_LEF="${ASAP7_REF}/lef/asap7_tech_1x_201209.lef"
TT_INVBUF="${ASAP7_REF}/lib/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib"
TT_SEQ="${ASAP7_REF}/lib/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib"

if [[ -f "${TECH_LEF}" && -f "${TT_INVBUF}" && -f "${TT_SEQ}" ]]; then
    echo "✓ Tech LEF: ${TECH_LEF}"
    echo "✓ INVBUF Liberty: ${TT_INVBUF}"
    echo "✓ SEQ Liberty: ${TT_SEQ}"
    echo ""
    echo "PDK setup complete. Run the flow with:"
    echo "  cd pnr && make librelane-asap7"
else
    echo "⚠ Some required files may be missing. Check output above."
fi
