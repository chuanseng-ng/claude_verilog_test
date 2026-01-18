# Phase 1: AI and Human Responsibilities

**Document Status**: Active guidance for Phase 1 RTL implementation

**Purpose**: Clear delineation of what AI (Claude) can assist with vs. what requires human oversight, decision-making, and approval during Phase 1.

---

## Quick Reference

### AI's Role: **Implementation Assistant**

- Generate boilerplate code
- Implement well-defined specifications
- Create test infrastructure
- Generate repetitive code patterns

### Human's Role: **Architect and Validator**

- Design critical logic (FSMs, control paths)
- Approve all functional decisions
- Validate correctness
- Make architectural trade-offs

---

## RTL Implementation

### Module: rv32i_regfile.sv (Register File)

#### ✅ AI MAY Assist With

- SystemVerilog module structure and ports
- 32x32-bit register array declaration
- Basic combinational read logic
- Write-enable logic based on spec
- x0 hardwiring logic (always 0)

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change register count or width
- Modify x0 behavior
- Add pipeline stages
- Change synchronous/asynchronous design choice

#### ✋ Human MUST

- **Approve** read/write port count (2 read, 1 write per spec)
- **Decide** synchronous vs. asynchronous reads
- **Verify** x0 is hardwired correctly
- **Review** final implementation before integration

**Complexity**: 🟢 Low - Well-defined specification

---

### Module: rv32i_imm_gen.sv (Immediate Generator)

#### ✅ AI MAY Assist With

- Module boilerplate
- Implement all 6 immediate formats (I, S, B, U, J, R-type)
- Sign-extension logic
- Case statement for instruction decoding

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change immediate formats from RV32I spec
- Modify bit-field extraction
- Optimize away "redundant" logic that's architecturally required

#### ✋ Human MUST

- **Verify** all 6 formats match RISC-V spec exactly
- **Check** sign-extension correctness (especially for negative values)
- **Test** with corner cases (max positive, max negative immediates)

**Complexity**: 🟢 Low - Purely combinational logic from spec

---

### Module: rv32i_alu.sv (Arithmetic Logic Unit)

#### ✅ AI MAY Assist With

- Module structure with all 10 RV32I ALU operations
- Basic arithmetic: ADD, SUB
- Logical operations: AND, OR, XOR
- Shift operations: SLL, SRL, SRA (using Verilog shift operators)
- Comparison operations: SLT, SLTU

#### ⚠️ AI MUST NOT (Without Human Approval)

- Add operations not in RV32I (e.g., MUL, DIV from M extension)
- Change operation encoding
- Optimize away operations that "seem unused"
- Modify shift amount masking

#### ✋ Human MUST

- **Approve** operation encodings (must match decoder)
- **Verify** signed vs. unsigned operations (SLT vs. SLTU, SRA vs. SRL)
- **Check** shift operations (only lower 5 bits of shift amount used)
- **Test** overflow behavior (wrapping, not saturation)
- **Validate** SRA (arithmetic right shift) preserves sign bit

**Complexity**: 🟡 Medium - Requires careful verification of signed/unsigned semantics

---

### Module: rv32i_decode.sv (Instruction Decoder)

#### ✅ AI MAY Assist With

- Opcode extraction (instruction[6:0])
- Funct3/funct7 field extraction
- Register address extraction (rs1, rs2, rd)
- Immediate format selection signal
- ALU operation selection boilerplate
- Generate control signal assignments based on spec

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change instruction encoding
- Add support for non-RV32I instructions
- Modify illegal instruction detection
- Change control signal definitions

#### ✋ Human MUST

- **Design** control signal encoding scheme
- **Approve** decoder truth table (all 37 instructions)
- **Verify** illegal instruction detection completeness
- **Review** every instruction's control signals match specification
- **Ensure** funct3/funct7 decoding is correct
- **Validate** that similar instructions are properly distinguished (e.g., ADD vs. SUB, SRL vs. SRA)

**Complexity**: 🟡 Medium - Large truth table, many control signals, critical correctness

**Critical**: This module determines instruction semantics. Errors here propagate everywhere.

---

### Module: rv32i_control.sv (Control FSM)

#### ✅ AI MAY Assist With

- FSM state enumeration structure
- State register declaration
- Next-state logic framework
- AXI handshake signal wiring

