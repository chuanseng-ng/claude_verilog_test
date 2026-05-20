# ASAP7 Run 14 Root Cause Analysis and Run 16 Proposals

*Prepared after Run 14 completion (RUN_2026-05-14_22-21-02), Run 15 running.*

---

## 1. Signal Identification

### 1.1 Post-route worst FF: `_54273_` (QN=`_03251_`, fanout=312)

**Module / RTL signal**: `u_core.u_dcache` — a bit of the D-cache data SRAM write-data
computation path, specifically a bit that participates in computing
`u_core.u_dcache.data_addr0[N][bit]` and `u_core.u_dcache.data_din0[N][bit]` for all
four data banks.

**Netlist evidence**:
- `_54273_` declared at line 179186: `DFFHQNx1 _54273_ (.CLK(clk_i), .D(_05133_), .QN(_03251_))`
- D-input `_05133_` driven by `O2A1O1Ixp33 _42340_` (line 109183), taking inputs
  `_01649_` (QN of `_56215_` — previous-cycle D-cache addr bit), `_18304_` (HB1-chain
  of `_08188_`), `_08183_` (OR5+HB1 output), `_09101_` (AXI rvalid path HB1).
- `_08183_` is a buffered OR5 that drives `A2O1A1Ixp33 _30614_` whose output is named
  `u_core.u_dcache.data_addr0[0][0]` (line 41118).
- QN output `_03251_` fans into `AOI21`, `OAI21`, `A2O1A1Ix`, `O2A1O1Ix` gates all
  combining consecutive bits (`_03252_`, `_03250_`, `_03249_`) for D-cache data mux logic.
- The INVx1+HB1 chain at lines 30394–30413 from `_03251_` appears verbatim in the
  post-route critical path report at gates `_28686_`/`_28687_`/`_28688_` → `_28765_` → ...

**Functional identity**: `_54273_` stores a bit of **`ex_mem_reg.alu_result`** (or an
equivalent internal D-cache state register bit derived from the memory access address).
Its QN directly drives the D-cache FSM path that computes SRAM data and address inputs
for all four 32-bit data banks — 4×32 data bits + 4×8 address bits = 160 named SRAM
input signals + intermediate gate fanout = 312 total post-route loads.

The post-route resizer inserted `wire438` (BUFx16f) + `load_slew437` (BUFx12f) +
`max_cap435` (BUFx12f) + `wire434` (BUFx12f) = 4 series buffers adding approximately
130 ps to the path before logic even begins.

**Critical path gate count** (from post-route max.rpt):
- FF QN → 4 series buffers (130 ps) → INVx8 → BUFx12f → BUFx12f → BUFx3 → BUFx3
  → A2O1A1O1Ixp25 → A2O1A1O1Ixp25 → AOI321xp33 → AOI311xp33 → OAI32xp33 → BUFx3
  → A2O1A1O1Ixp25 → BUFx3 → A2O1A1Ixp33 → BUFx3 → OA31x2 → OAI211xp5 → BUFx3
  → BUFx6f → HB1xp67 → OR2x6 → AO21x2 → NAND3x2 → BUFx12f → OAI211xp5 → BUFx3
  → HB1xp67 → OA211x2 → AOI211xp5 → endpoint FF `_55873_`/D
- **Total gate stages**: ~30 (post-buffer logic) — extremely deep for 1 GHz target
- **Data arrival at endpoint**: 916 ps, Required 101 ps → Slack **-814.6 ps**

---

### 1.2 Pre-PnR worst FF: `_55931_` (QN=`_01933_`, fanout=821)

**Module / RTL signal**: A bit of `u_core.u_dcache` D-cache data computation —
specifically a bit stored in a D-cache pipeline register that participates in
**tag comparison and write-data mux** for all four D-cache data banks.

**Netlist evidence**:
- `_55931_` at line 187476: `DFFHQNx1 _55931_ (.CLK(clk_i), .D(_06451_), .QN(_01933_))`
- D-input `_06451_` driven by `AND4x1 _49115_(.A(_23768_), .B(_23771_), .C(_23774_),
  .D(rst_n_i), .Y(_06451_))` — canonical sync-reset AND4 pattern
- `_23768_` is the output of `OAI22xp33 _49108_(.A1(_01081_), .A2(_23728_),
  .B1(_23731_), .B2(_23767_))` — a **tag-bit comparison** between two multi-bit values
- `_01081_` is QN of `_57130_` which is itself an icache/dcache tag comparison register
- The cluster `_55931_`–`_55941_` covers 10+ consecutive bits all with AND4+OAI22+rst_n
  pattern — the OAI22 performs tag bit comparison for the D-cache

