// Register File Unit Test
module test_regfile;

    import rv32i_pkg::*;

    // Clock and reset
    logic clk;
    logic rst_n;

    // DUT signals
    logic [REG_ADDR_WIDTH-1:0] rs1_addr;
    logic [XLEN-1:0]           rs1_data;
    logic [REG_ADDR_WIDTH-1:0] rs2_addr;
    logic [XLEN-1:0]           rs2_data;
    logic [REG_ADDR_WIDTH-1:0] rd_addr;
    logic [XLEN-1:0]           rd_data;
    logic                      rd_we;
    logic [REG_ADDR_WIDTH-1:0] dbg_addr;
    logic [XLEN-1:0]           dbg_wdata;
    logic                      dbg_we;
    logic [XLEN-1:0]           dbg_rdata;

    // Test counters
    int test_pass = 0;
    int test_fail = 0;
    int total_tests = 0;

    // Clock generation
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    // DUT instantiation
    rv32i_regfile u_dut (
        .clk       (clk),
        .rst_n     (rst_n),
        .rs1_addr  (rs1_addr),
        .rs1_data  (rs1_data),
        .rs2_addr  (rs2_addr),
        .rs2_data  (rs2_data),
        .rd_addr   (rd_addr),
        .rd_data   (rd_data),
        .rd_we     (rd_we),
        .dbg_addr  (dbg_addr),
        .dbg_wdata (dbg_wdata),
        .dbg_we    (dbg_we),
        .dbg_rdata (dbg_rdata)
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

    // Write register task
    task automatic write_reg(input logic [4:0] addr, input logic [31:0] data);
        rd_addr = addr;
        rd_data = data;
        rd_we   = 1'b1;
        @(posedge clk);
        rd_we = 1'b0;
        @(posedge clk);
    endtask

    // Read register task
    task automatic read_reg_rs1(input logic [4:0] addr, output logic [31:0] data);
        rs1_addr = addr;
        @(negedge clk);  // Read on negative edge to allow combinational read
        data = rs1_data;
    endtask

    // Main test
    initial begin
        $display("\n========================================");
        $display("  Register File Unit Test");
        $display("========================================\n");

        // Initialize signals
        rst_n     = 1'b0;
        rs1_addr  = '0;
        rs2_addr  = '0;
        rd_addr   = '0;
        rd_data   = '0;
        rd_we     = 1'b0;
        dbg_addr  = '0;
        dbg_wdata = '0;
        dbg_we    = 1'b0;

        // Reset
        repeat(5) @(posedge clk);
        rst_n = 1'b1;
        repeat(2) @(posedge clk);

        // =====================================================================
        // Test: x0 always reads zero
        // =====================================================================
        $display("--- x0 Always Zero Tests ---");

        rs1_addr = 5'd0;
        @(negedge clk);
        check("x0 reads 0 initially", 32'h0, rs1_data);

        // Try to write to x0
        write_reg(5'd0, 32'hDEADBEEF);
        rs1_addr = 5'd0;
        @(negedge clk);
        check("x0 reads 0 after write attempt", 32'h0, rs1_data);

        // =====================================================================
        // Test: Basic write and read
        // =====================================================================
        $display("\n--- Basic Write/Read Tests ---");

        write_reg(5'd1, 32'h12345678);
        rs1_addr = 5'd1;
        @(negedge clk);
        check("x1 write/read", 32'h12345678, rs1_data);

        write_reg(5'd31, 32'hABCDEF00);
        rs1_addr = 5'd31;
        @(negedge clk);
        check("x31 write/read", 32'hABCDEF00, rs1_data);

        // =====================================================================
        // Test: Dual-port read
        // =====================================================================
        $display("\n--- Dual-Port Read Tests ---");

        write_reg(5'd10, 32'h11111111);
        write_reg(5'd11, 32'h22222222);

        rs1_addr = 5'd10;
        rs2_addr = 5'd11;
        @(negedge clk);
        check("Dual read: rs1 (x10)", 32'h11111111, rs1_data);
        check("Dual read: rs2 (x11)", 32'h22222222, rs2_data);

        // Read same register on both ports
        rs1_addr = 5'd10;
        rs2_addr = 5'd10;
        @(negedge clk);
        check("Same reg on rs1", 32'h11111111, rs1_data);
        check("Same reg on rs2", 32'h11111111, rs2_data);

        // =====================================================================
        // Test: Debug port read
        // =====================================================================
        $display("\n--- Debug Port Read Tests ---");

        write_reg(5'd15, 32'hDEADC0DE);
        dbg_addr = 5'd15;
        @(negedge clk);
        check("Debug read x15", 32'hDEADC0DE, dbg_rdata);

        dbg_addr = 5'd0;
        @(negedge clk);
        check("Debug read x0", 32'h0, dbg_rdata);

        // =====================================================================
        // Test: Debug port write
        // =====================================================================
        $display("\n--- Debug Port Write Tests ---");

        // Disable normal write, enable debug write
        rd_we = 1'b0;
        dbg_addr  = 5'd20;
        dbg_wdata = 32'hCAFEBABE;
        dbg_we    = 1'b1;
        @(posedge clk);
        dbg_we = 1'b0;
        @(posedge clk);

        rs1_addr = 5'd20;
        @(negedge clk);
        check("Debug write x20", 32'hCAFEBABE, rs1_data);

        // Debug write to x0 should not work
        dbg_addr  = 5'd0;
        dbg_wdata = 32'hFFFFFFFF;
        dbg_we    = 1'b1;
        @(posedge clk);
        dbg_we = 1'b0;
        @(posedge clk);

        dbg_addr = 5'd0;
        @(negedge clk);
        check("Debug write x0 (should fail)", 32'h0, dbg_rdata);

        // =====================================================================
        // Test: Write priority (normal write has priority over debug)
        // =====================================================================
        $display("\n--- Write Priority Tests ---");

        // Simultaneous write - normal should win
        rd_addr   = 5'd25;
        rd_data   = 32'h11111111;
        rd_we     = 1'b1;
        dbg_addr  = 5'd25;
        dbg_wdata = 32'h22222222;
        dbg_we    = 1'b1;
        @(posedge clk);
        rd_we  = 1'b0;
        dbg_we = 1'b0;
        @(posedge clk);

        rs1_addr = 5'd25;
        @(negedge clk);
        check("Write priority: normal wins", 32'h11111111, rs1_data);

        // =====================================================================
        // Test: All registers
        // =====================================================================
        $display("\n--- All Registers Test ---");

        // Write unique values to all registers
        for (int i = 1; i < 32; i++) begin
            write_reg(i[4:0], 32'h1000 + i);
        end

        // Verify all registers
        for (int i = 0; i < 32; i++) begin
            rs1_addr = i[4:0];
            @(negedge clk);
            if (i == 0) begin
                check($sformatf("x%0d", i), 32'h0, rs1_data);
            end else begin
                check($sformatf("x%0d", i), 32'h1000 + i, rs1_data);
            end
        end

        // =====================================================================
        // Test: Reset clears all registers
        // =====================================================================
        $display("\n--- Reset Test ---");

        // Apply reset
        rst_n = 1'b0;
        repeat(3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        // Verify all registers are zero
        for (int i = 0; i < 32; i++) begin
            rs1_addr = i[4:0];
            @(negedge clk);
            check($sformatf("Reset: x%0d = 0", i), 32'h0, rs1_data);
        end

        // =====================================================================
        // Summary
        // =====================================================================
        $display("\n========================================");
        $display("  Register File Test Summary");
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

    // Timeout
    initial begin
        #100000;
        $display("ERROR: Timeout!");
        $finish;
    end

endmodule
