// sky130_sram_fi_tess.sv -- fault-injecting stand-in for sky130_sram_4kbyte_1rw1r_32x1024_8 for the Tessent MBIST
// simulations.  Reuses the project's existing fault-injecting core (tb/cocotb/soc/sram_fi_core.sv, proved equal to
// sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv with faults off by test_mbist_ctrl.py::test_fi_model_equals_real_model),
// and sets its fault controls from plusargs so one compiled simv serves every fault case:
//   +<tag>_kind=N +<tag>_va=ADDR +<tag>_vb=BIT +<tag>_aa=ADDR +<tag>_ab=BIT +<tag>_val=V +<tag>_dir=D +<tag>_ret=T
// where <tag> is "sr" for u_sram.u_sram_macro (sram_controller) and "wm" for u_wmem.u_sram_macro (NPU weight memory).
// Fault kinds are those of sram_fi_core.sv (1 SAF, 2 TF, 3 CFin, 4 CFid, 5 CFst, 6 AF none, 7 AF alias,
// 8 AF multi, 9 RET, 10 WMASK lane, 11 P1STUCK).
/* verilator lint_off DECLFILENAME */
module sky130_sram_4kbyte_1rw1r_32x1024_8 (
    input  logic        clk0,
    input  logic        csb0,
    input  logic        web0,
    input  logic [3:0]  wmask0,
    input  logic [9:0]  addr0,
    input  logic [31:0] din0,
    output logic [31:0] dout0,
    input  logic        clk1,
    input  logic        csb1,
    input  logic [9:0]  addr1,
    output logic [31:0] dout1
);

    sram_fi_core #(.AW(10)) u_core (
        .clk0(clk0), .csb0(csb0), .web0(web0), .wmask0(wmask0), .addr0(addr0), .din0(din0), .dout0(dout0),
        .clk1(clk1), .csb1(csb1), .addr1(addr1), .dout1(dout1)
    );

    // Which of the two instances am I?  %m contains "u_wmem" for the NPU weight memory.
    function automatic bit is_wmem(input string s);
        for (int i = 0; i + 6 <= s.len(); i++) begin
            if (s.substr(i, i + 5) == "u_wmem") return 1'b1;
        end
        return 1'b0;
    endfunction

    string tag;
    int    v;
    initial begin
        #1;   // after sram_fi_core's own initial block has zeroed the controls
        tag = is_wmem($sformatf("%m")) ? "wm" : "sr";
        if ($value$plusargs({tag, "_kind=%d"}, v)) u_core.fi_kind   = v;
        if ($value$plusargs({tag, "_va=%d"},   v)) u_core.fi_v_addr = v;
        if ($value$plusargs({tag, "_vb=%d"},   v)) u_core.fi_v_bit  = v;
        if ($value$plusargs({tag, "_aa=%d"},   v)) u_core.fi_a_addr = v;
        if ($value$plusargs({tag, "_ab=%d"},   v)) u_core.fi_a_bit  = v;
        if ($value$plusargs({tag, "_val=%d"},  v)) u_core.fi_val    = v;
        if ($value$plusargs({tag, "_dir=%d"},  v)) u_core.fi_dir    = v;
        if ($value$plusargs({tag, "_ret=%d"},  v)) u_core.fi_ret_t  = v;
    end

endmodule : sky130_sram_4kbyte_1rw1r_32x1024_8
/* verilator lint_on DECLFILENAME */
