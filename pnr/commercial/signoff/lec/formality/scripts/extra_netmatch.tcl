# net-name based matching: a compare point may be matched by the names of the nets it drives (Yosys keeps one alias of the Q net, e.g. u_core.if_id_instr_w[5], and the sv2v wire has the same name)
set_app_var verification_merge_duplicated_registers true
set_app_var name_match_net true
set_app_var name_match_pin_net true
set_app_var signature_analysis_allow_net_match true
