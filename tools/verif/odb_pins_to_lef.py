#!/usr/bin/env python3
"""Dump the signal-pin shapes of an OpenROAD ODB as a minimal LEF (bead lu09).

Runs inside OpenROAD's embedded Python (``openroad -python odb_pins_to_lef.py IN.odb OUT.lef``), which is
the same interpreter LibreLane's ``odbpy`` steps use. The output has just MACRO/SIZE/PIN/PORT/RECT, in the
syntax ``lef_pin_diff.py`` and ``pin_lock.py`` parse, so a floorplan-stage ODB can be compared with the
committed LEF without running a full harden (the LEF itself only exists after Magic.WriteLEF, step 61).
"""

import sys

import odb


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: openroad -python odb_pins_to_lef.py IN.odb OUT.lef")
    db = odb.dbDatabase.create()
    odb.read_db(db, argv[1])
    block = db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    die = block.getDieArea()

    def um(v):
        return f"{v / dbu:.3f}"

    lines = [f"MACRO {block.getName()}", f"  SIZE {um(die.dx())} BY {um(die.dy())} ;"]
    for bt in sorted(block.getBTerms(), key=lambda b: b.getName()):
        if bt.getSigType() in ("POWER", "GROUND"):
            continue
        lines += [f"  PIN {bt.getName()}", "    USE SIGNAL ;", "    PORT"]
        for bp in bt.getBPins():
            for box in bp.getBoxes():
                lines += [
                    f"      LAYER {box.getTechLayer().getName()} ;",
                    f"        RECT {um(box.xMin())} {um(box.yMin())} {um(box.xMax())} {um(box.yMax())} ;",
                ]
        lines += ["    END", f"  END {bt.getName()}"]
    lines.append(f"END {block.getName()}")
    with open(argv[2], "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(
        f"[odb_pins_to_lef] {sum(1 for b in block.getBTerms() if b.getSigType() not in ('POWER', 'GROUND'))} pins -> {argv[2]}"
    )


main(sys.argv)
