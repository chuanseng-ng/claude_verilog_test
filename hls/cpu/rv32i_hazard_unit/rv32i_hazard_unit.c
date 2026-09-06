/* =====================================================================
 * rv32i_hazard_unit.c -- RV32I pipeline hazard-detection + forwarding
 *                        unit, C source for Bambu HLS (PandA 2024.10),
 *                        GH #119 "NL -> C -> RTL" pilot.
 *
 * WHAT THIS IMPLEMENTS
 * --------------------
 * The purely combinational hazard/forward controller for the EX2-retimed
 * RV32I pipeline:
 *
 *   IF / ID / EX1a / EX1c(reg) / EX1b / EX1b2(reg) / EX2(reg) / MEM / WB
 *
 * It produces (a) the stall/flush enables for every pipeline register,
 * (b) the forwarding-mux selects for the instruction in EX1a, and (c) a
 * pre-decoded copy of those selects for the instruction still in ID, which
 * the caller registers into the ID/EX boundary.
 *
 * STAGE <-> REGISTER MAP (derived, see ASSUMPTIONS.md B1)
 * ------------------------------------------------------
 * The port documentation names each input group by the register it comes
 * from, and separately says which stage that register's OUTPUT is sitting
 * in.  Ordering them by "cycles behind the instruction in EX1a" gives:
 *
 *   port group   register            output stage   behind EX1a
 *   ----------   -----------------   ------------   -----------
 *   id_ex_*      id_ex               EX1a            0
 *   ex1b_*       ex1a_ex1b_reg       EX1c            1   <- fwd sel 2'b11
 *   ex1c_*       ex1c_ex1b_reg       EX1b            2   <- fwd_*_ex1c
 *   ex1b2_*      ex1b_ex2_reg_q      EX2             3   <- fwd_*_ex1b2
 *   ex_mem_*     ex_mem              MEM             4   <- fwd sel 2'b01
 *   mem_wb_*     mem_wb              WB              5   <- fwd sel 2'b10
 *
 * The "ex1b_/ex1c_" prefixes are deliberately crossed with the stage names
 * (the port doc says so: the names are kept for backward compatibility).
 * Everything below follows the *register* identity, never the prefix.
 *
 * A stall_<reg> output holds that register; a flush_<reg> output injects a
 * bubble into it.  Because a flush takes effect at the NEXT clock edge, a
 * flush of the FF between stage X and stage Y kills the instruction that is
 * currently in X.  So the "flush <stage>" wording of the spec maps as:
 *
 *   flush IF    -> flush_if_id          (IF/ID FF)
 *   flush ID    -> flush_id_ex          (ID/EX FF)
 *   flush EX1a  -> flush_ex1a_ex1b_o    (EX1a->EX1c FF)
 *   flush EX1c  -> flush_ex1c_ex1b_o    (EX1c->EX1b FF)
 *   flush EX1b  -> flush_ex1_ex2_o      (EX1b->EX2 FF, ex1b_ex2_reg_q)
 *   flush EX2   -> flush_ex_mem         (EX2->MEM FF)
 *
 * HARDWARE INTERFACE MAPPING
 * --------------------------
 * There is no clock, no reset and no state in this C source: the block is a
 * pure function of its inputs.  Bambu wraps it in its own start/done
 * handshake (the integrating shim ties start high and ignores done, exactly
 * as for a combinational block).  Every input is a scalar `unsigned` by
 * value and every output a pointer-out parameter tagged `mode = none`, so
 * each becomes a plain wire rather than a BRAM-style port group.
 *
 * Constraints honoured: plain C99, no dynamic allocation, no libc calls,
 * no floating point, no recursion, no memory interface of any kind.
 *
 * ASSUMPTIONS: every place the spec was silent is marked with an
 * `ASSUMPTION n:` comment below and expanded in ASSUMPTIONS.md.
 * ===================================================================== */

