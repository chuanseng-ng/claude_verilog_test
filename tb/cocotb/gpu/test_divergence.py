"""
Unit tests for gpu_compute_unit.sv — divergence stack and pipeline control.

The DUT is the full 4-stage pipeline (FETCH→DECODE→EX→WB).
Instructions are injected via the AXI4-Lite instruction-fetch interface.
The divergence stack state (div_stack_depth_i / div_stack_top_i) is
managed manually by each test, simulating what warp_scheduler.sv would do.

Pipeline timing (relative to issue):
  posedge A : issue (warp_issue_i=1, arready_i=1)
  posedge B : rvalid=1  →  if_id_q.instr captures rdata; instr_rdy_q latches
  posedge C : instr_rdy_q=1  →  id_ex_q advances (decode + regfile read)
  posedge D : ex_wb_q advances  (EX result computed)
  posedge D + 1 ns : WB outputs stable (combinational from ex_wb_q)

Note: posedge B used to simultaneously advance id_ex_q (same-cycle bypass).
The bypass was removed to eliminate the AXI rdata→decode combinational timing
path (critical-path limiter in ASAP7 PD). instr_avail now = instr_rdy_q only.

div_entry_t packing  (40 bits, MSB-first packed struct):
  bits[39:8] = return_pc[31:0]
  bits[ 7:0] = return_mask[7:0]

Tests:
  1. All-lanes-agree branch (converging, all-not-taken)  — no div_push
  2. All-lanes-agree branch (converging, all-taken)      — no div_push, next_pc = target
  3. Divergent VBLT after VMOV_TID_X setup              — div_push, mask split
  4. Stack overflow (5 nested divergent pushes)          — gpu_error_o asserted
  5. VRET on empty stack                                 — warp_done_o asserted
  6. VRET on non-empty stack                             — div_pop_o asserted
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

N_LANES         = 8
DIV_STACK_DEPTH = 4   # must match gpu_pkg::DIV_STACK_DEPTH

# GPU opcode constants (bits[6:0] of the 32-bit instruction word)
OP_VMOV_TID_X = 0x40
OP_VBEQ       = 0x30
OP_VBLT       = 0x32
OP_VRET       = 0x3F


# ---------------------------------------------------------------------------
# Instruction encoding helpers
# ---------------------------------------------------------------------------
def _enc_r(opcode, rd=0, rs1=0, rs2=0):
    """R-type: opcode + rd + rs1 + rs2 (no immediate)."""
    return ((opcode & 0x7F)      |
            ((rd  & 0x1F) <<  7) |
            ((rs1 & 0x1F) << 15) |
            ((rs2 & 0x1F) << 20))


def _enc_i(opcode, rd=0, rs1=0, imm12=0):
    """I-type: opcode + rd + rs1 + 12-bit immediate in bits[31:20]."""
    return ((opcode  & 0x7F)       |
            ((rd     & 0x1F) <<  7)|
            ((rs1    & 0x1F) << 15)|
            ((imm12  & 0xFFF) << 20))


# ---------------------------------------------------------------------------
# div_entry_t pack/unpack  (struct packed { logic[31:0] return_pc; logic[7:0] return_mask; })
# ---------------------------------------------------------------------------
def _pack_div_entry(return_pc, return_mask):
    return ((return_pc & 0xFFFF_FFFF) << N_LANES) | (return_mask & 0xFF)


def _unpack_div_entry(val):
    val = int(val)
    return (val >> N_LANES) & 0xFFFF_FFFF, val & 0xFF


# ---------------------------------------------------------------------------
# Reset and per-instruction drive helpers
# ---------------------------------------------------------------------------
async def _reset(dut, cycles=4):
    dut.rst_n.value              = 0
    dut.warp_issue_i.value       = 0
    dut.warp_id_i.value          = 0
    dut.warp_pc_i.value          = 0
    dut.warp_mask_i.value        = 0
    dut.if_arready_i.value       = 1
    dut.if_rdata_i.value         = 0
    dut.if_rvalid_i.value        = 0
    dut.mem_stall_i.value        = 0
    dut.mem_rdata_i.value        = 0
    dut.mem_rvalid_i.value       = 0
    dut.shmem_stall_i.value      = 0
    dut.shmem_rdata_i.value      = 0
    dut.shmem_rvalid_i.value     = 0
    dut.div_stack_depth_i.value  = 0
    dut.div_stack_top_i.value    = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _run_instr(dut, warp_id, pc, mask, instr_word,
                     div_depth=0, div_top_pc=0, div_top_mask=0):
    """
    Drive one instruction through the full pipeline.

    Sets div_stack_depth_i / div_stack_top_i before issue to mimic the
    warp_scheduler state for the given warp. Waits for pipe_stall_o=0
    before issuing. Returns a dict of all WB-stage outputs sampled one
    settle interval after the EX→WB register advances.
    """
    # Present the scheduler's divergence stack state for this warp
    dut.div_stack_depth_i.value = div_depth
    dut.div_stack_top_i.value   = _pack_div_entry(div_top_pc, div_top_mask)

    # Wait until pipeline is ready for a new warp
    for _ in range(20):
        if not int(dut.pipe_stall_o.value):
            break
        await RisingEdge(dut.clk)
    else:
        raise RuntimeError("pipe_stall_o stuck high — pipeline deadlock?")

    # posedge A: issue warp + accept AXI AR in same cycle
    dut.warp_issue_i.value = 1
    dut.warp_id_i.value    = warp_id
    dut.warp_pc_i.value    = pc
    dut.warp_mask_i.value  = mask
    dut.if_arready_i.value = 1
    await RisingEdge(dut.clk)      # if_id_q: valid=1, warp info captured
    dut.warp_issue_i.value = 0

    # posedge B: rvalid=1 → if_id_q.instr captures rdata, instr_rdy_q latches
    dut.if_rdata_i.value  = instr_word
    dut.if_rvalid_i.value = 1
    await RisingEdge(dut.clk)
    dut.if_rvalid_i.value = 0

    # posedge C: instr_rdy_q=1 → id_ex_q advances with correct decode+regfile data
    await RisingEdge(dut.clk)

    # posedge D: ex_wb_q advances with EX-stage results
    await RisingEdge(dut.clk)
    await Timer(1, "ns")           # settle combinational WB outputs from ex_wb_q

    out = {
        'warp_retire'     : int(dut.warp_retire_o.value),
        'warp_retire_id'  : int(dut.warp_retire_id_o.value),
        'warp_next_pc'    : int(dut.warp_next_pc_o.value),
        'warp_next_mask'  : int(dut.warp_next_mask_o.value),
        'warp_done'       : int(dut.warp_done_o.value),
        'div_push'        : int(dut.div_push_o.value),
        'div_push_entry'  : int(dut.div_push_entry_o.value),
        'div_pop'         : int(dut.div_pop_o.value),
        'div_pop_pc'      : int(dut.div_pop_pc_o.value),
        'div_pop_mask'    : int(dut.div_pop_mask_o.value),
        'gpu_error'       : int(dut.gpu_error_o.value),
    }
    if out['div_push']:
        rpc, rmask = _unpack_div_entry(out['div_push_entry'])
        out['div_push_return_pc']   = rpc
        out['div_push_return_mask'] = rmask
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_converging_not_taken(dut):
    """VBEQ r0, r0 with all-zero reg file: all lanes not taken → no div_push."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    # r0 == r0 → VBEQ: all lanes taken (rs1[i]==rs2[i]==0 → equal → taken)
    # All taken: mask_taken=0xFF, mask_not_taken=0x00 → converging → no div_push
    pc = 0x1000
    instr = _enc_r(OP_VBEQ, rd=0, rs1=0, rs2=0)   # VBEQ r0, r0 (always equal)
    out = await _run_instr(dut, warp_id=0, pc=pc, mask=0xFF, instr_word=instr)

    assert out['div_push']  == 0, f"Unexpected div_push on converging branch: {out}"
    assert out['gpu_error'] == 0, f"gpu_error unexpectedly set: {out}"
    assert out['warp_done'] == 0, f"warp_done unexpectedly set: {out}"
    assert out['warp_retire'] == 1, f"warp_retire should be 1 for taken converging branch: {out}"
    # All taken → next_pc = branch_target = pc + imm_sext(0) = pc
    assert out['warp_next_pc'] == pc, \
        f"next_pc should be branch target {pc:#010x}, got {out['warp_next_pc']:#010x}"


