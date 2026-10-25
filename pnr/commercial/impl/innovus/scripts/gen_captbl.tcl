# gen_captbl.tcl -- Innovus capTable from the authored Sky130 ICT (stop-gap while Techgen's qrcTechFile is unfinished).
set HERE $::env(HERE); set RUN $::env(RUN)
generateCapTbl -ict $HERE/build/tech/ict/sky130A_nom.ict -output $RUN/sky130A_nom.captbl
exit
