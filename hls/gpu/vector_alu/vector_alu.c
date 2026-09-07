/* =====================================================================
 * vector_alu.c -- GPU-Lite 8-lane vector ALU, C source for Bambu HLS
 *                 (PandA 2024.10), GH #119 "NL -> C -> RTL" pilot.
 *
 * WHAT THIS IMPLEMENTS
 * --------------------
 * The datapath of one warp-wide vector instruction, per the spec:
 *
 *   "8-lane vector ALU. All operations are single-cycle combinational.
 *    Inactive lanes (active_mask bit = 0) produce 0 on result_o and
 *    branch_taken_o.
 *    VMUL produces the lower 32 bits of the 64-bit product (no pipeline
 *    stage in Phase 4)."
 *
 * Eight identical lanes, each a pure function of (opcode, rs1[i], rs2[i],
 * imm). The lanes are MANUALLY UNROLLED below -- written out eight times
 * rather than as a `for` loop -- because the spec calls for eight parallel
 * lanes, and a loop would invite the HLS scheduler to fold them onto one
 * shared ALU across eight control steps, which is a different machine.
 * (See the IMPLEMENTATION NOTE on macros vs. functions further down.)
 *
 * OPCODE MAP (given verbatim by the spec, 7-bit)
 * ---------------------------------------------
 *   R-type   VADD 0x01 VSUB 0x02 VMUL 0x03 VAND 0x04 VOR  0x05
 *            VXOR 0x06 VSLL 0x07 VSRL 0x08 VSRA 0x09
 *   I-type   VADDI 0x11 VANDI 0x12 VORI 0x13 VXORI 0x14
 *   Memory   VLD 0x20 VST 0x21 VLDS 0x22 VSTS 0x23
 *   Branch   VBEQ 0x30 VBNE 0x31 VBLT 0x32 VBGE 0x33
 *   Control  VJMP 0x38 VRET 0x3F
 *   SpecReg  VMOV_TID_X 0x40 _Y 0x41 _Z 0x42
 *            VMOV_BID_X 0x46 _Y 0x47 _Z 0x48
 *   Barrier  VSYNC 0x50
 *
 * HARDWARE INTERFACE MAPPING
 * --------------------------
 * There is no clock, no reset and no state here: the block is a pure
 * function of its inputs, exactly as the spec's "single-cycle
 * combinational" demands. Bambu wraps it in its own start/done handshake
 * (the integrating shim ties start high and ignores done, as for the other
 * combinational block in this pilot). Every input is a scalar `unsigned`
 * by value and every output a pointer-out parameter tagged `mode = none`,
 * so each becomes a plain wire rather than a BRAM-style port group.
 *
 *   opcode_i      -> opcode           (7-bit value in a 32-bit word)
 *   funct3_i      -> funct3           (RESERVED -- see ASSUMPTION 10)
 *   funct7_i      -> funct7           (RESERVED -- see ASSUMPTION 10)
 *   rs1_i[7:0]    -> rs1_0 .. rs1_7
 *   rs2_i[7:0]    -> rs2_0 .. rs2_7
 *   imm_i         -> imm              (see ASSUMPTION 1)
 *   active_mask_i -> active_mask      (bit i = lane i active)
 *   result_o[i]   -> *result_i
 *   branch_taken_o[i] -> *branch_taken_i
 *
 * Constraints honoured: plain C99, no dynamic allocation, no libc calls,
 * no floating point, no recursion, no memory interface of any kind.
 *
 * ASSUMPTIONS: every place the spec was silent is marked with an
 * `ASSUMPTION n:` comment below and expanded in ASSUMPTIONS.md.
 * ===================================================================== */

#pragma HLS interface port = result_0 mode = none
#pragma HLS interface port = result_1 mode = none
#pragma HLS interface port = result_2 mode = none
#pragma HLS interface port = result_3 mode = none
#pragma HLS interface port = result_4 mode = none
#pragma HLS interface port = result_5 mode = none
#pragma HLS interface port = result_6 mode = none
#pragma HLS interface port = result_7 mode = none
#pragma HLS interface port = branch_taken_0 mode = none
#pragma HLS interface port = branch_taken_1 mode = none
#pragma HLS interface port = branch_taken_2 mode = none
#pragma HLS interface port = branch_taken_3 mode = none
#pragma HLS interface port = branch_taken_4 mode = none
#pragma HLS interface port = branch_taken_5 mode = none
#pragma HLS interface port = branch_taken_6 mode = none
#pragma HLS interface port = branch_taken_7 mode = none

