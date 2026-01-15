//-----------------------------------------------------------------------------
// APB3 Sequence Item
// Transaction class for APB3 debug interface
//-----------------------------------------------------------------------------

class apb3_seq_item extends uvm_sequence_item;

    //-------------------------------------------------------------------------
    // Transaction Fields
    //-------------------------------------------------------------------------
    rand bit           is_write;
    rand bit [11:0]    addr;
    rand bit [31:0]    data;       // Write data or Read data
         bit           slverr;     // Slave error response

    //-------------------------------------------------------------------------
    // Constraints
    //-------------------------------------------------------------------------

    // Address alignment
    constraint addr_align_c {
        addr[1:0] == 2'b00;
    }

    // Valid debug register addresses
    constraint valid_addr_c {
        addr inside {
            12'h000,  // DBG_CTRL
            12'h004,  // DBG_STATUS
            12'h008,  // DBG_PC
            12'h00C,  // DBG_INSTR
            [12'h010:12'h08C],  // GPR[0:31]
            12'h100,  // BP0_ADDR
            12'h104,  // BP0_CTRL
            12'h108,  // BP1_ADDR
            12'h10C   // BP1_CTRL
        };
    }

    //-------------------------------------------------------------------------
    // UVM Factory Registration
    //-------------------------------------------------------------------------
    `uvm_object_utils_begin(apb3_seq_item)
        `uvm_field_int(is_write, UVM_ALL_ON)
        `uvm_field_int(addr, UVM_ALL_ON | UVM_HEX)
        `uvm_field_int(data, UVM_ALL_ON | UVM_HEX)
        `uvm_field_int(slverr, UVM_ALL_ON)
    `uvm_object_utils_end

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name = "apb3_seq_item");
        super.new(name);
    endfunction

    //-------------------------------------------------------------------------
    // Convert to String
    //-------------------------------------------------------------------------
    function string convert2string();
        string reg_name;
        case (addr)
            12'h000: reg_name = "DBG_CTRL";
            12'h004: reg_name = "DBG_STATUS";
            12'h008: reg_name = "DBG_PC";
            12'h00C: reg_name = "DBG_INSTR";
            12'h100: reg_name = "BP0_ADDR";
            12'h104: reg_name = "BP0_CTRL";
            12'h108: reg_name = "BP1_ADDR";
            12'h10C: reg_name = "BP1_CTRL";
            default: begin
                if (addr >= 12'h010 && addr <= 12'h08C)
                    reg_name = $sformatf("GPR[%0d]", (addr - 12'h010) >> 2);
                else
                    reg_name = "UNKNOWN";
            end
        endcase
        return $sformatf("%s %s (0x%03h) = 0x%08h %s",
                        is_write ? "WR" : "RD",
                        reg_name, addr, data,
                        slverr ? "[ERROR]" : "");
    endfunction

endclass
