#!/usr/bin/env python3
# json_header_soc.py — Workaround for Synlig UHDM not emitting module
# instantiation cells for soc_top (Yosys assert in kernel/rtlil.cc:2150).
#
# Generates soc_top.h.json using a plain Verilog port-only stub
# (soc_top_ports.v) readable by Yosys read_verilog -sv without Synlig.
# The stub has the identical port signature as soc_top.sv but no imports.
#
# Usage: python3 json_header_soc.py --config-in <config.json>
#                                    --extra-in  <extra.json>
#                                    --output    <soc_top.h.json>

import json
import os
import sys
import click

# Locate ys_common relative to the LibreLane scripts directory
_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../../../librelane/librelane/scripts/pyosys"
)
sys.path.insert(0, _SCRIPTS_DIR)

from ys_common import ys  # type: ignore


@click.command()
@click.option("--output", type=click.Path(exists=False, dir_okay=False), required=True)
@click.option("--config-in", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--extra-in", type=click.Path(exists=True, dir_okay=False), required=True)
def json_header_soc(output, config_in, extra_in):
    config = json.load(open(config_in))
    extra  = json.load(open(extra_in))

    # The port stub lives next to this script.
    stub_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "soc_top_ports.v")
    if not os.path.exists(stub_path):
        print(f"ERROR: soc_top_ports.v not found at {stub_path}", file=sys.stderr)
        sys.exit(1)

    blackbox_models = extra["blackbox_models"]
    includes        = config.get("VERILOG_INCLUDE_DIRS") or []
    defines         = (
        (config.get("VERILOG_DEFINES") or [])
        + [
            f"PDK_{config['PDK']}",
            f"SCL_{config['STD_CELL_LIBRARY']}",
            "__librelane__",
            "__pnr__",
        ]
    )
    include_args = [f"-I{d}" for d in includes]
    define_args  = [f"-D{d}" for d in defines]

    design_name = config["DESIGN_NAME"]

    d = ys.Design()

    # Read blackbox models (Liberty + bb.v) first — same as normal json_header.
    for model in blackbox_models:
        if model.endswith(".lib"):
            d.run_pass("read_liberty", "-lib", model)
        else:
            # .bb.v — plain Verilog blackbox, readable without Synlig.
            d.run_pass("read_verilog", "-sv", "-lib",
                       *include_args, *define_args, model)

    # Read the port-only stub with plain read_verilog (no Synlig needed).
    # `(* blackbox *)` attribute tells hierarchy not to expand it.
    d.run_pass("read_verilog", "-sv", *include_args, *define_args, stub_path)

    # Set the top attribute directly on the module (no hierarchy pass needed
    # for a port-only stub with no children).
    d.run_pass("setattr", "-set", "top", "1", f"m:{design_name}")
    d.run_pass("json", "-o", output)

    print(f"[json_header_soc] Wrote {output}", file=sys.stderr)


if __name__ == "__main__":
    json_header_soc()
