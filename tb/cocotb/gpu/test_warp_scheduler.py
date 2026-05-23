"""
Unit tests for warp_scheduler.sv — Phase 4 Group 4.

Tests:
  test_round_robin_ordering    — 3 warps issue in order 0→1→2 then stall (all busy)
  test_busy_warp_skipped       — round-robin skips busy warp and advances rr_ptr
  test_retire_resumes_warp     — retired warp re-enters round-robin at correct PC
  test_all_done_kernel_done    — kernel_done_o asserts once all warps signal done
  test_div_push_pop_state      — divergence stack survives warp switches
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

N_LANES = 8


def _pack_div_entry(return_pc: int, return_mask: int) -> int:
    """Pack div_entry_t: {return_pc[31:0], return_mask[N_LANES-1:0]} = 40 bits."""
    return ((return_pc & 0xFFFF_FFFF) << N_LANES) | (return_mask & 0xFF)


async def _reset(dut):
    dut.rst_n.value             = 0
    dut.launch_i.value          = 0
    dut.kernel_pc_i.value       = 0
    dut.init_mask_i.value       = 0
    dut.n_warps_active_i.value  = 0
    dut.pipe_stall_i.value      = 0
    dut.warp_retire_i.value     = 0
    dut.warp_retire_id_i.value  = 0
    dut.warp_next_pc_i.value    = 0
    dut.warp_next_mask_i.value  = 0
    dut.warp_done_i.value       = 0
    dut.warp_done_id_i.value    = 0
    dut.div_push_i.value        = 0
    dut.div_push_warp_i.value   = 0
    dut.div_push_entry_i.value  = 0
    dut.div_pop_i.value         = 0
    dut.div_pop_warp_i.value    = 0
    dut.div_pop_pc_i.value      = 0
    dut.div_pop_mask_i.value    = 0
    dut.gpu_error_i.value       = 0
    dut.exec_warp_id_i.value    = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _launch(dut, pc: int = 0x1000, mask: int = 0xFF, n_warps: int = 3):
    dut.launch_i.value          = 1
    dut.kernel_pc_i.value       = pc
    dut.init_mask_i.value       = mask
    dut.n_warps_active_i.value  = n_warps
    await RisingEdge(dut.clk)
    dut.launch_i.value = 0


async def _retire(dut, warp_id: int, next_pc: int, next_mask: int = 0xFF):
    dut.warp_retire_i.value     = 1
    dut.warp_retire_id_i.value  = warp_id
    dut.warp_next_pc_i.value    = next_pc
    dut.warp_next_mask_i.value  = next_mask
    await RisingEdge(dut.clk)
    dut.warp_retire_i.value = 0


async def _done(dut, warp_id: int):
    dut.warp_done_i.value    = 1
    dut.warp_done_id_i.value = warp_id
    await RisingEdge(dut.clk)
    dut.warp_done_i.value = 0


# ---------------------------------------------------------------------------


@cocotb.test()
async def test_round_robin_ordering(dut):
    """Issues 3 warps in strict round-robin order 0→1→2, then stalls."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    dut.pipe_stall_i.value = 0
    await _launch(dut, pc=0x1000, mask=0xFF, n_warps=3)
    # After launch posedge: n_warps_q=3, all warp state cleared, rr_ptr=0

    await Timer(1, units="ns")
    assert dut.warp_issue_o.value == 1, "Expected issue after launch"
    assert int(dut.warp_id_o.value) == 0, \
        f"Expected warp 0 first, got {int(dut.warp_id_o.value)}"
    assert int(dut.warp_pc_o.value) == 0x1000, "warp_pc should be kernel_pc"

    # posedge: warp_busy[0]=1, rr_ptr=1
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert dut.warp_issue_o.value == 1, "Expected warp 1 to issue"
    assert int(dut.warp_id_o.value) == 1, \
        f"Expected warp 1, got {int(dut.warp_id_o.value)}"

    # posedge: warp_busy[1]=1, rr_ptr=2
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert dut.warp_issue_o.value == 1, "Expected warp 2 to issue"
    assert int(dut.warp_id_o.value) == 2, \
        f"Expected warp 2, got {int(dut.warp_id_o.value)}"

    # posedge: warp_busy[2]=1, rr_ptr=0 — all 3 busy
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert dut.warp_issue_o.value == 0, "All warps busy — no issue expected"


