// rv32i_control.sv
// RV32I Control FSM
// Single-cycle execution with AXI stalls

module rv32i_control (
  // Clock and reset
  input  logic        clk,
  input  logic        rst_n,

  // Decoder control signals
  input  logic        branch,          // Branch instruction
  input  logic        jump,            // Jump instruction (JAL/JALR)
  input  logic        mem_rd,          // Memory read
  input  logic        mem_wr,          // Memory write
  input  logic        reg_wr_en,       // Register write enable
  input  logic        illegal_insn,    // Illegal instruction from decoder
  input  logic        ebreak,          // EBREAK instruction (triggers halt)
  input  logic        misaligned_load, // Misaligned load address
  input  logic        misaligned_store,// Misaligned store address

  // Branch comparator
  input  logic        branch_taken,    // Branch condition result

  // AXI4-Lite handshake signals
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic        axi_arready,     // Read address ready (checked in output logic, not state transitions)
  /* verilator lint_on UNUSEDSIGNAL */
  input  logic        axi_rvalid,      // Read data valid
  input  logic [1:0]  axi_rresp,       // Read response
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic        axi_awready,     // Write address ready (checked in output logic, not state transitions)
  input  logic        axi_wready,      // Write data ready (checked in output logic, not state transitions)
  /* verilator lint_on UNUSEDSIGNAL */
  input  logic        axi_bvalid,      // Write response valid
  input  logic [1:0]  axi_bresp,       // Write response

  output logic        axi_arvalid,     // Read address valid
  output logic        axi_rready,      // Read data ready
  output logic        axi_awvalid,     // Write address valid
  output logic        axi_wvalid,      // Write data valid
  output logic        axi_bready,      // Write response ready

  // Debug interface
  input  logic        dbg_halt_req,    // Debug halt request
  input  logic        dbg_resume_req,  // Debug resume request
  input  logic        dbg_step_req,    // Single-step request
  output logic        dbg_halted,      // CPU is halted

  // Internal control signals
  output logic        pc_wr_en,        // PC write enable
  output logic        pc_src,          // PC source: 0=PC+4, 1=branch/jump target
  output logic        instr_valid,     // Instruction fetch valid
  output logic        regfile_wr_en,   // Register file write enable (gated)
  output logic        commit_valid,    // Instruction commit
  output logic        trap_valid,      // Trap taken
  output logic [3:0]  trap_cause,      // Trap cause encoding
  output logic        data_access,     // 1=data access (MEM_WAIT), 0=instruction fetch (FETCH)

  // Debug outputs (for verification observability)
  output logic        debug_take_branch_jump,  // Branch/jump decision flag (registered)
  output logic [3:0]  debug_state              // Current FSM state
);

  // ================================================================
  // FSM State Definitions
  // ================================================================

  typedef enum logic [3:0] {
    RESET       = 4'b0000,  // Reset state
    FETCH       = 4'b0001,  // Instruction fetch
    DECODE      = 4'b0010,  // Instruction decode
    EXECUTE     = 4'b0011,  // Execute (ALU/branch)
    MEM_WAIT    = 4'b0100,  // Wait for memory operation
    WRITEBACK   = 4'b0101,  // Writeback to register file
    TRAP        = 4'b0110,  // Trap handling
    HALTED      = 4'b0111   // Debug halted
  } state_t;

  state_t current_state, next_state;

  // Branch/jump decision signals (registered to hold across state transitions)
  // CRITICAL: Must register the decision in EXECUTE because decoder signals
  // (branch, jump) are combinational and will change when the instruction
  // register updates with the next instruction!
  logic take_branch_jump_reg;
  logic take_branch_jump;

  // Trap cause tracking (RISC-V standard encoding)
  localparam [3:0] TRAP_ILLEGAL_INSN       = 4'b0010;  // Illegal instruction (RISC-V cause 2)
  localparam [3:0] TRAP_LOAD_MISALIGNED    = 4'b0100;  // Load address misaligned (RISC-V cause 4)
  localparam [3:0] TRAP_STORE_MISALIGNED   = 4'b0110;  // Store address misaligned (RISC-V cause 6)
  logic [3:0] trap_cause_reg;

  // AXI transaction issued flags (prevent retriggering transactions)
  // These track whether each phase of an AXI transaction has been issued
  logic ar_issued;  // Read address issued (arvalid && arready handshake completed)
  logic aw_issued;  // Write address issued (awvalid && awready handshake completed)
  logic w_issued;   // Write data issued (wvalid && wready handshake completed)

  // ================================================================
  // State Register
  // ================================================================

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      current_state <= RESET;
    end else begin
      current_state <= next_state;
    end
  end

  // ================================================================
  // Branch/Jump Decision Flag (MUST be registered!)
  // ================================================================
  // CRITICAL: We MUST register the branch/jump decision at the END of EXECUTE
  // state because:
  // 1. In EXECUTE state, decoder outputs are valid for current instruction
  // 2. When we transition to WRITEBACK (or MEM_WAIT), the instruction register
  //    latches the NEXT instruction, so decoder outputs change!
  // 3. If we tried to use branch/jump signals combinationally in WRITEBACK,
  //    they would reflect the NEXT instruction, not the one we're committing!

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      take_branch_jump_reg <= 1'b0;
    end else begin
      case (current_state)
        EXECUTE: begin
          // Register the decision at END of EXECUTE state
          // This captures the decision for the CURRENT instruction before
          // the instruction register updates
          take_branch_jump_reg <= (branch && branch_taken) || jump;
        end
        WRITEBACK: begin
          // Clear after use
          take_branch_jump_reg <= 1'b0;
        end
        default: begin
          // Hold value in other states (MEM_WAIT, etc.)
          take_branch_jump_reg <= take_branch_jump_reg;
        end
      endcase
    end
  end

  // Output: always use the REGISTERED decision
  // This ensures we use the decision from the instruction being committed,
  // not from whatever instruction happens to be in the instruction register
  assign take_branch_jump = take_branch_jump_reg;

  // ================================================================
  // Trap Cause Register
  // ================================================================
  // Register trap cause when entering TRAP state to preserve it across cycles

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      trap_cause_reg <= 4'b0000;
    end else begin
      // Capture trap cause when entering TRAP state
      if (next_state == TRAP && current_state != TRAP) begin
        // Priority: misalignment > illegal instruction > AXI error
        if (misaligned_load) begin
          trap_cause_reg <= TRAP_LOAD_MISALIGNED;
        end else if (misaligned_store) begin
          trap_cause_reg <= TRAP_STORE_MISALIGNED;
        end else if (illegal_insn) begin
          trap_cause_reg <= TRAP_ILLEGAL_INSN;
        end else if ((current_state == FETCH || current_state == MEM_WAIT) &&
                     ((axi_rvalid && axi_rresp != 2'b00) || (axi_bvalid && axi_bresp != 2'b00))) begin
          trap_cause_reg <= TRAP_ILLEGAL_INSN;  // AXI error -> treat as illegal instruction
        end else begin
          trap_cause_reg <= TRAP_ILLEGAL_INSN;  // Default to illegal instruction
        end
      end
    end
  end

  // ================================================================
  // AXI Transaction Issued Flags
  // ================================================================
  // Track AXI handshake completion to prevent retriggering transactions
  // Each flag is set when the handshake completes and cleared when leaving the state

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ar_issued <= 1'b0;
      aw_issued <= 1'b0;
      w_issued  <= 1'b0;
    end else begin
      // Read address channel
      if (current_state == FETCH || current_state == MEM_WAIT) begin
        // Set flag when handshake completes
        if (axi_arvalid && axi_arready) begin
          ar_issued <= 1'b1;
        end
      end else begin
        // Clear flag when leaving FETCH or MEM_WAIT state
        ar_issued <= 1'b0;
      end

      // Write address channel
      if (current_state == MEM_WAIT) begin
        // Set flag when handshake completes
        if (axi_awvalid && axi_awready) begin
          aw_issued <= 1'b1;
        end
      end else begin
        // Clear flag when leaving MEM_WAIT state
        aw_issued <= 1'b0;
      end

      // Write data channel
      if (current_state == MEM_WAIT) begin
        // Set flag when handshake completes
        if (axi_wvalid && axi_wready) begin
          w_issued <= 1'b1;
        end
      end else begin
        // Clear flag when leaving MEM_WAIT state
        w_issued <= 1'b0;
      end
    end
  end

  // ================================================================
  // Next State Logic
  // ================================================================

  always_comb begin
    // Default: stay in current state
    next_state = current_state;

    case (current_state)
      // ------------------------------------------------------------
      // RESET: Initialize CPU
      // ------------------------------------------------------------
      RESET: begin
        next_state = FETCH;
      end

      // ------------------------------------------------------------
      // FETCH: Request instruction from memory via AXI
      // ------------------------------------------------------------
      FETCH: begin
        // Wait for AXI read data phase to complete
        // Note: Address phase (arvalid/arready) and data phase (rvalid/rready)
        // are independent. rvalid can come many cycles after arready.
        if (axi_rvalid && axi_rready) begin
          // Data received, check for AXI error
          if (axi_rresp != 2'b00) begin
            next_state = TRAP;  // AXI error -> illegal instruction trap
          end else begin
            next_state = DECODE;
          end
        end
        // Otherwise stay in FETCH state waiting for rvalid

        // Debug halt request during fetch
        if (dbg_halt_req) begin
          next_state = HALTED;
        end
      end

      // ------------------------------------------------------------
      // DECODE: Decode instruction
      // ------------------------------------------------------------
      DECODE: begin
        // Check for illegal instruction
        if (illegal_insn) begin
          next_state = TRAP;
        end else begin
          next_state = EXECUTE;
        end
      end

      // ------------------------------------------------------------
      // EXECUTE: Execute instruction
      // ------------------------------------------------------------
      EXECUTE: begin
        // EBREAK halts the CPU
        if (ebreak) begin
          next_state = HALTED;
        // Check for misaligned memory access
        end else if (misaligned_load || misaligned_store) begin
          next_state = TRAP;
        // Memory operations need to wait for AXI
        end else if (mem_rd || mem_wr) begin
          next_state = MEM_WAIT;
        end else begin
          // Non-memory instructions go directly to writeback
          next_state = WRITEBACK;
        end
      end

      // ------------------------------------------------------------
      // MEM_WAIT: Wait for AXI memory transaction
      // ------------------------------------------------------------
      MEM_WAIT: begin
        if (mem_rd) begin
          // Load: wait for read data phase
          // Note: Address phase may have completed earlier
          if (axi_rvalid && axi_rready) begin
            if (axi_rresp != 2'b00) begin
              next_state = TRAP;  // AXI error
            end else begin
              next_state = WRITEBACK;
            end
          end
          // Otherwise stay in MEM_WAIT waiting for rvalid
        end else if (mem_wr) begin
          // Store: wait for write response phase
          // Note: Address and data phases may have completed earlier
          if (axi_bvalid && axi_bready) begin
            if (axi_bresp != 2'b00) begin
              next_state = TRAP;  // AXI error
            end else begin
              next_state = WRITEBACK;
            end
          end
          // Otherwise stay in MEM_WAIT waiting for bvalid
        end
      end

      // ------------------------------------------------------------
      // WRITEBACK: Write result to register file
      // ------------------------------------------------------------
      WRITEBACK: begin
        // Single-cycle writeback, commit instruction
        next_state = FETCH;

        // Debug halt request
        if (dbg_halt_req) begin
          next_state = HALTED;
        end

        // Single-step returns to halted after one instruction
        if (dbg_step_req) begin
          next_state = HALTED;
        end
      end

      // ------------------------------------------------------------
      // TRAP: Handle trap (illegal instruction in Phase 1)
      // ------------------------------------------------------------
      TRAP: begin
        // In Phase 1, trap just updates PC to trap vector
        // and resumes execution
        next_state = FETCH;
      end

      // ------------------------------------------------------------
      // HALTED: Debug halt state
      // ------------------------------------------------------------
      HALTED: begin
        // Resume execution
        if (dbg_resume_req) begin
          next_state = FETCH;
        end

        // Single-step: execute one instruction
        if (dbg_step_req) begin
          next_state = FETCH;
        end
      end

      // ------------------------------------------------------------
      // Default
      // ------------------------------------------------------------
      default: begin
        next_state = RESET;
      end
    endcase
  end

  // ================================================================
  // Output Logic
  // ================================================================

  always_comb begin
    // Default values
    pc_wr_en      = 1'b0;
    pc_src        = 1'b0;  // PC+4
    instr_valid   = 1'b0;
    regfile_wr_en = 1'b0;
    commit_valid  = 1'b0;
    trap_valid    = 1'b0;
    trap_cause    = 4'b0000;
    axi_arvalid   = 1'b0;
    axi_rready    = 1'b0;
    axi_awvalid   = 1'b0;
    axi_wvalid    = 1'b0;
    axi_bready    = 1'b0;
    dbg_halted    = 1'b0;
    data_access   = 1'b0;  // Default: instruction fetch mode

    case (current_state)
      // ------------------------------------------------------------
      // RESET
      // ------------------------------------------------------------
      RESET: begin
        // PC is already initialized to 0x0000_0000 by reset logic in rv32i_core.sv
        // Do not update PC here (would increment it to 0x04)
        pc_wr_en = 1'b0;
        pc_src   = 1'b0;
      end

      // ------------------------------------------------------------
      // FETCH
      // ------------------------------------------------------------
      FETCH: begin
        // Initiate AXI read transaction for instruction fetch
        // Only assert arvalid if we haven't issued the read address yet
        axi_arvalid = !ar_issued;
        axi_rready  = 1'b1;  // Always ready to accept read data
      end

      // ------------------------------------------------------------
      // DECODE
      // ------------------------------------------------------------
      DECODE: begin
        instr_valid = 1'b1;  // Instruction is valid
      end

      // ------------------------------------------------------------
      // EXECUTE
      // ------------------------------------------------------------
      EXECUTE: begin
        // Branch/jump decision is latched in pc_src_execute register
        // and used in WRITEBACK state
        // (no pc_src setting needed here)
      end

      // ------------------------------------------------------------
      // MEM_WAIT
      // ------------------------------------------------------------
      MEM_WAIT: begin
        data_access = 1'b1;  // Data access mode (not instruction fetch)

        // Defensive: only issue AXI requests if access is properly aligned
        // (This should never be reached since we trap in EXECUTE for misaligned accesses)
        if (mem_rd && !misaligned_load) begin
          // Load: initiate read
          // Only assert arvalid if we haven't issued the read address yet
          axi_arvalid = !ar_issued;
          axi_rready  = 1'b1;  // Always ready to accept read data
        end else if (mem_wr && !misaligned_store) begin
          // Store: initiate write
          // Only assert awvalid/wvalid if we haven't issued them yet
          axi_awvalid = !aw_issued;
          axi_wvalid  = !w_issued;
          axi_bready  = 1'b1;  // Always ready to accept write response
        end
      end

      // ------------------------------------------------------------
      // WRITEBACK
      // ------------------------------------------------------------
      WRITEBACK: begin
        // Enable register file write if needed
        regfile_wr_en = reg_wr_en;

        // Commit instruction
        commit_valid = 1'b1;

        // Update PC using flag from EXECUTE state
        pc_wr_en = 1'b1;
        pc_src = take_branch_jump;  // 1 if branch/jump taken, 0 otherwise
      end

      // ------------------------------------------------------------
      // TRAP
      // ------------------------------------------------------------
      TRAP: begin
        trap_valid = 1'b1;
        trap_cause = trap_cause_reg;  // Use registered trap cause

        // Update PC to trap vector (0x0000_0000 in Phase 1)
        pc_wr_en = 1'b1;
        pc_src   = 1'b0;  // Trap vector
      end

      // ------------------------------------------------------------
      // HALTED
      // ------------------------------------------------------------
      HALTED: begin
        dbg_halted = 1'b1;
      end

      // ------------------------------------------------------------
      // Default
      // ------------------------------------------------------------
      default: begin
        // All outputs remain at default values
      end
    endcase
  end

  // ================================================================
  // Debug Output Assignments
  // ================================================================
  // Expose internal signals for verification observability

  assign debug_take_branch_jump = take_branch_jump_reg;
  assign debug_state = current_state;

endmodule

// ============================================================================
// HUMAN REVIEW CHECKLIST
// ============================================================================
//
// Please verify the following before approving this control FSM:
//
// ✓ State transitions are correct and complete
//   - RESET → FETCH
//   - FETCH → DECODE (or TRAP on AXI error)
//   - DECODE → EXECUTE (or TRAP on illegal instruction)
//   - EXECUTE → MEM_WAIT (if memory op) or WRITEBACK
//   - MEM_WAIT → WRITEBACK (or TRAP on AXI error)
//   - WRITEBACK → FETCH
//   - TRAP → FETCH
//   - HALTED → FETCH (on resume/step)
//
// ✓ AXI handshake logic is correct
//   - arvalid/arready for read address
//   - rvalid/rready for read data
//   - awvalid/awready for write address
//   - wvalid/wready for write data
//   - bvalid/bready for write response
//
// ✓ Commit signal timing is correct
//   - commit_valid asserts for 1 cycle in WRITEBACK state
//   - Includes PC, instruction, and result
//
// ✓ Trap handling is correct
//   - Illegal instructions trigger TRAP state
//   - AXI errors trigger TRAP state
//   - Trap updates PC to trap vector
//
// ✓ Debug logic is correct
//   - Halt request transitions to HALTED
//   - Resume request transitions to FETCH
//   - Single-step executes one instruction then returns to HALTED
//
// ✓ PC update logic is correct
//   - PC+4 for normal instructions
//   - Branch target for taken branches
//   - Jump target for JAL/JALR
//   - Trap vector for traps
//
// ============================================================================