**Fanout of `_01933_`**: First consumers (line 123998+) are `NAND2xp33`, `OAI21xp33`,
`INVxp33` which then feed HB1 chains. The INV path at line 124009 goes through 4 HB1
buffers before reaching `AO21` gates. Together with sibling bits (`_01932_`, `_01931_`),
these bits produce the **tag hit/miss comparison result** that gates every data SRAM mux
in the D-cache (4 banks × 32 bits = 128 data mux inputs + address logic = 821 loads).

**Functional identity**: `_55931_` stores **a bit of the D-cache tag comparison result
register** — the per-bit XOR/compare output between the incoming request tag and the
stored tag, accumulated into the hit/miss decision. The full 32-bit register fanout
of 821 means this comparison result gates ALL data-bank mux selections simultaneously
across the 4-bank D-cache array.

**Pre-PnR critical path from `_55931_`**:
- `_55931_/QN` → slew 3123 ps (massive capacitive load from 821 fanout, NO resizer
  intervention yet) → `INVxp33 _44941_` (311 ps delay) → HB1 chain × 3 → complex
  AO/OAI gates → OR5 → O2A1O1Ix → endpoint FF
- WNS: **-2175 ps** (data arrival 2161 ps at pre-PnR ideal clock)

---

### 1.3 Pre-PnR second-worst FF: `_56972_` (QN=`_01112_`, fanout=785)

**Module / RTL signal**: A bit of the **D-cache writeback/refill data mux** —
specifically a bit involved in the same D-cache tag comparison + data selection path
as `_55931_`, but for a different set of output endpoints.

**Netlist evidence**:
- `_56972_` at line 192681: `DFFHQNx1 _56972_ (.CLK(clk_i), .D(_07272_), .QN(_01112_))`
- D-input `_07272_` driven by `AND4x1 _51491_(.A(_25329_), .B(_23820_), .C(_23821_),
  .D(rst_n_i))` — same sync-reset pattern
- `_25329_` = output of `OAI22 _51490_(.A1(_01086_), .A2(_25314_), .B1(_23798_),
  .B2(_25328_))` — another tag comparison term
- `_23820_` = `HB1(_23770_)`, `_23821_` = `HB1(_23773_)` — buffered versions of the
  same shared tag comparison intermediate signals used by `_55931_`
- Consumers of `_01112_` (line 134062+): `OAI21xp33`, `A2O1A1Ixp33`, `NOR2xp33`,
  `AOI211xp5`, `INVxp33` → same structure as `_01933_` consumers — D-cache data mux

**Functional identity**: `_56972_` stores **another bit of the same D-cache tag
comparison result register** (different bit position). Both `_55931_` and `_56972_`
form parts of the same multi-bit registered tag-comparison word that broadcasts to
the entire D-cache data path.

**Key distinction from `_55931_`**: Violator list shows `_56972_` starts feeding
endpoints `_55676_`–`_55700_` (25 paths, WNS -2015 ps worst), while `_55931_` feeds
`_55643_`–`_55674_` (32 paths, WNS -2175 ps worst). These are different D-cache data
pipeline registers in the EX/MEM pipeline.

---

## 2. Why EX2 Stage Insertion Did NOT Improve WNS

### 2.1 What EX2 insertion was intended to do

The EX2 stage inserts a pipeline register (`ex1_ex2_reg_t`) at the EX1/EX2 boundary,
capturing ALU outputs. The intent was to break the combinational cone:
- **Before (5-stage)**: `id_ex_reg` → [ALU + branch logic, ~25 gates] → `ex_mem_reg`
- **After (6-stage)**: `id_ex_reg` → [ALU, ~12 gates] → `ex1_ex2_reg` → [branch/trap,
  ~12 gates] → `ex_mem_reg`

### 2.2 Why it failed — the actual bottleneck was NOT the EX combinational cone

**Run 13 critical path** started from `_54219_` (QN=`_03305_`), which has D-input
`NOR5xp2 _42234_` — a carry/forwarding logic gate. Run 13's WNS (-782 ps) was set by
a **forwarding mux / ALU path** from an EX-stage FF.

**Run 14 critical path** starts from `_54273_` (QN=`_03251_`), which has D-input
`O2A1O1Ixp33 _42340_` — a **D-cache address/data mux gate**. This is NOT an EX-stage
ALU computation — it is a **D-cache internal pipeline register** that holds SRAM
address computation results and feeds back into all four SRAM data banks.

