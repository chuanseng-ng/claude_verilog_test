// sram_fi_core.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.14): fault-injecting behavioural model of the Sky130 OpenRAM
// 1RW1R macros, for the MBIST fault-injection suites. SIMULATION ONLY (lives under tb/).
//
// With fi_kind = 0 it is cycle-equivalent to sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv and
// sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv (inputs captured at the posedge, operation at the following
// negedge, dout valid for the next posedge; a port-1 read in the same cycle as a port-0 write sees the OLD
// word). test_mbist_ctrl.py::test_fi_model_equals_real_model proves the equivalence with random traffic.
// Assumption shared with the real models' use in this design: clk1 is the same net as clk0.
//
// Fault controls are plain variables that cocotb writes hierarchically (Verilator --public-flat-rw):
//   fi_kind  0 none
//            1 SAF        cell (fi_v_addr, fi_v_bit) stuck at fi_val
//            2 TF         cell (fi_v_addr, fi_v_bit) cannot make the transition: fi_dir = 1 -> cannot RISE (0->1),
//                         fi_dir = 0 -> cannot FALL (1->0)
//            3 CFin       aggressor cell (fi_a_addr, fi_a_bit) making a transition fi_dir (1 = rising) INVERTS the
//                         victim cell (fi_v_addr, fi_v_bit)
//            4 CFid       as CFin but the victim is SET to fi_val
//            5 CFst       while the aggressor cell holds fi_dir, the victim reads as fi_val
//            6 AF none    address fi_v_addr selects no cell: writes lost, reads return 0
//            7 AF alias   address fi_v_addr selects the cells of fi_a_addr instead of its own
//            8 AF multi   address fi_v_addr selects its own cells AND those of fi_a_addr (write both, read AND)
//            9 RET        cell (fi_v_addr, fi_v_bit) decays to fi_val when more than fi_ret_t negedges have passed
//                         since the last write to the word
//           11 P1STUCK   read port 1 only: data bit fi_v_bit of dout1 stuck at fi_val (the array and port 0 are fine)
//           10 WMASK      write-mask lane fi_v_bit[1:0] stuck: fi_val = 0 never written, 1 always written
// Lint: this is a testbench model; the suite's lint target runs -Wall with the unused clk1 waived below.

