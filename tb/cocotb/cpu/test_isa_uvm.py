"""
Wrapper for pyuvm ISA compliance tests.

This file imports and re-exports the pyuvm ISA tests so they can be
discovered by cocotb when running from the tb/cocotb/cpu/ directory.

Migration Status: Phase E.3 - ISA test migration COMPLETE
All 54 tests covering all 37 RV32I instructions
"""

# Add project root to path to find tb.cpu_uvm modules
import sys
from pathlib import Path

# Get project root (tb/cocotb/cpu -> ../../.. -> project root)
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import all ISA test functions
from tb.cpu_uvm.tests.test_isa_uvm import (  # noqa: E402
    # Priority 2: Arithmetic/Logical instructions (15 tests)
    test_isa_add_basic_uvm,
    test_isa_add_overflow_uvm,
    test_isa_addi_positive_uvm,
    test_isa_and_uvm,
    test_isa_andi_uvm,
    test_isa_auipc_basic_uvm,
    test_isa_auipc_nonzero_pc_uvm,
    test_isa_beq_not_taken_uvm,
    # Priority 4: Branch instructions (12 tests)
    test_isa_beq_taken_uvm,
    test_isa_bge_not_taken_uvm,
    test_isa_bge_taken_uvm,
    test_isa_bgeu_not_taken_uvm,
    test_isa_bgeu_taken_uvm,
    test_isa_blt_not_taken_uvm,
    test_isa_blt_taken_uvm,
    test_isa_bltu_not_taken_uvm,
    test_isa_bltu_taken_uvm,
    test_isa_bne_not_taken_uvm,
    test_isa_bne_taken_uvm,
    test_isa_jal_backward_uvm,
    # Priority 5: Jump instructions (4 tests)
    test_isa_jal_basic_uvm,
    test_isa_jalr_basic_uvm,
    test_isa_jalr_zero_offset_uvm,
    test_isa_lb_negative_uvm,
    test_isa_lb_positive_uvm,
    test_isa_lbu_uvm,
    test_isa_lh_negative_uvm,
    test_isa_lh_positive_uvm,
    test_isa_lhu_uvm,
    # Priority 6: Upper Immediate instructions (4 tests)
    test_isa_lui_basic_uvm,
    test_isa_lui_max_uvm,
    # Priority 1: Load/Store instructions (12 tests)
    test_isa_lw_basic_uvm,
    test_isa_lw_offset_uvm,
    test_isa_or_uvm,
    test_isa_ori_uvm,
    test_isa_sb_uvm,
    test_isa_sh_uvm,
    # Priority 3: Shift instructions (7 tests)
    test_isa_sll_basic_uvm,
    test_isa_sll_max_shift_uvm,
    test_isa_slli_basic_uvm,
    test_isa_slt_true_uvm,
    test_isa_slti_true_uvm,
    test_isa_sltiu_false_uvm,
    test_isa_sltu_false_uvm,
    test_isa_sra_basic_uvm,
    test_isa_srai_basic_uvm,
    test_isa_srl_basic_uvm,
    test_isa_srli_basic_uvm,
    test_isa_sub_basic_uvm,
    test_isa_sub_underflow_uvm,
    test_isa_sw_basic_uvm,
    test_isa_sw_offset_uvm,
    test_isa_xor_uvm,
    test_isa_xori_uvm,
)

# Re-export for cocotb discovery
__all__ = [
    # Priority 1: Load/Store (12 tests)
    "test_isa_lw_basic_uvm",
    "test_isa_lw_offset_uvm",
    "test_isa_sw_basic_uvm",
    "test_isa_sw_offset_uvm",
    "test_isa_lb_positive_uvm",
    "test_isa_lb_negative_uvm",
    "test_isa_lbu_uvm",
    "test_isa_lh_positive_uvm",
    "test_isa_lh_negative_uvm",
    "test_isa_lhu_uvm",
    "test_isa_sb_uvm",
    "test_isa_sh_uvm",
    # Priority 2: Arithmetic/Logical (15 tests)
    "test_isa_add_basic_uvm",
    "test_isa_add_overflow_uvm",
    "test_isa_sub_basic_uvm",
    "test_isa_sub_underflow_uvm",
    "test_isa_and_uvm",
    "test_isa_or_uvm",
    "test_isa_xor_uvm",
    "test_isa_slt_true_uvm",
    "test_isa_sltu_false_uvm",
    "test_isa_addi_positive_uvm",
    "test_isa_slti_true_uvm",
    "test_isa_sltiu_false_uvm",
    "test_isa_andi_uvm",
    "test_isa_ori_uvm",
    "test_isa_xori_uvm",
    # Priority 3: Shift (7 tests)
    "test_isa_sll_basic_uvm",
    "test_isa_sll_max_shift_uvm",
    "test_isa_slli_basic_uvm",
    "test_isa_srl_basic_uvm",
    "test_isa_srli_basic_uvm",
    "test_isa_sra_basic_uvm",
    "test_isa_srai_basic_uvm",
    # Priority 4: Branch (12 tests)
    "test_isa_beq_taken_uvm",
    "test_isa_beq_not_taken_uvm",
    "test_isa_bne_taken_uvm",
    "test_isa_bne_not_taken_uvm",
    "test_isa_blt_taken_uvm",
    "test_isa_blt_not_taken_uvm",
    "test_isa_bge_taken_uvm",
    "test_isa_bge_not_taken_uvm",
    "test_isa_bltu_taken_uvm",
    "test_isa_bltu_not_taken_uvm",
    "test_isa_bgeu_taken_uvm",
    "test_isa_bgeu_not_taken_uvm",
    # Priority 5: Jump (4 tests)
    "test_isa_jal_basic_uvm",
    "test_isa_jal_backward_uvm",
    "test_isa_jalr_basic_uvm",
    "test_isa_jalr_zero_offset_uvm",
    # Priority 6: Upper Immediate (4 tests)
    "test_isa_lui_basic_uvm",
    "test_isa_lui_max_uvm",
    "test_isa_auipc_basic_uvm",
    "test_isa_auipc_nonzero_pc_uvm",
]

# Total: 54 tests covering all 37 RV32I instructions
# Migration completed: 2026-02-01
