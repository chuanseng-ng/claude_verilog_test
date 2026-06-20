# Flake-compat wrapper: lets `nix-shell` (non-flake) drop into the same sim+lint
# devShell defined in flake.nix. Primary entry point is `nix develop`; this exists
# for muscle memory and setups without flakes enabled. Pinned flake-compat rev.
(import
  (fetchTarball {
    url = "https://github.com/edolstra/flake-compat/archive/ff81ac966bb2cae68946d5ed5fc4994f96d0ffec.tar.gz";
    sha256 = "19d2z6xsvpxm184m41qrpi1bplilwipgnzv9jy17fgw421785q1m";
  })
  { src = ./.; }
).shellNix
