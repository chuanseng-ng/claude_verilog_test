//-----------------------------------------------------------------------------
// RV32I Scoreboard
// Checks DUT behavior against reference model
//-----------------------------------------------------------------------------

// Analysis Implementation Macros - MUST be declared before class
// These are already declared in rv32i_env_pkg.sv before this file is included

class rv32i_scoreboard extends uvm_scoreboard;

    `uvm_component_utils(rv32i_scoreboard)

    //-------------------------------------------------------------------------
    // Analysis Exports
    //-------------------------------------------------------------------------
    uvm_analysis_imp_axi_read  #(axi4lite_seq_item, rv32i_scoreboard) axi_read_export;
    uvm_analysis_imp_axi_write #(axi4lite_seq_item, rv32i_scoreboard) axi_write_export;
    uvm_analysis_imp_apb       #(apb3_seq_item, rv32i_scoreboard) apb_export;

    //-------------------------------------------------------------------------
    // Reference Model
    //-------------------------------------------------------------------------
    rv32i_ref_model ref_model;

    //-------------------------------------------------------------------------
    // Transaction Tracking
    //-------------------------------------------------------------------------
    int unsigned axi_read_count;
    int unsigned axi_write_count;
    int unsigned apb_read_count;
    int unsigned apb_write_count;
    int unsigned error_count;
    int unsigned check_count;

    // Last instruction fetch address (for tracking)
    logic [31:0] last_fetch_addr;

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
        axi_read_export  = new("axi_read_export", this);
        axi_write_export = new("axi_write_export", this);
        apb_export       = new("apb_export", this);
        ref_model = rv32i_ref_model::type_id::create("ref_model", this);
    endfunction

    //-------------------------------------------------------------------------
    // Start of Simulation
    //-------------------------------------------------------------------------
    function void start_of_simulation_phase(uvm_phase phase);
        super.start_of_simulation_phase(phase);
        ref_model.reset();
        axi_read_count = 0;
        axi_write_count = 0;
        apb_read_count = 0;
        apb_write_count = 0;
        error_count = 0;
        check_count = 0;
    endfunction

    //-------------------------------------------------------------------------
    // AXI Read Analysis (Instruction Fetch or Data Load)
    //-------------------------------------------------------------------------
    function void write_axi_read(axi4lite_seq_item txn);
        axi_read_count++;
        last_fetch_addr = txn.addr;
        `uvm_info("SCBD", $sformatf("AXI RD: addr=0x%08h data=0x%08h", txn.addr, txn.data), UVM_HIGH)
    endfunction

    //-------------------------------------------------------------------------
    // AXI Write Analysis (Data Store)
    //-------------------------------------------------------------------------
    function void write_axi_write(axi4lite_seq_item txn);
        axi_write_count++;
        `uvm_info("SCBD", $sformatf("AXI WR: addr=0x%08h data=0x%08h strb=%b",
                                    txn.addr, txn.data, txn.strb), UVM_HIGH)

        // Track store in reference model
        ref_model.mem_write(txn.addr, txn.data, txn.strb);
    endfunction

    //-------------------------------------------------------------------------
    // APB Analysis (Debug Interface)
    //-------------------------------------------------------------------------
    function void write_apb(apb3_seq_item txn);
        if (txn.is_write)
            apb_write_count++;
        else
            apb_read_count++;
        `uvm_info("SCBD", $sformatf("APB %s", txn.convert2string()), UVM_HIGH)
    endfunction

    //-------------------------------------------------------------------------
    // Compare DUT Registers with Reference Model
    //-------------------------------------------------------------------------
    function void compare_registers(logic [31:0] dut_regs[32], logic [31:0] dut_pc);
        bit match;
        check_count++;
        match = ref_model.compare_state(dut_pc, dut_regs);
        if (!match)
            error_count++;
    endfunction

    //-------------------------------------------------------------------------
    // Load Program into Scoreboard Reference
    //-------------------------------------------------------------------------
    function void load_program(logic [31:0] prog[], int start_addr = 0);
        ref_model.load_program(prog, start_addr);
    endfunction

    //-------------------------------------------------------------------------
    // Run Reference Model
    //-------------------------------------------------------------------------
    function void run_reference(int max_cycles = 10000);
        ref_model.run_to_halt(max_cycles);
    endfunction

    //-------------------------------------------------------------------------
    // Report Phase
    //-------------------------------------------------------------------------
    function void report_phase(uvm_phase phase);
        string report;
        super.report_phase(phase);

        ref_model.print_stats();

        report = "\n";
        report = {report, "========================================\n"};
        report = {report, "        SCOREBOARD SUMMARY\n"};
        report = {report, "========================================\n"};
        report = {report, $sformatf("  AXI Reads:    %0d\n", axi_read_count)};
        report = {report, $sformatf("  AXI Writes:   %0d\n", axi_write_count)};
        report = {report, $sformatf("  APB Reads:    %0d\n", apb_read_count)};
        report = {report, $sformatf("  APB Writes:   %0d\n", apb_write_count)};
        report = {report, $sformatf("  Checks:       %0d\n", check_count)};
        report = {report, $sformatf("  Errors:       %0d\n", error_count)};
        report = {report, "========================================\n"};

        if (error_count == 0)
            `uvm_info("SCBD", {report, "  TEST PASSED\n"}, UVM_LOW)
        else
            `uvm_error("SCBD", {report, "  TEST FAILED\n"})
    endfunction

endclass
