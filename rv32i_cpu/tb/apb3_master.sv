// APB3 Master BFM - Bus Functional Model for debug interface testing
module apb3_master
    import rv32i_pkg::*;
(
    input  logic        clk,
    input  logic        rst_n,

    // APB3 Master Interface
    output logic [11:0] paddr,
    output logic        psel,
    output logic        penable,
    output logic        pwrite,
    output logic [31:0] pwdata,
    input  logic [31:0] prdata,
    input  logic        pready,
    input  logic        pslverr
);

    // Internal state
    logic [31:0] read_data;
    logic        transfer_done;
    logic        transfer_error;

    // Initialize outputs
    initial begin
        paddr   = '0;
        psel    = 1'b0;
        penable = 1'b0;
        pwrite  = 1'b0;
        pwdata  = '0;
        read_data = '0;
        transfer_done = 1'b0;
        transfer_error = 1'b0;
    end

    // APB Write Task
    //task automatic apb_write(
    task automatic apb_write(
        input logic [11:0] addr,
        input logic [31:0] data
    );
        // Setup phase
        @(posedge clk);
        paddr   = addr;
        pwdata  = data;
        pwrite  = 1'b1;
        psel    = 1'b1;
        penable = 1'b0;

        // Access phase
        @(posedge clk);
        penable = 1'b1;

        // Wait for ready
        do begin
            @(posedge clk);
        end while (!pready);

        // Capture error status
        transfer_error = pslverr;
        transfer_done  = 1'b1;

        // Return to idle
        psel    = 1'b0;
        penable = 1'b0;
        pwrite  = 1'b0;

        @(posedge clk);
        transfer_done = 1'b0;
    endtask

    // APB Read Task
    //task automatic apb_read(
    task automatic apb_read(
        input  logic [11:0] addr,
        output logic [31:0] data
    );
        // Setup phase
        @(posedge clk);
        paddr   = addr;
        pwrite  = 1'b0;
        psel    = 1'b1;
        penable = 1'b0;

        // Access phase
        @(posedge clk);
        penable = 1'b1;

        // Wait for ready
        do begin
            @(posedge clk);
        end while (!pready);

        // Capture data and error status
        data           = prdata;
        read_data      = prdata;
        transfer_error = pslverr;
        transfer_done  = 1'b1;

        // Return to idle
        psel    = 1'b0;
        penable = 1'b0;

        @(posedge clk);
        transfer_done = 1'b0;
    endtask

    // =========================================================================
    // Debug Helper Tasks
    // =========================================================================

    // Halt the CPU
    task automatic halt_cpu();
        logic [31:0] status;
        $display("[APB] Requesting CPU halt...");
        apb_write(DBG_CTRL_ADDR, 32'h0000_0001);  // Set halt bit

        // Wait for halt to take effect
        do begin
            apb_read(DBG_STATUS_ADDR, status);
        end while (!(status[0]));  // Wait for halted bit

        $display("[APB] CPU halted. Status: 0x%08h", status);
    endtask

    // Resume the CPU
    task automatic resume_cpu();
        $display("[APB] Resuming CPU...");
        apb_write(DBG_CTRL_ADDR, 32'h0000_0002);  // Set resume bit
    endtask

    // Single-step the CPU
    task automatic step_cpu();
        logic [31:0] status;
        $display("[APB] Single-stepping CPU...");
        apb_write(DBG_CTRL_ADDR, 32'h0000_0004);  // Set step bit

        // Wait for step to complete (CPU halts after one instruction)
        do begin
            apb_read(DBG_STATUS_ADDR, status);
        end while (!(status[0]));

        $display("[APB] Step complete. Status: 0x%08h", status);
    endtask

    // Read PC
    task automatic read_pc(output logic [31:0] pc);
        apb_read(DBG_PC_ADDR, pc);
        $display("[APB] PC = 0x%08h", pc);
    endtask

    // Write PC
    task automatic write_pc(input logic [31:0] pc);
        $display("[APB] Setting PC to 0x%08h", pc);
        apb_write(DBG_PC_ADDR, pc);
    endtask

    // Read current instruction
    /* verilator lint_off UNDRIVEN */
    task automatic read_instr(output logic [31:0] instr);
        apb_read(DBG_INSTR_ADDR, instr);
        $display("[APB] Current instruction: 0x%08h", instr);
    endtask
    /* verilator lint_on UNDRIVEN */

    // Read GPR
    task automatic read_gpr(input int reg_num, output logic [31:0] value);
        logic [11:0] addr;
        addr = DBG_GPR_BASE_ADDR + (reg_num * 4);
        apb_read(addr, value);
        $display("[APB] x%0d = 0x%08h", reg_num, value);
    endtask

    // Write GPR
    task automatic write_gpr(input int reg_num, input logic [31:0] value);
        logic [11:0] addr;
        addr = DBG_GPR_BASE_ADDR + (reg_num * 4);
        $display("[APB] Setting x%0d to 0x%08h", reg_num, value);
        apb_write(addr, value);
    endtask

    // Read all GPRs
    task automatic dump_gprs();
        logic [31:0] value;
        $display("[APB] === GPR Dump ===");
        for (int i = 0; i < 32; i++) begin
            read_gpr(i, value);
        end
        $display("[APB] =================");
    endtask

    // Set breakpoint 0
    task automatic set_breakpoint0(input logic [31:0] addr, input logic enable);
        $display("[APB] Setting BP0: addr=0x%08h, enable=%0d", addr, enable);
        apb_write(DBG_BP0_ADDR_ADDR, addr);
        apb_write(DBG_BP0_CTRL_ADDR, {31'b0, enable});
    endtask

    // Set breakpoint 1
    task automatic set_breakpoint1(input logic [31:0] addr, input logic enable);
        $display("[APB] Setting BP1: addr=0x%08h, enable=%0d", addr, enable);
        apb_write(DBG_BP1_ADDR_ADDR, addr);
        apb_write(DBG_BP1_CTRL_ADDR, {31'b0, enable});
    endtask

    // Clear all breakpoints
    task automatic clear_breakpoints();
        $display("[APB] Clearing all breakpoints");
        apb_write(DBG_BP0_CTRL_ADDR, 32'h0);
        apb_write(DBG_BP1_CTRL_ADDR, 32'h0);
    endtask

    // Read debug status
    task automatic read_status(output logic [31:0] status);
        apb_read(DBG_STATUS_ADDR, status);
        $display("[APB] Status: halted=%0d, running=%0d, halt_cause=%0d",
                 status[0], status[1], status[7:4]);
    endtask

    // Wait for CPU to halt (with timeout)
    task automatic wait_for_halt(input int timeout_cycles);
        logic [31:0] status;
        int cycles = 0;

        $display("[APB] Waiting for CPU to halt...");
        do begin
            @(posedge clk);
            apb_read(DBG_STATUS_ADDR, status);
            cycles++;
            if (cycles >= timeout_cycles) begin
                $display("[APB] ERROR: Timeout waiting for halt!");
                return;
            end
        end while (!(status[0]));

        $display("[APB] CPU halted after %0d cycles. Halt cause: %0d",
                 cycles, status[7:4]);
    endtask

endmodule
