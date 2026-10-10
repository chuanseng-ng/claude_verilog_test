import os, sys
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
P = {}
P["p01_struct_portconn"] = """package pk; typedef struct packed { logic [31:0] instruction; logic [31:0] pc; logic v; } if_id_t; endpackage
module sub(input logic [4:0] rs1, output logic [4:0] o); assign o = rs1 ^ 5'h15; endmodule
module top(input logic [64:0] d, output logic [4:0] o);
  pk::if_id_t r; assign r = d;
  sub u(.rs1(r.instruction[19:15]), .o(o));
endmodule
"""
P["p02_const_bitsel_oob"] = """module top(input logic [3:0] a, output logic y);
  assign y = a[9];
endmodule
"""
P["p03_const_range_partial"] = """module top(input logic [3:0] a, output logic [3:0] y);
  assign y = a[5:2];
endmodule
"""
P["p04_array_const_oob"] = """module top(input logic [7:0] a0, a1, a2, a3, output logic [7:0] y);
  logic [7:0] m [0:3];
  always_comb begin m[0]=a0; m[1]=a1; m[2]=a2; m[3]=a3; end
  assign y = m[6];
endmodule
"""
P["p05_undriven_used"] = """module top(input logic a, output logic y);
  logic w;
  assign y = a & w;
endmodule
"""
P["p06_multidrive"] = """module top(input logic a, b, output logic y);
  assign y = a;
  assign y = b;
endmodule
"""
P["p07_implicit_typo"] = """module top(input logic a, b, output logic y);
  logic sig_ok;
  assign sig_okk = a & b;
  assign y = sig_ok;
endmodule
"""
P["p08_portwidth_trunc"] = """module sub(input logic [3:0] i, output logic [3:0] o); assign o = ~i; endmodule
module top(input logic [7:0] a, output logic [7:0] y);
  logic [3:0] lo;
  sub u(.i(a), .o(lo));
  assign y = {4'b0, lo};
endmodule
"""
P["p09_runtime_idx"] = """module top(input logic [3:0] a, input logic [3:0] idx, output logic y);
  assign y = a[idx];
endmodule
"""
P["p10_struct_member_sel"] = """package pk; typedef struct packed { logic [7:0] a; logic [7:0] b; } s_t; endpackage
module top(input pk::s_t s, output logic [3:0] y);
  assign y = s.b[3:0];
endmodule
"""
P["p11_unpacked_struct_portconn"] = """package pk; typedef struct { logic [31:0] instruction; logic [31:0] pc; } if_id_t; endpackage
module sub(input logic [4:0] rs1, output logic [4:0] o); assign o = rs1; endmodule
module top(input logic [31:0] d, output logic [4:0] o);
  pk::if_id_t r; assign r.instruction = d; assign r.pc = 32'h0;
  sub u(.rs1(r.instruction[19:15]), .o(o));
endmodule
"""
P["p12_wire_portconn_ctrl"] = """module sub(input logic [4:0] rs1, output logic [4:0] o); assign o = rs1; endmodule
module top(input logic [31:0] d, output logic [4:0] o);
  logic [31:0] w; assign w = d;
  sub u(.rs1(w[19:15]), .o(o));
endmodule
"""
P["p13_postinc_used"] = """module top(input logic [3:0] a, output logic [3:0] z);
  integer i, j;
  always_comb begin
    z = 4'd0;
    j = 0;
    for (i = 0; i < 4; i = i + 1) begin
      if (a[i]) begin z[j++] = 1'b1; end
    end
  end
endmodule
"""
P["p14_postinc_unused"] = """module top(input logic [3:0] a, output logic [3:0] z);
  integer i;
  always_comb begin
    z = 4'd0;
    for (i = 0; i < 4; i++) begin
      z[i] = a[3-i];
    end
  end
endmodule
"""
P["p15_enum_cast_struct_arr"] = """package pk; typedef struct packed { logic [3:0] a; logic [3:0] b; } e_t; endpackage
module sub(input logic [3:0] x, output logic [3:0] o); assign o = x; endmodule
module top(input logic [7:0] d, output logic [3:0] o);
  pk::e_t arr [0:1];
  always_comb begin arr[0] = d; arr[1] = ~d; end
  sub u(.x(arr[1].b), .o(o));
endmodule
"""
P["p16_latch_ctrl"] = """module top(input logic a, en, output logic y);
  always_comb if (en) y = a;
endmodule
"""
P["p17_param_oob_slice"] = """module top #(parameter int W = 4)(input logic [W-1:0] a, output logic y);
  assign y = a[W];   // one past the end via parameter
endmodule
"""
P["p18_instmem_idx"] = """module top(input logic [7:0] a0, a1, input logic [1:0] i, output logic [7:0] y);
  logic [7:0] m [0:1];
  assign m[0] = a0; assign m[1] = a1;
  assign y = m[i];   // runtime index wider than array
endmodule
"""
for k, v in P.items():
    with open(os.path.join(out, k + ".sv"), "w") as f:
        f.write(v)
print(len(P), "probes")
