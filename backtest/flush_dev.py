"""
Develop the flush-reversion sleeve. Test improvements vs the baseline (thr -12%, hold 6 bars):
  A. bounce-target exit (exit on +X% or after maxbars) instead of fixed hold
  B. magnitude sizing (bigger flush -> bigger position)
  C. knife filter (require a green confirmation bar before entering)
  D. lower threshold -8% (more signals) with the above
Report each: CAGR/DD/Sharpe full+OOS, trades, corr to trend, and blended-with-trend Sharpe/DD.
4h, 25 coins, merged 2021-2026.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)

def met(pr):
    pr=pr.dropna()
    if len(pr)<30 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return (eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY)

def flush_coin(s, thr, target, maxbars, knife, magsize):
    df=M[s]; c=df.close; r=c.pct_change()
    p=np.zeros(len(c)); entry_px=0.0; held=0; size=0.0
    rv=r.values; cv=c.values; hv=df.high.values
    for i in range(1,len(c)):
        if held>0:
            p[i]=size
            # exit: bounce target hit (this bar high) or maxbars
            if hv[i]/entry_px-1 >= target or held>=maxbars:
                held=0; size=0.0
            else:
                held+=1
            continue
        # entry: prior bar flushed; knife filter -> require this bar not also down hard
        if rv[i-1] < thr and (not knife or rv[i] > -0.02):
            size = min(3.0, abs(rv[i-1])/0.10) if magsize else 1.0   # bigger flush -> up to 3x unit
            p[i]=size; entry_px=cv[i]; held=1
    pos=pd.Series(p,index=c.index)
    cost=pos.diff().abs().fillna(0)*0.0008
    return (pos.shift(1).fillna(0)*r - cost).rename(s)

def basket(thr,target,maxbars,knife,magsize):
    fr=pd.concat([flush_coin(s,thr,target,maxbars,knife,magsize) for s in coins],axis=1).fillna(0.0).mean(axis=1)
    return ((1+fr).resample("1D").prod()-1)

configs={
 "baseline -12/6bars":      dict(thr=-0.12,target=99,maxbars=6,knife=False,magsize=False),
 "A bounce+6":              dict(thr=-0.12,target=0.06,maxbars=6,knife=False,magsize=False),
 "B mag+bounce":            dict(thr=-0.10,target=0.06,maxbars=6,knife=False,magsize=True),
 "C knife+mag+bounce":      dict(thr=-0.10,target=0.06,maxbars=6,knife=True,magsize=True),
 "D -8 knife+mag+bounce":   dict(thr=-0.08,target=0.05,maxbars=4,knife=True,magsize=True),
}
ti=trend.index; oo=int(len(ti)*0.6)
print(f"{'config':24s} FULL(Sh/DD) OOS(C/DD/Sh)   corr   blend70/30(Sh/DD/OOSsh)")
for name,cf in configs.items():
    fd=basket(**cf).reindex(ti).fillna(0.0)
    f=met(fd); o=met(fd.iloc[oo:]); corr=fd.corr(trend)
    bl=0.7*trend+0.3*fd; bf=met(bl); bo=met(bl.iloc[oo:])
    print(f"{name:24s} {f[2]:4.2f}/{f[1]:5.1f}  {o[0]:5.1f}/{o[1]:5.1f}/{o[2]:4.2f}  {corr:5.2f}  {bf[2]:.2f}/{bf[1]:5.1f}/{bo[2]:.2f}")
