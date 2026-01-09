//-----------------------------------------------------------------------------
// AXI4-Lite Monitor
// Monitors AXI4-Lite transactions and broadcasts to analysis ports
//-----------------------------------------------------------------------------

class axi4lite_monitor extends uvm_monitor;

    `uvm_component_utils(axi4lite_monitor)

    //-------------------------------------------------------------------------
    // Virtual Interface
    //-------------------------------------------------------------------------
    virtual axi4lite_if.slave_mon vif;

    //-------------------------------------------------------------------------
    // Analysis Ports
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
        read_ap  = new("read_ap", this);
        write_ap = new("write_ap", this);
        if (!uvm_config_db#(virtual axi4lite_if.slave_mon)::get(this, "", "vif", vif))
            `uvm_fatal("NOVIF", "Virtual interface not set for AXI monitor")
    endfunction

    //-------------------------------------------------------------------------
    // Run Phase
    //-------------------------------------------------------------------------
    task run_phase(uvm_phase phase);
        // Wait for reset
        @(posedge vif.rst_n);
        repeat(2) @(posedge vif.clk);

        fork
            monitor_reads();
            monitor_writes();
        join
    endtask

    //-------------------------------------------------------------------------
    // Monitor Read Transactions
    //-------------------------------------------------------------------------
    task monitor_reads();
        axi4lite_seq_item txn;
        logic [31:0] addr;

        forever begin
            @(vif.slv_mon_cb);

            // Wait for read address handshake
            if (vif.slv_mon_cb.arvalid && vif.slv_mon_cb.arready) begin
                addr = vif.slv_mon_cb.araddr;

                // Wait for read data handshake
                do @(vif.slv_mon_cb);
                while (!(vif.slv_mon_cb.rvalid && vif.slv_mon_cb.rready));

                // Create transaction
                txn = axi4lite_seq_item::type_id::create("rd_txn");
                txn.is_write = 0;
                txn.addr     = addr;
                txn.data     = vif.slv_mon_cb.rdata;
                txn.resp     = vif.slv_mon_cb.rresp;
                txn.strb     = 4'b1111;

                `uvm_info("AXI_MON", $sformatf("READ  %s", txn.convert2string()), UVM_HIGH)
                read_ap.write(txn);
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // Monitor Write Transactions
    //-------------------------------------------------------------------------
    task monitor_writes();
        axi4lite_seq_item txn;
        logic [31:0] addr;
        logic [31:0] data;
        logic [3:0]  strb;
        bit got_addr, got_data;

        forever begin
            got_addr = 0;
            got_data = 0;

            // Collect address and data (can come in any order)
            while (!got_addr || !got_data) begin
                @(vif.slv_mon_cb);

                if (!got_addr && vif.slv_mon_cb.awvalid && vif.slv_mon_cb.awready) begin
                    addr = vif.slv_mon_cb.awaddr;
                    got_addr = 1;
                end

                if (!got_data && vif.slv_mon_cb.wvalid && vif.slv_mon_cb.wready) begin
                    data = vif.slv_mon_cb.wdata;
                    strb = vif.slv_mon_cb.wstrb;
                    got_data = 1;
                end
            end

            // Wait for write response handshake
            do @(vif.slv_mon_cb);
            while (!(vif.slv_mon_cb.bvalid && vif.slv_mon_cb.bready));

            // Create transaction
            txn = axi4lite_seq_item::type_id::create("wr_txn");
            txn.is_write = 1;
            txn.addr     = addr;
            txn.data     = data;
            txn.strb     = strb;
            txn.resp     = vif.slv_mon_cb.bresp;

            `uvm_info("AXI_MON", $sformatf("WRITE %s", txn.convert2string()), UVM_HIGH)
            write_ap.write(txn);
        end
    endtask

endclass
