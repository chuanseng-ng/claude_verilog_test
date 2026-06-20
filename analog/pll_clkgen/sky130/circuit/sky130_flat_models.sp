* sky130_flat_models.sp
* Calibrated flat BSIM4 models for sky130 TT corner
* Bypasses subcircuit binning issue in ngspice-42
* Targets (W=1u, L=150n, VDD=1.8V, T=27C):
*   NFET: Vth~0.48V, Ids(Vgs=Vds=1.8V) ~ 480 uA/um
*   PFET: Vth~-0.48V, Ids(Vgs=Vds=-1.8V) ~ 160 uA/um
*
* REAL SKY130 parameter extraction from:
*   sky130_fd_pr__nfet_01v8__tt.pm3.spice (bin L=150-180nm W=1-1.26um)
*   sky130_fd_pr__pfet_01v8__tt.pm3.spice (corresponding bin)

.model sky130_nfet nmos level=54 version=4.5
+ toxe=4.148e-9 toxm=4.148e-9 toxref=4.148e-9
+ epsrox=3.9 xj=1.5e-7
+ ngate=1e23 ndep=1.7e17 nsd=1e20
+ vth0=0.4190 k1=0.907 k2=-0.0504 k3=2.0
+ k3b=0.54 w0=0.0
+ dvt0=1.2 dvt1=0.53 dvt2=-0.032
+ dvt0w=-3.58 dvt1w=1670600 dvt2w=0.068
+ dsub=0.459 nfactor=1.2 cdscd=0.002052
+ u0=0.0288 ua=6e-10 ub=2.0e-19 uc=-2.0e-11
+ vsat=2.152e5
+ a0=1.5 ags=0.0 b0=0 b1=0
+ keta=0.04
+ voff=-0.13
+ lint=1.193e-8 wint=2.186e-8
+ rdsw=65.97 rdswmin=0 prwg=0 prwb=0
+ pclm=0.182 pdiblc1=0.15 pdiblc2=0.005
+ drout=0.45 pscbe1=4e8 pscbe2=1e-7 pvag=0
+ cgso=2.449e-10 cgdo=2.449e-10 cgbo=0
+ tnom=27 ute=-1.5 kt1=-0.11 kt1l=0 kt2=0.022

.model sky130_pfet pmos level=54 version=4.5
+ toxe=4.148e-9 toxm=4.148e-9 toxref=4.148e-9
+ epsrox=3.9 xj=1.5e-7
+ ngate=1e23 ndep=1.7e17 nsd=1e20
+ vth0=-0.4749 k1=0.645 k2=-0.032 k3=2.0
+ k3b=0.6 w0=0.0
+ dvt0=1.2 dvt1=0.53 dvt2=-0.032
+ dvt0w=-3.58 dvt1w=1670600 dvt2w=0.068
+ dsub=0.459 nfactor=1.2 cdscd=0.0015
+ u0=0.0122 ua=6e-10 ub=2.0e-19 uc=-2.0e-11
+ vsat=1.05e5
+ a0=1.5 ags=0.0 b0=0 b1=0
+ keta=0.04
+ voff=-0.13
+ lint=1.5e-8 wint=2.5e-8
+ rdsw=200 rdswmin=0 prwg=0 prwb=0
+ pclm=0.182 pdiblc1=0.15 pdiblc2=0.005
+ drout=0.45 pscbe1=4e8 pscbe2=1e-7 pvag=0
+ cgso=2.449e-10 cgdo=2.449e-10 cgbo=0
+ tnom=27 ute=-1.5 kt1=-0.11 kt1l=0 kt2=0.022