#### ⚠️ AI MUST NOT (Without Human Approval)

- Design state machine topology
- Define state transitions
- Add or remove states
- Change stall/wait conditions
- Modify debug state handling

#### ✋ Human MUST

- **Design** complete state machine (states and transitions)
- **Define** stall conditions for AXI transactions
- **Approve** debug halt/resume/step logic integration
- **Verify** all state transitions are reachable and correct
- **Ensure** no deadlock states exist
- **Review** priority between debug halt and normal execution
- **Validate** trap handling transitions
- **Check** reset behavior

**Complexity**: 🔴 High - Critical control logic, difficult to debug if wrong

**Critical**: This is the "brain" of the CPU. Human must design and approve.

---

### Module: rv32i_core.sv (Core Integration)

#### ✅ AI MAY Assist With

- Module instantiation boilerplate
- Wire declarations for inter-module signals
- Signal name matching between modules
- Connecting datapath components

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change module interconnection topology
- Add pipeline registers
- Modify datapath connections
- Change signal widths

#### ✋ Human MUST

- **Approve** module interconnection diagram
- **Verify** all critical paths are correctly connected
- **Check** PC update logic (increments, branches, jumps)
- **Validate** register writeback path
- **Review** ALU operand selection (rs1, rs2, PC, immediates)
- **Ensure** control signal distribution is correct

**Complexity**: 🟡 Medium - Integration complexity, many signals

---

### Module: axi4lite_master.sv (AXI4-Lite Master Interface)

#### ✅ AI MAY Assist With

- AXI4-Lite channel signal declarations (per ARM spec)
- Basic valid/ready handshake logic
- Read/write transaction sequencing
- Address/data/strobe assignment

#### ⚠️ AI MUST NOT (Without Human Approval)

- Violate AXI4-Lite protocol rules
- Change transaction ordering
- Add features not in AXI4-Lite spec (e.g., bursts, atomics)
- Modify backpressure handling

#### ✋ Human MUST

- **Approve** AXI transaction ordering (read-before-write, etc.)
- **Verify** protocol compliance with ARM IHI 0022E specification
- **Check** valid/ready handshake correctness (no combinational loops)
- **Validate** address alignment handling
- **Ensure** write strobes (wstrb) match byte enables
- **Review** error response handling (SLVERR, DECERR)
- **Test** with backpressure scenarios

**Complexity**: 🟡 Medium - Protocol compliance critical, debugging difficult

**Reference**: ARM IHI 0022E (AXI4-Lite specification)

---

### Module: apb3_slave.sv (APB3 Debug Interface)

#### ✅ AI MAY Assist With

- APB3 signal declarations (per ARM spec)
- Address decoding for debug registers
- Register read/write boilerplate
- PSELx, PENABLE, PWRITE decoding

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change register map (defined in MEMORY_MAP.md)
- Modify APB3 protocol timing
- Add write restrictions beyond spec
- Change register reset values

#### ✋ Human MUST

- **Approve** register map implementation
- **Verify** APB3 protocol compliance (ARM IHI 0024C)
- **Design** halt/resume/step command priority
- **Ensure** register writes only allowed when CPU halted (per spec)
- **Validate** breakpoint enable/disable logic
- **Check** read-only vs. read-write register enforcement
- **Review** register side-effects (e.g., STEP triggers one instruction)

**Complexity**: 🟡 Medium - Register map, protocol compliance, debug semantics

**Reference**: ARM IHI 0024C (APB3 specification), MEMORY_MAP.md

---

### Module: rv32i_debug.sv (Debug Controller)

#### ✅ AI MAY Assist With

- Breakpoint address comparators
- Breakpoint enable logic structure
- Halt request signal generation

#### ⚠️ AI MUST NOT (Without Human Approval)

- Design halt/resume priority logic
- Change breakpoint count (2 per spec)
- Modify halt cause encoding
- Add debug features not in spec

#### ✋ Human MUST

- **Design** halt/resume/step command sequencing
- **Approve** halt cause encoding and priority
- **Define** breakpoint hit detection logic
- **Verify** single-step implementation (one instruction then halt)
- **Ensure** CPU state preservation during halt
- **Review** interaction with exception/trap handling
- **Validate** that debug doesn't interfere with normal operation when not halted

