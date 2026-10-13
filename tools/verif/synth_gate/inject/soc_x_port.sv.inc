    // j1b7 negative control (a2): an instance input port tied to 'x in SoC scope, result reaches irq_o.
    logic j1b7_sync_q;
    cdc_sync #(.WIDTH(1)) u_j1b7_x (.clk_i(clk), .rst_n_i(rst_n), .d_i(1'bx), .q_o(j1b7_sync_q));
    assign irq_o = (irq_en & irq_pending_q) | j1b7_sync_q;
