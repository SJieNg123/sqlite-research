import csv, os
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
FONT='assets/fonts/NotoSansCJKtc.otf'
fm.fontManager.addfont(FONT); plt.rcParams['font.family']=fm.FontProperties(fname=FONT).get_name()
plt.rcParams['figure.dpi']=130
OUT='results/ycsb_full/figs'
def rd(p): return list(csv.DictReader(open(p))) if os.path.exists(p) else []
def f(x):
    try: return float(x)
    except: return None
def cell(rows,st,arm,col):
    for r in rows:
        if r['strategy']==st and r['arm']==arm: return f(r[col])

def seed_path(wl,layout,s):
    if wl=='YC' and layout=='orig': return f'/tmp/ycsb_abl_seed_{s}/summary.csv'
    return f'/tmp/abl2/{wl}_{layout}_s{s}/summary.csv'

WLS=[('YC','A · Zipfian'),('YCu','B · uniform'),('YCh01','C · hotspot 1%')]
ARMS=[('2d','2d (interior · page-type)','#3b82f6'),
      ('leaf_rand_K10','leaf_rand (control)','#9ca3af'),
      ('leaf_freq_K10','leaf_freq (access-freq)','#059669'),
      ('2e_K10','2e_K10 (combined)','#111827')]

def boot(vals,n=10000):
    v=np.array([x for x in vals if x is not None]); 
    if len(v)==0: return (float('nan'),0,0)
    rng=np.random.default_rng(0); m=v[rng.integers(0,len(v),size=(n,len(v)))].mean(axis=1)
    return float(v.mean()), float(np.percentile(m,2.5)), float(np.percentile(m,97.5))

def deltas(wl,layout,arm,col):
    out=[]
    for s in range(1,11):
        rows=rd(seed_path(wl,layout,s)); b=cell(rows,'baseline','baseline',col)
        v=cell(rows,arm,'async',col)
        if b and v: out.append(100*(v-b)/b)
    return out

fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
metrics=[('fq_median','first-query Δ%'),('e2e_warm_median','warm-process e2e Δ%')]
layouts=['orig','ta']
x=np.arange(len(WLS)); w=0.19
for ri,layout in enumerate(layouts):
    for ci,(col,mlabel) in enumerate(metrics):
        ax=axes[ri][ci]
        for ai,(arm,albl,acol) in enumerate(ARMS):
            means=[];los=[];his=[]
            for wl,_ in WLS:
                m,lo,hi=boot(deltas(wl,layout,arm,col)); means.append(m);los.append(m-lo);his.append(hi-m)
            ax.bar(x+(ai-1.5)*w,means,w,yerr=[los,his],capsize=3,color=acol,ec='#444',lw=0.4,
                   label=albl if (ri==0 and ci==0) else None,error_kw={'lw':0.9})
        ax.axhline(0,color='k',lw=0.8); ax.grid(axis='y',alpha=0.3)
        ax.set_title(f'{mlabel} — layout {layout}',fontsize=10)
        if ci==0: ax.set_ylabel(f'{layout}\nΔ% vs baseline (← faster)',fontsize=9)
        ax.set_xticks(x); ax.set_xticklabels([lbl for _,lbl in WLS],fontsize=9)
fig.legend(loc='lower center',ncol=4,fontsize=9,bbox_to_anchor=(0.5,-0.02))
fig.suptitle('Fig 17 (重現) — 選擇槓桿 ablation:3 workload × 2 layout × 2 metric,10-seed 均值 + 95% bootstrap CI\n'
             'interior(2d)=穩健槓桿;leaf_freq(access-freq)≈ leaf_rand(control)→ 頻率非槓桿;2e_K10=interior+leaf 組合',fontsize=10.5)
plt.tight_layout(rect=[0,0.03,1,0.95]); plt.savefig(f'{OUT}/fig17_ablation.png',bbox_inches='tight'); plt.close()
print("wrote fig17_ablation.png (2x2 grid)")
