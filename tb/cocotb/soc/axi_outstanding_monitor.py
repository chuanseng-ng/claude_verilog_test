"""Passive monitor: requests in flight on one master face of the SoC crossbar.

A request counts from the edge where its AR or AW handshake completes. A read ends at the R beat
with RLAST, a write at the B beat. The monitor never drives a signal. It records the highest
number in flight per direction and in total, and how many requests it saw, so that a maximum of
one cannot come from a monitor that saw no traffic.
"""

import cocotb
from cocotb.triggers import RisingEdge


class AxiOutstandingMonitor:
    def __init__(self, dut, master, clk, xbar_path="u_soc"):
        self._dut = dut
        self._bus = getattr(dut, xbar_path)
        self._m = master
        self._clk = clk
        self.reads_in_flight = self.writes_in_flight = 0
        self.max_reads = self.max_writes = self.max_total = 0
        self.n_ar = self.n_aw = self.n_r_last = self.n_b = 0
        self.negative = False
        self._task = cocotb.start_soon(self._run())

    def _bit(self, name):
        return (int(getattr(self._bus, f"xbar_m_{name}").value) >> self._m) & 1

    async def _run(self):
        while True:
            await RisingEdge(self._clk)
            ar = self._bit("arvalid") & self._bit("arready")
            r_last = self._bit("rvalid") & self._bit("rready") & self._bit("rlast")
            aw = self._bit("awvalid") & self._bit("awready")
            b = self._bit("bvalid") & self._bit("bready")
            self.n_ar, self.n_aw, self.n_r_last, self.n_b = (
                self.n_ar + ar, self.n_aw + aw, self.n_r_last + r_last, self.n_b + b)
            self.reads_in_flight += ar - r_last
            self.writes_in_flight += aw - b
            if self.reads_in_flight < 0 or self.writes_in_flight < 0:
                self.negative = True
            self.max_reads = max(self.max_reads, self.reads_in_flight)
            self.max_writes = max(self.max_writes, self.writes_in_flight)
            self.max_total = max(self.max_total, self.reads_in_flight + self.writes_in_flight)

    def stop(self):
        self._task.kill()

    def summary(self):
        return (f"AR {self.n_ar} R-last {self.n_r_last} AW {self.n_aw} B {self.n_b}; "
                f"max in flight: reads {self.max_reads} writes {self.max_writes} "
                f"total {self.max_total}")