@cocotb.test()
async def test_converging_taken(dut):
    """VBEQ r0, r0 (all-taken) → next_pc = branch target, no div_push."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    # Use non-zero immediate: imm=8 → branch_target = pc + 8
    pc  = 0x2000
    imm = 8   # 12-bit positive offset
    # For a branch instruction, dec_imm = instr[31:20].
    # Branch target = pc + sign_extend(dec_imm[11:0]).
    # Use I-type encoding: imm in bits[31:20], rs1=0, rs2 field (bits[24:20]) = 0
    instr = _enc_i(OP_VBEQ, rs1=0, imm12=imm)  # rs2 implicitly 0 via _enc_i
    out = await _run_instr(dut, warp_id=0, pc=pc, mask=0xFF, instr_word=instr)

    assert out['div_push']  == 0, f"Unexpected div_push: {out}"
    assert out['warp_retire'] == 1, f"Expected warp_retire for converging branch: {out}"
    target = (pc + imm) & 0xFFFF_FFFF
    assert out['warp_next_pc'] == target, \
        f"Expected next_pc={target:#010x}, got {out['warp_next_pc']:#010x}"


@cocotb.test()
async def test_divergent_branch(dut):
    """VMOV_TID_X r1 then VBLT r0, r1 → lane 0 not taken, lanes 1-7 taken (divergent)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    # Step 1: Load per-lane thread IDs into r1 via VMOV_TID_X
    vmov = _enc_r(OP_VMOV_TID_X, rd=1)          # r1[lane] = lane_id
    r = await _run_instr(dut, warp_id=0, pc=0x1000, mask=0xFF, instr_word=vmov)
    assert r['warp_retire'] == 1, f"VMOV_TID_X should retire normally: {r}"
    assert r['div_push']    == 0, f"VMOV should not push divergence: {r}"

    # Step 2: VBLT r0, r1  →  lane 0: (0<0)=F, lanes 1-7: (0<1..7)=T  →  divergent
    # mask_taken = 0xFE (lanes 1-7), mask_not_taken = 0x01 (lane 0)
    pc   = 0x1004
    vblt = _enc_r(OP_VBLT, rd=0, rs1=0, rs2=1)
    r = await _run_instr(dut, warp_id=0, pc=pc, mask=0xFF, instr_word=vblt, div_depth=0)

    assert r['div_push']    == 1,    f"Expected div_push on divergent branch: {r}"
    assert r['gpu_error']   == 0,    f"Unexpected gpu_error: {r}"
    # warp_retire fires alongside div_push: the scheduler must update PC+mask even on divergence
    assert r['warp_retire'] == 1,    f"warp_retire should fire with div_push (scheduler needs new PC/mask): {r}"
    assert r['warp_done']   == 0,    f"Unexpected warp_done: {r}"

    # True-path mask (taken) = 0xFE; false-path mask = 0x01
    assert r['warp_next_mask'] == 0xFE, \
        f"Expected true-path mask 0xFE, got {r['warp_next_mask']:#04x}"

    # branch_target = pc + sign_extend(dec_imm).  dec_imm = instr[31:20] which overlaps
    # the rs2 field (bits[24:20]); rs2=1 → dec_imm bit 0 = 1 → imm_sext = 1.
    rs2_val = 1
    expected_target = (pc + rs2_val) & 0xFFFF_FFFF
    assert r['warp_next_pc'] == expected_target, \
        f"Expected branch target {expected_target:#010x}, got {r['warp_next_pc']:#010x}"

    # div_entry should contain (return_pc = pc+4, return_mask = false-path = 0x01)
    rpc, rmask = _unpack_div_entry(r['div_push_entry'])
    assert rpc   == pc + 4,  f"div_entry return_pc should be {pc+4:#010x}, got {rpc:#010x}"
    assert rmask == 0x01,    f"div_entry return_mask should be 0x01, got {rmask:#04x}"