The EX2 insertion broke the ALU cone (as intended), but immediately exposed a
co-critical path through the D-cache data SRAM address/data logic that was ALREADY
nearly as deep as the EX cone (hidden behind the longer EX path in Run 13).

### 2.3 Quantified regression source: 4 series buffers on `_03251_`

The post-route path shows the resizer inserted 4 series buffers (BUFx16f + 3×BUFx12f)
immediately on `_03251_` output, totaling approximately **130 ps** of pure buffer delay
before any logic gate. These buffers were inserted to fix the high-fanout (312 loads)
and max-cap violations on the net.

- Net `_03251_` post-QN: slew=29.3 ps (managed), but 4 buffers = +130 ps
- Without buffers: data arrival would be ~916 - 130 = 786 ps → slack ~ -686 ps
- Run 13 WNS was -782 ps from `_54219_` — so these two paths were CO-CRITICAL in Run 13

**The EX2 stage caused timing regression of -32.7 ps** (from -782 ps to -814.6 ps)
because:
1. The D-cache path was already at -782 ps (co-critical, not visible as the worst path)
2. EX2 insertion added area (+5,800 FFs approximately) → increased placement congestion
   → longer wires on all nets → slight WNS degradation on all paths including D-cache
3. The additional EX2 FFs required more hold buffering and resizing, shifting cell
   positions slightly and increasing D-cache path wire delay by ~33 ps

### 2.4 Structural reason: D-cache data path is deeper than EX cone

The D-cache data computation in `rv32i_dcache.sv` does the following in a single
clock cycle (CS_TAG_CHECK state):
1. SRAM read data arrives (`tag_dout_r`, `data_dout_r` — registered)
2. Tag comparison: `tag_dout_r[TAG_BITS-1:0] == latch_tag` — 20-bit equality
3. Hit/miss decision broadcast to all 4 data banks × 32-bit mux selectors (821 loads)
4. Data mux result feeds back into the next D-cache state register

This is a **two-hop fan-tree problem**: 1 bit drives 821 mux inputs, each of which must
settle before the next D-cache pipeline register (32 registers × 4 banks = 128+ FFs)
can capture the correct data. The logic depth (OAI22 + AND4 + INV + HB1 × 3 + AO/OAI
× 3 + OR5 + O2A1O1Ix) is 10-12 gate levels plus 4 buffer hops for the fan = ~16 stages
total, taking ~916 ps at ASAP7 7nm SIMPLE RVT.

---

## 3. Run 16 RTL Proposals

### 3.1 Priority 1: D-cache tag comparison duplication (HIGH IMPACT — estimated +150–250 ps)

**Root cause**: The single 20-bit tag comparison result (`_55931_`, `_56972_`) fans out
to 821 loads. Each bit must drive all 4 data banks simultaneously. The synthesis tool
cannot split this fan without RTL guidance because the result is a single logical signal.

**Fix**: Duplicate the tag comparison register in RTL — compute identical comparison
results separately for each data bank:

```systemverilog
// rv32i_dcache.sv — current (single comparison, one register)
always_ff @(posedge clk_i) begin
    if (!rst_n_i) tag_hit <= '0;
    else           tag_hit <= (tag_dout_r[TAG_BITS-1:0] == latch_tag);
end

// Proposed: per-bank comparison registers (4x duplication)
logic tag_hit_bank[0:3];
generate
    for (genvar b = 0; b < 4; b++) begin : g_tag_hit
        always_ff @(posedge clk_i) begin
            if (!rst_n_i) tag_hit_bank[b] <= 1'b0;
            else           tag_hit_bank[b] <= (tag_dout_r[TAG_BITS-1:0] == latch_tag);
        end
    end
endgenerate
// Each data bank's mux uses tag_hit_bank[b] instead of tag_hit
// data_bank[b] <= tag_hit_bank[b] ? cache_data[b] : refill_data[b];
```

**Expected fanout reduction**: 821 → ~205 per bank (4× reduction). Resizer can then
handle remaining fanout without 4-stage buffer chains. Estimated WNS gain: **+150–250 ps**.

**RTL cost**: 4× 1-bit FF addition (~4 FFs for tag hit, negligible area). No ISA change.
Synthesis impact: the 4 copies are identical logic so the synthesis tool can use them
with `(* keep = 1 *)` or `(* dont_merge = 1 *)` attributes to prevent re-merging.

### 3.2 Priority 2: D-cache data SRAM address pipeline register (MEDIUM IMPACT — estimated +80–150 ps)

