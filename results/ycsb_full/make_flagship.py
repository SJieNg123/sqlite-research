import csv, os, statistics
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Patch
FONT='assets/fonts/NotoSansCJKtc.otf'
fm.fontManager.addfont(FONT); plt.rcParams['font.family']=fm.FontProperties(fname=FONT).get_name()
plt.rcParams['figure.dpi']=130
OUT='results/ycsb_full/figs'
def rd(p): return list(csv.DictReader(open(p)))
def f(x):
    try: return float(x)
    except: return None
A=rd('/tmp/ycsb_main/summary.csv')
def cell(wl,db,st):
    arm='baseline' if st=='baseline' else 'async'
    for r in A:
        if r['workload']==wl and r['db']==db and r['strategy']==st and r['arm']==arm: return r
STRATS=['baseline','layers_5','layers_92','2d','2e_K10','2e_K500','2f_slru']
PANELS=[('YC','Zipfian (YCSB-C)'),('YCu','Uniform read'),('YCh01','Hotspot 1% (tight WS)')]

# ============ Fig 14 — stacked e2e decomposition (flagship) ============
# first-query (solid) is coloured PER STRATEGY (same palette as Fig 13);
# deliver is gold hatched, cold-open is grey cross-hatched (paper convention).
# EXACT paper palette (figures/plot_utils.py STRATEGY_COLORS)
SCOL={'baseline':'#9ca3af','layers_5':'#3b82f6','layers_92':'#1e3a8a',
      '2d':'#10b981','2e_K10':'#059669','2e_K500':'#064e3b','2f_slru':'#f59e0b'}
col_dl='#fbbf24'; col_op='#d1d5db'   # deliver amber ///, open grey xx (paper Fig 14)
fig,axes=plt.subplots(1,3,figsize=(15,5.2),sharey=True)
for ax,(wl,title) in zip(axes,PANELS):
    base=f(cell(wl,'orig','baseline')['fq_median'])
    x=np.arange(len(STRATS))
    for i,st in enumerate(STRATS):
        c=cell(wl,'orig',st)
        fq=f(c['fq_median']); dl=f(c['deliver_us_median']); op=f(c['open_us_median'])
        ax.bar(i,fq,0.62,color=SCOL[st],alpha=0.9,edgecolor='black',lw=0.5,zorder=3)
        ax.bar(i,dl,0.62,bottom=fq,color=col_dl,alpha=0.95,hatch='///',edgecolor='black',lw=0.5,zorder=3)
        ax.bar(i,op,0.62,bottom=fq+dl,color=col_op,alpha=0.95,hatch='xx',edgecolor='black',lw=0.5,zorder=3)
        ewarm=fq+dl
        pct=100*(ewarm-base)/base
        if st=='baseline': continue
        lbl=f'{pct:+.0f}%'
        ax.text(i,(fq+dl+op)*1.07,lbl,ha='center',va='bottom',fontsize=8.5,
                color=('#15803d' if pct<0 else '#dc2626'),fontweight='bold')
    ax.axhline(base,ls='--',color='#9ca3af',lw=1,alpha=0.7,zorder=2)
    ax.set_yscale('log'); ax.set_xticks(x); ax.set_xticklabels(STRATS,rotation=40,ha='right',fontsize=9)
    ax.set_title(f'{wl} — {title}',fontsize=11); ax.set_ylim(80,None); ax.grid(axis='y',alpha=0.3,zorder=0)
axes[0].set_ylabel('end-to-end cold start (µs, log)',fontsize=10)
leg=[Patch(fc='#cccccc',ec='#888',label='first-query (SQL) — 各 strategy 自身顏色'),
     Patch(fc=col_dl,hatch='//',label='deliver (prefetch syscalls)'),
     Patch(fc=col_op,hatch='xx',label='cold open(db) — saved if integrated')]
axes[0].legend(handles=leg,loc='upper left',fontsize=8,framealpha=0.95)
fig.suptitle('Fig 14 (重現) — 冷啟動 e2e 分解 × 原生 YCSB:整根=e2e_std,去灰段=e2e_warm;綠=warm 改善,紅=回歸',fontsize=11.5)
fig.text(0.5,0.005,'2f_slru 取得最低 first-query 卻因 deliver 爆炸使 e2e 慘敗;2e_K500 過度配置葉預算 → deliver 膨脹 → 回歸;2d/layers_92 為甜蜜點',
         ha='center',fontsize=9,color='#444')
plt.tight_layout(rect=[0,0.03,1,0.96]); plt.savefig(f'{OUT}/fig14_e2e_stacked.png'); plt.close()

# ============ Fig 13 — paired first-query reduction, all strategies ============
fig,axes=plt.subplots(1,3,figsize=(15,4.6),sharey=True)
bars=['layers_5','layers_92','2d','2e_K10','2e_K500','2f_slru']
cmap={'layers_5':'#3b82f6','layers_92':'#1e3a8a','2d':'#10b981','2e_K10':'#059669','2e_K500':'#064e3b','2f_slru':'#f59e0b'}
for ax,(wl,title) in zip(axes,PANELS):
    base=f(cell(wl,'orig','baseline')['fq_median'])
    vals=[100*(f(cell(wl,'orig',s)['fq_median'])-base)/base for s in bars]
    ax.bar(range(len(bars)),vals,color=[cmap[s] for s in bars],zorder=3)
    for i,v in enumerate(vals): ax.text(i,v+(1 if v<0 else -1),f'{v:+.0f}',ha='center',va='bottom' if v<0 else 'top',fontsize=8)
    ax.axhline(0,color='k',lw=0.8); ax.set_xticks(range(len(bars))); ax.set_xticklabels(bars,rotation=40,ha='right',fontsize=9)
    ax.set_title(f'{wl} — {title}',fontsize=11); ax.grid(axis='y',alpha=0.3,zorder=0)
axes[0].set_ylabel('first-query Δ vs baseline (%)',fontsize=10)
fig.suptitle('Fig 13 (重現) — 各 strategy 的 first-query 減少 × 原生 YCSB:2f_slru first-q 減最多,但 Fig 14 顯示不轉化為 e2e 勝利',fontsize=11)
plt.tight_layout(rect=[0,0,1,0.95]); plt.savefig(f'{OUT}/fig13_firstq_bars.png'); plt.close()
print("wrote fig13_firstq_bars.png, fig14_e2e_stacked.png")
