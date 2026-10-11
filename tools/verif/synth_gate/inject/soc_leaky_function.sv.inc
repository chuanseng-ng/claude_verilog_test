    // j1b7 negative control (b): the function leaves its result unassigned when c == 0 and the
    // value reaches the irq_o output port.  A gate that skipped every $func$ net by name would miss it.
    function automatic logic [3:0] j1b7_leaky(input logic [3:0] v, input logic c);
        if (c) j1b7_leaky = v;
    endfunction
    logic [3:0] j1b7_leak_o;
    assign j1b7_leak_o = j1b7_leaky(pwdata[3:0], pstrb[0]);
    assign irq_o = (irq_en & irq_pending_q) | j1b7_leak_o[0];
