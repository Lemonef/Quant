"""
NEW FAMILY CANDIDATE: liquidity-sweep reclaim (the testable core of the ICT/LuxAlgo "AMD" /
smart-money pattern from the TikTok). Mechanism: price pierces BELOW a prior N-bar range low
(stop-run / "manipulation") then CLOSES back above it (reclaim) -> long. This is a false-breakout
reversion. Question: does it have edge, and is it UNCORRELATED to our existing flush sleeve
(big-% capitulation reversion)? If corr<~0.3 and OOS-positive -> genuinely new sleeve.
4h, ~25 coins, merged 2021-2026. Exit rules mirror flush (+5% or N bars) for a fair correlation test.
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

# trend & flush (existing book) for correlation baseline
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index
def flush_coin(s):
    df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
    p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
    for i in range(1,len(c)):
        if held>0:
            p[i]=size
            if hv[i]/ep-1>=0.05 or held>=4: held=0;size=0.0
            else: held+=1
            continue
        if r[i-1]<-0.08 and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*0.0008).rename(s)
flush=((1+pd.concat([flush_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)

# --- sweep-reclaim: low[i] < prior L-bar range low, but close[i] reclaims above it ---
L,HOLD,TPCT=20,4,0.05
def sweep_coin(s):
    df=M[s]; c=df.close; cv=c.values; lo=df.low.values; hv=df.high.values
    prior_low=df.low.rolling(L).min().shift(1).values   # range low formed BEFORE this bar
    p=np.zeros(len(c)); ep=0.0; held=0
    for i in range(L+1,len(c)):
        if held>0:
            p[i]=1.0
            if hv[i]/ep-1>=TPCT or held>=HOLD: held=0
            else: held+=1
            continue
        pl=prior_low[i]
        if not np.isnan(pl) and lo[i]<pl and cv[i]>pl:   # pierced low then reclaimed on close
            p[i]=1.0; ep=cv[i]; held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*0.0008).rename(s)
sweep=((1+pd.concat([sweep_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)

# --- GATED variant: BTC-bull regime only + min sweep depth + tight accumulation range before ---
DEPTH,RANGEMAX=0.015,0.12   # pierce prior low by >=1.5%; prior L-bar range width <=12% (real accumulation)
regH=reg.reindex(btc.index).ffill()
def sweep2_coin(s):
    df=M[s]; c=df.close; cv=c.values; lo=df.low.values; hv=df.high.values
    plow=df.low.rolling(L).min().shift(1).values; phigh=df.high.rolling(L).max().shift(1).values
    bull=regH.reindex(c.index).ffill().fillna(False).values
    p=np.zeros(len(c)); ep=0.0; held=0
    for i in range(L+1,len(c)):
        if held>0:
            p[i]=1.0
            if hv[i]/ep-1>=TPCT or held>=HOLD: held=0
            else: held+=1
            continue
        pl=plow[i]; ph=phigh[i]
        if (not np.isnan(pl) and bull[i] and lo[i]<pl*(1-DEPTH) and cv[i]>pl
                and (ph/pl-1)<=RANGEMAX):
            p[i]=1.0; ep=cv[i]; held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*0.0008).rename(s)
sweep2=((1+pd.concat([sweep2_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
n2=sum(int(((sweep2_coin(s)!=0).astype(int).diff()==1).sum()) for s in coins)

def met(pr):
    pr=pr.dropna()
    if pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return (eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY)
oo=int(len(IDX)*0.6)
# trade count sanity
ntr=sum(int(((sweep_coin(s)!=0).astype(int).diff()==1).sum()) for s in coins)
print(f"sweep-reclaim entries (approx, all coins): ~{ntr}")
print(f"sweep-reclaim GATED entries (all coins): ~{n2}")
print("\ncorrelations (daily returns):")
print(pd.DataFrame({"trend":trend,"flush":flush,"sweep":sweep,"sweep2":sweep2}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("sweep standalone (raw)", sweep)
row("sweep2 standalone (gated)", sweep2)
row("trend65/flush25/sweep2_10", 0.65*trend+0.25*flush+0.10*sweep2)
row("flush standalone", flush)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend65/flush25/sweep10", 0.65*trend+0.25*flush+0.10*sweep)
row("trend60/flush20/sweep20", 0.60*trend+0.20*flush+0.20*sweep)
print("\nDECISION: add sweep only if corr-to-flush <~0.3 AND it lifts OOS Sharpe of the blend.")
