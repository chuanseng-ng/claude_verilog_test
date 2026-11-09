# lef_vs_gds_obs.py -- compare the SRAM LEF met3 OBS (what Innovus verify_drc checks wires against) with the real met3 geometry of the SRAM GDS near the dout0 pin edge.
#   usage: klayout -b -r lef_vs_gds_obs.py -rd gds=<sram.gds> -rd lef=<sram.lef> [-rd viol=<innovus verify_drc report> -rd deffile=<final DEF>] [-rd origin=...]  (bead: round-3 item 13)
import pya,re
ly=pya.Layout(); ly.read(gds); top=ly.top_cell()
print('top',top.name,'bbox',top.bbox().to_s())
# LEF met3 OBS rects
txt=open(lef).read()
obs=txt.split('   OBS',1)[1]
cur=None; rects=[]
for l in obs.splitlines():
    m=re.match(r'\s*LAYER\s+(\S+)',l)
    if m: cur=m.group(1); continue
    m=re.match(r'\s*RECT\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',l)
    if m and cur: rects.append((cur,[float(v) for v in m.groups()]))
def reg_of(layer):
    ln,dt=layer; li=ly.layer(ln,dt); r=pya.Region(top.begin_shapes_rec(li)); r.merge(); return r
lefm3=pya.Region()
for c,(a,b,cc,d) in rects:
    if c=='met3': lefm3.insert(pya.Box(int(a*1000),int(b*1000),int(cc*1000),int(d*1000)))
lefm3.merge()
gm3=reg_of((70,20)); gm4=reg_of((71,20))
# window near the bottom edge y<8 across all x: compare
win=pya.Region(pya.Box(0,0,480000,8000))
print('LEF met3 OBS in y<8 area um2:', (lefm3&win).area()/1e6)
print('GDS met3 in y<8 area um2:', (gm3&win).area()/1e6)
print('GDS met3 outside LEF OBS (y<8) um2:', ((gm3&win)-lefm3).area()/1e6)
print('LEF OBS outside GDS met3 (y<8) um2:', ((lefm3&win)-gm3).area()/1e6)
# per-pin: pins dout0[29] x 321.64-322.02: local y 0..1.06 met4 pin; what's met3 nearby
for name,x1,x2 in (('dout0[29]',321.64,322.02),('dout0[30]',327.76,328.14)):
    box=pya.Box(int((x1-3)*1000),0,int((x2+3)*1000),int(6*1000))
    print(name,'LEF met3 OBS polys near pin:',[ (p.bbox().to_s()) for p in (lefm3&pya.Region(box)).each()])
    print(name,'GDS met3 polys near pin   :',[ (p.bbox().to_s()) for p in (gm3&pya.Region(box)).each()])
    print(name,'GDS met4 polys near pin   :',[ (p.bbox().to_s()) for p in (gm4&pya.Region(box)).each()])
# gap: GDS met3 top-most edge near bottom for y<1.5 
print('GDS met3 min y over whole cell um:', gm3.bbox().bottom/1000, ' LEF met3 OBS min y:', lefm3.bbox().bottom/1000)

# ---- the Innovus verify_drc "Blockage of Cell ... (met3)" markers: map each marker to SRAM-local original-orientation coordinates (DEF orient FS = mirror about the X axis: y_orig = (y_origin_abs + H) - y_abs, x_local = x_abs - x_origin)
#      and report the real GDS met3 and the LEF OBS met3 within the marker's x range and +-0.6 um in y.
import os
viol=globals().get('viol',''); deff=globals().get('deffile','')
if viol and os.path.exists(viol) and deff and os.path.exists(deff):
    H=397.5; origin={}
    for l in open(deff):
        m=re.match(r'- (\S+) sky130_sram_1kbyte_1rw1r_32x256_8 \+ (?:FIXED|PLACED) \( (\d+) (\d+) \) (\S+)',l)
        if m: origin[m.group(1).replace('\\','')]=(int(m.group(2))/1000.0,int(m.group(3))/1000.0,m.group(4))
    print('SRAM origins from DEF:',origin)
    cur=None; n=0; nogds=0; res=[]
    for l in open(viol):
        m=re.search(r'Blockage of Cell (\S+)',l)
        if m: cur=m.group(1)
        m=re.match(r'Bounds : \( ([\d.]+), ([\d.]+) \) \( ([\d.]+), ([\d.]+) \)',l)
        if m and cur:
            x1,y1,x2,y2=[float(v) for v in m.groups()]
            ox,oy,ori=origin[cur]
            assert ori=='FS'
            yo1,yo2=(oy+H)-y2,(oy+H)-y1; xl1,xl2=x1-ox,x2-ox
            band=pya.Box(int((xl1-0.6)*1000),int(max(yo1-0.6,0)*1000),int((xl2+0.6)*1000),int((yo2+0.6)*1000))
            g=(gm3&pya.Region(band)); lf=(lefm3&pya.Region(band))
            gl=[q.bbox() for q in g.each()]; ll=[q.bbox() for q in lf.each()]
            # smallest distance from the marker box to any real met3 (GDS) polygon / LEF OBS polygon
            mk=pya.Box(int(xl1*1000),int(yo1*1000),int(xl2*1000),int(yo2*1000))
            dg=min([max(b.left-mk.right,mk.left-b.right,b.bottom-mk.top,mk.bottom-b.top,0) for b in gl] or [999999])/1000.0
            dl=min([max(b.left-mk.right,mk.left-b.right,b.bottom-mk.top,mk.bottom-b.top,0) for b in ll] or [999999])/1000.0
            print('%-44s x_local %.2f..%.2f y_orig %.3f..%.3f  dist(marker, GDS met3)=%.3f  dist(marker, LEF OBS met3)=%.3f'%(cur,xl1,xl2,yo1,yo2,dg,dl))
            n+=1; cur=None
            if dg>0.0: nogds+=1
    print('markers %d; markers with NO GDS met3 touching the marker box: %d'%(n,nogds))
