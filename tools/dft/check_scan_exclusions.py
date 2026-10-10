#!/usr/bin/env python3
"""Gate: the excluded flops are NOT scan cells, and every other flop IS.

usage: check_scan_exclusions.py scan_netlist.v [--expect N] [--regex RE]
Exit 0 only if (a) exactly N flops match the exclusion regex on their Q net (default 256),
(b) none of them is a scan cell (type contains __sdf/__sedf, or has an SCD pin),
(c) every other flop is a scan cell, (d) no excluded flop's Q net is also a scan-chain SCD/scan_out net.
Matching is on the Q net name, so a renamed or merged register makes (a) fail loudly rather than silently
leaving the exclusion unenforced."""
import re
import sys

args = sys.argv[1:]
path = args[0]
expect = int(args[args.index('--expect') + 1]) if '--expect' in args else 256
rx = re.compile(args[args.index('--regex') + 1] if '--regex' in args
                else r'u_crypto\.(g_aes\.u_aes\.rk_q|key_q)\b')
t = open(path).read()
cells = re.findall(r'\n\s*(sky130_fd_sc_hd__\w+)\s+(\\?\S+)\s*\((.*?)\);', t, re.S)
bad = []
excl = other = 0
scd_nets = set()
flops = []
for typ, name, body in cells:
    if not re.search(r'__(s?e?df)', typ):
        continue
    pins = {p: n.strip() for p, n in re.findall(r'\.(\w+)\(([^()]*)\)', body)}
    flops.append((typ, name, pins))
    if 'SCD' in pins:
        scd_nets.add(pins['SCD'])
for typ, name, pins in flops:
    scan = '__sdf' in typ or '__sedf' in typ or 'SCD' in pins
    if rx.search(pins.get('Q', '')):
        excl += 1
        if scan or pins.get('Q') in scd_nets:
            bad.append('excluded flop %s (%s) is on a scan chain' % (name, typ))
    else:
        other += 1
        if not scan:
            bad.append('non-excluded flop %s (%s, Q=%s) is not a scan cell' % (name, typ, pins.get('Q')))
if excl != expect:
    bad.append('expected %d excluded flops, found %d (renamed/merged register?)' % (expect, excl))
print('flops: %d excluded, %d other; %d problems' % (excl, other, len(bad)))
for b in bad[:10]:
    print('FAIL:', b)
sys.exit(1 if bad else 0)
