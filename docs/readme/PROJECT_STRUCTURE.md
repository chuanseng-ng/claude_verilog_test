# Project Structure

```text
├── docs/                         # Specifications (Phase 0)
│   ├── ROADMAP.md                # Project phases and plan
│   ├── PHASE_STATUS.md           # Current phase status
│   ├── readme/                   # README detail set (this directory)
│   ├── design/
│   │   ├── PHASE0_ARCHITECTURE_SPEC.md   # CPU architectural spec
│   │   ├── PHASE1_ARCHITECTURE_SPEC.md   # CPU implementation spec (Phase 1)
│   │   ├── PHASE4_GPU_ARCHITECTURE_SPEC.md # GPU architecture spec (Phase 4)
│   │   ├── RTL_DEFINITION.md     # Interface signal definitions
│   │   ├── MEMORY_MAP.md         # Address space and registers
│   │   └── REFERENCE_MODEL_SPEC.md # Python reference model API
│   └── verification/
│       └── VERIFICATION_PLAN.md  # Verification strategy
├── tb/                           # Testbench and reference models
│   ├── models/                   # Python reference models (Phase 0)
│   │   ├── rv32i_model.py        # CPU instruction-accurate model
│   │   ├── gpu_kernel_model.py   # GPU SIMT execution model
│   │   └── memory_model.py       # Memory system model
│   ├── tests/                    # Unit tests for reference models
│   │   ├── test_rv32i_model.py
│   │   ├── test_gpu_model.py
│   │   └── test_memory_model.py
│   └── cocotb/                   # cocotb testbenches (Phase 1+)
├── rtl/                          # RTL source files
│   ├── cpu/                      # ✅ Phase 2 CPU (14 modules, ~3000 lines)
│   │   ├── core/                 # Pipeline stages, hazard/forward units, CSR
│   │   │   ├── pipeline/         # IF, ID, EX, MEM, WB stages
│   │   │   ├── rv32i_hazard_unit.sv
│   │   │   ├── rv32i_forwarding_unit.sv
│   │   │   ├── rv32i_csr_file.sv
│   │   │   ├── rv32i_interrupt_ctrl.sv
│   │   │   └── ...
│   │   ├── rv32i_cpu_top.sv      # Top-level with AXI4-Lite + APB3
│   │   └── rv32i_axi_arbiter.sv  # IF/MEM priority arbiter
│   ├── gpu/                      # ✅ Phase 4 GPU-Lite (9 modules; ASAP7 571 MHz signoff)
│   ├── mem/                      # ✅ Phase 3 caches (~1,424 lines)
│   │   ├── rv32i_cache_pkg.sv    # Cache parameters and types
│   │   ├── rv32i_icache.sv       # I-cache (4 KB, direct-mapped, FENCE.I)
│   │   ├── rv32i_dcache.sv       # D-cache (4 KB, write-back + write-allocate)
│   │   └── rv32i_cache_arbiter.sv # D$ priority AXI arbiter
│   ├── periph/                   # ✅ Phase 5 UART, SPI, timer, IRQ ctrl, DMA (M4/M5); Phase 6 GPIO, PWM, WDT, TRNG, I2C, CRYPTO
│   ├── npu/                      # ✅ Phase 6c INT8 4×4 NPU (npu_top, npu_mac_array, npu_weight_mem)
│   ├── fpga/                     # 🚧 FPGA Stage 0: block-RAM arms behind the FPGA define (epic hlrm)
│   └── soc/                      # ✅ Phase 5 SoC: AXI4 crossbar, AXI-Lite/APB fabric, SRAM ctrl, PMU, PLL, async bridge, soc_top
│       ├── cdc/                  # cdc_sync, cdc_reset_sync, cdc_gray_fifo (cdc_2ff_sync renamed to cdc_sync, PR #277)
│       └── dft/                  # 🚧 DFT Stage 1a/1b: jtag_tap, dft_ctrl, dft_clk_switch, dft_clk_mux, dft_rst_mux, dft_ctrl_ports
├── tools/                        # Helper scripts: fpga/ (Stage 0 synthesis), dft/ (scan checks), cdc/, verif/, eda/
├── micro_p/                      # Phase 1 single-cycle CPU (archived)
├── sim/                          # Simulation scripts (Phase 1+)
└── CLAUDE.md                     # Claude Code instructions
```
