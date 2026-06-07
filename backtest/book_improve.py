"""
IMPROVE THE BOOK (trend + flush + crashreb). Three things, all judged by OOS (2024-26) robustness:
  1. FLUSH param sweep: dump threshold, take-profit, hold -> is current (-8%/+5%/4bar) optimal?
  2. TREND exit/stop sweep: Donchian exit + ATR stop -> can we beat 55/20 + 2.5ATR robustly?
  3. CRASHREB lock: confirm best threshold/hold.
  4. WEIGHTS: search trend/flush/crashreb blend weights for best OOS Sharpe vs current 1.05.
4h, 25 coins, merged 2021-2026.
"""
import numpy as np, pandas as pd
from itertools import product
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean(); alts=[c for c in coins if c!="BTCUSDT"]
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))

# ---- TREND (param sweep) ----
def trend_cfg(exit,stop):
    cfg=dict(strat="donchian",entry=55,exit=exit,risk=5,stop_mult=stop,adx_filter=True,ma_filter=200,btc_regime=reg)
    return pd.concat([backtest(M[s],cfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
trend=trend_cfg(20,2.5)  # current
IDX=trend.index
oo=int(len(IDX)*0.6)

# ---- FLUSH (param sweep) ----
def flush_var(THR,TP,HOLD):
    def fc(s):
        df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
        p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
        for i in range(1,len(c)):
            if held>0:
                p[i]=size
                if hv[i]/ep-1>=TP or held>=HOLD: held=0;size=0.0
                else: held+=1
                continue
            if r[i-1]<THR and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([fc(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
flush=flush_var(-0.08,0.05,4)  # current

# ---- CRASHREB ----
def crash_var(THR,H2):
    def cc(s):
        c=M[s].close; cv=c.values; hv=M[s].high.values; brv=btc.pct_change().reindex(c.index).values
        p=np.zeros(len(c)); ep=0.0; held=0
        for i in range(1,len(c)):
            if held>0:
                p[i]=1.0
                if hv[i]/ep-1>=0.05 or held>=H2: held=0
                else: held+=1
                continue
            if brv[i-1]<THR: p[i]=1.0; ep=cv[i]; held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([cc(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
crashreb=crash_var(-0.05,3)

print("=== 1. FLUSH sweep (OOS) — current = THR-0.08 TP0.05 H4 ===")
best=None
for THR,TP,H in product([-0.06,-0.08,-0.10,-0.12],[0.04,0.05,0.07],[3,4,6]):
    o=met(flush_var(THR,TP,H).iloc[oo:])
    if best is None or o[2]>best[0]: best=(o[2],THR,TP,H,o[1])
    if (THR,TP,H)==(-0.08,0.05,4): print(f"  current      THR{THR} TP{TP} H{H}: OOS Sh{o[2]:.2f} DD{o[1]:.1f}%")
print(f"  best flush   THR{best[1]} TP{best[2]} H{best[3]}: OOS Sh{best[0]:.2f} DD{best[4]:.1f}%")

print("\n=== 2. TREND exit/stop sweep (OOS) — current = exit20 stop2.5 ===")
bt=None
for ex,st in product([10,15,20,30],[2.0,2.5,3.0]):
    o=met(trend_cfg(ex,st).iloc[oo:])
    if bt is None or o[2]>bt[0]: bt=(o[2],ex,st,o[1])
    if (ex,st)==(20,2.5): print(f"  current      exit{ex} stop{st}: OOS Sh{o[2]:.2f} DD{o[1]:.1f}%")
print(f"  best trend   exit{bt[1]} stop{bt[2]}: OOS Sh{bt[0]:.2f} DD{bt[3]:.1f}%")

print("\n=== 3. CRASHREB (OOS) ===")
for THR,H2 in [(-0.04,3),(-0.05,3),(-0.06,3)]:
    o=met(crash_var(THR,H2).iloc[oo:]); print(f"  THR{THR} H{H2}: OOS Sh{o[2]:.2f} DD{o[1]:.1f}%")

print("\n=== 4. WEIGHT search trend/flush/crashreb (OOS) — current trend.7/flush.3 = 1.05 ===")
bw=None
for wt,wf,wc in product([0.5,0.55,0.6,0.65,0.7],[0.15,0.2,0.25,0.3],[0.0,0.1,0.15,0.2]):
    if abs(wt+wf+wc-1.0)>0.001: continue
    o=met((wt*trend+wf*flush+wc*crashreb).iloc[oo:])
    if bw is None or o[2]>bw[0]: bw=(o[2],wt,wf,wc,o[1])
o=met((0.7*trend+0.3*flush).iloc[oo:]); print(f"  current  t.70/f.30/c.00: OOS Sh{o[2]:.2f} DD{o[1]:.1f}%")
print(f"  BEST     t{bw[1]:.2f}/f{bw[2]:.2f}/c{bw[3]:.2f}: OOS Sh{bw[0]:.2f} DD{bw[4]:.1f}%")
# also report full-period of the best weights to check it's not OOS-overfit
fbest=met(bw[1]*trend+bw[2]*flush+bw[3]*crashreb); print(f"           (same weights FULL: Sh{fbest[2]:.2f} DD{fbest[1]:.1f}%)")
print("\nNOTE: trust changes only if better on BOTH OOS and FULL, and not a lone grid spike.")
