# Patched json_header.py — skips proc/flatten/opt_clean to avoid
# Synlig UHDM empty-wire assert in kernel/rtlil.cc:2150 for soc_top.
# Only generates the port interface JSON needed by downstream steps.
import json
import click
from ys_common import ys

@click.command()
@click.option("--output", type=click.Path(exists=False, dir_okay=False), required=True)
@click.option("--config-in", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--extra-in", type=click.Path(exists=True, dir_okay=False), required=True)
def json_header(output, config_in, extra_in):
    config = json.load(open(config_in))
    extra = json.load(open(extra_in))
    blackbox_models = extra["blackbox_models"]
    includes = config["VERILOG_INCLUDE_DIRS"] or []
    defines = (
        (config["VERILOG_DEFINES"] or [])
        + [f"PDK_{config['PDK']}", f"SCL_{config['STD_CELL_LIBRARY']}",
           "__librelane__", "__pnr__"]
        + ([] if config.get("VERILOG_POWER_DEFINE") is None
           else [config.get("VERILOG_POWER_DEFINE")])
    )
    d = ys.Design()
    d.add_blackbox_models(blackbox_models, includes=includes, defines=defines)
    d.read_verilog_files(
        config["VERILOG_FILES"],
        top=config["DESIGN_NAME"],
        synth_parameters=config["SYNTH_PARAMETERS"] or [],
        includes=includes, defines=defines,
        use_synlig=config["USE_SYNLIG"],
        synlig_defer=config["SYNLIG_DEFER"],
    )
    # hierarchy WITHOUT -check: avoids the RTLIL wire-name assert that Synlig
    # UHDM triggers for non-blackbox submodule connections via packed 2D nets.
    d.run_pass("hierarchy", "-top", config["DESIGN_NAME"])
    d.run_pass("rename", "-top", config["DESIGN_NAME"])
    # proc is required when SYNLIG_DEFER=true because defer+link fully elaborates
    # all modules (unlike the monolithic read which left modules unelaborated);
    # the resulting RTLIL contains always/initial processes that JSON can't emit.
    # flatten and opt_clean are still skipped — only port declarations are needed.
    d.run_pass("proc")
    d.run_pass("json", "-o", output)

if __name__ == "__main__":
    json_header()
