// boot_rom.sv
// Phase 5 (M8) — Behavioral AXI4 read-only boot ROM.
//
// 4 KB (1024 × 32-bit words), mapped at SOC_ROM_BASE = 0x0000_1000.
// Optionally pre-loaded via $readmemh (MEM_INIT_FILE parameter).
//
// Protocol:
//   Read  — INCR bursts of any length supported; returns OKAY.
//   Write — accepted on AW+W channels (to avoid stalling), always responds
//           SLVERR (read-only memory).
//
// Ports mirror sram_controller.sv exactly so the crossbar can use either
// as a generic AXI4 slave.
//
// Coding conventions: `default_nettype none, synchronous reset, no #delays,
// no initial blocks in synthesisable path.  $readmemh is in an initial block
// (behavioral ROM pre-load, identical pattern to sram_controller.sv).
//
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module boot_rom
    import axi_pkg::*;
    import soc_addr_map_pkg::*;
#(
    parameter int unsigned AW       = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW       = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW       = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW       = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW     = axi_pkg::AXI_LEN_WIDTH,
    // ROM depth in 32-bit words (must be a power of two; 1024 = 4 KB).
    parameter int unsigned MEM_WORDS    = 1024,
    // Optional hex image.  Empty string → ROM contains 0 after reset.
    parameter string       MEM_INIT_FILE = ""
) (
    input  logic clk,
    input  logic rst_n,

    // ── Write address channel (accept, then SLVERR) ──────────────────────────
    input  logic [IW-1:0]   s_awid,
    input  logic [AW-1:0]   s_awaddr,
    input  logic [LENW-1:0] s_awlen,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]      s_awsize,
    input  logic [1:0]      s_awburst,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic            s_awvalid,
    output logic            s_awready,

    // ── Write data channel (accept, discard) ────────────────────────────────
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [DW-1:0]   s_wdata,
    input  logic [SW-1:0]   s_wstrb,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic            s_wlast,
    input  logic            s_wvalid,
    output logic            s_wready,

    // ── Write response channel (SLVERR) ─────────────────────────────────────
    output logic [IW-1:0]   s_bid,
    output logic [1:0]      s_bresp,
    output logic            s_bvalid,
    input  logic            s_bready,

    // ── Read address channel ─────────────────────────────────────────────────
    input  logic [IW-1:0]   s_arid,
    input  logic [AW-1:0]   s_araddr,
    input  logic [LENW-1:0] s_arlen,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]      s_arsize,
    input  logic [1:0]      s_arburst,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic            s_arvalid,
    output logic            s_arready,

    // ── Read data channel ────────────────────────────────────────────────────
    output logic [IW-1:0]   s_rid,
    output logic [DW-1:0]   s_rdata,
    output logic [1:0]      s_rresp,
    output logic            s_rlast,
    output logic            s_rvalid,
    input  logic            s_rready
);

    // ── Local geometry ───────────────────────────────────────────────────────
    localparam int unsigned IDX_W    = $clog2(MEM_WORDS);
    localparam int unsigned ADDR_LSB = 2;   // 4-byte word addressing

    // ── ROM array ────────────────────────────────────────────────────────────
    logic [DW-1:0] mem [MEM_WORDS];

    // Pre-load from hex file if provided (behavioral only; ignored by synthesis).
    /* verilator lint_off INITIALDLY */
    initial begin
        if (MEM_INIT_FILE != "") begin
            $readmemh(MEM_INIT_FILE, mem);
        end else begin
            for (int i = 0; i < int'(MEM_WORDS); i++) mem[i] = '0;
        end
    end
    /* verilator lint_on  INITIALDLY */

    // =========================================================================
    // WRITE engine — accept burst, respond SLVERR (ROM is read-only)
    // =========================================================================
    typedef enum logic [1:0] {
        W_IDLE,
        W_AW,       // waiting for AW handshake
        W_DATA,     // draining write data beats
        W_RESP      // waiting for B handshake
    } wr_state_e;

    wr_state_e  w_state_q;
    logic [IW-1:0]   w_id_q;
    logic [LENW-1:0] w_cnt_q;   // beats remaining (counts down from awlen)

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            w_state_q <= W_IDLE;
            w_id_q    <= '0;
            w_cnt_q   <= '0;
        end else begin
            unique case (w_state_q)
                W_IDLE: begin
                    if (s_awvalid && s_awready) begin
                        w_id_q    <= s_awid;
                        w_cnt_q   <= s_awlen;
                        w_state_q <= W_DATA;
                    end
                end
                W_DATA: begin
                    if (s_wvalid && s_wready) begin
                        if (s_wlast || w_cnt_q == '0) begin
                            w_state_q <= W_RESP;
                        end else begin
                            w_cnt_q <= w_cnt_q - 1'b1;
                        end
                    end
                end
                W_RESP: begin
                    if (s_bvalid && s_bready) begin
                        w_state_q <= W_IDLE;
                    end
                end
                default: w_state_q <= W_IDLE;
            endcase
        end
    end

    assign s_awready = (w_state_q == W_IDLE);
    assign s_wready  = (w_state_q == W_DATA);
    assign s_bvalid  = (w_state_q == W_RESP);
    assign s_bid     = w_id_q;
    assign s_bresp   = AXI_RESP_SLVERR;    // ROM: writes always error

    // =========================================================================
    // READ engine — INCR bursts, OKAY response
    // =========================================================================
    typedef enum logic [1:0] {
        R_IDLE,
        R_BUSY      // transferring read data beats
    } rd_state_e;

    rd_state_e  r_state_q;
    logic [IW-1:0]   r_id_q;
    logic [AW-1:0]   r_addr_q;      // current beat byte address
    logic [LENW-1:0] r_beats_rem_q; // beats still to send (awlen down to 0)
    logic            r_last_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            r_state_q     <= R_IDLE;
            r_id_q        <= '0;
            r_addr_q      <= '0;
            r_beats_rem_q <= '0;
            r_last_q      <= 1'b0;
        end else begin
            unique case (r_state_q)
                R_IDLE: begin
                    if (s_arvalid && s_arready) begin
                        r_id_q        <= s_arid;
                        r_addr_q      <= s_araddr;
                        r_beats_rem_q <= s_arlen;
                        r_last_q      <= (s_arlen == '0);
                        r_state_q     <= R_BUSY;
                    end
                end
                R_BUSY: begin
                    if (s_rvalid && s_rready) begin
                        if (r_last_q) begin
                            r_state_q <= R_IDLE;
                        end else begin
                            r_addr_q      <= r_addr_q + 32'd4;  // INCR, 4-byte beat
                            r_beats_rem_q <= r_beats_rem_q - 1'b1;
                            r_last_q      <= (r_beats_rem_q == {{(LENW-1){1'b0}}, 1'b1});
                        end
                    end
                end
                default: r_state_q <= R_IDLE;
            endcase
        end
    end

    // Word index: strip byte offset and mask to ROM depth.
    logic [IDX_W-1:0] r_idx;
    assign r_idx = r_addr_q[ADDR_LSB +: IDX_W];

    assign s_arready = (r_state_q == R_IDLE);
    assign s_rvalid  = (r_state_q == R_BUSY);
    assign s_rid     = r_id_q;
    assign s_rdata   = mem[r_idx];
    assign s_rresp   = AXI_RESP_OKAY;
    assign s_rlast   = r_last_q;

endmodule : boot_rom
/* verilator lint_on  UNUSEDPARAM */