#pragma HLS interface port = stall_pc mode = none
#pragma HLS interface port = stall_if_id mode = none
#pragma HLS interface port = stall_id_ex mode = none
#pragma HLS interface port = stall_ex_mem mode = none
#pragma HLS interface port = stall_ex1_ex2_o mode = none
#pragma HLS interface port = stall_ex1a_ex1b_o mode = none
#pragma HLS interface port = stall_ex1c_ex1b_o mode = none
#pragma HLS interface port = flush_if_id mode = none
#pragma HLS interface port = flush_id_ex mode = none
#pragma HLS interface port = flush_ex_mem mode = none
#pragma HLS interface port = flush_ex1_ex2_o mode = none
#pragma HLS interface port = flush_ex1a_ex1b_o mode = none
#pragma HLS interface port = flush_ex1c_ex1b_o mode = none
#pragma HLS interface port = fwd_a_sel mode = none
#pragma HLS interface port = fwd_b_sel mode = none
#pragma HLS interface port = fwd_store_sel mode = none
#pragma HLS interface port = fwd_a_ex1c mode = none
#pragma HLS interface port = fwd_b_ex1c mode = none
#pragma HLS interface port = fwd_store_ex1c mode = none
#pragma HLS interface port = fwd_a_ex1b2 mode = none
#pragma HLS interface port = fwd_b_ex1b2 mode = none
#pragma HLS interface port = fwd_store_ex1b2 mode = none
#pragma HLS interface port = fwd_a_sel_pre mode = none
#pragma HLS interface port = fwd_a_ex1c_pre mode = none
#pragma HLS interface port = fwd_a_ex1b2_pre mode = none
#pragma HLS interface port = fwd_b_sel_pre mode = none
#pragma HLS interface port = fwd_b_ex1c_pre mode = none
#pragma HLS interface port = fwd_b_ex1b2_pre mode = none

/* Architectural register addresses are 5 bits (RV32I). Inputs arrive as
 * 32-bit words on the Bambu interface, so every address is masked before
 * use. ASSUMPTION 1: bits [31:5] of an address port are IGNORED rather than
 * being an error -- a wrapper that sign-extends or leaves junk in the upper
 * bits still behaves correctly, and no fault channel exists to report it. */
#define REG_ADDR_MASK 0x1Fu

/* Forwarding-mux encoding on fwd_*_sel (given verbatim by the spec). */
#define FWD_SEL_REGFILE 0u /* 2'b00 */
#define FWD_SEL_EX2     1u /* 2'b01 -- ex_mem result, 4 behind EX1a */
#define FWD_SEL_WB      2u /* 2'b10 -- mem_wb result, 5 behind EX1a */
#define FWD_SEL_EX1B    3u /* 2'b11 -- ex1a_ex1b_reg result, 1 behind EX1a */

/* Internal tier codes produced by FWD_TIER(). These are NOT port encodings;
 * they name the winning producer so the caller can drive the three separate
 * output groups (sel[2], the ex1c bit, the ex1b2 bit) consistently. */
#define TIER_NONE  0u
#define TIER_EX1B  1u /* 1 stage behind EX1a -- highest priority */
#define TIER_EX1C  2u /* 2 stages behind */
#define TIER_EX1B2 3u /* 3 stages behind */
#define TIER_EX2   4u /* 4 stages behind */
#define TIER_WB    5u /* 5 stages behind -- lowest forwarding priority */

