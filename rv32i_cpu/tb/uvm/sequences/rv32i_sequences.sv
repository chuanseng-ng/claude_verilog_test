//-----------------------------------------------------------------------------
// RV32I Test Sequences
// Virtual sequences for CPU verification
//-----------------------------------------------------------------------------

import rv32i_pkg::*;

//-----------------------------------------------------------------------------
// Base Virtual Sequence
//-----------------------------------------------------------------------------
class rv32i_base_vseq extends uvm_sequence;

    `uvm_object_utils(rv32i_base_vseq)
    `uvm_declare_p_sequencer(rv32i_virtual_sequencer)

    // Instruction generator
    rv32i_instr_gen instr_gen;

    // Environment handle (set by test)
    rv32i_env env;

    function new(string name = "rv32i_base_vseq");
        super.new(name);
        instr_gen = rv32i_instr_gen::type_id::create("instr_gen");
    endfunction

    // Wait for CPU to halt
    task wait_for_halt(int timeout = 10000);
        apb3_wait_halt_seq halt_seq;
        halt_seq = apb3_wait_halt_seq::type_id::create("halt_seq");
        halt_seq.timeout_cycles = timeout;
        halt_seq.start(p_sequencer.apb_sqr);
        if (halt_seq.timed_out)
            `uvm_error("VSEQ", "Timeout waiting for CPU halt")
    endtask

    // Halt CPU via debug
    task halt_cpu();
        apb3_halt_seq halt_seq;
        halt_seq = apb3_halt_seq::type_id::create("halt_seq");
        halt_seq.start(p_sequencer.apb_sqr);
    endtask

    // Resume CPU via debug
    task resume_cpu();
        apb3_resume_seq resume_seq;
        resume_seq = apb3_resume_seq::type_id::create("resume_seq");
        resume_seq.start(p_sequencer.apb_sqr);
    endtask

    // Single step CPU
    task step_cpu();
        apb3_step_seq step_seq;
        step_seq = apb3_step_seq::type_id::create("step_seq");
        step_seq.start(p_sequencer.apb_sqr);
    endtask

    // Read PC
    task read_pc(output logic [31:0] pc);
        apb3_read_pc_seq pc_seq;
        pc_seq = apb3_read_pc_seq::type_id::create("pc_seq");
        pc_seq.start(p_sequencer.apb_sqr);
        pc = pc_seq.pc;
    endtask

    // Read all GPRs
    task read_all_gprs(output logic [31:0] gprs[32]);
        apb3_read_all_gprs_seq gpr_seq;
        gpr_seq = apb3_read_all_gprs_seq::type_id::create("gpr_seq");
        gpr_seq.start(p_sequencer.apb_sqr);
        gprs = gpr_seq.gprs;
    endtask

    // Set breakpoint
    task set_breakpoint(int bp_num, logic [31:0] addr, bit enable = 1);
        apb3_set_breakpoint_seq bp_seq;
        bp_seq = apb3_set_breakpoint_seq::type_id::create("bp_seq");
        bp_seq.bp_num = bp_num;
        bp_seq.bp_addr = addr;
        bp_seq.enable = enable;
        bp_seq.start(p_sequencer.apb_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// Random Program Sequence
// Generates and runs random programs, checks results
//-----------------------------------------------------------------------------
class rv32i_random_prog_vseq extends rv32i_base_vseq;

    `uvm_object_utils(rv32i_random_prog_vseq)

    // Configuration
    int num_instructions = 50;
    int num_iterations = 10;

    function new(string name = "rv32i_random_prog_vseq");
        super.new(name);
    endfunction

    task body();
        logic [31:0] prog[];
        logic [31:0] dut_pc;
        logic [31:0] dut_gprs[32];

        `uvm_info("RAND_VSEQ", $sformatf("Running %0d random program iterations", num_iterations), UVM_LOW)

        for (int iter = 0; iter < num_iterations; iter++) begin
            `uvm_info("RAND_VSEQ", $sformatf("=== Iteration %0d ===", iter), UVM_MEDIUM)

            // Generate random program
            instr_gen.max_instructions = num_instructions;
            instr_gen.generate_program();
            instr_gen.get_program(prog);
            instr_gen.print_program();

            // Load into memory and reference model
            env.load_program(prog);

            // Run reference model
            env.scoreboard.ref_model.reset();
            env.scoreboard.load_program(prog);
            env.scoreboard.run_reference();

            // Resume CPU to run program
            resume_cpu();

            // Wait for halt (EBREAK)
            wait_for_halt();

            // Read DUT state
            read_pc(dut_pc);
            read_all_gprs(dut_gprs);

            // Compare
            env.scoreboard.compare_registers(dut_gprs, dut_pc);

            // Small delay between iterations
            #100ns;
        end

        `uvm_info("RAND_VSEQ", "Random program test complete", UVM_LOW)
    endtask

endclass

//-----------------------------------------------------------------------------
// ALU Test Sequence
// Focused testing of ALU operations
//-----------------------------------------------------------------------------
class rv32i_alu_test_vseq extends rv32i_base_vseq;

    `uvm_object_utils(rv32i_alu_test_vseq)

    function new(string name = "rv32i_alu_test_vseq");
        super.new(name);
    endfunction

    task body();
        logic [31:0] prog[];
        logic [31:0] dut_pc;
        logic [31:0] dut_gprs[32];

        `uvm_info("ALU_VSEQ", "Running ALU test sequence", UVM_LOW)

        // Configure generator for ALU-heavy program
        instr_gen.weight_alu_reg  = 40;
        instr_gen.weight_alu_imm  = 40;
        instr_gen.weight_load     = 5;
        instr_gen.weight_store    = 5;
        instr_gen.weight_branch   = 5;
        instr_gen.weight_jump     = 2;
        instr_gen.weight_upper    = 3;

        instr_gen.max_instructions = 100;
        instr_gen.generate_program();
        instr_gen.get_program(prog);
        instr_gen.print_program();

        // Load and run
        env.load_program(prog);
        env.scoreboard.ref_model.reset();
        env.scoreboard.load_program(prog);
        env.scoreboard.run_reference();

        resume_cpu();
        wait_for_halt();

        read_pc(dut_pc);
        read_all_gprs(dut_gprs);
        env.scoreboard.compare_registers(dut_gprs, dut_pc);

        `uvm_info("ALU_VSEQ", "ALU test complete", UVM_LOW)
    endtask