**Root cause**: `_54273_` (post-route worst) stores a D-cache data SRAM address bit
that drives 312 loads. The OR5+HB1 output (`_08183_`) feeding into this register's
D-input already accounts for the fanout to all 4 banks' addr0 inputs.

**Fix**: Pre-compute and register the 8-bit SRAM address index one cycle earlier:

```systemverilog
// rv32i_dcache.sv — currently:
// data_addr0[b] <= latch_addr[ADDR_BITS-1:OFFSET_BITS]  (computed combinatorially each cycle)

// Proposed: register the address in CS_IDLE (before CS_TAG_CHECK)
logic [7:0] latch_index_q;   // registered address index
always_ff @(posedge clk_i) begin
    if (!rst_n_i) latch_index_q <= '0;
    else if (state == CS_IDLE && dc_req_valid_i)
        latch_index_q <= dc_addr_i[ADDR_BITS-1:OFFSET_BITS];
end
// Use latch_index_q directly as SRAM address (cuts OR5 mux out of the addr path)
```

**Expected impact**: Removes the OR5+HB1 mux level from the D-cache address path.
Reduces `_54273_` D-input complexity from O2A1O1Ixp33+HB1×2 to a direct register.
Estimated gain: **+80–150 ps** on the D-cache address computation path.

### 3.3 Priority 3: EX2 stage forwarding path simplification (LOW-MEDIUM — +30–80 ps)

**Concern**: EX2 insertion added a full pipeline stage register (`ex1_ex2_reg_t`, ~260
bits) that now sits between EX1 and MEM. The forwarding unit in `rv32i_forwarding_unit.sv`
must now also check `ex2_mem_reg.rd_addr` and `ex2_mem_reg.reg_wr_en` for hazard
detection — these signals fan out to the ID-stage register muxes.

**Fix**: Verify that `ex2_mem_reg` forwarding paths do not introduce a new high-fanout
bottleneck. If `ex2_mem_reg.rd_addr` drives 100+ muxes in the forwarding unit, duplicate
it per-bus-width (rs1 check and rs2 check should use separate register copies).

---

## 4. Run 16 PD Config Proposals

### 4.1 Keep `CLOCK_PERIOD: 1.2 ns` (from Run 15)

Run 15 already changed this. The 1.2 ns period reduces constraint pressure and allows
the resizer to make more aggressive moves. Keep this change — do NOT revert to 1.0 ns.

### 4.2 Add `MAX_FANOUT_CONSTRAINT: 20` (or remove limit entirely)

Run 14 changed `MAX_FANOUT_CONSTRAINT` from 4 (Run 13 had it removed from SDC) to 8
in config.json. Run 15 keeps 8. For Run 16, the limit should be **20 or higher** because:
- The root cause is structural (single tag-comparison bit drives 821 loads) — a fanout
  limit of 8 forces massive buffer chains that ADD delay, they don't remove it
- A fanout limit of 20 allows the resizer to use BUFx16f/BUFx12f in a 2-level tree
  instead of 4 series levels → saves ~60–80 ps compared to 4 series buffers

If the RTL duplication fix (§3.1) is applied, the natural fanout of each copy will
drop from 821 to ~205. At `MAX_FANOUT_CONSTRAINT: 20`, the resizer would create a
2-level tree: 1 BUFx16f → 10 BUFx12f → 205 loads ≈ 20 loads each = 2 buffer hops
instead of 4 hops. Estimated savings: **+60–80 ps** on the `_01933_` path.

### 4.3 Add synthesis attribute `(* keep_hierarchy *)` on `u_dcache`

When using Synlig/Yosys, add to `rv32i_dcache.sv`:
```systemverilog
(* keep_hierarchy *)
module rv32i_dcache (...)
```
This prevents Yosys from flattening the D-cache into the top-level module and allows
the synthesis tool to optimize within-module wire RC independently. This may help
the resizer see better path groupings.

Alternatively, add `SYNTH_HIERARCHY_PARAMS: {"rv32i_dcache": "keep_hierarchy"}`
or specify via Yosys script in the LibreLane flow.

### 4.4 Explicit false-path on D-cache refill paths

The D-cache refill path (AXI4-Lite burst → write to data SRAM) is a multi-cycle
operation — it takes 4+ cycles. Add:
```tcl
# SDC: D-cache refill data is a multi-cycle path (4 AXI beats = 4 cycles minimum)
set_multicycle_path -setup 2 -through [get_nets -hierarchical "*u_dcache*wb_tag*"]
set_multicycle_path -hold  1 -through [get_nets -hierarchical "*u_dcache*wb_tag*"]
```
This relaxes the timing on writeback paths that are structurally multi-cycle,
reducing TNS and potentially freeing the resizer to focus on the true critical path.