/* ---- opcode encoding, verbatim from the spec ------------------------ */
#define OP_VADD  0x01u
#define OP_VSUB  0x02u
#define OP_VMUL  0x03u
#define OP_VAND  0x04u
#define OP_VOR   0x05u
#define OP_VXOR  0x06u
#define OP_VSLL  0x07u
#define OP_VSRL  0x08u
#define OP_VSRA  0x09u

#define OP_VADDI 0x11u
#define OP_VANDI 0x12u
#define OP_VORI  0x13u
#define OP_VXORI 0x14u

#define OP_VLD   0x20u
#define OP_VST   0x21u
#define OP_VLDS  0x22u
#define OP_VSTS  0x23u

#define OP_VBEQ  0x30u
#define OP_VBNE  0x31u
#define OP_VBLT  0x32u
#define OP_VBGE  0x33u

#define OP_VJMP  0x38u
#define OP_VRET  0x3Fu

#define OP_VMOV_TID_X 0x40u
#define OP_VMOV_TID_Y 0x41u
#define OP_VMOV_TID_Z 0x42u
#define OP_VMOV_BID_X 0x46u
#define OP_VMOV_BID_Y 0x47u
#define OP_VMOV_BID_Z 0x48u

#define OP_VSYNC 0x50u

/* ASSUMPTION 2 -- the opcode port is 7 bits wide (`gpu_opcode_t` is stated
 * to be 7-bit), but arrives here inside a 32-bit word. Bits [31:7] are
 * MASKED OFF and ignored rather than treated as an error: there is no fault
 * channel on this interface on which an "illegal opcode" could be reported,
 * and a shim that leaves junk in the upper bits must still behave. This
 * mirrors the same choice made for register addresses in
 * hls/cpu/rv32i_hazard_unit/rv32i_hazard_unit.c. */
#define OPCODE_MASK 0x7Fu

/* ASSUMPTION 3 -- SHIFT AMOUNT WIDTH = 5 bits, taken from rs2[4:0].
 * The spec says only "RV32I-derived vector ISA, so the standard RV32I
 * meanings apply". RV32I's SLL/SRL/SRA use rs2[4:0] and ignore rs2[31:5];
 * a shift by 32 or more is simply not representable. We therefore mask the
 * shift amount to 5 bits. This is also the ONLY choice that is well defined
 * in C -- shifting a 32-bit value by >= 32 is undefined behaviour, so an
 * unmasked shift would make the C source itself meaningless, not merely a
 * mismatch. Note the ISA has no shift-immediate opcode (there is no VSLLI /
 * VSRLI / VSRAI in the table), so the shift amount always comes from rs2,
 * never from imm. */
#define SHAMT_MASK 0x1Fu

/* ASSUMPTION 1 -- `imm` HANDLING: sign-extended from bit 11, idempotently.
 * The spec is self-contradictory here: the port is declared `logic [11:0]`
 * (12 bits, which cannot hold a sign-extended 32-bit value) yet the comment
 * says "sign-extended by caller". Bambu's C interface gives us a 32-bit
 * word either way. We resolve it by sign-extending from bit 11 explicitly:
 *
 *   imm32 = (imm & 0x800) ? (imm | 0xFFFFF000) : (imm & 0x00000FFF)
 *
 * This is deliberately IDEMPOTENT and therefore agrees with BOTH readings
 * of the spec for every legal input:
 *   - if the caller drove a raw 12-bit field (upper bits zero), we perform
 *     the sign extension the value needs;
 *   - if the caller already sign-extended to 32 bits, then bits [31:11] are
 *     all copies of bit 11 by definition, so the expression reproduces the
 *     input unchanged.
 * The two readings only diverge for an input that is neither -- i.e. junk
 * in bits [31:12] that does not match bit 11 -- which is illegal under
 * either reading. The residual risk is that the hand-written reference
 * ZERO-extends its 12-bit port instead (SystemVerilog widens an unsigned
 * `logic [11:0]` with zeros unless it is explicitly `$signed`), in which
 * case negative immediates will differ. Recorded in ASSUMPTIONS.md. */
#define SIGN_EXTEND_12(v) \
   ( ((v) & 0x00000800u) ? ((v) | 0xFFFFF000u) : ((v) & 0x00000FFFu) )

