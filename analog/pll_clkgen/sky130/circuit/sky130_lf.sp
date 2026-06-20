* ============================================================
* Sky130 PLL Loop Filter — 3rd-order passive RC
* C1=17.5pF, R2=272.73kΩ, C2=1.75pF, R3=90.91kΩ, C3=0.175pF
* Ports: in out vss
* in = CP output node
* out = VCO vtune node
* Topology: in→C1→vss; in→R2→mid→C2→vss; in→R3→out→C3→vss
* Loop BW=1 MHz, PM=60°
* ============================================================
.subckt sky130_lf in out vss

* C1 shunt (main integrating cap; dominant filter pole)
* In sky130: MIM cap C3 flavor, max ~5pF/cell → use 4 in parallel
* Modeled as ideal capacitor for netlist
C1_lf in vss 17.5p

* R2-C2 zero-creating branch
R2_lf in lf_mid 272.73k
C2_lf lf_mid vss 1.75p

* R3-C3 third-order pole (reference spur rejection)
R3_lf in out 90.91k
C3_lf out vss 0.175p

.ends sky130_lf