**Complexity**: 🔴 High - Complex control logic, interaction with CPU FSM

---

### Module: rv32i_cpu_top.sv (Top-Level Integration)

#### ✅ AI MAY Assist With

- Port declarations
- Module instantiations (core, AXI master, APB slave, debug)
- Wire connections between modules
- Commit signal generation

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change top-level interface (must match RTL_DEFINITION.md)
- Add/remove modules
- Modify clock/reset distribution
- Change commit signal semantics

#### ✋ Human MUST

- **Approve** final top-level architecture
- **Verify** all interfaces match RTL_DEFINITION.md
- **Check** clock domain crossings (if any)
- **Validate** reset behavior (all modules reset correctly)
- **Ensure** commit signals accurately reflect retired instructions
- **Review** debug access paths
- **Test** integration with all interfaces active

**Complexity**: 🟡 Medium - Integration, interface compliance

---

## Verification & Testing

### cocotb Infrastructure

#### ✅ AI MAY Assist With

- cocotb test harness boilerplate
- AXI4-Lite driver implementation (using existing BFM in `tb/cocotb/bfm/`)
- APB3 driver implementation (using existing BFM in `tb/cocotb/bfm/`)
- Clock/reset generation utilities (already in `tb/cocotb/common/`)
- Basic transaction sequences
- Monitor implementation for signal capture
- Scoreboard boilerplate (compare RTL vs. Python model)

#### ⚠️ AI MUST NOT (Without Human Approval)

- Change test strategy or approach
- Skip protocol compliance checks
- Modify Python reference model behavior
- Change scoreboard comparison algorithm

#### ✋ Human MUST

- **Design** overall test strategy
- **Approve** scoreboard comparison logic
- **Define** what constitutes a "pass" vs. "fail"
- **Review** BFM protocol compliance
- **Validate** timing of transactions

**Complexity**: 🟡 Medium - Testbench infrastructure

---

### Directed Tests

#### ✅ AI MAY Assist With

- Generate simple directed tests for each instruction
- Create test templates
- Write memory initialization code
- Generate expected results based on Python model

**Example tests AI can write**:

- ADD instruction with known operands
- Load/store with aligned addresses
- Simple branch taken/not-taken
- Register file read/write

#### ⚠️ AI MUST NOT (Without Human Approval)

- Define corner cases to test
- Decide test coverage strategy
- Mark tests as "sufficient"

#### ✋ Human MUST

- **Define** corner case scenarios to test:
  - Overflow/underflow in arithmetic
  - Misaligned memory accesses
  - Branch to invalid addresses
  - x0 write attempts
  - Debug halt during different CPU states
  - Breakpoint hit handling
- **Approve** test coverage plan
- **Review** all test results
- **Decide** when testing is complete

**Complexity**: 🟡 Medium - Coverage strategy is critical

---

### Random Instruction Tests

#### ✅ AI MAY Assist With

- Random instruction generator framework
- Constraints for legal instruction generation
- Register dependency tracking
- Memory address management (avoid conflicts)
- Test harness integration

#### ⚠️ AI MUST NOT (Without Human Approval)

- Relax constraints to "make tests pass"
- Filter out failing instruction sequences
- Modify Python reference model to match RTL bugs

#### ✋ Human MUST

- **Define** randomization constraints
- **Approve** instruction mix (weight certain instructions)
- **Analyze** all failures
- **Decide** whether failure is RTL bug or test bug
- **Set** exit criteria (10,000+ instructions, 0 failures)

**Complexity**: 🔴 High - Debugging random failures is difficult

---

### Scoreboard (RTL vs. Python Reference Model)

#### ✅ AI MAY Assist With

- Capture RTL commit transactions
- Call Python reference model with same inputs
- Compare register writes
- Compare memory writes
- Report mismatches

#### ⚠️ AI MUST NOT (Without Human Approval)

- Ignore mismatches
- Add tolerance to comparisons
- Modify reference model to match RTL

#### ✋ Human MUST

- **Design** comparison algorithm
- **Define** what signals to compare (PC, rd, rd_value, mem_addr, mem_data)
- **Approve** timing of comparisons (when to check)
- **Analyze** every single mismatch
- **Root-cause** failures (RTL bug vs. test bug vs. reference model bug)

**Complexity**: 🟡 Medium - Critical for verification confidence

---

