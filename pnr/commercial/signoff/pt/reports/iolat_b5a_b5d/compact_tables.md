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
| nom_tt_025C_1v80 | +0.0396 | 0.000 | 0 (0 / 0) | -0.0165 | -0.032 | 5 (5 / 0) | 550 | 163 | `u_core/u_mem_mem_wb_reg_o_reg_mem_rd_/CLK` -> `u_core/ex1a_ex1b_reg_q_reg_alu_result__31_/D` |
| nom_ss_100C_1v60 | -14.8826 | -4434.190 | 1462 (1410 / 52) | -0.3063 | -3.310 | 22 (0 / 22) | 39627 | 164 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +2.6919 | 0.000 | 0 (0 / 0) | -0.0976 | -4.014 | 99 (99 / 0) | 33 | 160 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| min_tt_025C_1v80 | +0.2632 | 0.000 | 0 (0 / 0) | -0.0110 | -0.016 | 2 (2 / 0) | 33 | 162 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.6982 | -3686.387 | 1169 (1136 / 33) | -0.1815 | -0.954 | 11 (0 / 11) | 34069 | 163 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +2.9099 | 0.000 | 0 (0 / 0) | -0.0973 | -3.872 | 100 (100 / 0) | 29 | 158 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| max_tt_025C_1v80 | -0.5253 | -1.739 | 7 (7 / 0) | -0.0210 | -0.047 | 8 (8 / 0) | 5933 | 166 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -15.1176 | -5710.267 | 1901 (1869 / 32) | -0.4718 | -7.872 | 31 (0 / 31) | 45120 | 168 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +2.3932 | 0.000 | 0 (0 / 0) | -0.1059 | -4.355 | 101 (101 / 0) | 248 | 164 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |

#### Innovus (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +1.1610 | 0.000 | 0 (0 / 0) | -0.0180 | -0.018 | 1 (0 / 1) | 351 | 227 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |
| nom_ss_100C_1v60 | -7.8677 | -2897.333 | 1421 (1344 / 77) | -1.2323 | -19.425 | 37 (0 / 37) | 18557 | 266 | `u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| nom_ff_n40C_1v95 | +3.6420 | 0.000 | 0 (0 / 0) | +0.0273 | 0.000 | 0 (0 / 0) | 349 | 173 | `apb_paddr_i[1]` -> `apb_prdata_o_reg[0]/D` |
| min_tt_025C_1v80 | +1.7124 | 0.000 | 0 (0 / 0) | +0.1246 | 0.000 | 0 (0 / 0) | 350 | 197 | `apb_paddr_i[4]` -> `apb_prdata_o_reg[2]/D` |
| min_ss_100C_1v60 | -7.1188 | -2128.129 | 1189 (1121 / 68) | -1.0235 | -14.647 | 29 (0 / 29) | 11553 | 263 | `u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| min_ff_n40C_1v95 | +3.9459 | 0.000 | 0 (0 / 0) | +0.0242 | 0.000 | 0 (0 / 0) | 345 | 164 | `apb_paddr_i[4]` -> `apb_prdata_o_reg[11]/D` |
| max_tt_025C_1v80 | -0.0352 | -0.035 | 1 (0 / 1) | -0.2063 | -0.206 | 1 (0 / 1) | 382 | 254 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |
| max_ss_100C_1v60 | -8.8593 | -4027.202 | 1653 (1561 / 92) | -1.5306 | -27.326 | 39 (0 / 39) | 28217 | 267 | `u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| max_ff_n40C_1v95 | +2.7698 | 0.000 | 0 (0 / 0) | +0.0297 | 0.000 | 0 (0 / 0) | 357 | 186 | `apb_prdata_o_reg[14]/CLK` -> `apb_prdata_o[14]` |

#### OpenROAD (OpenRCX SPEF)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

