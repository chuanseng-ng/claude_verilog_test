# OpenROAD Flow Scripts

This directory contains TCL scripts for each stage of the OpenROAD physical design flow.

## Script List

| Script | Stage | Tool | Purpose |
|:-------|:------|:-----|:--------|
| 01_synth.tcl | Synthesis | Yosys | RTL to gate-level netlist |
| 02_floorplan.tcl | Floorplan | OpenROAD | Die size, I/O placement, power grid |
| 03_place.tcl | Placement | OpenROAD | Cell placement |
| 04_cts.tcl | CTS | TritonCTS | Clock tree synthesis |
| 05_route.tcl | Routing | TritonRoute | Wire routing |
| 06_sta.tcl | Timing | OpenSTA | Static timing analysis (post-route) |
| 07_power.tcl | Power | OpenROAD | Power analysis |
| 08_verify.tcl | Verification | KLayout | Physical verification (DRC/LVS) |

## Usage

Scripts are called automatically by the top-level Makefile:

```bash
# Run individual stage
make synth
make place
make route

# Run full flow
make all
```

## Script Structure

Each script follows a common pattern:

1. **Load configuration**: Read PDK and design parameters
2. **Read inputs**: Load netlist, constraints, libraries
3. **Execute stage**: Run the specific flow step
4. **Generate reports**: Create timing, area, power reports
5. **Write outputs**: Save DEF, netlist, or other artifacts

## Environment Variables

Scripts use these environment variables (set by Makefile):

- `TOP_MODULE`: Top-level module name
- `CLOCK_PERIOD`: Target clock period in ns
- `CLOCK_PORT`: Clock port name
- `PDK`: PDK selection (sky130 or asap7)
- `SDC_FILE`: Path to timing constraints
- `UPF_FILE`: Path to power intent

## Adding New Scripts

To add a new script:

1. Create `XX_stage_name.tcl` in this directory
2. Follow the structure of existing scripts
3. Add target to `../Makefile`
4. Document in this README

## References

- OpenROAD Flow Scripts: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
- Yosys Manual: https://yosyshq.net/yosys/documentation.html
- OpenSTA Commands: https://github.com/The-OpenROAD-Project/OpenSTA/tree/master/doc