### Protocol Compliance Tests

#### ✅ AI MAY Assist With

- Generate AXI4-Lite protocol checkers (per ARM spec)
- Generate APB3 protocol checkers (per ARM spec)
- Implement protocol assertions
- Create backpressure scenarios

#### ⚠️ AI MUST NOT (Without Human Approval)

- Skip protocol checks
- Relax protocol requirements
- Assume protocol compliance without testing

#### ✋ Human MUST

- **Verify** all AXI4-Lite protocol rules are checked
- **Verify** all APB3 protocol rules are checked
- **Test** with heavy backpressure on both interfaces
- **Validate** concurrent AXI read and APB write scenarios
- **Ensure** error responses are handled correctly

**Complexity**: 🟡 Medium - Protocol specs are detailed

---

### Debug Interface Tests

#### ✅ AI MAY Assist With

- Basic halt/resume test sequences
- Single-step test template
- Register read/write tests (when halted)
- Breakpoint enable/disable tests

#### ⚠️ AI MUST NOT (Without Human Approval)

- Define complex debug scenarios
- Approve halt behavior during exceptions
- Skip edge cases

#### ✋ Human MUST

- **Define** debug test scenarios:
  - Halt during instruction fetch
  - Halt during memory access (load/store)
  - Halt at breakpoint
  - Single-step through branch
  - Resume from halt
  - Register modification while halted
  - PC modification while halted
- **Verify** CPU state is preserved during halt
- **Validate** breakpoint priority (if both hit simultaneously)
- **Test** illegal debug operations (e.g., write registers while running)

**Complexity**: 🔴 High - Debug interaction with CPU state is complex

---

## SystemVerilog Assertions (SVA)

#### ✅ AI MAY Assist With

- Generate assertion templates
- Basic protocol assertions (valid/ready handshakes)
- Simple property templates

**Example assertions AI can write**:

```systemverilog
// x0 is always zero
assert property (@(posedge clk) regfile.regs[0] == 0);

// Valid/ready handshake on AXI
assert property (@(posedge clk)
    axi_arvalid && !axi_arready |=> axi_arvalid);
```

#### ⚠️ AI MUST NOT (Without Human Approval)

- Decide which properties to assert
- Disable assertions that "fail too often"

#### ✋ Human MUST

- **Define** critical properties to assert:
  - No double write to same register in one cycle
  - PC must increment or jump (never random values)
  - AXI transactions must eventually complete (no deadlock)
  - Commit signal only valid when instruction retires
  - Debug halt must freeze CPU state
- **Analyze** assertion failures
- **Decide** if failure is RTL bug or assertion bug

**Complexity**: 🟡 Medium - Requires deep understanding of design invariants

---

## Coverage

#### ✅ AI MAY Assist With

- Generate instruction coverage bins (37 RV32I instructions)
- Generate state coverage bins (FSM states)
- Generate cross-coverage bins (instruction × state)
- Collect and report coverage metrics

#### ⚠️ AI MUST NOT (Without Human Approval)

- Decide coverage goals
- Declare coverage "sufficient" without hitting goals
- Remove coverage bins to inflate percentages

#### ✋ Human MUST

- **Define** coverage goals:
  - 100% instruction coverage (37/37)
  - 100% FSM state coverage
  - 100% FSM transition coverage
  - Cross-coverage: instruction × alignment
  - Cross-coverage: instruction × register dependencies
- **Analyze** coverage gaps
- **Write** tests to hit uncovered scenarios
- **Decide** when coverage is acceptable

**Complexity**: 🟡 Medium - Strategy is critical

---

## Documentation

#### ✅ AI MAY Assist With

- Generate module header comments
- Write signal descriptions
- Create timing diagrams from specs
- Format documentation markdown

#### ⚠️ AI MUST NOT (Without Human Approval)

- Write architectural documentation
- Define interfaces or protocols
- Document design decisions without human input

#### ✋ Human MUST

- **Write** architectural design documents
- **Document** critical design decisions and rationale
- **Explain** complex FSM behavior
- **Create** integration diagrams
- **Maintain** specification compliance matrix

**Complexity**: 🟢 Low - But human-authored

---

## Workflow Summary

### Typical Module Implementation Flow

