//-----------------------------------------------------------------------------
// AXI4-Lite Interface
// Used for connecting UVM agents to DUT
//-----------------------------------------------------------------------------

interface axi4lite_if #(
    parameter int ADDR_WIDTH = 32,
    parameter int DATA_WIDTH = 32
) (
    input logic clk,
    input logic rst_n
);
    import axi4lite_pkg::*;

    localparam int STRB_WIDTH = DATA_WIDTH / 8;

    //-------------------------------------------------------------------------
    // Write Address Channel
    //-------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0] awaddr;
    logic                  awvalid;
    logic                  awready;

    //-------------------------------------------------------------------------
    // Write Data Channel
    //-------------------------------------------------------------------------
    logic [DATA_WIDTH-1:0] wdata;
    logic [STRB_WIDTH-1:0] wstrb;
    logic                  wvalid;
    logic                  wready;

    //-------------------------------------------------------------------------
    // Write Response Channel
    //-------------------------------------------------------------------------
    logic [1:0]            bresp;
    logic                  bvalid;
    logic                  bready;

    //-------------------------------------------------------------------------
    // Read Address Channel
    //-------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0] araddr;
    logic                  arvalid;
    logic                  arready;

    //-------------------------------------------------------------------------
    // Read Data Channel
    //-------------------------------------------------------------------------
    logic [DATA_WIDTH-1:0] rdata;
    logic [1:0]            rresp;
    logic                  rvalid;
    logic                  rready;

    //-------------------------------------------------------------------------
    // Clocking Blocks for UVM Agent
    //-------------------------------------------------------------------------

    // Slave driver clocking block (responds to master requests)
    clocking slv_drv_cb @(posedge clk);
        default input #1step output #1ns;
        // Write Address Channel - slave provides ready
        input  awaddr, awvalid;
        output awready;
        // Write Data Channel - slave provides ready
        input  wdata, wstrb, wvalid;
        output wready;
        // Write Response Channel - slave drives
        output bresp, bvalid;
        input  bready;
        // Read Address Channel - slave provides ready
        input  araddr, arvalid;
        output arready;
        // Read Data Channel - slave drives
        output rdata, rresp, rvalid;
        input  rready;
    endclocking

    // Slave monitor clocking block
    clocking slv_mon_cb @(posedge clk);
        default input #1step;
        input awaddr, awvalid, awready;
        input wdata, wstrb, wvalid, wready;
        input bresp, bvalid, bready;
        input araddr, arvalid, arready;
        input rdata, rresp, rvalid, rready;
    endclocking

    // Master driver clocking block (for active master if needed)
    clocking mst_drv_cb @(posedge clk);
        default input #1step output #1ns;
        output awaddr, awvalid;
        input  awready;
        output wdata, wstrb, wvalid;
        input  wready;
        input  bresp, bvalid;
        output bready;
        output araddr, arvalid;
        input  arready;
        input  rdata, rresp, rvalid;
        output rready;
    endclocking

    //-------------------------------------------------------------------------
    // Modports
    //-------------------------------------------------------------------------
    modport slave_drv (clocking slv_drv_cb, input clk, rst_n);
    modport slave_mon (clocking slv_mon_cb, input clk, rst_n);
    modport master_drv (clocking mst_drv_cb, input clk, rst_n);

    // Direct DUT connection modport (master side - DUT is master)
    modport dut_master (
        output awaddr, awvalid,
        input  awready,
        output wdata, wstrb, wvalid,
        input  wready,
        input  bresp, bvalid,
        output bready,
        output araddr, arvalid,
        input  arready,
        input  rdata, rresp, rvalid,
        output rready
    );

    // Direct DUT connection modport (slave side - for memory)
    modport dut_slave (
        input  awaddr, awvalid,
        output awready,
        input  wdata, wstrb, wvalid,
        output wready,
        output bresp, bvalid,
        input  bready,
        input  araddr, arvalid,
        output arready,
        output rdata, rresp, rvalid,
        input  rready
    );

    //-------------------------------------------------------------------------
    // Assertions
    //-------------------------------------------------------------------------
    `ifdef ENABLE_ASSERTIONS
    // Write address valid must not change until ready
    property aw_stable;
        @(posedge clk) disable iff (!rst_n)
        (awvalid && !awready) |=> ($stable(awaddr) && awvalid);
    endproperty
    assert property (aw_stable) else $error("AXI: AWADDR changed while AWVALID high");

    // Write data valid must not change until ready
    property w_stable;
        @(posedge clk) disable iff (!rst_n)
        (wvalid && !wready) |=> ($stable(wdata) && $stable(wstrb) && wvalid);
    endproperty
    assert property (w_stable) else $error("AXI: WDATA/WSTRB changed while WVALID high");

    // Read address valid must not change until ready
    property ar_stable;
        @(posedge clk) disable iff (!rst_n)
        (arvalid && !arready) |=> ($stable(araddr) && arvalid);
    endproperty
    assert property (ar_stable) else $error("AXI: ARADDR changed while ARVALID high");

    // Response valid must not change until ready
    property b_stable;
        @(posedge clk) disable iff (!rst_n)
        (bvalid && !bready) |=> ($stable(bresp) && bvalid);
    endproperty
    assert property (b_stable) else $error("AXI: BRESP changed while BVALID high");

    // Read data valid must not change until ready
    property r_stable;
        @(posedge clk) disable iff (!rst_n)
        (rvalid && !rready) |=> ($stable(rdata) && $stable(rresp) && rvalid);
    endproperty
    assert property (r_stable) else $error("AXI: RDATA/RRESP changed while RVALID high");
    `endif

endinterface
