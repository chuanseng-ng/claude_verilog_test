//-----------------------------------------------------------------------------
// RV32I UVM Testbench Top
// Top-level module for UVM verification
//-----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_uvm_top;

    import uvm_pkg::*;
    import rv32i_pkg::*;
    import axi4lite_pkg::*;
    import rv32i_uvm_pkg::*;
    import axi4lite_agent_pkg::*;
    import apb3_agent_pkg::*;
    import rv32i_env_pkg::*;
    import rv32i_test_pkg::*;

    //-------------------------------------------------------------------------
    // Parameters
    //-------------------------------------------------------------------------
    parameter CLK_PERIOD = 10;  // 100 MHz

    //-------------------------------------------------------------------------
    // Clock and Reset
    //-------------------------------------------------------------------------
    logic clk;
    logic rst_n;

    // Clock generation
    initial begin
        clk = 0;
        forever #(CLK_PERIOD/2) clk = ~clk;
    end

    // Reset generation
    initial begin
        rst_n = 0;
        repeat(10) @(posedge clk);
        rst_n = 1;
    end

    //-------------------------------------------------------------------------
    // Interfaces
    //-------------------------------------------------------------------------
    axi4lite_if #(.ADDR_WIDTH(32), .DATA_WIDTH(32)) axi_if (clk, rst_n);
    apb3_if #(.ADDR_WIDTH(12), .DATA_WIDTH(32)) apb_if (clk, rst_n);

    //-------------------------------------------------------------------------
    // DUT Instantiation
    //-------------------------------------------------------------------------
    rv32i_cpu_top dut (
        .clk            (clk),
        .rst_n          (rst_n),

        // AXI4-Lite Master Interface
        .m_axi_awaddr   (axi_if.awaddr),
        .m_axi_awvalid  (axi_if.awvalid),
        .m_axi_awready  (axi_if.awready),
        .m_axi_wdata    (axi_if.wdata),
        .m_axi_wstrb    (axi_if.wstrb),
        .m_axi_wvalid   (axi_if.wvalid),
        .m_axi_wready   (axi_if.wready),
        .m_axi_bresp    (axi_if.bresp),
        .m_axi_bvalid   (axi_if.bvalid),
        .m_axi_bready   (axi_if.bready),
        .m_axi_araddr   (axi_if.araddr),
        .m_axi_arvalid  (axi_if.arvalid),
        .m_axi_arready  (axi_if.arready),
        .m_axi_rdata    (axi_if.rdata),
        .m_axi_rresp    (axi_if.rresp),
        .m_axi_rvalid   (axi_if.rvalid),
        .m_axi_rready   (axi_if.rready),

        // APB3 Slave Interface (Debug)
        .s_apb_paddr    (apb_if.paddr),
        .s_apb_psel     (apb_if.psel),
        .s_apb_penable  (apb_if.penable),
        .s_apb_pwrite   (apb_if.pwrite),
        .s_apb_pwdata   (apb_if.pwdata),
        .s_apb_prdata   (apb_if.prdata),
        .s_apb_pready   (apb_if.pready),
        .s_apb_pslverr  (apb_if.pslverr)
    );

    //-------------------------------------------------------------------------
    // Interface Configuration
    //-------------------------------------------------------------------------
    initial begin
        // Set virtual interfaces in config DB
        uvm_config_db#(virtual axi4lite_if.slave_drv)::set(null, "uvm_test_top.env.axi_agent.driver", "vif", axi_if.slave_drv);
        uvm_config_db#(virtual axi4lite_if.slave_mon)::set(null, "uvm_test_top.env.axi_agent.monitor", "vif", axi_if.slave_mon);
        uvm_config_db#(virtual apb3_if.master_drv)::set(null, "uvm_test_top.env.apb_agent.driver", "vif", apb_if.master_drv);
        uvm_config_db#(virtual apb3_if.master_mon)::set(null, "uvm_test_top.env.apb_agent.monitor", "vif", apb_if.master_mon);
    end

    //-------------------------------------------------------------------------
    // Run UVM Test
    //-------------------------------------------------------------------------
    initial begin
        // Set timeout
        uvm_top.set_timeout(10ms, 0);

        // Run test
        run_test();
    end

    //-------------------------------------------------------------------------
    // Waveform Dump
    //-------------------------------------------------------------------------
    initial begin
        if ($test$plusargs("waves")) begin
            $dumpfile("tb_uvm_top.vcd");
            $dumpvars(0, tb_uvm_top);
        end
    end

    //-------------------------------------------------------------------------
    // Simulation Timeout
    //-------------------------------------------------------------------------
    initial begin
        #10ms;
        `uvm_fatal("TIMEOUT", "Simulation timeout")
    end

endmodule
