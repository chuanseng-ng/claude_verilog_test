// Verilator main.cpp for RV32I CPU testbench with --timing mode
#include <verilated.h>
#include <verilated_vcd_c.h>
#include "Vtb_rv32i_cpu_top.h"

#include <iostream>
#include <memory>

int main(int argc, char** argv) {
    // Set up context
    const std::unique_ptr<VerilatedContext> contextp{new VerilatedContext};
    contextp->commandArgs(argc, argv);
    contextp->traceEverOn(true);

    // Create DUT
    const std::unique_ptr<Vtb_rv32i_cpu_top> dut{new Vtb_rv32i_cpu_top{contextp.get()}};

    // Set up VCD tracing
    VerilatedVcdC* tfp = new VerilatedVcdC;
    dut->trace(tfp, 99);
    tfp->open("waveform.vcd");

    std::cout << "Starting RV32I CPU simulation..." << std::endl;

    // Run simulation - timing scheduler handles clock generation from testbench
    while (!contextp->gotFinish()) {
        // Evaluate design
        dut->eval();

        // Dump waveform
        tfp->dump(contextp->time());

        // Advance time to next event
        contextp->timeInc(1);
    }

    // Cleanup
    dut->final();
    tfp->close();
    delete tfp;

    std::cout << "Simulation completed at time " << contextp->time() << std::endl;

    return 0;
}
