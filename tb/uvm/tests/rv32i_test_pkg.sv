//-----------------------------------------------------------------------------
// RV32I Test Package
// Contains all test classes
//-----------------------------------------------------------------------------

package rv32i_test_pkg;
    import uvm_pkg::*;
    `include "uvm_macros.svh"

    import rv32i_pkg::*;
    import axi4lite_pkg::*;
    import rv32i_uvm_pkg::*;
    import axi4lite_agent_pkg::*;
    import apb3_agent_pkg::*;
    import rv32i_env_pkg::*;

    // Include sequences
    `include "../sequences/rv32i_instr_gen.sv"
    `include "../sequences/rv32i_sequences.sv"

    // Include tests
    `include "rv32i_base_test.sv"

endpackage
