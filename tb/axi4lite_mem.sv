// AXI4-Lite Memory Model - Simple memory slave for testbench
module axi4lite_mem
    import rv32i_pkg::*;
    import axi4lite_pkg::*;
#(
    parameter int MEM_SIZE_BYTES = 65536,  // 64KB default
    parameter int MEM_LATENCY    = 1       // Response latency in cycles
)(
    input  logic                      clk,
    input  logic                      rst_n,

    // AXI4-Lite Slave Interface
    // Write Address Channel
    input  logic [AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input  logic                      s_axi_awvalid,
    output logic                      s_axi_awready,

    // Write Data Channel
    input  logic [AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input  logic [AXI_STRB_WIDTH-1:0] s_axi_wstrb,
    input  logic                      s_axi_wvalid,
    output logic                      s_axi_wready,

    // Write Response Channel
    output logic [1:0]                s_axi_bresp,
    output logic                      s_axi_bvalid,
    input  logic                      s_axi_bready,

    // Read Address Channel
    input  logic [AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input  logic                      s_axi_arvalid,
    output logic                      s_axi_arready,

    // Read Data Channel
    output logic [AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output logic [1:0]                s_axi_rresp,
    output logic                      s_axi_rvalid,
    input  logic                      s_axi_rready
);

    // Memory array
    localparam int MEM_DEPTH = MEM_SIZE_BYTES / 4;
    logic [31:0] mem [0:MEM_DEPTH-1];

    // State machines
    typedef enum logic [1:0] {
        WR_IDLE,
        WR_DATA,
        WR_RESP
    } wr_state_e;

    typedef enum logic [1:0] {
        RD_IDLE,
        RD_RESP
    } rd_state_e;

    wr_state_e wr_state;
    rd_state_e rd_state;

    // Registered addresses
    logic [AXI_ADDR_WIDTH-1:0] wr_addr;
    logic [AXI_ADDR_WIDTH-1:0] rd_addr;

    // Latency counters
    logic [7:0] wr_latency_cnt;
    logic [7:0] rd_latency_cnt;

    // Word address calculation
    logic [31:0] wr_word_addr;
    logic [31:0] rd_word_addr;

    assign wr_word_addr = wr_addr[31:2];
    assign rd_word_addr = rd_addr[31:2];

    // Write state machine
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_state       <= WR_IDLE;
            wr_addr        <= '0;
            wr_latency_cnt <= '0;
            s_axi_awready  <= 1'b1;
            s_axi_wready   <= 1'b1;
            s_axi_bvalid   <= 1'b0;
            s_axi_bresp    <= AXI_RESP_OKAY;
        end else begin
            case (wr_state)
                WR_IDLE: begin
                    s_axi_awready <= 1'b1;
                    s_axi_wready  <= 1'b1;
                    s_axi_bvalid  <= 1'b0;

                    if (s_axi_awvalid && s_axi_awready) begin
                        wr_addr <= s_axi_awaddr;
                        s_axi_awready <= 1'b0;

                        if (s_axi_wvalid && s_axi_wready) begin
                            // Both address and data ready
                            s_axi_wready <= 1'b0;
                            wr_state <= WR_RESP;
                            wr_latency_cnt <= MEM_LATENCY;

                            // Perform write
                            if (wr_word_addr < MEM_DEPTH) begin
                                if (s_axi_wstrb[0]) mem[s_axi_awaddr[31:2]][7:0]   <= s_axi_wdata[7:0];
                                if (s_axi_wstrb[1]) mem[s_axi_awaddr[31:2]][15:8]  <= s_axi_wdata[15:8];
                                if (s_axi_wstrb[2]) mem[s_axi_awaddr[31:2]][23:16] <= s_axi_wdata[23:16];
                                if (s_axi_wstrb[3]) mem[s_axi_awaddr[31:2]][31:24] <= s_axi_wdata[31:24];
                            end
                        end else begin
                            wr_state <= WR_DATA;
                        end
                    end
                end

                WR_DATA: begin
                    if (s_axi_wvalid && s_axi_wready) begin
                        s_axi_wready <= 1'b0;
                        wr_state <= WR_RESP;
                        wr_latency_cnt <= MEM_LATENCY;

                        // Perform write
                        if (wr_word_addr < MEM_DEPTH) begin
                            if (s_axi_wstrb[0]) mem[wr_word_addr][7:0]   <= s_axi_wdata[7:0];
                            if (s_axi_wstrb[1]) mem[wr_word_addr][15:8]  <= s_axi_wdata[15:8];
                            if (s_axi_wstrb[2]) mem[wr_word_addr][23:16] <= s_axi_wdata[23:16];
                            if (s_axi_wstrb[3]) mem[wr_word_addr][31:24] <= s_axi_wdata[31:24];
                        end
                    end
                end

                WR_RESP: begin
                    if (wr_latency_cnt > 0) begin
                        wr_latency_cnt <= wr_latency_cnt - 1;
                    end else begin
                        s_axi_bvalid <= 1'b1;
                        s_axi_bresp  <= (wr_word_addr < MEM_DEPTH) ? AXI_RESP_OKAY : AXI_RESP_DECERR;

                        if (s_axi_bvalid && s_axi_bready) begin
                            s_axi_bvalid <= 1'b0;
                            wr_state <= WR_IDLE;
                        end
                    end
                end

                default: wr_state <= WR_IDLE;
            endcase
        end
    end

    // Read state machine
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_state       <= RD_IDLE;
            rd_addr        <= '0;
            rd_latency_cnt <= '0;
            s_axi_arready  <= 1'b1;
            s_axi_rvalid   <= 1'b0;
            s_axi_rdata    <= '0;
            s_axi_rresp    <= AXI_RESP_OKAY;
        end else begin
            case (rd_state)
                RD_IDLE: begin
                    s_axi_arready <= 1'b1;
                    s_axi_rvalid  <= 1'b0;

                    if (s_axi_arvalid && s_axi_arready) begin
                        rd_addr <= s_axi_araddr;
                        s_axi_arready <= 1'b0;
                        rd_state <= RD_RESP;
                        rd_latency_cnt <= MEM_LATENCY;
                    end
                end

                RD_RESP: begin
                    if (rd_latency_cnt > 0) begin
                        rd_latency_cnt <= rd_latency_cnt - 1;
                    end else begin
                        s_axi_rvalid <= 1'b1;
                        s_axi_rdata  <= (rd_word_addr < MEM_DEPTH) ? mem[rd_word_addr] : 32'hDEADBEEF;
                        s_axi_rresp  <= (rd_word_addr < MEM_DEPTH) ? AXI_RESP_OKAY : AXI_RESP_DECERR;

                        if (s_axi_rvalid && s_axi_rready) begin
                            s_axi_rvalid <= 1'b0;
                            rd_state <= RD_IDLE;
                        end
                    end
                end

                default: rd_state <= RD_IDLE;
            endcase
        end
    end

    // Memory initialization and debug tasks
    // Initialize memory from hex file
    task automatic load_hex(string filename);
        $readmemh(filename, mem);
    endtask

    // Write a word to memory (for testbench use)
    task automatic write_word(input logic [31:0] addr, input logic [31:0] data);
        if (addr[31:2] < MEM_DEPTH) begin
            mem[addr[31:2]] = data;
        end
    endtask

    // Read a word from memory (for testbench use)
    function automatic logic [31:0] read_word(input logic [31:0] addr);
        if (addr[31:2] < MEM_DEPTH) begin
            return mem[addr[31:2]];
        end else begin
            return 32'hDEADBEEF;
        end
    endfunction

    // Dump memory contents
    task automatic dump_mem(input int start_addr, input int num_words);
        for (int i = 0; i < num_words; i++) begin
            $display("MEM[0x%08h] = 0x%08h", (start_addr + i*4), mem[start_addr/4 + i]);
        end
    endtask

endmodule
