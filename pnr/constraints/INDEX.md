# SDC Constraints Directory - File Index

## Quick Start

**For synthesis**: Use `phase1_cpu_enhanced.sdc`
**After CTS**: Switch to `phase1_cpu_post_cts.sdc`
**To verify**: Run `./validate_sdc.sh` or `source check_constraints.tcl`

## All Files

### SDC Constraint Files (3 files)

1. **phase1_cpu.sdc** - Baseline constraints from specification
2. **phase1_cpu_enhanced.sdc** ⭐ - Enhanced, recommended for use
3. **phase1_cpu_post_cts.sdc** - Post-CTS with tighter timing

### Documentation Files (4 files)

4. **README_SDC.md** - Complete documentation (read this first!)
5. **QUICK_REFERENCE.md** - Quick lookup during STA sessions
6. **SDC_FILES_SUMMARY.md** - High-level overview
7. **INDEX.md** - This file

### Verification Tools (3 files)

8. **check_constraints.tcl** - TCL script for OpenSTA verification
9. **validate_sdc.sh** - Shell script for quick validation (no STA needed)
10. **Makefile.sdc** - Makefile targets for SDC operations

### Power Constraints (existing)

11. **phase1_cpu.upf** - UPF power intent (existing file)

## File Sizes

```
phase1_cpu.sdc              ~4 KB   (127 lines)
phase1_cpu_enhanced.sdc     ~14 KB  (356 lines)
phase1_cpu_post_cts.sdc     ~9 KB   (250 lines)
README_SDC.md               ~16 KB  (detailed docs)
QUICK_REFERENCE.md          ~8 KB   (quick lookup)
SDC_FILES_SUMMARY.md        ~12 KB  (overview)
check_constraints.tcl       ~6 KB   (verification)
validate_sdc.sh             ~7 KB   (bash validation)
Makefile.sdc                ~7 KB   (make targets)
```

## Usage Examples

### Validate SDC file (quick check, no tools required)

```bash
cd pnr/constraints
./validate_sdc.sh phase1_cpu_enhanced.sdc
```

### Verify constraints with OpenSTA

```bash
cd pnr
sta -no_splash -exit constraints/check_constraints.tcl
```

### Use in Makefile

```bash
cd pnr
make check_sdc              # Verify constraints
make sdc_info               # Show SDC info
make help_sdc               # SDC-specific help
```

### Read documentation

```bash
# Complete guide
cat constraints/README_SDC.md | less

# Quick reference
cat constraints/QUICK_REFERENCE.md | less

# Overview
cat constraints/SDC_FILES_SUMMARY.md | less
```

## What Each File Does

| File | When to Use | Purpose |
|:-----|:------------|:--------|
| `phase1_cpu_enhanced.sdc` | Synthesis, pre-CTS | Main constraints file (use this!) |
| `phase1_cpu_post_cts.sdc` | After CTS | Tighter timing after clock tree built |
| `validate_sdc.sh` | Anytime | Quick check without STA tools |
| `check_constraints.tcl` | With OpenSTA | Detailed verification |
| `README_SDC.md` | Learning | Complete documentation |
| `QUICK_REFERENCE.md` | During debug | Quick command lookup |

## Constraint Summary at a Glance

```
Clock:        100 MHz (10ns period)
Uncertainty:  0.5ns (pre-CTS) → 0.1ns/0.05ns (post-CTS)
AXI Timing:   2.0ns max, 0.5ns min
APB Timing:   3.0ns max, 1.0ns min
Total Ports:  40 (18 inputs, 20 outputs)
```

## Getting Help

1. **Quick lookup**: `QUICK_REFERENCE.md`
2. **Full guide**: `README_SDC.md`
3. **File overview**: `SDC_FILES_SUMMARY.md`
4. **Verify constraints**: `./validate_sdc.sh`

## Next Steps

1. ✅ Read `README_SDC.md` to understand SDC structure
2. ✅ Run `./validate_sdc.sh` to verify constraints
3. ✅ Use `phase1_cpu_enhanced.sdc` for synthesis
4. ✅ Switch to `phase1_cpu_post_cts.sdc` after CTS
5. ✅ Check timing with `make sta`

---

**Last Updated**: 2026-01-22
**Phase**: Phase 1 (RV32I Single-Cycle CPU)
**Status**: Ready for synthesis
