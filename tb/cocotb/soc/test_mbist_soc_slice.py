"""
test_mbist_soc_slice.py -- beads claude_verilog_test-j41m.14 / j41m.10: MBIST through the JTAG TAP on the REAL
SoC-level wrappers.

DUT: tb_mbist_soc_slice = dft_ctrl + soc_mbist + the real sram_controller and npu_top, built with
+define+SRAM_SKY130 so each wrapper instantiates its mem_collar and the Sky130 macro (a fault-injecting stand-in
carrying the real macro's name). This is the soc_top wiring of the two SoC-level macros (section 16.1 rows 1-2),
full size: two 1024 x 32 macros, port 1 on the SRAM controller's macro.

  * the controller's functional AXI4 path works before and after an MBIST run (the collar is a pass-through
    when bist_en = 0, and MBIST leaves the wrapper usable);
  * no fault: done, no failure on either macro;
  * a fault in the SRAM controller's macro and a different one in the NPU weight macro: only those two
    go/no-go bits fail, each record equals the independent golden model's, port record 0b11 on the macro with
    a functional port 1 and 0b01 on the one without;
  * a fault visible ONLY on read port 1 (the SoC SRAM's functional read path) is caught and reported as a
    port-1 mismatch (port record 0b10), which a port-0-only test would miss.
"""

import cocotb
from bfm.axi4_master import RESP_OKAY, AXI4Master
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from jtag_driver import OP_MBIST_CTRL, OP_MBIST_STATUS, JtagDriver
from mbist_golden import Fault, ctl_word, decode_status, golden_first_fail

SRAM_BASE = 0x0000_2000
AW = 10


def macro(dut, which):
    return dut.u_sram.u_sram_macro.u_core if which == "sram" else dut.u_npu.g_on.u_wmem.u_sram_macro.u_core


def arm(dut, which, f: Fault):
    m = macro(dut, which)
    m.fi_kind.value = f.kind
    m.fi_a_addr.value = f.a_addr
    m.fi_a_bit.value = f.a_bit
    m.fi_v_addr.value = f.v_addr
    m.fi_v_bit.value = f.v_bit
    m.fi_val.value = f.val
    m.fi_dir.value = f.dir
    m.fi_ret_t.value = f.ret_t


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.scan_clk_i.value = 0
    m = AXI4Master(dut, "s", dut.clk)
    dut.s_awid.value = 0
    dut.s_arid.value = 0
    dut.rst_n.value = 0
    drv = JtagDriver(dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o,
                     period_ns=53, probe=None, name="slice")  # fmt: skip
    await drv.start(hold_reset=True)
    await ClockCycles(dut.clk, 6)
    dut.rst_n.value = 1
    await drv.release_trst()
    await ClockCycles(dut.clk, 6)
    return m, drv


async def read_status(drv):
    await drv.load_ir(OP_MBIST_STATUS)
    v = await drv.shift_dr(0, 140)
    return {"ovf": v & 1, "present": (v >> 1) & 1, "core": decode_status((v >> 2) & ((1 << 69) - 1))}


async def run(drv, **kw):
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=1, dom_cpu=0, **kw), 29)
    for _ in range(300):
        st = await read_status(drv)
        if st["core"]["done"]:
            return st
    raise AssertionError("MBIST did not finish")


async def record(drv, base, i):
    kw = dict(base)
    kw["rd_sel"] = i
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=1, dom_cpu=0, **kw), 29)
    return (await read_status(drv))["core"]


async def stop(dut, drv):
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=0), 29)
    await ClockCycles(dut.clk, 8)
    assert int(dut.bist_en_o.value) == 0


async def axi_roundtrip(dut, m, base_off, words):
    rsp = await m.write(SRAM_BASE + base_off, words)
    assert rsp == RESP_OKAY
    got, rresp = await m.read(SRAM_BASE + base_off, length=len(words))
    assert rresp == RESP_OKAY and got == words, f"AXI round trip {got} != {words}"


