import csv, os, statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
FONT='assets/fonts/NotoSansCJKtc.otf'
if os.path.exists(FONT):
    fm.fontManager.addfont(FONT); plt.rcParams['font.family']=fm.FontProperties(fname=FONT).get_name()
plt.rcParams['figure.dpi']=130; plt.rcParams['axes.grid']=True; plt.rcParams['grid.alpha']=0.3
OUT='results/ycsb_full/figs'
def rd(p): return list(csv.DictReader(open(p))) if os.path.exists(p) else []
def f(x):
    try: return float(x)
    except: return None
def cell(rows,wl,db,st,arm):
    for r in rows:
        if r['workload']==wl and r['db']==db and r['strategy']==st and r['arm']==arm: return r
C={'baseline':'#9ca3af','layers_5':'#3b82f6','2d':'#10b981','2e_K10':'#059669','2f_slru':'#f59e0b'}

A=rd('/tmp/ycsb_main/summary.csv')
READS=['YC','YCu','YCh01','YCh05','YCh10','YCh20','YCh50','YCo01','YCo05','YCo10','YCo20','YCo50']

# --- Fig 1: Phase A fq reduction across 12 workloads (2d vs 2e) ---
fig,ax=plt.subplots(figsize=(10,4.2))
import numpy as np
x=np.arange(len(READS)); w=0.38
r2d=[100*(f(cell(A,wl,'orig','2d','async')['fq_median'])-f(cell(A,wl,'orig','baseline','baseline')['fq_median']))/f(cell(A,wl,'orig','baseline','baseline')['fq_median']) for wl in READS]
r2e=[100*(f(cell(A,wl,'orig','2e_K10','async')['fq_median'])-f(cell(A,wl,'orig','baseline','baseline')['fq_median']))/f(cell(A,wl,'orig','baseline','baseline')['fq_median']) for wl in READS]
ax.bar(x-w/2,r2d,w,label='2d (interior skeleton)',color=C['2d'])
ax.bar(x+w/2,r2e,w,label='2e_K10 (+top-K leaves)',color=C['2e_K10'])
ax.axhline(0,color='k',lw=0.8); ax.axhline(statistics.median(r2d),color=C['2d'],ls='--',lw=1,alpha=0.6)
ax.set_xticks(x); ax.set_xticklabels(READS,rotation=45,ha='right'); ax.set_ylabel('first-query Δ vs baseline (%)')
ax.set_title(f'Fig A1 — 首查頁錯減少 across 12 原生 YCSB 讀取 workload (orig layout)\n2d 中位 {statistics.median(r2d):+.0f}%  |  2e 中位 {statistics.median(r2e):+.0f}%')
ax.legend(); plt.tight_layout(); plt.savefig(f'{OUT}/figA1_read_matrix.png'); plt.close()

# --- Fig 2: e2e stacked (2d cheap vs 2f trap) for YC ---
fig,ax=plt.subplots(figsize=(7,4.2))
str2=['baseline','layers_5','2d','2e_K10','2f_slru']
pre=[f(cell(A,'YC','orig',s,'async' if s!='baseline' else 'baseline')['preproc_us_median']) for s in str2]
fq=[f(cell(A,'YC','orig',s,'async' if s!='baseline' else 'baseline')['fq_median']) for s in str2]
xb=np.arange(len(str2))
ax.bar(xb,pre,0.6,label='preproc (warming)',color='#c44e52')
ax.bar(xb,fq,0.6,bottom=pre,label='first-query',color='#4c72b0')
ax.set_yscale('log'); ax.set_xticks(xb); ax.set_xticklabels(str2,rotation=20)
ax.set_ylabel('µs (log)'); ax.set_title('Fig A2 — warm-process e2e 分解 (YC, orig)\n2f_slru preproc 吞噬一切 (deliver trap)')
for i,(p,q) in enumerate(zip(pre,fq)): ax.text(i,p+q,f'{p+q:.0f}',ha='center',va='bottom',fontsize=8)
ax.legend(); plt.tight_layout(); plt.savefig(f'{OUT}/figA2_e2e_trap.png'); plt.close()

