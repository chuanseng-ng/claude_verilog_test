#!/usr/bin/env bash
set -u
cd /nobackup/claude_sim_build/dft_stage0/qg
OSSL_LIB=$(nix build nixpkgs#openssl.out --no-link --print-out-paths)
OSSL_DEV=$(nix build nixpkgs#openssl.dev --no-link --print-out-paths)
export OPENSSL_LIB_DIR=$OSSL_LIB/lib OPENSSL_INCLUDE_DIR=$OSSL_DEV/include
export CARGO_HOME=/nobackup/claude_sim_build/dft_stage0/qg/cargo
nix shell nixpkgs#cargo nixpkgs#rustc nixpkgs#gcc nixpkgs#pkg-config nixpkgs#cmake nixpkgs#curl nixpkgs#gnumake -c \
  cargo install quaigh --root /nobackup/claude_sim_build/dft_stage0/qg/root > install4.log 2>&1
echo rc=$? >> install4.log
