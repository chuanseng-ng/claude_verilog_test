//-----------------------------------------------------------------------------
// APB3 Monitor
// Monitors APB3 debug transactions
//-----------------------------------------------------------------------------

class apb3_monitor extends uvm_monitor;

    `uvm_component_utils(apb3_monitor)

    //-------------------------------------------------------------------------
    // Virtual Interface
    //-------------------------------------------------------------------------
    virtual apb3_if.master_mon vif;

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
        ap = new("ap", this);
        if (!uvm_config_db#(virtual apb3_if.master_mon)::get(this, "", "vif", vif))
            `uvm_fatal("NOVIF", "Virtual interface not set for APB monitor")
    endfunction

    //-------------------------------------------------------------------------
    // Run Phase
    //-------------------------------------------------------------------------
    task run_phase(uvm_phase phase);
        apb3_seq_item txn;

        // Wait for reset
        @(posedge vif.rst_n);
        repeat(2) @(posedge vif.clk);

        forever begin
            @(vif.mst_mon_cb);

            // Detect setup phase (psel asserted, penable not yet)
            if (vif.mst_mon_cb.psel && !vif.mst_mon_cb.penable) begin
                txn = apb3_seq_item::type_id::create("apb_txn");
                txn.addr     = vif.mst_mon_cb.paddr;
                txn.is_write = vif.mst_mon_cb.pwrite;
                if (txn.is_write)
                    txn.data = vif.mst_mon_cb.pwdata;

                // Wait for access phase completion
                do @(vif.mst_mon_cb);
                while (!(vif.mst_mon_cb.psel && vif.mst_mon_cb.penable && vif.mst_mon_cb.pready));

                if (!txn.is_write)
                    txn.data = vif.mst_mon_cb.prdata;
                txn.slverr = vif.mst_mon_cb.pslverr;

                `uvm_info("APB_MON", $sformatf("%s", txn.convert2string()), UVM_HIGH)
                ap.write(txn);
            end
        end
    endtask

endclass
