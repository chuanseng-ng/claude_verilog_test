//-----------------------------------------------------------------------------
// AXI4-Lite Slave Driver
// Responds to AXI4-Lite master requests (CPU memory accesses)
// Implements a simple memory model for instruction/data storage
//-----------------------------------------------------------------------------

class axi4lite_slave_driver extends uvm_driver #(axi4lite_seq_item);

    `uvm_component_utils(axi4lite_slave_driver)

    //-------------------------------------------------------------------------
    // Virtual Interface
    //-------------------------------------------------------------------------
    virtual axi4lite_if.slave_drv vif;

    //-------------------------------------------------------------------------
    // Memory Model
    //-------------------------------------------------------------------------
    bit [31:0] memory [int];  // Associative array for memory
    int unsigned mem_size;
    int unsigned latency;     // Response latency in cycles

    //-------------------------------------------------------------------------
    // Configuration
    //-------------------------------------------------------------------------
    bit random_latency = 0;   // Enable random response latency
    int min_latency = 0;
    int max_latency = 5;

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name, uvm_component parent);
        super.new(name, parent);
        mem_size = 65536;  // Default 64KB
        latency = 0;       // Default zero latency
    endfunction

    //-------------------------------------------------------------------------
    // Build Phase
    //-------------------------------------------------------------------------
    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if (!uvm_config_db#(virtual axi4lite_if.slave_drv)::get(this, "", "vif", vif))
            `uvm_fatal("NOVIF", "Virtual interface not set for AXI slave driver")
    endfunction

    //-------------------------------------------------------------------------
    // Run Phase - Main Driver Loop
    //-------------------------------------------------------------------------
    task run_phase(uvm_phase phase);
        // Initialize interface signals
        reset_interface();

        // Wait for reset to complete
        @(posedge vif.rst_n);
        repeat(2) @(posedge vif.clk);

        // Run read and write handlers in parallel
        fork
            handle_read_transactions();
            handle_write_transactions();
        join
    endtask

    //-------------------------------------------------------------------------
    // Reset Interface Signals
    //-------------------------------------------------------------------------
    task reset_interface();
        vif.slv_drv_cb.awready <= 1'b0;
        vif.slv_drv_cb.wready  <= 1'b0;
        vif.slv_drv_cb.bvalid  <= 1'b0;
        vif.slv_drv_cb.bresp   <= 2'b00;
        vif.slv_drv_cb.arready <= 1'b0;
        vif.slv_drv_cb.rvalid  <= 1'b0;
        vif.slv_drv_cb.rdata   <= 32'h0;
        vif.slv_drv_cb.rresp   <= 2'b00;
    endtask

    //-------------------------------------------------------------------------
    // Handle Read Transactions
    //-------------------------------------------------------------------------
    task handle_read_transactions();
        logic [31:0] addr;
        logic [31:0] data;
        int delay;

        forever begin
            @(vif.slv_drv_cb);

            // Check for read address valid
            if (vif.slv_drv_cb.arvalid) begin
                addr = vif.slv_drv_cb.araddr;

                // Accept address
                vif.slv_drv_cb.arready <= 1'b1;
                @(vif.slv_drv_cb);
                vif.slv_drv_cb.arready <= 1'b0;

                // Calculate latency
                delay = get_latency();
                repeat(delay) @(vif.slv_drv_cb);

                // Read from memory
                data = read_memory(addr);

                // Send read response
                vif.slv_drv_cb.rdata  <= data;
                vif.slv_drv_cb.rresp  <= 2'b00;  // OKAY
                vif.slv_drv_cb.rvalid <= 1'b1;

                // Wait for ready
                while (!vif.slv_drv_cb.rready) @(vif.slv_drv_cb);
                @(vif.slv_drv_cb);
                vif.slv_drv_cb.rvalid <= 1'b0;

                `uvm_info("AXI_SLV_DRV", $sformatf("READ addr=0x%08h data=0x%08h", addr, data), UVM_HIGH)
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // Handle Write Transactions
    //-------------------------------------------------------------------------
    task handle_write_transactions();
        logic [31:0] addr;
        logic [31:0] data;
        logic [3:0]  strb;
        bit got_addr, got_data;
        int delay;

        forever begin
            got_addr = 0;
            got_data = 0;

            // Handle address and data phases (can come in any order)
            while (!got_addr || !got_data) begin
                @(vif.slv_drv_cb);

                if (!got_addr && vif.slv_drv_cb.awvalid) begin
                    addr = vif.slv_drv_cb.awaddr;
                    vif.slv_drv_cb.awready <= 1'b1;
                    @(vif.slv_drv_cb);
                    vif.slv_drv_cb.awready <= 1'b0;
                    got_addr = 1;
                end

                if (!got_data && vif.slv_drv_cb.wvalid) begin
                    data = vif.slv_drv_cb.wdata;
                    strb = vif.slv_drv_cb.wstrb;
                    vif.slv_drv_cb.wready <= 1'b1;
                    @(vif.slv_drv_cb);
                    vif.slv_drv_cb.wready <= 1'b0;
                    got_data = 1;
                end
            end

            // Calculate latency
            delay = get_latency();
            repeat(delay) @(vif.slv_drv_cb);

            // Write to memory
            write_memory(addr, data, strb);

            // Send write response
            vif.slv_drv_cb.bresp  <= 2'b00;  // OKAY
            vif.slv_drv_cb.bvalid <= 1'b1;

            // Wait for ready
            while (!vif.slv_drv_cb.bready) @(vif.slv_drv_cb);
            @(vif.slv_drv_cb);
            vif.slv_drv_cb.bvalid <= 1'b0;

            `uvm_info("AXI_SLV_DRV", $sformatf("WRITE addr=0x%08h data=0x%08h strb=%b", addr, data, strb), UVM_HIGH)
        end
    endtask

    //-------------------------------------------------------------------------
    // Memory Access Functions
    //-------------------------------------------------------------------------

    function logic [31:0] read_memory(logic [31:0] addr);
        int word_addr = addr >> 2;
        if (memory.exists(word_addr))
            return memory[word_addr];
        else
            return 32'h0;  // Uninitialized memory reads as 0
    endfunction

    function void write_memory(logic [31:0] addr, logic [31:0] data, logic [3:0] strb);
        int word_addr = addr >> 2;
        logic [31:0] old_data;

        if (memory.exists(word_addr))
            old_data = memory[word_addr];
        else
            old_data = 32'h0;

        // Apply byte strobes
        if (strb[0]) old_data[7:0]   = data[7:0];
        if (strb[1]) old_data[15:8]  = data[15:8];
        if (strb[2]) old_data[23:16] = data[23:16];
        if (strb[3]) old_data[31:24] = data[31:24];

        memory[word_addr] = old_data;
    endfunction

    //-------------------------------------------------------------------------
    // Memory Load/Dump Functions
    //-------------------------------------------------------------------------

    // Load hex file into memory
    function void load_hex(string filename);
        int fd;
        string line;
        logic [31:0] data;
        int addr = 0;

        fd = $fopen(filename, "r");
        if (fd == 0) begin
            `uvm_error("AXI_SLV_DRV", $sformatf("Cannot open file: %s", filename))
            return;
        end

        while (!$feof(fd)) begin
            if ($fgets(line, fd)) begin
                if ($sscanf(line, "%h", data) == 1) begin
                    memory[addr >> 2] = data;
                    addr += 4;
                end
            end
        end

        $fclose(fd);
        `uvm_info("AXI_SLV_DRV", $sformatf("Loaded %0d words from %s", addr/4, filename), UVM_MEDIUM)
    endfunction

    // Load binary array directly
    function void load_program(logic [31:0] program_data[], int start_addr = 0);
        foreach (program_data[i]) begin
            memory[(start_addr >> 2) + i] = program_data[i];
        end
        `uvm_info("AXI_SLV_DRV", $sformatf("Loaded %0d instructions at 0x%08h", program_data.size(), start_addr), UVM_MEDIUM)
    endfunction

    // Dump memory contents
    function void dump_memory(int start_addr, int num_words);
        string dump_str;
        dump_str = $sformatf("\n=== Memory Dump (0x%08h - 0x%08h) ===\n", start_addr, start_addr + (num_words-1)*4);
        for (int i = 0; i < num_words; i++) begin
            int addr = start_addr + i*4;
            dump_str = {dump_str, $sformatf("  0x%08h: 0x%08h\n", addr, read_memory(addr))};
        end
        `uvm_info("AXI_SLV_DRV", dump_str, UVM_MEDIUM)
    endfunction

    //-------------------------------------------------------------------------
    // Latency Control
    //-------------------------------------------------------------------------

    function int get_latency();
        if (random_latency)
            return $urandom_range(min_latency, max_latency);
        else
            return latency;
    endfunction

    function void set_latency(int lat);
        latency = lat;
        random_latency = 0;
    endfunction

    function void set_random_latency(int min_lat, int max_lat);
        min_latency = min_lat;
        max_latency = max_lat;
        random_latency = 1;
    endfunction

endclass