@cocotb.test()
async def test_functional_path_and_no_fault_run(dut):
    m, drv = await setup(dut)
    assert int(dut.bist_en_o.value) == 0
    await axi_roundtrip(dut, m, 0x40, [0xDEADBEEF, 0x01234567, 0xFFFF0000, 5])
    st = await run(drv, alg=2, pause_mant=2, pause_exp=0)
    c = st["core"]
    assert c["done"] == 1 and c["fail_any"] == 0 and c["fail"] == 0 and c["cfg_err"] == 0, c
    assert int(dut.bist_en_o.value) == 1
    await stop(dut, drv)
    await axi_roundtrip(dut, m, 0x80, [0xA5A5A5A5, 0x5A5A5A5A])  # the wrapper is usable again, collar transparent
    # a second algorithm family on the same hardware
    st = await run(drv, alg=3, bg_sel=1)
    assert st["core"]["fail_any"] == 0
    await stop(dut, drv)
    dut._log.info("full-size SoC slice: March C- + retention and CKBD pass with no fault")


@cocotb.test()
async def test_faults_in_both_macros(dut):
    m, drv = await setup(dut)
    f_sram = Fault(1, v_addr=1000, v_bit=31, val=1)  # SAF1 in the SRAM controller's macro (memory 0, port 1)
    f_npu = Fault(5, a_addr=300, a_bit=5, v_addr=301, v_bit=5, val=1, dir=0)  # CFst in the NPU weight macro
    arm(dut, "sram", f_sram)
    arm(dut, "npu", f_npu)
    base = dict(alg=0, mask_sel=0)
    st = await run(drv, **base)
    assert st["core"]["fail"] == 0b11, st["core"]
    for i, f, p1 in ((0, f_sram, True), (1, f_npu, False)):
        exp = golden_first_fail(0, AW, p1, f)
        rec = await record(drv, base, i)
        for k in ("addr", "elem", "slot", "bg", "port"):
            assert rec[k] == exp[k], f"memory {i} {f.label()}: {k} TAP {rec[k]} golden {exp[k]}"
    rec = await record(drv, base, 0)
    assert rec["mask"] == 1 << 31 and rec["port"] == 0b11
    assert (await record(drv, base, 1))["port"] == 0b01
    await stop(dut, drv)
    arm(dut, "sram", Fault())
    arm(dut, "npu", Fault())
    # CKBD and LANE on the faulty hardware as well (golden agreement for a different algorithm each)
    arm(dut, "sram", Fault(10, v_bit=0, val=1))  # lane-0 mask stuck at 1: only the reverse lane pass sees it
    base = dict(alg=4)
    await run(drv, **base)
    rec = await record(drv, base, 0)
    exp = golden_first_fail(4, AW, True, Fault(10, v_bit=0, val=1))
    assert exp is not None and exp["elem"] == 21 and rec["elem"] == 21 and rec["addr"] == exp["addr"]
    await stop(dut, drv)
    arm(dut, "sram", Fault())


@cocotb.test()
async def test_port1_only_fault_is_caught(dut):
    """The SoC SRAM's functional read path is port 1. A stuck bit on dout1 alone leaves the array and port 0
    intact, so a port-0-only BIST would pass; this one must fail with the port-1 mismatch flag only."""
    m, drv = await setup(dut)
    for val, want_elem in ((1, 1), (0, 2)):  # stuck-at-1 shows in r0 (element 1), stuck-at-0 in r1 (element 2)
        arm(dut, "sram", Fault(11, v_bit=9, val=val))
        base = dict(alg=0, mask_sel=0)
        st = await run(drv, **base)
        assert st["core"]["fail"] == 0b01, st["core"]
        rec = await record(drv, base, 0)
        assert rec["port"] == 0b10, f"port-1-only fault must set only the port-1 flag, got {rec['port']:#b}"
        assert rec["elem"] == want_elem and rec["addr"] in (0, 1023) and rec["mask"] == 1 << 9, rec
        await stop(dut, drv)
    arm(dut, "sram", Fault())