# --- Fig 3: ablation ---
Ab=rd('/tmp/ycsb_ablation/summary.csv')
fig,ax=plt.subplots(figsize=(7,4))
abst=['baseline','leaf_rand_K10','leaf_freq_K10','2e_K10','2d']
lbl=['baseline','leaf_rand (control)','leaf_freq','2e_K10','2d (interior)']
vals=[f(cell(Ab,'YC','orig',s,'async' if s!='baseline' else 'baseline')['fq_median']) for s in abst]
cols=['#888','#bbb','#f0a','#c44e52','#dd8452']
ax.bar(range(len(abst)),vals,color=cols)
ax.set_xticks(range(len(abst))); ax.set_xticklabels(lbl,rotation=25,ha='right'); ax.set_ylabel('first-query µs')
ax.set_title('Fig B — Ablation (YC): interior skeleton 是槓桿,leaf 頻率 ≈ 隨機對照')
for i,v in enumerate(vals): ax.text(i,v,f'{v:.0f}',ha='center',va='bottom',fontsize=9)
plt.tight_layout(); plt.savefig(f'{OUT}/figB_ablation.png'); plt.close()

# --- Fig 4: RAM pressure delivery ---
fig,ax=plt.subplots(figsize=(7,4))
def deliv(path,st):
    rows=rd(path); vals=[f(r.get('delivery_pct') or r.get('delivery_pct_median')) for r in rows if r['workload']=='YC' and r['strategy']==st and r['arm']=='async']
    vals=[v for v in vals if v is not None]; return statistics.median(vals) if vals else None
caps=['none','16M']; paths=['/tmp/ycsb_ram_none/summary.csv','/tmp/ycsb_ram_16M/raw.csv']
xc=np.arange(len(caps)); w=0.25
for i,st in enumerate(['2d','2e_K10','2f_slru']):
    ax.bar(xc+(i-1)*w,[deliv(p,st) for p in paths],w,label=st,color=C[st])
ax.set_xticks(xc); ax.set_xticklabels([f'{c} cgroup cap' for c in caps]); ax.set_ylabel('prefetch delivery (%)')
ax.set_title('Fig C — RAM 壓力下的 delivery (YC)\ntargeted (2d/2e) 保持 100%,2f_slru 崩到 13%'); ax.legend()
plt.tight_layout(); plt.savefig(f'{OUT}/figC_ram.png'); plt.close()

# --- Fig 5: 10-seed CI ---
seed=[]
for s in range(1,11):
    rows=rd(f'/tmp/ycsb_seed_{s}/summary.csv')
    b=cell(rows,'YC','orig','baseline','baseline'); d=cell(rows,'YC','orig','2d','async')
    if b and d: seed.append(100*(f(d['fq_median'])-f(b['fq_median']))/f(b['fq_median']))
fig,ax=plt.subplots(figsize=(7,4))
ax.bar(range(1,11),seed,color=C['2d'],alpha=0.8)
m=statistics.mean(seed); sd=statistics.stdev(seed); ci=2*sd/len(seed)**0.5
ax.axhline(m,color='k',ls='--',label=f'mean {m:+.1f}%'); ax.axhspan(m-ci,m+ci,alpha=0.2,color='k',label=f'95% CI [{m-ci:+.1f},{m+ci:+.1f}]')
ax.set_xlabel('seed'); ax.set_ylabel('2d first-query Δ (%)'); ax.set_xticks(range(1,11))
ax.set_title('Fig D — 10-seed 穩健性 (YC, 2d):跨獨立 YCSB 抽樣'); ax.legend()
plt.tight_layout(); plt.savefig(f'{OUT}/figD_seeds.png'); plt.close()