```text
1. Human: Review PHASE1_ARCHITECTURE_SPEC.md for module requirements
2. Human: Design module architecture (if complex, like FSM)
3. AI: Generate module boilerplate (ports, signals, structure)
4. AI: Implement logic based on spec
5. Human: Review generated code line-by-line
6. Human: Approve or request changes
7. AI: Generate directed tests for module
8. Human: Define corner case tests
9. AI: Run tests, report results
10. Human: Analyze failures, debug
11. Iterate 8-10 until all tests pass
12. Human: Final approval, commit to git
```

### Typical Verification Flow

```text
1. Human: Define test strategy for the module/integration
2. AI: Generate test infrastructure (cocotb drivers, monitors)
3. AI: Write directed tests based on human-defined scenarios
4. Human: Review tests, add corner cases
5. AI: Generate random instruction tests
6. Human: Define randomization constraints
7. AI: Run 10,000+ random instruction tests
8. Human: Analyze every failure
9. Human: Root-cause failures (RTL bug? Test bug? Ref model bug?)
10. AI: Fix RTL bugs (if approved by human)
11. Iterate 7-10 until 0 failures
12. Human: Review coverage report
13. AI: Generate tests for coverage gaps
14. Human: Approve exit criteria met
```

---

## Red Flags 🚩

### When AI Is Overstepping

If AI does any of these **without explicit human approval**, stop and review:

- ❌ Modifies FSM states or transitions
- ❌ Changes instruction encoding
- ❌ Adds features not in spec
- ❌ Relaxes protocol requirements
- ❌ Ignores test failures
- ❌ Changes Python reference model to match RTL
- ❌ Declares verification "complete"
- ❌ Skips corner case testing
- ❌ Modifies specifications

### When Human Should Intervene

Human **must** step in when:

- 🛑 Designing control logic (FSMs, priority logic)
- 🛑 Approving decoder truth tables
- 🛑 Validating instruction semantics
- 🛑 Analyzing test failures
- 🛑 Making architectural trade-offs
- 🛑 Deciding verification completeness
- 🛑 Debugging protocol violations
- 🛑 Root-causing random test failures

---

## Exit Criteria (Phase 1)

Before Phase 1 is considered complete, **human must verify**:

### RTL Implementation

- ✅ All 8 modules implemented and reviewed
- ✅ All modules match PHASE1_ARCHITECTURE_SPEC.md
- ✅ All interfaces match RTL_DEFINITION.md
- ✅ All FSMs reviewed and approved by human
- ✅ No linter warnings or errors

### Functional Verification

- ✅ 37/37 RV32I instructions tested (100% coverage)
- ✅ All directed tests passing (100%)
- ✅ 10,000+ random instruction tests with 0 failures
- ✅ Scoreboard: 0 mismatches between RTL and Python reference model
- ✅ All corner cases tested and passing

### Protocol Compliance

- ✅ AXI4-Lite protocol compliance verified (all assertions pass)
- ✅ APB3 protocol compliance verified (all assertions pass)
- ✅ Backpressure scenarios tested

### Debug Interface

- ✅ Halt/resume tested
- ✅ Single-step tested
- ✅ Breakpoints tested (both breakpoints)
- ✅ Register read/write while halted tested
- ✅ PC modification while halted tested

### Code Quality

- ✅ All code reviewed by human
- ✅ All SVA assertions passing
- ✅ Coverage goals met (100% instruction, 100% state)
- ✅ Documentation complete

### Sign-Off

- ✅ **Human approval** that Phase 1 is complete

---

## Reference Documents

- **PHASE0_ARCHITECTURE_SPEC.md** - Architectural requirements (ISA, behavior)
- **PHASE1_ARCHITECTURE_SPEC.md** - Implementation requirements (modules, FSM, interfaces)
- **RTL_DEFINITION.md** - Interface signal definitions (AXI4-Lite, APB3)
- **MEMORY_MAP.md** - Debug register map
- **REFERENCE_MODEL_SPEC.md** - Python reference model API
- **VERIFICATION_PLAN.md** - Verification strategy
- **ROADMAP.md** - Phase boundaries and responsibilities

---

## Questions?

If unclear whether AI or human should do something:

**Default to human review and approval.**

When in doubt:

1. AI proposes
2. Human reviews
3. Human approves or rejects
4. AI implements approved changes

This ensures quality, correctness, and maintains human oversight of critical decisions.
