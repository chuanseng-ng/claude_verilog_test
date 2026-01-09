//-----------------------------------------------------------------------------
// APB3 Debug Sequences
// Common sequences for debug interface operations
//-----------------------------------------------------------------------------

import rv32i_pkg::*;

//-----------------------------------------------------------------------------
// Base APB3 Sequence
//-----------------------------------------------------------------------------
class apb3_base_seq extends uvm_sequence #(apb3_seq_item);

    `uvm_object_utils(apb3_base_seq)

    function new(string name = "apb3_base_seq");
        super.new(name);
    endfunction

    // Helper task: Write to register
    task apb_write(input bit [11:0] addr, input bit [31:0] data);
        apb3_seq_item txn = apb3_seq_item::type_id::create("txn");
        start_item(txn);
        txn.is_write = 1;
        txn.addr     = addr;
        txn.data     = data;
        finish_item(txn);
    endtask

    // Helper task: Read from register
    task apb_read(input bit [11:0] addr, output bit [31:0] data);
        apb3_seq_item txn = apb3_seq_item::type_id::create("txn");
        start_item(txn);
        txn.is_write = 0;
        txn.addr     = addr;
        finish_item(txn);
        data = txn.data;
    endtask

endclass

//-----------------------------------------------------------------------------
// Halt CPU Sequence
//-----------------------------------------------------------------------------
class apb3_halt_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_halt_seq)

    int timeout_cycles = 1000;

    function new(string name = "apb3_halt_seq");
        super.new(name);
    endfunction

    task body();
        bit [31:0] status;
        int cycles = 0;

        // Send halt request
        apb_write(DBG_CTRL_ADDR, 32'h0000_0001);

        // Poll for halted status
        do begin
            apb_read(DBG_STATUS_ADDR, status);
            cycles++;
            if (cycles >= timeout_cycles) begin
                `uvm_error("HALT_SEQ", "Timeout waiting for CPU to halt")
                return;
            end
        end while (!(status & 32'h0000_0001));

        `uvm_info("HALT_SEQ", "CPU halted successfully", UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Resume CPU Sequence
//-----------------------------------------------------------------------------
class apb3_resume_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_resume_seq)

    function new(string name = "apb3_resume_seq");
        super.new(name);
    endfunction

    task body();
        apb_write(DBG_CTRL_ADDR, 32'h0000_0002);
        `uvm_info("RESUME_SEQ", "CPU resume requested", UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Single Step Sequence
//-----------------------------------------------------------------------------
class apb3_step_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_step_seq)

    int timeout_cycles = 100;

    function new(string name = "apb3_step_seq");
        super.new(name);
    endfunction

    task body();
        bit [31:0] status;
        int cycles = 0;

        // Send step request
        apb_write(DBG_CTRL_ADDR, 32'h0000_0004);

        // Wait for step complete (halted again)
        do begin
            apb_read(DBG_STATUS_ADDR, status);
            cycles++;
            if (cycles >= timeout_cycles) begin
                `uvm_error("STEP_SEQ", "Timeout waiting for step complete")
                return;
            end
        end while (!(status & 32'h0000_0001));

        `uvm_info("STEP_SEQ", "Single step completed", UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Read PC Sequence
//-----------------------------------------------------------------------------
class apb3_read_pc_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_read_pc_seq)

    bit [31:0] pc;

    function new(string name = "apb3_read_pc_seq");
        super.new(name);
    endfunction

    task body();
        apb_read(DBG_PC_ADDR, pc);
        `uvm_info("READ_PC_SEQ", $sformatf("PC = 0x%08h", pc), UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Write PC Sequence
//-----------------------------------------------------------------------------
class apb3_write_pc_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_write_pc_seq)

    bit [31:0] pc;

    function new(string name = "apb3_write_pc_seq");
        super.new(name);
    endfunction

    task body();
        apb_write(DBG_PC_ADDR, pc);
        `uvm_info("WRITE_PC_SEQ", $sformatf("PC <- 0x%08h", pc), UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Read GPR Sequence
//-----------------------------------------------------------------------------
class apb3_read_gpr_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_read_gpr_seq)

    int reg_num;
    bit [31:0] value;

    function new(string name = "apb3_read_gpr_seq");
        super.new(name);
    endfunction

    task body();
        bit [11:0] addr = DBG_GPR_BASE_ADDR + (reg_num << 2);
        apb_read(addr, value);
        `uvm_info("READ_GPR_SEQ", $sformatf("x%0d = 0x%08h", reg_num, value), UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Write GPR Sequence
//-----------------------------------------------------------------------------
class apb3_write_gpr_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_write_gpr_seq)

    int reg_num;
    bit [31:0] value;

    function new(string name = "apb3_write_gpr_seq");
        super.new(name);
    endfunction

    task body();
        bit [11:0] addr = DBG_GPR_BASE_ADDR + (reg_num << 2);
        apb_write(addr, value);
        `uvm_info("WRITE_GPR_SEQ", $sformatf("x%0d <- 0x%08h", reg_num, value), UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Read All GPRs Sequence
//-----------------------------------------------------------------------------
class apb3_read_all_gprs_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_read_all_gprs_seq)

    bit [31:0] gprs [32];

    function new(string name = "apb3_read_all_gprs_seq");
        super.new(name);
    endfunction

    task body();
        string dump_str;

        for (int i = 0; i < 32; i++) begin
            bit [11:0] addr = DBG_GPR_BASE_ADDR + (i << 2);
            apb_read(addr, gprs[i]);
        end

        dump_str = "\n=== GPR Dump ===\n";
        for (int i = 0; i < 32; i += 4) begin
            dump_str = {dump_str, $sformatf("  x%-2d=0x%08h  x%-2d=0x%08h  x%-2d=0x%08h  x%-2d=0x%08h\n",
                        i, gprs[i], i+1, gprs[i+1], i+2, gprs[i+2], i+3, gprs[i+3])};
        end
        `uvm_info("READ_ALL_GPRS", dump_str, UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Set Breakpoint Sequence
//-----------------------------------------------------------------------------
class apb3_set_breakpoint_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_set_breakpoint_seq)

    int bp_num;           // 0 or 1
    bit [31:0] bp_addr;
    bit enable = 1;

    function new(string name = "apb3_set_breakpoint_seq");
        super.new(name);
    endfunction

    task body();
        bit [11:0] addr_reg, ctrl_reg;

        if (bp_num == 0) begin
            addr_reg = DBG_BP0_ADDR;
            ctrl_reg = DBG_BP0_CTRL_ADDR;
        end else begin
            addr_reg = DBG_BP1_ADDR;
            ctrl_reg = DBG_BP1_CTRL_ADDR;
        end

        apb_write(addr_reg, bp_addr);
        apb_write(ctrl_reg, {31'h0, enable});
        `uvm_info("SET_BP_SEQ", $sformatf("Breakpoint %0d set at 0x%08h, enable=%b", bp_num, bp_addr, enable), UVM_MEDIUM)
    endtask

endclass

//-----------------------------------------------------------------------------
// Wait for Halt Sequence
//-----------------------------------------------------------------------------
class apb3_wait_halt_seq extends apb3_base_seq;

    `uvm_object_utils(apb3_wait_halt_seq)

    int timeout_cycles = 10000;
    bit [3:0] halt_cause;
    bit timed_out = 0;

    function new(string name = "apb3_wait_halt_seq");
        super.new(name);
    endfunction

    task body();
        bit [31:0] status;
        int cycles = 0;

        do begin
            apb_read(DBG_STATUS_ADDR, status);
            cycles++;
            if (cycles >= timeout_cycles) begin
                `uvm_warning("WAIT_HALT_SEQ", "Timeout waiting for halt")
                timed_out = 1;
                return;
            end
        end while (!(status & 32'h0000_0001));

        halt_cause = status[7:4];
        `uvm_info("WAIT_HALT_SEQ", $sformatf("CPU halted, cause=%0d", halt_cause), UVM_MEDIUM)
    endtask

endclass
