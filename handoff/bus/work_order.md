# Work order: authored chapters for the bus fabric and the memory map

Repo: `<repo>` (Windows host, MiKTeX, little free memory).
Templates: the CDC pilot work order (`scratchpad/pilot/work_order.md`, sections C.1-C.4, "Owner decisions") and
the PMU work order (`scratchpad/pmu/work_order.md`). The method, the macros, the tools, the archive procedure and
the PR procedure are the same. This order states only what differs or what is specific to this area. Read both
earlier orders and the three truth reviews (`pilot/p2/truth_review.md`, `pmu/truth_review.md`,
`pmu/prb/truth_review.md`) first: they list the errors that a first draft makes.
Executor: a Sonnet worker. Reviewer: an Opus agent that checks every authored statement against the RTL.
The primary planner verifies and commits. Cut each PR branch from fresh `origin/main`
(`git fetch`, then `git checkout -B <branch> origin/main`). Never commit to `main`.

Host rules (unchanged): one foreground command at a time. No simulators, no Docker, no `make` sim targets, no
mutation or formal runs. You may run the Python doc tools, `pytest tb/tests/test_docs_*.py`,
`python tools/verif/check_periph_filelists.py`, `python tools/verif/gen_filelist.py --check`,
`python tools/verif/check_upf.py -v`, and `python tools/docs/build_books.py` (one book per run, `--timeout 1800`).
Prefix shell commands with `rtk`; for exact grep output use `rtk proxy grep` or the Grep tool.
The content PRs change **no** file under `rtl/`, `pnr/`, `tb/`, `tools/` or `.github/` (the optional infrastructure
PR-0 in section 11 is the only exception, and only if the owner approves it).

Legend: **[V]** verified by the planner by reading the named file and symbol; **[Q]** the worker must find and
verify the answer before writing it; **[I]** inferred by the planner from the RTL, not measured by any test (the
text must say "derived from the RTL" or carry no number).

## Standing rules for this area (state them in your notes file and obey them in every sentence)

1. Every statement comes from the code (RTL, test, tool). Never from old book text, never from a source comment
   alone. Old text and comments are leads to check, nothing more. Section 9 lists old claims that are false.
2. A `test:` reference only when that test **fails if the rule alone is broken**. A test that only shows that a
   transfer completes does not prove an order, a priority, a concurrency or a latency. Otherwise write `review`
   and list the gap.
3. A test marked `expect_fail` is never a proof of a rule (it measures the opposite). Cite it in an Information
   note as a measurement.
4. There is no mutation script for this area. Do not write `mutation:`. If you predict by reading that a test
   kills a change, write "predicted by reading, not run".
5. State the coverage limit of each test: the unit benches use their own maps and sizes (for example the crossbar
   bench has 3 masters and 2 slaves, not 4 and 3), simulation is zero-delay, some tests use backdoor access.
6. Timing figures and cycle counts are derived cycle by cycle from the RTL and are labelled "derived". No test
   measures a fabric latency. Do not write a latency as measured.
