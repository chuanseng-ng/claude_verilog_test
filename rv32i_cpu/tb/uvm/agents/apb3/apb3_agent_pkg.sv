//-----------------------------------------------------------------------------
// APB3 Agent Package
// Contains all APB3 agent components
//-----------------------------------------------------------------------------

package apb3_agent_pkg;
    import uvm_pkg::*;
    `include "uvm_macros.svh"

    import rv32i_pkg::*;

    `include "apb3_seq_item.sv"
    `include "apb3_master_driver.sv"
    `include "apb3_monitor.sv"
    `include "apb3_sequences.sv"
    `include "apb3_agent.sv"

endpackage
