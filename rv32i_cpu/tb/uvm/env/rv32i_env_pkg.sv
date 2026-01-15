//-----------------------------------------------------------------------------
// RV32I Environment Package
// Contains environment, scoreboard, coverage, and reference model
//-----------------------------------------------------------------------------

// Analysis implementation declarations must be outside package
`uvm_analysis_imp_decl(_axi_read)
`uvm_analysis_imp_decl(_axi_write)
`uvm_analysis_imp_decl(_apb)

package rv32i_env_pkg;
    import uvm_pkg::*;
    `include "uvm_macros.svh"

    import rv32i_pkg::*;
    import axi4lite_pkg::*;
    import rv32i_uvm_pkg::*;
    import axi4lite_agent_pkg::*;
    import apb3_agent_pkg::*;

    `include "rv32i_ref_model.sv"
    `include "rv32i_scoreboard.sv"
    `include "rv32i_coverage.sv"
    `include "rv32i_env.sv"

endpackage
