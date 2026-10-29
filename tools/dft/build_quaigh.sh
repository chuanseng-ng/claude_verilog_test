#!/usr/bin/env bash
# build_quaigh.sh [patched]
#   (no arg)  stock quaigh 0.0.6 from crates.io into /nobackup/claude_sim_build/dft_stage0/qg/root (DFT Stage 0 / j41m.15)
#   patched   quaigh 0.0.6+cvt1: the same crate source with tools/dft/atpg/quaigh/*.patch applied (bead j41m.18: sparse
#             pattern-detection rows, so the fabric cut fits the 12 GB box), into /nobackup/claude_sim_build/j41m18/qroot.
#             Needs the stock build first (it fills the cargo registry the source is copied from).
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd /nobackup/claude_sim_build/dft_stage0/qg
OSSL_LIB=$(nix build nixpkgs#openssl.out --no-link --print-out-paths)
OSSL_DEV=$(nix build nixpkgs#openssl.dev --no-link --print-out-paths)
export OPENSSL_LIB_DIR=$OSSL_LIB/lib OPENSSL_INCLUDE_DIR=$OSSL_DEV/include
export CARGO_HOME=/nobackup/claude_sim_build/dft_stage0/qg/cargo
NIX_TOOLS=(nixpkgs#cargo nixpkgs#rustc nixpkgs#gcc nixpkgs#pkg-config nixpkgs#cmake nixpkgs#curl nixpkgs#gnumake)

if [ "${1:-}" != patched ]; then
  nix shell "${NIX_TOOLS[@]}" -c \
    cargo install quaigh --root /nobackup/claude_sim_build/dft_stage0/qg/root > install4.log 2>&1
  echo rc=$? >> install4.log
  exit 0
fi

PW=/nobackup/claude_sim_build/j41m18
src=$(ls -d "$CARGO_HOME"/registry/src/*/quaigh-0.0.6 | head -1)
[ -d "$src" ] || { echo "quaigh-0.0.6 source not in $CARGO_HOME/registry: run the stock build first" >&2; exit 1; }
mkdir -p "$PW/src"
rm -rf "$PW/src/quaigh-0.0.6"
cp -r "$src" "$PW/src/quaigh-0.0.6"
for p in "$here"/atpg/quaigh/*.patch; do
  patch -d "$PW/src/quaigh-0.0.6" -p1 --forward < "$p" || { echo "patch failed: $p" >&2; exit 1; }
done
cd "$PW/src/quaigh-0.0.6"
nix shell "${NIX_TOOLS[@]}" -c cargo install --path . --root "$PW/qroot" > "$PW/build.log" 2>&1
rc=$?
echo rc=$rc >> "$PW/build.log"
[ $rc = 0 ] && "$PW/qroot/bin/quaigh" --version
exit $rc
