    // j1b7 negative control (a1): the dud4 defect class in SoC scope - a constant part-select that lies
    // outside its vector (the frontend substitutes undef) and reaches irq_o.  (The struct-member form of
    // the dud4 bug is Synlig-specific: sv2v flattens struct members to in-range slices, so the plain
    // out-of-range select is the construct that reproduces the same undef substitution under sv2v.)
    logic [7:0] j1b7_v;
    assign j1b7_v = pwdata[7:0];
    logic [3:0] j1b7_oob;
    assign j1b7_oob = j1b7_v[11:8];
    assign irq_o = (irq_en & irq_pending_q) | j1b7_oob[0];
