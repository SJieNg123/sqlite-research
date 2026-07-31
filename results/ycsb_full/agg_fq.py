import csv, statistics, os
def rd(p): return list(csv.DictReader(open(p))) if os.path.exists(p) else []
def f(x):
    try: return float(x)
    except: return None
def cell(rows,wl,db,st,arm):
    for r in rows:
        if r['workload']==wl and r['db']==db and r['strategy']==st and r['arm']==arm: return r
A=rd('/tmp/ycsb_main/summary.csv')
READS=['YC','YCu','YCh01','YCh05','YCh10','YCh20','YCh50','YCo01','YCo05','YCo10','YCo20','YCo50']
print("=== PHASE A: fq_median reduction vs baseline (orig, async) — paper Fig13 metric ===")
r2d=[];r2e=[]
for wl in READS:
    b=cell(A,wl,'orig','baseline','baseline'); d=cell(A,wl,'orig','2d','async'); e=cell(A,wl,'orig','2e_K10','async')
    if not(b and d): continue
    bf=f(b['fq_median']); df=f(d['fq_median']); ef=f(e['fq_median']) if e else None
    p2d=100*(df-bf)/bf; p2e=100*(ef-bf)/bf if ef else None
    r2d.append(p2d); 
    if p2e is not None: r2e.append(p2e)
    print(f"{wl:7} base_fq={bf:7.1f}  2d={df:7.1f} ({p2d:+5.1f}%)  2e={ef if ef else 0:7.1f} ({(f'{p2e:+.1f}%' if p2e is not None else 'NA'):>7})")
print(f"\n2d fq reduction: mean={statistics.mean(r2d):+.1f}% median={statistics.median(r2d):+.1f}% range=[{min(r2d):+.1f},{max(r2d):+.1f}]")
print(f"2e fq reduction: mean={statistics.mean(r2e):+.1f}% median={statistics.median(r2e):+.1f}%")

# layout comparison for YC
print("\n=== YC across layouts (2d fq reduction) ===")
for db in ['orig','vacuum','ta']:
    b=cell(A,'YC',db,'baseline','baseline'); d=cell(A,'YC',db,'2d','async')
    if b and d: print(f"  {db:7}: base={f(b['fq_median']):.1f} 2d={f(d['fq_median']):.1f} ({100*(f(d['fq_median'])-f(b['fq_median']))/f(b['fq_median']):+.1f}%)")
