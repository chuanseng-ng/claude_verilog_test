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
| nom_tt_025C_1v80 | +0.0855 | 0.000 | 0 (0 / 0) | -1.2264 | -246.505 | 521 (0 / 521) | 855 | 172 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ss_100C_1v60 | -14.3315 | -4683.796 | 1360 (1324 / 36) | -2.2231 | -551.560 | 550 (0 / 550) | 39542 | 179 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +3.3352 | 0.000 | 0 (0 / 0) | -0.7755 | -112.884 | 534 (117 / 417) | 110 | 165 | `u_core/u_icache_gen_data_sram_1__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_1__4_/D` |
| min_tt_025C_1v80 | +0.2274 | 0.000 | 0 (0 / 0) | -1.1363 | -219.106 | 512 (0 / 512) | 193 | 168 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.0743 | -3936.416 | 1212 (1183 / 29) | -2.0721 | -509.332 | 547 (0 / 547) | 34569 | 173 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +3.5241 | 0.000 | 0 (0 / 0) | -0.7074 | -97.625 | 505 (112 / 393) | 68 | 158 | `u_core/u_icache_gen_data_sram_1__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_1__4_/D` |
| max_tt_025C_1v80 | -0.3612 | -3.590 | 25 (25 / 0) | -1.3561 | -282.442 | 538 (3 / 535) | 6329 | 178 | `u_core/u_icache_ic_addr_q_reg_4_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -14.6682 | -5805.738 | 1623 (1567 / 56) | -2.4058 | -602.195 | 555 (0 / 555) | 45122 | 186 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +3.0773 | 0.000 | 0 (0 / 0) | -0.8779 | -138.310 | 583 (121 / 462) | 358 | 173 | `u_core/u_icache_gen_data_sram_1__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_1__4_/D` |

#### Innovus (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | -0.3199 | -0.320 | 1 (0 / 1) | -2.0437 | -112.242 | 430 (0 / 430) | 266 | 203 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| nom_ss_100C_1v60 | -7.8723 | -1227.623 | 840 (741 / 99) | -3.5229 | -319.429 | 468 (0 / 468) | 19334 | 243 | `u_core/u_if_if_id_reg_o_reg[instruction][1]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| nom_ff_n40C_1v95 | +2.5403 | 0.000 | 0 (0 / 0) | -1.3494 | -46.931 | 191 (0 / 191) | 266 | 160 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| min_tt_025C_1v80 | +0.3163 | 0.000 | 0 (0 / 0) | -1.8973 | -111.649 | 429 (0 / 429) | 266 | 170 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| min_ss_100C_1v60 | -7.1466 | -850.739 | 579 (497 / 82) | -3.3258 | -317.894 | 468 (0 / 468) | 11921 | 240 | `u_core/u_if_if_id_reg_o_reg[instruction][1]/CLK` -> `u_core/u_if_pc_q_reg[31]/D` |
| min_ff_n40C_1v95 | +3.0470 | 0.000 | 0 (0 / 0) | -1.2376 | -41.848 | 188 (0 / 188) | 266 | 158 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| max_tt_025C_1v80 | -1.2419 | -2.583 | 3 (0 / 3) | -2.2398 | -115.322 | 401 (0 / 401) | 312 | 230 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |
| max_ss_100C_1v60 | -8.8789 | -1914.948 | 1174 (1050 / 124) | -3.8002 | -324.055 | 478 (0 / 478) | 28958 | 243 | `u_core/u_dcache_state_q_reg[2]/CLK` -> `axi_wdata_o[25]` |
| max_ff_n40C_1v95 | +1.7899 | 0.000 | 0 (0 / 0) | -1.4893 | -51.723 | 183 (0 / 183) | 273 | 166 | `apb_pslverr_o_reg/CLK` -> `apb_pslverr_o` |

#### OpenROAD (OpenRCX SPEF)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

