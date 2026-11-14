/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Ultra(TM) in wire load mode
// Version   : X-2025.06-SP3
// Date      : Sat Nov 14 00:55:38 2026
/////////////////////////////////////////////////////////////


module apb_cdc_bridge ( scanmode_i, scan_rst_ni, s_clk_i, s_rst_n_i, s_psel_i, 
        s_penable_i, s_pwrite_i, s_paddr_i, s_pwdata_i, s_pstrb_i, s_prdata_o, 
        s_pready_o, s_pslverr_o, m_clk_i, m_rst_n_i, m_psel_o, m_penable_o, 
        m_pwrite_o, m_paddr_o, m_pwdata_o, m_pstrb_o, m_prdata_i, m_pready_i, 
        m_pslverr_i );
  input [11:0] s_paddr_i;
  input [31:0] s_pwdata_i;
  input [3:0] s_pstrb_i;
  output [31:0] s_prdata_o;
  output [11:0] m_paddr_o;
  output [31:0] m_pwdata_o;
  output [3:0] m_pstrb_o;
  input [31:0] m_prdata_i;
  input scanmode_i, scan_rst_ni, s_clk_i, s_rst_n_i, s_psel_i, s_penable_i,
         s_pwrite_i, m_clk_i, m_rst_n_i, m_pready_i, m_pslverr_i;
  output s_pready_o, s_pslverr_o, m_psel_o, m_penable_o, m_pwrite_o;
  wire   rst_both_n, s_rst_sync_n, m_rst_sync_n, m_in_rst_s, ack_s, req_fwd_q,
         cmd_pwrite_q, req_q, req_m, ack_q, resp_pslverr_dq, n25, n26, n27,
         n28, n29, n30, n31, n32, n33, n34, n35, n36, n37, n38, n39, n40, n41,
         n42, n43, n44, n45, n46, n47, n48, n49, n50, n51, n52, n53, n54, n55,
         n56, n57, n58, n59, n60, n61, n62, n63, n64, n65, n66, n67, n68, n69,
         n70, n71, n72, n73, n74, n75, n76, n77, n78, n79, n80, n81, n82, n83,
         n84, n85, n86, n87, n88, n89, n90, n91, n92, n93, n94, n95, n96, n97,
         n98, n99, n100, n101, n102, n103, n104, n105, n106, n107, n108, n109,
         n110, n111, n112, n113, n114, n115, n116, n117, n118, n119, n120,
         n121, n122, n123, n124, n125, n126, n127, n128, n129, n130, n131,
         n132, n133, n134, n135, n136, n137, n138, n139, n140, n141, n142,
         n143, n144, n145, n146, n147, n148, n149, n150, n151, n152, n153,
         n154, n155, n156, n157, n158, n159, n160, n161, n162, n163, n164,
         n165, n166, n167, n168, n169, n170, n171, n172, n173, n174, n175,
         n176, n177, n178, n179, n180, n181, n182, n183, n184, n185, n186,
         n187, n188, n189, n190, n191, n192, n193, n194, n195, n197, n198,
         n199, n200, n201, n202, n203, n204, n205, n206, n207, n208, n209,
         n210, n211, n212, n213, n214, n215, n216, n217, n218, n219, n220,
         n221, n222, n223, n224, u_s_rst_sync_n2, u_s_rst_sync_rst_n_async,
         u_m_rst_sync_n1, u_m_rst_sync_rst_n_async,
         u_m_rst_status_sync_sync_q_0__0_, u_req_sync_sync_q_0__0_,
         u_ack_sync_sync_q_0__0_;
  wire   [1:0] s_state_q;
  wire   [11:0] cmd_paddr_q;
  wire   [31:0] cmd_pwdata_q;
  wire   [3:0] cmd_pstrb_q;
  wire   [1:0] d_state_q;
  wire   [31:0] resp_prdata_dq;
  wire   [1:0] u_s_rst_sync_sync_q;
  wire   [1:0] u_m_rst_sync_sync_q;

  sky130_fd_sc_hd__dfrbp_2 cmd_paddr_cap_q_reg_1_ ( .D(n58), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[1]) );
  sky130_fd_sc_hd__dfrbp_2 cmd_pwdata_q_reg_23_ ( .D(n142), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[23]) );
  sky130_fd_sc_hd__dfrtp_2 d_state_q_reg_0_ ( .D(n195), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(d_state_q[0]) );
  sky130_fd_sc_hd__dfrtp_2 ack_q_reg ( .D(n193), .CLK(m_clk_i), .RESET_B(n223), 
        .Q(ack_q) );
  sky130_fd_sc_hd__dfrtp_2 s_state_q_reg_1_ ( .D(n192), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_state_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 s_state_q_reg_0_ ( .D(n191), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_state_q[0]) );
  sky130_fd_sc_hd__dfrtp_2 req_q_reg ( .D(n190), .CLK(s_clk_i), .RESET_B(n224), 
        .Q(req_q) );
  sky130_fd_sc_hd__dfrtp_2 d_state_q_reg_1_ ( .D(n194), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(d_state_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_31_ ( .D(n189), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[31]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_30_ ( .D(n188), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[30]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_29_ ( .D(n187), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[29]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_28_ ( .D(n186), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[28]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_27_ ( .D(n185), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[27]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_26_ ( .D(n184), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[26]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_25_ ( .D(n183), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[25]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_24_ ( .D(n182), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[24]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_23_ ( .D(n181), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[23]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_22_ ( .D(n180), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[22]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_21_ ( .D(n179), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[21]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_20_ ( .D(n178), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[20]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_19_ ( .D(n177), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[19]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_18_ ( .D(n176), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[18]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_17_ ( .D(n175), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[17]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_16_ ( .D(n174), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[16]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_15_ ( .D(n173), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[15]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_14_ ( .D(n172), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[14]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_13_ ( .D(n171), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[13]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_12_ ( .D(n170), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[12]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_11_ ( .D(n169), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[11]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_10_ ( .D(n168), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[10]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_9_ ( .D(n167), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[9]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_8_ ( .D(n166), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[8]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_7_ ( .D(n165), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[7]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_6_ ( .D(n164), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[6]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_5_ ( .D(n163), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[5]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_4_ ( .D(n162), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[4]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_3_ ( .D(n161), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[3]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_2_ ( .D(n160), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[2]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_1_ ( .D(n159), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[1]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_q_reg_0_ ( .D(n158), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_prdata_o[0]) );
  sky130_fd_sc_hd__dfrtp_2 resp_pslverr_q_reg ( .D(n157), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(s_pslverr_o) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwrite_q_reg ( .D(n156), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwrite_q) );
  sky130_fd_sc_hd__dfrtp_2 req_fwd_q_reg ( .D(n155), .CLK(s_clk_i), .RESET_B(
        n224), .Q(req_fwd_q) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_q_reg_3_ ( .D(n154), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pstrb_q[3]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_q_reg_2_ ( .D(n153), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pstrb_q[2]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_q_reg_1_ ( .D(n152), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pstrb_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_q_reg_0_ ( .D(n151), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pstrb_q[0]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_31_ ( .D(n150), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[31]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_30_ ( .D(n149), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[30]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_29_ ( .D(n148), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[29]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_28_ ( .D(n147), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[28]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_27_ ( .D(n146), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[27]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_26_ ( .D(n145), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[26]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_25_ ( .D(n144), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[25]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_24_ ( .D(n143), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[24]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_22_ ( .D(n141), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[22]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_21_ ( .D(n140), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[21]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_20_ ( .D(n139), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[20]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_19_ ( .D(n138), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[19]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_18_ ( .D(n137), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[18]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_17_ ( .D(n136), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[17]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_16_ ( .D(n135), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[16]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_15_ ( .D(n134), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[15]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_14_ ( .D(n133), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[14]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_13_ ( .D(n132), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[13]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_12_ ( .D(n131), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[12]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_11_ ( .D(n130), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[11]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_10_ ( .D(n129), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[10]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_9_ ( .D(n128), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[9]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_8_ ( .D(n127), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[8]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_7_ ( .D(n126), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[7]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_6_ ( .D(n125), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[6]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_5_ ( .D(n124), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[5]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_4_ ( .D(n123), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[4]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_3_ ( .D(n122), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[3]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_2_ ( .D(n121), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[2]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_1_ ( .D(n120), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_q_reg_0_ ( .D(n119), .CLK(s_clk_i), 
        .RESET_B(n224), .Q(cmd_pwdata_q[0]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_11_ ( .D(n118), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[11]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_10_ ( .D(n117), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[10]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_9_ ( .D(n116), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[9]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_8_ ( .D(n115), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[8]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_7_ ( .D(n114), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[7]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_6_ ( .D(n113), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[6]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_5_ ( .D(n112), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[5]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_4_ ( .D(n111), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[4]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_3_ ( .D(n110), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[3]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_2_ ( .D(n109), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[2]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_1_ ( .D(n108), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_q_reg_0_ ( .D(n107), .CLK(s_clk_i), 
        .RESET_B(s_rst_sync_n), .Q(cmd_paddr_q[0]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_cap_q_reg_3_ ( .D(n106), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pstrb_o[3]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_cap_q_reg_2_ ( .D(n105), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pstrb_o[2]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_cap_q_reg_1_ ( .D(n104), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pstrb_o[1]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pstrb_cap_q_reg_0_ ( .D(n103), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pstrb_o[0]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_0_ ( .D(n102), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[0]) );
  sky130_fd_sc_hd__dfrtp_2 resp_pslverr_dq_reg ( .D(n101), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_pslverr_dq) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_31_ ( .D(n100), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[31]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_30_ ( .D(n99), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[30]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_29_ ( .D(n98), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[29]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_28_ ( .D(n97), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[28]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_27_ ( .D(n96), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[27]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_26_ ( .D(n95), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[26]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_25_ ( .D(n94), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[25]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_24_ ( .D(n93), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[24]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_23_ ( .D(n92), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[23]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_22_ ( .D(n91), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[22]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_21_ ( .D(n90), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[21]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_20_ ( .D(n89), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[20]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_19_ ( .D(n88), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[19]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_18_ ( .D(n87), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[18]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_17_ ( .D(n86), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[17]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_16_ ( .D(n85), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[16]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_15_ ( .D(n84), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[15]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_14_ ( .D(n83), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[14]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_13_ ( .D(n82), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[13]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_12_ ( .D(n81), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[12]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_11_ ( .D(n80), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[11]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_10_ ( .D(n79), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[10]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_9_ ( .D(n78), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[9]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_8_ ( .D(n77), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[8]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_7_ ( .D(n76), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[7]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_6_ ( .D(n75), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[6]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_5_ ( .D(n74), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[5]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_4_ ( .D(n73), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[4]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_3_ ( .D(n72), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[3]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_2_ ( .D(n71), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[2]) );
  sky130_fd_sc_hd__dfrtp_2 resp_prdata_dq_reg_1_ ( .D(n70), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(resp_prdata_dq[1]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwrite_cap_q_reg ( .D(n69), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwrite_o) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_11_ ( .D(n68), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[11]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_10_ ( .D(n67), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[10]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_9_ ( .D(n66), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[9]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_8_ ( .D(n65), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[8]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_7_ ( .D(n64), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[7]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_6_ ( .D(n63), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[6]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_5_ ( .D(n62), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[5]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_4_ ( .D(n61), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[4]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_3_ ( .D(n60), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[3]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_2_ ( .D(n59), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[2]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_paddr_cap_q_reg_0_ ( .D(n57), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_paddr_o[0]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_31_ ( .D(n56), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[31]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_30_ ( .D(n55), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[30]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_29_ ( .D(n54), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[29]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_28_ ( .D(n53), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[28]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_27_ ( .D(n52), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[27]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_26_ ( .D(n51), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[26]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_25_ ( .D(n50), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[25]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_24_ ( .D(n49), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[24]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_23_ ( .D(n48), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[23]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_22_ ( .D(n47), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[22]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_21_ ( .D(n46), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[21]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_20_ ( .D(n45), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[20]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_19_ ( .D(n44), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[19]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_18_ ( .D(n43), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[18]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_17_ ( .D(n42), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[17]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_16_ ( .D(n41), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[16]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_15_ ( .D(n40), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[15]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_14_ ( .D(n39), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[14]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_13_ ( .D(n38), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[13]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_12_ ( .D(n37), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[12]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_11_ ( .D(n36), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[11]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_10_ ( .D(n35), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[10]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_9_ ( .D(n34), .CLK(m_clk_i), 
        .RESET_B(n223), .Q(m_pwdata_o[9]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_8_ ( .D(n33), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[8]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_7_ ( .D(n32), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[7]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_6_ ( .D(n31), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[6]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_5_ ( .D(n30), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[5]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_4_ ( .D(n29), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[4]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_3_ ( .D(n28), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[3]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_2_ ( .D(n27), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[2]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_1_ ( .D(n26), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[1]) );
  sky130_fd_sc_hd__dfrtp_2 cmd_pwdata_cap_q_reg_0_ ( .D(n25), .CLK(m_clk_i), 
        .RESET_B(m_rst_sync_n), .Q(m_pwdata_o[0]) );
  sky130_fd_sc_hd__clkinvlp_2 U203 ( .A(d_state_q[1]), .Y(n199) );
  sky130_fd_sc_hd__clkinvlp_2 U204 ( .A(n198), .Y(m_psel_o) );
  sky130_fd_sc_hd__clkinvlp_2 U205 ( .A(ack_s), .Y(n210) );
  sky130_fd_sc_hd__clkinvlp_2 U206 ( .A(n222), .Y(n221) );
  sky130_fd_sc_hd__clkinvlp_2 U207 ( .A(n218), .Y(n219) );
  sky130_fd_sc_hd__clkinvlp_2 U208 ( .A(n214), .Y(n215) );
  sky130_fd_sc_hd__clkinvlp_2 U209 ( .A(m_rst_n_i), .Y(n197) );
  sky130_fd_sc_hd__nor2_1 U210 ( .A(d_state_q[0]), .B(n199), .Y(m_penable_o)
         );
  sky130_fd_sc_hd__buf_2 U211 ( .A(m_rst_sync_n), .X(n223) );
  sky130_fd_sc_hd__buf_2 U212 ( .A(s_rst_sync_n), .X(n224) );
  sky130_fd_sc_hd__nor4b_1 U213 ( .D_N(s_psel_i), .A(s_penable_i), .B(
        s_state_q[0]), .C(s_state_q[1]), .Y(n216) );
  sky130_fd_sc_hd__clkbuf_1 U214 ( .A(n216), .X(n214) );
  sky130_fd_sc_hd__o2bb2ai_1 U215 ( .B1(n215), .B2(m_in_rst_s), .A1_N(n215), 
        .A2_N(req_fwd_q), .Y(n155) );
  sky130_fd_sc_hd__nor2b_1 U216 ( .B_N(s_rst_n_i), .A(n197), .Y(rst_both_n) );
  sky130_fd_sc_hd__and2_0 U217 ( .A(s_state_q[1]), .B(s_state_q[0]), .X(
        s_pready_o) );
  sky130_fd_sc_hd__a21oi_1 U218 ( .A1(n199), .A2(d_state_q[0]), .B1(
        m_penable_o), .Y(n198) );
  sky130_fd_sc_hd__clkinvlp_2 U219 ( .A(req_m), .Y(n217) );
  sky130_fd_sc_hd__nand2_1 U220 ( .A(m_penable_o), .B(m_pready_i), .Y(n218) );
  sky130_fd_sc_hd__o21ai_1 U221 ( .A1(n217), .A2(m_psel_o), .B1(n218), .Y(n195) );
  sky130_fd_sc_hd__o21ai_1 U222 ( .A1(n199), .A2(n217), .B1(n198), .Y(n194) );
  sky130_fd_sc_hd__nor2_1 U223 ( .A(n219), .B(ack_q), .Y(n200) );
  sky130_fd_sc_hd__a31oi_1 U224 ( .A1(d_state_q[0]), .A2(d_state_q[1]), .A3(
        n217), .B1(n200), .Y(n193) );
  sky130_fd_sc_hd__nor3b_1 U225 ( .C_N(req_fwd_q), .A(m_in_rst_s), .B(ack_s), 
        .Y(n202) );
  sky130_fd_sc_hd__clkinvlp_2 U226 ( .A(s_state_q[0]), .Y(n201) );
  sky130_fd_sc_hd__nor2_1 U227 ( .A(s_state_q[1]), .B(n201), .Y(n205) );
  sky130_fd_sc_hd__nand2b_1 U228 ( .A_N(n202), .B(n205), .Y(n209) );
  sky130_fd_sc_hd__nand2_1 U229 ( .A(s_state_q[1]), .B(n201), .Y(n204) );
  sky130_fd_sc_hd__nand2_1 U230 ( .A(n209), .B(n204), .Y(n192) );
  sky130_fd_sc_hd__a21oi_1 U231 ( .A1(n205), .A2(n202), .B1(n214), .Y(n203) );
  sky130_fd_sc_hd__o21ai_1 U232 ( .A1(ack_s), .A2(n204), .B1(n203), .Y(n191)
         );
  sky130_fd_sc_hd__nand2_1 U233 ( .A(ack_s), .B(n205), .Y(n207) );
  sky130_fd_sc_hd__a21oi_1 U234 ( .A1(req_q), .A2(n207), .B1(n214), .Y(n206)
         );
  sky130_fd_sc_hd__nor2_1 U235 ( .A(m_in_rst_s), .B(n206), .Y(n190) );
  sky130_fd_sc_hd__clkinvlp_2 U236 ( .A(n207), .Y(n208) );
  sky130_fd_sc_hd__a22o_1 U237 ( .A1(n208), .A2(resp_prdata_dq[31]), .B1(
        s_prdata_o[31]), .B2(n209), .X(n189) );
  sky130_fd_sc_hd__a22o_1 U238 ( .A1(n208), .A2(resp_prdata_dq[30]), .B1(
        s_prdata_o[30]), .B2(n209), .X(n188) );
  sky130_fd_sc_hd__a22o_1 U239 ( .A1(n208), .A2(resp_prdata_dq[29]), .B1(
        s_prdata_o[29]), .B2(n209), .X(n187) );
  sky130_fd_sc_hd__a22o_1 U240 ( .A1(n208), .A2(resp_prdata_dq[28]), .B1(
        s_prdata_o[28]), .B2(n209), .X(n186) );
  sky130_fd_sc_hd__a22o_1 U241 ( .A1(n208), .A2(resp_prdata_dq[27]), .B1(
        s_prdata_o[27]), .B2(n209), .X(n185) );
  sky130_fd_sc_hd__a22o_1 U242 ( .A1(n208), .A2(resp_prdata_dq[26]), .B1(
        s_prdata_o[26]), .B2(n209), .X(n184) );
  sky130_fd_sc_hd__a22o_1 U243 ( .A1(n208), .A2(resp_prdata_dq[25]), .B1(
        s_prdata_o[25]), .B2(n209), .X(n183) );
  sky130_fd_sc_hd__a22o_1 U244 ( .A1(n208), .A2(resp_prdata_dq[24]), .B1(
        s_prdata_o[24]), .B2(n209), .X(n182) );
  sky130_fd_sc_hd__a22o_1 U245 ( .A1(n208), .A2(resp_prdata_dq[23]), .B1(
        s_prdata_o[23]), .B2(n209), .X(n181) );
  sky130_fd_sc_hd__a22o_1 U246 ( .A1(n208), .A2(resp_prdata_dq[22]), .B1(
        s_prdata_o[22]), .B2(n209), .X(n180) );
  sky130_fd_sc_hd__a22o_1 U247 ( .A1(n208), .A2(resp_prdata_dq[21]), .B1(
        s_prdata_o[21]), .B2(n209), .X(n179) );
  sky130_fd_sc_hd__a22o_1 U248 ( .A1(n208), .A2(resp_prdata_dq[20]), .B1(
        s_prdata_o[20]), .B2(n209), .X(n178) );
  sky130_fd_sc_hd__a22o_1 U249 ( .A1(n208), .A2(resp_prdata_dq[19]), .B1(
        s_prdata_o[19]), .B2(n209), .X(n177) );
  sky130_fd_sc_hd__a22o_1 U250 ( .A1(n208), .A2(resp_prdata_dq[18]), .B1(
        s_prdata_o[18]), .B2(n209), .X(n176) );
  sky130_fd_sc_hd__a22o_1 U251 ( .A1(n208), .A2(resp_prdata_dq[17]), .B1(
        s_prdata_o[17]), .B2(n209), .X(n175) );
  sky130_fd_sc_hd__a22o_1 U252 ( .A1(n208), .A2(resp_prdata_dq[16]), .B1(
        s_prdata_o[16]), .B2(n209), .X(n174) );
  sky130_fd_sc_hd__a22o_1 U253 ( .A1(n208), .A2(resp_prdata_dq[15]), .B1(
        s_prdata_o[15]), .B2(n209), .X(n173) );
  sky130_fd_sc_hd__a22o_1 U254 ( .A1(n208), .A2(resp_prdata_dq[14]), .B1(
        s_prdata_o[14]), .B2(n209), .X(n172) );
  sky130_fd_sc_hd__a22o_1 U255 ( .A1(n208), .A2(resp_prdata_dq[13]), .B1(
        s_prdata_o[13]), .B2(n209), .X(n171) );
  sky130_fd_sc_hd__a22o_1 U256 ( .A1(n208), .A2(resp_prdata_dq[12]), .B1(
        s_prdata_o[12]), .B2(n209), .X(n170) );
  sky130_fd_sc_hd__a22o_1 U257 ( .A1(n208), .A2(resp_prdata_dq[11]), .B1(
        s_prdata_o[11]), .B2(n209), .X(n169) );
  sky130_fd_sc_hd__a22o_1 U258 ( .A1(n208), .A2(resp_prdata_dq[10]), .B1(
        s_prdata_o[10]), .B2(n209), .X(n168) );
  sky130_fd_sc_hd__a22o_1 U259 ( .A1(n208), .A2(resp_prdata_dq[9]), .B1(
        s_prdata_o[9]), .B2(n209), .X(n167) );
  sky130_fd_sc_hd__a22o_1 U260 ( .A1(n208), .A2(resp_prdata_dq[8]), .B1(
        s_prdata_o[8]), .B2(n209), .X(n166) );
  sky130_fd_sc_hd__a22o_1 U261 ( .A1(n208), .A2(resp_prdata_dq[7]), .B1(
        s_prdata_o[7]), .B2(n209), .X(n165) );
  sky130_fd_sc_hd__a22o_1 U262 ( .A1(n208), .A2(resp_prdata_dq[6]), .B1(
        s_prdata_o[6]), .B2(n209), .X(n164) );
  sky130_fd_sc_hd__a22o_1 U263 ( .A1(n208), .A2(resp_prdata_dq[5]), .B1(
        s_prdata_o[5]), .B2(n209), .X(n163) );
  sky130_fd_sc_hd__a22o_1 U264 ( .A1(n208), .A2(resp_prdata_dq[4]), .B1(
        s_prdata_o[4]), .B2(n209), .X(n162) );
  sky130_fd_sc_hd__a22o_1 U265 ( .A1(n208), .A2(resp_prdata_dq[3]), .B1(
        s_prdata_o[3]), .B2(n209), .X(n161) );
  sky130_fd_sc_hd__a22o_1 U266 ( .A1(n208), .A2(resp_prdata_dq[2]), .B1(
        s_prdata_o[2]), .B2(n209), .X(n160) );
  sky130_fd_sc_hd__a22o_1 U267 ( .A1(n208), .A2(resp_prdata_dq[1]), .B1(
        s_prdata_o[1]), .B2(n209), .X(n159) );
  sky130_fd_sc_hd__a22o_1 U268 ( .A1(n208), .A2(resp_prdata_dq[0]), .B1(
        s_prdata_o[0]), .B2(n209), .X(n158) );
  sky130_fd_sc_hd__clkinvlp_2 U269 ( .A(n209), .Y(n213) );
  sky130_fd_sc_hd__clkinvlp_2 U270 ( .A(s_pslverr_o), .Y(n212) );
  sky130_fd_sc_hd__o21ai_1 U271 ( .A1(n210), .A2(resp_pslverr_dq), .B1(n213), 
        .Y(n211) );
  sky130_fd_sc_hd__o21ai_1 U272 ( .A1(n213), .A2(n212), .B1(n211), .Y(n157) );
  sky130_fd_sc_hd__a22o_1 U273 ( .A1(n214), .A2(s_pwrite_i), .B1(n215), .B2(
        cmd_pwrite_q), .X(n156) );
  sky130_fd_sc_hd__a22o_1 U274 ( .A1(n214), .A2(s_pstrb_i[3]), .B1(n215), .B2(
        cmd_pstrb_q[3]), .X(n154) );
  sky130_fd_sc_hd__a22o_1 U275 ( .A1(n214), .A2(s_pstrb_i[2]), .B1(n215), .B2(
        cmd_pstrb_q[2]), .X(n153) );
  sky130_fd_sc_hd__a22o_1 U276 ( .A1(n216), .A2(s_pstrb_i[1]), .B1(n215), .B2(
        cmd_pstrb_q[1]), .X(n152) );
  sky130_fd_sc_hd__a22o_1 U277 ( .A1(n214), .A2(s_pstrb_i[0]), .B1(n215), .B2(
        cmd_pstrb_q[0]), .X(n151) );
  sky130_fd_sc_hd__a22o_1 U278 ( .A1(n214), .A2(s_pwdata_i[31]), .B1(n215), 
        .B2(cmd_pwdata_q[31]), .X(n150) );
  sky130_fd_sc_hd__a22o_1 U279 ( .A1(n214), .A2(s_pwdata_i[30]), .B1(n215), 
        .B2(cmd_pwdata_q[30]), .X(n149) );
  sky130_fd_sc_hd__a22o_1 U280 ( .A1(n214), .A2(s_pwdata_i[29]), .B1(n215), 
        .B2(cmd_pwdata_q[29]), .X(n148) );
  sky130_fd_sc_hd__a22o_1 U281 ( .A1(n214), .A2(s_pwdata_i[28]), .B1(n215), 
        .B2(cmd_pwdata_q[28]), .X(n147) );
  sky130_fd_sc_hd__a22o_1 U282 ( .A1(n214), .A2(s_pwdata_i[27]), .B1(n215), 
        .B2(cmd_pwdata_q[27]), .X(n146) );
  sky130_fd_sc_hd__a22o_1 U283 ( .A1(n214), .A2(s_pwdata_i[26]), .B1(n215), 
        .B2(cmd_pwdata_q[26]), .X(n145) );
  sky130_fd_sc_hd__a22o_1 U284 ( .A1(n214), .A2(s_pwdata_i[25]), .B1(n215), 
        .B2(cmd_pwdata_q[25]), .X(n144) );
  sky130_fd_sc_hd__a22o_1 U285 ( .A1(n214), .A2(s_pwdata_i[24]), .B1(n215), 
        .B2(cmd_pwdata_q[24]), .X(n143) );
  sky130_fd_sc_hd__a22o_1 U286 ( .A1(n214), .A2(s_pwdata_i[23]), .B1(n215), 
        .B2(cmd_pwdata_q[23]), .X(n142) );
  sky130_fd_sc_hd__a22o_1 U287 ( .A1(n214), .A2(s_pwdata_i[22]), .B1(n215), 
        .B2(cmd_pwdata_q[22]), .X(n141) );
  sky130_fd_sc_hd__a22o_1 U288 ( .A1(n214), .A2(s_pwdata_i[21]), .B1(n215), 
        .B2(cmd_pwdata_q[21]), .X(n140) );
  sky130_fd_sc_hd__a22o_1 U289 ( .A1(n214), .A2(s_pwdata_i[20]), .B1(n215), 
        .B2(cmd_pwdata_q[20]), .X(n139) );
  sky130_fd_sc_hd__a22o_1 U290 ( .A1(n214), .A2(s_pwdata_i[19]), .B1(n215), 
        .B2(cmd_pwdata_q[19]), .X(n138) );
  sky130_fd_sc_hd__a22o_1 U291 ( .A1(n216), .A2(s_pwdata_i[18]), .B1(n215), 
        .B2(cmd_pwdata_q[18]), .X(n137) );
  sky130_fd_sc_hd__a22o_1 U292 ( .A1(n216), .A2(s_pwdata_i[17]), .B1(n215), 
        .B2(cmd_pwdata_q[17]), .X(n136) );
  sky130_fd_sc_hd__a22o_1 U293 ( .A1(n216), .A2(s_pwdata_i[16]), .B1(n215), 
        .B2(cmd_pwdata_q[16]), .X(n135) );
  sky130_fd_sc_hd__a22o_1 U294 ( .A1(n216), .A2(s_pwdata_i[15]), .B1(n215), 
        .B2(cmd_pwdata_q[15]), .X(n134) );
  sky130_fd_sc_hd__a22o_1 U295 ( .A1(n216), .A2(s_pwdata_i[14]), .B1(n215), 
        .B2(cmd_pwdata_q[14]), .X(n133) );
  sky130_fd_sc_hd__a22o_1 U296 ( .A1(n216), .A2(s_pwdata_i[13]), .B1(n215), 
        .B2(cmd_pwdata_q[13]), .X(n132) );
  sky130_fd_sc_hd__a22o_1 U297 ( .A1(n216), .A2(s_pwdata_i[12]), .B1(n215), 
        .B2(cmd_pwdata_q[12]), .X(n131) );
  sky130_fd_sc_hd__a22o_1 U298 ( .A1(n216), .A2(s_pwdata_i[11]), .B1(n215), 
        .B2(cmd_pwdata_q[11]), .X(n130) );
  sky130_fd_sc_hd__a22o_1 U299 ( .A1(n216), .A2(s_pwdata_i[10]), .B1(n215), 
        .B2(cmd_pwdata_q[10]), .X(n129) );
  sky130_fd_sc_hd__a22o_1 U300 ( .A1(n216), .A2(s_pwdata_i[9]), .B1(n215), 
        .B2(cmd_pwdata_q[9]), .X(n128) );
  sky130_fd_sc_hd__a22o_1 U301 ( .A1(n214), .A2(s_pwdata_i[8]), .B1(n215), 
        .B2(cmd_pwdata_q[8]), .X(n127) );
  sky130_fd_sc_hd__a22o_1 U302 ( .A1(n214), .A2(s_pwdata_i[7]), .B1(n215), 
        .B2(cmd_pwdata_q[7]), .X(n126) );
  sky130_fd_sc_hd__a22o_1 U303 ( .A1(n214), .A2(s_pwdata_i[6]), .B1(n215), 
        .B2(cmd_pwdata_q[6]), .X(n125) );
  sky130_fd_sc_hd__a22o_1 U304 ( .A1(n214), .A2(s_pwdata_i[5]), .B1(n215), 
        .B2(cmd_pwdata_q[5]), .X(n124) );
  sky130_fd_sc_hd__a22o_1 U305 ( .A1(n214), .A2(s_pwdata_i[4]), .B1(n215), 
        .B2(cmd_pwdata_q[4]), .X(n123) );
  sky130_fd_sc_hd__a22o_1 U306 ( .A1(n214), .A2(s_pwdata_i[3]), .B1(n215), 
        .B2(cmd_pwdata_q[3]), .X(n122) );
  sky130_fd_sc_hd__a22o_1 U307 ( .A1(n214), .A2(s_pwdata_i[2]), .B1(n215), 
        .B2(cmd_pwdata_q[2]), .X(n121) );
  sky130_fd_sc_hd__a22o_1 U308 ( .A1(n214), .A2(s_pwdata_i[1]), .B1(n215), 
        .B2(cmd_pwdata_q[1]), .X(n120) );
  sky130_fd_sc_hd__a22o_1 U309 ( .A1(n214), .A2(s_pwdata_i[0]), .B1(n215), 
        .B2(cmd_pwdata_q[0]), .X(n119) );
  sky130_fd_sc_hd__a22o_1 U310 ( .A1(n214), .A2(s_paddr_i[11]), .B1(n215), 
        .B2(cmd_paddr_q[11]), .X(n118) );
  sky130_fd_sc_hd__a22o_1 U311 ( .A1(n214), .A2(s_paddr_i[10]), .B1(n215), 
        .B2(cmd_paddr_q[10]), .X(n117) );
  sky130_fd_sc_hd__a22o_1 U312 ( .A1(n214), .A2(s_paddr_i[9]), .B1(n215), .B2(
        cmd_paddr_q[9]), .X(n116) );
  sky130_fd_sc_hd__a22o_1 U313 ( .A1(n214), .A2(s_paddr_i[8]), .B1(n215), .B2(
        cmd_paddr_q[8]), .X(n115) );
  sky130_fd_sc_hd__a22o_1 U314 ( .A1(n214), .A2(s_paddr_i[7]), .B1(n215), .B2(
        cmd_paddr_q[7]), .X(n114) );
  sky130_fd_sc_hd__a22o_1 U315 ( .A1(n214), .A2(s_paddr_i[6]), .B1(n215), .B2(
        cmd_paddr_q[6]), .X(n113) );
  sky130_fd_sc_hd__a22o_1 U316 ( .A1(n214), .A2(s_paddr_i[5]), .B1(n215), .B2(
        cmd_paddr_q[5]), .X(n112) );
  sky130_fd_sc_hd__a22o_1 U317 ( .A1(n214), .A2(s_paddr_i[4]), .B1(n215), .B2(
        cmd_paddr_q[4]), .X(n111) );
  sky130_fd_sc_hd__a22o_1 U318 ( .A1(n214), .A2(s_paddr_i[3]), .B1(n215), .B2(
        cmd_paddr_q[3]), .X(n110) );
  sky130_fd_sc_hd__a22o_1 U319 ( .A1(n214), .A2(s_paddr_i[2]), .B1(n215), .B2(
        cmd_paddr_q[2]), .X(n109) );
  sky130_fd_sc_hd__a22o_1 U320 ( .A1(n214), .A2(s_paddr_i[1]), .B1(n215), .B2(
        cmd_paddr_q[1]), .X(n108) );
  sky130_fd_sc_hd__a22o_1 U321 ( .A1(n216), .A2(s_paddr_i[0]), .B1(n215), .B2(
        cmd_paddr_q[0]), .X(n107) );
  sky130_fd_sc_hd__nor3_1 U322 ( .A(d_state_q[1]), .B(d_state_q[0]), .C(n217), 
        .Y(n220) );
  sky130_fd_sc_hd__clkbuf_1 U323 ( .A(n220), .X(n222) );
  sky130_fd_sc_hd__a22o_1 U324 ( .A1(n222), .A2(cmd_pstrb_q[3]), .B1(n221), 
        .B2(m_pstrb_o[3]), .X(n106) );
  sky130_fd_sc_hd__a22o_1 U325 ( .A1(n222), .A2(cmd_pstrb_q[2]), .B1(n221), 
        .B2(m_pstrb_o[2]), .X(n105) );
  sky130_fd_sc_hd__a22o_1 U326 ( .A1(n222), .A2(cmd_pstrb_q[1]), .B1(n221), 
        .B2(m_pstrb_o[1]), .X(n104) );
  sky130_fd_sc_hd__a22o_1 U327 ( .A1(n222), .A2(cmd_pstrb_q[0]), .B1(n221), 
        .B2(m_pstrb_o[0]), .X(n103) );
  sky130_fd_sc_hd__a22o_1 U328 ( .A1(n219), .A2(m_prdata_i[0]), .B1(n218), 
        .B2(resp_prdata_dq[0]), .X(n102) );
  sky130_fd_sc_hd__a22o_1 U329 ( .A1(n219), .A2(m_pslverr_i), .B1(n218), .B2(
        resp_pslverr_dq), .X(n101) );
  sky130_fd_sc_hd__a22o_1 U330 ( .A1(n219), .A2(m_prdata_i[31]), .B1(n218), 
        .B2(resp_prdata_dq[31]), .X(n100) );
  sky130_fd_sc_hd__a22o_1 U331 ( .A1(n219), .A2(m_prdata_i[30]), .B1(n218), 
        .B2(resp_prdata_dq[30]), .X(n99) );
  sky130_fd_sc_hd__a22o_1 U332 ( .A1(n219), .A2(m_prdata_i[29]), .B1(n218), 
        .B2(resp_prdata_dq[29]), .X(n98) );
  sky130_fd_sc_hd__a22o_1 U333 ( .A1(n219), .A2(m_prdata_i[28]), .B1(n218), 
        .B2(resp_prdata_dq[28]), .X(n97) );
  sky130_fd_sc_hd__a22o_1 U334 ( .A1(n219), .A2(m_prdata_i[27]), .B1(n218), 
        .B2(resp_prdata_dq[27]), .X(n96) );
  sky130_fd_sc_hd__a22o_1 U335 ( .A1(n219), .A2(m_prdata_i[26]), .B1(n218), 
        .B2(resp_prdata_dq[26]), .X(n95) );
  sky130_fd_sc_hd__a22o_1 U336 ( .A1(n219), .A2(m_prdata_i[25]), .B1(n218), 
        .B2(resp_prdata_dq[25]), .X(n94) );
  sky130_fd_sc_hd__a22o_1 U337 ( .A1(n219), .A2(m_prdata_i[24]), .B1(n218), 
        .B2(resp_prdata_dq[24]), .X(n93) );
  sky130_fd_sc_hd__a22o_1 U338 ( .A1(n219), .A2(m_prdata_i[23]), .B1(n218), 
        .B2(resp_prdata_dq[23]), .X(n92) );
  sky130_fd_sc_hd__a22o_1 U339 ( .A1(n219), .A2(m_prdata_i[22]), .B1(n218), 
        .B2(resp_prdata_dq[22]), .X(n91) );
  sky130_fd_sc_hd__a22o_1 U340 ( .A1(n219), .A2(m_prdata_i[21]), .B1(n218), 
        .B2(resp_prdata_dq[21]), .X(n90) );
  sky130_fd_sc_hd__a22o_1 U341 ( .A1(n219), .A2(m_prdata_i[20]), .B1(n218), 
        .B2(resp_prdata_dq[20]), .X(n89) );
  sky130_fd_sc_hd__a22o_1 U342 ( .A1(n219), .A2(m_prdata_i[19]), .B1(n218), 
        .B2(resp_prdata_dq[19]), .X(n88) );
  sky130_fd_sc_hd__a22o_1 U343 ( .A1(n219), .A2(m_prdata_i[18]), .B1(n218), 
        .B2(resp_prdata_dq[18]), .X(n87) );
  sky130_fd_sc_hd__a22o_1 U344 ( .A1(n219), .A2(m_prdata_i[17]), .B1(n218), 
        .B2(resp_prdata_dq[17]), .X(n86) );
  sky130_fd_sc_hd__a22o_1 U345 ( .A1(n219), .A2(m_prdata_i[16]), .B1(n218), 
        .B2(resp_prdata_dq[16]), .X(n85) );
  sky130_fd_sc_hd__a22o_1 U346 ( .A1(n219), .A2(m_prdata_i[15]), .B1(n218), 
        .B2(resp_prdata_dq[15]), .X(n84) );
  sky130_fd_sc_hd__a22o_1 U347 ( .A1(n219), .A2(m_prdata_i[14]), .B1(n218), 
        .B2(resp_prdata_dq[14]), .X(n83) );
  sky130_fd_sc_hd__a22o_1 U348 ( .A1(n219), .A2(m_prdata_i[13]), .B1(n218), 
        .B2(resp_prdata_dq[13]), .X(n82) );
  sky130_fd_sc_hd__a22o_1 U349 ( .A1(n219), .A2(m_prdata_i[12]), .B1(n218), 
        .B2(resp_prdata_dq[12]), .X(n81) );
  sky130_fd_sc_hd__a22o_1 U350 ( .A1(n219), .A2(m_prdata_i[11]), .B1(n218), 
        .B2(resp_prdata_dq[11]), .X(n80) );
  sky130_fd_sc_hd__a22o_1 U351 ( .A1(n219), .A2(m_prdata_i[10]), .B1(n218), 
        .B2(resp_prdata_dq[10]), .X(n79) );
  sky130_fd_sc_hd__a22o_1 U352 ( .A1(n219), .A2(m_prdata_i[9]), .B1(n218), 
        .B2(resp_prdata_dq[9]), .X(n78) );
  sky130_fd_sc_hd__a22o_1 U353 ( .A1(n219), .A2(m_prdata_i[8]), .B1(n218), 
        .B2(resp_prdata_dq[8]), .X(n77) );
  sky130_fd_sc_hd__a22o_1 U354 ( .A1(n219), .A2(m_prdata_i[7]), .B1(n218), 
        .B2(resp_prdata_dq[7]), .X(n76) );
  sky130_fd_sc_hd__a22o_1 U355 ( .A1(n219), .A2(m_prdata_i[6]), .B1(n218), 
        .B2(resp_prdata_dq[6]), .X(n75) );
  sky130_fd_sc_hd__a22o_1 U356 ( .A1(n219), .A2(m_prdata_i[5]), .B1(n218), 
        .B2(resp_prdata_dq[5]), .X(n74) );
  sky130_fd_sc_hd__a22o_1 U357 ( .A1(n219), .A2(m_prdata_i[4]), .B1(n218), 
        .B2(resp_prdata_dq[4]), .X(n73) );
  sky130_fd_sc_hd__a22o_1 U358 ( .A1(n219), .A2(m_prdata_i[3]), .B1(n218), 
        .B2(resp_prdata_dq[3]), .X(n72) );
  sky130_fd_sc_hd__a22o_1 U359 ( .A1(n219), .A2(m_prdata_i[2]), .B1(n218), 
        .B2(resp_prdata_dq[2]), .X(n71) );
  sky130_fd_sc_hd__a22o_1 U360 ( .A1(n219), .A2(m_prdata_i[1]), .B1(n218), 
        .B2(resp_prdata_dq[1]), .X(n70) );
  sky130_fd_sc_hd__a22o_1 U361 ( .A1(n222), .A2(cmd_pwrite_q), .B1(n221), .B2(
        m_pwrite_o), .X(n69) );
  sky130_fd_sc_hd__a22o_1 U362 ( .A1(n222), .A2(cmd_paddr_q[11]), .B1(n221), 
        .B2(m_paddr_o[11]), .X(n68) );
  sky130_fd_sc_hd__a22o_1 U363 ( .A1(n222), .A2(cmd_paddr_q[10]), .B1(n221), 
        .B2(m_paddr_o[10]), .X(n67) );
  sky130_fd_sc_hd__a22o_1 U364 ( .A1(n222), .A2(cmd_paddr_q[9]), .B1(n221), 
        .B2(m_paddr_o[9]), .X(n66) );
  sky130_fd_sc_hd__a22o_1 U365 ( .A1(n222), .A2(cmd_paddr_q[8]), .B1(n221), 
        .B2(m_paddr_o[8]), .X(n65) );
  sky130_fd_sc_hd__a22o_1 U366 ( .A1(n222), .A2(cmd_paddr_q[7]), .B1(n221), 
        .B2(m_paddr_o[7]), .X(n64) );
  sky130_fd_sc_hd__a22o_1 U367 ( .A1(n222), .A2(cmd_paddr_q[6]), .B1(n221), 
        .B2(m_paddr_o[6]), .X(n63) );
  sky130_fd_sc_hd__a22o_1 U368 ( .A1(n222), .A2(cmd_paddr_q[5]), .B1(n221), 
        .B2(m_paddr_o[5]), .X(n62) );
  sky130_fd_sc_hd__a22o_1 U369 ( .A1(n222), .A2(cmd_paddr_q[4]), .B1(n221), 
        .B2(m_paddr_o[4]), .X(n61) );
  sky130_fd_sc_hd__a22o_1 U370 ( .A1(n220), .A2(cmd_paddr_q[3]), .B1(n221), 
        .B2(m_paddr_o[3]), .X(n60) );
  sky130_fd_sc_hd__a22o_1 U371 ( .A1(n220), .A2(cmd_paddr_q[2]), .B1(n221), 
        .B2(m_paddr_o[2]), .X(n59) );
  sky130_fd_sc_hd__a22o_1 U372 ( .A1(n220), .A2(cmd_paddr_q[1]), .B1(n221), 
        .B2(m_paddr_o[1]), .X(n58) );
  sky130_fd_sc_hd__a22o_1 U373 ( .A1(n220), .A2(cmd_paddr_q[0]), .B1(n221), 
        .B2(m_paddr_o[0]), .X(n57) );
  sky130_fd_sc_hd__a22o_1 U374 ( .A1(n220), .A2(cmd_pwdata_q[31]), .B1(n221), 
        .B2(m_pwdata_o[31]), .X(n56) );
  sky130_fd_sc_hd__a22o_1 U375 ( .A1(n220), .A2(cmd_pwdata_q[30]), .B1(n221), 
        .B2(m_pwdata_o[30]), .X(n55) );
  sky130_fd_sc_hd__a22o_1 U376 ( .A1(n220), .A2(cmd_pwdata_q[29]), .B1(n221), 
        .B2(m_pwdata_o[29]), .X(n54) );
  sky130_fd_sc_hd__a22o_1 U377 ( .A1(n220), .A2(cmd_pwdata_q[28]), .B1(n221), 
        .B2(m_pwdata_o[28]), .X(n53) );
  sky130_fd_sc_hd__a22o_1 U378 ( .A1(n220), .A2(cmd_pwdata_q[27]), .B1(n221), 
        .B2(m_pwdata_o[27]), .X(n52) );
  sky130_fd_sc_hd__a22o_1 U379 ( .A1(n220), .A2(cmd_pwdata_q[26]), .B1(n221), 
        .B2(m_pwdata_o[26]), .X(n51) );
  sky130_fd_sc_hd__a22o_1 U380 ( .A1(n220), .A2(cmd_pwdata_q[25]), .B1(n221), 
        .B2(m_pwdata_o[25]), .X(n50) );
  sky130_fd_sc_hd__a22o_1 U381 ( .A1(n220), .A2(cmd_pwdata_q[24]), .B1(n221), 
        .B2(m_pwdata_o[24]), .X(n49) );
  sky130_fd_sc_hd__a22o_1 U382 ( .A1(n220), .A2(cmd_pwdata_q[23]), .B1(n221), 
        .B2(m_pwdata_o[23]), .X(n48) );
  sky130_fd_sc_hd__a22o_1 U383 ( .A1(n220), .A2(cmd_pwdata_q[22]), .B1(n221), 
        .B2(m_pwdata_o[22]), .X(n47) );
  sky130_fd_sc_hd__a22o_1 U384 ( .A1(n220), .A2(cmd_pwdata_q[21]), .B1(n221), 
        .B2(m_pwdata_o[21]), .X(n46) );
  sky130_fd_sc_hd__a22o_1 U385 ( .A1(n220), .A2(cmd_pwdata_q[20]), .B1(n221), 
        .B2(m_pwdata_o[20]), .X(n45) );
  sky130_fd_sc_hd__a22o_1 U386 ( .A1(n220), .A2(cmd_pwdata_q[19]), .B1(n221), 
        .B2(m_pwdata_o[19]), .X(n44) );
  sky130_fd_sc_hd__a22o_1 U387 ( .A1(n220), .A2(cmd_pwdata_q[18]), .B1(n221), 
        .B2(m_pwdata_o[18]), .X(n43) );
  sky130_fd_sc_hd__a22o_1 U388 ( .A1(n222), .A2(cmd_pwdata_q[17]), .B1(n221), 
        .B2(m_pwdata_o[17]), .X(n42) );
  sky130_fd_sc_hd__a22o_1 U389 ( .A1(n222), .A2(cmd_pwdata_q[16]), .B1(n221), 
        .B2(m_pwdata_o[16]), .X(n41) );
  sky130_fd_sc_hd__a22o_1 U390 ( .A1(n220), .A2(cmd_pwdata_q[15]), .B1(n221), 
        .B2(m_pwdata_o[15]), .X(n40) );
  sky130_fd_sc_hd__a22o_1 U391 ( .A1(n222), .A2(cmd_pwdata_q[14]), .B1(n221), 
        .B2(m_pwdata_o[14]), .X(n39) );
  sky130_fd_sc_hd__a22o_1 U392 ( .A1(n222), .A2(cmd_pwdata_q[13]), .B1(n221), 
        .B2(m_pwdata_o[13]), .X(n38) );
  sky130_fd_sc_hd__a22o_1 U393 ( .A1(n222), .A2(cmd_pwdata_q[12]), .B1(n221), 
        .B2(m_pwdata_o[12]), .X(n37) );
  sky130_fd_sc_hd__a22o_1 U394 ( .A1(n222), .A2(cmd_pwdata_q[11]), .B1(n221), 
        .B2(m_pwdata_o[11]), .X(n36) );
  sky130_fd_sc_hd__a22o_1 U395 ( .A1(n222), .A2(cmd_pwdata_q[10]), .B1(n221), 
        .B2(m_pwdata_o[10]), .X(n35) );
  sky130_fd_sc_hd__a22o_1 U396 ( .A1(n222), .A2(cmd_pwdata_q[9]), .B1(n221), 
        .B2(m_pwdata_o[9]), .X(n34) );
  sky130_fd_sc_hd__a22o_1 U397 ( .A1(n222), .A2(cmd_pwdata_q[8]), .B1(n221), 
        .B2(m_pwdata_o[8]), .X(n33) );
  sky130_fd_sc_hd__a22o_1 U398 ( .A1(n222), .A2(cmd_pwdata_q[7]), .B1(n221), 
        .B2(m_pwdata_o[7]), .X(n32) );
  sky130_fd_sc_hd__a22o_1 U399 ( .A1(n222), .A2(cmd_pwdata_q[6]), .B1(n221), 
        .B2(m_pwdata_o[6]), .X(n31) );
  sky130_fd_sc_hd__a22o_1 U400 ( .A1(n222), .A2(cmd_pwdata_q[5]), .B1(n221), 
        .B2(m_pwdata_o[5]), .X(n30) );
  sky130_fd_sc_hd__a22o_1 U401 ( .A1(n222), .A2(cmd_pwdata_q[4]), .B1(n221), 
        .B2(m_pwdata_o[4]), .X(n29) );
  sky130_fd_sc_hd__a22o_1 U402 ( .A1(n222), .A2(cmd_pwdata_q[3]), .B1(n221), 
        .B2(m_pwdata_o[3]), .X(n28) );
  sky130_fd_sc_hd__a22o_1 U403 ( .A1(n222), .A2(cmd_pwdata_q[2]), .B1(n221), 
        .B2(m_pwdata_o[2]), .X(n27) );
  sky130_fd_sc_hd__a22o_1 U404 ( .A1(n222), .A2(cmd_pwdata_q[1]), .B1(n221), 
        .B2(m_pwdata_o[1]), .X(n26) );
  sky130_fd_sc_hd__a22o_1 U405 ( .A1(n222), .A2(cmd_pwdata_q[0]), .B1(n221), 
        .B2(m_pwdata_o[0]), .X(n25) );
  sky130_fd_sc_hd__conb_1 u_s_rst_sync_U3 ( .HI(u_s_rst_sync_n2) );
  sky130_fd_sc_hd__dfrtp_2 u_s_rst_sync_sync_q_reg_1_ ( .D(
        u_s_rst_sync_sync_q[0]), .CLK(s_clk_i), .RESET_B(
        u_s_rst_sync_rst_n_async), .Q(u_s_rst_sync_sync_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 u_s_rst_sync_sync_q_reg_0_ ( .D(u_s_rst_sync_n2), 
        .CLK(s_clk_i), .RESET_B(u_s_rst_sync_rst_n_async), .Q(
        u_s_rst_sync_sync_q[0]) );
  sky130_fd_sc_hd__mux2_2 u_s_rst_sync_U4 ( .A0(s_rst_n_i), .A1(scan_rst_ni), 
        .S(scanmode_i), .X(u_s_rst_sync_rst_n_async) );
  sky130_fd_sc_hd__mux2_2 u_s_rst_sync_U5 ( .A0(u_s_rst_sync_sync_q[1]), .A1(
        scan_rst_ni), .S(scanmode_i), .X(s_rst_sync_n) );
  sky130_fd_sc_hd__conb_1 u_m_rst_sync_U3 ( .HI(u_m_rst_sync_n1) );
  sky130_fd_sc_hd__dfrtp_2 u_m_rst_sync_sync_q_reg_1_ ( .D(
        u_m_rst_sync_sync_q[0]), .CLK(m_clk_i), .RESET_B(
        u_m_rst_sync_rst_n_async), .Q(u_m_rst_sync_sync_q[1]) );
  sky130_fd_sc_hd__dfrtp_2 u_m_rst_sync_sync_q_reg_0_ ( .D(u_m_rst_sync_n1), 
        .CLK(m_clk_i), .RESET_B(u_m_rst_sync_rst_n_async), .Q(
        u_m_rst_sync_sync_q[0]) );
  sky130_fd_sc_hd__mux2_2 u_m_rst_sync_U4 ( .A0(rst_both_n), .A1(scan_rst_ni), 
        .S(scanmode_i), .X(u_m_rst_sync_rst_n_async) );
  sky130_fd_sc_hd__mux2_2 u_m_rst_sync_U5 ( .A0(u_m_rst_sync_sync_q[1]), .A1(
        scan_rst_ni), .S(scanmode_i), .X(m_rst_sync_n) );
  sky130_fd_sc_hd__dfrtp_2 u_m_rst_status_sync_sync_q_reg_1__0_ ( .D(
        u_m_rst_status_sync_sync_q_0__0_), .CLK(s_clk_i), .RESET_B(n224), .Q(
        m_in_rst_s) );
  sky130_fd_sc_hd__dfrbp_2 u_m_rst_status_sync_sync_q_reg_0__0_ ( .D(n197), 
        .CLK(s_clk_i), .RESET_B(n224), .Q(u_m_rst_status_sync_sync_q_0__0_) );
  sky130_fd_sc_hd__dfrtp_2 u_req_sync_sync_q_reg_0__0_ ( .D(req_q), .CLK(
        m_clk_i), .RESET_B(n223), .Q(u_req_sync_sync_q_0__0_) );
  sky130_fd_sc_hd__dfrbp_2 u_req_sync_sync_q_reg_1__0_ ( .D(
        u_req_sync_sync_q_0__0_), .CLK(m_clk_i), .RESET_B(n223), .Q(req_m) );
  sky130_fd_sc_hd__dfrtp_2 u_ack_sync_sync_q_reg_1__0_ ( .D(
        u_ack_sync_sync_q_0__0_), .CLK(s_clk_i), .RESET_B(n224), .Q(ack_s) );
  sky130_fd_sc_hd__dfrtp_2 u_ack_sync_sync_q_reg_0__0_ ( .D(ack_q), .CLK(
        s_clk_i), .RESET_B(n224), .Q(u_ack_sync_sync_q_0__0_) );
endmodule

