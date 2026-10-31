#### OpenROAD (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +3.1230 | 0.000 | 0 (0 / 0) | +0.5257 | 0.000 | 0 (0 / 0) | 3613 | 268 | `apb_paddr_i[4]` -> `_49279_/D` |
| nom_ss_100C_1v60 | -3.4259 | -1192.959 | 1014 (986 / 28) | +0.9777 | 0.000 | 0 (0 / 0) | 52862 | 290 | `_53923_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.9284 | 0.000 | 0 (0 / 0) | +0.2425 | 0.000 | 0 (0 / 0) | 1429 | 262 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.1861 | 0.000 | 0 (0 / 0) | +0.5420 | 0.000 | 0 (0 / 0) | 2422 | 258 | `apb_paddr_i[4]` -> `_49279_/D` |
| min_ss_100C_1v60 | -2.7770 | -774.753 | 788 (761 / 27) | +1.1903 | 0.000 | 0 (0 / 0) | 37292 | 282 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.0664 | 0.000 | 0 (0 / 0) | +0.2496 | 0.000 | 0 (0 / 0) | 888 | 255 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +3.0186 | 0.000 | 0 (0 / 0) | +0.4952 | 0.000 | 0 (0 / 0) | 6230 | 277 | `apb_paddr_i[4]` -> `_49279_/D` |
| max_ss_100C_1v60 | -4.3264 | -1880.283 | 1155 (1121 / 34) | +0.7070 | 0.000 | 0 (0 / 0) | 71277 | 302 | `_52681_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.7132 | 0.000 | 0 (0 / 0) | +0.2122 | 0.000 | 0 (0 / 0) | 2408 | 268 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

#### ICC2 (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +0.0855 | 0.000 | 0 (0 / 0) | +0.0013 | 0.000 | 0 (0 / 0) | 855 | 172 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ss_100C_1v60 | -14.3315 | -4682.344 | 1383 (1323 / 60) | -0.4451 | -6.160 | 28 (0 / 28) | 39542 | 179 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +3.3352 | 0.000 | 0 (0 / 0) | -0.0949 | -4.577 | 117 (117 / 0) | 110 | 165 | `u_core/u_icache_gen_data_sram_1__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_1__4_/D` |
| min_tt_025C_1v80 | +0.2274 | 0.000 | 0 (0 / 0) | +0.0075 | 0.000 | 0 (0 / 0) | 193 | 168 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.0743 | -3935.219 | 1209 (1183 / 26) | -0.2941 | -2.833 | 20 (0 / 20) | 34569 | 173 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +3.5241 | 0.000 | 0 (0 / 0) | -0.0886 | -4.172 | 112 (112 / 0) | 68 | 158 | `u_core/u_icache_gen_data_sram_1__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_1__4_/D` |
| max_tt_025C_1v80 | -0.3612 | -3.590 | 25 (25 / 0) | -0.0104 | -0.019 | 3 (3 / 0) | 6329 | 178 | `u_core/u_icache_ic_addr_q_reg_4_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -14.6682 | -5831.582 | 1703 (1542 / 161) | -0.6278 | -11.767 | 44 (0 / 44) | 45122 | 186 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +3.0773 | 0.000 | 0 (0 / 0) | -0.1023 | -5.328 | 121 (121 / 0) | 358 | 173 | `u_core/u_icache_gen_data_sram_1__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_1__4_/D` |

#### Innovus (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +1.4581 | 0.000 | 0 (0 / 0) | -0.2657 | -0.266 | 1 (0 / 1) | 266 | 203 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| nom_ss_100C_1v60 | -7.8723 | -1184.734 | 820 (741 / 79) | -1.7449 | -12.714 | 18 (0 / 18) | 19334 | 243 | `u_core/u_if_if_id_reg_o_reg[instruction][1]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| nom_ff_n40C_1v95 | +3.9527 | 0.000 | 0 (0 / 0) | +0.0154 | 0.000 | 0 (0 / 0) | 266 | 160 | `apb_paddr_i[1]` -> `apb_prdata_o_reg[5]/D` |
| min_tt_025C_1v80 | +2.0943 | 0.000 | 0 (0 / 0) | -0.1193 | -0.119 | 1 (0 / 1) | 266 | 170 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| min_ss_100C_1v60 | -7.1466 | -819.460 | 564 (497 / 67) | -1.5478 | -10.390 | 16 (0 / 16) | 11921 | 240 | `u_core/u_if_if_id_reg_o_reg[instruction][1]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| min_ff_n40C_1v95 | +4.3000 | 0.000 | 0 (0 / 0) | +0.0121 | 0.000 | 0 (0 / 0) | 266 | 158 | `apb_paddr_i[1]` -> `apb_prdata_o_reg[5]/D` |
| max_tt_025C_1v80 | +0.5361 | 0.000 | 0 (0 / 0) | -0.4618 | -0.933 | 5 (0 / 5) | 312 | 230 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| max_ss_100C_1v60 | -8.8230 | -1856.757 | 1143 (1050 / 93) | -2.0222 | -16.381 | 23 (0 / 23) | 28958 | 243 | `u_core/u_if_if_id_reg_o_reg[instruction][1]/CLK` -> `u_core/u_if_pc_q_reg[30]/D` |
| max_ff_n40C_1v95 | +3.4626 | 0.000 | 0 (0 / 0) | +0.0178 | 0.000 | 0 (0 / 0) | 273 | 166 | `apb_paddr_i[0]` -> `apb_prdata_o_reg[0]/D` |

#### OpenROAD (OpenRCX SPEF)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