/* ---------------------------------------------------------------------
 * One operand's forwarding decision.
 *
 * ASSUMPTION 2 -- a SINGLE strict priority cascade, i.e. the three output
 * groups are mutually exclusive.
 * The spec describes the tiers relationally ("EX1c overrides EX2 but not the
 * EX1b tier"; "EX1b2 has priority between the EX1c and EX2 tiers"), which
 * yields one total order:  EX1b > EX1c > EX1b2 > EX2 > WB > regfile.
 * Two implementations satisfy that description:
 *   (a) one cascade -- at most ONE of {sel != 00, ex1c, ex1b2} is asserted,
 *       the losing groups are driven to their inactive value; or
 *   (b) three INDEPENDENT comparators -- sel could read 2'b01 (EX2) while
 *       ex1c is simultaneously 1, and the datapath mux resolves the clash.
 * Both drive the same operand value into the ALU, so they are functionally
 * equivalent, but they differ bit-for-bit on the "losing" ports. We choose
 * (a): it is the common single-always_comb RTL idiom, it makes the outputs
 * self-describing (the winner is readable from the ports alone), and it is
 * correct under ANY downstream mux priority, whereas (b) is only correct if
 * the datapath happens to rank the muxes the same way.
 *
 * ASSUMPTION 3 -- x0 gating is on the PRODUCER's rd only.
 * RV32I hardwires x0 to zero, so a producer with rd == 0 must never forward.
 * We do not separately test `rs != 0`: rd != 0 together with rd == rs already
 * implies rs != 0, so the extra test would be dead logic.
 *
 * ASSUMPTION 4 -- the EX2 tier is suppressed when ex_mem holds a LOAD.
 * `ex_mem_mem_rd` is an input but no priority case in the spec mentions a
 * load in MEM, so its only sensible use is to qualify forwarding: the value
 * sitting in the ex_mem register for a load is the computed ADDRESS, not the
 * loaded data (which only appears in mem_wb one cycle later, which is why
 * the mem_wb group has no `mem_rd` port at all). Leaving `ex_mem_mem_rd`
 * unconnected would make it an unused input, which no hand-written RTL is
 * likely to declare. NOTE: the load-use interlock below already guarantees
 * a dependent instruction can never reach EX1a while its producing load is
 * in ex_mem, so this gate is unreachable in a legal pipeline state -- it is
 * a don't-care that we resolve one way and record.
 * The same gate is applied one stage earlier in the _pre computation, where
 * the producer that WILL be in ex_mem next cycle is the ex1b2_* group.
 * The EX1b / EX1c / EX1b2 tiers are deliberately NOT gated on their mem_rd
 * bits: those bits already have a defined use (the load-use interlock), so
 * there is no "unused input" argument for gating there.
 * ------------------------------------------------------------------- */
/* IMPLEMENTATION NOTE (a measured HLS artefact, not a spec ambiguity):
 * these three pieces of logic were first written as `static` C functions.
 * Bambu 2024.10 answered "Required never inline for function fwd_tier",
 * turned it into a shared 1-resource submodule, and allocated 80 bytes of
 * internal memory to pass its arguments -- which then failed the run outright
 * with "clock constraint too tight: BRAMs for this device cannot run so fast
 * (ARRAY_1D_STD_DISTRAM_NN_SDS: 0.813 > 0.705)". `__attribute__((always_inline))`
 * did NOT change that decision. They are therefore preprocessor macros, which
 * is the only construct that reliably keeps a purely combinational block
 * combinational here. See ASSUMPTIONS.md section B. */

/* One producer/consumer address comparison. `s` must already be masked. */
#define TIER_MATCH(rd, we, s) \
   ( (we) && ((((rd) & REG_ADDR_MASK)) != 0u) && ((((rd) & REG_ADDR_MASK)) == (s)) )

/* Full 5-tier strict priority cascade for one operand -> a TIER_* code. */
#define FWD_TIER(rs, t1_rd, t1_we, t2_rd, t2_we, t3_rd, t3_we, \
                 t4_rd, t4_we, t4_ld, t5_rd, t5_we)                            \
   ( TIER_MATCH(t1_rd, t1_we, ((rs) & REG_ADDR_MASK)) ? TIER_EX1B  :           \
     TIER_MATCH(t2_rd, t2_we, ((rs) & REG_ADDR_MASK)) ? TIER_EX1C  :           \
     TIER_MATCH(t3_rd, t3_we, ((rs) & REG_ADDR_MASK)) ? TIER_EX1B2 :           \
    (TIER_MATCH(t4_rd, t4_we, ((rs) & REG_ADDR_MASK)) && !(t4_ld))             \
                                                      ? TIER_EX2   :           \
     TIER_MATCH(t5_rd, t5_we, ((rs) & REG_ADDR_MASK)) ? TIER_WB    :           \
                                                        TIER_NONE )

/* TIER_* code -> the 2-bit fwd_*_sel port value. TIER_EX1C / TIER_EX1B2 are
 * signalled on their own single-bit ports, and the 2-bit select is parked at
 * "regfile" so that no second mux leg can also claim the operand
 * (ASSUMPTION 2). TIER_NONE -> regfile as well. */
