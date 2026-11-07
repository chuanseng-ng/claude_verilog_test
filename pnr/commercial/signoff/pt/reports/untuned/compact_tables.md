#### OpenROAD (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +3.0493 | 0.000 | 0 (0 / 0) | -0.3470 | -4.579 | 62 (0 / 62) | 4143 | 271 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| nom_ss_100C_1v60 | -3.6789 | -1466.222 | 1130 (1055 / 75) | -0.8225 | -27.928 | 124 (0 / 124) | 58696 | 295 | `_51961_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.8917 | 0.000 | 0 (0 / 0) | -0.1524 | -0.673 | 9 (0 / 9) | 1584 | 265 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.6856 | 0.000 | 0 (0 / 0) | -0.0347 | -0.035 | 1 (0 / 1) | 1643 | 250 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_ss_100C_1v60 | -2.1167 | -448.660 | 645 (641 / 4) | -0.3414 | -0.663 | 5 (0 / 5) | 22611 | 267 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.1739 | 0.000 | 0 (0 / 0) | +0.0985 | 0.000 | 0 (0 / 0) | 649 | 248 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +2.1797 | 0.000 | 0 (0 / 0) | -0.6981 | -48.499 | 231 (0 / 231) | 10541 | 289 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| max_ss_100C_1v60 | -5.3352 | -3004.335 | 1480 (1376 / 104) | -1.3624 | -95.575 | 199 (0 / 199) | 88325 | 324 | `_51961_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.5418 | 0.000 | 0 (0 / 0) | -0.4315 | -8.831 | 90 (0 / 90) | 3190 | 276 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

#### ICC2 (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | -0.0909 | -0.160 | 2 (2 / 0) | -1.1597 | -171.277 | 432 (5 / 427) | 677 | 164 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| nom_ss_100C_1v60 | -14.9330 | -4572.401 | 1504 (1488 / 16) | -2.0797 | -399.996 | 468 (0 / 468) | 40243 | 166 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +2.6717 | 0.000 | 0 (0 / 0) | -0.7186 | -81.926 | 401 (98 / 303) | 33 | 161 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| min_tt_025C_1v80 | +0.3839 | 0.000 | 0 (0 / 0) | -0.9884 | -131.402 | 370 (1 / 369) | 36 | 154 | `u_core/ex1a_ex1b_reg_q_reg_immediate__0_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.4809 | -2971.842 | 842 (841 / 1) | -1.8059 | -336.688 | 467 (0 / 467) | 26975 | 156 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +3.1705 | 0.000 | 0 (0 / 0) | -0.5988 | -61.379 | 341 (98 / 243) | 24 | 152 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| max_tt_025C_1v80 | -1.4141 | -17.264 | 67 (67 / 0) | -1.3408 | -214.760 | 463 (15 / 448) | 11592 | 176 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -15.4061 | -7281.157 | 2293 (2225 / 68) | -2.3746 | -472.103 | 478 (0 / 478) | 49535 | 178 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +2.1312 | 0.000 | 0 (0 / 0) | -0.8512 | -107.907 | 436 (102 / 334) | 562 | 176 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |

#### Innovus b5c (StarRC)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

#### OpenROAD (OpenRCX SPEF)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +2.9768 | 0.000 | 0 (0 / 0) | -0.5197 | -30.138 | 192 (0 / 192) | 4166 | 270 | `_51959_/CLK` -> `axi_araddr_o[3]` |
| nom_ss_100C_1v60 | -3.5188 | -1156.629 | 1048 (968 / 80) | -1.1609 | -81.751 | 197 (0 / 197) | 49081 | 295 | `_53923_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.8218 | 0.000 | 0 (0 / 0) | -0.2793 | -4.202 | 50 (0 / 50) | 1953 | 262 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.4334 | 0.000 | 0 (0 / 0) | -0.3351 | -7.539 | 109 (0 / 109) | 2715 | 262 | `_51959_/CLK` -> `axi_araddr_o[3]` |
| min_ss_100C_1v60 | -2.6617 | -636.431 | 754 (686 / 68) | -0.8912 | -43.648 | 152 (0 / 152) | 30817 | 286 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.0251 | 0.000 | 0 (0 / 0) | -0.1377 | -0.672 | 15 (0 / 15) | 1167 | 254 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +2.5645 | 0.000 | 0 (0 / 0) | -0.6888 | -59.158 | 272 (0 / 272) | 6326 | 274 | `_51959_/CLK` -> `axi_araddr_o[3]` |
| max_ss_100C_1v60 | -4.2715 | -1757.610 | 1189 (1094 / 95) | -1.3806 | -116.593 | 226 (0 / 226) | 65290 | 304 | `_52681_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.7128 | 0.000 | 0 (0 / 0) | -0.4215 | -11.788 | 113 (0 / 113) | 2615 | 265 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

