// Verilator main.cpp for RV32I CPU testbench
#include <verilated.h>
#include <verilated_vcd_c.h>
#include "Vtb_rv32i_cpu_top.h"

#include <iostream>
#include <memory>

// Simulation time
vluint64_t sim_time = 0;
vluint64_t max_sim_time = 1000000;  // Maximum simulation time

int main(int argc, char** argv) {
    // Initialize Verilator
    Verilated::commandArgs(argc, argv);
    Verilated::traceEverOn(true);

    // Create DUT instance
    auto dut = std::make_unique<Vtb_rv32i_cpu_top>();

    // Create VCD trace
    auto trace = std::make_unique<VerilatedVcdC>();
    dut->trace(trace.get(), 99);
    trace->open("waveform.vcd");

    std::cout << "Starting RV32I CPU simulation..." << std::endl;

    // Main simulation loop
    while (!Verilated::gotFinish() && sim_time < max_sim_time) {
        // Evaluate model
        dut->eval();

        // Dump trace
        trace->dump(sim_time);

        // Advance time
        sim_time++;
    }

    // Cleanup
    trace->close();
    dut->final();

    std::cout << "Simulation completed at time " << sim_time << std::endl;

    return 0;
}
