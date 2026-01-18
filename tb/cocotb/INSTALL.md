# cocotb Installation Guide

Quick guide to install cocotb and simulators for testing.

## Prerequisites

- Python 3.10+ (✅ Already installed: Python 3.13.2)
- cocotb (✅ Already installed: 2.0.1)
- A Verilog/SystemVerilog simulator

## Step 1: cocotb Installation (Already Complete ✅)

```bash
pip install cocotb cocotb-bus
```

**Status**: ✅ Installed (cocotb 2.0.1)

## Step 2: Install a Simulator

You need one of the following simulators. Choose the easiest for your platform.

### Option A: Icarus Verilog (Easiest for Windows)

**Recommended for**: Quick setup, learning, initial testing

#### Windows Installation

**Method 1: Chocolatey (Recommended)**

```bash
# If you have Chocolatey installed
choco install iverilog
```

**Method 2: Direct Download**

1. Download from: http://bleyer.org/icarus/
2. Run installer
3. Add to PATH: `C:\iverilog\bin`
4. Verify: `iverilog -v`

**Method 3: WSL**

```bash
# In WSL
sudo apt-get update
sudo apt-get install iverilog
```

#### Linux/WSL Installation

```bash
sudo apt-get update
sudo apt-get install iverilog
```

#### Verification

```bash
iverilog -v
```

### Option B: Verilator (Best Performance)

**Recommended for**: Large designs, performance, Phase 1+ testing

#### Windows Installation (via WSL)

```bash
# In WSL
sudo apt-get update
sudo apt-get install verilator
```

#### Linux Installation

```bash
sudo apt-get update
sudo apt-get install verilator
```

#### Verification

```bash
verilator --version
```

### Option C: Vivado (If You Have Xilinx Tools)

**Status**: ✅ Detected in PATH: `C:/Xilinx/Vivado/2024.1/bin`

You can use Vivado simulator (xsim):

```bash
make SIM=xcelium  # May need configuration
```

## Step 3: Verify Installation

### Quick Test

```bash
cd tb/cocotb/cpu

# With Icarus Verilog
make -f Makefile.example SIM=icarus

# With Verilator
make -f Makefile.example SIM=verilator

# Expected output:
# ✓ All 3 tests pass
# ✓ No errors
```

### What Success Looks Like

```text
test_counter_basic PASSED
test_counter_disable PASSED
test_counter_reset PASSED

Results:
========================================
  3 tests passed
  0 tests failed
  0 tests skipped
========================================
```

## Troubleshooting

### "cocotb not found"

```bash
pip install --upgrade cocotb cocotb-bus
python -c "import cocotb; print(cocotb.__version__)"
```

### "iverilog not found"

```bash
# Windows: Install via Chocolatey or direct download
# Linux/WSL: sudo apt-get install iverilog
# Verify it's in PATH: which iverilog
```

### "verilator not found"

```bash
# Use WSL for Windows
# Linux: sudo apt-get install verilator
# macOS: brew install verilator
```

### "Permission denied" on Windows

```bash
# Run Git Bash or PowerShell as Administrator
# Or use WSL instead
```

### Simulation hangs

```bash
# Add timeout to test
@cocotb.test(timeout_time=1000, timeout_unit="us")
```

### Import errors

```bash
# Ensure you're in the right directory
cd tb/cocotb/cpu

# Check Python can find modules
python -c "import sys; print(sys.path)"
```

## Next Steps After Installation

1. **Verify cocotb works**:

   ```bash
   cd tb/cocotb/cpu
   make -f Makefile.example SIM=icarus
   ```

2. **Explore examples**:
   - Look at `test_example_counter.py` for basic cocotb structure
   - Look at `test_cpu_basic.py` for CPU test templates

3. **Wait for Phase 1 RTL**:
   - CPU tests will run once RTL is implemented
   - Templates are ready in `test_cpu_basic.py`

4. **Read documentation**:
   - `tb/cocotb/README.md` - Complete cocotb infrastructure guide
   - `docs/verification/VERIFICATION_PLAN.md` - Verification strategy

## Recommended Setup for This Project

**For Windows users**:

1. ✅ Install cocotb (done)
2. Install Icarus Verilog via Chocolatey
3. Test with example: `make -f Makefile.example SIM=icarus`
4. For Phase 1+: Consider using WSL + Verilator for better performance

**For Linux/WSL users**:

1. ✅ Install cocotb (done)
2. Install both Icarus and Verilator: `sudo apt-get install iverilog verilator`
3. Use Icarus for quick tests, Verilator for performance

## Installation Status Checklist

- [x] Python 3.10+ installed
- [x] cocotb installed (2.0.1)
- [ ] Icarus Verilog installed
- [x] Verilator installed (optional)
- [ ] Waveform viewer installed (GTKWave recommended)
- [x] cocotb infrastructure created
- [x] Example tests ready

## Quick Commands Reference

```bash
# Install cocotb
pip install cocotb cocotb-bus

# Install Icarus (Linux/WSL)
sudo apt-get install iverilog

# Install Verilator (Linux/WSL)
sudo apt-get install verilator

# Install GTKWave (waveform viewer)
sudo apt-get install gtkwave  # Linux
choco install gtkwave          # Windows

# Test cocotb
cd tb/cocotb/cpu
make -f Makefile.example

# View waveforms
gtkwave dump.vcd
```

## Support

If you encounter issues:

1. Check this guide
2. Check `tb/cocotb/README.md`
3. Check cocotb docs: https://docs.cocotb.org/
4. Check simulator docs
