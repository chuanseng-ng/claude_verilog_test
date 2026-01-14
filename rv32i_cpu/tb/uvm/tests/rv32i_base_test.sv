//-----------------------------------------------------------------------------
// RV32I Base Test
// Base class for all RV32I UVM tests
//-----------------------------------------------------------------------------

class rv32i_base_test extends uvm_test;

    `uvm_component_utils(rv32i_base_test)

    //-------------------------------------------------------------------------
    // Environment
    //-------------------------------------------------------------------------
    rv32i_env env;

    //-------------------------------------------------------------------------
    // Configuration
    //-------------------------------------------------------------------------
    int unsigned timeout_cycles = 100000;

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    //-------------------------------------------------------------------------
    // Build Phase
    //-------------------------------------------------------------------------
    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        env = rv32i_env::type_id::create("env", this);
    endfunction

    //-------------------------------------------------------------------------
    // End of Elaboration
    //-------------------------------------------------------------------------
    function void end_of_elaboration_phase(uvm_phase phase);
        super.end_of_elaboration_phase(phase);
        uvm_top.print_topology();
    endfunction

    //-------------------------------------------------------------------------
    // Run Phase
    //-------------------------------------------------------------------------
    task run_phase(uvm_phase phase);
        phase.raise_objection(this);

        // Apply reset
        `uvm_info("TEST", "Waiting for reset...", UVM_MEDIUM)
        #100ns;

        // Run test sequence (override in derived tests)
        run_test_sequence();

        // Drain time
        #1000ns;

        phase.drop_objection(this);
    endtask

    //-------------------------------------------------------------------------
    // Test Sequence (override in derived tests)
    //-------------------------------------------------------------------------
    virtual task run_test_sequence();
        `uvm_info("TEST", "Base test - no sequence", UVM_LOW)
    endtask

    //-------------------------------------------------------------------------
    // Report Phase
    //-------------------------------------------------------------------------
    function void report_phase(uvm_phase phase);
        uvm_report_server rs;
        int error_count;

        super.report_phase(phase);

        rs = uvm_report_server::get_server();
        error_count = rs.get_severity_count(UVM_ERROR) + rs.get_severity_count(UVM_FATAL);

        if (error_count == 0) begin
            `uvm_info("TEST", "\n\n*** TEST PASSED ***\n", UVM_NONE)
        end else begin
            `uvm_info("TEST", $sformatf("\n\n*** TEST FAILED (%0d errors) ***\n", error_count), UVM_NONE)
        end
    endfunction

endclass

//-----------------------------------------------------------------------------
// Random Test
// Runs multiple iterations of random programs
//-----------------------------------------------------------------------------
class rv32i_random_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_random_test)

    int num_iterations = 10;
    int num_instructions = 50;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_random_prog_vseq vseq;
        vseq = rv32i_random_prog_vseq::type_id::create("vseq");
        vseq.env = env;
        vseq.num_iterations = num_iterations;
        vseq.num_instructions = num_instructions;
        vseq.start(env.v_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// ALU Test
//-----------------------------------------------------------------------------
class rv32i_alu_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_alu_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_alu_test_vseq vseq;
        vseq = rv32i_alu_test_vseq::type_id::create("vseq");
        vseq.env = env;
        vseq.start(env.v_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// Load/Store Test
//-----------------------------------------------------------------------------
class rv32i_loadstore_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_loadstore_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_loadstore_test_vseq vseq;
        vseq = rv32i_loadstore_test_vseq::type_id::create("vseq");
        vseq.env = env;
        vseq.start(env.v_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// Branch Test
//-----------------------------------------------------------------------------
class rv32i_branch_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_branch_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_branch_test_vseq vseq;
        vseq = rv32i_branch_test_vseq::type_id::create("vseq");
        vseq.env = env;
        vseq.start(env.v_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// Debug Interface Test
//-----------------------------------------------------------------------------
class rv32i_debug_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_debug_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_debug_test_vseq vseq;
        vseq = rv32i_debug_test_vseq::type_id::create("vseq");
        vseq.env = env;
        vseq.start(env.v_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// Latency Stress Test
//-----------------------------------------------------------------------------
class rv32i_latency_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_latency_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_latency_stress_vseq vseq;
        vseq = rv32i_latency_stress_vseq::type_id::create("vseq");
        vseq.env = env;
        vseq.start(env.v_sqr);
    endtask

endclass

//-----------------------------------------------------------------------------
// Comprehensive Test (runs all sequences)
//-----------------------------------------------------------------------------
class rv32i_comprehensive_test extends rv32i_base_test;

    `uvm_component_utils(rv32i_comprehensive_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    task run_test_sequence();
        rv32i_alu_test_vseq alu_seq;
        rv32i_loadstore_test_vseq ls_seq;
        rv32i_branch_test_vseq br_seq;
        rv32i_debug_test_vseq dbg_seq;
        rv32i_random_prog_vseq rand_seq;

        `uvm_info("TEST", "=== Running ALU Test ===", UVM_LOW)
        alu_seq = rv32i_alu_test_vseq::type_id::create("alu_seq");
        alu_seq.env = env;
        alu_seq.start(env.v_sqr);

        `uvm_info("TEST", "=== Running Load/Store Test ===", UVM_LOW)
        ls_seq = rv32i_loadstore_test_vseq::type_id::create("ls_seq");
        ls_seq.env = env;
        ls_seq.start(env.v_sqr);

        `uvm_info("TEST", "=== Running Branch Test ===", UVM_LOW)
        br_seq = rv32i_branch_test_vseq::type_id::create("br_seq");
        br_seq.env = env;
        br_seq.start(env.v_sqr);

        `uvm_info("TEST", "=== Running Debug Test ===", UVM_LOW)
        dbg_seq = rv32i_debug_test_vseq::type_id::create("dbg_seq");
        dbg_seq.env = env;
        dbg_seq.start(env.v_sqr);

        `uvm_info("TEST", "=== Running Random Test ===", UVM_LOW)
        rand_seq = rv32i_random_prog_vseq::type_id::create("rand_seq");
        rand_seq.env = env;
        rand_seq.num_iterations = 5;
        rand_seq.start(env.v_sqr);

        `uvm_info("TEST", "=== All tests complete ===", UVM_LOW)
    endtask

endclass
