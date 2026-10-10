#!/usr/bin/env python3
"""Print D-pin setup (rise/fall constraint) and CLK->Q delay at the middle index of the
tables for given cells in a Liberty file. Measured from the .lib, no STA."""
import re
import sys

lib = sys.argv[1]
cells = sys.argv[2:]
t = open(lib).read()


def block(text, start):
    i = text.index('{', start)
    d = 0
    for j in range(i, len(text)):
        if text[j] == '{':
            d += 1
        elif text[j] == '}':
            d -= 1
            if d == 0:
                return text[start:j + 1]
    return text[start:]


def mid(tbl):
    rows = re.findall(r'"([^"]+)"', re.search(r'values\s*\((.*?)\)\s*;', tbl, re.S).group(1))
    r = rows[len(rows) // 2].split(',')
    return float(r[len(r) // 2])


for c in cells:
    m = re.search(r'cell\s*\(\s*"%s"\s*\)' % re.escape(c), t)
    cb = block(t, m.start())
    out = [c]
    for pin in ('D', 'SCD', 'SCE'):
        pm = re.search(r'pin\s*\(\s*"%s"\s*\)' % pin, cb)
        if not pm:
            continue
        pb = block(cb, pm.start())
        for tm in re.finditer(r'timing\s*\(\s*\)', pb):
            tb = block(pb, tm.start())
            ty = re.search(r'timing_type\s*:\s*"?(\w+)', tb)
            if ty and ty.group(1) == 'setup_rising':
                for k in ('rise_constraint', 'fall_constraint'):
                    km = re.search(k, tb)
                    if km:
                        out.append('%s.%s=%.3f' % (pin, k[:4], mid(block(tb, km.start()))))
    qm = re.search(r'pin\s*\(\s*"Q"\s*\)', cb)
    if qm:
        qb = block(cb, qm.start())
        for tm in re.finditer(r'timing\s*\(\s*\)', qb):
            tb = block(qb, tm.start())
            if 'rising_edge' in tb:
                for k in ('cell_rise', 'cell_fall'):
                    km = re.search(k, tb)
                    if km:
                        out.append('clk2q.%s=%.3f' % (k[5:], mid(block(tb, km.start()))))
                break
    print(' '.join(out))