7. AGENTS.md rule 6 ("a reset value must not advertise availability") is a defect class: for every module, write
   down what each ready output shows while `rst_n` is low (section 9.3 has the planner's table).
8. No power, area or timing result. No frequency. The caveats of AGENTS.md section 2 apply; this area quotes none
   of those figures.
9. "must" only inside `requirement` bodies. One statement per rule. A rule that has several parts with different
   verification is split.
10. Where a document and the RTL disagree on intent, report it in the PR description and do not decide alone
    (section 9.2; owner questions in section 12).
11. A cross-reference to a done area is a `\reqref{}` or `\cref{}`. Do not restate CDC bridge or PMU clamp
    behaviour.

---------------------------------------------------------------------------------------------------

## 1. Scope

### 1.1 Modules and instances (in scope)

All fabric modules are instantiated inside `soc_bus` (`u_bus` in `soc_top`), except the GPU instruction-fetch
adapter and the two memory slaves, which `soc_top` instantiates directly [V `rtl/soc/soc_bus.sv`, `rtl/soc/soc_top.sv`].

| Item | File | Instance (path in `soc_top`) | What the chapters describe |
|---|---|---|---|
| `soc_bus` | `rtl/soc/soc_bus.sv` | `u_bus` | Structural wrapper, no logic [V]. Topology, port groups, the fixed sizes from the packages. Not a module of its own in the DS; one "Fabric topology" section. |
| `axi4_crossbar` | `rtl/soc/axi4_crossbar.sv` | `u_bus.u_xbar` | 4 masters x 3 slaves in the SoC (`N_MASTERS` from `soc_top`, `SOC_N_SLAVES`=3); module defaults 3 x 2 [V]. Decode, per-slave engines, arbitration, decode-error engines, ID tagging. |
| `axi4_to_axilite` | `rtl/soc/axi4_to_axilite.sv` | `u_bus.u_periph_bridge` | Crossbar slave S2 to one AXI4-Lite master; burst split [V]. |
| `axi_lite_interconnect` | `rtl/soc/axi_lite_interconnect.sv` | `u_bus.u_axil_ic` | 1 master x 3 slaves (GPU, APB bridge, DMA) [V]. The package and some tests call it "ring"; it is a decoder/demux (no ring structure). Use "AXI-Lite interconnect"; mention once that the code calls it the ring. |
| `axil_to_apb` | `rtl/soc/axil_to_apb.sv` | `u_bus.u_axil_apb_bridge` | AXI-Lite slave to APB4 master, depth 1 [V]. |
| `apb_interconnect` | `rtl/soc/apb_interconnect.sv` | `u_bus.u_apb_ic` | 1 APB master x 14 APB slaves, combinational [V]. |
| `axilite_to_axi4` | `rtl/soc/axilite_to_axi4.sv` | `u_gif_adapter` | GPU instruction-fetch AXI-Lite read master to crossbar master M1, AR skid buffer [V]. |
| Packages | `rtl/soc/axi_pkg.sv`, `rtl/soc/soc_addr_map_pkg.sv`, `rtl/soc/soc_periph_map_pkg.sv` | - | Bus geometry and the memory map (the single source of truth, section 4). |
| Slave building blocks | `rtl/soc/apb4_register_bank.sv`, `rtl/soc/axi_lite_register_bank.sv` | inside every APB peripheral and the PMU / inside `dma_engine` (`u_regbank`) | Bus-side behaviour only (pready, pslverr, out-of-range, AW/W capture, strobes). Placement: owner question Q9. |
| `boot_rom` | `rtl/soc/boot_rom.sv` | `u_boot_rom` (S0) | Bus behaviour only: reads, SLVERR writes, 4 KB index. It has **no** DS or TM section today [V labels.tsv]; it gets one (Q9). |
| `sram_controller` | `rtl/soc/sram_controller.sv` | `u_sram` (S1) | **Out of scope as a module**: it keeps `ds:mod:sram-controller` and `tm:mod:sram-controller`. The bus chapter states only its memory-map row (decode window versus realised storage, aliasing) and cross-references it. |

Masters on the crossbar (bus-side contract only) [V `soc_top.sv`]:
M0 = CPU through `u_cpu_axi_cdc` (m face drives `xbar_m_*[0]`); M1 = GPU instruction fetch through `u_gif_adapter`;
M2 = GPU data (`u_gpu` `m_axi_*`; `awlen/arlen` tied 0, `wlast` tied 1, sizes 4 B, INCR, in `soc_top`);
M3 = DMA (`u_dma` `m_*`). Slaves of the AXI-Lite interconnect: slot 0 GPU control (`u_gpu` `s_axil_*`, only
`[11:0]` of the address connected), slot 1 `u_axil_apb_bridge`, slot 2 DMA control (`u_dma` `s_axil_*`, `[11:0]`).
APB slots 0-13: UART, SPI, timer, IRQ, PLL (through `u_apb_pll_cdc`), PMU, PLL2 (through `u_apb_pll2_cdc`), GPIO,
PWM, WDT, TRNG, I2C, CRYPTO, NPU; each gets `paddr[11:0]` [V].

Tests that are evidence (all confirmed to exist; function names in section 3). Abbreviations used in section 3
(expand them to full paths in the TeX; the checker needs full paths):
`X=tb/cocotb/soc/test_crossbar.py`, `XE=tb/cocotb/soc/test_crossbar_errors.py`,
`A2L=tb/cocotb/soc/test_axi4_to_axilite.py`, `L2A=tb/cocotb/soc/test_axilite_to_axi4.py`,
`IC=tb/cocotb/soc/test_axil_interconnect.py`, `FAB=tb/cocotb/soc/test_axil_apb_fabric.py`,
`L2P=tb/cocotb/soc/test_axil_to_apb.py`, `PIC=tb/cocotb/soc/test_apb_interconnect.py`,
`PRB=tb/cocotb/soc/test_apb4_register_bank.py`, `LRB=tb/cocotb/soc/test_register_bank.py`,
`ROM=tb/cocotb/soc/test_boot_rom.py`, `SOC=tb/cocotb/soc/test_soc_integration.py`,
`BOOT=tb/cocotb/soc/test_boot.py`.
All of these targets are in `SOC_CI_SUITES` of `tb/cocotb/soc/Makefile`: `crossbar` (runs both crossbar modules),
`register_bank`, `axil_interconnect`, `axil_apb_fabric`, `axi4_to_axilite`, `axilite_to_axi4`, `boot_rom`,
`apb4_register_bank`, `axil_to_apb`, `apb_interconnect`, `soc_boot`, `soc_integration` [V]. `soc_stress`
(`test_soc_stress.py`) is **not** in the CI list [V]; do not cite it as a CI gate.
Build points: `register_bank` and `apb4_register_bank` run at `ADDR_W=12` and `ADDR_W=5`; `apb_interconnect`
sweeps `N_SLAVES` in {1,2,7,8,9,13,14,15,16,17} with `APB_IC_OVERLAP=0` and has an overlap build for
`test_first_match_wins` [V Makefile; Q confirm the overlap build is in the same target].
Bench maps differ from the SoC map: `tb_axi4_crossbar.sv` (3 x 2, `SOC_SLV_BASE` truncated to ROM and SRAM),
`tb_axi_lite_interconnect.sv` (the SoC ring map, register-bank stubs with `BANK_AW=12`),
`tb_axil_apb_fabric.sv` (its own map: ring slot 0 scripted, APB slots 0-2 at 0x2000_2000/3000/4000,
0x2000_5000 unclaimed, 0x2000_8000 unmapped) [V headers]. Say which map each test uses.

### 1.2 Out of scope (cross-reference only, do not move or repeat)

- The CDC chapters: `async_axi_fifo` (`u_cpu_axi_cdc`, the M0 master face) and `apb_cdc_bridge`
  (`u_apb_pll_cdc`, `u_apb_pll2_cdc` behind APB slots 4 and 6; `u_apb_dbg_cdc` is the debug port, not on the
  bus). Cite `\reqref{DS-CDC-102}` / `DS-CDC-103` (error completion of a PLL-slot access), `DS-CDC-111`
  (configuration and debug only), `DS-CDC-154` (quiet outputs in reset), `tm:mod:apb-cdc-bridge`
  ("no timeout when `m_clk_i` stops"), `tm:mod:async-axi-fifo`.
- The power chapters: the ISO_GPU clamps on `xbar_m_*valid[2]`, `xbar_m_*ready[2]`, `gif_axil_arvalid`,
  `gif_axil_rready` and the ISO_CPU clamps (`\reqref{DS-PMU-103}`, `DS-PMU-104`); the hang of a GPU register
  access while the GPU is off (`\reqref{DS-PMU-185}`, measured by `test_p3_*` in
  `tb/cocotb/soc/test_soc_pmu_multiclock.py`, two of them `expect_fail`); the quiet-bus rule before a CPU
  power-down (`DS-PMU-182`); the reset of `rst_n_i` alone (`DS-PMU-186`). The bus chapter adds only what the
  fabric does in those cases (section 3.7, item BUS-213/214).
- `soc_top` as a module (`ds:mod:soc-top`, `tm:mod:soc-top`; their relocated blocks stay). `sram_controller` as a
  module. Masters and slaves as blocks (CPU, caches, GPU, DMA, peripherals, NPU, crypto, PLL).
- The register maps of the peripherals in the old memory-map document (`ds:mm:memory-map:*-registers*`) stay
  until their areas are authored (owner question Q3).
- Phase plans (`ds:ch:phase5-soc-integration-plan:*`, `ds:ch:phase6-ip-expansion-plan:*`), every `cr:*` record,
  `tm:suite:*` sections: stay; link them. The RTL headers of `axi4_crossbar.sv` and `axi_lite_interconnect.sv`
  cite "ds:ch:phase5-soc-integration-plan M3" (not a label; report it, do not fix it, section 10).

---------------------------------------------------------------------------------------------------

## 2. Requirement areas and IDs

Ledger rules (unchanged): `docs/manual/common/requirement_ids.tsv` is append-only (`id<TAB>status<TAB>first_file`);
IDs match `^DS-([A-Z][A-Z0-9]{1,7})-(\d{3})$`; never renumber, never reuse, retire by hand;
`check_requirements.py --write` appends and writes `docs/manual/ds/generated/requirements-<area>.tex`.
Verify methods accepted by the checker: `test:<path>::<func>` (top-level `def`/`async def` in a `.py` under
`tb/`), `mutation:<path>::<string literal>`, `check:<path>`, `formal:<path>` (file must exist), `review`
[V `tools/docs/check_requirements.py::METHODS`, `check_ref`]. The ledger holds DS-CDC (54), DS-PMU (45),
DS-PWR (30) today [V].

Proposal (owner question Q1):
- **`DS-MAP-NNN`** - the memory map: regions, decode, unmapped addresses, storage behind each region, software
  rules. In the DS chapter section `ds:ch:mod-bus-fabric:map` (or the re-authored `ds:ch:memory-map`, Q3).
  Blocks: 001-019 regions and decode; 020-039 unmapped addresses and decode errors; 040-059 storage and
  sub-word behaviour of the slaves; 060-079 software rules.
- **`DS-BUS-NNN`** - the fabric. In the new DS chapter `ds:ch:mod-bus-fabric`.
  Blocks: 001-019 topology, clocks, resets, IDs; 020-059 `axi4_crossbar`; 060-079 `axilite_to_axi4`;
  080-109 `axi4_to_axilite`; 110-139 `axi_lite_interconnect`; 140-169 `axil_to_apb`; 170-189 `apb_interconnect`;
  190-209 slave building blocks and `boot_rom`; 210-239 contract on masters and slaves (integration rules).
Two areas give two map tables (`tab:ds:req:map-map` - pick a better slug such as `tab:ds:req:memmap-map` - and
`tab:ds:req:bus-map`).

---------------------------------------------------------------------------------------------------

## 3. Draft requirement list

Marks: **T** tested (the cited test fails if the rule alone is broken, judged by reading the test body),
**C** checked by a tool, **R** review only, **O** pending an owner decision. Every function named below was
confirmed with Grep as a top-level `async def` and its body was read [V] unless marked [Q]. The code fact is for
your notes file and the reviewer; the TeX never cites a line number.

### 3.1 DS-MAP: regions and decode (001-019)

- **DS-MAP-001 T** The crossbar decodes three regions: boot ROM 0x0000_1000-0x0000_1FFF to S0, SRAM
  0x0000_2000-0x0FFF_FFFF to S1, peripherals 0x2000_1000-0x2001_0FFF to S2. Fact: `soc_addr_map_pkg::ROM_*`,
  `SRAM_*`, `PERIPH_*`, `SOC_SLV_BASE/LIMIT`; `soc_bus` passes them to `u_xbar`.
  verify `test:X::test_routing_and_decerr; test:SOC::test_soc_gpu_walk_both_masters`. Limit: the unit bench has
  only S0 and S1; S2 is shown only at SoC level (gpu walk phase C writes and reads the timer through M2).
- **DS-MAP-002 T** Inside the peripheral region the AXI-Lite interconnect selects GPU control at
  0x2000_1000-0x2000_1FFF, DMA control at 0x2000_5000-0x2000_5FFF, and the APB bridge for the rest of
  0x2000_2000-0x2001_0FFF. Fact: `AXIL_SLV_BASE/LIMIT`; `decode` keeps the last match, so slot 2 (DMA) overrides
  slot 1 inside the DMA page. verify `test:IC::test_route_and_isolation`. Predicted by reading: with a first-match
  decode the DMA write lands at offset 0 of the APB-bridge stub (`BANK_AW=12`) and the read-back of the bridge
  base fails.
- **DS-MAP-003 T** The APB bridge window holds 14 slots of 4 KB at the bases of table T-MAP (section 4).
  Fact: `soc_periph_map_pkg::APB_*_BASE/LIMIT`, `APB_SLV_BASE/LIMIT`. verify `test:SOC::test_soc_register_walk`
  [Q confirm from `soc_reg_fw.py` that the walk covers all 14 APB windows and that a slot routed to the wrong
  peripheral fails a check; if one window has no checkable register, say so].
- **DS-MAP-004 R** Every 4 KB page of the peripheral region has exactly one slave after the override of
  DS-MAP-002, so no address in that region reaches the decode-error path of the AXI-Lite interconnect or of the
  APB interconnect. Fact: derived from the two packages [I]; the waiver `soc_bus | toggle | ^apb_m_pslverr`
  in `tools/verif/coverage_waivers.txt` records the same conclusion as an owner decision ("waive, do not change
  the map"). verify `review` (becomes `check:` if PR-0 adds the map checker, Q2).
- **DS-MAP-005 R** The decode uses the address of the first beat only. A burst that starts inside a region and
  runs past its end goes to the slave of the first beat. Fact: `axi4_crossbar` decodes `m_awaddr/m_araddr` in
  `W_IDLE/R_IDLE` and latches the grant. verify `review`. Gap: no test (4 KB boundary).

### 3.2 DS-MAP: unmapped addresses (020-039)

- **DS-MAP-020 T** A read of an address outside the three crossbar regions completes with ARLEN+1 R beats, each
  DECERR with data 0, RLAST on the last beat only. Fact: `drstate`, `dr_len`, `dr_cnt`, `_m_rdata = '0`.
  verify `test:XE::test_decerr_read_bursts; test:SOC::test_soc_gpu_walk_both_masters`.
- **DS-MAP-021 T** A write to such an address takes every W beat up to WLAST and then completes with one B,
  DECERR. Fact: `dwstate` DW_DATA sinks until `m_wvalid && m_wlast`. verify `test:XE::test_decerr_write_bursts;
  test:SOC::test_soc_dma_walk_rom_write_and_decode_errors`.
- **DS-MAP-022 T** No beat of an access to an unmapped address reaches a slave. verify
  `test:XE::test_decerr_read_bursts; test:XE::test_decerr_write_bursts` (the `Watch` on the six slave valids).
- **DS-MAP-023 T** The unmapped ranges are 0x0000_0000-0x0000_0FFF, 0x1000_0000-0x2000_0FFF and
  0x2001_1000-0xFFFF_FFFF. verify `test:XE::test_decerr_read_bursts` (unit: 0x0, 0x0FFC, 0x1000_0000,
  0xFFFF_FFF0), `test:SOC::test_soc_dma_walk_rom_write_and_decode_errors` (DMA: 0x1000_0000, 0x2002_0000,
  0x4000_0000, 0x8000_0000 per `integ_fw/gen_integ_hex.py::WALK_DECERR_ADDRS`),
  `test:SOC::test_soc_gpu_walk_both_masters` (0x1000_0000, 0x8000_0000 loads; 0x4000_0000, 0x2001_1000 stores).
  Limit: the range 0x2000_0000-0x2000_0FFF has no SoC-level test [Q confirm]; only the bench of the AXI-Lite
  interconnect probes 0x2000_0000, which in the SoC never reaches it. The unit bench address 0x2000_1000 is
  unmapped only in that 2-slave bench; in the SoC it is the GPU. Do not quote it as an SoC unmapped address.
- **DS-MAP-024 R** The fabric has no other default slave that the SoC map can reach: the AXI-Lite interconnect
  returns DECERR and the APB interconnect returns PSLVERR (then SLVERR) only for addresses that the crossbar does
  not route to them (DS-MAP-004). verify `review`. Put the module-level behaviour in DS-BUS-111/172.

### 3.3 DS-MAP: storage and sub-word behaviour (040-059)

- **DS-MAP-040 T** A write to the boot ROM completes with SLVERR and does not change the ROM. Fact:
  `boot_rom` `s_bresp = AXI_RESP_SLVERR`, write data unused. verify
  `test:ROM::test_write_burst_is_sunk_and_answered_slverr; test:ROM::test_write_partial_strobes_do_not_modify_rom;
  test:SOC::test_soc_dma_walk_rom_write_and_decode_errors`.
- **DS-MAP-041 T** The boot ROM index is address bits [11:2]; the 4 KB repeat inside the index width. Fact:
  `r_idx = r_addr_q[ADDR_LSB +: IDX_W]`, `MEM_WORDS=1024` in `soc_top`. verify
  `test:ROM::test_read_index_is_masked_to_rom_depth`. Limit: inside the SoC the crossbar sends only
  0x1000-0x1FFF to the ROM, so a repeat is seen only when a burst runs past the region end (DS-MAP-005).
- **DS-MAP-042 O** The SRAM region decodes 256 MB onto `SRAM_MEM_WORDS` words (default 1024 = 4 KB in `soc_top`;
  module default 4096; `SRAM_SKY130` requires 1024). The word index is `(addr - SRAM_BASE)[2 +: IDX_W]`, so the
  storage repeats every `SRAM_MEM_WORDS*4` bytes. Fact: `soc_top::SRAM_MEM_WORDS`,
  `sram_controller::word_index`. Measured: `test:SOC::test_soc_dma_walk_rom_write_and_decode_errors` (alias walk),
  `test:SOC::test_soc_gpu_walk_both_masters` (phase A). **Owner question Q5**: is the repeat specified, or is only
  the first `SRAM_MEM_WORDS*4` bytes defined? Write the TM fact now; write the DS rule after Q5.
- **DS-MAP-043 T** In a peripheral slot, a word with no register reads 0 and a write to it is dropped, with an
  OKAY response. Fact: `apb4_register_bank` (`< N_REGS` compares, `pslverr = 1'b0`); `axi_lite_register_bank`.
  verify `test:PRB::test_out_of_range; test:PRB::test_every_out_of_range_address_bit;
  test:LRB::test_out_of_range; test:SOC::test_soc_dma_walk_rom_write_and_decode_errors` (unaligned reads of an
  unmapped timer word read 0). Exception: the PLL slots (DS-BUS-195).
- **DS-MAP-044 T** The peripherals ignore address bits [1:0]: a byte offset +1 to +3 addresses the register at +0.
  Fact: `addr_word = paddr[ADDR_W-1:2]`. verify `test:SOC::test_soc_gpu_walk_both_masters` (phase F, PLL1 window
  only). Limit: one window at SoC level; register-bank unit tests [Q find one that drives non-zero paddr[1:0]].
- **DS-MAP-045 R** The data cache treats every address at or above `MMIO_BASE` (0x2000_0000) as uncached. Fact:
  `rv32i_dcache.sv` compares with `soc_addr_map_pkg::MMIO_BASE`. verify `review` [Q find a cache test that fails
  if the bypass moves; if none, keep review]. Note for the TM: the instruction cache has no such bypass [Q].

### 3.4 DS-MAP: software rules (060-079)

- **DS-MAP-060 T** After reset the CPU fetches its first instruction at 0x0000_1000, the base of the boot ROM.
  Fact: `soc_top` `.RESET_PC (32'h0000_1000)`; `rv32i_cpu_top` default is 0x0000_0000. verify
  `test:BOOT::test_boot_pc_scoreboard` [Q confirm that the golden PC stream starts at 0x1000 and that a wrong
  reset PC fails it].
- **DS-MAP-061 R** Software accesses a peripheral register with a 32-bit aligned word access. Reason: bits [1:0]
  are ignored (DS-MAP-044) and the write strobes select the bytes. verify `review`.
- **DS-MAP-062 O** Software does not use SRAM addresses at or above `SRAM_BASE + SRAM_MEM_WORDS*4` (only if Q5 = a).
- **DS-MAP-063 R** The debug APB3 port of the CPU is not in the bus address space; a bus access to
  0x2000_0000-0x2000_0FFF gets DECERR. Fact: `soc_top` `apb_paddr_i[11:0]` top-level port into `u_apb_dbg_cdc`;
  crossbar map. verify `review` (no SoC-level test of 0x2000_0xxx, DS-MAP-023).

### 3.5 DS-BUS: topology, clocks, resets, IDs (001-019)

- **DS-BUS-001 R** All modules of the fabric, `u_gif_adapter`, `u_boot_rom` and `u_sram` run on `core_clk` and
  reset on `core_rst_n`. Fact: `soc_top` port maps of `u_bus`, `u_gif_adapter`, `u_boot_rom`, `u_sram`. verify
  `review`. Information: the only fabric endpoints in other domains are behind the CDC bridges (cross-reference).
- **DS-BUS-002 R** The crossbar has the masters M0 CPU, M1 GPU instruction fetch, M2 GPU data, M3 DMA, and the
  slaves S0 boot ROM, S1 SRAM, S2 peripheral bridge. verify `review` (structure; the gpu walk scores M1 and M2 by
  index, which supports it).
- **DS-BUS-003 R** The master ports of the crossbar carry no ID. Towards a slave the crossbar drives AWID and
  ARID with the master index; it routes responses by its grant register and ignores BID and RID. Fact:
  `_s_awid[s] = IW'(wsel[s])`, `s_bid`/`s_rid` under `lint_off UNUSEDSIGNAL`. verify `review`. Gap: no test checks
  the slave-side ID value [V grep of the crossbar tests and `axi4_fabric_bfm.py` found no awid/arid check].
  Information: `u_gif_adapter` drives `m_axi_arid = MASTER_ID`, but `soc_top` does not connect `gif_axi_arid` to
  the crossbar [V], so that ID has no effect.
- **DS-BUS-004 R** `AXI_ID_WIDTH` is at least `$clog2(N_MASTERS)`. Fact: `axi_pkg` comment "`>= clog2(masters)`";
  `IW'(wsel)` truncates silently. verify `review`. Gap: no elaboration guard.
- **DS-BUS-005 R** `N_MASTERS` of `soc_bus` equals the `N_MASTERS` localparam of `soc_top`. Fact: `soc_bus`
  parameter comment; `soc_top` passes it. verify `review`.

### 3.6 DS-BUS: `axi4_crossbar` (020-059)

- **DS-BUS-020 R** Each slave has one write engine and one read engine. An engine serves one transaction at a
  time and stays with the granted master from the address phase to the last response, so beats of two masters
  never interleave at one slave. Fact: `wstate/rstate`, `wsel/rsel`. verify `review`. Gap: no test runs bursts
  of two masters to one slave and checks beat order (test_arbitration_same_slave uses single beats and checks
  only completion).
- **DS-BUS-021 T** The read and write engines of a slave are independent: one master can have a read and a write
  in flight to the same slave at the same time. verify `test:X::test_concurrent_ar_aw_same_slave` (a hang is the
  failure; `with_timeout`).
- **DS-BUS-022 R** The crossbar keeps no order between a read and a write. A master that needs read-after-write
  order to one slave waits for B before it sends AR. Fact: header assumption; independent engines. verify
  `review`. (Cross-reference the same caller rule of `sram_controller`.)
- **DS-BUS-023 R** Engines of different slaves serve different masters at the same time. verify `review`. Gap:
  `test_concurrency_diff_slaves` and `test_slave_side_stalls_on_every_channel` pass also if the transfers were
  serialised; no test asserts overlap in time.
- **DS-BUS-024 R** Arbitration is fixed priority for each slave: when several masters request an idle engine in
  the same cycle, the lowest master index wins (M0 CPU first, M3 DMA last). Fact: `wr_arb_*` / `rd_arb_*` loops,
  `aw_priority_winner`. verify `review`. Gap: `test_arbitration_same_slave` checks only that both writes complete.
  Information [I]: a master that requests the same slave again in the cycle its engine goes idle wins again, so M0
  can hold off M1-M3 without limit (no fairness).
- **DS-BUS-025 T** The crossbar accepts the AR of the winning master in the cycle the read engine is idle and then
  drives the captured AR to the slave until the slave accepts it, so a one-cycle ARVALID is enough. Fact:
  `R_IDLE` early accept, `ar_*_q`, `R_AR`. verify `test:XE::test_one_cycle_arvalid_pulse_is_held_to_slow_slave`.
- **DS-BUS-026 R** The same holds for AW (`W_IDLE` early accept, `aw_*_q`, `W_AW`). verify `review`. Gap: no AW
  pulse test.
- **DS-BUS-027 R** The crossbar passes W beats to the slave only after the slave has accepted AW; a W beat
  offered before that waits. Fact: `_s_wvalid` only in `W_DATA`, `slv_wready` only in `W_DATA`. verify `review`
  [Q: check whether any crossbar test offers W before AW; the ROM test `test_w_before_aw_is_not_consumed` is for
  `boot_rom`, not for the crossbar].
- **DS-BUS-028 R** The write engine ends the data phase on the WLAST of the master; the read engine ends on the
  RLAST of the slave. The crossbar does not count beats. Fact: `W_DATA` exit `m_wlast[wsel]`, `R_DATA` exit
  `s_rlast`. verify `review`. Gap: no WLAST or RLAST error test.
- **DS-BUS-029 T** Every response of a slave (B, and each R beat) reaches the master that holds the engine, with
  the response code of the slave unchanged. verify `test:XE::test_slave_responses_are_steered_per_beat;
  test:X::test_response_steering`.
- **DS-BUS-030 T** A ready held low by a slave (AWREADY, WREADY, ARREADY, or late BVALID/RVALID) or by the master
  (BREADY, RREADY) stalls the transfer without loss, duplication or change of payload. verify `test:X::test_backpressure;
  test:XE::test_slave_side_stalls_on_every_channel` [Q confirm the BFM `viol` lists include payload stability].
- **DS-BUS-031 T** The decode-error engines are separate for each master; a decode error of one master does not
  delay the mapped traffic of another master. verify
  `test:XE::test_decerr_masters_run_concurrently_and_do_not_block_mapped` [Q: it shows completion and absence of
  leaks; check whether it shows "not delayed"; if not, reword to "does not block"].
- **DS-BUS-032 T** After a decode error the engines of that master accept the next transaction. verify
  `test:XE::test_decerr_then_mapped_on_same_master`.
- **DS-BUS-033 R** The crossbar has no timeout. An engine waits without limit for the slave and for BREADY or
  RREADY of the master; while it waits, that slave is not available to any master. Fact: no counter in the
  module. verify `review`. Cross-reference `\reqref{DS-PMU-185}` (measured hang through the AXI-Lite slot of the
  GPU) and section 3.10 item BUS-213.
- **DS-BUS-034 R** AxLEN, AxSIZE and AxBURST pass to the slave unchanged. verify `review`
  (`test_one_cycle_arvalid_pulse_is_held_to_slow_slave` checks `len` only).
- **DS-BUS-035 R** The reset of the crossbar is synchronous and returns every engine to idle. The crossbar has no
  drain step: a reset of the crossbar or of a slave during a burst can leave an engine and a slave out of step.
  Fact: `always_ff @(posedge clk)` with `if (!rst_n)`; `soc_top` caller rule. verify `review`. Gap: no
  reset-during-burst test for the crossbar.

### 3.7 DS-BUS: `axilite_to_axi4` (060-079)

- **DS-BUS-060 T** Each AXI-Lite read becomes one AXI4 read with ARLEN 0, ARSIZE 4 bytes, ARBURST INCR and ARID
  `MASTER_ID`. verify `test:L2A::test_pulse_is_held_until_accepted` (checks `(id, len, size, burst)` each cycle).
- **DS-BUS-061 T** A one-cycle ARVALID is held towards the crossbar with a stable address until ARREADY, and
  gives exactly one AR. verify `test:L2A::test_pulse_is_held_until_accepted;
  test:L2A::test_protocol_legal_master_that_holds_arvalid`.
- **DS-BUS-062 T** The adapter returns ARREADY to its master only in the cycle the crossbar accepts the AR.
  verify `test:L2A::test_pulse_is_held_until_accepted` (`sum(sar) == 1`).
- **DS-BUS-063 T** The R channel passes through without a register; RLAST is not used. verify
  `test:L2A::test_read_channel_passthrough`.
- **DS-BUS-064 T** The write channels never request, and BREADY is 1. verify `test:L2A::test_write_channels_tied_off`.
- **DS-BUS-065 T** A reset drops a held request. verify `test:L2A::test_reset_clears_held_request`.
- **DS-BUS-066 R** The master of the adapter does not raise a new ARVALID while a request is held: in that state
  the adapter returns ARREADY for the new valid but sends the held address [I from `s_axil_arready =
  m_axi_arready & ar_pending`]. verify `review`. [Q] check whether `gpu_compute_unit` can pulse a second fetch
  before the R of the first; if it cannot, say so in the Information note.
- **DS-BUS-067 R** The adapter resets with `core_rst_n`, not with the GPU domain reset, so a held request survives
  a GPU power-down. verify `review`. Cross-reference DS-PMU-104 (the clamp on `gif_axil_arvalid` and
  `gif_axil_rready`).

### 3.8 DS-BUS: `axi4_to_axilite` (080-109)

- **DS-BUS-080 T** A write burst of N beats becomes N AXI-Lite writes at the AWADDR, AWADDR+4, ... verify
  `test:A2L::test_write_burst_okay; test:A2L::test_write_stalls`.
- **DS-BUS-081 T** A read burst of N beats becomes N AXI-Lite reads at ARADDR, ARADDR+4, ... verify
  `test:A2L::test_read_burst` (N = 1, 2, 4, 8, 16).
- **DS-BUS-082 R** AxSIZE and AxBURST are not used: every burst is treated as INCR with 4-byte beats. Fact:
  `s_awsize/s_awburst/s_arsize/s_arburst` unused, `+ 32'd4`. verify `review`. Gap: no FIXED, WRAP or narrow test.
- **DS-BUS-083 R** The number of beats comes from AWLEN; WLAST is not used. verify `review`. Information [I]:
  with DS-BUS-028 a burst whose WLAST does not match AWLEN leaves the crossbar and the bridge out of step and
  hangs the peripheral path. No test.
- **DS-BUS-084 T** The bridge takes one W beat at a time and only after the AW. verify
  `test:A2L::test_w_offered_before_aw_is_not_consumed; test:A2L::test_write_burst_okay`.
- **DS-BUS-085 T** The single B comes after the B of the last AXI-Lite write, carries the AWID, and has the worst
  response of the burst (DECERR over SLVERR over OKAY); an error beat does not stop the burst. verify
  `test:A2L::test_write_response_accumulation; test:A2L::test_write_burst_okay`. Split if the reviewer asks
  (B position / BID / accumulation).
- **DS-BUS-086 T** Each R beat carries the response of its own AXI-Lite read, RID equals ARID, and RLAST is on
  the last beat only. verify `test:A2L::test_read_error_responses_are_per_beat; test:A2L::test_read_burst`.
- **DS-BUS-087 R** The write path and the read path are independent. verify `review`. Gap:
  `test_read_and_write_run_concurrently` passes also when serialised.
- **DS-BUS-088 T?** The bridge has at most one AXI-Lite write and one AXI-Lite read in flight. verify
  [Q `test:A2L::...` only if `AxiLiteSlave` in `axi4_fabric_bfm.py` records a violation for a second request;
  otherwise `review`].
- **DS-BUS-089 T** A reset during a burst returns the bridge to idle without a stray B and clears the response
  accumulator. verify `test:A2L::test_reset_mid_burst_returns_to_idle`.
- **DS-BUS-090 R** AWPROT and ARPROT are 000. verify `review` (the coverage waivers state the same).

### 3.9 DS-BUS: `axi_lite_interconnect` (110-139)

- **DS-BUS-110 T** The interconnect sends each transfer to the slave whose window holds the address; when windows
  overlap the slave with the higher index wins. verify `test:IC::test_route_and_isolation` (see DS-MAP-002).
- **DS-BUS-111 T** A transfer to an address outside every window completes with DECERR (read data 0), reaches no
  slave, and gives one R beat for one AR. verify `test:IC::test_decerr_unmapped;
  test:FAB::test_ring_decerr_with_master_stalls; test:FAB::test_ring_unmapped_read_single_beat`. Information:
  unreachable in the SoC (DS-MAP-004).
- **DS-BUS-112 T** One write and one read can be in flight, independently: a read completes while a write waits
  for its B. verify `test:FAB::test_ring_engines_independent` (asserts `not wr_done` when the read ends).
- **DS-BUS-113 R** The interconnect offers W to the slave only after the AW handshake. verify `review`. The
  matching slave rule is DS-BUS-220.
- **DS-BUS-114 T** A slave that holds AWREADY, WREADY or ARREADY low stalls the master for the same time with
  stable valid and payload, and the transfer completes once. verify `test:FAB::test_ring_aw_stall;
  test:FAB::test_ring_w_stall; test:FAB::test_ring_ar_stall; test:FAB::test_ring_aw_and_w_stall_together`.
- **DS-BUS-115 T** A master that holds BREADY or RREADY low sees the response held stable. verify
  `test:IC::test_backpressure; test:FAB::test_ring_slave_error_responses_reach_master`.
- **DS-BUS-116 T** Slave responses (EXOKAY, SLVERR, DECERR) reach the master unchanged and do not affect the next
  transfer. verify `test:FAB::test_ring_slave_error_responses_reach_master`.
- **DS-BUS-117 T** AWPROT and ARPROT reach the selected slave only. verify
  `test:IC::test_axprot_routed_to_selected_slave_only`. Information: in the SoC the only master drives 000
  (DS-BUS-090).
- **DS-BUS-118 R** The interconnect has one master and no arbitration. In the SoC that master is
  `u_periph_bridge`, which carries the peripheral traffic of all four crossbar masters. verify `review`.
- **DS-BUS-119 R** The interconnect has no timeout (wait on the slave without limit). verify `review`.

### 3.10 DS-BUS: `axil_to_apb` (140-169)

- **DS-BUS-140 T** Each AXI-Lite transfer becomes one APB transfer: one SETUP cycle (PSEL 1, PENABLE 0), then
  ACCESS (PSEL 1, PENABLE 1) until PREADY. verify `test:L2P::test_write_roundtrip;
  test:FAB::test_apb_ext_slave_wait_states_and_payload` (wait states 3 and 5).
- **DS-BUS-141 T** AW and W can arrive in either order; the APB write starts when both are held. verify
  `test:L2P::test_aw_before_w; test:L2P::test_w_before_aw`.
- **DS-BUS-142 T** When a read and a write are both offered, the write goes first. verify
  `test:L2P::test_concurrent_ar_aw_w_write_priority` [Q read its body; its docstring says it failed on old RTL].
- **DS-BUS-143 T** PSLVERR 1 gives SLVERR, else OKAY; the error is not kept for the next transfer. verify
  `test:L2P::test_pslverr_propagation; test:FAB::test_apb_slverr_end_to_end`.
- **DS-BUS-144 T** The response is held while BREADY or RREADY is low. verify
  `test:L2P::test_bresp_held_while_bready_low; test:L2P::test_rresp_held_while_rready_low`.
- **DS-BUS-145 T** PADDR, PWDATA and PSTRB of a write equal the AXI-Lite address, data and strobes. verify
  `test:FAB::test_apb_ext_slave_wait_states_and_payload; test:FAB::test_apb_write_data_routing_and_isolation`.
- **DS-BUS-146 O** PSTRB in a read transfer. RTL: `pstrb = wstrb_q`, the strobes of the previous write, in every
  state [V]; the AMBA APB specification asks for PSTRB low in a read [planner's reading of the specification;
  quote no section number unless you have the document]. **Owner question Q6.** No test checks PSTRB in a read.
- **DS-BUS-147 R** The bridge has no PPROT output and does not use AxPROT. verify `review`.
- **DS-BUS-148 R** The bridge has no timeout on PREADY. verify `review`.

### 3.11 DS-BUS: `apb_interconnect` (170-189)

- **DS-BUS-170 T** PSEL goes to the slave whose window holds PADDR; with overlap the lowest index wins; PENABLE,
  PWRITE, PADDR, PWDATA and PSTRB go to every slave. verify `test:PIC::test_basic_decode;
  test:PIC::test_first_match_wins; test:PIC::test_write_fanout_reaches_every_slave`. Information: this is the
  opposite overlap rule to the crossbar and the AXI-Lite interconnect; the SoC map has no APB overlap.
- **DS-BUS-171 T** PRDATA, PREADY and PSLVERR come from the selected slave. verify `test:PIC::test_response_mux`.
- **DS-BUS-172 T** With PSEL high and no slave selected: PSLVERR 1, PREADY 1, PRDATA 0, no PSEL out. verify
  `test:PIC::test_unmapped_slverr; test:FAB::test_apb_unclaimed_slot_slverr`. Information: unreachable in the SoC.
- **DS-BUS-173 T** With PSEL low: PREADY 1, PSLVERR 0, PRDATA 0. verify `test:PIC::test_idle`.
- **DS-BUS-174 R** The module is combinational and has no clock. verify `review`.

### 3.12 DS-BUS: slave building blocks and `boot_rom` (190-209)

- **DS-BUS-190 T** `apb4_register_bank` completes every transfer with no wait state and no error. Fact:
  `pready = 1'b1`, `pslverr = 1'b0`. verify `test:PRB::test_apb_setup_access_protocol` [Q read; keep only what it
  asserts].
- **DS-BUS-191 T** `apb4_register_bank` writes only the bytes whose PSTRB bit is 1. verify
  `test:PRB::test_partial_pstrb_write`.
- **DS-BUS-192 T** `axi_lite_register_bank` takes AW and W in either order and writes when both are held. verify
  `test:LRB::test_w_before_aw_uses_latched_data; test:LRB::test_aw_before_w_uses_latched_address`.
- **DS-BUS-193 T** `axi_lite_register_bank` takes no new request while its response waits for the master. verify
  `test:LRB::test_response_backpressure_blocks_new_requests`.
- **DS-BUS-194 T** `boot_rom` returns a read burst of ARLEN+1 beats with OKAY and RLAST on the last beat. verify
  `test:ROM::test_read_burst_and_rready_stalls`. Information: ARBURST is not used (INCR always) [V].
- **DS-BUS-195 R** Every APB slave connected directly to the APB interconnect has no wait state and never returns
  PSLVERR. The PLL and PLL2 slots go through `apb_cdc_bridge`: they have wait states and can end with PSLVERR
  (`\reqref{DS-CDC-102}`, `DS-CDC-103`). Fact: each peripheral and `pmu` pass `pready/pslverr` of
  `apb4_register_bank`; `npu_top` drives `1'b1/1'b0` in one arm [V]. verify `review`. This contradicts a coverage
  waiver (section 9.2 item 11).

### 3.13 DS-BUS: contract on masters and slaves (210-239)

- **DS-BUS-210 R** A master has at most one read and one write in flight: it sends a new AR only after the last R
  beat of the previous read, and a new AW only after the B of the previous write. Reason [I]: the crossbar keeps
  one engine for each slave and ORs the responses of all engines that a master holds; two reads to two slaves
  would mix their R beats, two writes would share W beats; and while an engine is in `W_AW`/`R_AR` the crossbar
  passes the slave's AWREADY/ARREADY to the granted master, so a new request offered in that window is
  acknowledged and lost. verify `review`. Information: the DMA engine (`dma_engine` `state_q` S_AR->S_R->S_AW->
  S_W->S_B) and the CPU cache arbiter (header: grant held to RLAST / B) obey this [V headers and FSM; Q confirm the
  arbiter allows no AR and AW together if that matters]; GPU M2 [Q].
- **DS-BUS-211 R** A master sends WLAST on beat AWLEN+1 exactly (DS-BUS-028, DS-BUS-083). verify `review`.
- **DS-BUS-212 R** A master keeps BREADY and RREADY able to rise; a master that never takes its response blocks
  the slave for every master (DS-BUS-033). verify `review`.
- **DS-BUS-213 O** Information-level link to power: while the GPU clamp is active, `xbar_m_bready[2]`,
  `xbar_m_rready[2]` and `gif_axil_rready` are 0, so a GPU transaction in flight at a GPU power-down holds its
  crossbar engine (and that slave) until the clamp releases [I]. **Owner question Q8** (whether to add a power
  software rule "stop GPU bus traffic before GPU_OFF", the GPU analogue of DS-PMU-182). Do not write the rule
  before Q8.
- **DS-BUS-220 R** A slave of the AXI-Lite interconnect accepts AW without waiting for W. Reason: DS-BUS-113.
  verify `review`. Information: the three SoC slots obey it (`gpu_top` `s_axil_awready = ~aw_cap_q`,
  `axi_lite_register_bank`, `axil_to_apb`) [V].
- **DS-BUS-221 R** An APB slave ends each transfer (PREADY) in bounded time; the fabric does not end it
  otherwise. verify `review`.
- **DS-BUS-222 R** A new slave or master runs on `core_clk`/`core_rst_n` or connects through a CDC bridge.
  Cross-reference `\reqref{DS-CDC-001}` ("Crossings use the primitives", per the pilot truth review; [Q] confirm
  the title in `ds/parts/chapters/cdc.tex`). verify `review`.
- **DS-BUS-223 C** Every module under `rtl/periph/` and `rtl/npu/` is in the five build lists. verify
  `check:tools/verif/check_periph_filelists.py`. Information: the check does not scan `rtl/soc/`, so a new fabric
  module is not covered (gap; section 7).

Totals (counted from this list):
- DS-MAP: 20 rules - T 12 (001, 002, 003, 020, 021, 022, 023, 040, 041, 043, 044, 060), R 6 (004, 005, 024, 045,
  061, 063), O 2 (042, 062).
- DS-BUS: 78 rules - T 41 (one of them, 088, is T? until the worker confirms the BFM check), R 34, O 2 (146,
  213), C 1 (223). By block: 001-005 R5; 020-035 T6 R10; 060-067 T6 R2; 080-090 T7 R4; 110-119 T7 R3;
  140-148 T6 R2 O1; 170-174 T4 R1; 190-195 T5 R1; 210-223 R6 O1 C1.
- **All: 98 draft rules: T 53, C 1, R 40, O 4.** The R share is high because the fabric tests prove data paths and
  responses well but prove no order, priority, concurrency in time, WLAST handling or reset in a burst (gaps
  below). The worker may merge rules that the reviewer finds redundant; record every merge in the notes file so
  the ledger stays consistent.

Verification gaps to state in the TM "Verification" subsections (present tense, honest):
1. No priority test (fixed priority, starvation) and no test that asserts concurrency in time (crossbar; also
   `axi4_to_axilite` read/write independence).
2. No WLAST/RLAST error test; no test of a WLAST that disagrees with AWLEN (crossbar plus bridge hang, derived).
3. No test of two outstanding reads or writes of one master to two slaves (DS-BUS-210), and none of a new request
   in the `W_AW`/`R_AR` window.
4. No AW one-cycle pulse test; no W-before-AW test at the crossbar.
5. No reset-during-burst test for the crossbar, the AXI-Lite interconnect or `axil_to_apb` (only
   `axi4_to_axilite` and `axilite_to_axi4` have one).
6. Narrow (AxSIZE < 4 B), FIXED and WRAP bursts: never sent to the bridge; the SRAM controller tests cover them for
   S1 only [Q `test_sram_controller.py`].
7. 4 KB / region boundary crossing by a burst: no test (DS-MAP-005).
8. ID values on the slave side: no test (DS-BUS-003). ID reordering cannot occur (one transaction per engine);
   say so as a design fact, not as a test result.
9. Decode errors per region: SoC-level DECERR is shown for 0x1000_0000, 0x2001_1000, 0x2002_0000, 0x4000_0000,
   0x8000_0000; not for 0x0000_0000-0x0FFF [Q `test_boot` docstring mentions it; check whether any SoC test
   asserts it] and not for 0x2000_0000-0x0FFF.
10. PSTRB in an APB read: no test (DS-BUS-146).
11. No timeout exists, so none is tested; the GPU-off hang is measured by `expect_fail` tests (power chapter).
12. Unit benches use other maps and sizes (section 1.1); SoC-level tests run at one clock ratio [Q which: read
    `tb_soc_top` / `soc_clocks.py`] and zero delay.
13. The register walk and the DMA/GPU walks are firmware self-checks: a failure shows as FAIL_PC; they are
    end-to-end, not per-module proofs.

---------------------------------------------------------------------------------------------------

## 4. The memory map (central reference)

### 4.1 Single source of truth [V]
- `rtl/soc/soc_addr_map_pkg.sv`: `ROM_BASE/LIMIT`, `SRAM_BASE/LIMIT`, `PERIPH_BASE/LIMIT`, `MMIO_BASE`,
  slave indices `SLV_ROM/SLV_SRAM/SLV_PERIPH`, `SOC_SLV_BASE/LIMIT` (packed arrays), `decode_slave()`.
- `rtl/soc/soc_periph_map_pkg.sv`: `AXIL_GPU/APB_BRIDGE/DMA` indices, `AXIL_*_BASE/LIMIT`, `AXIL_SLV_BASE/LIMIT`,
  `APB_<name>` indices 0-13, `APB_*_BASE/LIMIT`, `APB_SLV_BASE/LIMIT` (unpacked arrays), legacy `AXIL_UART_*` ...
  `AXIL_PLL_*` constants (unused by the fabric), `decode_axil_slave()`.
- `soc_bus` passes the arrays to `u_xbar`, `u_axil_ic`, `u_apb_ic`; `soc_top` passes `RESET_PC`, `SRAM_MEM_WORDS`
  and the ROM depth `MEM_WORDS (1024)`.
- `decode_slave()` and `decode_axil_slave()` are used by no file in `rtl/` or `tb/` [V grep]; the package header
  says "The top level and the testbench use it as the reference model" (false, section 9.2).
- Firmware and tests hard-code the addresses (`sw/drivers/gpio.h`, `tb/cocotb/soc/integ_fw/*.py`, `reg_maps.py`,
  many tests). There is no generator of a C header or Python constants from the packages [V grep].

### 4.2 The table (T-MAP) the chapter must hold (all values [V] from the packages)

| Range | Size | Target (instance) | Path from a crossbar master | Notes |
|---|---|---|---|---|
| 0x0000_0000-0x0000_0FFF | 4 KB | none | - | DECERR (crossbar). Old text calls this "Reset & Traps". |
| 0x0000_1000-0x0000_1FFF | 4 KB | boot ROM `u_boot_rom` (S0) | AXI4 | Read OKAY, write SLVERR; reset PC 0x0000_1000. |
| 0x0000_2000-0x0FFF_FFFF | 256 MB - 8 KB decode | SRAM `u_sram` (S1) | AXI4 | Storage `SRAM_MEM_WORDS` words, repeats (Q5). |
| 0x1000_0000-0x2000_0FFF | - | none | - | DECERR. Includes 0x2000_0000-0FFF (old "CPU debug" row). |
| 0x2000_1000-0x2000_1FFF | 4 KB | GPU control `u_gpu` `s_axil_*` | AXI4 -> AXI-Lite (slot 0) | Hang while GPU off (DS-PMU-185). |
| 0x2000_2000-0x2000_2FFF | 4 KB | UART `u_uart` | AXI4 -> AXI-Lite -> APB slot 0 | |
| 0x2000_3000-0x2000_3FFF | 4 KB | SPI `u_spi` | APB slot 1 | |
| 0x2000_4000-0x2000_4FFF | 4 KB | timer `u_timer` [Q instance name] | APB slot 2 | |
| 0x2000_5000-0x2000_5FFF | 4 KB | DMA control `u_dma` `s_axil_*` | AXI-Lite slot 2 (overrides slot 1) | |
| 0x2000_6000-0x2000_6FFF | 4 KB | IRQ controller [Q instance] | APB slot 3 | |
| 0x2000_7000-0x2000_7FFF | 4 KB | PLL `u_pll_sub` via `u_apb_pll_cdc` | APB slot 4 + CDC | Wait states, SLVERR possible. |
| 0x2000_8000-0x2000_8FFF | 4 KB | PMU `u_pmu` | APB slot 5 | |
| 0x2000_9000-0x2000_9FFF | 4 KB | PLL2 `u_cpu_pll_sub` via `u_apb_pll2_cdc` [Q names] | APB slot 6 + CDC | m face reset `cpu_rst_n_i`. |
| 0x2000_A000-0x2000_AFFF | 4 KB | GPIO | APB slot 7 | |
| 0x2000_B000-0x2000_BFFF | 4 KB | PWM | APB slot 8 | |
| 0x2000_C000-0x2000_CFFF | 4 KB | WDT | APB slot 9 | |
| 0x2000_D000-0x2000_DFFF | 4 KB | TRNG | APB slot 10 | |
| 0x2000_E000-0x2000_EFFF | 4 KB | I2C | APB slot 11 | |
| 0x2000_F000-0x2000_FFFF | 4 KB | CRYPTO | APB slot 12 | |
| 0x2001_0000-0x2001_0FFF | 4 KB | NPU | APB slot 13 | |
| 0x2001_1000-0xFFFF_FFFF | - | none | - | DECERR (old "External memory" at 0x8000_0000 does not exist). |

Columns the worker adds: the label of each target's register map (where it exists today) and "cached" (only
< 0x2000_0000; DS-MAP-045). Every peripheral consumes `paddr[11:0]` only. The window crosses from 0x2000_xxxx to
0x2001_0xxx at slot 13; `paddr` is 32 bits end to end, so this has no effect [V `soc_bus` `.ADDR_W (32)`].

### 4.3 Can the table be generated? [V tools/docs/gen_fact_tables.py]
`gen_fact_tables.py` handles module ports and parameters only (it skips `localparam`, rejects unpacked parameters
and unpacked port dimensions, and reads no package). It cannot make the map. Smallest designs:
- **(a) New generator `tools/docs/gen_memory_map.py` (recommended, infrastructure PR-0).** Read the two packages
  with pyslang (already installed in `docs.yml` as `pyslang==11.0.0`) or, simpler and stdlib-only, with a regex on
  the literal `localparam logic [31:0] <NAME>_BASE/_LIMIT = 32'h...` lines (all are literal hex today [V]). A
  sidecar `docs/manual/common/facts/memory_map.yaml` gives, per base name, the target instance, the path and a
  description. Output `docs/manual/common/generated/memory-map.tex` (longtable via `tools/docs/doc_tables.py`).
  `--check` mode in `docs.yml`. The same tool asserts: every region 4 KB aligned; the union of the AXI-Lite windows
  equals `PERIPH_*`; every APB page claimed once; the only overlap is the declared DMA override. That turns
  DS-MAP-004 into `check:tools/docs/gen_memory_map.py`, with a pytest negative control in
  `tb/tests/test_docs_gen_memory_map.py`. About 200 lines + 80 test lines.
- (b) Hand-written table plus a small pytest that parses the packages and compares with the TeX table.
- (c) Hand-written table, review only.
This is owner question Q2. If the answer is not available when PR-A starts, write the table by hand (b-shape
text) and mark DS-MAP-004 `review`.

---------------------------------------------------------------------------------------------------

## 5. TM chapter outline

New file `docs/manual/tm/parts/chapters/bus.tex`, `\chapter{Bus fabric}\label{tm:ch:mod-bus-fabric}`; input it in
`tm/parts/01-module-reference.tex` next to `\input{parts/chapters/cdc}` (planner suggests before it). The old
`tm:ch:mod-soc-fabric` chapter keeps `soc_top` and `sram_controller` and gets one pointer sentence.
Chapter intro: purpose; the three protocol levels; what the fabric does not do (no timeout, no ordering between
read and write, no fairness, no burst split at region ends, no security); figures F1 and F2.

**F1 Fabric topology** (`fig:tm:ch:mod-bus-fabric:topology`, TikZ): masters M0 (`u_cpu` -> ISO_CPU clamp box ->
`u_cpu_axi_cdc`, drawn as one box marked CDC, `cpu_gated_clk` | `core_clk`), M1 (`u_gpu` -> ISO_GPU clamp ->
`u_gif_adapter`), M2 (`u_gpu` -> ISO_GPU clamp), M3 (`u_dma`); `u_xbar` with S0 `u_boot_rom`, S1 `u_sram`, S2
`u_periph_bridge` -> `u_axil_ic` -> {slot 0 `u_gpu` control (dashed: GPU domain), slot 1 `u_axil_apb_bridge` ->
`u_apb_ic` -> 14 APB slots (group the 12 direct ones; draw `u_apb_pll_cdc` and `u_apb_pll2_cdc` as CDC boxes),
slot 2 `u_dma` control}. Dashed box around `u_bus`. Domain shading: `core_clk` for everything except behind the
CDC boxes and inside the GPU power domain. Label each link with its protocol (AXI4, AXI-Lite, APB4). Do not draw
CDC or clamp internals.

**F2 Address decode tree** (`fig:tm:ch:mod-bus-fabric:decode`): three decode levels with their windows and the
decode-error leaves (crossbar DECERR reachable; AXI-Lite DECERR and APB PSLVERR leaves drawn and marked "not
reachable with the SoC map").

### 5.1 Fabric topology and memory map: `\section{Fabric topology}\label{tm:mod:soc-bus}` (new label)
Port groups of `soc_bus`; the sizes from the packages; T-MAP (generated or hand-written, Q2); storage behind S0
and S1 (ROM index, SRAM repeat - TM fact, measured by the walks); unmapped ranges; the end-to-end paths with the
derived latencies of 5.8.

### 5.2 `\section{\texttt{axi4\_crossbar}}\label{tm:mod:axi4-crossbar}` (existing label moves here)
- Introduction; `\reqref` list.
- Functional description: decode function (last match, start address only); write engine states `W_IDLE`,
  `W_AW`, `W_DATA`, `W_RESP` and read engine `R_IDLE`, `R_AR`, `R_DATA` with a state table (what each state drives
  to the slave and returns to the master); early accept and the captured address registers; decode-error engines
  `DW_*` / `DR_*`; response resolution (`_m_* = slv_* | dec_*`); ID tagging.
  **F3 Engine state machines** (`fig:tm:mod:axi4-crossbar:fsm`, TikZ automata, both engines in one figure).
  **F4 Arbitration** (`fig:tm:mod:axi4-crossbar:arb`, tikztimingtable): M0 and M1 raise ARVALID to the same idle
  slave in cycle 0; M0 gets `m_arready` in cycle 0 (early accept); `s_arvalid` with M0's address from cycle 1;
  M1 waits until `rstate` returns to `R_IDLE` after M0's RLAST, then gets early accept. Derived, single-beat,
  slave ready at once. Caption states it is derived.
  **F5 Read through the crossbar** (`fig:tm:mod:axi4-crossbar:read`): derived [I]: E0 master AR handshake
  (`R_IDLE`); cycle 1 `s_arvalid` from `ar_*_q`, slave `s_arready` -> E1 `R_DATA` (note: in cycle 1 the master
  also sees `m_arready = s_arready`, the window of DS-BUS-210); R passes through combinationally.
  **F6 Write through the crossbar** (`fig:tm:mod:axi4-crossbar:write`): E0 AW early accept; cycle 1 `s_awvalid`;
  `W_DATA` after the slave's AWREADY; W and B pass through.
- The note that the RTL cites by label: `axi4_crossbar.sv` says "Do not drive port array slices from always_comb
  in a loop. Synlig makes empty wire names. See tm:mod:axi4-crossbar." [V]. This section **must** contain that
  implementation note (always_comb drives packed intermediates `_s_*`/`_m_*`; continuous assigns connect them to
  the ports; reason: a Synlig/UHDM defect). Cite `tm` tool-defect text if it exists [Q search the TM part "Tool
  defects and standing caveats" for the Synlig empty-wire defect].
- Parameters and signals: generated tables (section 6). State that the widths in the table are at the module
  defaults (3 masters, 2 slaves); the SoC uses 4 and 3.
- Integration: master contract (DS-BUS-210-212), no ordering, no timeout, reset caller rule.
- Verification: suites `crossbar` (two modules), the SoC walks; gaps 1-9.
- Known limits: fixed priority without fairness; no timeout; the `W_AW`/`R_AR` ready window; WLAST trust; no
  boundary split; synchronous reset without drain; early-accept AWREADY/ARREADY is combinational from the master's
  valid and is high during reset if a master raises valid (section 9.3).

### 5.3 `\section{\texttt{axilite\_to\_axi4}}\label{tm:mod:axilite-to-axi4}` (new)
Skid buffer (`ar_hold_q`, `ar_addr_q`), fixed AR fields, R pass-through, tied write channels.
**F7** (`fig:tm:mod:axilite-to-axi4:timing`): one-cycle `s_axil_arvalid` pulse at cycle 0 with `m_axi_arready` low
for two cycles: `m_axi_arvalid` high cycles 0-2 with the pulsed address, `ar_hold_q` high from E0 to E2,
`s_axil_arready` only in cycle 2. Derived; matches the intent of `test_pulse_is_held_until_accepted`.
Known limits: DS-BUS-066, DS-BUS-067; the module header's "clk and rst_n unused" is false (section 9.2).

### 5.4 `\section{\texttt{axi4\_to\_axilite}}\label{tm:mod:axi4-to-axilite}` (new)
Write FSM `WS_IDLE, WS_DATA, WS_REQ, WS_B, WS_RESP`; read FSM `RS_IDLE, RS_AR, RS_R, RS_FWD`; `worse_resp`.
**F8 Write** (`fig:tm:mod:axi4-to-axilite:write`), derived [I] with an AXI-Lite slave that accepts AW and W at once
and answers B one cycle later: E0 AW handshake; cycle 1 `s_wready`, E1 W beat; cycle 2 `m_axil_awvalid` and
`m_axil_wvalid`, E2 both handshakes; cycle 3 `m_axil_bready`, E3 B; cycle 4 `s_bvalid`. Each further beat adds 3
cycles (`WS_B -> WS_DATA -> WS_REQ -> WS_B`).
**F9 Read** (`fig:tm:mod:axi4-to-axilite:read`): E0 AR; cycle 1 `m_axil_arvalid`, E1; cycle 2 `m_axil_rready`, R at
E2 if the slave answers in that cycle; cycle 3 `s_rvalid` (+`s_rlast` on the last beat). Each further beat 3
cycles. Re-derive both; state the slave assumption in the caption.
Known limits: DS-BUS-082, 083; one transfer at a time towards the ring.

### 5.5 `\section{\texttt{axi\_lite\_interconnect}}\label{tm:mod:axi-lite-interconnect}` (new TM label; DS label
`ds:mod:axi-lite-interconnect` exists)
Write engine `W_IDLE, W_AW, W_DATA, W_RESP` (AW and W serialised), read engine with the output register
`r_d*_q` (one more cycle of read latency; `r_dreg_ready` depends only on `r_dvalid_q` and `m_axil_rready`; the
DECERR beat offered only while the register is empty). This is the content of the old relocated DS block "bead
rvb" (move the reason - one register boundary for timing - without the history; history to CR).
**F10** (`fig:tm:mod:axi-lite-interconnect:timing`): write: cycle 0 `m_axil_awvalid`, E0 `W_AW`; cycle 1 AW to
slave, E1 handshake; cycle 2 W, E2; B passes through. Read: E0 `R_AR`; E1 AR handshake; slave R in cycle k;
master R in cycle k+1. Derived.

### 5.6 `\section{\texttt{axil\_to\_apb}}\label{tm:mod:axil-to-apb}` (new)
FSM `S_IDLE, S_SETUP, S_ACCESS, S_WRESP, S_RRESP`; capture flags; write priority; PSTRB in reads (Q6).
**F11** (`fig:tm:mod:axil-to-apb:timing`): write with AW and W in the same cycle: E0 capture; cycle 1 SETUP;
cycle 2 ACCESS (PREADY 1); cycle 3 `bvalid`. Read: same shape with `rvalid` in cycle 3. A second panel with
two wait states.

### 5.7 `\section{\texttt{apb\_interconnect}}\label{tm:mod:apb-interconnect}` (existing label moves here)
First-match decode, broadcast, response mux, default response; the `SEL_W`/`IDXW` width note (it is in the
relocated TM block today; keep the reason, it explains a lint fix: the sentinel needs one more bit when
`N_SLAVES` is a power of two).

### 5.8 End-to-end latency (inside 5.1 or its own subsection)
Derived [I] by the planner for a single-word access from a crossbar master to a zero-wait APB slave, master ready
at once (worker re-derives, figure optional **F12**, `fig:tm:ch:mod-bus-fabric:e2e`):
- Read: AR handshake at the crossbar E0; bridge takes AR E1; AXI-Lite interconnect `R_AR` E2; AR handshake at
  `axil_to_apb` E3; SETUP cycle 4; ACCESS cycle 5 (E5 captures PRDATA); `s_axil_rvalid` cycle 6 into the
  interconnect register; interconnect `m_axil_rvalid` cycle 7, bridge latches E7; master sees R in cycle 8.
- Write: AW handshake E0; bridge AW E1; bridge W E2; interconnect `W_AW` E3; AW handshake at `axil_to_apb` E4;
  W handshake E5; SETUP 6; ACCESS 7; `bvalid` 8 (bridge takes B at E8); master sees B in cycle 9.
Label both "derived from the RTL; no test measures them".

### 5.9 Slave building blocks and `boot_rom`
`\section{\texttt{apb4\_register\_bank}}\label{tm:mod:apb4-register-bank}`,
`\section{\texttt{axi\_lite\_register\_bank}}\label{tm:mod:axi-lite-register-bank}`,
`\section{\texttt{boot\_rom}}\label{tm:mod:boot-rom}` (all new TM labels; placement Q9). Bus behaviour only:
ready/err constants, capture, strobes, out-of-range, read-data timing (`apb4_register_bank` drives `prdata`
combinationally while `psel`), ROM write sink, ROM read engine, `MEM_INIT_FILE` arms (`__pnr__`, `FPGA`).

Each module section follows the Arm TRM order used before: Introduction; Functional description (with figures);
Configuration parameters and Signal descriptions (generated tables or the fallback of section 6); Integration;
Verification; Known limits.

---------------------------------------------------------------------------------------------------

## 6. Fact tables

New sidecar `docs/manual/common/facts/bus.yaml` (`family: bus`), same schema as `cdc.yaml` / `power.yaml`
(`rtl`, `deps`, `label`, `params: {NAME: {legal, description}}`, `ports: {name: {domain, description}}`; every
port and parameter needs an entry; `domain` is a clock port name of the module or `clock`/`async`/
`quasi-static`).

Planner's prediction of what `gen_fact_tables.py` accepts [V by reading the tool; Q run it module by module]:

| Module | Expected | Reason |
|---|---|---|
| `axi4_crossbar` | OK | Packed 2-D parameters and ports; widths at defaults (3 x 2). Deps: `rtl/soc/axi_pkg.sv`. |
| `axi4_to_axilite` | OK? | `import axi_pkg::*;` in the header [Q confirm the syntax pass accepts it]. |
| `axilite_to_axi4` | OK? | Same; `MASTER_ID` is `logic [3:0]`. |
| `axi_lite_interconnect` | OK | Packed parameters `[N_SLAVES-1:0][AW-1:0]`. Defaults N_SLAVES=6. |
| `axil_to_apb` | OK | `ifndef __pnr__` is in the body, not the header. |
| `apb_interconnect` | FAILS | Unpacked parameters `SLV_BASE [N_SLAVES]` and unpacked ports `psel_o [N_SLAVES]` ("unpacked parameter", "unpacked dimension on port"). |
| `soc_bus` | FAILS | Unpacked APB port arrays `[APB_N_SLAVES]`. |
| `boot_rom` | FAILS | `ifndef __pnr__` inside the parameter list ("conditional compilation in the module header"); both arms are the same text [V]. |
| `apb4_register_bank`, `axi_lite_register_bank` | FAIL | Unpacked parameters `RESET_VAL`/`WMASK`, unpacked ports `regs_o`, `hw_wen_i`, `hw_wdata_i`. |

For the failures (owner question Q4): (a) PR-0 extends `gen_fact_tables.py` to accept unpacked dimensions (width
cell "element width x count", e.g. `32 [N_SLAVES]`; parameter default text as written) - about 60 lines and a
test; (b) hand-written tables with the same columns and a sentence "This table is written by hand; the generator
does not read unpacked arrays"; (c) no table. `boot_rom` needs either an RTL change (remove the redundant
`ifdef` from the header; out of these PRs) or a hand-written table.
Domains: every port of the clocked modules is in the domain `clk` (the clock port itself is `clock`).
`apb_interconnect` has no clock port, and the tool accepts only a clock port name of the same module or the words
`clock`, `async`, `quasi-static` [V `DOMAIN_WORDS`]; none of them is true for a combinational path. [Q] check
whether `cdc.yaml` or `power.yaml` has a precedent; if not, ask the primary planner (a fourth word such as
`comb` needs a tool change, which belongs in PR-0).
Descriptions come from the RTL behaviour, not from the port comments (several port comments are stale, e.g.
`s_bid` "reserved").

---------------------------------------------------------------------------------------------------

## 7. UM integration additions

New chapter in `docs/manual/um/parts/02-integration.tex` after `um:ch:power-integration`:
`\chapter{Bus fabric integration}\label{um:ch:bus-integration}` with the template of the earlier chapters:

1. **Read the memory map** (link T-MAP): region, path, response of an unmapped address, which slots wait
   (PLL, PLL2), which addresses are cached.
2. **Firmware rules** (from DS-MAP-06x, DS-BUS-210-212): aligned word accesses to registers; one transaction in
   flight per master (relevant to a new master, not to CPU firmware); read-after-write to the same slave needs the
   B first; check `rresp`/`bresp` where the master exposes them (DMA `STATUS.error` - [Q name the DMA error
   field from `gen_integ_hex.py::ERRINFO_*`]); do not access the GPU while it is off (link DS-PMU-185).
3. **Add an APB slave** (task): pick a free 4 KB page inside `AXIL_APB_BASE..AXIL_APB_LIMIT` or grow the window
   (then also `PERIPH_LIMIT`, so DS-MAP-004 still holds); add `APB_<NAME>`, `APB_<NAME>_BASE/LIMIT`, grow
   `APB_N_SLAVES`, extend `APB_SLV_BASE/LIMIT` in index order; connect `apb_*[APB_<NAME>]` in `soc_top` with
   `paddr[11:0]`; use `apb4_register_bank` so PREADY/PSLVERR behave as DS-BUS-195; add the module to the five
   lists (AGENTS.md rule 7: `PLL_SOURCES`, `SOC_BOOT_SOURCES` in `tb/cocotb/soc/Makefile`, `SOC_TOP_SOURCES` in
   `sim/Makefile`, `SKY130_SOC_SV_FILES`, `SOC_SV_FILES` in `pnr/Makefile`) [V `check_periph_filelists.py::LISTS`];
   never edit `rtl/filelist/*.f` - run `python tools/verif/gen_filelist.py` then `--check` (rule 9); add the
   instance to the `# upf-check aon` roster of `pnr/constraints/phase5_soc.upf` and run
   `python tools/verif/check_upf.py -v` and `gen-facts --check` (power chapter); update the hard-coded constants
   in tests that pin the window end (`tb/cocotb/soc/test_axil_interconnect.py::BAD_HIGH` - its docstring says to
   bump it by hand [V]); update the map table (or its sidecar if PR-0 exists); run the checks of step 6.
4. **Add an AXI-Lite slave** (task): new `AXIL_*` index, base and limit, grow `AXIL_N_SLAVES`, the slave must
   accept AW without W (DS-BUS-220); new flat port group in `soc_bus` (copy `axil_dma_*`).
5. **Add a crossbar master or slave** (task): `N_MASTERS` in `soc_top` (and so `soc_bus`), `AXI_ID_WIDTH`
   (DS-BUS-004); a master must obey DS-BUS-210-212; a new slave region in `soc_addr_map_pkg` (`SOC_N_SLAVES`,
   `SOC_SLV_BASE/LIMIT`, `SLV_*`), new flat port group in `soc_bus`; consider the fixed priority (index order).
   New `rtl/soc/` modules are **not** covered by `check_periph_filelists.py` (it scans `rtl/periph` and `rtl/npu`
   only) [V]; check the five lists by hand and run `python3 tools/verif/check_source_closure.py <config>` for each
   PD config (it checks package closure only).
6. **Verify** (task): `nix develop --command make -C tb/cocotb/soc <target>` for `crossbar`,
   `axi4_to_axilite`, `axilite_to_axi4`, `axil_interconnect`, `axil_apb_fabric`, `axil_to_apb`,
   `apb_interconnect`, `apb4_register_bank`, `register_bank`, `boot_rom`, `soc_integration`, `soc_boot`; then
   `python tools/verif/check_periph_filelists.py`, `python tools/verif/gen_filelist.py --check`,
   `python tools/verif/check_source_closure.py` [Q exact arguments], the equivalence script
   `tools/verif/equiv_sv2v_module.sh` lists the fabric files [V] (state what it proves only after reading it).
7. **Checklist.**
Use imperative mood; no "must" in the UM.

---------------------------------------------------------------------------------------------------

## 8. Source-archive plan

Blocks that leave the books (exact `\begin{relocated}` ... `\end{relocated}` spans with their section heading;
re-measure on `origin/main` before cutting; planner's line numbers on today's `main`):

| Archive label | From | Location today |
|---|---|---|
| `cr:arc:ds-apb4-register-bank` | `ds:mod:apb4-register-bank`, `ds/parts/03-module-contracts.tex` | 561-596 (only if Q9 = a) |
| `cr:arc:ds-axi-lite-interconnect` | `ds:mod:axi-lite-interconnect`, same file | 598-629 |
| `cr:arc:ds-axi-lite-register-bank` | `ds:mod:axi-lite-register-bank`, same file | 631-666 (Q9) |
| `cr:arc:ds-soc-addr-map-pkg` | `ds:mod:soc-addr-map-pkg`, same file | 668-705 |
| `cr:arc:ds-soc-bus` | `ds:mod:soc-bus`, same file | 707-743 |
| `cr:arc:ds-soc-periph-map-pkg` | `ds:mod:soc-periph-map-pkg`, same file | 745-798 |
| `cr:arc:tm-apb-interconnect` | `tm:mod:apb-interconnect`, `tm/parts/01-module-reference.tex` | 448-472 |
| `cr:arc:tm-axi4-crossbar` | `tm:mod:axi4-crossbar`, same file | 474-494 |
| `cr:arc:ds-memory-map` | parts of `ds:ch:memory-map`, `ds/parts/01-architecture.tex` | one `relocated{docs/design/MEMORY_MAP.md}` block 11946-13690 (Q3) |

Labels stay on the authored sections and do not change: `ds:mod:apb4-register-bank`,
`ds:mod:axi-lite-interconnect`, `ds:mod:axi-lite-register-bank`, `ds:mod:soc-addr-map-pkg`, `ds:mod:soc-bus`,
`ds:mod:soc-periph-map-pkg`, `tm:mod:apb-interconnect`, `tm:mod:axi4-crossbar`. Source files cite them
(`Doc:` lines in `apb4_register_bank.sv`, `axi_lite_register_bank.sv`, `soc_addr_map_pkg.sv`, `soc_bus.sv`,
`soc_periph_map_pkg.sv`; `axi4_crossbar.sv` cites `tm:mod:axi4-crossbar` in a body comment; `tm/parts/chapters/
power.tex` cites `ds:mod:apb4-register-bank`) [V]. The DS packages get authored DS sections (the map) under
`ds:mod:soc-addr-map-pkg` and `ds:mod:soc-periph-map-pkg` - one short section each that points to the map table,
or put both labels on the map section with `\label` twice [Q check that `check_doc_labels.py` allows two labels on
one section; the CDC chapter has a precedent if it did this]. New DS module labels: `ds:mod:axi4-crossbar`,
`ds:mod:axi4-to-axilite`, `ds:mod:axilite-to-axi4`, `ds:mod:axil-to-apb`, `ds:mod:apb-interconnect`,
`ds:mod:boot-rom`. New chapter labels: `ds:ch:mod-bus-fabric`, `tm:ch:mod-bus-fabric`, `um:ch:bus-integration`.

Memory map (Q3): the block holds (a) overview, address space, "minimum region", global map, phase maps
(11948-12141), (b) register maps of the debug port, GPU and peripherals (12142-13459), (c) reset/trap vectors,
alignment, permissions, SoC interconnect, interrupt hierarchy, testing recommendations, references (13460-13689).
Recommended: archive (a) and (c) except the interrupt hierarchy [Q decide with the primary planner; it is not
fabric], keep (b) in a shortened relocated block under `ds:ch:memory-map` with the header line, so the
`ds:mm:memory-map:*-registers` labels that tests and `reg_maps.py` cite keep pointing to the DS. Labels of the
moved subsections move into the archive with the text (precedent: `ds:ch:upf-power-spec:*` now lives in CR [V]).
Before cutting, list every citation of each moving sub-label (`rtk proxy grep -rn "ds:mm:memory-map:" rtl tb tools
sw docs/manual`) - `test_ebreak.py`, `test_debug_if.py`, `apb3_master.py` cite sub-labels [V]; make sure none of
them points into a moved span, or report it. `ds:mm:memory-map` itself (cited by about 30 files [V]) stays on the
DS block.

Leftovers: `% --- generated by PR7a: begin` at DS line 560 and TM line 447 have no matching end marker in those
files [V]; [Q] confirm no tool reads them (the pilot found the same for PR7c); remove the one inside a span you
cut, leave the other.

Procedure (pilot P2 step 4, unchanged): base files from `origin/main` with `git show`; a scratch script cuts each
span to `<scratch>/old/<book>-<slug>.tex`; paste the bytes unchanged into `docs/manual/cr/parts/06-source-archive.tex`
(DS chapter `cr:ch:source-archive-ds`, then TM chapter) with the section heading form and the sentence already
used there ("This text was in the Design Specification section \cref{...}. The authored section replaced it. The
text is unchanged."). Proofs:
1. Byte identity by hash: for each old span, `sha256` of the span equals `sha256` of its copy in
   `06-source-archive.tex` (extract by the section label), and the span is absent from the new DS/TM files ->
   `IDENTICAL n/n, REMOVED n/n`. Do not gate on `diff` (AGENTS.md section 6).
2. Line-run check: every maximal run of non-blank lines of each old span occurs once, contiguous, in the archive
   (the check used in the last PR).
3. `python tools/docs/prose_preserve.py --from <scratch>/old/*.tex --to docs/manual/cr/parts/06-source-archive.tex`
   -> `PRESERVED ... 0 missing`. Negative control: `--to docs/manual/cr/parts/01-phase-and-status-history.tex`.
   The negative control did **not** fail in the last PR, so `prose_preserve.py` is not a proof alone; proofs 1
   and 2 decide. Report what the negative control printed.
Trap: `um/parts/01-chapters.tex` holds sample `relocated` blocks inside `lstlisting`; cut by section label, never
by searching for the first `relocated{...}`.

---------------------------------------------------------------------------------------------------

## 9. Truth risks

### 9.1 Statements to verify or avoid (old text that is wrong or unsupported)
1. Memory map "0x0000_0000-0x0000_0FFF Reset & Traps", "Reset vector 0x0000_0000", "Trap vector 0x0000_0100":
   unmapped in the SoC (DECERR); `RESET_PC` is 0x0000_1000 in `soc_top` [V]. Do not repeat.
2. "0x2000_0000-0x2000_0FFF CPU Debug (APB3)": not on the bus (DECERR); the debug port is a top-level APB3 port.
3. "UART (AXI-Lite)", "SPI (AXI-Lite)", "Timer", "DMA", "IRQ (AXI-Lite)": UART/SPI/timer/IRQ are APB4 slots;
   GPU and DMA control are AXI-Lite.
4. "0x8000_0000-0xFFFF_FFFF External Memory": no slave; DECERR (measured by the gpu walk at 0x8000_0000).
5. "S2 ... 0x2000_1000-0x2000_AFFF", "6 AXI-Lite slaves: GPU, UART, SPI, TIMER, DMA, IRQ": stale (window ends
   0x2001_0FFF; 3 slots).
6. "The AXI-Lite control ring is single-master (CPU config access only) ... a second master (DMA-to-peripheral)
   requires an upgrade": the one master of the interconnect is the bridge, which carries the peripheral traffic of
   the CPU, the GPU data master, the DMA and in principle the GPU fetch; the gpu walk writes the timer through M2
   and the PMU test makes the DMA write `CTRL` [V]. Same stale claim in the `axi_lite_interconnect.sv` header and
   in its relocated DS block ("CPU only").
7. "unmapped accesses within 0x2000_xxxx return DECERR": only 0x2000_0000-0x0FFF is unmapped; the rest of
   0x2000_1000-0x2000_FFFF is claimed.
8. "Main Memory ~256 MB": the decode window is 256 MB; the storage is `SRAM_MEM_WORDS` words (Q5).
9. "Minimum region 4 KB due to Ubuntu page size", "Document status: Frozen": no basis in the code; do not repeat.
10. `axi4_to_axilite.sv` header "peripheral window 0x2000_1000-6FFF": stale.
11. `axilite_to_axi4.sv` "Clock and reset (unused in pure combinatorial adapter)": false; they clock and reset
    the skid buffer.
12. `boot_rom.sv` header "synchronous reset": the flops use `always_ff @(posedge clk or negedge rst_n)`
    (asynchronous) [V].
13. `soc_addr_map_pkg.sv` "The top level and the testbench use decode_slave as the reference model": no file uses
    it [V].
14. `soc_periph_map_pkg.sv` comments "APB peripheral sub-map - 5 slaves", "covers all APB peripheral slots
    (8 x 4 KB)"; `soc_top` comment "APB peripheral ports (all 7 slaves)"; `axi_pkg.sv` "(today) single-beat
    transfers": stale.
15. `test_axil_interconnect.py` docstring "Only the first 8 APB slots have real slaves (APB_N_SLAVES stays 8)",
    "PWM slot ... not yet a real APB slave": stale (14 slots, PWM exists). Describe what the test asserts.
16. `tb_axi4_crossbar.sv` "parameterized unpacked-array ports": the ports are packed.
17. Crossbar header "the fabric cannot deadlock" / "a bad address never stalls a master": true only for masters
    that obey DS-BUS-210-212 and drain responses; the header itself narrows it. Write the narrow form.
18. "Fixed priority ... round-robin is a fairness upgrade if benchmarks show starvation": a design note; do not
    claim that no starvation occurs.
19. The relocated `soc_periph_map_pkg` text cites `rtl/soc/soc_bus.sv:608,652` (file and line): never cite lines.
20. Old DS "Testing recommendations" ("verify invalid addresses return DECERR or pslverr", "misaligned accesses
    trap"): plans, not facts.

### 9.2 Document-versus-RTL (or tool) disagreements - report, do not resolve
1. Reset vector (DS 0x0000_0000) versus `soc_top` `RESET_PC` 0x0000_1000.
2. Memory regions "Reset & Traps", "CPU Debug", "External Memory" versus DECERR in the RTL.
3. SRAM "256 MB main memory" versus `SRAM_MEM_WORDS` storage with repeat (Q5).
4. "Single-master control ring" (DS, RTL header) versus four masters reaching it through the crossbar.
5. `boot_rom` header synchronous reset versus asynchronous flops; mixed reset styles in the fabric:
   synchronous (`axi4_crossbar`, `axi_lite_interconnect`, `axil_to_apb`, both register banks) and asynchronous
   (`axi4_to_axilite`, `axilite_to_axi4`, `boot_rom`) on the same `core_rst_n` [V]. State as a fact; the
   reset-discipline decision is the owner's.
6. `axilite_to_axi4` header (clock unused) versus the RTL.
7. `decode_slave`/`decode_axil_slave` documented as reference models, used by nothing.
8. APB4 PSTRB in reads (Q6).
9. `apb_interconnect` first match versus crossbar/AXI-Lite last match (documented in each module; not a
   contradiction, but two policies; say so once).
10. Old DS "ring" names versus a demux; keep the code name in parentheses once.
11. `tools/verif/coverage_waivers.txt`: `soc_bus | toggle | ^apb_pslverr` says pslverr "can never toggle", and the
    `apb_m_pslverr` waiver says "every APB slave ties pslverr=0". RTL: APB slots 4 and 6 are driven by
    `apb_cdc_bridge` `s_pslverr_o`, which is 1 for an access while the m-face reset (`rst_n_i` resp.
    `cpu_rst_n_i`) is low (DS-CDC-102/103) [V `soc_top` `u_apb_pll_cdc`, `u_apb_pll2_cdc`]. Whether the error is
    reachable in a CI test [Q]. Report to the owner; the waiver file is not touched in these PRs.
12. RTL headers cite "Doc: ds:ch:phase5-soc-integration-plan M3" (not a label) and give no `Doc:` line for
    `axi4_crossbar`, `axi4_to_axilite`, `axilite_to_axi4`, `axi_lite_interconnect`, `axil_to_apb`,
    `apb_interconnect`, `axi_pkg`, `boot_rom` (no new-style header). Follow-up comment PR (Q10).

### 9.3 Reset values that advertise availability (AGENTS.md rule 6), planner's table [V by reading; I for effect]
| Module | Ready outputs while `rst_n` is low |
|---|---|
| `axi4_crossbar` | `m_awready`/`m_arready` = 1 for a master that raises AWVALID/ARVALID (early accept and decode-error accept are combinational from the valid; the FSMs reset synchronously, so nothing is captured): a handshake in reset is lost. |
| `axi4_to_axilite` | `s_awready`, `s_arready` = 1 (state `*_IDLE`). |
| `axilite_to_axi4` | `s_axil_arready` = `m_axi_arready` (pass-through). |
| `axi_lite_interconnect` | All 0 (W_IDLE/R_IDLE drive no ready). |
| `axil_to_apb` | `s_axil_awready`, `s_axil_wready` = 1; `s_axil_arready` = 1 if no AW/W valid. |
| `apb_interconnect` | `pready_o` = 1 when `psel_i` = 0 (combinational). |
| `apb4_register_bank` | `pready` = 1 always. |
| `axi_lite_register_bank` | `s_axil_awready`, `s_axil_wready`, `s_axil_arready` = 1. |
| `boot_rom` | `s_awready`, `s_arready` = 1. |
In the SoC every master and slave of the fabric shares `core_rst_n` with the fabric, and the M0 face of
`u_cpu_axi_cdc` is quiet in reset (DS-CDC-154), so this is inferred harmless today. The one cross-reset pair is
the GPU control slave on `gpu_domain_rst_n` behind the fabric, which is the measured DS-PMU-185 case
(`gpu_top` `s_axil_awready = ~aw_cap_q` high in reset). State the table in TM Known limits / Integration; do not
claim harmlessness as measured.

### 9.4 Design observations for the owner (read from the RTL, not simulated)
1. Crossbar `W_AW`/`R_AR` ready window: the granted master sees the slave's AWREADY/ARREADY a second time; a
   pipelining master would lose its next request. No SoC master pipelines today (DMA, CPU arbiter) [V]; GPU M2 [Q].
2. Two outstanding reads (or writes) of one master to two slaves mix responses / share W beats.
3. Fixed priority without fairness (M0 can hold off the others).
4. WLAST versus AWLEN: the crossbar trusts WLAST, the bridge counts AWLEN; a mismatch hangs the peripheral path.
5. `axi4_to_axilite` ignores AxSIZE/AxBURST (FIXED/WRAP/narrow become INCR 4-byte).
6. `axil_to_apb` drives stale PSTRB in reads; no PPROT.
7. No timeout and no default-slave error path for a slave that does not answer, at any level. The only
   reachable default response is the crossbar DECERR for unmapped addresses; the AXI-Lite DECERR and APB PSLVERR
   defaults are unreachable with the SoC map; the PLL slots can answer SLVERR through their CDC bridges.
8. A GPU power-down with a GPU transaction in flight holds a crossbar engine (clamped BREADY/RREADY) [I]; the
   `u_gif_adapter` skid buffer is outside the GPU reset.
9. Mixed synchronous/asynchronous resets in the fabric on one reset net.
10. SRAM aliasing of a 256 MB window onto 4 KB by default.

---------------------------------------------------------------------------------------------------

## 10. Pinned-text and tool constraints

The content PRs change no source. These constraints matter for the follow-up comment PR (Q10) and tell the
worker not to "fix" a source comment in a docs PR:
- `tools/formal/modules.json` (group "l" of `tools/docs/check_pinned_text.py`) pins exact `find` lines in
  `rtl/soc/axil_to_apb.sv` (`S_ACCESS: if (pready) state_d = ...`), `rtl/soc/boot_rom.sv` (the INCR stride line
  `r_addr_q <= r_addr_q + 32'd4;  // INCR, 4-byte beat` [Q exact]), `rtl/soc/axi_lite_interconnect.sv`
  (`if (a >= SLV_BASE[s] && a <= SLV_LIMIT[s]) decode = 32'(s);`) and `rtl/soc/sram_controller.sv` [V].
- `tools/verif/coverage_waivers.txt` line waivers anchor on comment-stripped text of `default:` arms in
  `axi4_crossbar`, `axi4_to_axilite`, `axi_lite_interconnect`, `axil_to_apb`, `boot_rom`, and on the
  `worse_resp` lines of `axi4_to_axilite` [V]; toggle waivers name `soc_bus`, `axilite_to_axi4`, `boot_rom`
  ports. Run `python tools/verif/coverage_report.py --check-waivers --waivers tools/verif/coverage_waivers.txt`
  after any RTL comment edit (AGENTS.md rule 13).
- `pnr/constraints/phase5_soc.upf` roster lines `# upf-check aon u_bus`, `u_gif_adapter`, `u_boot_rom` (group "f";
  "Do not reword the upf-check lines"); `phase5_soc_rtl_facts.json` lists `u_bus`, `u_gif_adapter`,
  `u_boot_rom` [V]. The ISO_GPU clamp lines on `xbar_m_*[2]` and `gif_axil_*` in `soc_top.sv` are pinned by
  `check_upf.py` and the PMU mutation script (power chapter, section 9 of the PMU order).
- `tools/verif/soc_shards.py` and `tb/tests/test_soc_shards.py` parse `SOC_CI_SUITES` and every `@cocotb.test` of
  the suites (group "g"/"h"); a docs PR adds no test, so nothing changes.
- `tools/verif/equiv_sv2v_module.sh` lists the fabric RTL files [V]; `tb/tests/test_sim_build_key.py` and
  `tools/verif/check_source_closure.py` reference the packages [V].
- No SDC under `pnr/` names a fabric instance [V grep of `*.sdc`/`*.tcl`; only JSON comments mention
  `axi_lite_interconnect` timing history]. Say "no constraint names a fabric path" only after you repeat the grep.
- `python tools/docs/check_pinned_text.py --skip-waivers` must exit 0 at acceptance.
- Out-of-scope source-comment rule violations to report (not fix): history in headers ("Phase 5 (M3)", "bead",
  "GH #", "PR-7", line citations) in `axi4_crossbar.sv`, `axi4_to_axilite.sv`, `axilite_to_axi4.sv`,
  `axi_lite_interconnect.sv`, `axil_to_apb.sv`, `apb_interconnect.sv`, `axi_pkg.sv`, `boot_rom.sv`,
  `soc_periph_map_pkg.sv` (`// Phase 6a`, `// Added before Phase 6`).

---------------------------------------------------------------------------------------------------

## 11. Proofs, commands and PR split

**PR-0 (optional, infrastructure, only with owner approval of Q2 and/or Q4)**
`[Env] Generate the memory map table and accept unpacked arrays in the fact tables`. Branch `env/bus-doc-tools`.
Files: `tools/docs/gen_memory_map.py` (+ `tb/tests/test_docs_gen_memory_map.py` with a negative control: a copy of
the packages with an unclaimed APB page must fail), `docs/manual/common/facts/memory_map.yaml`,
`docs/manual/common/generated/memory-map.tex`, a step in `.github/workflows/docs.yml`; changes to
`tools/docs/gen_fact_tables.py` for unpacked dimensions with tests in the existing test file
[Q name: `tb/tests/test_docs_gen_fact_tables.py`?]. Size about 400 lines. This PR changes `tools/` and
`.github/`; it is not a docs-only PR and needs its own review.

**PR-A - `[Doc] Author the memory map and the crossbar chapters and archive their moved source text`**
Branch `docs/bus-map-crossbar`. Files: new `ds/parts/chapters/bus.tex` (chapter `ds:ch:mod-bus-fabric`; sections
memory map with DS-MAP rules, fabric topology DS-BUS-001-005, `axi4_crossbar` DS-BUS-020-035, contract
DS-BUS-210-223, architecture decisions [Q only decisions the code supports: per-slave depth-1 engines, master
index as ID, fixed priority, decode-error engines per master, packed parameter arrays for Synlig]),
new `tm/parts/chapters/bus.tex` (5.1, 5.2, 5.8, F1, F2, F3-F6, F12), UM chapter `um:ch:bus-integration` (steps 1,
2, 5, 6 parts, 7), `common/facts/bus.yaml` (crossbar only) + generated tables, `ds/generated/requirements-map.tex`,
`requirements-bus.tex`, ledger, archive `cr:arc:ds-soc-addr-map-pkg`, `cr:arc:ds-soc-bus`,
`cr:arc:ds-soc-periph-map-pkg`, `cr:arc:tm-axi4-crossbar`, `cr:arc:ds-memory-map` (per Q3), edits to
`ds/parts/03-module-contracts.tex`, `ds/parts/01-architecture.tex`, `tm/parts/01-module-reference.tex` (remove the
moved sections, `\input{parts/chapters/bus}`, pointer sentences in the soc-fabric chapters), glossary terms
(present: AXI, APB [V]; add AXI4-Lite, DECERR, SLVERR, OKAY, burst, beat, default slave/decode error, memory map,
crossbar, outstanding transaction - check `dictionary.yaml` first), `labels.tsv`.
Size estimate: DS about 500 lines, TM about 650 (7 figures), UM about 120, YAML about 150, generated about 120,
archive about 150 plus the memory-map spans (about 450 with Q3 = a).

**PR-B - `[Doc] Author the bridge and APB chapters and archive their moved source text`** (after PR-A)
Branch `docs/bus-bridges-apb`. DS-BUS-060-195 in the same DS chapter; TM 5.3-5.7, 5.9 with F7-F11; UM steps 3
and 4; `bus.yaml` entries for the remaining modules (or hand-written tables, Q4); archive
`cr:arc:ds-axi-lite-interconnect`, `cr:arc:tm-apb-interconnect`, and (Q9) `cr:arc:ds-apb4-register-bank`,
`cr:arc:ds-axi-lite-register-bank`. Size: DS about 450, TM about 800, UM about 120, YAML about 250, archive about
150.

Acceptance for each content PR (one command at a time; expected result):
1. `python tools/docs/gen_fact_tables.py --family bus`, then `--check` -> exit 0.
2. `python tools/docs/check_requirements.py --write`, then `-v` -> `0 finding(s)`.
3. `python tools/docs/check_doc_labels.py --write-labels`, then `-v` -> 0 findings; for every moved or new label
   `rtk proxy grep -n "^<label>\b" docs/manual/common/labels.tsv` shows the new file.
4. Archive proofs of section 8 (hash identity, line runs, prose_preserve with its negative control reported).
5. `python tools/docs/check_pinned_text.py --skip-waivers` -> exit 0.
6. `python tools/docs/check_comment_budget.py` -> exit 0.
7. `python tools/docs/ste_check.py <each new chapter file>`; review every hint.
8. `python tools/docs/gen_glossary.py`, then `--check` -> exit 0.
9. `python -m pytest tb/tests/test_docs_*.py -q` -> pass.
10. `python tools/docs/build_books.py --timeout 1800` per book -> `undefined=0 multiply-defined=0 glossary=0
    errors=0 ... tallrows=0`; then `--strict ds tm um`.
11. Banned-content scan on the new files: `rtk proxy grep -nE "GH #|PR #|RUN_|20[0-9]{2}-[0-9]{2}-[0-9]{2}|bead|
    PR-7|Phase 5 \(M" <files>` -> no hits.
12. "must" only inside `requirement` bodies: `rtk proxy grep -n "must" <TM and UM files>` -> review each hit.
13. `python tools/verif/check_upf.py -v` and `python tools/verif/check_periph_filelists.py` -> exit 0 (prove that
    nothing outside the books changed).
Not run by the worker (state so in the PR): every cocotb suite, `coverage_report.py` (needs coverage data), the
formal harness, `equiv_sv2v_module.sh`.
Fast iteration: scratch driver as in the pilot (`\documentclass[book=tm]{cvtdocs}` + `\input{parts/chapters/bus}`).

---------------------------------------------------------------------------------------------------

## 12. Open questions for the owner

**Q1. Requirement areas.** (a) Two areas: `DS-MAP` (memory map) and `DS-BUS` (fabric). (b) One area `DS-BUS`.
(c) Three areas: `DS-MAP`, `DS-AXI` (crossbar and AXI bridges), `DS-APB` (APB side). Recommendation: (a) - the map
is what firmware reads and may later get a check of its own; the fabric is one area.

**Q2. Source of the memory-map table.** (a) New generator `tools/docs/gen_memory_map.py` with a sidecar and a
`--check` step in `docs.yml`, which also checks DS-MAP-004 (infrastructure PR-0). (b) Hand-written table plus a
pytest that compares it with the packages. (c) Hand-written table, review only. Recommendation: (a); the packages
change each time a peripheral is added (six times in Phase 6), and the old table went stale exactly that way.

**Q3. The converted MEMORY_MAP document** (one `relocated` block of about 1 750 lines in `ds:ch:memory-map`).
(a) Archive the global map, the phase maps, the reset/trap/alignment/permission text, the SoC interconnect and the
testing recommendations; keep the register maps of the debug port, the GPU and the peripherals in DS until their
areas are authored; the authored map replaces the archived part. (b) Archive the whole block; the register-map
sub-labels move into the Changes record. (c) Leave the block and add the authored map beside it. Recommendation:
(a) - tests and `reg_maps.py` cite the register-map labels, and they describe other areas.

**Q4. Fact tables for modules with unpacked arrays** (`apb_interconnect`, `soc_bus`, both register banks) and
for `boot_rom` (`ifdef` in the header). (a) Extend `gen_fact_tables.py` in PR-0; for `boot_rom` a one-line RTL
cleanup later (both `ifdef` arms are the same). (b) Hand-written tables with a stated reason. (c) No tables for
these modules. Recommendation: (a) for the arrays, (b) for `boot_rom` until the RTL cleanup.

**Q5. SRAM size and repeat.** The decode window is 256 MB; the storage is `SRAM_MEM_WORDS` words (4 KB at the
`soc_top` default) and repeats. Tests use the repeat (alias walks). (a) Specify that only
`SRAM_BASE .. SRAM_BASE + SRAM_MEM_WORDS*4 - 1` is defined and that software must not rely on the repeat; the TM
states the repeat as model behaviour that the walks measure. (b) Specify the repeat as architecture. (c) Specify
256 MB and record the model shortfall as a known limit. Recommendation: (a).

**Q6. PSTRB during APB reads.** `axil_to_apb` drives the strobes of the previous write in a read; the planner
reads the APB4 specification as asking for PSTRB low in reads. No SoC slave uses PSTRB in a read. (a) Document it
as a known limit now and open a tracker item for an RTL fix (`pstrb` = 0 when `!is_write_q`). (b) Write the DS
rule now (verify `review`, RTL fix in a later PR, rule failing until then). (c) Accept as is and document.
Recommendation: (a).

**Q7. Crossbar master contract** (observations 9.4 items 1-3). (a) Specify the contract on masters
(DS-BUS-210-212) and list the hazards as known limits; no RTL change now. (b) Also open RTL work: stop passing
`s_awready`/`s_arready` to the master in `W_AW`/`R_AR`, and add round-robin. (c) Treat the crossbar as able to
take pipelined masters and fix the RTL before documenting. Recommendation: (a) now, with (b) as a tracker item.

**Q8. GPU bus traffic at a GPU power-down.** A GPU transaction in flight when the clamp rises holds a crossbar
engine [I]. (a) Add a power software rule (next free `DS-PMU-18x`, power chapter) "stop GPU bus traffic before
GPU_OFF", cross-referenced from the bus chapter; the bus chapter states the fabric behaviour. (b) Only a bus known
limit. (c) RTL change (drain or abort in the fabric). Recommendation: (a); it is the GPU counterpart of
DS-PMU-182, which the owner already approved for the CPU.

**Q9. Where the register banks and `boot_rom` are described.** (a) In the bus chapter (bus-side behaviour), with
`ds:mod:apb4-register-bank` and `ds:mod:axi-lite-register-bank` moving there and a new `ds:mod:boot-rom`;
peripheral chapters later cite them. (b) Keep the register banks in the soc-fabric chapter as relocated text and
give `boot_rom` a section in the soc-fabric chapter. Recommendation: (a).

**Q10. Stale RTL headers** (section 9.1 items 10-16, 9.2 item 12). (a) A separate comment-only PR after PR-B,
with the pinned-text, waiver and formal-anchor checks of section 10. (b) Leave them until each file is touched.
Recommendation: (a), because several headers contradict the new chapters.

Not owner questions (settled from the code, listed so nobody asks): the region bases and limits, the overlap
policies, the decode-error behaviour, the engine structure, the ID tagging, the absence of any timeout, the label
moves, and the terminology (keep the RTL terms master and slave; mention the AMBA terms manager and subordinate
once in the Definitions).


## Owner decisions (final; these override any option text above)

- Q1 (primary planner): two ID areas, `DS-MAP-NNN` and `DS-BUS-NNN`.
- Q2 (owner): the memory-map table is GENERATED. PR-0 (infrastructure) comes first: a generator that
  reads `soc_addr_map_pkg` and `soc_periph_map_pkg` and writes the table, with `--check` as a CI drift
  gate that also proves that every page of the peripheral window is claimed.
- Q3 (owner): archive the global map, interconnect, reset/trap and testing parts of the old MEMORY_MAP
  document. The per-peripheral register maps stay in the DS until the peripherals chapter.
- Q4 (owner, with Q2): PR-0 also extends `gen_fact_tables.py` to read unpacked-array ports, so
  `apb_interconnect`, `soc_bus` and the register banks get generated tables. `boot_rom`: hand-written
  table only if the generator still cannot read it; say so in the chapter.
- Q5 (owner): **specify the repeat.** The DS rule states the SRAM window, the realised storage size
  (the parameter), and that the storage repeats across the window. This is specification, not a model
  property. The old "256 MB of main memory" statement is not repeated; report it as a disagreement.
- Q6 and Q7 (owner): the DS states a contract on masters (one transfer in flight per direction; wait for
  completion), review-only. The TM known limits state, as read from the RTL and not simulated: the
  crossbar second-ready window and the mixed beats; fixed-priority arbitration with no fairness; PSTRB
  driven with old write strobes during reads. Tracker issues exist on GitHub; do not cite numbers.
- Q8 (owner): add a software rule in the DS-PMU area: software must stop GPU bus traffic before it
  requests GPU_OFF (the GPU counterpart of DS-PMU-182), review-only. It goes in
  `ds/parts/chapters/power.tex` with the next free number of its block, in PR-A.
- Q9 (primary planner): the register banks and `boot_rom` are described in the bus chapter (bus
  behaviour only).
- Q10 (primary planner): stale RTL headers go to a separate comment-only PR after PR-B.
- Doc PRs run one at a time (each regenerates `labels.tsv`). The git remote is `claude_verilog_test`.