#define TIER_TO_SEL(t)                                    \
   ( ((t) == TIER_EX1B) ? FWD_SEL_EX1B :                  \
     ((t) == TIER_EX2)  ? FWD_SEL_EX2  :                  \
     ((t) == TIER_WB)   ? FWD_SEL_WB   : FWD_SEL_REGFILE )

/* One load-use predicate: a load producer at one stage versus BOTH source
 * registers of the instruction in ID.
 *
 * ASSUMPTION 5 -- the consumer of the load-use check is the instruction in
 * ID, so the addresses used are if_id_rs1_addr / if_id_rs2_addr.
 * The spec pins the consumer for cases 5..8 by its OUTPUTS, not by naming a
 * stage: "stall IF,ID; flush ID->EX1a" holds the instruction in ID and drops
 * a bubble into EX1a, which only makes sense if the waiting instruction is
 * the one in ID. (Had the consumer been in EX1a, the vector would have been
 * "stall IF,ID,EX1a; flush EX1a->EX1c".) It is also the only other use those
 * two input ports could have, besides the _pre outputs.
 * rs2 is included unconditionally, which also covers the store-data operand
 * of an SW/SH/SB. A load with rd == 0 writes nothing and must not stall. */
#define LOAD_USE(rs1, rs2, ld_rd, ld_mem_rd)                            \
   ( (ld_mem_rd) && ((((ld_rd) & REG_ADDR_MASK)) != 0u) &&              \
     ( ((((ld_rd) & REG_ADDR_MASK)) == (((rs1) & REG_ADDR_MASK))) ||    \
       ((((ld_rd) & REG_ADDR_MASK)) == (((rs2) & REG_ADDR_MASK))) ) )

