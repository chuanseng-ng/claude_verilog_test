// Blackbox of the ASAP7 clock-gate cell instantiated by rv32i_clock_gate.sv under USE_ICG_CELL, so the
// ASAP7 SoC can be elaborated by plain yosys without the PDK models (bead j1b7 gate, elaboration only).
(* blackbox *)
module ICGx1_ASAP7_75t_R (
    input  CLK,
    input  ENA,
    input  SE,
    output GCLK
);
endmodule
