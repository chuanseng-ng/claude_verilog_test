{
  description = "RV32I + GPU-lite SoC — simulation & lint dev environment (Verilator/iverilog).";

  # Pinned to nixos-unstable for Verilator >= 5.036 (CI requires v5.036; nixos-25.05
  # ships only 5.034). flake.lock pins the exact nixpkgs rev, so the build is
  # reproducible regardless of the "unstable" channel name.
  #
  # Scope: SIMULATION + LINT ONLY. This shell intentionally provides the EDA/system
  # toolchain (Verilator, iverilog, gcc, make) but NOT a Python interpreter. The
  # cocotb Python stack (cocotb, pyuvm, cocotbext-axi, cocotb-bus) stays on the
  # system Python + pip (`requirements.txt`), exactly as today. Reasons:
  #   * sim/Makefile is tuned for "nix Verilator + system Python 3.10" — it hardcodes
  #     BUILD_ARGS += PYTHON3=/usr/bin/python3 and a g++ shim (cxx_shim.sh) to dodge a
  #     documented nix-3.11 vs system-3.10 verilator_includer crash. Adding a nix
  #     Python would re-trigger that mismatch.
  #   * pyuvm / cocotbext-axi / cocotb-bus are not packaged in nixpkgs anyway.
  # Synthesis / PnR is OUT OF SCOPE here — it stays on the external librelane nix env
  # (~/Downloads/Github/librelane) invoked by pnr/Makefile.

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f:
        nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      # Expose the pinned Verilator as a package so CI can put just the binary on
      # PATH (`nix profile install .#verilator`) and compile/run the cocotb sim in
      # the system shell with the system g++/glibc. Linking Vtop with the nix gcc
      # instead makes it use the nix glibc loader, which mixes badly with the
      # system Python/libffi at runtime (segfaults on the CI runner). The local
      # `nix develop` shell still bundles gcc for convenience.
      packages = forAllSystems (pkgs: {
        verilator = pkgs.verilator;
        default = pkgs.verilator;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          name = "soc-sim-lint";

          packages = with pkgs; [
            verilator   # >= 5.036 (5.048 on the pinned rev)
            iverilog    # Icarus Verilog (alternate SIM=icarus path)
            gcc         # g++ for Verilator-generated C++ (via sim/cxx_shim.sh)
            gnumake
            ccache
            gtkwave     # optional waveform viewer
            git
          ];

          shellHook = ''
            echo "soc sim+lint env ready — Verilator $(verilator --version | head -1 | awk '{print $2}')"
            echo "Python/cocotb come from system + pip: 'pip install -r requirements.txt cocotb-bus cocotbext-axi'"
          '';
        };

        # Bare-metal RISC-V cross toolchain for compiling C benchmarks (M10 L2
        # decision: Dhrystone/CoreMark/synthetic working-set sweep -> .elf -> .hex).
        # Separate from `default` so the lean sim+lint CI shell is unaffected.
        # `pkgsCross.riscv32-embedded` gives a newlib bare-metal gcc named
        # `riscv32-none-elf-gcc` (binutils objcopy/objdump come bundled). Target
        # the SoC ISA explicitly with -march=rv32i -mabi=ilp32.
        bench = pkgs.mkShell {
          name = "soc-riscv-bench";

          packages = with pkgs; [
            pkgsCross.riscv32-embedded.buildPackages.gcc   # riscv32-none-elf-gcc (newlib)
            pkgsCross.riscv32-embedded.buildPackages.binutils
            gnumake
            python3        # hex/elf post-processing for the harness
            git
          ];

          shellHook = ''
            echo "soc riscv-bench env ready — $(riscv32-none-elf-gcc --version | head -1)"
            echo "Build for the SoC: riscv32-none-elf-gcc -march=rv32i -mabi=ilp32 ..."
          '';
        };
      });
    };
}