/* ---------------------------------------------------------------------
 * IMPLEMENTATION NOTE (an HLS artefact, not a spec ambiguity):
 * the per-lane datapath is a MACRO, not a `static` C function. In the
 * previous block of this pilot (rv32i_hazard_unit) Bambu 2024.10 answered
 * "Required never inline for function ..." to a static helper, turned it
 * into a shared 1-resource submodule, and allocated internal memory to pass
 * its arguments -- which then failed the run outright on the ASAP7 clock
 * constraint. `__attribute__((always_inline))` did not change that. A macro
 * is the only construct that reliably keeps a combinational block
 * combinational here, and -- equally important for THIS block -- it is what
 * guarantees eight independent copies of the datapath rather than one
 * shared, sequentially-reused ALU.
 *
 * ONE LANE. `a` = rs1[i], `b` = rs2[i], `opc` = masked opcode,
 * `immx` = sign-extended immediate, `act` = this lane's mask bit.
 * `res` / `btk` are the lvalues written.
 * ------------------------------------------------------------------- */
#define VALU_LANE(a, b, opc, immx, act, res, btk)                             \
   do {                                                                       \
      unsigned _a  = (a);                                                     \
      unsigned _b  = (b);                                                     \
      int      _sa = (int)(a);                                                \
      int      _sb = (int)(b);                                                \
      unsigned _sh = (b) & SHAMT_MASK;                                        \
      unsigned _r  = 0u;                                                      \
      unsigned _t  = 0u;                                                      \
                                                                              \
      switch (opc)                                                            \
      {                                                                       \
         /* ---- R-type arithmetic / logic, both operands from registers.     \
          * ASSUMPTION 4: funct3/funct7 do NOT participate. The spec calls    \
          * them "reserved for future R-type sub-encoding" AND gives every    \
          * R-type operation its own distinct primary opcode, so the primary  \
          * opcode alone fully determines the operation today. */             \
         case OP_VADD:  _r = _a + _b;                       break;            \
         case OP_VSUB:  _r = _a - _b;                       break;            \
                                                                              \
         /* ASSUMPTION 5 -- VMUL: "lower 32 bits of the 64-bit product".      \
          * C's unsigned arithmetic is modulo 2^32, so `_a * _b` on two       \
          * 32-bit unsigneds IS exactly the low 32 bits of the full product.  \
          * The low half is identical for signed and unsigned multiplication, \
          * so the spec's silence on signedness is a non-issue -- and this    \
          * formulation asks the tool for a 32x32->32 multiplier rather than  \
          * a 32x32->64 one whose upper half would then be discarded. */      \
         case OP_VMUL:  _r = _a * _b;                       break;            \
                                                                              \
         case OP_VAND:  _r = _a & _b;                       break;            \
         case OP_VOR:   _r = _a | _b;                       break;            \
         case OP_VXOR:  _r = _a ^ _b;                       break;            \
                                                                              \
         /* Shifts: amount = rs2[4:0] (ASSUMPTION 3).                         \
          * VSLL/VSRL are LOGICAL -- performed on the unsigned copy, so the   \
          * vacated bits are zeros. VSRA is ARITHMETIC -- performed on the    \
          * signed copy, so the vacated bits replicate the sign. This is the  \
          * whole point of having both VSRL (0x08) and VSRA (0x09), and it is \
          * the RV32I meaning the spec tells us to import.                    \
          * ASSUMPTION 6: `>>` on a negative `int` is implementation-defined  \
          * in C99, not guaranteed arithmetic. Every compiler this project    \
          * uses (and clang-16 specifically, which is Bambu's front end here) \
          * defines it as an arithmetic shift, and Bambu lowers it to an      \
          * arithmetic right-shift operator. Written this way rather than as  \
          * a hand-built sign-fill so the tool can infer its own ASR cell. */ \
         case OP_VSLL:  _r = _a << _sh;                     break;            \
         case OP_VSRL:  _r = _a >> _sh;                     break;            \
         case OP_VSRA:  _r = (unsigned)(_sa >> _sh);        break;            \
                                                                              \
         /* ---- I-type: second operand is the immediate. Note the ISA has    \
          * no VSUBI and no shift-immediate, so this list is complete. */     \
         case OP_VADDI: _r = _a + (immx);                   break;            \
         case OP_VANDI: _r = _a & (immx);                   break;            \
         case OP_VORI:  _r = _a | (immx);                   break;            \
         case OP_VXORI: _r = _a ^ (immx);                   break;            \
                                                                              \
         /* ---- Memory: ASSUMPTION 7 -- result_o carries the per-lane        \
          * EFFECTIVE ADDRESS, rs1 + sign-extended imm, for all four of       \
          * VLD/VST/VLDS/VSTS (global and shared alike).                      \
          * The spec does not say what this block does for memory opcodes.    \
          * Reasons for this choice:                                         \
          *   (a) these are declared I-type, and in RV32I the I-type          \
          *       load/store address is exactly rs1 + sign-extended imm --    \
          *       which is what "the standard RV32I meanings apply" imports;  \
          *   (b) the interface hands this block precisely the two operands   \
          *       that address computation needs, and nothing else in the     \
          *       lane datapath is given them;                                \
          *   (c) the downstream memory coalescer consumes EIGHT per-lane     \
          *       byte addresses, and the vector ALU is the only per-lane     \
          *       adder in the pipeline that can produce them. Returning 0    \
          *       here would leave the coalescer with no address source.      \
          * Store DATA is rs2 and is routed around this block; VST/VSTS       \
          * therefore still emit the address, not the data. */                \
         case OP_VLD:                                                         \
         case OP_VST:                                                         \
         case OP_VLDS:                                                        \
         case OP_VSTS:  _r = _a + (immx);                   break;            \
                                                                              \
         /* ---- Branch: B-type, per-lane compare -> branch_taken_o.          \
          * SIGNEDNESS: RV32I's BLT/BGE are SIGNED comparisons (the unsigned  \
          * forms are separate opcodes, BLTU/BGEU, which this ISA does not    \
          * define at all). So VBLT/VBGE compare the signed copies.           \
          * ASSUMPTION 8 -- result_o is 0 for branch opcodes. The branch      \
          * TARGET cannot be computed here: RV32I branch targets are          \
          * PC-relative and no PC is an input to this block, so the only      \
          * thing result_o could carry is a comparison by-product. 0 is the   \
          * one default value the spec actually states anywhere ("inactive    \
          * lanes produce 0"), so we reuse it rather than invent another. */  \
         case OP_VBEQ:  _t = (_a == _b)  ? 1u : 0u;         break;            \
         case OP_VBNE:  _t = (_a != _b)  ? 1u : 0u;         break;            \
         case OP_VBLT:  _t = (_sa <  _sb) ? 1u : 0u;        break;            \
         case OP_VBGE:  _t = (_sa >= _sb) ? 1u : 0u;        break;            \
                                                                              \
         /* ---- Control, special-register reads, barrier, and anything       \
          * unrecognised: result_o = 0, branch_taken_o = 0.                   \
          * ASSUMPTION 9 (control / barrier): VJMP and VRET are unconditional \
          * control transfers resolved by the warp scheduler / SIMT stack,    \
          * and VSYNC is a scheduler barrier; none of them writes a           \
          * destination register, and none is a per-lane comparison, so       \
          * neither output is meaningful. branch_taken_o is deliberately NOT  \
          * forced to 1 for VJMP: the spec names the port "branch decision",  \
          * which is a predicate, and VJMP needs no predicate.                \
          * ASSUMPTION 10 (special registers): VMOV_TID_* / VMOV_BID_* want   \
          * the thread and block ids -- and this block HAS NO tid/bid INPUT.  \
          * It is physically incapable of producing them, so they must be     \
          * injected upstream (operand fetch) or bypassed around the ALU      \
          * entirely. We emit 0. The plausible alternative, passing rs1       \
          * through on the theory that operand fetch pre-loaded the id into   \
          * rs1, is recorded in ASSUMPTIONS.md as the main risk here. */      \
         default:       _r = 0u; _t = 0u;                   break;            \
      }                                                                       \
                                                                              \
      /* Inactive lanes produce 0 on BOTH outputs -- stated by the spec.      \
       * Masking is applied at the output rather than by skipping the         \
       * computation: the block is combinational, so there is nothing to      \
       * skip, and a mux to 0 is what the RTL would build. */                 \
      (res) = (act) ? _r : 0u;                                                \
      (btk) = (act) ? _t : 0u;                                                \
   } while (0)

