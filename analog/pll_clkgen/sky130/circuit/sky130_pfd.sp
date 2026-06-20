* sky130_pfd.sp — Phase-Frequency Detector
* Ports: clk_ref clk_div up dn vdd vss
* Classic 3-state PFD with reset: two D-FFs, reset from AND(up,dn)
* All transistors use sky130_fd_pr__nfet_01v8 / sky130_fd_pr__pfet_01v8
* NFET: W=500n L=150n  PFET: W=1u L=150n

.subckt sky130_pfd clk_ref clk_div up dn vdd vss

* ============================================================
* CMOS INVERTER MACRO (used for clarity)
* inv: in -> out, supply vdd/vss
* ============================================================
* INV for CLK_REF
MP_inv_refclk  refclk_b  clk_ref  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_inv_refclk  refclk_b  clk_ref  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* INV for CLK_DIV
MP_inv_divclk  divclk_b  clk_div  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_inv_divclk  divclk_b  clk_div  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* ============================================================
* FF_REF: D flip-flop triggered by clk_ref, Q=up
* Transmission-gate master-slave DFF
* D is tied to VDD (D=1 always — PFD latch style)
* ============================================================
* Master latch (transparent when clk=0, i.e. clk_ref=0)
* Transmission gate: NFET gate=clk_ref, PFET gate=refclk_b
MP_tg1_ref  dff1_m  vdd  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_tg1_ref  dff1_m  vdd  vdd  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
* Note: simplified — D tied to vdd; implement pass-gate from vdd through TG
* TG master: pass vdd to dff1_m when refclk_b=1 (clk=0)
* Use actual TG: PFET(g=clk_ref) + NFET(g=refclk_b) from vdd to dff1_m
MP_tgm_ref  dff1_m  clk_ref   vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_tgm_ref  dff1_m  refclk_b  vdd  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
* Master hold inverter
MP_mi_ref  dff1_m_b  dff1_m  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_mi_ref  dff1_m_b  dff1_m  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
* Master feedback TG (holds state): PFET(g=refclk_b) + NFET(g=clk_ref)
MP_mfb_ref  dff1_m  refclk_b  dff1_m_b  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_mfb_ref  dff1_m  clk_ref   dff1_m_b  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* Slave latch (transparent when clk=1)
* TG slave: pass dff1_m to dff1_s when clk_ref=1
MP_tgs_ref  dff1_s  refclk_b  dff1_m  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_tgs_ref  dff1_s  clk_ref   dff1_m  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
* Slave hold inverter
MP_si_ref  dff1_s_b  dff1_s  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_si_ref  dff1_s_b  dff1_s  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
* Slave feedback TG
MP_sfb_ref  dff1_s  clk_ref   dff1_s_b  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_sfb_ref  dff1_s  refclk_b  dff1_s_b  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* Q output buffer (up signal before reset)
MP_q_ref_buf  up_pre  dff1_s_b  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_q_ref_buf  up_pre  dff1_s_b  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* ============================================================
* FF_DIV: D flip-flop triggered by clk_div, Q=dn
* Same structure as FF_REF but clocked by clk_div
* ============================================================
MP_tgm_div  dff2_m  clk_div   vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_tgm_div  dff2_m  divclk_b  vdd  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MP_mi_div  dff2_m_b  dff2_m  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_mi_div  dff2_m_b  dff2_m  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MP_mfb_div  dff2_m  divclk_b  dff2_m_b  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_mfb_div  dff2_m  clk_div   dff2_m_b  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

MP_tgs_div  dff2_s  divclk_b  dff2_m  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_tgs_div  dff2_s  clk_div   dff2_m  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MP_si_div  dff2_s_b  dff2_s  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_si_div  dff2_s_b  dff2_s  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MP_sfb_div  dff2_s  clk_div   dff2_s_b  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_sfb_div  dff2_s  divclk_b  dff2_s_b  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

MP_q_div_buf  dn_pre  dff2_s_b  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_q_div_buf  dn_pre  dff2_s_b  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* ============================================================
* RESET LOGIC: NAND2(up_pre, dn_pre) -> reset_b -> reset_buf
* Reset both FFs when both UP and DN are high
* ============================================================
* NAND2: reset_b = !(up_pre & dn_pre)
MP_rst1  rst_b  up_pre  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MP_rst2  rst_b  dn_pre  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_rst1  rst_b  up_pre  rst_n1  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MN_rst2  rst_n1 dn_pre  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* Reset buffer -> reset (active high to FFs)
MP_rst_buf  rst  rst_b  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_rst_buf  rst  rst_b  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1

* Apply reset to FF1: NAND(dff1_s_b, rst_b) to clear state
* Simple reset: reset forces dff1_s high (which inverts to up_pre=0)
* Implement as: up_pre = up_pre_raw AND NOT(rst)
MP_rst_up1  up  rst_b   up_pre  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_rst_up1  up  up_pre  rst_n2  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MN_rst_up2  rst_n2 rst  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MP_rst_up3  up  rst  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1

MP_rst_dn1  dn  rst_b   dn_pre  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1
MN_rst_dn1  dn  dn_pre  rst_n3  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MN_rst_dn2  rst_n3 rst  vss  vss  sky130_fd_pr__nfet_01v8 l=0.15u w=0.5u nf=1
MP_rst_dn3  dn  rst  vdd  vdd  sky130_fd_pr__pfet_01v8 l=0.15u w=1u nf=1

.ends sky130_pfd
