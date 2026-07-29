import csv, statistics, glob, os
def rd(p):
    if not os.path.exists(p): return []
    return list(csv.DictReader(open(p)))

def f(x):
    try: return float(x)
    except: return None

# ---- Phase A: main matrix ----
A = rd('/tmp/ycsb_main/summary.csv')
def cell(rows, wl, db, st, arm):
    for r in rows:
        if r['workload']==wl and r['db']==db and r['strategy']==st and r['arm']==arm:
            return r
    return None

READS = ['YC','YCu','YCh01','YCh05','YCh10','YCh20','YCh50','YCo01','YCo05','YCo10','YCo20','YCo50']
print("=== PHASE A: warm-e2e reduction vs baseline (orig layout, async arm) ===")
print(f"{'wl':7} {'base_e2ew':>10} {'2d':>8} {'2d%':>7} {'2f':>10} {'2f%':>8} {'2d_deliv':>8}")
red2d=[]
for wl in READS:
    b=cell(A,wl,'orig','baseline','baseline')
    d=cell(A,wl,'orig','2d','async')
    tf=cell(A,wl,'orig','2f_slru','async')
    if not(b and d): continue
    be=f(b['e2e_warm_median']); de=f(d['e2e_warm_median']); fe=f(tf['e2e_warm_median']) if tf else None
    dpct=100*(de-be)/be; fpct=100*(fe-be)/be if fe else None
    red2d.append(dpct)
    print(f"{wl:7} {be:10.1f} {de:8.1f} {dpct:+6.1f}% {fe:10.1f} {(f'{fpct:+.1f}%' if fpct else 'NA'):>8} {f(d['delivery_pct_median']):7.0f}%")
print(f"\n2d warm-e2e reduction: mean={statistics.mean(red2d):+.1f}% median={statistics.median(red2d):+.1f}% range=[{min(red2d):+.1f},{max(red2d):+.1f}]")

# ---- Phase D: 10-seed CI ----
print("\n=== PHASE D: 10-seed 2d fq reduction (bootstrap-able) ===")
seedrows=[]
for s in range(1,11):
    rows=rd(f'/tmp/ycsb_seed_{s}/summary.csv')
    b=cell(rows,'YC','orig','baseline','baseline'); d=cell(rows,'YC','orig','2d','async')
    if b and d:
        r=100*(f(d['fq_median'])-f(b['fq_median']))/f(b['fq_median'])
        seedrows.append(r)
print(f"per-seed 2d fq reduction: {[f'{x:+.0f}' for x in seedrows]}")
print(f"mean={statistics.mean(seedrows):+.1f}% sd={statistics.stdev(seedrows):.1f} 95%CI≈[{statistics.mean(seedrows)-2*statistics.stdev(seedrows)/len(seedrows)**.5:+.1f},{statistics.mean(seedrows)+2*statistics.stdev(seedrows)/len(seedrows)**.5:+.1f}]")

# ---- Phase C: RAM ----
print("\n=== PHASE C: delivery under RAM pressure ===")
for cap,path in [('none','/tmp/ycsb_ram_none/summary.csv'),('16M','/tmp/ycsb_ram_16M/raw.csv')]:
    rows=rd(path)
    for st in ['2d','2e_K10','2f_slru']:
        vals=[f(r.get('delivery_pct') or r.get('delivery_pct_median')) for r in rows if r['workload']=='YC' and r['strategy']==st and r['arm']=='async']
        vals=[v for v in vals if v is not None]
        if vals: print(f"  {cap:5} YC {st:9}: delivery median={statistics.median(vals):.1f}% (n={len(vals)})")

# ---- Phase B: ablation ----
print("\n=== PHASE B: ablation (YC orig, fq_median async) ===")
Ab=rd('/tmp/ycsb_ablation/summary.csv')
b=cell(Ab,'YC','orig','baseline','baseline')
for st in ['2d','leaf_freq_K10','leaf_rand_K10','2e_K10']:
    d=cell(Ab,'YC','orig',st,'async')
    if b and d:
        print(f"  {st:15}: fq={f(d['fq_median']):.1f} ({100*(f(d['fq_median'])-f(b['fq_median']))/f(b['fq_median']):+.1f}% vs base {f(b['fq_median']):.1f})")
