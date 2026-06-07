"""
Push for higher risk-adjusted return (then leverage to higher CAGR at same DD).
Techniques:
  1. STRATEGY ENSEMBLE  - blend trend(Donchian+MA) + mean-reversion + TSMOM (anti-correlated)
  2. LONG/SHORT market-neutral cross-sectional momentum (uncorrelated to direction)
  3. CONSTANT-VOL targeting overlay on the blend
All on daily returns, merged 2021-2026, basket. Full / 2022 bear / OOS split + leverage.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest

DATA = Path(__file__).parent / "data"; DPY=365
BASKET = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOGEUSDT"]

def merged(sym):
    df=pd.concat([load(f"{sym}_bear","4h",DATA), load(sym,"4h",DATA)])
    return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in BASKET}
PX=pd.DataFrame({s:M[s].close.resample("1D").last() for s in BASKET}).dropna(how="all")
RET=PX.pct_change().fillna(0.0)

def met(pr):
    pr=pr.dropna();
    if len(pr)<30 or pr.std()==0: return (0,0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    cagr=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    dn=pr[pr<0].std(); so=pr.mean()/dn*np.sqrt(DPY) if dn>0 else 0
    return (cagr*100,dd*100,sh,so)

def voltarget(pr, target=0.40, win=30):
    rv=pr.rolling(win).std()*np.sqrt(DPY)
    return pr*(target/rv).clip(upper=3.0).shift(1).fillna(0.0)

def basket_daily(cfg):
    rs=[]
    for s in BASKET:
        eq,_=backtest(M[s],cfg)
        rs.append(eq.resample("1D").last().ffill().pct_change().rename(s))
    return pd.concat(rs,axis=1).reindex(PX.index).fillna(0.0).mean(axis=1)

# sleeves
trend = basket_daily(dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200))
mrev  = basket_daily(dict(strat="meanrev",risk=5,stop_mult=2.5))
lb=28
sig=(PX/PX.shift(lb)-1)
posL=(sig>0).astype(float).shift(1).fillna(0.0); posL=posL.div(posL.sum(axis=1).replace(0,np.nan),axis=0).fillna(0.0)
tsmom=(posL*RET).sum(axis=1)

# market-neutral long/short cross-sectional
rank=sig.rank(axis=1,ascending=False)
nlong=(rank<=3).astype(float); nshort=(rank>=8).astype(float)
wl=nlong.div(nlong.sum(axis=1).replace(0,np.nan),axis=0).fillna(0.0)
ws=nshort.div(nshort.sum(axis=1).replace(0,np.nan),axis=0).fillna(0.0)
ls_gross=((wl-ws).shift(1).fillna(0.0)*RET).sum(axis=1)   # dollar-neutral, no costs
# realistic costs: short-leg funding/borrow ~15%/yr + turnover slippage on rebalances
turnover=(wl-ws).diff().abs().sum(axis=1).fillna(0.0)
ls=ls_gross - 0.15/DPY - turnover*0.0005

y22a=pd.Timestamp("2022-01-01",tz="UTC"); y22b=pd.Timestamp("2023-01-01",tz="UTC")
def bear(pr): return pr[(pr.index>=y22a)&(pr.index<y22b)]
n=len(trend); oos=int(n*0.6)
def row(tag,pr):
    f=met(pr); b=met(bear(pr)); o=met(pr.iloc[oos:])
    print(f"  {tag:24s} FULL C{f[0]:6.1f}% DD{f[1]:6.1f}% Sh{f[2]:5.2f} | BEAR Sh{b[2]:5.2f} | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")

print("=== individual sleeves (daily, 1x) ===")
row("trend (Don+MA)", trend); row("meanrev", mrev); row("tsmom", tsmom); row("long/short neutral", ls)

print(f"\ncorrelations (daily): trend-mrev {trend.corr(mrev):.2f}  trend-tsmom {trend.corr(tsmom):.2f}  trend-LS {trend.corr(ls):.2f}  mrev-LS {mrev.corr(ls):.2f}")

# ensembles (equal risk via inverse-vol, then constant-vol target)
def ens(streams, vt=0.40):
    df=pd.concat(streams,axis=1).fillna(0.0)
    vol=df.std()*np.sqrt(DPY); w=(1/vol)/(1/vol).sum()
    blend=(df*w).sum(axis=1)
    return voltarget(blend, vt)

print("\n=== ensembles (inverse-vol weight + constant-vol target 40%) ===")
row("trend+mrev", ens([trend,mrev]))
row("trend+tsmom", ens([trend,tsmom]))
row("trend+mrev+tsmom", ens([trend,mrev,tsmom]))
row("trend+mrev+tsmom+LS", ens([trend,mrev,tsmom,ls]))
row("trend+LS", ens([trend,ls]))

print("\n=== trend-tilted blends (fixed weights, vol-target 40%) — keep trend OOS, add LS hedge ===")
for wt in [0.6,0.75,0.85]:
    blend=voltarget(wt*trend + (1-wt)*ls, 0.40)
    row(f"trend{int(wt*100)}/LS{int((1-wt)*100)}", blend)
print("\n  (compare: trend alone OOS Sh 0.61 — does the hedge keep OOS while fixing bear?)")

best=voltarget(0.75*trend+0.25*ls,0.40)
print("\n=== leverage on trend75/LS25 ===")
for L in [1.0,1.5,2.0,2.5,3.0]:
    f=met(best*L); print(f"  {L:.1f}x: CAGR {f[0]:7.1f}%  DD {f[1]:7.1f}%  Sharpe {f[2]:.2f}")
