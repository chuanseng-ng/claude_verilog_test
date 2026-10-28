#!/usr/bin/env python3
"""klayout_report_summary.py <drc_violations.klayout.xml>: violation count per rule category (streaming iterparse; clears elements)."""
import sys, collections
import xml.etree.ElementTree as ET
cnt = collections.Counter(); total = 0
for ev, el in ET.iterparse(sys.argv[1], events=("end",)):
    if el.tag == "item":
        cat = el.findtext("category") or "?"
        cnt[cat.strip("'\"")] += 1; total += 1
        el.clear()
print(f"# KLayout DRC report {sys.argv[1]}")
print(f"TOTAL_VIOLATION_ITEMS {total}  RULES_VIOLATED {len(cnt)}")
for k, v in cnt.most_common(): print(f"{v:10d}  {k}")