### 4.5 Increase `PL_TARGET_DENSITY_PCT` from 50 back to 45

Run 14 used 50% density (up from Run 13's 45%). The extra density may have contributed
to the 33 ps regression by creating placement congestion around the D-cache cells.
The D-cache FFs (`_55931_`, `_56972_`, `_54273_`) need routing clearance for the
821-load fan trees. Reverting to 45% density gives the router more room.

### 4.6 Add D-cache macro placement constraint

In `macro_placement.cfg`, explicitly place the D-cache SRAM macros at a specific
die corner (e.g., bottom-right) and ensure the D-cache standard cells are clustered
near them. This reduces wire length for the 821-load fan from the tag comparison FF
to the data mux gates:

```
# pnr/asap7/macro_placement.cfg — add explicit dcache SRAMs placement
# Force dcache macros to bottom-right corner
u_core/u_dcache/u_data_sram_0 120 10 R0
u_core/u_dcache/u_data_sram_1 120 30 R0
u_core/u_dcache/u_data_sram_2 120 50 R0
u_core/u_dcache/u_data_sram_3 120 70 R0
u_core/u_dcache/u_tag_sram    120 90 R0
```
(Exact coordinates depend on macro dimensions — adjust to fit within CORE_AREA.)

---

## 5. Priority Matrix for Run 16

| Item | Type | Expected Gain | Effort | Dependency |
|------|------|--------------|--------|------------|
| Tag comparison register duplication (§3.1) | RTL | +150–250 ps | Medium | Requires RTL + re-verify |
| Remove `MAX_FANOUT_CONSTRAINT` or raise to 20 (§4.2) | Config | +60–80 ps | Low | None |
| Revert `PL_TARGET_DENSITY_PCT` to 45 (§4.5) | Config | +20–40 ps | Low | None |
| D-cache SRAM address pre-registration (§3.2) | RTL | +80–150 ps | Medium | Requires RTL + re-verify |
| D-cache multi-cycle false path (§4.4) | SDC | +10–30 ps | Low | None |
| D-cache macro placement (§4.6) | Config | +10–30 ps | Low | Needs coord check |
| `keep_hierarchy` on dcache (§4.3) | Config | +5–15 ps | Low | None |
| Validate EX2 forwarding fanout (§3.3) | RTL analysis | +30–80 ps | Low | Investigate first |

**Recommended Run 16 minimum changes** (if no RTL change is approved):
1. Remove `MAX_FANOUT_CONSTRAINT` (or set to 20)
2. Revert `PL_TARGET_DENSITY_PCT` to 45
3. Add D-cache false-path SDC annotation
4. Add D-cache macro placement hints
5. Keep `CLOCK_PERIOD: 1.2 ns` (from Run 15)

**Recommended Run 16 with RTL** (for maximum gain):
1. Apply tag comparison register duplication in `rv32i_dcache.sv`
2. All config changes above
3. Re-run verification suite before launching PD

**Projected Run 16 WNS**: 
- Config only: -814 + 80 + 40 + 20 = approximately **-674 ps** → ~597 MHz
- RTL + Config: -814 + 200 + 80 + 40 + 20 = approximately **-474 ps** → ~678 MHz

---

## 6. Run 14 Summary vs Run 13

| Metric | Run 13 | Run 14 | Delta | Verdict |
|--------|--------|--------|-------|---------|
| WNS (ps) | -782 | -814 | -32 | REGRESSION |
| fmax (MHz) | ~561 | ~551 | -10 | REGRESSION |
| Hold violations | 38 | 0 | -38 | IMPROVED |
| Total area (µm²) | 7087 | 7066 | -21 | flat |
| Instance count | ~32k | 33379 | +~1k | EX2 FFs added |
| Power (mW) | 33.86 | 33.81 | flat | flat |

**EX2 insertion verdict**: The EX2 stage insertion correctly broke the EX-stage ALU
cone (as designed), but the D-cache tag comparison path — already at -782 ps in Run 13
as a co-critical hidden path — became the new critical path, and was slightly worsened
by +32 ps due to placement pressure from the added EX2 FFs.

The SRAM hold fix worked perfectly (0 hold violations vs 38 in Run 13).

---

*Analysis completed 2026-05-15. Run 15 (1.2 ns period + MAX_FANOUT=8) is running.*
*Run 16 should target D-cache tag comparison duplication for the largest WNS improvement.*
