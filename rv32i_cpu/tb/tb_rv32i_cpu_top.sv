// Top-level Testbench for RV32I CPU
module tb_rv32i_cpu_top;

    import rv32i_pkg::*;
    import axi4lite_pkg::*;

    // =========================================================================
    // Parameters
    // =========================================================================
    parameter int CLK_PERIOD = 10;  // 100 MHz
    parameter int MEM_SIZE   = 65536;  // 64KB

    // =========================================================================
    // Signals
    // =========================================================================
    logic clk;
    logic rst_n;

    // AXI4-Lite signals
    logic [AXI_ADDR_WIDTH-1:0] m_axi_awaddr;
    logic                      m_axi_awvalid;
    logic                      m_axi_awready;
    logic [AXI_DATA_WIDTH-1:0] m_axi_wdata;
    logic [AXI_STRB_WIDTH-1:0] m_axi_wstrb;
    logic                      m_axi_wvalid;
    logic                      m_axi_wready;
    logic [1:0]                m_axi_bresp;
    logic                      m_axi_bvalid;
    logic                      m_axi_bready;
    logic [AXI_ADDR_WIDTH-1:0] m_axi_araddr;
    logic                      m_axi_arvalid;
    logic                      m_axi_arready;
    logic [AXI_DATA_WIDTH-1:0] m_axi_rdata;
    logic [1:0]                m_axi_rresp;
    logic                      m_axi_rvalid;
    logic                      m_axi_rready;

    // APB3 signals
    logic [11:0]               s_apb_paddr;
    logic                      s_apb_psel;
    logic                      s_apb_penable;
    logic                      s_apb_pwrite;
    logic [31:0]               s_apb_pwdata;
    logic [31:0]               s_apb_prdata;
    logic                      s_apb_pready;
    logic                      s_apb_pslverr;

    // Test control
    string test_name;
    int    test_pass;
    int    test_fail;
    int    total_tests;

    // =========================================================================
    // Clock Generation
    // =========================================================================
    initial begin
        clk = 1'b0;
        forever #(CLK_PERIOD/2) clk = ~clk;
    end

    // =========================================================================
    // DUT Instantiation
    // =========================================================================
    rv32i_cpu_top u_dut (
        .clk            (clk),
        .rst_n          (rst_n),

        // AXI4-Lite
        .m_axi_awaddr   (m_axi_awaddr),
        .m_axi_awvalid  (m_axi_awvalid),
        .m_axi_awready  (m_axi_awready),
        .m_axi_wdata    (m_axi_wdata),
        .m_axi_wstrb    (m_axi_wstrb),
        .m_axi_wvalid   (m_axi_wvalid),
        .m_axi_wready   (m_axi_wready),
        .m_axi_bresp    (m_axi_bresp),
        .m_axi_bvalid   (m_axi_bvalid),
        .m_axi_bready   (m_axi_bready),
        .m_axi_araddr   (m_axi_araddr),
        .m_axi_arvalid  (m_axi_arvalid),
        .m_axi_arready  (m_axi_arready),
        .m_axi_rdata    (m_axi_rdata),
        .m_axi_rresp    (m_axi_rresp),
        .m_axi_rvalid   (m_axi_rvalid),
        .m_axi_rready   (m_axi_rready),

        // APB3
        .s_apb_paddr    (s_apb_paddr),
        .s_apb_psel     (s_apb_psel),
        .s_apb_penable  (s_apb_penable),
        .s_apb_pwrite   (s_apb_pwrite),
        .s_apb_pwdata   (s_apb_pwdata),
        .s_apb_prdata   (s_apb_prdata),
        .s_apb_pready   (s_apb_pready),
        .s_apb_pslverr  (s_apb_pslverr)
    );

    // =========================================================================
    // Memory Model
    // =========================================================================
    axi4lite_mem #(
        .MEM_SIZE_BYTES (MEM_SIZE),
        .MEM_LATENCY    (1)
    ) u_mem (
        .clk            (clk),
        .rst_n          (rst_n),
        .s_axi_awaddr   (m_axi_awaddr),
        .s_axi_awvalid  (m_axi_awvalid),
        .s_axi_awready  (m_axi_awready),
        .s_axi_wdata    (m_axi_wdata),
        .s_axi_wstrb    (m_axi_wstrb),
        .s_axi_wvalid   (m_axi_wvalid),
        .s_axi_wready   (m_axi_wready),
        .s_axi_bresp    (m_axi_bresp),
        .s_axi_bvalid   (m_axi_bvalid),
        .s_axi_bready   (m_axi_bready),
        .s_axi_araddr   (m_axi_araddr),
        .s_axi_arvalid  (m_axi_arvalid),
        .s_axi_arready  (m_axi_arready),
        .s_axi_rdata    (m_axi_rdata),
        .s_axi_rresp    (m_axi_rresp),
        .s_axi_rvalid   (m_axi_rvalid),
        .s_axi_rready   (m_axi_rready)
    );

    // =========================================================================
    // APB Master BFM
    // =========================================================================
    apb3_master u_apb_master (
        .clk            (clk),
        .rst_n          (rst_n),
        .paddr          (s_apb_paddr),
        .psel           (s_apb_psel),
        .penable        (s_apb_penable),
        .pwrite         (s_apb_pwrite),
        .pwdata         (s_apb_pwdata),
        .prdata         (s_apb_prdata),
        .pready         (s_apb_pready),
        .pslverr        (s_apb_pslverr)
    );

    // =========================================================================
    // Test Tasks
    // =========================================================================

    // Reset the DUT
    task automatic reset_dut();
        rst_n = 1'b0;
        repeat(10) @(posedge clk);
        rst_n = 1'b1;
        repeat(5) @(posedge clk);
    endtask

    // Check test result
    task automatic check_result(string name, logic [31:0] expected, logic [31:0] actual);
        total_tests++;
        if (expected === actual) begin
            $display("[PASS] %s: expected=0x%08h, actual=0x%08h", name, expected, actual);
            test_pass++;
        end else begin
            $display("[FAIL] %s: expected=0x%08h, actual=0x%08h", name, expected, actual);
            test_fail++;
        end
    endtask

    // Run for N cycles
    task automatic run_cycles(int n);
        repeat(n) @(posedge clk);
    endtask

    // =========================================================================
    // Test: Simple ALU operations via program execution
    // =========================================================================
    task automatic test_alu_program();
        logic [31:0] result;

        test_name = "ALU Program Test";
        $display("\n=== %s ===", test_name);

        // Load program: ADDI x1, x0, 10; ADDI x2, x0, 20; ADD x3, x1, x2
        // ADDI x1, x0, 10  -> 0x00A00093
        // ADDI x2, x0, 20  -> 0x01400113
        // ADD  x3, x1, x2  -> 0x002081B3
        // EBREAK           -> 0x00100073
        u_mem.write_word(32'h0000, 32'h00A00093);  // ADDI x1, x0, 10
        u_mem.write_word(32'h0004, 32'h01400113);  // ADDI x2, x0, 20
        u_mem.write_word(32'h0008, 32'h002081B3);  // ADD x3, x1, x2
        u_mem.write_word(32'h000C, 32'h00100073);  // EBREAK

        reset_dut();

        // Wait for EBREAK (CPU will halt)
        u_apb_master.wait_for_halt(1000);

        // Check results via debug interface
        u_apb_master.read_gpr(1, result);
        check_result("x1 = 10", 32'd10, result);

        u_apb_master.read_gpr(2, result);
        check_result("x2 = 20", 32'd20, result);

        u_apb_master.read_gpr(3, result);
        check_result("x3 = 30", 32'd30, result);
    endtask

    // =========================================================================
    // Test: Load/Store operations
    // =========================================================================
    task automatic test_load_store();
        logic [31:0] result;

        test_name = "Load/Store Test";
        $display("\n=== %s ===", test_name);

        // Load program:
        // ADDI x1, x0, 0x42    -> 0x04200093
        // SW   x1, 0x100(x0)   -> 0x10102023  (store to 0x100)
        // LW   x2, 0x100(x0)   -> 0x10002103  (load from 0x100)
        // EBREAK               -> 0x00100073
        u_mem.write_word(32'h0000, 32'h04200093);  // ADDI x1, x0, 0x42
        u_mem.write_word(32'h0004, 32'h10102023);  // SW x1, 0x100(x0)
        u_mem.write_word(32'h0008, 32'h10002103);  // LW x2, 0x100(x0)
        u_mem.write_word(32'h000C, 32'h00100073);  // EBREAK

        reset_dut();

        // Wait for EBREAK
        u_apb_master.wait_for_halt(1000);

        // Check that x2 loaded the value
        u_apb_master.read_gpr(2, result);
        check_result("x2 = 0x42 (loaded)", 32'h42, result);

        // Check memory contents
        result = u_mem.read_word(32'h100);
        check_result("MEM[0x100] = 0x42", 32'h42, result);
    endtask

    // =========================================================================
    // Test: Branch operations
    // =========================================================================
    task automatic test_branches();
        logic [31:0] result;

        test_name = "Branch Test";
        $display("\n=== %s ===", test_name);

        // Load program that tests BEQ:
        // ADDI x1, x0, 5       -> 0x00500093
        // ADDI x2, x0, 5       -> 0x00500113
        // BEQ  x1, x2, +8      -> 0x00208463  (branch to PC+8 if equal)
        // ADDI x3, x0, 1       -> 0x00100193  (skipped if branch taken)
        // ADDI x4, x0, 99      -> 0x06300213  (executed after branch)
        // EBREAK               -> 0x00100073
        u_mem.write_word(32'h0000, 32'h00500093);  // ADDI x1, x0, 5
        u_mem.write_word(32'h0004, 32'h00500113);  // ADDI x2, x0, 5
        u_mem.write_word(32'h0008, 32'h00208463);  // BEQ x1, x2, +8
        u_mem.write_word(32'h000C, 32'h00100193);  // ADDI x3, x0, 1 (skipped)
        u_mem.write_word(32'h0010, 32'h06300213);  // ADDI x4, x0, 99
        u_mem.write_word(32'h0014, 32'h00100073);  // EBREAK

        reset_dut();

        // Wait for EBREAK
        u_apb_master.wait_for_halt(1000);

        // x3 should be 0 (instruction was skipped)
        u_apb_master.read_gpr(3, result);
        check_result("x3 = 0 (branch taken, skipped)", 32'd0, result);

        // x4 should be 99
        u_apb_master.read_gpr(4, result);
        check_result("x4 = 99", 32'd99, result);
    endtask

    // =========================================================================
    // Test: Debug halt/resume
    // =========================================================================
    task automatic test_debug_halt_resume();
        logic [31:0] pc1, pc2, status;

        test_name = "Debug Halt/Resume Test";
        $display("\n=== %s ===", test_name);

        // Load infinite loop program
        // loop: ADDI x1, x1, 1  -> 0x00108093
        //       JAL  x0, loop   -> 0xFFDFF06F  (jump back -4)
        u_mem.write_word(32'h0000, 32'h00108093);  // ADDI x1, x1, 1
        u_mem.write_word(32'h0004, 32'hFFDFF06F);  // JAL x0, -4

        reset_dut();

        // Let it run for a bit
        run_cycles(100);

        // Halt the CPU
        u_apb_master.halt_cpu();

        // Read PC
        u_apb_master.read_pc(pc1);

        // Read status
        u_apb_master.read_status(status);
        check_result("CPU is halted", 32'h1, status & 32'h1);

        // Resume for a bit
        u_apb_master.resume_cpu();
        run_cycles(50);

        // Halt again
        u_apb_master.halt_cpu();
        u_apb_master.read_pc(pc2);

        // PC should have changed (program was running)
        total_tests++;
        if (pc1 !== pc2 || pc1 !== 32'h0) begin
            $display("[PASS] PC changed after resume: pc1=0x%08h, pc2=0x%08h", pc1, pc2);
            test_pass++;
        end else begin
            $display("[FAIL] PC did not change as expected");
            test_fail++;
        end
    endtask

    // =========================================================================
    // Test: Debug register access
    // =========================================================================
    task automatic test_debug_reg_access();
        logic [31:0] result;

        test_name = "Debug Register Access Test";
        $display("\n=== %s ===", test_name);

        // Load simple program
        u_mem.write_word(32'h0000, 32'h00100073);  // EBREAK immediately

        reset_dut();

        // Wait for halt
        u_apb_master.wait_for_halt(100);

        // Write to x5 via debug
        u_apb_master.write_gpr(5, 32'hDEADBEEF);

        // Read back
        u_apb_master.read_gpr(5, result);
        check_result("x5 written via debug", 32'hDEADBEEF, result);

        // Write to x10
        u_apb_master.write_gpr(10, 32'h12345678);
        u_apb_master.read_gpr(10, result);
        check_result("x10 written via debug", 32'h12345678, result);

        // Verify x0 always reads 0
        u_apb_master.write_gpr(0, 32'hFFFFFFFF);
        u_apb_master.read_gpr(0, result);
        check_result("x0 always 0", 32'h0, result);
    endtask

    // =========================================================================
    // Test: Breakpoints
    // =========================================================================
    task automatic test_breakpoints();
        logic [31:0] pc, status;

        test_name = "Breakpoint Test";
        $display("\n=== %s ===", test_name);

        // Load program: series of NOPs with breakpoint in middle
        // NOP = ADDI x0, x0, 0 -> 0x00000013
        u_mem.write_word(32'h0000, 32'h00000013);  // NOP @ 0x00
        u_mem.write_word(32'h0004, 32'h00000013);  // NOP @ 0x04
        u_mem.write_word(32'h0008, 32'h00000013);  // NOP @ 0x08 <- breakpoint here
        u_mem.write_word(32'h000C, 32'h00000013);  // NOP @ 0x0C
        u_mem.write_word(32'h0010, 32'h00100073);  // EBREAK @ 0x10

        reset_dut();

        // Set breakpoint at address 0x08
        u_apb_master.set_breakpoint0(32'h00000008, 1'b1);

        // Wait for breakpoint hit
        u_apb_master.wait_for_halt(500);

        // Check that we stopped at the breakpoint address
        u_apb_master.read_pc(pc);
        check_result("Stopped at breakpoint", 32'h00000008, pc);

        // Check halt cause
        u_apb_master.read_status(status);
        check_result("Halt cause is breakpoint", 4'd2, status[7:4]);  // HALT_BREAKPOINT = 2

        // Clear breakpoint and continue
        u_apb_master.clear_breakpoints();
        u_apb_master.resume_cpu();

        // Wait for EBREAK
        u_apb_master.wait_for_halt(500);

        // Should now be at EBREAK
        u_apb_master.read_pc(pc);
        check_result("Continued to EBREAK", 32'h00000010, pc);
    endtask

    // =========================================================================
    // Test: Single-step
    // =========================================================================
    task automatic test_single_step();
        logic [31:0] pc;

        test_name = "Single-Step Test";
        $display("\n=== %s ===", test_name);

        // Load simple program
        u_mem.write_word(32'h0000, 32'h00000013);  // NOP
        u_mem.write_word(32'h0004, 32'h00000013);  // NOP
        u_mem.write_word(32'h0008, 32'h00000013);  // NOP
        u_mem.write_word(32'h000C, 32'h00100073);  // EBREAK

        reset_dut();

        // Halt immediately
        u_apb_master.halt_cpu();

        // Check initial PC
        u_apb_master.read_pc(pc);
        check_result("Initial PC", 32'h00000000, pc);

        // Single step
        u_apb_master.step_cpu();
        u_apb_master.read_pc(pc);
        check_result("After step 1", 32'h00000004, pc);

        // Single step again
        u_apb_master.step_cpu();
        u_apb_master.read_pc(pc);
        check_result("After step 2", 32'h00000008, pc);

        // Single step once more
        u_apb_master.step_cpu();
        u_apb_master.read_pc(pc);
        check_result("After step 3", 32'h0000000C, pc);
    endtask

    // =========================================================================
    // Main Test Sequence
    // =========================================================================
    initial begin
        // Initialize
        test_pass = 0;
        test_fail = 0;
        total_tests = 0;

        $display("\n");
        $display("========================================");
        $display("  RV32I CPU Testbench");
        $display("========================================");

        // Reset
        rst_n = 1'b0;
        repeat(10) @(posedge clk);
        rst_n = 1'b1;
        repeat(10) @(posedge clk);

        // Run tests
        test_alu_program();
        test_load_store();
        test_branches();
        test_debug_halt_resume();
        test_debug_reg_access();
        test_breakpoints();
        test_single_step();

        // Summary
        $display("\n");
        $display("========================================");
        $display("  Test Summary");
        $display("========================================");
        $display("  Total:  %0d", total_tests);
        $display("  Passed: %0d", test_pass);
        $display("  Failed: %0d", test_fail);
        $display("========================================");

        if (test_fail == 0) begin
            $display("  ALL TESTS PASSED!");
        end else begin
            $display("  SOME TESTS FAILED!");
        end
        $display("========================================\n");

        $finish;
    end

    // =========================================================================
    // Timeout
    // =========================================================================
    initial begin
        #1000000;  // 1ms timeout at 100MHz
        $display("ERROR: Simulation timeout!");
        $finish;
    end

    // =========================================================================
    // Waveform Dump
    // =========================================================================
    initial begin
        $dumpfile("waveform.vcd");
        $dumpvars(0, tb_rv32i_cpu_top);
    end

endmodule
