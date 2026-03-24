#!/usr/bin/env python3
"""
Generate a GDS2 stub file containing the router-generated VIA cells
that are missing from the NanGate45 PDK GDS.

KLayout layer map (from nangate45.lyt, dbu=0.0001 um => 10000 units/um):
  via1=12/0  via2=14/0  via3=16/0  via4=18/0  via5=20/0
  via6=22/0  via7=24/0  via8=26/0  via9=28/0
  metal1=11/0  metal2=13/0  metal3=15/0  metal4=17/0
  metal5=19/0  metal6=21/0  metal7=23/0  metal8=25/0  metal9=27/0

All coordinates are in GDS database units (dbu = 0.0001 um).
"""

import struct, datetime, math
from pathlib import Path

# ── GDS2 low-level writer ────────────────────────────────────────────────────

def _rec(rtype, dtype, data_bytes=b""):
    length = 4 + len(data_bytes)
    return struct.pack(">HH", length, rtype) + data_bytes

def _i2(val):   return struct.pack(">h", val)
def _i4(val):   return struct.pack(">i", val)
def _r8(val):
    # IEEE 754 double → GDS real8
    if val == 0: return b"\x00" * 8
    sign = 0 if val >= 0 else 1
    val = abs(val)
    exp = math.floor(math.log(val, 16)) + 1
    mant = val / (16 ** exp)
    mant_int = int(mant * (2**56))
    return struct.pack(">B", (sign << 7) | (exp + 64)) + mant_int.to_bytes(7, "big")

def _str_pad(s):
    b = s.encode("ascii")
    if len(b) % 2: b += b"\x00"
    return b

def _timestamp():
    now = datetime.datetime.now()
    return b"".join(_i2(x) for x in [now.year, now.month, now.day,
                                       now.hour, now.minute, now.second]) * 2

# Record type codes
HEADER    = 0x0002
BGNLIB    = 0x0102
LIBNAME   = 0x0206
UNITS     = 0x0305
ENDLIB    = 0x0400
BGNSTR    = 0x0502
STRNAME   = 0x0606
ENDSTR    = 0x0700
BOUNDARY  = 0x0800
SREF      = 0x0A00
AREF      = 0x0B00
LAYER     = 0x0D02
DATATYPE  = 0x0E02
XY        = 0x1003
ENDEL     = 0x1100
SNAME     = 0x1206
COLROW    = 0x1302
STRANS    = 0x1A01

def gds_box(layer, datatype, x0, y0, x1, y1):
    """A closed rectangular boundary on the given layer."""
    xy = b"".join(_i4(v) for v in [x0, y0, x1, y0, x1, y1, x0, y1, x0, y0])
    return (
        _rec(BOUNDARY, 0)
        + _rec(LAYER, 0, _i2(layer))
        + _rec(DATATYPE, 0, _i2(datatype))
        + _rec(XY, 0, xy)
        + _rec(ENDEL, 0)
    )

def gds_cell(name, geometry_bytes=b""):
    body = (
        _rec(BGNSTR, 0, _timestamp())
        + _rec(STRNAME, 0, _str_pad(name))
        + geometry_bytes
        + _rec(ENDSTR, 0)
    )
    return body

def gds_library(name, cells_bytes, dbu_user=1e-6, dbu_phys=1e-10):
    """dbu_user = user unit in metres; dbu_phys = physical unit in metres."""
    header = (
        _rec(HEADER, 0, _i2(600))
        + _rec(BGNLIB, 0, _timestamp())
        + _rec(LIBNAME, 0, _str_pad(name))
        + _rec(UNITS, 0, _r8(dbu_user / dbu_phys) + _r8(dbu_phys))
    )
    return header + cells_bytes + _rec(ENDLIB, 0)

# ── NanGate45 layer numbers ──────────────────────────────────────────────────

LAYER_MAP = {
    "metal1": 11, "metal2": 13, "metal3": 15, "metal4": 17,
    "metal5": 19, "metal6": 21, "metal7": 23, "metal8": 25,
    "metal9": 27, "metal10": 29,
    "via1": 12, "via2": 14, "via3": 16, "via4": 18,
    "via5": 20, "via6": 22, "via7": 24, "via8": 26,
    "via9": 28, "via10": 30,
}

# dbu = 0.0001 um → 1 um = 10000 dbu units
DBU = 10000  # units per micron