endclass

//-----------------------------------------------------------------------------
// Load/Store Test Sequence
//-----------------------------------------------------------------------------
class rv32i_loadstore_test_vseq extends rv32i_base_vseq;

    `uvm_object_utils(rv32i_loadstore_test_vseq)

    function new(string name = "rv32i_loadstore_test_vseq");
        super.new(name);
    endfunction

    task body();
        logic [31:0] prog[];
        logic [31:0] dut_pc;
        logic [31:0] dut_gprs[32];

        `uvm_info("LS_VSEQ", "Running Load/Store test sequence", UVM_LOW)

        // Configure generator for load/store-heavy program
        instr_gen.weight_alu_reg  = 10;
        instr_gen.weight_alu_imm  = 20;
        instr_gen.weight_load     = 30;
        instr_gen.weight_store    = 30;
        instr_gen.weight_branch   = 5;
        instr_gen.weight_jump     = 2;
        instr_gen.weight_upper    = 3;

        instr_gen.max_instructions = 80;
        instr_gen.generate_program();
        instr_gen.get_program(prog);
        instr_gen.print_program();

        // Load and run
        env.load_program(prog);
        env.scoreboard.ref_model.reset();
        env.scoreboard.load_program(prog);
        env.scoreboard.run_reference();

        resume_cpu();
        wait_for_halt();

        read_pc(dut_pc);
        read_all_gprs(dut_gprs);
        env.scoreboard.compare_registers(dut_gprs, dut_pc);

        `uvm_info("LS_VSEQ", "Load/Store test complete", UVM_LOW)
    endtask

endclass

//-----------------------------------------------------------------------------
// Branch Test Sequence
//-----------------------------------------------------------------------------
class rv32i_branch_test_vseq extends rv32i_base_vseq;

    `uvm_object_utils(rv32i_branch_test_vseq)

    function new(string name = "rv32i_branch_test_vseq");
        super.new(name);
    endfunction

    task body();
        logic [31:0] prog[];
        logic [31:0] dut_pc;
        logic [31:0] dut_gprs[32];

        `uvm_info("BR_VSEQ", "Running Branch test sequence", UVM_LOW)

        // Configure generator for branch-heavy program
        instr_gen.weight_alu_reg  = 15;
        instr_gen.weight_alu_imm  = 20;
        instr_gen.weight_load     = 5;
        instr_gen.weight_store    = 5;
        instr_gen.weight_branch   = 40;
        instr_gen.weight_jump     = 10;
        instr_gen.weight_upper    = 5;

        instr_gen.max_instructions = 60;
        instr_gen.generate_program();
        instr_gen.get_program(prog);
        instr_gen.print_program();

        // Load and run
        env.load_program(prog);
        env.scoreboard.ref_model.reset();
        env.scoreboard.load_program(prog);
        env.scoreboard.run_reference();

        resume_cpu();
        wait_for_halt();

        read_pc(dut_pc);
        read_all_gprs(dut_gprs);
        env.scoreboard.compare_registers(dut_gprs, dut_pc);

        `uvm_info("BR_VSEQ", "Branch test complete", UVM_LOW)
    endtask

endclass