@cocotb.test()
async def test_stack_overflow(dut):
    """5 nested divergent branches → gpu_error_o on the 5th push (DIV_STACK_DEPTH=4)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    # First, load r1 with per-lane TIDs so VBLT is divergent
    vmov = _enc_r(OP_VMOV_TID_X, rd=1)
    await _run_instr(dut, warp_id=0, pc=0x0000, mask=0xFF, instr_word=vmov)

    vblt = _enc_r(OP_VBLT, rd=0, rs1=0, rs2=1)   # divergent: lane 0 not taken

    # Push 4 entries — all should succeed (no error)
    for depth in range(DIV_STACK_DEPTH):
        r = await _run_instr(dut, warp_id=0, pc=0x0004*(depth+1), mask=0xFF,
                             instr_word=vblt, div_depth=depth)
        assert r['div_push']  == 1, f"Push {depth}: expected div_push, got {r}"
        assert r['gpu_error'] == 0, f"Push {depth}: unexpected gpu_error, got {r}"

    # 5th push: stack is now full (depth == DIV_STACK_DEPTH=4) → should error
    r5 = await _run_instr(dut, warp_id=0, pc=0x0018, mask=0xFF,
                          instr_word=vblt, div_depth=DIV_STACK_DEPTH)
    assert r5['gpu_error'] == 1, \
        f"Expected gpu_error on 5th divergent push, got {r5}"


@cocotb.test()
async def test_vret_empty_stack(dut):
    """VRET on empty stack → warp_done asserted, no div_pop."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    vret = _enc_r(OP_VRET)
    r = await _run_instr(dut, warp_id=0, pc=0x3000, mask=0xFF,
                         instr_word=vret, div_depth=0)

    assert r['warp_done'] == 1,  f"Expected warp_done on VRET+empty stack: {r}"
    assert r['div_pop']   == 0,  f"Unexpected div_pop on empty stack: {r}"
    assert r['div_push']  == 0,  f"Unexpected div_push: {r}"
    assert r['gpu_error'] == 0,  f"Unexpected gpu_error: {r}"


@cocotb.test()
async def test_vret_nonempty_stack(dut):
    """VRET on non-empty stack → div_pop asserted, false-path state returned."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    false_pc   = 0xABCD_0100
    false_mask = 0x01   # lane 0 (false path)

    vret = _enc_r(OP_VRET)
    r = await _run_instr(dut, warp_id=0, pc=0x4000, mask=0xFE,
                         instr_word=vret,
                         div_depth=1,
                         div_top_pc=false_pc,
                         div_top_mask=false_mask)

    assert r['div_pop']   == 1,          f"Expected div_pop on VRET+non-empty stack: {r}"
    assert r['warp_done'] == 0,          f"Unexpected warp_done: {r}"
    assert r['div_push']  == 0,          f"Unexpected div_push: {r}"
    assert r['gpu_error'] == 0,          f"Unexpected gpu_error: {r}"
    assert r['div_pop_pc']   == false_pc,   \
        f"div_pop_pc wrong: expected {false_pc:#010x}, got {r['div_pop_pc']:#010x}"
    assert r['div_pop_mask'] == false_mask, \
        f"div_pop_mask wrong: expected {false_mask:#04x}, got {r['div_pop_mask']:#04x}"