@cocotb.test()
async def test_busy_warp_skipped(dut):
    """After warp 0 is issued, it is skipped until retired; rr_ptr advances past it."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    dut.pipe_stall_i.value = 1
    await _launch(dut, pc=0x2000, mask=0xFF, n_warps=3)
    await Timer(1, units="ns")
    assert dut.warp_issue_o.value == 0, "Stall should suppress issue"

    # Release stall for one cycle: warp 0 issues, becomes busy, rr_ptr→1
    dut.pipe_stall_i.value = 0
    await RisingEdge(dut.clk)
    dut.pipe_stall_i.value = 1
    await Timer(1, units="ns")
    assert int(dut.warp_id_o.value) == 1, \
        f"After warp 0 busy, expected warp 1 next, got {int(dut.warp_id_o.value)}"

    # Retire warp 0; rr_ptr stays at 1 (stalled, no issue)
    await _retire(dut, warp_id=0, next_pc=0x2004)
    await Timer(1, units="ns")
    # rr_ptr=1, warp0 free, warp1 free — but rr_ptr=1 so warp 1 leads

    # Release stall: warp 1 issues next (rr_ptr=1), then rr_ptr→2 → warp 2
    dut.pipe_stall_i.value = 0
    await RisingEdge(dut.clk)  # warp 1 issues, rr_ptr→2
    await Timer(1, units="ns")
    assert int(dut.warp_id_o.value) == 2, \
        f"Expected warp 2 (rr_ptr=2), got {int(dut.warp_id_o.value)}"


@cocotb.test()
async def test_retire_resumes_warp(dut):
    """Retired warp becomes eligible again on next round-robin pass with updated PC."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    dut.pipe_stall_i.value = 0
    await _launch(dut, pc=0x3000, mask=0xFF, n_warps=2)
    await Timer(1, units="ns")
    assert int(dut.warp_id_o.value) == 0, "Warp 0 should be selected first"

    # posedge: warp_busy[0]=1, rr_ptr=1 → warp 1 selected
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.warp_id_o.value) == 1, "Warp 1 should issue second"

    # posedge: warp 1 issues (busy[1]=1, rr_ptr=2);
    # simultaneously retire warp 0 — retire wins on simultaneous busy write
    dut.warp_retire_i.value    = 1
    dut.warp_retire_id_i.value = 0
    dut.warp_next_pc_i.value   = 0x3004
    dut.warp_next_mask_i.value = 0xFF
    await RisingEdge(dut.clk)   # busy[1]←1, rr_ptr←2, busy[0]←0, pc[0]←0x3004
    dut.warp_retire_i.value = 0
    await Timer(1, units="ns")
    # rr_ptr=2, n_warps=2: wrap-around → warp 0 found first
    assert int(dut.warp_id_o.value) == 0, \
        f"Retired warp 0 should re-issue via wrap-around, got {int(dut.warp_id_o.value)}"
    assert int(dut.warp_pc_o.value) == 0x3004, \
        f"Warp 0 should have updated PC 0x3004, got 0x{int(dut.warp_pc_o.value):08x}"


