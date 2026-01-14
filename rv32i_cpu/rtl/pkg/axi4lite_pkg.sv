// AXI4-Lite Package - Defines types and parameters for AXI4-Lite interface
package axi4lite_pkg;

    // ============================================================================
    // AXI4-Lite Parameters
    // ============================================================================
    parameter int AXI_ADDR_WIDTH = 32;
    parameter int AXI_DATA_WIDTH = 32;
    parameter int AXI_STRB_WIDTH = AXI_DATA_WIDTH / 8;

    // ============================================================================
    // AXI4-Lite Response Codes
    // ============================================================================
    typedef enum logic [1:0] {
        AXI_RESP_OKAY   = 2'b00,    // Normal access success
        AXI_RESP_EXOKAY = 2'b01,    // Exclusive access success
        AXI_RESP_SLVERR = 2'b10,    // Slave error
        AXI_RESP_DECERR = 2'b11     // Decode error
    } axi_resp_e;

    // ============================================================================
    // AXI4-Lite Master Interface Signals (from master's perspective)
    // ============================================================================

    // Write Address Channel
    typedef struct packed {
        logic [AXI_ADDR_WIDTH-1:0] awaddr;
        logic                      awvalid;
    } axi_aw_m2s_t;

    typedef struct packed {
        logic                      awready;
    } axi_aw_s2m_t;

    // Write Data Channel
    typedef struct packed {
        logic [AXI_DATA_WIDTH-1:0] wdata;
        logic [AXI_STRB_WIDTH-1:0] wstrb;
        logic                      wvalid;
    } axi_w_m2s_t;

    typedef struct packed {
        logic                      wready;
    } axi_w_s2m_t;

    // Write Response Channel
    typedef struct packed {
        logic                      bready;
    } axi_b_m2s_t;

    typedef struct packed {
        axi_resp_e                 bresp;
        logic                      bvalid;
    } axi_b_s2m_t;

    // Read Address Channel
    typedef struct packed {
        logic [AXI_ADDR_WIDTH-1:0] araddr;
        logic                      arvalid;
    } axi_ar_m2s_t;

    typedef struct packed {
        logic                      arready;
    } axi_ar_s2m_t;

    // Read Data Channel
    typedef struct packed {
        logic                      rready;
    } axi_r_m2s_t;

    typedef struct packed {
        logic [AXI_DATA_WIDTH-1:0] rdata;
        axi_resp_e                 rresp;
        logic                      rvalid;
    } axi_r_s2m_t;

    // ============================================================================
    // Combined AXI4-Lite Interface Structures
    // ============================================================================

    // Master to Slave signals
    typedef struct packed {
        axi_aw_m2s_t aw;
        axi_w_m2s_t  w;
        axi_b_m2s_t  b;
        axi_ar_m2s_t ar;
        axi_r_m2s_t  r;
    } axi4lite_m2s_t;

    // Slave to Master signals
    typedef struct packed {
        axi_aw_s2m_t aw;
        axi_w_s2m_t  w;
        axi_b_s2m_t  b;
        axi_ar_s2m_t ar;
        axi_r_s2m_t  r;
    } axi4lite_s2m_t;

    // ============================================================================
    // AXI4-Lite Master FSM States
    // ============================================================================
    typedef enum logic [2:0] {
        AXI_IDLE      = 3'b000,
        AXI_AR_WAIT   = 3'b001,    // Waiting for AR handshake
        AXI_R_WAIT    = 3'b010,    // Waiting for R handshake
        AXI_AW_WAIT   = 3'b011,    // Waiting for AW handshake
        AXI_W_WAIT    = 3'b100,    // Waiting for W handshake
        AXI_B_WAIT    = 3'b101     // Waiting for B handshake
    } axi_master_state_e;

    // ============================================================================
    // AXI4-Lite Slave FSM States
    // ============================================================================
    typedef enum logic [1:0] {
        AXI_SLV_IDLE     = 2'b00,
        AXI_SLV_RD_RESP  = 2'b01,
        AXI_SLV_WR_RESP  = 2'b10
    } axi_slave_state_e;

endpackage
