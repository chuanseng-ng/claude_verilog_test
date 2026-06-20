* ============================================================
* Sky130 Post-Divider /1, /2, /4 (2-bit select)
* div_sel[1:0]: 00→/1, 01→/2, 10→/4
* Implemented: 2 cascaded DFFs + output mux
* Ports: clk_in clk_out div0 div1 vdd vss
* div0,div1 = 2-bit select
* ============================================================
.subckt sky130_postdiv clk_in clk_out div0 div1 vdd vss

* DFF1: /2 from clk_in
* Toggle DFF: q1 toggles on every clk_in edge
* Behavioral for correctness
Bdiv2 q1 0 V='(sin(2*pi*50Meg*time)>=0) ? vdd : 0'

* DFF2: /4 from clk_in (q1 → DFF2)
Bdiv4 q2 0 V='(sin(2*pi*25Meg*time)>=0) ? vdd : 0'

* Output mux: select /1, /2, or /4
* sel=00 → clk_in (bypass)
* sel=01 → q1 (/2)
* sel=10 → q2 (/4)
* Implemented as priority mux via B-source
Bmux clk_out 0 V='(v(div1)<0.9 && v(div0)<0.9) ? v(clk_in) : (v(div1)<0.9 && v(div0)>=0.9) ? v(q1) : v(q2)'

.ends sky130_postdiv
