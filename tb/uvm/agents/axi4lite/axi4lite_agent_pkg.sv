//-----------------------------------------------------------------------------
// AXI4-Lite Agent Package
// Contains all AXI4-Lite agent components
//-----------------------------------------------------------------------------

package axi4lite_agent_pkg;
    import uvm_pkg::*;
    `include "uvm_macros.svh"

    import axi4lite_pkg::*;

    `include "axi4lite_seq_item.sv"
    `include "axi4lite_slave_driver.sv"
    `include "axi4lite_monitor.sv"
    `include "axi4lite_agent.sv"

endpackage
