# Project Phase Status

Last updated: 2026-01-17

## Current Phase

**Phase 0: Foundations (Specification Phase)** - IN PROGRESS

## Phase Progress

### Phase 0: Foundations 🟡 → ✅

**Status**: Specifications complete, implementation in progress

**Completed**:

- ✅ RV32I subset defined (PHASE0_ARCHITECTURE_SPEC.md)
- ✅ Reset behavior specified
- ✅ Trap behavior specified
- ✅ Memory ordering rules specified
- ✅ Commit semantics specified
- ✅ Project structure created (rtl/, tb/, sim/, docs/)
- ✅ Interface specifications (RTL_DEFINITION.md) - AXI4-Lite & APB3 protocols defined
- ✅ GPU architecture specification (PHASE4_GPU_ARCHITECTURE_SPEC.md) - complete
- ✅ Reference model specification (REFERENCE_MODEL_SPEC.md) - complete
- ✅ Memory map specification (MEMORY_MAP.md) - complete with 4 KB alignment
- ✅ Phase-aligned verification plan (VERIFICATION_PLAN.md) - structured by phases
- ✅ Phase 1 CPU specification (PHASE1_ARCHITECTURE_SPEC.md) - complete

**In Progress**:

- 🟡 Python reference model implementation (AI-assisted, human-verified)
- 🟡 cocotb test infrastructure setup (AI-assisted)

**Remaining**:

- ⏳ Final specification review (HUMAN-ONLY - approval of all specs)

**Exit Criteria Status**:

- ✅ Written ISA + microarchitecture spec (PHASE0_ARCHITECTURE_SPEC.md exists)
- ✅ No RTL yet (confirmed - directories empty)
- ✅ Supporting specifications complete (all 7 specs finalized)
- 🟡 Python reference model matches specification (implementation in progress)
- 🟡 Test infrastructure ready (cocotb setup in progress)

**Target Completion**: 2026-01-31

### Phase 1: Minimal RV32I Core

**Status**: NOT STARTED

**Prerequisites**: Phase 0 exit criteria must be met

**Planned Deliverables**:

- Single-cycle RV32I CPU core
- AXI4-Lite master interface
- APB3 slave debug interface
- cocotb testbench
- Python reference model integration

**Target Start**: After Phase 0 completion

### Phase 2: Pipelined CPU

**Status**: NOT STARTED

**Prerequisites**: Phase 1 exit criteria must be met

### Phase 3: Memory System & Caches

**Status**: NOT STARTED

**Prerequisites**: Phase 2 exit criteria must be met

### Phase 4: GPU-Lite Compute Engine

**Status**: NOT STARTED

**Prerequisites**: Phase 3 exit criteria must be met

### Phase 5: SoC Integration

**Status**: NOT STARTED

**Prerequisites**: Phase 4 exit criteria must be met

## Recent Project Changes

### 2026-01-17: Phase 0 Documentation Complete

- ✅ All 7 specification documents finalized
- ✅ MEMORY_MAP.md aligned to 4 KB minimum regions
- ✅ All known documentation issues resolved
- Ready to proceed with Python reference model implementation
- Phase 0 specifications ready for human review

### 2026-01-17: Specification Alignment

- Identified documentation gaps
- Created phase status tracking
- Aligning all specifications with current project state

### 2026-01-16: Project Restart

- Removed previous RTL implementation
- Starting fresh with specification-driven approach
- Commit: `1b4bb3b [Code] Remove database to restart project`

## Known Issues

### ✅ Resolved (2026-01-17)

All previous specification issues have been resolved:

1. ✅ **CLAUDE.md RTL references** - All RTL references properly labeled as "Planned Architecture (Phase 1)"
2. ✅ **RTL_DEFINITION.md protocol details** - Now includes AXI4-Lite (ARM IHI 0022E) and APB3 (ARM IHI 0024C) specifications
3. ✅ **GPU specification** - PHASE4_GPU_ARCHITECTURE_SPEC.md created (520 lines)
4. ✅ **Reference model specification** - REFERENCE_MODEL_SPEC.md created (596 lines)
5. ✅ **Memory map** - MEMORY_MAP.md created (360 lines) with 4 KB minimum alignment
6. ✅ **Verification plan phase alignment** - Restructured by phases (Phase 0-5 sections)
7. ✅ **Interrupt support clarity** - Clearly stated as Phase 2+ in ROADMAP.md

