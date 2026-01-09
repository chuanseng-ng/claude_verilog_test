//-----------------------------------------------------------------------------
// APB3 Interface
// Used for connecting UVM agents to DUT debug interface
//-----------------------------------------------------------------------------

interface apb3_if #(
    parameter int ADDR_WIDTH = 12,
    parameter int DATA_WIDTH = 32
) (
    input logic clk,
    input logic rst_n
);

    //-------------------------------------------------------------------------
    // APB3 Signals
    //-------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0] paddr;
    logic                  psel;
    logic                  penable;
    logic                  pwrite;
    logic [DATA_WIDTH-1:0] pwdata;
    logic [DATA_WIDTH-1:0] prdata;
    logic                  pready;
    logic                  pslverr;

    //-------------------------------------------------------------------------
    // Clocking Blocks
    //-------------------------------------------------------------------------

    // Master driver clocking block (debug controller driving CPU)
    clocking mst_drv_cb @(posedge clk);
        default input #1step output #1ns;
        output paddr, psel, penable, pwrite, pwdata;
        input  prdata, pready, pslverr;
    endclocking

    // Master monitor clocking block
    clocking mst_mon_cb @(posedge clk);
        default input #1step;
        input paddr, psel, penable, pwrite, pwdata;
        input prdata, pready, pslverr;
    endclocking

    //-------------------------------------------------------------------------
    // Modports
    //-------------------------------------------------------------------------
    modport master_drv (clocking mst_drv_cb, input clk, rst_n);
    modport master_mon (clocking mst_mon_cb, input clk, rst_n);

    // Direct DUT connection modport (master side - testbench is master)
    modport dut_master (
        output paddr, psel, penable, pwrite, pwdata,
        input  prdata, pready, pslverr
    );

    // Direct DUT connection modport (slave side - CPU is slave)
    modport dut_slave (
        input  paddr, psel, penable, pwrite, pwdata,
        output prdata, pready, pslverr
    );

    //-------------------------------------------------------------------------
    // Assertions
    //-------------------------------------------------------------------------
    `ifdef ENABLE_ASSERTIONS
    // PENABLE must only assert after PSEL
    property penable_follows_psel;
        @(posedge clk) disable iff (!rst_n)
        $rose(penable) |-> psel;
    endproperty
    assert property (penable_follows_psel) else $error("APB: PENABLE without PSEL");

    // PSEL must be stable during transfer
    property psel_stable;
        @(posedge clk) disable iff (!rst_n)
        (psel && !penable) |=> psel;
    endproperty
    assert property (psel_stable) else $error("APB: PSEL deasserted during setup phase");

    // Address must be stable during transfer
    property addr_stable;
        @(posedge clk) disable iff (!rst_n)
        (psel && penable && !pready) |=> $stable(paddr);
    endproperty
    assert property (addr_stable) else $error("APB: PADDR changed during access phase");
    `endif

endinterface
