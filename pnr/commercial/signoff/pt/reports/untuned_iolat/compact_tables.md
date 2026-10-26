#### OpenROAD (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +3.0953 | 0.000 | 0 (0 / 0) | +0.5326 | 0.000 | 0 (0 / 0) | 4143 | 271 | `apb_paddr_i[4]` -> `_49279_/D` |
| nom_ss_100C_1v60 | -3.6789 | -1426.074 | 1084 (1054 / 30) | +0.9555 | 0.000 | 0 (0 / 0) | 58696 | 295 | `_51961_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.8917 | 0.000 | 0 (0 / 0) | +0.2473 | 0.000 | 0 (0 / 0) | 1584 | 265 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.2300 | 0.000 | 0 (0 / 0) | +0.5600 | 0.000 | 0 (0 / 0) | 1643 | 250 | `apb_paddr_i[4]` -> `_49279_/D` |
| min_ss_100C_1v60 | -2.1167 | -453.796 | 666 (641 / 25) | +1.3152 | 0.000 | 0 (0 / 0) | 22611 | 267 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.1739 | 0.000 | 0 (0 / 0) | +0.2614 | 0.000 | 0 (0 / 0) | 649 | 248 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +2.6595 | 0.000 | 0 (0 / 0) | +0.4962 | 0.000 | 0 (0 / 0) | 10541 | 289 | `_52681_/CLK` -> `_53323_/D` |
| max_ss_100C_1v60 | -5.3352 | -2883.810 | 1447 (1376 / 71) | +0.4156 | 0.000 | 0 (0 / 0) | 88325 | 324 | `_51961_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.5418 | 0.000 | 0 (0 / 0) | +0.2070 | 0.000 | 0 (0 / 0) | 3190 | 276 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

#### ICC2 (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | -0.0909 | -0.160 | 2 (2 / 0) | -0.0147 | -0.028 | 5 (5 / 0) | 677 | 164 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| nom_ss_100C_1v60 | -14.9330 | -4615.273 | 1519 (1464 / 55) | -0.3017 | -3.386 | 22 (0 / 22) | 40243 | 166 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +2.6717 | 0.000 | 0 (0 / 0) | -0.0908 | -4.068 | 99 (99 / 0) | 33 | 161 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| min_tt_025C_1v80 | +0.3839 | 0.000 | 0 (0 / 0) | -0.0027 | -0.003 | 1 (1 / 0) | 36 | 154 | `u_core/ex1a_ex1b_reg_q_reg_immediate__0_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.4809 | -2992.382 | 870 (841 / 29) | -0.0279 | -0.036 | 2 (0 / 2) | 26975 | 156 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +3.1705 | 0.000 | 0 (0 / 0) | -0.0887 | -3.692 | 101 (99 / 2) | 24 | 152 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| max_tt_025C_1v80 | -1.4141 | -17.264 | 67 (67 / 0) | -0.0191 | -0.107 | 15 (15 / 0) | 11592 | 176 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -15.4061 | -7306.531 | 2258 (2225 / 33) | -0.5966 | -12.385 | 40 (0 / 40) | 49535 | 178 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +2.1312 | 0.000 | 0 (0 / 0) | -0.1066 | -4.755 | 103 (103 / 0) | 562 | 176 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |

#### Innovus b5c (StarRC)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

#### OpenROAD (OpenRCX SPEF)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

