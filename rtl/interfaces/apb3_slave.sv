// APB3 Slave Interface - Provides debug access to CPU via APB protocol
module apb3_slave
    import rv32i_pkg::*;
(
    input  logic                      clk,
    input  logic                      rst_n,

    // APB3 Slave Interface
    input  logic [11:0]               paddr,
    input  logic                      psel,
    input  logic                      penable,
    input  logic                      pwrite,
    input  logic [31:0]               pwdata,
    output logic [31:0]               prdata,
    output logic                      pready,
    output logic                      pslverr,

    // Debug control outputs
    output logic                      dbg_halt_req,
    output logic                      dbg_resume_req,
    output logic                      dbg_step_req,
    output logic                      dbg_reset_req,

    // Debug status inputs
    input  logic                      dbg_halted,
    input  halt_cause_e               dbg_halt_cause,

    // PC access
    output logic                      dbg_pc_we,
    output logic [XLEN-1:0]           dbg_pc_wdata,
    input  logic [XLEN-1:0]           dbg_pc_rdata,

    // Instruction readback
    input  logic [ILEN-1:0]           dbg_instr,

    // Register file access
    output logic [REG_ADDR_WIDTH-1:0] dbg_reg_addr,
    output logic [XLEN-1:0]           dbg_reg_wdata,
    output logic                      dbg_reg_we,
    input  logic [XLEN-1:0]           dbg_reg_rdata,

    // Breakpoint configuration
    output logic [XLEN-1:0]           bp0_addr,
    output logic                      bp0_en,
    output logic [XLEN-1:0]           bp1_addr,
    output logic                      bp1_en
);

    // APB state machine
    typedef enum logic [1:0] {
        APB_IDLE   = 2'b00,
        APB_SETUP  = 2'b01,
        APB_ACCESS = 2'b10
    } apb_state_e;

    apb_state_e apb_state;

    // Internal registers
    logic [31:0] ctrl_reg;      // DBG_CTRL
    logic [31:0] bp0_addr_reg;  // Breakpoint 0 address
    logic [31:0] bp0_ctrl_reg;  // Breakpoint 0 control
    logic [31:0] bp1_addr_reg;  // Breakpoint 1 address
    logic [31:0] bp1_ctrl_reg;  // Breakpoint 1 control

    // Pulse generation for control bits
    logic halt_pulse, resume_pulse, step_pulse, reset_pulse;

    // APB state detection
    logic apb_write, apb_read;
    assign apb_write = psel && penable && pwrite;
    assign apb_read  = psel && penable && !pwrite;

    // APB always ready (single-cycle access)
    assign pready  = 1'b1;
    assign pslverr = 1'b0;

    // Detect rising edge on control bits
    logic [31:0] ctrl_reg_prev;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ctrl_reg_prev <= '0;
        end else begin
            ctrl_reg_prev <= ctrl_reg;
        end
    end

    assign halt_pulse   = ctrl_reg[0] && !ctrl_reg_prev[0];
    assign resume_pulse = ctrl_reg[1] && !ctrl_reg_prev[1];
    assign step_pulse   = ctrl_reg[2] && !ctrl_reg_prev[2];
    assign reset_pulse  = ctrl_reg[3] && !ctrl_reg_prev[3];

    // Register writes
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ctrl_reg     <= '0;
            bp0_addr_reg <= '0;
            bp0_ctrl_reg <= '0;
            bp1_addr_reg <= '0;
            bp1_ctrl_reg <= '0;
        end else if (apb_write) begin
            case (paddr)
                DBG_CTRL_ADDR:     ctrl_reg     <= pwdata;
                DBG_BP0_ADDR_ADDR: bp0_addr_reg <= pwdata;
                DBG_BP0_CTRL_ADDR: bp0_ctrl_reg <= pwdata;
                DBG_BP1_ADDR_ADDR: bp1_addr_reg <= pwdata;
                DBG_BP1_CTRL_ADDR: bp1_ctrl_reg <= pwdata;
                default: ;
            endcase
        end else begin
            // Auto-clear control bits after one cycle
            if (halt_pulse)   ctrl_reg[0] <= 1'b0;
            if (resume_pulse) ctrl_reg[1] <= 1'b0;
            if (step_pulse)   ctrl_reg[2] <= 1'b0;
            if (reset_pulse)  ctrl_reg[3] <= 1'b0;
        end
    end

    // Register reads
    always_comb begin
        prdata = '0;

        if (apb_read) begin
            // Check if address is in GPR range
            if (paddr >= DBG_GPR_BASE_ADDR && paddr < (DBG_GPR_BASE_ADDR + 32*4)) begin
                prdata = dbg_reg_rdata;
            end else begin
                case (paddr)
                    DBG_CTRL_ADDR:     prdata = ctrl_reg;
                    DBG_STATUS_ADDR:   prdata = {24'b0, dbg_halt_cause, 2'b0, !dbg_halted, dbg_halted};
                    DBG_PC_ADDR:       prdata = dbg_pc_rdata;
                    DBG_INSTR_ADDR:    prdata = dbg_instr;
                    DBG_BP0_ADDR_ADDR: prdata = bp0_addr_reg;
                    DBG_BP0_CTRL_ADDR: prdata = bp0_ctrl_reg;
                    DBG_BP1_ADDR_ADDR: prdata = bp1_addr_reg;
                    DBG_BP1_CTRL_ADDR: prdata = bp1_ctrl_reg;
                    default:           prdata = '0;
                endcase
            end
        end
    end

    // GPR address calculation
    logic [4:0] gpr_index;
    assign gpr_index = (paddr - DBG_GPR_BASE_ADDR) >> 2;

    // Debug outputs
    assign dbg_halt_req   = halt_pulse;
    assign dbg_resume_req = resume_pulse;
    assign dbg_step_req   = step_pulse;
    assign dbg_reset_req  = reset_pulse;

    // PC write
    assign dbg_pc_we    = apb_write && (paddr == DBG_PC_ADDR);
    assign dbg_pc_wdata = pwdata;

    // Register file access
    assign dbg_reg_addr  = gpr_index;
    assign dbg_reg_wdata = pwdata;
    assign dbg_reg_we    = apb_write &&
                           (paddr >= DBG_GPR_BASE_ADDR) &&
                           (paddr < (DBG_GPR_BASE_ADDR + 32*4));

    // Breakpoint outputs
    assign bp0_addr = bp0_addr_reg;
    assign bp0_en   = bp0_ctrl_reg[0];
    assign bp1_addr = bp1_addr_reg;
    assign bp1_en   = bp1_ctrl_reg[0];

endmodule
