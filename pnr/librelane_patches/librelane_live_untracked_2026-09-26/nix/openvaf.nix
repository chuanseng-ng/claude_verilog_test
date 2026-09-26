# OpenVAF — Verilog-A to OSDI shared-library compiler
#
# OpenVAF is NOT available in nixpkgs. This derivation fetches the upstream
# prebuilt Linux x86_64 binary and autopatchelfs it into the Nix store.
#
# TODO (M-a / M-b stretch): Populate url and sha256 once the upstream release
# URL is confirmed stable. Until then this derivation is intentionally DISABLED
# in the analog devShell — see flake.nix. M-a and M-b can proceed using
# ngspice-native behavioral models (B-sources / XSPICE extensions) instead of
# OSDI-compiled Verilog-A.
#
# When ready, verify the sha256 with:
#   nix-prefetch-url --type sha256 <url>
# then un-comment the reference in the analog devShell's extra-packages list.
{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
  # Runtime deps inferred by autopatchelf; add extras here if ldd shows gaps.
}:
stdenv.mkDerivation rec {
  pname = "openvaf";
  # TODO: update to the actual release tag once confirmed.
  version = "23.5.0";

  src = fetchurl {
    # TODO: replace with the verified upstream release URL, e.g.:
    #   https://github.com/pascalkuthe/OpenVAF/releases/download/v23.5.0/openvaf_23_5_0_linux_amd64
    url = "TODO_REPLACE_WITH_REAL_URL";
    # TODO: replace with the correct sha256 from nix-prefetch-url.
    sha256 = "0000000000000000000000000000000000000000000000000000";
  };

  nativeBuildInputs = [ autoPatchelfHook ];

  # The upstream release is a single statically-linked binary; no shared libs
  # are required beyond libc/libm which autoPatchelfHook handles automatically.
  buildInputs = [];

  dontUnpack = true;
  dontBuild  = true;

  installPhase = ''
    runHook preInstall
    install -Dm755 $src $out/bin/openvaf
    runHook postInstall
  '';

  meta = with lib; {
    description = "Verilog-A to OSDI compiler for ngspice/Xyce Verilog-A model support";
    homepage    = "https://github.com/pascalkuthe/OpenVAF";
    license     = licenses.gpl3Plus;
    platforms   = [ "x86_64-linux" ];
    mainProgram = "openvaf";
  };
}
