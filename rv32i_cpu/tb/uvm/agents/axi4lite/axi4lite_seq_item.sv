//-----------------------------------------------------------------------------
// AXI4-Lite Sequence Item
// Transaction class for AXI4-Lite transfers
//-----------------------------------------------------------------------------

class axi4lite_seq_item extends uvm_sequence_item;

    //-------------------------------------------------------------------------
    // Transaction Fields
    //-------------------------------------------------------------------------
    rand bit           is_write;      // 1 = write, 0 = read
    rand bit [31:0]    addr;          // Transaction address
    rand bit [31:0]    data;          // Write data / Read data
    rand bit [3:0]     strb;          // Write strobe (byte enables)
    rand bit [1:0]     resp;          // Response (OKAY, SLVERR, etc.)

    // Response delay (for slave agent)
    rand int unsigned  resp_delay;    // Cycles to wait before responding

    //-------------------------------------------------------------------------
    // Constraints
    //-------------------------------------------------------------------------

    // Address alignment constraint
    constraint addr_align_c {
        addr[1:0] == 2'b00;  // Word-aligned addresses
    }

    // Default to full word strobe for writes
    constraint strb_default_c {
        soft strb == 4'b1111;
    }

    // Response delay constraint
    constraint resp_delay_c {
        resp_delay inside {[0:10]};
    }

    // Default to OKAY response
    constraint resp_default_c {
        soft resp == 2'b00;
    }

    //-------------------------------------------------------------------------
    // UVM Factory Registration
    //-------------------------------------------------------------------------
    `uvm_object_utils_begin(axi4lite_seq_item)
        `uvm_field_int(is_write, UVM_ALL_ON)
        `uvm_field_int(addr, UVM_ALL_ON | UVM_HEX)
        `uvm_field_int(data, UVM_ALL_ON | UVM_HEX)
        `uvm_field_int(strb, UVM_ALL_ON | UVM_BIN)
        `uvm_field_int(resp, UVM_ALL_ON)
        `uvm_field_int(resp_delay, UVM_ALL_ON)
    `uvm_object_utils_end

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name = "axi4lite_seq_item");
        super.new(name);
    endfunction

    //-------------------------------------------------------------------------
    // Convert to String
    //-------------------------------------------------------------------------
    function string convert2string();
        return $sformatf("%s addr=0x%08h data=0x%08h strb=%b resp=%0d delay=%0d",
                        is_write ? "WR" : "RD",
                        addr, data, strb, resp, resp_delay);
    endfunction

endclass
