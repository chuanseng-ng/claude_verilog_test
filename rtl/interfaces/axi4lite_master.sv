// AXI4-Lite Master Interface - Converts simple memory interface to AXI4-Lite
module axi4lite_master
    import rv32i_pkg::*;
    import axi4lite_pkg::*;
(
    input  logic                      clk,
    input  logic                      rst_n,

    // Simple memory interface (from CPU core)
    input  logic [XLEN-1:0]           mem_addr,
    input  logic [XLEN-1:0]           mem_wdata,
    input  logic [3:0]                mem_wstrb,
    output logic [XLEN-1:0]           mem_rdata,
    input  logic                      mem_req,
    input  logic                      mem_we,
    output logic                      mem_ready,
    output logic                      mem_valid,

    // AXI4-Lite Master Interface
    // Write Address Channel
    output logic [AXI_ADDR_WIDTH-1:0] m_axi_awaddr,
    output logic                      m_axi_awvalid,
    input  logic                      m_axi_awready,

    // Write Data Channel
    output logic [AXI_DATA_WIDTH-1:0] m_axi_wdata,
    output logic [AXI_STRB_WIDTH-1:0] m_axi_wstrb,
    output logic                      m_axi_wvalid,
    input  logic                      m_axi_wready,

    // Write Response Channel
    input  logic [1:0]                m_axi_bresp,
    input  logic                      m_axi_bvalid,
    output logic                      m_axi_bready,

    // Read Address Channel
    output logic [AXI_ADDR_WIDTH-1:0] m_axi_araddr,
    output logic                      m_axi_arvalid,
    input  logic                      m_axi_arready,

    // Read Data Channel
    input  logic [AXI_DATA_WIDTH-1:0] m_axi_rdata,
    input  logic [1:0]                m_axi_rresp,
    input  logic                      m_axi_rvalid,
    output logic                      m_axi_rready
);

    // State machine
    axi_master_state_e state_q, state_d;

    // Registered outputs
    logic [AXI_ADDR_WIDTH-1:0] addr_q;
    logic [AXI_DATA_WIDTH-1:0] wdata_q;
    logic [AXI_STRB_WIDTH-1:0] wstrb_q;
    logic [AXI_DATA_WIDTH-1:0] rdata_q;
    logic                      we_q;

    // Handshake completion tracking
    logic aw_done_q, w_done_q;

    // State machine
    always_comb begin
        state_d = state_q;

        case (state_q)
            AXI_IDLE: begin
                if (mem_req) begin
                    if (mem_we) begin
                        state_d = AXI_AW_WAIT;
                    end else begin
                        state_d = AXI_AR_WAIT;
                    end
                end
            end

            // Read path
            AXI_AR_WAIT: begin
                if (m_axi_arready) begin
                    state_d = AXI_R_WAIT;
                end
            end

            AXI_R_WAIT: begin
                if (m_axi_rvalid) begin
                    state_d = AXI_IDLE;
                end
            end

            // Write path (AW and W can complete in any order)
            AXI_AW_WAIT: begin
                if (m_axi_awready && m_axi_wready) begin
                    // Both ready at same time
                    state_d = AXI_B_WAIT;
                end else if (m_axi_awready) begin
                    state_d = AXI_W_WAIT;
                end else if (m_axi_wready) begin
                    // W done first, wait for AW
                    state_d = AXI_AW_WAIT;  // Stay and track w_done
                end
            end

            AXI_W_WAIT: begin
                if (m_axi_wready) begin
                    state_d = AXI_B_WAIT;
                end
            end

            AXI_B_WAIT: begin
                if (m_axi_bvalid) begin
                    state_d = AXI_IDLE;
                end
            end

            default: state_d = AXI_IDLE;
        endcase
    end

    // Track AW/W completion for parallel handshakes
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            aw_done_q <= 1'b0;
            w_done_q  <= 1'b0;
        end else begin
            if (state_q == AXI_IDLE) begin
                aw_done_q <= 1'b0;
                w_done_q  <= 1'b0;
            end else begin
                if (m_axi_awvalid && m_axi_awready) aw_done_q <= 1'b1;
                if (m_axi_wvalid && m_axi_wready)   w_done_q  <= 1'b1;
            end
        end
    end

    // State register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q <= AXI_IDLE;
        end else begin
            state_q <= state_d;
        end
    end

    // Register inputs on request
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            addr_q  <= '0;
            wdata_q <= '0;
            wstrb_q <= '0;
            we_q    <= 1'b0;
        end else if (state_q == AXI_IDLE && mem_req) begin
            addr_q  <= mem_addr;
            wdata_q <= mem_wdata;
            wstrb_q <= mem_wstrb;
            we_q    <= mem_we;
        end
    end

    // Register read data
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rdata_q <= '0;
        end else if (m_axi_rvalid && m_axi_rready) begin
            rdata_q <= m_axi_rdata;
        end
    end

    // AXI Write Address Channel
    assign m_axi_awaddr  = addr_q;
    assign m_axi_awvalid = (state_q == AXI_AW_WAIT || state_q == AXI_W_WAIT) && !aw_done_q;

    // AXI Write Data Channel
    assign m_axi_wdata  = wdata_q;
    assign m_axi_wstrb  = wstrb_q;
    assign m_axi_wvalid = (state_q == AXI_AW_WAIT || state_q == AXI_W_WAIT) && !w_done_q;

    // AXI Write Response Channel
    assign m_axi_bready = (state_q == AXI_B_WAIT);

    // AXI Read Address Channel
    assign m_axi_araddr  = addr_q;
    assign m_axi_arvalid = (state_q == AXI_AR_WAIT);

    // AXI Read Data Channel
    assign m_axi_rready = (state_q == AXI_R_WAIT);

    // Memory interface outputs
    // Bypass rdata_q register when read is completing to avoid 1-cycle delay
    assign mem_rdata = (state_q == AXI_R_WAIT && m_axi_rvalid) ? m_axi_rdata : rdata_q;
    assign mem_ready = (state_q == AXI_IDLE);
    assign mem_valid = (state_q == AXI_R_WAIT && m_axi_rvalid) ||
                       (state_q == AXI_B_WAIT && m_axi_bvalid);

endmodule