void rv32i_hazard_unit(
   /* ---- inputs, in the order the port documentation lists them ------- */
   /* From ID/EX register (instruction currently in EX1a). */
   unsigned id_ex_rs1_addr, unsigned id_ex_rs2_addr, unsigned id_ex_rd_addr,
   unsigned id_ex_mem_rd, unsigned id_ex_reg_wr_en,
   /* From EX1b register (ex1a_ex1b_reg -- instruction in EX1c). */
   unsigned ex1b_rd_addr, unsigned ex1b_reg_wr_en, unsigned ex1b_mem_rd,
   /* From EX1c register (ex1c_ex1b_reg -- instruction in EX1b). */
   unsigned ex1c_rd_addr, unsigned ex1c_reg_wr_en, unsigned ex1c_mem_rd,
   /* From EX1b2 register (ex1b_ex2_reg_q -- instruction in EX2). */
   unsigned ex1b2_rd_addr, unsigned ex1b2_reg_wr_en, unsigned ex1b2_mem_rd,
   /* From EX/MEM register (instruction completing EX2 / entering MEM). */
   unsigned ex_mem_rd_addr, unsigned ex_mem_reg_wr_en, unsigned ex_mem_mem_rd,
   /* From MEM/WB register (instruction currently in WB). */
   unsigned mem_wb_rd_addr, unsigned mem_wb_reg_wr_en,
   /* From IF/ID register (instruction currently in ID). */
   unsigned if_id_rs1_addr, unsigned if_id_rs2_addr,
   /* Cache stall indicators. */
   unsigned if_cache_stall, unsigned mem_cache_stall,
   /* Redirects / early flush. */
   unsigned ex_pc_redirect, unsigned mem_trap_redirect, unsigned id_jal_taken,

   /* ---- outputs, in the order the port documentation lists them ------ */
   unsigned *stall_pc, unsigned *stall_if_id, unsigned *stall_id_ex,
   unsigned *stall_ex_mem,
   unsigned *stall_ex1_ex2_o, unsigned *stall_ex1a_ex1b_o,
   unsigned *stall_ex1c_ex1b_o,
   unsigned *flush_if_id, unsigned *flush_id_ex, unsigned *flush_ex_mem,
   unsigned *flush_ex1_ex2_o, unsigned *flush_ex1a_ex1b_o,
   unsigned *flush_ex1c_ex1b_o,
   unsigned *fwd_a_sel, unsigned *fwd_b_sel, unsigned *fwd_store_sel,
   unsigned *fwd_a_ex1c, unsigned *fwd_b_ex1c, unsigned *fwd_store_ex1c,
   unsigned *fwd_a_ex1b2, unsigned *fwd_b_ex1b2, unsigned *fwd_store_ex1b2,
   unsigned *fwd_a_sel_pre, unsigned *fwd_a_ex1c_pre, unsigned *fwd_a_ex1b2_pre,
   unsigned *fwd_b_sel_pre, unsigned *fwd_b_ex1c_pre, unsigned *fwd_b_ex1b2_pre)
{
   unsigned tier_a, tier_b, tier_s;
   unsigned tier_a_pre, tier_b_pre;
   unsigned lu_ex1, lu_ex1c, lu_ex1b, lu_ex2, lu_any;

   unsigned s_pc, s_if_id, s_id_ex, s_ex_mem;
   unsigned s_ex1_ex2, s_ex1a_ex1b, s_ex1c_ex1b;
   unsigned f_if_id, f_id_ex, f_ex_mem;
   unsigned f_ex1_ex2, f_ex1a_ex1b, f_ex1c_ex1b;

   /* ==================================================================
    * 1. FORWARDING for the instruction in EX1a (consumer = id_ex_rs*).
    * ================================================================== */
   tier_a = FWD_TIER(id_ex_rs1_addr,
                     ex1b_rd_addr,   ex1b_reg_wr_en,
                     ex1c_rd_addr,   ex1c_reg_wr_en,
                     ex1b2_rd_addr,  ex1b2_reg_wr_en,
                     ex_mem_rd_addr, ex_mem_reg_wr_en, ex_mem_mem_rd,
                     mem_wb_rd_addr, mem_wb_reg_wr_en);

   tier_b = FWD_TIER(id_ex_rs2_addr,
                     ex1b_rd_addr,   ex1b_reg_wr_en,
                     ex1c_rd_addr,   ex1c_reg_wr_en,
                     ex1b2_rd_addr,  ex1b2_reg_wr_en,
                     ex_mem_rd_addr, ex_mem_reg_wr_en, ex_mem_mem_rd,
                     mem_wb_rd_addr, mem_wb_reg_wr_en);

   /* ASSUMPTION 6 -- fwd_store_* is the rs2 decision on a SEPARATE mux.
    * In RV32I the store data operand is always rs2, and this block is only
    * ever told about the instruction in EX1a, so the store-forward decision
    * is computed from id_ex_rs2_addr with the identical tier priority. The
    * ports are duplicated (rather than the caller reusing fwd_b_*) because
    * the B-operand mux feeds the ALU -- where a store selects the immediate,
    * not rs2 -- while the store-data mux needs the forwarded rs2 value. The
    * three fwd_store_* outputs are therefore bit-identical to fwd_b_* by
    * construction; if the reference instead evaluates store forwarding at a
    * later stage or against a different address, this will not match. */
   tier_s = FWD_TIER(id_ex_rs2_addr,
                     ex1b_rd_addr,   ex1b_reg_wr_en,
                     ex1c_rd_addr,   ex1c_reg_wr_en,
                     ex1b2_rd_addr,  ex1b2_reg_wr_en,
                     ex_mem_rd_addr, ex_mem_reg_wr_en, ex_mem_mem_rd,
                     mem_wb_rd_addr, mem_wb_reg_wr_en);

   *fwd_a_sel      = TIER_TO_SEL(tier_a);
   *fwd_b_sel      = TIER_TO_SEL(tier_b);
   *fwd_store_sel  = TIER_TO_SEL(tier_s);

   *fwd_a_ex1c     = (tier_a == TIER_EX1C)  ? 1u : 0u;
   *fwd_b_ex1c     = (tier_b == TIER_EX1C)  ? 1u : 0u;
   *fwd_store_ex1c = (tier_s == TIER_EX1C)  ? 1u : 0u;

   *fwd_a_ex1b2     = (tier_a == TIER_EX1B2) ? 1u : 0u;
   *fwd_b_ex1b2     = (tier_b == TIER_EX1B2) ? 1u : 0u;
   *fwd_store_ex1b2 = (tier_s == TIER_EX1B2) ? 1u : 0u;

   /* ==================================================================
    * 2. PRE-DECODED forwarding for the instruction still in ID.
    *
    * ASSUMPTION 7 -- the exact producer/consumer pairing of the _pre ports.
    * The spec says only "computed using if_id_rs*_addr (the consumer in ID)
    * against producer addresses shifted one stage earlier". The consumer in
    * ID this cycle is the consumer in EX1a NEXT cycle, and every producer
    * also advances one stage, so each forwarding tier is re-sourced from the
    * group one stage YOUNGER than the group that feeds the live decision:
    *
    *   tier                live source     _pre source      why
    *   ------------------  --------------  ---------------  -------------------
    *   2'b11 EX1b          ex1b_*  (EX1c)  id_ex_*  (EX1a)  EX1a -> EX1c
    *   fwd_*_ex1c          ex1c_*  (EX1b)  ex1b_*   (EX1c)  EX1c -> EX1b
    *   fwd_*_ex1b2         ex1b2_* (EX2)   ex1c_*   (EX1b)  EX1b -> EX2
    *   2'b01 EX2           ex_mem_* (MEM)  ex1b2_*  (EX2)   EX2  -> MEM
    *   2'b10 WB            mem_wb_* (WB)   ex_mem_* (MEM)   MEM  -> WB
    *   2'b00 regfile       --              mem_wb_*         WB retires; the
    *                                                        value is in the
    *                                                        regfile next cycle
    *
    * mem_wb_* therefore has NO _pre role: the instruction in WB this cycle
    * has committed by the time the ID instruction reaches EX1a, so a plain
    * register read returns its result. This assumes the register file is
    * write-first / internally bypassed within a cycle, which is the standard
    * arrangement and the only one under which a 5-tier forwarding network is
    * sufficient at all.
    *
    * The _pre outputs are computed unconditionally, i.e. they are NOT
    * squashed by a stall or a flush. The spec says they are "registered by
    * the caller"; suppressing them here would double up on the enable/clear
    * the caller already applies to the ID/EX boundary, and would corrupt the
    * value if the caller does NOT apply one. Leaving them raw is the choice
    * that composes correctly in both cases.
    * ================================================================== */
   tier_a_pre = FWD_TIER(if_id_rs1_addr,
                         id_ex_rd_addr,  id_ex_reg_wr_en,
                         ex1b_rd_addr,   ex1b_reg_wr_en,
                         ex1c_rd_addr,   ex1c_reg_wr_en,
                         ex1b2_rd_addr,  ex1b2_reg_wr_en, ex1b2_mem_rd,
                         ex_mem_rd_addr, ex_mem_reg_wr_en);

   tier_b_pre = FWD_TIER(if_id_rs2_addr,
                         id_ex_rd_addr,  id_ex_reg_wr_en,
                         ex1b_rd_addr,   ex1b_reg_wr_en,
                         ex1c_rd_addr,   ex1c_reg_wr_en,
                         ex1b2_rd_addr,  ex1b2_reg_wr_en, ex1b2_mem_rd,
                         ex_mem_rd_addr, ex_mem_reg_wr_en);

   *fwd_a_sel_pre   = TIER_TO_SEL(tier_a_pre);
   *fwd_a_ex1c_pre  = (tier_a_pre == TIER_EX1C)  ? 1u : 0u;
   *fwd_a_ex1b2_pre = (tier_a_pre == TIER_EX1B2) ? 1u : 0u;

   *fwd_b_sel_pre   = TIER_TO_SEL(tier_b_pre);
   *fwd_b_ex1c_pre  = (tier_b_pre == TIER_EX1C)  ? 1u : 0u;
   *fwd_b_ex1b2_pre = (tier_b_pre == TIER_EX1B2) ? 1u : 0u;

   /* There is no fwd_store_*_pre in the interface. The spec lists only the A
    * and B pre-decoded groups, so the store-data mux select is assumed to be
    * generated live in EX1a only (see ASSUMPTION 6). Nothing is emitted. */

   /* ==================================================================
    * 3. LOAD-USE INTERLOCK -- four predicates, one per producer stage that
    *    a load can occupy while a dependent instruction waits in ID.
    *
    * A load's result first becomes forwardable from the WB tier (mem_wb),
    * five stages behind EX1a, so a consumer in ID must be held until its
    * producing load has advanced past the ex_mem register:
    *
    *   cycle 0  load in EX1a  (id_ex_*)   -> load_use_ex1   stall #1
    *   cycle 1  load in EX1c  (ex1b_*)    -> load_use_ex1c  stall #2
    *   cycle 2  load in EX1b  (ex1c_*)    -> load_use_ex1b  stall #3
    *   cycle 3  load in EX2   (ex1b2_*)   -> load_use_ex2   stall #4
    *   cycle 4  load in MEM   (ex_mem_*)  -> no stall; consumer enters EX1a
    *   cycle 5  consumer in EX1a, load in WB -> forward 2'b10
    *
    * ASSUMPTION 8 -- the four spec case names bind to those four groups.
    * The comments read "load in EX1a / EX1c / EX1b / EX1b2". The first three
    * are unambiguous. "EX1b2" is the register ex1b_ex2_reg_q, whose port
    * group is ex1b2_* -- so load_use_ex2 uses ex1b2_mem_rd, NOT
    * ex_mem_mem_rd. That reading is the only one that yields four
    * CONSECUTIVE producer stages with no gap, and it is exactly the number
    * of stall cycles needed for the load to reach WB, which is a strong
    * self-consistency check.
    *
    * ASSUMPTION 9 -- the interlock is gated on mem_rd and rd != 0 only; it
    * does NOT additionally require reg_wr_en. Every real load asserts both,
    * and a bubble asserts neither, so the extra term is only observable on
    * an input vector the pipeline cannot produce.
    * ================================================================== */
   lu_ex1  = LOAD_USE(if_id_rs1_addr, if_id_rs2_addr,
                      id_ex_rd_addr,  id_ex_mem_rd);
   lu_ex1c = LOAD_USE(if_id_rs1_addr, if_id_rs2_addr,
                      ex1b_rd_addr,   ex1b_mem_rd);
   lu_ex1b = LOAD_USE(if_id_rs1_addr, if_id_rs2_addr,
                      ex1c_rd_addr,   ex1c_mem_rd);
   lu_ex2  = LOAD_USE(if_id_rs1_addr, if_id_rs2_addr,
                      ex1b2_rd_addr,  ex1b2_mem_rd);

   /* ASSUMPTION 10 -- the four load-use cases are listed at four distinct
    * priority levels (5..8) but produce IDENTICAL output vectors, and none
    * of them can be distinguished at the interface. They are therefore
    * merged into one term. Keeping them separate would generate the same
    * logic; the spec's four levels only matter relative to cases 1-4 and 9,
    * which is preserved exactly by the cascade below. */
   lu_any = (lu_ex1 || lu_ex1c || lu_ex1b || lu_ex2) ? 1u : 0u;

   /* ==================================================================
    * 4. STALL / FLUSH PRIORITY CASCADE.
    *
    * ASSUMPTION 11 -- "Priority (highest -> lowest)" means a strict
    * if / else-if chain, i.e. the cases are MUTUALLY EXCLUSIVE, not a set of
    * independently-OR'd contributions. Under the OR reading, a trap
    * coinciding with mem_cache_stall would flush AND freeze simultaneously,
    * which is self-contradictory (a frozen register cannot accept a bubble);
    * and if_cache_stall would keep asserting stall_pc underneath a trap
    * redirect, defeating the redirect. The chain also makes the two
    * deliberate orderings meaningful: mem_trap_redirect OUTRANKS
    * mem_cache_stall (a trap must escape a stalled D-cache), while
    * ex_pc_redirect is OUTRANKED by it (a branch redirect waits for the
    * cache).
    * ================================================================== */
   s_pc = 0u; s_if_id = 0u; s_id_ex = 0u; s_ex_mem = 0u;
   s_ex1_ex2 = 0u; s_ex1a_ex1b = 0u; s_ex1c_ex1b = 0u;
   f_if_id = 0u; f_id_ex = 0u; f_ex_mem = 0u;
   f_ex1_ex2 = 0u; f_ex1a_ex1b = 0u; f_ex1c_ex1b = 0u;

   if (mem_trap_redirect)
   {
      /* Case 1: flush EX2, EX1b2, EX1b, EX1c, EX1a, ID, IF.
       * ASSUMPTION 12 -- "EX1b2" and "EX2" in that list name the same
       * physical slot (the port doc calls ex1b_ex2_reg_q "the EX1b2
       * register" and says its output is "the instruction in EX2"), so the
       * seven listed stage names collapse onto the six available flush
       * outputs -- all of which are asserted. The PC is not stalled: the
       * redirect must be allowed to load the trap vector. There is no
       * flush_pc port, so "flush IF" is realised by flush_if_id, which
       * bubbles the instruction leaving IF. */
      f_if_id = 1u; f_id_ex = 1u;
      f_ex1a_ex1b = 1u; f_ex1c_ex1b = 1u; f_ex1_ex2 = 1u; f_ex_mem = 1u;
   }
   else if (mem_cache_stall)
   {
      /* Case 2: global freeze. Every pipeline register holds, including the
       * PC; nothing is flushed, so no instruction is lost. */
      s_pc = 1u; s_if_id = 1u; s_id_ex = 1u;
      s_ex1a_ex1b = 1u; s_ex1c_ex1b = 1u; s_ex1_ex2 = 1u; s_ex_mem = 1u;
   }
   else if (ex_pc_redirect)
   {
      /* Case 3: identical output vector to case 1 -- the spec gives the two
       * the same flush list, and from this block's interface they are
       * distinguishable only by priority (and by the redirect target, which
       * is chosen outside this block). ASSUMPTION 13: taken literally, this
       * also flushes EX2, i.e. the stage the redirecting instruction has
       * itself advanced into ("registered from EX1b stage"). We implement
       * the spec as written rather than second-guessing it; if the reference
       * spares EX2 so that a JAL/JALR can still write rd, flush_ex_mem is
       * the single bit that will differ. */
      f_if_id = 1u; f_id_ex = 1u;
      f_ex1a_ex1b = 1u; f_ex1c_ex1b = 1u; f_ex1_ex2 = 1u; f_ex_mem = 1u;
   }
   else if (id_jal_taken)
   {
      /* Case 4: flush IF only -- the JAL is in ID and survives; only the
       * sequentially-fetched instruction behind it is killed. */
      f_if_id = 1u;
   }
   else if (lu_any)
   {
      /* Cases 5-8: stall IF and ID, bubble into EX1a. The consumer is held
       * in ID (stall_if_id) and the PC is held with it (stall_pc), while
       * EX1a and everything downstream keep advancing so the offending load
       * can drain toward WB. */
      s_pc = 1u; s_if_id = 1u;
      f_id_ex = 1u;
   }
   else if (if_cache_stall)
   {
      /* Case 9: stall PC only.
       * ASSUMPTION 14 -- taken literally: stall_if_id is NOT asserted and no
       * bubble is injected. That is only safe if the fetch stage presents an
       * explicitly invalid/NOP instruction while the I-cache is missing,
       * which is outside this block's interface (there is no if_valid input
       * to tell us otherwise). The alternative -- also asserting
       * flush_if_id, which is what many designs do -- would silently discard
       * a validly fetched instruction if the fetch unit does hold its own
       * output, so the literal reading is the safer of the two here. */
      s_pc = 1u;
   }

   *stall_pc          = s_pc;
   *stall_if_id       = s_if_id;
   *stall_id_ex       = s_id_ex;
   *stall_ex_mem      = s_ex_mem;
   *stall_ex1_ex2_o   = s_ex1_ex2;
   *stall_ex1a_ex1b_o = s_ex1a_ex1b;
   *stall_ex1c_ex1b_o = s_ex1c_ex1b;

   *flush_if_id       = f_if_id;
   *flush_id_ex       = f_id_ex;
   *flush_ex_mem      = f_ex_mem;
   *flush_ex1_ex2_o   = f_ex1_ex2;
   *flush_ex1a_ex1b_o = f_ex1a_ex1b;
   *flush_ex1c_ex1b_o = f_ex1c_ex1b;
}
