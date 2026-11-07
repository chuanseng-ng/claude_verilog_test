# gen_captbl6.tcl -- Innovus capTable (6 metal layers: M1=li1 .. M6=met5) from the tuned ICT.  env: HERE CORNER OUTDIR
setMultiCpuUsage -localCpu 2
set c $::env(CORNER)
generateCapTbl -ict $::env(OUTDIR)/sky130A_${c}_li1m1.ict -output $::env(OUTDIR)/sky130A_${c}_li1m1.captbl
exit
