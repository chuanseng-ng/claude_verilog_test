#### OpenROAD (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +3.1723 | 0.000 | 0 (0 / 0) | -0.3186 | -3.514 | 51 (0 / 51) | 3613 | 268 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| nom_ss_100C_1v60 | -3.4259 | -1221.518 | 1062 (987 / 75) | -0.8003 | -25.599 | 121 (0 / 121) | 52862 | 290 | `_53923_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.9284 | 0.000 | 0 (0 / 0) | -0.1361 | -0.524 | 8 (0 / 8) | 1429 | 262 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.5477 | 0.000 | 0 (0 / 0) | -0.1735 | -0.508 | 5 (0 / 5) | 2422 | 258 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| min_ss_100C_1v60 | -2.7770 | -776.630 | 800 (761 / 39) | -0.5877 | -7.358 | 78 (0 / 78) | 37292 | 282 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.0664 | 0.000 | 0 (0 / 0) | -0.0151 | -0.037 | 3 (0 / 3) | 888 | 255 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +2.6794 | 0.000 | 0 (0 / 0) | -0.5218 | -21.797 | 169 (0 / 169) | 6230 | 277 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| max_ss_100C_1v60 | -4.3264 | -1948.455 | 1207 (1122 / 85) | -1.0710 | -55.318 | 155 (0 / 155) | 71277 | 302 | `_52681_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.7132 | 0.000 | 0 (0 / 0) | -0.3071 | -3.293 | 43 (0 / 43) | 2408 | 268 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

#### ICC2 (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +0.0396 | 0.000 | 0 (0 / 0) | -1.1616 | -170.471 | 430 (5 / 425) | 550 | 163 | `u_core/u_mem_mem_wb_reg_o_reg_mem_rd_/CLK` -> `u_core/ex1a_ex1b_reg_q_reg_alu_result__31_/D` |
| nom_ss_100C_1v60 | -14.8826 | -4393.569 | 1444 (1430 / 14) | -2.0843 | -399.420 | 469 (0 / 469) | 39627 | 164 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +2.6919 | 0.000 | 0 (0 / 0) | -0.7199 | -81.440 | 401 (98 / 303) | 33 | 160 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| min_tt_025C_1v80 | +0.2632 | 0.000 | 0 (0 / 0) | -1.0840 | -151.758 | 408 (2 / 406) | 33 | 162 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.6982 | -3653.990 | 1139 (1138 / 1) | -1.9595 | -370.098 | 467 (0 / 467) | 34069 | 163 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +2.9099 | 0.000 | 0 (0 / 0) | -0.6607 | -70.842 | 371 (99 / 272) | 29 | 158 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| max_tt_025C_1v80 | -0.5253 | -1.739 | 7 (7 / 0) | -1.2702 | -196.398 | 454 (8 / 446) | 5933 | 166 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -15.1176 | -5670.440 | 1914 (1869 / 45) | -2.2498 | -440.292 | 476 (0 / 476) | 45120 | 168 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +2.3932 | 0.000 | 0 (0 / 0) | -0.8014 | -97.059 | 421 (100 / 321) | 248 | 164 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |

#### Innovus (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | -0.6170 | -1.713 | 5 (0 / 5) | -1.7960 | -92.027 | 209 (0 / 209) | 351 | 227 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |
| nom_ss_100C_1v60 | -7.8677 | -2937.521 | 1440 (1344 / 96) | -3.0103 | -266.967 | 383 (0 / 383) | 18557 | 266 | `u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| nom_ff_n40C_1v95 | +2.0348 | 0.000 | 0 (0 / 0) | -1.1639 | -45.321 | 89 (0 / 89) | 349 | 173 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |
| min_tt_025C_1v80 | +0.1491 | 0.000 | 0 (0 / 0) | -1.6534 | -94.678 | 259 (0 / 259) | 350 | 197 | `apb_prdata_o_reg[26]/CLK` -> `apb_prdata_o[26]` |
| min_ss_100C_1v60 | -7.1188 | -2157.166 | 1211 (1121 / 90) | -2.8015 | -278.716 | 413 (0 / 413) | 11553 | 263 | `u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| min_ff_n40C_1v95 | +2.7417 | 0.000 | 0 (0 / 0) | -1.0616 | -44.199 | 123 (0 / 123) | 345 | 164 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |
| max_tt_025C_1v80 | -1.8132 | -7.670 | 6 (0 / 6) | -1.9843 | -91.037 | 167 (0 / 167) | 382 | 254 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |
| max_ss_100C_1v60 | -8.8593 | -4084.506 | 1672 (1561 / 111) | -3.3086 | -261.192 | 367 (0 / 367) | 28217 | 267 | `u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| max_ff_n40C_1v95 | +0.9918 | 0.000 | 0 (0 / 0) | -1.3026 | -49.073 | 82 (0 / 82) | 357 | 186 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |

#### OpenROAD (OpenRCX SPEF)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

