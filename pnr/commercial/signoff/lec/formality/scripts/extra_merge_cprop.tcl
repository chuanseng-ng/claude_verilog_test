# merge duplicated registers + propagate constant-0/X registers that have no counterpart (Formality's own "Constrained 0X" registers; Yosys removed them as constants)
set_app_var verification_merge_duplicated_registers true
set_app_var verification_propagate_const_reg_x true
