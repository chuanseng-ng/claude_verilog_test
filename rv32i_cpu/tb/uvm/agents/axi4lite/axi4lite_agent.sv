//-----------------------------------------------------------------------------
// AXI4-Lite Slave Agent
// Contains driver, monitor, and sequencer for AXI4-Lite slave
//-----------------------------------------------------------------------------

class axi4lite_agent extends uvm_agent;

    `uvm_component_utils(axi4lite_agent)

    //-------------------------------------------------------------------------
    // Agent Components
    //-------------------------------------------------------------------------
    axi4lite_slave_driver driver;
    axi4lite_monitor      monitor;
    uvm_sequencer #(axi4lite_seq_item) sequencer;

    //-------------------------------------------------------------------------
    // Analysis Ports (from monitor)
    //-------------------------------------------------------------------------
    uvm_analysis_port #(axi4lite_seq_item) read_ap;
    uvm_analysis_port #(axi4lite_seq_item) write_ap;

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

        // Always build monitor
        monitor = axi4lite_monitor::type_id::create("monitor", this);

        // Build driver and sequencer if active
        if (get_is_active() == UVM_ACTIVE) begin
            driver    = axi4lite_slave_driver::type_id::create("driver", this);
            sequencer = uvm_sequencer#(axi4lite_seq_item)::type_id::create("sequencer", this);
        end
    endfunction

    //-------------------------------------------------------------------------
    // Connect Phase
    //-------------------------------------------------------------------------
    function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);

        // Connect analysis ports
        read_ap  = monitor.read_ap;
        write_ap = monitor.write_ap;

        // Connect driver to sequencer if active
        if (get_is_active() == UVM_ACTIVE) begin
            driver.seq_item_port.connect(sequencer.seq_item_export);
        end
    endfunction

    //-------------------------------------------------------------------------
    // Convenience Methods
    //-------------------------------------------------------------------------

    // Load program into memory
    function void load_program(logic [31:0] program_data[], int start_addr = 0);
        if (driver != null)
            driver.load_program(program_data, start_addr);
        else
            `uvm_error("AXI_AGT", "Cannot load program - driver not created (passive agent?)")
    endfunction

    // Load hex file
    function void load_hex(string filename);
        if (driver != null)
            driver.load_hex(filename);
        else
            `uvm_error("AXI_AGT", "Cannot load hex - driver not created (passive agent?)")
    endfunction

    // Read from memory model
    function logic [31:0] read_memory(logic [31:0] addr);
        if (driver != null)
            return driver.read_memory(addr);
        else begin
            `uvm_error("AXI_AGT", "Cannot read memory - driver not created (passive agent?)")
            return 32'h0;
        end
    endfunction

    // Write to memory model
    function void write_memory(logic [31:0] addr, logic [31:0] data);
        if (driver != null)
            driver.write_memory(addr, data, 4'b1111);
        else
            `uvm_error("AXI_AGT", "Cannot write memory - driver not created (passive agent?)")
    endfunction

    // Set response latency
    function void set_latency(int lat);
        if (driver != null)
            driver.set_latency(lat);
    endfunction

    // Enable random latency
    function void set_random_latency(int min_lat, int max_lat);
        if (driver != null)
            driver.set_random_latency(min_lat, max_lat);
    endfunction

    // Dump memory
    function void dump_memory(int start_addr, int num_words);
        if (driver != null)
            driver.dump_memory(start_addr, num_words);
    endfunction

endclass