def um(x): return int(round(x * DBU))

# ── Via geometry helper ──────────────────────────────────────────────────────

def via_array_geom(cut_layer, bot_layer, top_layer,
                   cut_w, cut_h, rows, cols, cut_sp_x, cut_sp_y,
                   enc_bot_x, enc_bot_y, enc_top_x, enc_top_y):
    """
    Build GDS geometry for a via array cell.
    All dimensions in dbu units.
    Origin at (0,0); array is centred there.
    """
    # Total array width / height
    arr_w = cols * cut_w + (cols - 1) * cut_sp_x
    arr_h = rows * cut_h + (rows - 1) * cut_sp_y
    x0_cut = -(arr_w // 2)
    y0_cut = -(arr_h // 2)

    geom = b""
    # Cut rectangles
    for r in range(rows):
        for c in range(cols):
            x = x0_cut + c * (cut_w + cut_sp_x)
            y = y0_cut + r * (cut_h + cut_sp_y)
            geom += gds_box(LAYER_MAP[cut_layer], 0, x, y, x + cut_w, y + cut_h)

    # Bottom metal enclosure
    bx0 = x0_cut - enc_bot_x
    by0 = y0_cut - enc_bot_y
    bx1 = x0_cut + arr_w + enc_bot_x
    by1 = y0_cut + arr_h + enc_bot_y
    geom += gds_box(LAYER_MAP[bot_layer], 0, bx0, by0, bx1, by1)

    # Top metal enclosure
    tx0 = x0_cut - enc_top_x
    ty0 = y0_cut - enc_top_y
    tx1 = x0_cut + arr_w + enc_top_x
    ty1 = y0_cut + arr_h + enc_top_y
    geom += gds_box(LAYER_MAP[top_layer], 0, tx0, ty0, tx1, ty1)

    return geom

def single_via_geom(cut_layer, bot_layer, top_layer, cut_w, cut_h,
                    enc_x=0, enc_y=0):
    """Single-cut via centred at origin."""
    x0 = -(cut_w // 2)
    y0 = -(cut_h // 2)
    geom = gds_box(LAYER_MAP[cut_layer], 0, x0, y0, x0 + cut_w, y0 + cut_h)
    geom += gds_box(LAYER_MAP[bot_layer], 0, x0 - enc_x, y0 - enc_y,
                    x0 + cut_w + enc_x, y0 + cut_h + enc_y)
    geom += gds_box(LAYER_MAP[top_layer], 0, x0 - enc_x, y0 - enc_y,
                    x0 + cut_w + enc_x, y0 + cut_h + enc_y)
    return geom

# ── Via cell definitions ─────────────────────────────────────────────────────
# DEF VIAS section (from routed DEF):
#   via4_5_960_2800_5_2_600_600  VIARULE Via4Array  CUTSIZE 280 280
#       LAYERS metal4 via4 metal5  CUTSPACING 320 320  ENCLOSURE 40 0 0 0  ROWCOL 5 2
#   via5_6_960_2800_5_2_600_600  VIARULE Via5Array  CUTSIZE 280 280
#       LAYERS metal5 via5 metal6  CUTSPACING 320 320  ENCLOSURE 0 0 0 0   ROWCOL 5 2
#   via6_7_960_2800_4_1_600_600  VIARULE Via6Array  CUTSIZE 280 280
#       LAYERS metal6 via6 metal7  CUTSPACING 320 320  ENCLOSURE 0 0 260 360 ROWCOL 4 1
#
# DEF units are 2000/um → 280 dbu_DEF = 280/2000 um = 0.14 um = 1400 dbu_GDS
# All values below converted: x_GDS = x_DEF / 2000 * 10000 = x_DEF * 5

def _d(x): return x * 5   # DEF dbu (2000/um) → GDS dbu (10000/um)

ARRAY_VIAS = [
    # (cell_name, cut_layer, bot, top, cut_w, cut_h, rows, cols,
    #  sp_x, sp_y, enc_bot_x, enc_bot_y, enc_top_x, enc_top_y)
    ("via4_5_960_2800_5_2_600_600",
     "via4", "metal4", "metal5",
     _d(280), _d(280), 5, 2, _d(320), _d(320), _d(40), _d(0), _d(0), _d(0)),
    ("via5_6_960_2800_5_2_600_600",
     "via5", "metal5", "metal6",
     _d(280), _d(280), 5, 2, _d(320), _d(320), _d(0), _d(0), _d(0), _d(0)),
    ("via6_7_960_2800_4_1_600_600",
     "via6", "metal6", "metal7",
     _d(280), _d(280), 4, 1, _d(320), _d(320), _d(0), _d(0), _d(260), _d(360)),
]

# Single-cut vias — standard NanGate45 cut sizes (from tech LEF WIDTH values)
# via1-3: 0.07 um cut; via4-9: 0.14 um cut
# Standard enclosure: use minimum from tech LEF (~0.04 um for via1-3, ~0.04 um for via4+)
SINGLE_VIA_SPECS = {
    "via1": ("via1", "metal1", "metal2", um(0.07), um(0.07), um(0.04), um(0.04)),
    "via2": ("via2", "metal2", "metal3", um(0.07), um(0.07), um(0.04), um(0.04)),
    "via3": ("via3", "metal3", "metal4", um(0.07), um(0.07), um(0.04), um(0.04)),
    "via4": ("via4", "metal4", "metal5", um(0.14), um(0.14), um(0.04), um(0.04)),
    "via5": ("via5", "metal5", "metal6", um(0.14), um(0.14), um(0.04), um(0.04)),
    "via6": ("via6", "metal6", "metal7", um(0.14), um(0.14), um(0.04), um(0.04)),
    "via7": ("via7", "metal7", "metal8", um(0.14), um(0.14), um(0.04), um(0.04)),
    "via8": ("via8", "metal8", "metal9", um(0.14), um(0.14), um(0.04), um(0.04)),
    "via9": ("via9", "metal9", "metal10", um(0.14), um(0.14), um(0.04), um(0.04)),
}

# Missing single-cut via cell names from the KLayout error log
# Format: VIA_via{layer}_{index}
SINGLE_VIA_CELLS = [
    ("VIA_via1_4",  "via1"),
    ("VIA_via2_5",  "via2"),
    ("VIA_via1_7",  "via1"),
    ("VIA_via5_0",  "via5"),
    ("VIA_via3_2",  "via3"),
    ("VIA_via4_0",  "via4"),
    ("VIA_via7_0",  "via7"),
    ("VIA_via6_0",  "via6"),
    ("VIA_via8_0",  "via8"),
    ("VIA_via9_0",  "via9"),
]

# ── Build GDS ────────────────────────────────────────────────────────────────

cells_bytes = b""

# Array via cells (from DEF VIAS section; prefixed with "VIA_" by KLayout)
for (name, cl, bl, tl, cw, ch, rows, cols, spx, spy, ebx, eby, etx, ety) in ARRAY_VIAS:
    geom = via_array_geom(cl, bl, tl, cw, ch, rows, cols, spx, spy, ebx, eby, etx, ety)
    cells_bytes += gds_cell("VIA_" + name, geom)

# Single-cut via cells
for (cell_name, via_key) in SINGLE_VIA_CELLS:
    spec = SINGLE_VIA_SPECS[via_key]
    cl, bl, tl, cw, ch, enc_x, enc_y = spec
    geom = single_via_geom(cl, bl, tl, cw, ch, enc_x, enc_y)
    cells_bytes += gds_cell(cell_name, geom)

# dbu_user = 1e-6 (1 unit = 1 um * 1e-4 = 0.1 nm … actually:
# KLayout dbu = 0.0001 um, so user unit = 0.0001e-6 m = 1e-10 m
# physical dbu = 1e-10 m
gds_bytes = gds_library("nangate45_generated_vias", cells_bytes,
                         dbu_user=1e-4,    # 1 unit = 0.0001 um (relative)
                         dbu_phys=1e-10)   # 1 unit = 0.1 nm

output_path = Path(__file__).resolve().parent / "nangate45_generated_vias.gds"
with open(output_path, "wb") as f:
    f.write(gds_bytes)

print(f"Written {len(gds_bytes)} bytes to {output_path}")
print(f"Cells generated: {len(ARRAY_VIAS) + len(SINGLE_VIA_CELLS)}")
for (name, *_) in ARRAY_VIAS:
    print(f"  VIA_{name}")
for (name, _) in SINGLE_VIA_CELLS:
    print(f"  {name}")
