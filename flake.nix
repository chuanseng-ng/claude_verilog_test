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
  #
  # EXCEPTION: the `hls` devShell (GH #119) packages the Bambu HLS tool. It is a
  # C++->Verilog front-end, not a PnR tool, and its output is fed to the normal
  # LibreLane flow like any other RTL. See devShells.hls below.

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f:
        nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      inherit (nixpkgs) lib;

      # ── Bambu (PandA) HLS — GH #119 ────────────────────────────────────────────
      # Upstream ships only a prebuilt AppImage (no nixpkgs package, no source
      # derivation worth maintaining here), so it is unpacked and run inside an FHS
      # sandbox. The AppImage is pinned by sha256, which is what makes the
      # "pin the HLS release before measuring" requirement of
      # docs/CPP_TO_RTL_HLS_EVALUATION.md actually enforceable — nix refuses to build
      # if the upstream artefact ever changes under that URL.
      #
      # Version: PandA 2024.10, revision c2ba6936ca2ed63137095fea0b630a1c66e20e63-main.
      #
      # Three things here are load-bearing; do not "simplify" them away:
      #
      #  1. runScript execs usr/bin/bambu DIRECTLY rather than going through the
      #     AppImage's AppRun. AppRun delegates to usr/bin/tool_select.sh, which
      #     dispatches on `basename "$ARGV0"` to pick one of several bundled tools
      #     (bambu/spider/eucalyptus/...). nixpkgs' appimage-exec.sh execs AppRun
      #     WITHOUT setting ARGV0, so tool_select.sh resolves to the bare directory
      #     `usr/bin/` and dies with "Is a directory". Calling the real binary
      #     directly skips that dispatch entirely.
      #
      #  2. APPDIR must be exported. The binary hardcodes absolute paths like
      #     /usr/share/panda/... and /usr/gcc_plugins/...; APPDIR is the only knob
      #     that re-roots them into the unpacked tree.
      #
      #  3. extraBuildCommands links the AppImage's OWN libtinfo.so.5 and libbdd.so.0
      #     into the FHS /usr/lib64 (note: $out/usr/lib is itself a dangling symlink
      #     to /usr/lib64 at build time, so lib64 is the only writable target).
      #     Two separate reasons this shape, not another:
      #       * Not LD_LIBRARY_PATH: Bambu shells out to a sub-make for its MDPI
      #         co-simulation harness which does not inherit it, so an env fix works
      #         for the HLS front-end and then fails at the cosim step.
      #       * Not pkgs.ncurses5: ldconfig indexes by SONAME, and nixpkgs'
      #         ncurses-abi5-compat ships libtinfo.so.5 as a symlink to
      #         libncursesw.so.5.9 whose SONAME is libncursesw.so.5. The cache then
      #         contains no libtinfo.so.5 entry at all and the loader still fails,
      #         even though the file is on disk. The AppImage's own copies carry the
      #         correct SONAMEs and are ABI-matched to its plugins.
      #     The bundled clang-16 needs libtinfo.so.5; the dumpGimpleSSA clang plugin
      #     needs libbdd.so.0. Symptom if libbdd is missing: that plugin silently
      #     fails to load, its -panda-* options never register, and clang rejects them
      #     with "Did you mean '--panda-TFN'?". clang-16's RUNPATH is $ORIGIN/../lib,
      #     which covers neither.
      #
      #  4. verilator must be INSIDE the FHS env: Bambu locates it with a literal
      #     system("which verilator") for --simulator=VERILATOR.
      #
      #  5. glibc.dev populates /usr/include. Bambu's MDPI co-simulation harness
      #     compiles C/C++ glue (mdpi.c, generated_tb.c, mdpi_wrapper.cpp) with the
      #     bundled clang-16, which needs stdio.h / features.h / bits/wordsize.h. The
      #     FHS profile already adds -idirafter /usr/include, so headers only need to
      #     be present. Without it HLS succeeds and only --simulate fails.
      #     It must be glibc_multi.dev, not glibc.dev: Bambu builds that harness with
      #     -m32 to match the synthesised design's 32-bit pointers (our blocks are all
      #     32-bit too), so it needs gnu/stubs-32.h. multiPkgs supplies the matching
      #     32-bit libs in /usr/lib32.
      bambuFor = pkgs:
        let
          version = "2024.10";
          extracted = pkgs.appimageTools.extract {
            pname = "bambu";
            inherit version;
            src = pkgs.fetchurl {
              url = "https://release.bambuhls.eu/bambu-${version}.AppImage";
              sha256 = "e4f0214496a5d35de1932975b0f41cd95bc33a53a904fc565d6c2cb01df40773";
            };
          };
        in
        pkgs.appimageTools.wrapAppImage {
          pname = "bambu";
          inherit version;
          src = extracted;

          extraPkgs = p: [
            p.verilator  # located via `which verilator`  (see note 4)
            p.gcc        # Verilator compiles the generated model
            p.glibc_multi.dev  # /usr/include, incl. 32-bit stubs (see note 5)
            p.gnumake
            p.python3
            p.zlib
          ];

          # 32-bit runtime libs for the -m32 MDPI harness (see note 5).
          # multiArch=true is the actual gate: buildFHSEnv computes
          # isMultiBuild = multiArch && x86_64-linux, and populates /usr/lib32 only
          # then. Setting multiPkgs alone silently leaves /usr/lib32 empty.
          multiArch = true;
          multiPkgs = p: [ p.glibc p.zlib ];

          # See note 3. These are the AppImage's own libraries, not nixpkgs'.
          extraBuildCommands = ''
            ln -sf ${extracted}/lib/x86_64-linux-gnu/libtinfo.so.5 $out/usr/lib64/libtinfo.so.5
            ln -sf ${extracted}/usr/lib/libbdd.so.0 $out/usr/lib64/libbdd.so.0
          '';

          runScript = "${pkgs.writeShellScript "bambu-run" ''
            export APPDIR=${extracted}
            exec ${extracted}/usr/bin/bambu "$@"
          ''}";

          meta = {
            description = "Bambu (PandA) high-level synthesis tool — C/C++ to Verilog";
            homepage = "https://panda.dei.polimi.it/";
            license = lib.licenses.gpl3Plus;
            platforms = [ "x86_64-linux" ];
          };
        };
    in
    {
      # Expose the pinned Verilator as a package so CI can put just the binary on
      # PATH (`nix profile install .#verilator`) and compile/run the cocotb sim in
      # the system shell with the system g++/glibc. Linking Vtop with the nix gcc
      # instead makes it use the nix glibc loader, which mixes badly with the
      # system Python/libffi at runtime (segfaults on the CI runner). The local
      # `nix develop` shell still bundles gcc for convenience.
      packages = forAllSystems (pkgs:
        {
          verilator = pkgs.verilator;
          default = pkgs.verilator;
        }
        # AppImage + FHS sandbox are Linux-only.
        // lib.optionalAttrs pkgs.stdenv.isLinux {
          bambu = bambuFor pkgs;
        });

      devShells = forAllSystems (pkgs:
        {
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

            # Only greet an interactive shell. `nix develop --command <cmd>` is how the
            # test/lint flows are driven, and these two lines otherwise prepend to every
            # captured command output (they are emitted by the shell before the command
            # runs, so no downstream output filter can remove them).
            shellHook = ''
              if [[ $- == *i* ]]; then
                echo "soc sim+lint env ready — Verilator $(verilator --version | head -1 | awk '{print $2}')"
                echo "Python/cocotb come from system + pip: 'pip install -r requirements.txt cocotb-bus cocotbext-axi'"
              fi
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
              if [[ $- == *i* ]]; then
                echo "soc riscv-bench env ready — $(riscv32-none-elf-gcc --version | head -1)"
                echo "Build for the SoC: riscv32-none-elf-gcc -march=rv32i -mabi=ilp32 ..."
              fi
            '';
          };
        }
        # Bambu HLS shell (GH #119). Linux-only; see bambuFor above.
        // lib.optionalAttrs pkgs.stdenv.isLinux {
          hls = pkgs.mkShell {
            name = "soc-hls-bambu";

            packages = [
              (bambuFor pkgs)
              pkgs.verilator   # also outside the sandbox, for linting generated .v
              pkgs.gnumake
              pkgs.git
            ];

            shellHook = ''
              if [[ $- == *i* ]]; then
                echo "soc hls env ready — $(bambu --version 2>/dev/null | grep -i '^ Version:' | sed 's/^ *//')"
                echo "GH #119 pilot. Generated Verilog is NOT committed; it goes to /nobackup/hls/out/."
              fi
            '';
          };
        });
    };
}
