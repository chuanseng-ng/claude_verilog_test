#!/usr/bin/env bash
# g++ shim for nix-verilator on hosts where clang++ is unavailable.
#
# nix verilator generates Vtop.mk with CXX=clang++ and emits clang-only flags.
# This script strips those flags and delegates to g++.
#
# Flags stripped:
#   -fbracket-depth=N       clang parser limit, rejected by g++
#   -Qunused-arguments      clang silence, rejected by g++
#   -fcf-protection=none    clang-only form (g++ does accept -fcf-protection but
#                           the combination with other flags can warn)
#   -Wno-c++11-narrowing    clang-only warning name (g++ uses -Wno-narrowing)
#   -Wno-non-pod-varargs    clang-only warning
#   -Wno-overloaded-virtual clang-only warning
#   -Wno-parentheses-equality  clang-only warning
#   -Wno-constant-logical-operand  clang-only warning
#   -Wno-tautological-*     clang-only warning family
#   -include-pch <file>     clang PCH loader; dropped because Vtop.cpp has
#                           an explicit #include "Vtop__pch.h" at the top
ARGS=()
skip_next=0
for arg in "$@"; do
    [ "$skip_next" = "1" ] && { skip_next=0; continue; }
    case "$arg" in
        -fbracket-depth=*|-Qunused-arguments|-fcf-protection=*|\
        -Wno-constant-logical-operand|-Wno-tautological-bitwise-compare|\
        -Wno-tautological-type-limit-compare|\
        -Wno-c++11-narrowing|-Wno-non-pod-varargs|\
        -Wno-overloaded-virtual|-Wno-parentheses-equality) : ;;
        -include-pch) skip_next=1 ;;
        *) ARGS+=("$arg") ;;
    esac
done
exec g++ "${ARGS[@]}"