# --- Fig 6: size-scaling (all 6 prefetch strategies) ---
S1=rd('/tmp/ycsb_size_1gb/summary.csv')       # layers_5,2d,2e_K10,2f_slru
S2=rd('/tmp/ycsb_size2_1gb/summary.csv')       # layers_92,2e_K500
def cell1gb(st,col):
    src=S2 if st in ('layers_92','2e_K500') else S1
    return f(cell(src,'YC','1gb',st,'async')[col])
fig,(ax1,ax2)=plt.subplots(1,2,figsize=(12,4.2))
sts=['layers_5','layers_92','2d','2e_K10','2e_K500','2f_slru']
for ax,col,title in [(ax1,'preproc_us_median','preproc 成本 (µs, log)'),(ax2,'fq_median','first-query (µs)')]:
    ov=[f(cell(A,'YC','orig',s,'async')[col]) for s in sts]
    sv=[cell1gb(s,col) for s in sts]
    xx=np.arange(len(sts)); w=0.38
    ax.bar(xx-w/2,ov,w,label='orig (600K rows)',color='#4c72b0')
    ax.bar(xx+w/2,sv,w,label='1gb (6M rows)',color='#dd8452')
    if 'preproc' in col: ax.set_yscale('log')
    ax.set_xticks(xx); ax.set_xticklabels(sts,rotation=25,ha='right'); ax.set_title(title); ax.legend(fontsize=8)
fig.suptitle('Fig E — Size-scaling (全 6 strategy):2d 成本持平(~0.1ms)收益增大(fq −57%);2f preproc 仍是 31ms trap')
plt.tight_layout(); plt.savefig(f'{OUT}/figE_size.png'); plt.close()

# --- Fig 7: aging (all 6 static strategies + baseline) ---
Ag=rd('/tmp/ycsb_aging.csv')
AG_STS=[('baseline','#9ca3af','baseline'),('layers_5_static','#3b82f6','layers_5'),
        ('layers_92_static','#1e3a8a','layers_92'),('2d_static','#10b981','2d'),
        ('2e_K10_static','#059669','2e_K10'),('2e_K500_static','#064e3b','2e_K500'),
        ('2f_slru_static','#f59e0b','2f_slru')]
fig,axs=plt.subplots(1,2,figsize=(13,4.6))
for ax,wl in zip(axs,['YD','YE']):
    ck=sorted(set(int(r['checkpoint']) for r in Ag if r['workload']==wl and r['layout']=='orig'))
    for st,c,lbl in AG_STS:
        y=[statistics.median([f(r['first_query_us']) for r in Ag if r['workload']==wl and r['layout']=='orig' and int(r['checkpoint'])==k and r['strategy']==st] or [float('nan')]) for k in ck]
        ax.plot(ck,y,marker='o',ms=4,label=lbl,color=c,lw=1.8)
    ax.set_xlabel('aging checkpoint'); ax.set_ylabel('first-query µs'); ax.set_title(f'{wl} (orig)'); ax.grid(alpha=0.3)
axs[1].legend(fontsize=7.5,ncol=2,loc='upper right')
fig.suptitle('Fig G — Aging (YD read-latest+insert, YE scan+insert):全 6 static t=0 熱集隨 DB 成長的穩定度')
plt.tight_layout(); plt.savefig(f'{OUT}/figG_aging.png'); plt.close()

# --- Fig 8: cadence ---
# `round` is an independent repeat (every round does its own drop-caches), NOT a time axis, so
# there is no trend to draw across it -- group by cadence instead (as figures/08_cadence_comparison
# .py does). Each round waits GAP s after drop-caches before probing, and the background warmer
# re-warms every `cadence` s, so the outcome is bimodal: the warmer either fired inside that gap
# (delivery 100%, first-q ~14 us) or it did not (delivery ~0%, first-q ~600 us). A median alone
# would report ~300 us for cadence=5 -- a value no round ever produced -- so the per-round points
# are drawn on top of the bars.
GAP=3.0                                     # cadence_ycsb.py --gap default
Cd=rd('results/ycsb_full/data/phaseH_cadence.csv')
def _k(c):
    try: return float(c)
    except ValueError: return 1e9
