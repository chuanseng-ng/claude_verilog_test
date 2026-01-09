// ALU Unit Test
module test_alu;

    import rv32i_pkg::*;

    // DUT signals
    logic [XLEN-1:0] operand_a;
    logic [XLEN-1:0] operand_b;
    alu_op_e         alu_op;
    logic [XLEN-1:0] result;
    logic            zero;
    logic            negative;
    logic            carry;
    logic            overflow;

    // Test counters
    int test_pass = 0;
    int test_fail = 0;
    int total_tests = 0;

    // DUT instantiation
    rv32i_alu u_dut (
        .operand_a (operand_a),
        .operand_b (operand_b),
        .alu_op    (alu_op),
        .result    (result),
        .zero      (zero),
        .negative  (negative),
        .carry     (carry),
        .overflow  (overflow)
    );

    // Check result task
    task automatic check(string name, logic [31:0] expected, logic [31:0] actual);
        total_tests++;
        if (expected === actual) begin
            $display("[PASS] %s: expected=0x%08h, actual=0x%08h", name, expected, actual);
            test_pass++;
        end else begin
            $display("[FAIL] %s: expected=0x%08h, actual=0x%08h", name, expected, actual);
            test_fail++;
        end
    endtask

    // Check flag task
    task automatic check_flag(string name, logic expected, logic actual);
        total_tests++;
        if (expected === actual) begin
            $display("[PASS] %s: expected=%0d, actual=%0d", name, expected, actual);
            test_pass++;
        end else begin
            $display("[FAIL] %s: expected=%0d, actual=%0d", name, expected, actual);
            test_fail++;
        end
    endtask

    // Main test
    initial begin
        $display("\n========================================");
        $display("  ALU Unit Test");
        $display("========================================\n");

        // =====================================================================
        // ADD Tests
        // =====================================================================
        $display("--- ADD Tests ---");

        operand_a = 32'd10;
        operand_b = 32'd20;
        alu_op = ALU_OP_ADD;
        #1;
        check("ADD: 10 + 20", 32'd30, result);
        check_flag("ADD: zero flag", 1'b0, zero);

        operand_a = 32'd0;
        operand_b = 32'd0;
        #1;
        check("ADD: 0 + 0", 32'd0, result);
        check_flag("ADD: zero flag (0+0)", 1'b1, zero);

        operand_a = 32'hFFFFFFFF;
        operand_b = 32'd1;
        #1;
        check("ADD: 0xFFFFFFFF + 1 (overflow)", 32'd0, result);
        check_flag("ADD: carry", 1'b1, carry);

        operand_a = 32'h7FFFFFFF;
        operand_b = 32'd1;
        #1;
        check("ADD: 0x7FFFFFFF + 1 (signed overflow)", 32'h80000000, result);
        check_flag("ADD: overflow", 1'b1, overflow);

        // =====================================================================
        // SUB Tests
        // =====================================================================
        $display("\n--- SUB Tests ---");

        operand_a = 32'd30;
        operand_b = 32'd10;
        alu_op = ALU_OP_SUB;
        #1;
        check("SUB: 30 - 10", 32'd20, result);

        operand_a = 32'd10;
        operand_b = 32'd10;
        #1;
        check("SUB: 10 - 10", 32'd0, result);
        check_flag("SUB: zero flag", 1'b1, zero);

        operand_a = 32'd0;
        operand_b = 32'd1;
        #1;
        check("SUB: 0 - 1", 32'hFFFFFFFF, result);
        check_flag("SUB: negative", 1'b1, negative);

        // =====================================================================
        // SLL Tests (Shift Left Logical)
        // =====================================================================
        $display("\n--- SLL Tests ---");

        operand_a = 32'h00000001;
        operand_b = 32'd4;
        alu_op = ALU_OP_SLL;
        #1;
        check("SLL: 1 << 4", 32'h00000010, result);

        operand_a = 32'hFFFFFFFF;
        operand_b = 32'd16;
        #1;
        check("SLL: 0xFFFFFFFF << 16", 32'hFFFF0000, result);

        operand_a = 32'h12345678;
        operand_b = 32'd0;
        #1;
        check("SLL: shift by 0", 32'h12345678, result);

        // =====================================================================
        // SRL Tests (Shift Right Logical)
        // =====================================================================
        $display("\n--- SRL Tests ---");

        operand_a = 32'h80000000;
        operand_b = 32'd4;
        alu_op = ALU_OP_SRL;
        #1;
        check("SRL: 0x80000000 >> 4", 32'h08000000, result);

        operand_a = 32'hFFFFFFFF;
        operand_b = 32'd16;
        #1;
        check("SRL: 0xFFFFFFFF >> 16", 32'h0000FFFF, result);

        // =====================================================================
        // SRA Tests (Shift Right Arithmetic)
        // =====================================================================
        $display("\n--- SRA Tests ---");

        operand_a = 32'h80000000;
        operand_b = 32'd4;
        alu_op = ALU_OP_SRA;
        #1;
        check("SRA: 0x80000000 >>> 4 (sign extend)", 32'hF8000000, result);

        operand_a = 32'h7FFFFFFF;
        operand_b = 32'd4;
        #1;
        check("SRA: 0x7FFFFFFF >>> 4 (positive)", 32'h07FFFFFF, result);

        // =====================================================================
        // SLT Tests (Set Less Than - signed)
        // =====================================================================
        $display("\n--- SLT Tests ---");

        operand_a = 32'd5;
        operand_b = 32'd10;
        alu_op = ALU_OP_SLT;
        #1;
        check("SLT: 5 < 10", 32'd1, result);

        operand_a = 32'd10;
        operand_b = 32'd5;
        #1;
        check("SLT: 10 < 5", 32'd0, result);

        operand_a = 32'hFFFFFFFF;  // -1 signed
        operand_b = 32'd1;
        #1;
        check("SLT: -1 < 1 (signed)", 32'd1, result);

        // =====================================================================
        // SLTU Tests (Set Less Than - unsigned)
        // =====================================================================
        $display("\n--- SLTU Tests ---");

        operand_a = 32'd5;
        operand_b = 32'd10;
        alu_op = ALU_OP_SLTU;
        #1;
        check("SLTU: 5 < 10", 32'd1, result);

        operand_a = 32'hFFFFFFFF;
        operand_b = 32'd1;
        #1;
        check("SLTU: 0xFFFFFFFF < 1 (unsigned)", 32'd0, result);

        // =====================================================================
        // XOR Tests
        // =====================================================================
        $display("\n--- XOR Tests ---");

        operand_a = 32'hAAAAAAAA;
        operand_b = 32'h55555555;
        alu_op = ALU_OP_XOR;
        #1;
        check("XOR: 0xAAAAAAAA ^ 0x55555555", 32'hFFFFFFFF, result);

        operand_a = 32'hFFFFFFFF;
        operand_b = 32'hFFFFFFFF;
        #1;
        check("XOR: same values", 32'h00000000, result);

        // =====================================================================
        // OR Tests
        // =====================================================================
        $display("\n--- OR Tests ---");

        operand_a = 32'hAAAAAAAA;
        operand_b = 32'h55555555;
        alu_op = ALU_OP_OR;
        #1;
        check("OR: 0xAAAAAAAA | 0x55555555", 32'hFFFFFFFF, result);

        operand_a = 32'h00000000;
        operand_b = 32'h12345678;
        #1;
        check("OR: 0 | value", 32'h12345678, result);

        // =====================================================================
        // AND Tests
        // =====================================================================
        $display("\n--- AND Tests ---");

        operand_a = 32'hAAAAAAAA;
        operand_b = 32'h55555555;
        alu_op = ALU_OP_AND;
        #1;
        check("AND: 0xAAAAAAAA & 0x55555555", 32'h00000000, result);

        operand_a = 32'hFFFFFFFF;
        operand_b = 32'h12345678;
        #1;
        check("AND: 0xFFFFFFFF & value", 32'h12345678, result);

        // =====================================================================
        // PASS_B Tests
        // =====================================================================
        $display("\n--- PASS_B Tests ---");

        operand_a = 32'hDEADBEEF;
        operand_b = 32'h12345678;
        alu_op = ALU_OP_PASS_B;
        #1;
        check("PASS_B", 32'h12345678, result);

        // =====================================================================
        // Summary
        // =====================================================================
        $display("\n========================================");
        $display("  ALU Test Summary");
        $display("========================================");
        $display("  Total:  %0d", total_tests);
        $display("  Passed: %0d", test_pass);
        $display("  Failed: %0d", test_fail);
        $display("========================================\n");

        if (test_fail == 0) begin
            $display("  ALL TESTS PASSED!");
        end else begin
            $display("  SOME TESTS FAILED!");
        end

        $finish;
    end

endmodule