//-----------------------------------------------------------------------------
// Debug Interface Test Sequence
//-----------------------------------------------------------------------------
class rv32i_debug_test_vseq extends rv32i_base_vseq;

    `uvm_object_utils(rv32i_debug_test_vseq)

    function new(string name = "rv32i_debug_test_vseq");
        super.new(name);
    endfunction

    task body();
        logic [31:0] prog[];
        logic [31:0] pc_val;
        logic [31:0] gprs[32];
        apb3_write_gpr_seq wr_gpr;
        apb3_read_gpr_seq rd_gpr;

        `uvm_info("DBG_VSEQ", "Running Debug interface test", UVM_LOW)

        // Generate simple program
        instr_gen.max_instructions = 20;
        instr_gen.generate_program();
        instr_gen.get_program(prog);
        env.load_program(prog);

        // Test halt/resume
        `uvm_info("DBG_VSEQ", "Testing halt/resume", UVM_MEDIUM)
        resume_cpu();
        #500ns;
        halt_cpu();
        read_pc(pc_val);
        `uvm_info("DBG_VSEQ", $sformatf("Halted at PC=0x%08h", pc_val), UVM_MEDIUM)

        // Test single step
        `uvm_info("DBG_VSEQ", "Testing single step", UVM_MEDIUM)
        for (int i = 0; i < 5; i++) begin
            step_cpu();
            read_pc(pc_val);
            `uvm_info("DBG_VSEQ", $sformatf("Step %0d: PC=0x%08h", i, pc_val), UVM_MEDIUM)
        end

        // Test GPR write/read
        `uvm_info("DBG_VSEQ", "Testing GPR access", UVM_MEDIUM)
        wr_gpr = apb3_write_gpr_seq::type_id::create("wr_gpr");
        rd_gpr = apb3_read_gpr_seq::type_id::create("rd_gpr");

        for (int i = 1; i < 32; i++) begin
            wr_gpr.reg_num = i;
            wr_gpr.value = 32'hDEAD_0000 + i;
            wr_gpr.start(p_sequencer.apb_sqr);
        end

        read_all_gprs(gprs);
        for (int i = 1; i < 32; i++) begin
            if (gprs[i] != (32'hDEAD_0000 + i))
                `uvm_error("DBG_VSEQ", $sformatf("GPR[%0d] mismatch: exp=0x%08h, got=0x%08h",
                                                 i, 32'hDEAD_0000 + i, gprs[i]))
        end

        // Test breakpoints
        `uvm_info("DBG_VSEQ", "Testing breakpoints", UVM_MEDIUM)
        set_breakpoint(0, 32'h0000_0010, 1);  // Breakpoint at addr 0x10
        resume_cpu();
        wait_for_halt(5000);
        read_pc(pc_val);
        if (pc_val == 32'h0000_0010)
            `uvm_info("DBG_VSEQ", "Breakpoint hit correctly", UVM_MEDIUM)
        else
            `uvm_warning("DBG_VSEQ", $sformatf("Breakpoint may not have hit: PC=0x%08h", pc_val))

        `uvm_info("DBG_VSEQ", "Debug interface test complete", UVM_LOW)
    endtask

endclass

//-----------------------------------------------------------------------------
// Latency Stress Test Sequence
//-----------------------------------------------------------------------------
class rv32i_latency_stress_vseq extends rv32i_base_vseq;

    `uvm_object_utils(rv32i_latency_stress_vseq)

    function new(string name = "rv32i_latency_stress_vseq");
        super.new(name);
    endfunction

    task body();
        logic [31:0] prog[];
        logic [31:0] dut_pc;
        logic [31:0] dut_gprs[32];
        int latencies[] = '{0, 1, 2, 5, 10};

        `uvm_info("LAT_VSEQ", "Running latency stress test", UVM_LOW)

        // Generate program
        instr_gen.max_instructions = 40;
        instr_gen.generate_program();
        instr_gen.get_program(prog);

        foreach (latencies[i]) begin
            `uvm_info("LAT_VSEQ", $sformatf("Testing with latency=%0d", latencies[i]), UVM_MEDIUM)

            // Set memory latency
            env.set_memory_latency(latencies[i]);

            // Load and run
            env.load_program(prog);
            env.scoreboard.ref_model.reset();
            env.scoreboard.load_program(prog);
            env.scoreboard.run_reference();

            resume_cpu();
            wait_for_halt(20000);

            read_pc(dut_pc);
            read_all_gprs(dut_gprs);
            env.scoreboard.compare_registers(dut_gprs, dut_pc);

            #100ns;
        end

        // Test with random latency
        `uvm_info("LAT_VSEQ", "Testing with random latency 0-5", UVM_MEDIUM)
        env.set_random_memory_latency(0, 5);

        env.load_program(prog);
        env.scoreboard.ref_model.reset();
        env.scoreboard.load_program(prog);
        env.scoreboard.run_reference();

        resume_cpu();
        wait_for_halt(20000);

        read_pc(dut_pc);
        read_all_gprs(dut_gprs);
        env.scoreboard.compare_registers(dut_gprs, dut_pc);

        `uvm_info("LAT_VSEQ", "Latency stress test complete", UVM_LOW)
    endtask

endclass