CADS=sorted({r['cadence'] for r in Cd},key=_k)
xs=list(range(len(CADS)))
COLS=['#10b981','#34d399','#fbbf24','#9ca3af'][:len(CADS)] or ['#10b981']
fig,(ax1,ax2)=plt.subplots(1,2,figsize=(11,4.4))
warm_all=[f(r['first_q_us']) for r in Cd if f(r['delivery_pct'])>50]
cold_all=[f(r['first_q_us']) for r in Cd if f(r['delivery_pct'])<=50]
for i,cad in enumerate(CADS):
    rows=[r for r in Cd if r['cadence']==cad]
    n=len(rows); hits=sum(1 for r in rows if f(r['delivery_pct'])>50)
    # deterministic jitter so overlapping rounds stay countable and the figure is reproducible
    for j,r in enumerate(rows):
        warm=f(r['delivery_pct'])>50
        ax1.scatter(i+(j-(n-1)/2)*0.042,f(r['first_q_us']),s=26,zorder=3,
                    color=COLS[i] if warm else '#9ca3af',edgecolor='#374151',lw=0.5)
    ax2.bar(i,100*hits/n,0.62,color=COLS[i],edgecolor='white')
    ax2.text(i,100*hits/n+2,f'{hits}/{n}',ha='center',fontsize=9,fontweight='bold')
for y,txt,col,xa,ha in ((statistics.median(cold_all),f'落回冷讀 ≈ {statistics.median(cold_all):.0f} µs','#6b7280',-0.42,'left'),
                        (statistics.median(warm_all),f'命中熱狀態 ≈ {statistics.median(warm_all):.0f} µs','#059669',len(CADS)-0.58,'right')):
    ax1.axhline(y,ls='--',lw=1,color=col,alpha=0.8)
    ax1.text(xa,y*1.25,txt,fontsize=8.5,color=col,ha=ha,va='bottom')
ax1.annotate(f'{statistics.median(cold_all)/statistics.median(warm_all):.0f}× 差距',
             xy=(len(CADS)-0.58,statistics.median(warm_all)*6),fontsize=9,color='#374151',ha='right')
LBL=[(f'{c} s' if c!='never' else 'never\n(無 warmer)')+('\n≤ gap' if _k(c)<=GAP else '') for c in CADS]
for ax in (ax1,ax2): ax.set_xticks(xs); ax.set_xticklabels(LBL,fontsize=9); ax.set_xlabel('背景 re-warm cadence')
ax1.set_yscale('log'); ax1.set_ylabel('first-query (µs, log)')
ax1.set_ylim(8,1400); ax1.set_yticks([10,30,100,300,1000])
ax1.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
ax1.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
ax1.set_xlim(-0.5,len(CADS)-0.5)
ax1.set_title('每輪的 first-query(8 輪逐點,無中位數)\n結果是二元的:不是命中就是冷讀,中間沒有值')
ax2.set_ylabel('命中熱狀態的輪次比例 (%)'); ax2.set_title('warm-hit rate'); ax2.set_ylim(0,112)
fig.suptitle(f'Fig H — Cadence (YC):warmer 每 cadence 秒重暖一次,每輪 drop-caches 後等 gap={GAP:g}s 才測。\n'
             f'cadence ≤ gap → 每輪都命中(14 µs);cadence 越大命中越少,never 全數落回冷讀(~600 µs)',fontsize=10.5)
plt.tight_layout(rect=[0,0,1,0.88]); plt.savefig(f'{OUT}/figH_cadence.png'); plt.close()

print("figures written:", sorted(os.listdir(OUT)))
