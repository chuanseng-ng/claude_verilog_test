//-----------------------------------------------------------------------------
// APB3 Master Driver
// Drives debug transactions to the CPU's APB3 slave interface
//-----------------------------------------------------------------------------

class apb3_master_driver extends uvm_driver #(apb3_seq_item);

    `uvm_component_utils(apb3_master_driver)

    //-------------------------------------------------------------------------
    // Virtual Interface
    //-------------------------------------------------------------------------
    virtual apb3_if.master_drv vif;

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
        if (!uvm_config_db#(virtual apb3_if.master_drv)::get(this, "", "vif", vif))
            `uvm_fatal("NOVIF", "Virtual interface not set for APB master driver")
    endfunction

    //-------------------------------------------------------------------------
    // Run Phase
    //-------------------------------------------------------------------------
    task run_phase(uvm_phase phase);
        apb3_seq_item txn;

        // Initialize interface
        reset_interface();

        // Wait for reset
        @(posedge vif.rst_n);
        repeat(2) @(posedge vif.clk);

        forever begin
            seq_item_port.get_next_item(txn);

            if (txn.is_write)
                do_write(txn);
            else
                do_read(txn);

            seq_item_port.item_done();
        end
    endtask

    //-------------------------------------------------------------------------
    // Reset Interface
    //-------------------------------------------------------------------------
    task reset_interface();
        vif.mst_drv_cb.paddr   <= '0;
        vif.mst_drv_cb.psel    <= 1'b0;
        vif.mst_drv_cb.penable <= 1'b0;
        vif.mst_drv_cb.pwrite  <= 1'b0;
        vif.mst_drv_cb.pwdata  <= '0;
    endtask

    //-------------------------------------------------------------------------
    // APB Write Transaction
    //-------------------------------------------------------------------------
    task do_write(apb3_seq_item txn);
        // Setup phase
        @(vif.mst_drv_cb);
        vif.mst_drv_cb.paddr  <= txn.addr;
        vif.mst_drv_cb.pwrite <= 1'b1;
        vif.mst_drv_cb.pwdata <= txn.data;
        vif.mst_drv_cb.psel   <= 1'b1;

        // Access phase
        @(vif.mst_drv_cb);
        vif.mst_drv_cb.penable <= 1'b1;

        // Wait for ready
        do @(vif.mst_drv_cb);
        while (!vif.mst_drv_cb.pready);

        // Capture response
        txn.slverr = vif.mst_drv_cb.pslverr;

        // Return to idle
        vif.mst_drv_cb.psel    <= 1'b0;
        vif.mst_drv_cb.penable <= 1'b0;

        `uvm_info("APB_DRV", $sformatf("WRITE %s", txn.convert2string()), UVM_HIGH)
    endtask

    //-------------------------------------------------------------------------
    // APB Read Transaction
    //-------------------------------------------------------------------------
    task do_read(apb3_seq_item txn);
        // Setup phase
        @(vif.mst_drv_cb);
        vif.mst_drv_cb.paddr  <= txn.addr;
        vif.mst_drv_cb.pwrite <= 1'b0;
        vif.mst_drv_cb.psel   <= 1'b1;

        // Access phase
        @(vif.mst_drv_cb);
        vif.mst_drv_cb.penable <= 1'b1;

        // Wait for ready
        do @(vif.mst_drv_cb);
        while (!vif.mst_drv_cb.pready);

        // Capture data and response
        txn.data   = vif.mst_drv_cb.prdata;
        txn.slverr = vif.mst_drv_cb.pslverr;

        // Return to idle
        vif.mst_drv_cb.psel    <= 1'b0;
        vif.mst_drv_cb.penable <= 1'b0;

        `uvm_info("APB_DRV", $sformatf("READ  %s", txn.convert2string()), UVM_HIGH)
    endtask

endclass