/* verilator lint_off BLKSEQ */
/* verilator lint_off UNUSEDSIGNAL */
module sram_fi_core #(
    parameter int unsigned AW = 10
) (
    input  logic          clk0,
    input  logic          csb0,
    input  logic          web0,
    input  logic [3:0]    wmask0,
    input  logic [AW-1:0] addr0,
    input  logic [31:0]   din0,
    output logic [31:0]   dout0,
    input  logic          clk1,
    input  logic          csb1,
    input  logic [AW-1:0] addr1,
    output logic [31:0]   dout1
);

    localparam int unsigned N = 1 << AW;

    logic [31:0] mem [N];
    int          tw  [N];
    int          now;

    int fi_kind;
    int fi_a_addr;
    int fi_a_bit;
    int fi_v_addr;
    int fi_v_bit;
    int fi_val;
    int fi_dir;
    int fi_ret_t;
    int fi_clear;   // cocotb sets 1: every word is zeroed at the next negedge (deterministic start state)

    initial begin
        now       = 0;
        fi_kind   = 0;
        fi_a_addr = 0;
        fi_a_bit  = 0;
        fi_v_addr = 0;
        fi_v_bit  = 0;
        fi_val    = 0;
        fi_dir    = 0;
        fi_ret_t  = 0;
        fi_clear  = 0;
        dout0     = 32'd0;
        dout1     = 32'd0;
        for (int i = 0; i < N; i++) begin
            mem[i] = 32'd0;
            tw[i]  = 0;
        end
    end

    function automatic logic [31:0] expand4(input logic [3:0] m);
        return {{8{m[3]}}, {8{m[2]}}, {8{m[1]}}, {8{m[0]}}};
    endfunction

    // Read one word through the fault model (uses the state BEFORE this negedge's write).
    function automatic logic [31:0] rd(input int w);
        logic [31:0] v;
        if (fi_kind == 6 && w == fi_v_addr) begin
            v = 32'd0;
        end else begin
            v = mem[(fi_kind == 7 && w == fi_v_addr) ? fi_a_addr : w];
            if (fi_kind == 8 && w == fi_v_addr) begin
                v = v & mem[fi_a_addr];
            end
            if (fi_kind == 1 && w == fi_v_addr) begin
                v[fi_v_bit] = fi_val[0];
            end
            if (fi_kind == 5 && w == fi_v_addr && mem[fi_a_addr][fi_a_bit] == fi_dir[0]) begin
                v[fi_v_bit] = fi_val[0];
            end
            if (fi_kind == 9 && w == fi_v_addr && (now - tw[w]) > fi_ret_t) begin
                v[fi_v_bit] = fi_val[0];
            end
        end
        return v;
    endfunction

    // Write one word through the fault model.
    task automatic wr(input int w, input logic [31:0] data, input logic [3:0] mask);
        logic [31:0] old_v;
        logic [31:0] new_v;
        logic [3:0]  m;
        m = mask;
        if (fi_kind == 10) begin
            m[fi_v_bit[1:0]] = fi_val[0];
        end
        old_v = mem[w];
        new_v = (old_v & ~expand4(m)) | (data & expand4(m));
        if (fi_kind == 2 && w == fi_v_addr) begin
            if (fi_dir == 1 && !old_v[fi_v_bit] && new_v[fi_v_bit]) begin
                new_v[fi_v_bit] = 1'b0;
            end
            if (fi_dir == 0 && old_v[fi_v_bit] && !new_v[fi_v_bit]) begin
                new_v[fi_v_bit] = 1'b1;
            end
        end
        if (fi_kind == 1 && w == fi_v_addr) begin
            new_v[fi_v_bit] = fi_val[0];
        end
        mem[w] = new_v;
        tw[w]  = now;
        if ((fi_kind == 3 || fi_kind == 4) && w == fi_a_addr) begin
            if (old_v[fi_a_bit] != new_v[fi_a_bit] && new_v[fi_a_bit] == fi_dir[0]) begin
                if (fi_kind == 3) begin
                    mem[fi_v_addr][fi_v_bit] = ~mem[fi_v_addr][fi_v_bit];
                end else begin
                    mem[fi_v_addr][fi_v_bit] = fi_val[0];
                end
            end
        end
    endtask

    // ── Input capture (posedge) ──────────────────────────────────────────────
    logic          csb0_r;
    logic          web0_r;
    logic [3:0]    wmask0_r;
    logic [AW-1:0] addr0_r;
    logic [31:0]   din0_r;
    logic          csb1_r;
    logic [AW-1:0] addr1_r;

    always @(posedge clk0) begin
        csb0_r   <= csb0;
        web0_r   <= web0;
        wmask0_r <= wmask0;
        addr0_r  <= addr0;
        din0_r   <= din0;
    end

    always @(posedge clk1) begin
        csb1_r  <= csb1;
        addr1_r <= addr1;
    end

    // ── Operation (negedge; one block so a port-1 read sees the pre-write state) ──
    always @(negedge clk0) begin
        now = now + 1;
        if (fi_clear != 0) begin
            for (int i = 0; i < N; i++) begin
                mem[i] = 32'd0;
                tw[i]  = now;
            end
            fi_clear = 0;
        end
        if (!csb1_r) begin
            dout1 <= rd(int'(addr1_r));
            if (fi_kind == 11) begin
                // read-port-1 data bit stuck (port 0 and the array are fine)
                dout1[fi_v_bit] <= fi_val[0];
            end
        end
        if (!csb0_r && web0_r) begin
            dout0 <= rd(int'(addr0_r));
        end
        if (!csb0_r && !web0_r) begin
            if (fi_kind == 6 && int'(addr0_r) == fi_v_addr) begin
                // address selects no cell: the write is lost
            end else if (fi_kind == 7 && int'(addr0_r) == fi_v_addr) begin
                wr(fi_a_addr, din0_r, wmask0_r);
            end else begin
                wr(int'(addr0_r), din0_r, wmask0_r);
                if (fi_kind == 8 && int'(addr0_r) == fi_v_addr) begin
                    wr(fi_a_addr, din0_r, wmask0_r);
                end
            end
        end
    end

endmodule : sram_fi_core
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on BLKSEQ */
