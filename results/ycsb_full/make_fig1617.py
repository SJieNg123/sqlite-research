import csv, os, statistics
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
def cell(rows,st,arm,col='fq_median'):
    for r in rows:
        if r['strategy']==st and r['arm']==arm: return f(r[col])

# ---- helper: per-seed Δ% + bootstrap 95% CI ----
def boot_ci(vals,n=10000):
    vals=np.array(vals); k=len(vals)
    rng=np.random.default_rng(0)   # fixed seed → reproducible CI
    means=vals[rng.integers(0,k,size=(n,k))].mean(axis=1)
    return float(np.mean(vals)), float(np.percentile(means,2.5)), float(np.percentile(means,97.5))

# ============ Fig 17 — ablation dual panel, 10-seed + CI ============
ARMS=['2d','2e_K10','leaf_freq_K10','leaf_rand_K10']
LBL={'2d':'2d\n(interior)','2e_K10':'2e_K10\n(int+leaf)','leaf_freq_K10':'leaf_freq\n(hot leaves)','leaf_rand_K10':'leaf_rand\n(control)'}
COL={'2d':'#45c393','2e_K10':'#2fac7e','leaf_freq_K10':'#8e44ad','leaf_rand_K10':'#aaaaaa'}
def seed_deltas(col_warm):
    out={a:[] for a in ARMS}
    for s in range(1,11):
        rows=rd(f'/tmp/ycsb_abl_seed_{s}/summary.csv')
        base=cell(rows,'baseline','baseline',col_warm)
        if not base: continue
        for a in ARMS:
            v=cell(rows,a,'async',col_warm)
            if v: out[a].append(100*(v-base)/base)
    return out
fig,(ax1,ax2)=plt.subplots(1,2,figsize=(12,4.8),sharex=True)
for ax,col,title in [(ax1,'fq_median','first-query Δ% (10-seed)'),(ax2,'e2e_warm_median','warm-process e2e Δ% (10-seed)')]:
    d=seed_deltas(col)
    for i,a in enumerate(ARMS):
        m,lo,hi=boot_ci(d[a])
        ax.bar(i,m,0.6,color=COL[a],yerr=[[m-lo],[hi-m]],capsize=5,error_kw={'lw':1.3})
        ax.text(i,m+(1 if m<0 else -1),f'{m:+.0f}%',ha='center',va='bottom' if m<0 else 'top',fontsize=9,fontweight='bold')
    ax.axhline(0,color='k',lw=0.8); ax.set_xticks(range(len(ARMS))); ax.set_xticklabels([LBL[a] for a in ARMS],fontsize=8.5)
    ax.set_title(title,fontsize=11); ax.grid(axis='y',alpha=0.3)
ax1.set_ylabel('Δ vs baseline (%)')
fig.suptitle('Fig 17 (重現) — 選擇槓桿 ablation (YC, 10-seed 均值 + 95% bootstrap CI)\ninterior (2d) 是唯一穩健槓桿;leaf_freq 與 leaf_rand 控制組打平 → 葉「頻率」本身不是槓桿',fontsize=11)
plt.tight_layout(rect=[0,0,1,0.92])
# The 10-seed ablation inputs live in /tmp and do not survive a reboot. Without them every bar
# is NaN, so refuse to overwrite the committed figure with an empty one -- fail loud, not quiet.
if any(seed_deltas('fq_median').values()):
    plt.savefig(f'{OUT}/fig17_ablation.png'); print("wrote fig17_ablation.png")
else:
    print("SKIP fig17_ablation.png: no /tmp/ycsb_abl_seed_*/summary.csv on disk; "
          "keeping the committed figure (re-run the ablation sweep to refresh it)")
plt.close()

# ============ Fig 16 — RAM cap sweep dual panel (all 6 prefetch strategies) ============
# Data provenance: 128M..16M was measured on nvme0n1 / kernel 6.17.0-19; the 12M/8M/6M points
# on nvme1n1 / kernel 6.17.0-41 (see data/phaseC_env2.txt). 16M was re-run on the second machine
# state as an overlap check -- all 6 prefetch strategies moved only +0.5..+1.9% and 2f_slru
# delivery reproduced 13.3% -> 13.4%, so the two stretches are plotted as one continuous series.
# Only the no-prefetch baseline differed there (-7.4%); the dashed baseline line below is the
# original one (data/phaseC_ram_none.csv). data/phaseC_ram_none_env2.csv holds the other.
CAPS =[('128M',128),('64M',64),('48M',48),('32M',32),('24M',24),('20M',20),('16M',16)]
CAPS2=[('12M',12),('8M',8),('6M',6)]   # 16M was also re-measured in env2 as the overlap anchor
                                       # (data/fig16_ramsweep*_16M_env2.csv); the env1 16M point
                                       # is the one plotted, so the series stays continuous.
DATA='results/ycsb_full/data'
# strategy -> (color, which sweep the strategy lives in)
STS=[('layers_5','#3b82f6','ramsweep2'),('layers_92','#1e3a8a','ramsweep2'),
     ('2d','#10b981','ramsweep'),('2e_K10','#059669','ramsweep'),
     ('2e_K500','#064e3b','ramsweep2'),('2f_slru','#f59e0b','ramsweep')]
def sweep_val(cap,st,col,src,env2=False):
    rows=rd(f'{DATA}/fig16_{src}_{cap}{"_env2" if env2 else ""}.csv')
    return cell(rows,st,'async',col)
base_none =cell(rd(f'{DATA}/phaseC_ram_none.csv'),'baseline','baseline','fq_median') or 855
fig,(ax1,ax2)=plt.subplots(1,2,figsize=(12,4.6))
# Categorical x (paper convention, figures/16_ram_pressure_sweep.py): a linear MB axis spends
# half its width on the flat 128->64 stretch and squashes the 16->6 collapse into a corner.
TICKS=[c for c,_ in CAPS]+[c for c,_ in CAPS2]
xs=list(range(len(TICKS)))
for st,c,src in STS:
    for col,ax in (('delivery_pct_median',ax1),('fq_median',ax2)):
        ys=[sweep_val(cap,st,col,src) for cap,_ in CAPS] \
          +[sweep_val(cap,st,col,src,env2=True) for cap,_ in CAPS2]
        ax.plot(xs,ys,marker='o',label=st,color=c,lw=2)
ax2.axhline(base_none,ls='--',color='#888',label='baseline first-q')
for ax in (ax1,ax2):
    ax.set_xticks(xs); ax.set_xticklabels(TICKS,fontsize=8)
    ax.set_xlabel('cgroup MemoryMax cap (越右越緊,等距刻度)')
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
ax1.set_ylabel('prefetch delivery (%)'); ax1.set_title('delivery vs RAM 壓力'); ax1.set_ylim(-5,105)
ax2.set_ylabel('first-query (µs)'); ax2.set_title('first-query vs RAM 壓力')
fig.suptitle('Fig 16 (重現+延伸至 6M) — RAM 壓力掃描 (YC):targeted (2d/2e/layers) delivery 恆 100%、first-q 持平,\n即使 cgroup 僅 6M(DB 的 1/17);2f_slru delivery 隨 cap 收緊崩潰 13.3%→3.5%,first-q 回升向 baseline',fontsize=11)
plt.tight_layout(rect=[0,0,1,0.93]); plt.savefig(f'{OUT}/fig16_ram_sweep.png'); plt.close()
print("wrote fig16_ram_sweep.png")
