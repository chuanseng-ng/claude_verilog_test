#!/bin/bash
# wait_then_b7.sh <icc2|innovus> -- wait for the arm's b7 implementation chain to write its final out/ (icc2: markers/b7_08_write_verilog.done; innovus: b6done/07_restream.done), then run chain_b7_all.sh <arm>.
cd "$(dirname "$0")"
case $1 in
  icc2) F=../impl/icc2/runs/b7_icc2/markers/b7_08_write_verilog.done ;;
  innovus) F=../impl/innovus/runs/b7_innovus/b6done/07_restream.done ;;
esac
until [ -f $F ]; do sleep 30; done
exec ./chain_b7_all.sh $1
