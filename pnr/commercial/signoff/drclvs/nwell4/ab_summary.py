# ab_summary.py <out_dir> : per Magic A/B run, nwell.4 item count and the count of every other rule (items touching the clip edge flagged)
import sys,glob,os,re,collections
d=sys.argv[1]
wins={"P":(0,0,101,930),"C":(0,419,700,519),"F":(1250,925,1580,1265)}
print('run\tstd\tnwell4\tother_rules(interior)\tother_rules(on clip edge)')
for f in sorted(glob.glob(d+'/m_*/reports/drc_violations.magic.rpt')):
    n=f.split('/')[-3]; m=re.match(r'm_(.+)_([PCF])_(lef|gds)$',n); arm,w,std=m.groups(); x0,y0,x1,y1=wins[w]
    rule=None; nw=0; nwe=0; inner=collections.Counter(); edge=collections.Counter()
    for l in open(f):
        l=l.rstrip('\n')
        if l.startswith('-') or l.startswith('[INFO]') or l=='clip_top' or not l.strip(): continue
        if l.startswith(' '):
            v=[float(t.replace('um','')) for t in l.split()]
            on_edge = v[0]<=x0+.05 or v[1]<=y0+.05 or v[2]>=x1-.05 or v[3]>=y1-.05
            if rule.endswith('(nwell.4)'):
                if on_edge: nwe+=1
                else: nw+=1
            else:
                on_edge = v[0]<=x0+.05 or v[1]<=y0+.05 or v[2]>=x1-.05 or v[3]>=y1-.05
                (edge if on_edge else inner)[rule]+=1
        else: rule=l
    print('%s_%s\t%s\t%d(+%d on clip edge)\t%s\t%s'%(arm,w,std,nw,nwe,dict(inner) or '-',sum(edge.values())))
