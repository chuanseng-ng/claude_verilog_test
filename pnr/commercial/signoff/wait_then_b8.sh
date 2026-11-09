#!/bin/bash
# wait_then_b8.sh <icc2|innovus> -- wait for the arm's b8 implementation to write its final out/, then run chain_b8_all.sh <arm>.
cd "$(dirname "$0")"
case $1 in
  icc2) F=../impl/icc2/runs/b8_icc2/markers/b8_08_write_verilog.done ;;
  innovus) F=../impl/innovus/runs/b8_innovus/b6done/07_restream.done ;;
esac
until [ -f $F ]; do sleep 60; done
exec ./chain_b8_all.sh $1