void vector_alu(unsigned opcode, unsigned funct3, unsigned funct7,
                unsigned rs1_0, unsigned rs1_1, unsigned rs1_2, unsigned rs1_3,
                unsigned rs1_4, unsigned rs1_5, unsigned rs1_6, unsigned rs1_7,
                unsigned rs2_0, unsigned rs2_1, unsigned rs2_2, unsigned rs2_3,
                unsigned rs2_4, unsigned rs2_5, unsigned rs2_6, unsigned rs2_7,
                unsigned imm, unsigned active_mask,
                unsigned *result_0, unsigned *result_1, unsigned *result_2, unsigned *result_3,
                unsigned *result_4, unsigned *result_5, unsigned *result_6, unsigned *result_7,
                unsigned *branch_taken_0, unsigned *branch_taken_1,
                unsigned *branch_taken_2, unsigned *branch_taken_3,
                unsigned *branch_taken_4, unsigned *branch_taken_5,
                unsigned *branch_taken_6, unsigned *branch_taken_7)
{
   /* ASSUMPTION 10 (cont.) -- `funct3` and `funct7` are READ BY NOTHING.
    * The spec labels both "reserved for future R-type sub-encoding" and
    * gives every currently-defined operation a unique primary opcode, so
    * there is no sub-decode to perform. They are cast to void so the intent
    * ("deliberately unused", not "forgotten") is explicit in the source.
    * CAVEAT, measured: an input a synthesis tool can prove is unused may be
    * optimised away, in which case the generated module would be MISSING
    * these two ports relative to the reference interface. See ASSUMPTIONS.md
    * for what Bambu actually did. */
   (void)funct3;
   (void)funct7;

   /* ASSUMPTION 2 in force: ignore bits [31:7] of the opcode word. */
   const unsigned opc = opcode & OPCODE_MASK;

   /* ASSUMPTION 1 in force: idempotent sign-extension from bit 11. */
   const unsigned immx = SIGN_EXTEND_12(imm);

   /* ASSUMPTION 11 -- `active_mask` bit i selects lane i, bits [31:8] are
    * ignored. The spec says "carries the 8 lane flags in bits 0..7" and is
    * silent on the rest of the word; ignoring them is the only reading that
    * keeps an 8-lane block 8 lanes wide. */
   unsigned r0, r1, r2, r3, r4, r5, r6, r7;
   unsigned t0, t1, t2, t3, t4, t5, t6, t7;

   /* Eight lanes, written out rather than looped -- see the header note.
    * Each expansion is an independent copy of the lane datapath, including
    * its own 32x32->32 multiplier for VMUL, matching the spec's "all
    * operations are single-cycle combinational" across all 8 lanes.
    * Whether the HLS scheduler then SHARES those eight multipliers is a
    * tool decision this C cannot express; it is reported in ASSUMPTIONS.md
    * as a measured result, not asserted here. */
   VALU_LANE(rs1_0, rs2_0, opc, immx, (active_mask >> 0) & 1u, r0, t0);
   VALU_LANE(rs1_1, rs2_1, opc, immx, (active_mask >> 1) & 1u, r1, t1);
   VALU_LANE(rs1_2, rs2_2, opc, immx, (active_mask >> 2) & 1u, r2, t2);
   VALU_LANE(rs1_3, rs2_3, opc, immx, (active_mask >> 3) & 1u, r3, t3);
   VALU_LANE(rs1_4, rs2_4, opc, immx, (active_mask >> 4) & 1u, r4, t4);
   VALU_LANE(rs1_5, rs2_5, opc, immx, (active_mask >> 5) & 1u, r5, t5);
   VALU_LANE(rs1_6, rs2_6, opc, immx, (active_mask >> 6) & 1u, r6, t6);
   VALU_LANE(rs1_7, rs2_7, opc, immx, (active_mask >> 7) & 1u, r7, t7);

   *result_0 = r0; *result_1 = r1; *result_2 = r2; *result_3 = r3;
   *result_4 = r4; *result_5 = r5; *result_6 = r6; *result_7 = r7;

   /* ASSUMPTION 12 -- branch_taken_o is a 1-bit-valued port carried in a
    * 32-bit word here (Bambu's C interface has no sub-word scalar type that
    * survives as a plain wire). Only value 0 or 1 is ever written, so the
    * integrating shim can take bit 0 -- or the whole word, they agree. */
   *branch_taken_0 = t0; *branch_taken_1 = t1;
   *branch_taken_2 = t2; *branch_taken_3 = t3;
   *branch_taken_4 = t4; *branch_taken_5 = t5;
   *branch_taken_6 = t6; *branch_taken_7 = t7;
}