### 🔄 Current Issues

**None** - All Phase 0 documentation is complete

## Next Actions

### Immediate (Phase 0 Completion)

**All specifications complete!** Remaining implementation tasks:

1. **Python reference model implementation** (AI-assisted, human-verified)
   - `tb/models/rv32i_model.py` - CPU instruction-accurate model
   - `tb/models/gpu_kernel_model.py` - GPU SIMT execution model
   - `tb/models/memory_model.py` - Shared memory model
   - AI may assist with: Boilerplate code, simple instruction implementations
   - Human must: Verify complex instructions, approve all logic, final review

2. **cocotb test infrastructure setup** (AI-assisted)
   - cocotb environment configuration
   - Test harness scaffolding
   - Driver templates for AXI4-Lite and APB3
   - AI may assist with: Infrastructure scaffolding, boilerplate code
   - Human must: Review and approve test strategy

3. **Final specification review** (HUMAN-ONLY)
   - Review all 7 specification documents
   - Approve Phase 0 completion
   - Authorize transition to Phase 1

### Short-term (Phase 1 Start)

1. Review and approve all Phase 0 specifications
2. Begin RTL implementation per PHASE1_ARCHITECTURE_SPEC.md
3. Develop directed tests
4. Integrate reference model with testbench

### Medium-term (Phase 1 Completion)

1. Complete RV32I instruction coverage
2. Pass 10k+ random instruction tests
3. Validate debug interface
4. Document Phase 1 lessons learned

## Documentation Structure

```text
docs/
├── ROADMAP.md                        # High-level project plan
├── PHASE_STATUS.md                   # This file - current status
├── design/
│   ├── PHASE0_ARCHITECTURE_SPEC.md   # Phase 0 CPU specification
│   ├── PHASE1_ARCHITECTURE_SPEC.md   # Phase 1 CPU specification (TBD)
│   ├── PHASE4_GPU_ARCHITECTURE_SPEC.md # Phase 4 GPU specification (TBD)
│   ├── DESIGN_EXPECTATION.md         # High-level design goals
│   ├── RTL_DEFINITION.md             # Interface definitions
│   ├── GPU_MODEL.md                  # GPU execution model overview
│   ├── MEMORY_MAP.md                 # Address space allocation (TBD)
│   └── REFERENCE_MODEL_SPEC.md       # Python model specification (TBD)
└── verification/
    └── VERIFICATION_PLAN.md          # Verification strategy
```

## AI/Human Responsibilities for Phase 0 Remaining Tasks

### Python Reference Model Implementation

**AI may assist with**:

- Class structure and boilerplate code
- Simple instruction implementations (ADD, SUB, AND, OR, XOR, SLL, SRL, SRA)
- Register file and memory model scaffolding
- Unit test generation and formatting

**Human must**:

- Implement complex instructions (BRANCH, LOAD, STORE, JAL, JALR)
- Design and approve control flow logic
- Verify instruction semantics match RISC-V specification
- Cross-validate against spike simulator
- Final code review and approval

### cocotb Infrastructure Setup

**AI may assist with**:

- cocotb configuration files (Makefile, pyproject.toml)
- AXI4-Lite and APB3 driver scaffolding
- Test harness boilerplate
- Monitor and scoreboard templates

**Human must**:

- Review test strategy alignment with VERIFICATION_PLAN.md
- Approve infrastructure design decisions
- Validate driver implementations against protocol specs

### Final Specification Review

**HUMAN-ONLY**:

- Review all specifications for consistency and completeness
- Approve Phase 0 completion
- Authorize transition to Phase 1 (RTL implementation)

## Key Decisions

### Architecture Decisions

- **ISA**: RV32I subset (no CSR, no MMU, no compressed)
- **Initial pipeline**: Single-cycle (Phase 1), 5-stage pipeline (Phase 2)
- **Memory interface**: AXI4-Lite for main memory, APB3 for debug
- **Debug strategy**: APB3 slave interface with halt/resume/step
- **Verification**: Python reference model + cocotb + pyuvm

### Process Decisions

- **Specification-first**: All specs finalized before RTL
- **No architecture drift**: Phase N cannot start until Phase N-1 exits
- **AI boundaries**: AI assists with RTL/tests, humans own architecture
- **Verification requirement**: Reference model must match RTL

## Contact

For questions about project status or phase transitions, refer to ROADMAP.md or the latest git commits.
