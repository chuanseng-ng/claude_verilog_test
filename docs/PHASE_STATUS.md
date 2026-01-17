# Project Phase Status

Last updated: 2026-01-17

## Current Phase

**Phase 0: Foundations (Specification Phase)** - IN PROGRESS

## Phase Progress

### Phase 0: Foundations ✅ → 🟡

**Status**: Specifications being finalized

**Completed**:

- ✅ RV32I subset defined (PHASE0_ARCHITECTURE_SPEC.md)
- ✅ Reset behavior specified
- ✅ Trap behavior specified
- ✅ Memory ordering rules specified
- ✅ Commit semantics specified
- ✅ Project structure created (rtl/, tb/, sim/, docs/)

**In Progress**:

- 🟡 Interface specifications (RTL_DEFINITION.md) - needs protocol details
- 🟡 GPU architecture specification - needs creation
- 🟡 Reference model specification - needs creation
- 🟡 Memory map specification - needs creation
- 🟡 Phase-aligned verification plan - needs update

**Remaining**:

- ⏳ Python reference model implementation
- ⏳ cocotb test infrastructure setup
- ⏳ Final specification review

**Exit Criteria Status**:

- ✅ Written ISA + microarchitecture spec (PHASE0_ARCHITECTURE_SPEC.md exists)
- ✅ No RTL yet (confirmed - directories empty)
- 🟡 Supporting specifications complete (in progress)
- ⏳ Python reference model matches specification (not started)
- ⏳ Test infrastructure ready (not started)

**Target Completion**: TBD

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

### 2026-01-16: Project Restart

- Removed previous RTL implementation
- Starting fresh with specification-driven approach
- Commit: `1b4bb3b [Code] Remove database to restart project`

### 2026-01-17: Specification Alignment

- Identified documentation gaps
- Created phase status tracking
- Aligning all specifications with current project state

## Known Issues

1. **CLAUDE.md references non-existent RTL** - Contains references to old implementation
   - Status: Needs update to remove RTL references
   - Priority: Medium

2. **RTL_DEFINITION.md lacks protocol details** - Only mentions "AXI" and "APB" generically
   - Status: Needs specific protocol versions and signal definitions
   - Priority: High

3. **GPU specification incomplete** - GPU_MODEL.md lacks architectural detail
   - Status: Needs PHASE4_GPU_ARCHITECTURE_SPEC.md creation
   - Priority: High

4. **No reference model specification** - Multiple docs reference it, but no spec exists
   - Status: Needs REFERENCE_MODEL_SPEC.md creation
   - Priority: High

5. **No memory map** - Address space undefined
   - Status: Needs MEMORY_MAP.md creation
   - Priority: High

6. **Verification plan not phase-aligned** - Monolithic document doesn't show phase progression
   - Status: Needs restructure by phase
   - Priority: High

7. **Interrupt support unclear** - Phase 0 excludes, but RTL_DEFINITION.md includes
   - Status: Needs clarification of which phase adds interrupts
   - Priority: Medium

## Next Actions

### Immediate (Phase 0 Completion)

1. Create missing specification documents:
   - PHASE1_ARCHITECTURE_SPEC.md
   - PHASE4_GPU_ARCHITECTURE_SPEC.md
   - REFERENCE_MODEL_SPEC.md
   - MEMORY_MAP.md
2. Update existing specifications:
   - RTL_DEFINITION.md (add protocol details)
   - VERIFICATION_PLAN.md (phase-align)
   - ROADMAP.md (clarify interrupt phases)
   - CLAUDE.md (remove RTL references)
3. Implement Python reference model
4. Set up cocotb infrastructure

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