@cocotb.test()
async def test_all_done_kernel_done(dut):
    """kernel_done_o asserts once all active warps have signalled warp_done_i."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    dut.pipe_stall_i.value = 1
    await _launch(dut, pc=0x4000, mask=0xFF, n_warps=3)
    await Timer(1, units="ns")
    assert dut.kernel_done_o.value == 0, "Kernel should not be done yet"

    await _done(dut, warp_id=0)
    await Timer(1, units="ns")
    assert dut.kernel_done_o.value == 0, "Still 2 warps remaining"

    await _done(dut, warp_id=1)
    await Timer(1, units="ns")
    assert dut.kernel_done_o.value == 0, "Still 1 warp remaining"

    await _done(dut, warp_id=2)
    await Timer(1, units="ns")
    assert dut.kernel_done_o.value == 1, "All warps done — kernel_done should assert"


@cocotb.test()
async def test_div_push_pop_state(dut):
    """Divergence stack state for warp 0 is preserved when the scheduler switches to warp 1."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    RETURN_PC   = 0xDEAD_0000
    RETURN_MASK = 0x0F  # false-path lanes

    dut.pipe_stall_i.value = 0
    await _launch(dut, pc=0x5000, mask=0xFF, n_warps=2)
    await Timer(1, units="ns")
    assert int(dut.warp_id_o.value)          == 0
    assert int(dut.div_stack_depth_o.value)  == 0, "Warp 0 stack should start empty"

    # Issue warp 0 with a divergent branch: retire (true path) + push (false path)
    dut.warp_retire_i.value    = 1
    dut.warp_retire_id_i.value = 0
    dut.warp_next_pc_i.value   = 0x5008    # true-path PC
    dut.warp_next_mask_i.value = 0xF0      # true-path mask
    dut.div_push_i.value       = 1
    dut.div_push_warp_i.value  = 0
    dut.div_push_entry_i.value = _pack_div_entry(RETURN_PC, RETURN_MASK)
    await RisingEdge(dut.clk)
    # busy[0]←0, pc[0]←0x5008, mask[0]←0xF0, div_depth[0]←1, rr_ptr←1
    dut.warp_retire_i.value = 0
    dut.div_push_i.value    = 0
    # div_stack_*_o reflect the EXECUTING warp (exec_warp_id_i), not the issued
    # warp — inspect warp 1's (empty) stack by pointing exec_warp_id_i at it.
    dut.exec_warp_id_i.value = 1
    await Timer(1, units="ns")

    # Scheduler now presents warp 1 (rr_ptr=1); warp 1 stack depth = 0
    assert int(dut.warp_id_o.value)         == 1, \
        f"Expected warp 1 after div push, got {int(dut.warp_id_o.value)}"
    assert int(dut.div_stack_depth_o.value) == 0, "Warp 1 stack should be empty"

    # Retire warp 1 (simple, no divergence); rr_ptr→2 then wraps to 0
    dut.warp_retire_i.value    = 1
    dut.warp_retire_id_i.value = 1
    dut.warp_next_pc_i.value   = 0x6000
    dut.warp_next_mask_i.value = 0xFF
    await RisingEdge(dut.clk)   # busy[1]←0, rr_ptr←2
    dut.warp_retire_i.value = 0
    # Inspect warp 0's preserved stack (the executing warp after wrap-around).
    dut.exec_warp_id_i.value = 0
    await Timer(1, units="ns")

    # rr_ptr=2, n_warps=2 → wraps to warp 0; stack depth should be 1
    assert int(dut.warp_id_o.value)         == 0, \
        f"Expected warp 0 (wrap-around), got {int(dut.warp_id_o.value)}"
    assert int(dut.div_stack_depth_o.value) == 1, \
        f"Warp 0 stack depth should be 1, got {int(dut.div_stack_depth_o.value)}"
    top      = int(dut.div_stack_top_o.value)
    top_pc   = (top >> N_LANES) & 0xFFFF_FFFF
    top_mask = top & 0xFF
    assert top_pc   == RETURN_PC, \
        f"Expected return_pc 0x{RETURN_PC:08x}, got 0x{top_pc:08x}"
    assert top_mask == RETURN_MASK, \
        f"Expected return_mask 0x{RETURN_MASK:02x}, got 0x{top_mask:02x}"

    # Pop: warp 0 true-path VRET → restore false-path.
    # Stall the issue port so rr_ptr does not advance during the pop cycle;
    # otherwise issue+pop fire together and rr_ptr skips past warp 0.
    dut.pipe_stall_i.value   = 1
    dut.div_pop_i.value      = 1
    dut.div_pop_warp_i.value = 0
    dut.div_pop_pc_i.value   = RETURN_PC
    dut.div_pop_mask_i.value = RETURN_MASK
    await RisingEdge(dut.clk)   # div_depth[0]←0, pc[0]←RETURN_PC, rr_ptr unchanged
    dut.div_pop_i.value    = 0
    dut.pipe_stall_i.value = 0
    await Timer(1, units="ns")

    # rr_ptr=2 (unchanged); n_warps=2 → wraps back to warp 0
    assert int(dut.div_stack_depth_o.value) == 0, "Stack should be empty after pop"
    assert int(dut.warp_pc_o.value)          == RETURN_PC, \
        f"PC should be RETURN_PC after pop, got 0x{int(dut.warp_pc_o.value):08x}"
    assert int(dut.warp_mask_o.value)        == RETURN_MASK, \
        f"Mask should be RETURN_MASK after pop, got 0x{int(dut.warp_mask_o.value):02x}"
