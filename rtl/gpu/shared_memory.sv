// Shared memory: 16 KiB scratchpad, 32 banks × 128 words × 32 bits/word,
// implemented as 32 instances of the 1RW sram_1rw_128x32_asap7 macro (one per
// bank) so that the array is hardened to SRAM rather than synthesised as a
// ~131 k flip-flop array (which would OOM gpu_top synthesis).
//
// Address layout (14-bit byte address):
//   bank_id   = addr[6:2]   (5 bits — selects 1 of 32 bank macros)
//   word_off  = addr[13:7]  (7 bits — 128 words per bank, macro addr0[6:0])
//   byte_sel  = addr[1:0]   (ignored — 32-bit word accesses only)
//
// Bank-conflict serialisation: each cycle one lane per bank may access it.
// When two or more active lanes hit the same bank the request is spread over
// successive cycles — one conflicting lane per bank per cycle — while
// sh_stall_o is held high.
//
// Read latency: each SRAM macro registers its read (dout0 valid the cycle after
// addr/csb are presented). A read served in cycle T therefore presents data in
// T+1; that data is latched into rdata_q (per lane) and held. The external
// handshake contract is preserved for gpu_compute_unit:
//   - sh_stall_o stays high for the whole access (issue + read-capture),
//   - sh_rvalid_o pulses (while sh_stall_o is still high) the cycle every
//     rdata_q is valid, mirroring the gpu_memory_unit (VLD) capture contract.
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
    output logic                             sh_stall_o,
    output logic                             sh_rvalid_o
);

    localparam int WORD_W = 7;   // log2(SHARED_WORDS) — macro addr0[6:0]
    localparam int BANK_W = 5;   // log2(SHARED_BANKS)

    // -----------------------------------------------------------------------
    // Per-lane request registers
    // -----------------------------------------------------------------------
    logic [N_LANES-1:0]              pending_q;   // lane awaiting macro issue
    logic [N_LANES-1:0]              we_q;
    logic [SHMEM_W-1:0]              addr_q  [N_LANES-1:0];
    logic [31:0]                     wdata_q [N_LANES-1:0];
    logic [31:0]                     rdata_q [N_LANES-1:0];

    // Read-capture pipeline: a read served this cycle is captured next cycle.
    logic [N_LANES-1:0]              rdcap_q;     // lane awaiting dout capture
    logic [BANK_W-1:0]               capbank_q [N_LANES-1:0];

    logic                            busy_q;      // an access is in flight

    // -----------------------------------------------------------------------
    // Per-lane bank / word decode (combinational)
    // -----------------------------------------------------------------------
    logic [BANK_W-1:0] lane_bank [N_LANES-1:0];   // addr[6:2]
    logic [WORD_W-1:0] lane_word [N_LANES-1:0];   // addr[13:7]

    always_comb begin
        for (int l = 0; l < N_LANES; l++) begin
            lane_bank[l] = addr_q[l][6:2];
            lane_word[l] = addr_q[l][13:7];
        end
    end

    // -----------------------------------------------------------------------
    // Bank arbitration: served[l] = 1 iff lane l is pending AND no lower-indexed
    // pending lane maps to the same bank (lowest lane wins each bank each cycle).
    // -----------------------------------------------------------------------
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

    // -----------------------------------------------------------------------
    // Per-bank macro drive (combinational) from the served lane on each bank.
    // served guarantees at most one lane per bank per cycle.
    // -----------------------------------------------------------------------
    logic                    bank_sel  [SHARED_BANKS-1:0];
    logic                    bank_we   [SHARED_BANKS-1:0];
    logic [WORD_W-1:0]       bank_word [SHARED_BANKS-1:0];
    logic [31:0]             bank_din  [SHARED_BANKS-1:0];
    logic [31:0]             bank_dout [SHARED_BANKS-1:0];

    always_comb begin
        for (int b = 0; b < SHARED_BANKS; b++) begin
            bank_sel [b] = 1'b0;
            bank_we  [b] = 1'b0;
            bank_word[b] = '0;
            bank_din [b] = '0;
        end
        for (int l = 0; l < N_LANES; l++) begin
            if (served[l]) begin
                bank_sel [lane_bank[l]] = 1'b1;
                bank_we  [lane_bank[l]] = we_q[l];
                bank_word[lane_bank[l]] = lane_word[l];
                bank_din [lane_bank[l]] = wdata_q[l];
            end
        end
    end

    genvar b;
    generate
    for (b = 0; b < SHARED_BANKS; b++) begin : g_bank
        sram_1rw_128x32_asap7 u_bank (
            .clk0  (clk),
            .csb0  (~bank_sel[b]),     // active-low chip select
            .web0  (~bank_we[b]),      // active-low write enable (low = write)
            .addr0 (bank_word[b]),
            .din0  (bank_din[b]),
            .dout0 (bank_dout[b])
        );
    end : g_bank
    endgenerate

    // -----------------------------------------------------------------------
    // Completion: the access is done (and every rdata_q is valid) when there is
    // nothing left to issue (pending_q==0) and no read awaiting capture
    // (rdcap_q==0). sh_rvalid_o pulses that cycle while sh_stall_o is still high.
    // -----------------------------------------------------------------------
    logic access_done;
    assign access_done = busy_q && (pending_q == '0) && (rdcap_q == '0);

    assign sh_stall_o  = busy_q;
    assign sh_rvalid_o = access_done;

    // -----------------------------------------------------------------------
    // Sequential state
    // -----------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_q <= '0;
            we_q      <= '0;
            rdcap_q   <= '0;
            busy_q    <= 1'b0;
            for (int l = 0; l < N_LANES; l++) begin
                addr_q   [l] <= '0;
                wdata_q  [l] <= '0;
                rdata_q  [l] <= '0;
                capbank_q[l] <= '0;
            end
        end else begin
            // Capture read data presented this cycle by the macros (issued last cycle)
            for (int l = 0; l < N_LANES; l++) begin
                if (rdcap_q[l])
                    rdata_q[l] <= bank_dout[capbank_q[l]];
            end

            // Pipeline the read-capture flag: lanes served as reads this cycle
            // present their data next cycle.
            for (int l = 0; l < N_LANES; l++) begin
                rdcap_q[l] <= served[l] && !we_q[l];
                if (served[l])
                    capbank_q[l] <= lane_bank[l];
            end

            // Retire served lanes from the issue set.
            for (int l = 0; l < N_LANES; l++) begin
                if (served[l])
                    pending_q[l] <= 1'b0;
            end

            // Accept a new request only when fully idle (one-shot guard).
            if (|sh_active_i && !busy_q) begin
                for (int l = 0; l < N_LANES; l++) begin
                    pending_q[l] <= sh_active_i[l];
                    we_q[l]      <= sh_we_i[l];
                    addr_q [l]   <= sh_addr_i[l];
                    wdata_q[l]   <= sh_wdata_i[l];
                end
                busy_q <= 1'b1;
            end else if (access_done) begin
                busy_q <= 1'b0;
            end
        end
    end

    // -----------------------------------------------------------------------
    // Read data output
    // -----------------------------------------------------------------------
    genvar gl;
    generate
    for (gl = 0; gl < N_LANES; gl++) begin : g_rdata
        assign sh_rdata_o[gl] = rdata_q[gl];
    end : g_rdata
    endgenerate

endmodule

`default_nettype wire
