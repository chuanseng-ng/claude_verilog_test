// Memory coalescer: serialises per-lane VLD/VST requests into AXI4 single-beat
// transactions and reassembles read data.
//
// Phase 4 default (GPU_ENABLE_COALESCE=0): one AXI transaction per active lane
// in lane-index order.  The coalescer walks lanes from lowest to highest,
// skipping lanes where mask_i[lane]=0.
//
// AXI4 single-beat: ARLEN=0 / AWLEN=0 hardwired.  All error responses (rresp,
// bresp) are accepted and silently ignored — Phase 4 has no fault model.
//
// State machine per request:
//   IDLE → find first active lane
//        → (load) AR → R → next lane or DONE
//        → (store) AW → W → B → next lane or DONE
//   DONE: assert done_o for one cycle, then return to IDLE.
`default_nettype none

module memory_coalescer
    import gpu_pkg::*;
#(
    /* verilator lint_off UNUSEDPARAM */
    parameter logic GPU_ENABLE_COALESCE = 1'b0  // Phase 4: serial only by default
    /* verilator lint_on UNUSEDPARAM */
)(
    input  logic clk,
    input  logic rst_n,

    // -----------------------------------------------------------------------
    // Request/response — from/to gpu_memory_unit
    // -----------------------------------------------------------------------
    input  logic                          start_i,   // single-cycle pulse
    input  logic                          we_i,      // 1=store, 0=load
    input  logic [N_LANES-1:0][31:0]      addr_i,
    input  logic [N_LANES-1:0][31:0]      wdata_i,
    input  logic [N_LANES-1:0]            mask_i,

    output logic                          done_o,    // single-cycle pulse on completion
    output logic [N_LANES-1:0][31:0]      rdata_o,   // per-lane read results

    // -----------------------------------------------------------------------
    // AXI4 master (32-bit addr/data, single beat)
    // -----------------------------------------------------------------------
    // AR channel
    output logic [31:0]  m_araddr_o,
    output logic         m_arvalid_o,
    input  logic         m_arready_i,
    // R channel
    input  logic [31:0]  m_rdata_i,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]   m_rresp_i,     // accepted, not checked (Phase 4)
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic         m_rvalid_i,
    output logic         m_rready_o,
    // AW channel
    output logic [31:0]  m_awaddr_o,
    output logic         m_awvalid_o,
    input  logic         m_awready_i,
    // W channel
    output logic [31:0]  m_wdata_o,
    output logic [3:0]   m_wstrb_o,
    output logic         m_wvalid_o,
    input  logic         m_wready_i,
    // B channel
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]   m_bresp_i,     // accepted, not checked (Phase 4)
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic         m_bvalid_i,
    output logic         m_bready_o
);

    // -----------------------------------------------------------------------
    // FSM
    // -----------------------------------------------------------------------
    typedef enum logic [2:0] {
        S_IDLE = 3'd0,
        S_AR   = 3'd1,   // issue AXI AR
        S_R    = 3'd2,   // wait for AXI R
        S_AW   = 3'd3,   // issue AXI AW
        S_W    = 3'd4,   // issue AXI W
        S_B    = 3'd5,   // wait for AXI B
        S_DONE = 3'd6    // one-cycle done pulse
    } coal_state_t;

    coal_state_t          state_q;
    logic [2:0]           lane_q;    // current lane being served (0..N_LANES-1)
    logic [N_LANES-1:0][31:0] addr_q;
    logic [N_LANES-1:0][31:0] wdata_q;
    logic [N_LANES-1:0]       mask_q;
    logic [N_LANES-1:0][31:0] rdata_q;

    assign rdata_o = rdata_q;

    // -----------------------------------------------------------------------
    // Combinational next-lane lookups
    // -----------------------------------------------------------------------
    // First active lane in mask_i (used on start_i while still in S_IDLE)
    logic [2:0] first_lane;
    logic       first_found;
    always_comb begin
        first_lane  = '0;
        first_found = 1'b0;
        for (int i = 0; i < N_LANES; i++) begin
            if (!first_found && mask_i[i]) begin
                first_lane  = 3'(i);
                first_found = 1'b1;
            end
        end
    end

    // Next active lane in mask_q after lane_q (used when advancing lanes)
    logic [2:0] next_lane;
    logic       next_found;
    always_comb begin
        next_lane  = '0;
        next_found = 1'b0;
        for (int i = 0; i < N_LANES; i++) begin
            if (!next_found && (i > int'(lane_q)) && mask_q[i]) begin
                next_lane  = 3'(i);
                next_found = 1'b1;
            end
        end
    end

    // -----------------------------------------------------------------------
    // AXI output mux (combinational)
    // -----------------------------------------------------------------------
    always_comb begin
        m_araddr_o  = addr_q[lane_q];
        m_arvalid_o = (state_q == S_AR);
        m_rready_o  = (state_q == S_R);
        m_awaddr_o  = addr_q[lane_q];
        m_awvalid_o = (state_q == S_AW);
        m_wdata_o   = wdata_q[lane_q];
        m_wstrb_o   = 4'hF;             // full 32-bit write
        m_wvalid_o  = (state_q == S_W);
        m_bready_o  = (state_q == S_B);
        done_o      = (state_q == S_DONE);
    end

    // -----------------------------------------------------------------------
    // FSM sequencer
    // -----------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q <= S_IDLE;
            lane_q  <= '0;
            addr_q  <= '0;
            wdata_q <= '0;
            mask_q  <= '0;
            rdata_q <= '0;
        end else begin
            unique case (state_q)

                S_IDLE: begin
                    if (start_i) begin
                        addr_q  <= addr_i;
                        wdata_q <= wdata_i;
                        mask_q  <= mask_i;
                        rdata_q <= '0;
                        if (first_found) begin
                            lane_q  <= first_lane;
                            state_q <= we_i ? S_AW : S_AR;
                        end else begin
                            state_q <= S_DONE;  // mask all-zero
                        end
                    end
                end

                S_AR: begin
                    if (m_arready_i) state_q <= S_R;
                end

                S_R: begin
                    if (m_rvalid_i) begin
                        rdata_q[lane_q] <= m_rdata_i;
                        if (next_found) begin
                            lane_q  <= next_lane;
                            state_q <= S_AR;
                        end else begin
                            state_q <= S_DONE;
                        end
                    end
                end

                S_AW: begin
                    if (m_awready_i) state_q <= S_W;
                end

                S_W: begin
                    if (m_wready_i) state_q <= S_B;
                end

                S_B: begin
                    if (m_bvalid_i) begin
                        if (next_found) begin
                            lane_q  <= next_lane;
                            state_q <= S_AW;
                        end else begin
                            state_q <= S_DONE;
                        end
                    end
                end

                S_DONE: begin
                    state_q <= S_IDLE;
                end

                default: state_q <= S_IDLE;

            endcase
        end
    end

endmodule

`default_nettype wire
