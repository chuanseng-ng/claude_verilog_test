# merge duplicated registers (a register pair with identical D/clock/reset is treated as one) -- guidance-free; Yosys opt_merge merges such flops
set_app_var verification_merge_duplicated_registers true
