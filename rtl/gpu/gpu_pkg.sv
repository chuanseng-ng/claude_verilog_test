// GPU-Lite SIMT package: constants, types, and opcode definitions for Phase 4.
// All GPU RTL modules import this package.
// lint_off UNUSEDPARAM: not every module uses every localparam; suppress globally.
/* verilator lint_off UNUSEDPARAM */
package gpu_pkg;

    // -----------------------------------------------------------------------
    // Top-level parameters
    // -----------------------------------------------------------------------
    localparam int N_LANES          = 8;    // SIMT lanes per warp
    localparam int N_WARPS          = 8;    // max warps in flight
    localparam int N_REGS           = 32;   // GPRs per lane
    localparam int REG_WIDTH        = 32;   // bits per register
    localparam int SHARED_MEM_BYTES = 16384;// 16 KiB scratchpad
    localparam int SHARED_BANKS     = 32;   // banks in shared memory
    /* verilator lint_off UNUSEDPARAM */
    localparam int SHARED_WORDS     = SHARED_MEM_BYTES / (SHARED_BANKS * 4); // 16 words/bank (used by shared_memory.sv)
    /* verilator lint_on UNUSEDPARAM */
    /* verilator lint_off UNUSEDPARAM */
    localparam int DIV_STACK_DEPTH  = 4;    // per-warp divergence stack entries
    /* verilator lint_on UNUSEDPARAM */

    // Derived widths
    /* verilator lint_off UNUSEDPARAM */
    localparam int LANE_W  = $clog2(N_LANES);   // 3 (used by shared_memory.sv)
    /* verilator lint_on UNUSEDPARAM */
    /* verilator lint_off UNUSEDPARAM */
    localparam int WARP_W  = $clog2(N_WARPS);   // 3
    /* verilator lint_on UNUSEDPARAM */
    /* verilator lint_off UNUSEDPARAM */
    localparam int REG_W   = $clog2(N_REGS);    // 5
    localparam int SHMEM_W = $clog2(SHARED_MEM_BYTES); // 14 (byte address)
    /* verilator lint_on UNUSEDPARAM */

    // -----------------------------------------------------------------------
    // Opcode encoding (7-bit primary opcode, RISC-V–style fields retained)
    // -----------------------------------------------------------------------
    typedef enum logic [6:0] {
        // Arithmetic / logic — R-type (funct3/funct7 differentiate)
        VADD    = 7'h01,
        VSUB    = 7'h02,
        VMUL    = 7'h03,
        VAND    = 7'h04,
        VOR     = 7'h05,
        VXOR    = 7'h06,
        VSLL    = 7'h07,
        VSRL    = 7'h08,
        VSRA    = 7'h09,
        // Arithmetic / logic — I-type (immediate)
        VADDI   = 7'h11,
        VANDI   = 7'h12,
        VORI    = 7'h13,
        VXORI   = 7'h14,
        // Memory — I-type (global)
        VLD     = 7'h20,
        VST     = 7'h21,
        // Memory — I-type (shared scratchpad)
        VLDS    = 7'h22,
        VSTS    = 7'h23,
        // Branch — B-type
        VBEQ    = 7'h30,
        VBNE    = 7'h31,
        VBLT    = 7'h32,
        VBGE    = 7'h33,
        // Control
        VJMP    = 7'h38,
        VRET    = 7'h3F,
        // Special register reads
        VMOV_TID_X = 7'h40,
        VMOV_TID_Y = 7'h41,
        VMOV_TID_Z = 7'h42,
        VMOV_BID_X = 7'h46,
        VMOV_BID_Y = 7'h47,
        VMOV_BID_Z = 7'h48,
        // Barrier
        VSYNC   = 7'h50
    } gpu_opcode_t;

    // Instruction class — decoded by gpu_compute_unit
    typedef enum logic [3:0] {
        IC_ALU    = 4'd0,
        IC_BRANCH = 4'd1,
        IC_MEMORY = 4'd2,
        IC_SPECIAL= 4'd3,   // VMOV tid/bid
        IC_VSYNC  = 4'd4,
        IC_VRET   = 4'd5,
        IC_VJMP   = 4'd6,
        IC_SHMEM  = 4'd8,   // shared-memory load/store (VLDS/VSTS)
        IC_INVALID= 4'd9
    } instr_class_t;

    // -----------------------------------------------------------------------
    // Instruction format structs (decoded from raw 32-bit word)
    // -----------------------------------------------------------------------
    typedef struct packed {
        logic [6:0]  funct7;
        logic [4:0]  rs2;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [4:0]  rd;
        logic [6:0]  opcode;
    } gpu_r_instr_t;

    typedef struct packed {
        logic [11:0] imm;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [4:0]  rd;
        logic [6:0]  opcode;
    } gpu_i_instr_t;

    typedef struct packed {
        logic [6:0]  imm_hi;   // [12|10:5]
        logic [4:0]  rs2;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [4:0]  imm_lo;   // [4:1|11]
        logic [6:0]  opcode;
    } gpu_b_instr_t;

    // -----------------------------------------------------------------------
    // Per-warp state (held in warp_scheduler)
    // -----------------------------------------------------------------------
    typedef struct packed {
        logic [31:0] pc;
        logic [N_LANES-1:0] active_mask;
        logic        busy;   // issued to compute unit, not yet VRET
        logic        done;   // completed (VRET with empty div stack)
    } warp_state_t;

    // Divergence stack entry
    typedef struct packed {
        logic [31:0] return_pc;
        logic [N_LANES-1:0] return_mask;
    } div_entry_t;

    // -----------------------------------------------------------------------
    // GPU top-level FSM state
    // -----------------------------------------------------------------------
    typedef enum logic [2:0] {
        GPS_IDLE    = 3'd0,
        GPS_RUNNING = 3'd1,
        GPS_DONE    = 3'd2,
        GPS_ERROR   = 3'd3
    } gpu_state_t;

    // -----------------------------------------------------------------------
    // Kernel descriptor (written by CPU via AXI4-Lite, queued in command queue)
    // -----------------------------------------------------------------------
    typedef struct packed {
        logic [31:0] kernel_pc;
        logic [15:0] grid_x;
        logic [15:0] grid_y;
        logic [15:0] grid_z;
        logic [9:0]  block_x;
        logic [9:0]  block_y;
        logic [9:0]  block_z;
        logic [31:0] arg_ptr;
    } kernel_desc_t;

endpackage
/* verilator lint_on UNUSEDPARAM */
