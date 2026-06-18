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
      });
    };
}
