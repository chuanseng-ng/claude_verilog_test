* Test BSIM4 (level=14) with standard 180nm-equivalent params to verify model works
* Then we'll know if the issue is model parameters or model level

.model ntest nmos level=14 version=4.5
+ toxe=4e-9
+ vth0=0.5
+ u0=0.04
+ vsat=8e4
+ cgso=3e-10 cgdo=3e-10 cgbo=0
+ tnom=27 lint=0 wint=0
+ nsub=1e17 nsd=1e20
+ cdsc=2.4e-4 cit=0
+ a0=1 b0=0 b1=0
+ rdsw=200
+ pclm=0.1 pscbe1=4e8 pscbe2=1e-7
+ k1=0.5 k2=0 epsrox=3.9

VDD vdd 0 DC 1.8
MN1 d1 g1 0 0 ntest w=1u l=180n
Vg1 g1 0 DC 0.9
Vd1 d1 0 DC 0.9

.dc Vg1 0 1.8 0.1

.print dc i(Vd1)

.end
