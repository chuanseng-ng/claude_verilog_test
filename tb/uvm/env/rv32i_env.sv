//-----------------------------------------------------------------------------
// RV32I UVM Environment
// Top-level environment containing all agents, scoreboard, and coverage
//-----------------------------------------------------------------------------

class rv32i_env extends uvm_env;

    `uvm_component_utils(rv32i_env)

    //-------------------------------------------------------------------------
    // Agents
    //-------------------------------------------------------------------------
    axi4lite_agent  axi_agent;   // AXI4-Lite slave agent (memory)
    apb3_agent      apb_agent;   // APB3 master agent (debug)

    //-------------------------------------------------------------------------
    // Scoreboard and Coverage
    //-------------------------------------------------------------------------
    rv32i_scoreboard scoreboard;
    rv32i_coverage   coverage;

    //-------------------------------------------------------------------------
    // Virtual Sequencer
    //-------------------------------------------------------------------------
    rv32i_virtual_sequencer v_sqr;

    //-------------------------------------------------------------------------
    // Configuration
    //-------------------------------------------------------------------------
    bit has_scoreboard = 1;
    bit has_coverage   = 1;

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

        // Create agents
        axi_agent = axi4lite_agent::type_id::create("axi_agent", this);
        apb_agent = apb3_agent::type_id::create("apb_agent", this);

        // Set agents to active mode
        axi_agent.set_is_active(UVM_ACTIVE);
        apb_agent.set_is_active(UVM_ACTIVE);

        // Create scoreboard
        if (has_scoreboard)
            scoreboard = rv32i_scoreboard::type_id::create("scoreboard", this);

        // Create coverage
        if (has_coverage)
            coverage = rv32i_coverage::type_id::create("coverage", this);

        // Create virtual sequencer
        v_sqr = rv32i_virtual_sequencer::type_id::create("v_sqr", this);
    endfunction

    //-------------------------------------------------------------------------
    // Connect Phase
    //-------------------------------------------------------------------------
    function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);

        // Connect virtual sequencer
        v_sqr.apb_sqr = apb_agent.sequencer;

        // Connect scoreboard
        if (has_scoreboard) begin
            axi_agent.read_ap.connect(scoreboard.axi_read_export);
            axi_agent.write_ap.connect(scoreboard.axi_write_export);
            apb_agent.ap.connect(scoreboard.apb_export);
        end

        // Connect coverage
        if (has_coverage) begin
            axi_agent.read_ap.connect(coverage.analysis_export);
        end
    endfunction

    //-------------------------------------------------------------------------
    // Convenience Methods
    //-------------------------------------------------------------------------

    // Load program into memory agent
    function void load_program(logic [31:0] prog[], int start_addr = 0);
        axi_agent.load_program(prog, start_addr);
        if (has_scoreboard)
            scoreboard.load_program(prog, start_addr);
    endfunction

    // Load hex file
    function void load_hex(string filename);
        axi_agent.load_hex(filename);
    endfunction

    // Set memory latency
    function void set_memory_latency(int lat);
        axi_agent.set_latency(lat);
    endfunction

    // Enable random memory latency
    function void set_random_memory_latency(int min_lat, int max_lat);
        axi_agent.set_random_latency(min_lat, max_lat);
    endfunction

endclass

//-----------------------------------------------------------------------------
// Virtual Sequencer
//-----------------------------------------------------------------------------
class rv32i_virtual_sequencer extends uvm_sequencer;

    `uvm_component_utils(rv32i_virtual_sequencer)

    // Sub-sequencers
    uvm_sequencer #(apb3_seq_item) apb_sqr;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

endclass
