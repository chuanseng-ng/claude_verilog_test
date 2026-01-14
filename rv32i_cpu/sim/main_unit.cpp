// Verilator main.cpp for unit tests (generic)
#include <verilated.h>
#include <iostream>

// Forward declaration - Verilator will generate the actual class
// This file works with any unit test module

int main(int argc, char** argv) {
    // Initialize Verilator
    Verilated::commandArgs(argc, argv);

    std::cout << "Starting unit test simulation..." << std::endl;

    // Note: The actual test execution is handled by the SystemVerilog
    // testbench's initial block. Verilator will call $finish when done.

    // For unit tests, we use a simpler approach without VCD
    // The testbench handles everything

    return 0;
}
