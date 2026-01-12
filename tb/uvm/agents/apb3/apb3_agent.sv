//-----------------------------------------------------------------------------
// APB3 Master Agent
// Contains driver, monitor, and sequencer for APB3 debug interface
//-----------------------------------------------------------------------------

class apb3_agent extends uvm_agent;

    `uvm_component_utils(apb3_agent)

    //-------------------------------------------------------------------------
    // Agent Components
    //-------------------------------------------------------------------------
    apb3_master_driver driver;
    apb3_monitor       monitor;
    uvm_sequencer #(apb3_seq_item) sequencer;

    //-------------------------------------------------------------------------
    // Analysis Port
    //-------------------------------------------------------------------------
    uvm_analysis_port #(apb3_seq_item) ap;

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
        monitor = apb3_monitor::type_id::create("monitor", this);

        // Build driver and sequencer if active
        if (get_is_active() == UVM_ACTIVE) begin
            driver    = apb3_master_driver::type_id::create("driver", this);
            sequencer = uvm_sequencer#(apb3_seq_item)::type_id::create("sequencer", this);
        end
    endfunction

    //-------------------------------------------------------------------------
    // Connect Phase
    //-------------------------------------------------------------------------
    function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);

        // Connect analysis port
        ap = monitor.ap;

        // Connect driver to sequencer if active
        if (get_is_active() == UVM_ACTIVE) begin
            driver.seq_item_port.connect(sequencer.seq_item_export);
        end
    endfunction

endclass
