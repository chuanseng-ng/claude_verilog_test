#!/usr/bin/env python3
"""publish_reports.py [arm ...] -- STEP 8: copy runs/<arm>/apl_{static,dynamic,dynamic_nodecap,dynamic_estdecap}_summary.json to reports/<arm>_{static,dynamic,dynamic_nodecap,dynamic_estdecap}_summary.json
(the names compare/compare.py reads).  The b6-era OpenROAD files (same layout, old model: Liberty-default currents, W/L decap estimate, ideal feed) are first kept as reports/openroad_b6model_*."""
import os, shutil, sys
here = os.path.dirname(os.path.abspath(__file__)); rh = os.path.join(here, ".."); rep = os.path.join(rh, "reports")
arms = sys.argv[1:] or ["icc2b9", "innovusb11", "openroad"]
kinds = ["static", "dynamic", "dynamic_nodecap", "dynamic_estdecap"]
for a in arms:
    if a == "openroad":
        for k in kinds[:3]:
            old = os.path.join(rep, "openroad_%s_summary.json" % k); keep = os.path.join(rep, "openroad_b6model_%s_summary.json" % k)
            if os.path.exists(old) and not os.path.exists(keep): shutil.copy(old, keep)
    for k in kinds:
        src = os.path.join(rh, "runs", a, "apl_%s_summary.json" % k)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(rep, "%s_%s_summary.json" % (a, k))); print("published", a, k)
        else: print("MISSING", a, k)
