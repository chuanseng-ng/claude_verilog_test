// Shared memory: 16 KiB scratchpad, 32 banks × 128 words × 32 bits/word.
//
// Address layout (14-bit byte address):
//   bank_id   = addr[6:2]   (5 bits — low-order word-address bits mod 32)
//   word_off  = addr[13:7]  (7 bits — 128 words per bank)
//   byte_sel  = addr[1:0]   (ignored — 32-bit word accesses only)
//
// Bank-conflict serialisation: each cycle one lane per bank may access it.
// When two or more active lanes hit the same bank the request is spread over
// successive cycles — one conflicting lane per bank per cycle — while
// sh_stall_o is held high.  The read data for each lane is captured in
// rdata_q[] and remains valid after sh_stall_o drops.
`default_nettype none

module shared_memory
    import gpu_pkg::*;
(
    input  logic clk,
    input  logic rst_n,

    // -----------------------------------------------------------------------
    // Per-lane request interface (from gpu_compute_unit)
    // -----------------------------------------------------------------------
    input  logic [N_LANES-1:0][SHMEM_W-1:0] sh_addr_i,       // 14-bit byte address
    input  logic [N_LANES-1:0]               sh_we_i,
    input  logic [N_LANES-1:0][31:0]         sh_wdata_i,
    input  logic [N_LANES-1:0]               sh_active_i,

    output logic [N_LANES-1:0][31:0]         sh_rdata_o,
    output logic                             sh_stall_o
);

    // -----------------------------------------------------------------------
    // Bank storage: 32 banks × 128 words × 32 bits
    // -----------------------------------------------------------------------
    logic [31:0] bank_mem [SHARED_BANKS-1:0][SHARED_WORDS-1:0];

    // -----------------------------------------------------------------------
    // Per-lane request registers
    // -----------------------------------------------------------------------
    logic [N_LANES-1:0]               pending_q;
    logic [N_LANES-1:0]               we_q;
    logic [SHMEM_W-1:0]              addr_q  [N_LANES-1:0];
    logic [31:0]                      wdata_q [N_LANES-1:0];
    logic [31:0]                      rdata_q [N_LANES-1:0];

    // -----------------------------------------------------------------------
    // Bank index per lane (combinational)
    // -----------------------------------------------------------------------
    logic [4:0] lane_bank [N_LANES-1:0];   // addr[6:2]
    logic [6:0] lane_word [N_LANES-1:0];   // addr[13:7]

    always_comb begin
        for (int l = 0; l < N_LANES; l++) begin
            lane_bank[l] = addr_q[l][6:2];
            lane_word[l] = addr_q[l][13:7];
        end
    end

    // -----------------------------------------------------------------------
    // Bank-arbitration: which pending lanes are served this cycle
    // -----------------------------------------------------------------------
    // served[l] = 1 iff lane l is pending AND no lower-indexed pending lane
    // maps to the same bank (lowest lane wins each bank each cycle).
    logic [N_LANES-1:0] served;

    always_comb begin
        for (int l = 0; l < N_LANES; l++) begin
            served[l] = pending_q[l];
            for (int k = 0; k < l; k++) begin
                if (pending_q[k] && (lane_bank[k] == lane_bank[l]))
                    served[l] = 1'b0;
            end
        end
    end

    assign sh_stall_o = |pending_q;

    // -----------------------------------------------------------------------
    // Sequential state update
    // -----------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_q <= '0;
            we_q      <= '0;
            for (int l = 0; l < N_LANES; l++) begin
                addr_q [l] <= '0;
                wdata_q[l] <= '0;
                rdata_q[l] <= '0;
            end
        end else begin
            // Accept a new request only when the previous one is fully served
            if (|sh_active_i && !sh_stall_o) begin
                for (int l = 0; l < N_LANES; l++) begin
                    pending_q[l] <= sh_active_i[l];
                    we_q[l]      <= sh_we_i[l];
                    addr_q [l]   <= sh_addr_i[l];
                    wdata_q[l]   <= sh_wdata_i[l];
                    rdata_q[l]   <= '0;
                end
            end

            // Service arbitration winners this cycle
            for (int l = 0; l < N_LANES; l++) begin
                if (served[l]) begin
                    pending_q[l] <= 1'b0;
                    if (we_q[l])
                        bank_mem[lane_bank[l]][lane_word[l]] <= wdata_q[l];
                    else
                        rdata_q[l] <= bank_mem[lane_bank[l]][lane_word[l]];
                end
            end
        end
    end

    // -----------------------------------------------------------------------
    // Read data output
    // -----------------------------------------------------------------------
    for (genvar l = 0; l < N_LANES; l++) begin : g_rdata
        assign sh_rdata_o[l] = rdata_q[l];
    end : g_rdata

endmodule

`default_nettype wire
