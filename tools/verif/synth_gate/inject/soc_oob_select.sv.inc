    // j1b7 negative control (a1): the dud4 defect class in SoC scope - a constant part-select of a
    // struct member that lies outside the member (yosys substitutes undef) and reaches irq_o.
    typedef struct packed {
        logic [7:0] hi;
        logic [7:0] lo;
    } j1b7_s_t;
    j1b7_s_t j1b7_s;
    assign j1b7_s = pwdata[15:0];
    logic [3:0] j1b7_oob;
    assign j1b7_oob = j1b7_s.lo[11:8];
    assign irq_o = (irq_en & irq_pending_q) | j1b7_oob[0];
