// rv32i_axi_arbiter.sv
// AXI4-Lite Priority Arbiter: Instruction Fetch (IF) vs Memory (MEM)
//
// MEM wins when both requestors are active simultaneously.
// One outstanding transaction at a time (no pipelining of AXI transactions).
//
// Stall signal semantics (to hazard unit):
//   if_axi_stall_o  = IF has an outstanding transaction AND response not yet received
//                     OR IF wants to transact but arbiter is busy with MEM
//                     Deasserted in the SAME cycle the IF response is accepted
//                     so the hazard unit un-stalls IF/ID in time to load the instruction.
//   mem_axi_stall_o = MEM has an outstanding transaction.
//                     Deasserted in the SAME cycle the MEM response is accepted.

module rv32i_axi_arbiter (
    input  logic        clk,
    input  logic        rst_n,

    // ── IF requestor (read-only) ──────────────────────────────────────────────
    input  logic [31:0] if_araddr_i,
    input  logic        if_arvalid_i,
    output logic        if_arready_o,   // 1 when arbiter grants this AR request

    output logic [31:0] if_rdata_o,
    output logic [1:0]  if_rresp_o,
    output logic        if_rvalid_o,
    input  logic        if_rready_i,

    // ── MEM requestor (read + write) ─────────────────────────────────────────
    // Read channel
    input  logic [31:0] mem_araddr_i,
    input  logic        mem_arvalid_i,
    output logic        mem_arready_o,

    output logic [31:0] mem_rdata_o,
    output logic [1:0]  mem_rresp_o,
    output logic        mem_rvalid_o,
    input  logic        mem_rready_i,

    // Write address channel
    input  logic [31:0] mem_awaddr_i,
    input  logic        mem_awvalid_i,
    output logic        mem_awready_o,

    // Write data channel
    input  logic [31:0] mem_wdata_i,
    input  logic [3:0]  mem_wstrb_i,
    input  logic        mem_wvalid_i,
    output logic        mem_wready_o,

    // Write response channel
    input  logic        mem_bready_i,
    output logic        mem_bvalid_o,
    output logic [1:0]  mem_bresp_o,

    // ── AXI4-Lite master output (to external memory/interconnect) ─────────────
    output logic [31:0] axi_araddr_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,

    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    output logic        axi_rready_o,

    output logic [31:0] axi_awaddr_o,
    output logic        axi_awvalid_o,
    input  logic        axi_awready_i,

    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,

    input  logic        axi_bvalid_i,
    input  logic [1:0]  axi_bresp_i,
    output logic        axi_bready_o,

    // ── Stall outputs to hazard unit ──────────────────────────────────────────
    output logic        if_axi_stall_o,   // IF stage must stall
    output logic        mem_axi_stall_o   // MEM stage must stall
);

    // =========================================================================
    // Arbiter FSM
    // =========================================================================
    typedef enum logic [2:0] {
        IDLE         = 3'b000,  // Ready for next transaction
        IF_READ      = 3'b001,  // IF fetch in flight, waiting for rvalid
        MEM_READ     = 3'b010,  // MEM load in flight, waiting for rvalid
        MEM_WRITE    = 3'b011,  // MEM store: waiting for AW+W handshakes and B response
        MEM_WRITE_B  = 3'b100   // MEM store: AW+W done, waiting for bvalid
    } arb_state_t;

    arb_state_t state_q, state_d;

    // Track AW and W channel completions during a write transaction
    logic aw_done_q, w_done_q;
    logic aw_done_d, w_done_d;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q   <= IDLE;
            aw_done_q <= 1'b0;
            w_done_q  <= 1'b0;
        end else begin
            state_q   <= state_d;
            aw_done_q <= aw_done_d;
            w_done_q  <= w_done_d;
        end
    end

    // Shorthand: does MEM have any pending request?
    logic mem_any_req;
    assign mem_any_req = mem_arvalid_i || mem_awvalid_i;

    // =========================================================================
    // Combinational next-state and output logic
    // =========================================================================
    always_comb begin
        // ── FSM default ──────────────────────────────────────────────────────
        state_d    = state_q;
        aw_done_d  = aw_done_q;
        w_done_d   = w_done_q;

        // ── AXI master defaults (all deasserted) ─────────────────────────────
        axi_araddr_o  = 32'h0;
        axi_arvalid_o = 1'b0;
        axi_rready_o  = 1'b0;
        axi_awaddr_o  = 32'h0;
        axi_awvalid_o = 1'b0;
        axi_wdata_o   = 32'h0;
        axi_wstrb_o   = 4'h0;
        axi_wvalid_o  = 1'b0;
        axi_bready_o  = 1'b0;

        // ── IF requestor defaults ─────────────────────────────────────────────
        if_arready_o  = 1'b0;
        if_rvalid_o   = 1'b0;
        if_rdata_o    = 32'h0;
        if_rresp_o    = 2'h0;

        // ── MEM requestor defaults ────────────────────────────────────────────
        mem_arready_o = 1'b0;
        mem_rvalid_o  = 1'b0;
        mem_rdata_o   = 32'h0;
        mem_rresp_o   = 2'h0;
        mem_awready_o = 1'b0;
        mem_wready_o  = 1'b0;
        mem_bvalid_o  = 1'b0;
        mem_bresp_o   = 2'h0;

        // ── Stall defaults ────────────────────────────────────────────────────
        if_axi_stall_o  = 1'b0;
        mem_axi_stall_o = 1'b0;

        case (state_q)
            // ──────────────────────────────────────────────────────────────────
            IDLE: begin
                if (mem_arvalid_i) begin
                    // MEM read request — wins over IF
                    axi_araddr_o    = mem_araddr_i;
                    axi_arvalid_o   = 1'b1;
                    mem_axi_stall_o = 1'b1;
                    // Stall IF if it also wanted to transact
                    if_axi_stall_o  = if_arvalid_i;

                    if (axi_arready_i) begin
                        mem_arready_o = 1'b1;
                        state_d       = MEM_READ;
                    end

                end else if (mem_awvalid_i) begin
                    // MEM write request — wins over IF
                    // Issue AW and W simultaneously
                    axi_awaddr_o    = mem_awaddr_i;
                    axi_awvalid_o   = 1'b1;
                    axi_wdata_o     = mem_wdata_i;
                    axi_wstrb_o     = mem_wstrb_i;
                    axi_wvalid_o    = mem_wvalid_i;
                    mem_axi_stall_o = 1'b1;
                    if_axi_stall_o  = if_arvalid_i;

                    aw_done_d = axi_awready_i;
                    w_done_d  = axi_wready_i && mem_wvalid_i;

                    mem_awready_o = axi_awready_i;
                    mem_wready_o  = axi_wready_i && mem_wvalid_i;

                    if (axi_awready_i && (axi_wready_i && mem_wvalid_i)) begin
                        // Both accepted in the same cycle — go straight to B-wait
                        state_d   = MEM_WRITE_B;
                        aw_done_d = 1'b1;
                        w_done_d  = 1'b1;
                    end else begin
                        state_d = MEM_WRITE;
                    end

                end else if (if_arvalid_i) begin
                    // IF read request (MEM has no request — IF gets the bus)
                    axi_araddr_o   = if_araddr_i;
                    axi_arvalid_o  = 1'b1;
                    if_axi_stall_o = 1'b1;

                    if (axi_arready_i) begin
                        if_arready_o  = 1'b1;
                        state_d       = IF_READ;
                    end
                end
            end

            // ──────────────────────────────────────────────────────────────────
            IF_READ: begin
                // Waiting for instruction data
                axi_rready_o = if_rready_i;
                if_rvalid_o  = axi_rvalid_i;
                if_rdata_o   = axi_rdata_i;
                if_rresp_o   = axi_rresp_i;

                // Keep stall asserted while waiting, deassert when response arrives
                // so the hazard unit un-stalls IF/ID in the same cycle as rvalid.
                if_axi_stall_o = !(axi_rvalid_i && if_rready_i);

                if (axi_rvalid_i && if_rready_i) begin
                    state_d = IDLE;
                end
            end

            // ──────────────────────────────────────────────────────────────────
            MEM_READ: begin
                // Waiting for load data
                axi_rready_o    = mem_rready_i;
                mem_rvalid_o    = axi_rvalid_i;
                mem_rdata_o     = axi_rdata_i;
                mem_rresp_o     = axi_rresp_i;

                // Deassert stall in the same cycle the response is accepted
                mem_axi_stall_o = !(axi_rvalid_i && mem_rready_i);

                if (axi_rvalid_i && mem_rready_i) begin
                    state_d = IDLE;
                end
            end

            // ──────────────────────────────────────────────────────────────────
            MEM_WRITE: begin
                // Waiting for AW and/or W channel handshakes
                mem_axi_stall_o = 1'b1;

                if (!aw_done_q) begin
                    axi_awaddr_o  = mem_awaddr_i;
                    axi_awvalid_o = 1'b1;
                    mem_awready_o = axi_awready_i;
                    if (axi_awready_i) aw_done_d = 1'b1;
                end

                if (!w_done_q) begin
                    axi_wdata_o  = mem_wdata_i;
                    axi_wstrb_o  = mem_wstrb_i;
                    axi_wvalid_o = mem_wvalid_i;
                    mem_wready_o = axi_wready_i && mem_wvalid_i;
                    if (axi_wready_i && mem_wvalid_i) w_done_d = 1'b1;
                end

                // Both AW and W done → wait for write response
                if ((aw_done_q || axi_awready_i) && (w_done_q || (axi_wready_i && mem_wvalid_i))) begin
                    state_d   = MEM_WRITE_B;
                    aw_done_d = 1'b1;
                    w_done_d  = 1'b1;
                end
            end

            // ──────────────────────────────────────────────────────────────────
            MEM_WRITE_B: begin
                // Waiting for write response
                axi_bready_o    = mem_bready_i;
                mem_bvalid_o    = axi_bvalid_i;
                mem_bresp_o     = axi_bresp_i;

                // Deassert stall in same cycle response is accepted
                mem_axi_stall_o = !(axi_bvalid_i && mem_bready_i);

                if (axi_bvalid_i && mem_bready_i) begin
                    state_d   = IDLE;
                    aw_done_d = 1'b0;
                    w_done_d  = 1'b0;
                end
            end

            // ──────────────────────────────────────────────────────────────────
            default: state_d = IDLE;
        endcase
    end

endmodule
