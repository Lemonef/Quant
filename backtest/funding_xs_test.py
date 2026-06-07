"""
FAMILY: cross-sectional funding reversion (positioning/crowding factor). Mechanism (real, documented):
perp funding rate = a crowding gauge. Very POSITIVE funding = crowded longs paying shorts = overheated
-> tends to mean-revert DOWN. Very NEGATIVE = crowded shorts = squeeze UP. Trade it cross-sectionally:
each day LONG the most-negative-funding coins, SHORT the most-positive. Market-neutral -> should be
~uncorrelated to trend(momentum) & flush(abs reversion). Also test a long-only variant (long neg-funding).
Uses real Binance funding (8h) + perp close. 25 coins, daily rebalance, 2021-2026.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists() and (DATA/f"{s}_funding.csv").exists() and (DATA/f"{s}_perp_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
print(f"{len(coins)} coins with funding+perp data")

# --- daily funding panel (sum of 3 prints/day) + daily perp returns ---
def fund_daily(s):
    f=pd.read_csv(DATA/f"{s}_funding.csv"); f.index=pd.to_datetime(f.fundingTime,unit="ms",utc=True)
    return f.fundingRate.resample("1D").sum().rename(s)
def perp_daily_ret(s):
    p=pd.read_csv(DATA/f"{s}_perp_4h.csv"); p.index=pd.to_datetime(p.open_time,unit="ms",utc=True)
    return p.close.resample("1D").last().pct_change().rename(s)
F=pd.concat([fund_daily(s) for s in coins],axis=1)
R=pd.concat([perp_daily_ret(s) for s in coins],axis=1).reindex(F.index)
F=F.reindex(R.index)
# require >=10 coins with data each day
valid=F.notna().sum(axis=1)>=10
F,R=F[valid],R[valid]

# --- cross-sectional: rank by trailing funding (mean last LB days), long bottom Q, short top Q ---
LB,Q,COST=1,5,0.0008   # Q=5 -> quintiles
sig=F.rolling(LB).mean()
def xs_ret(longshort=True):
    out=[]
    idx=sig.index
    for d in range(LB,len(idx)-1):
        row=sig.iloc[d].dropna()
        if len(row)<10: out.append((idx[d+1],0.0)); continue
        k=max(1,len(row)//Q)
        srt=row.sort_values()
        longs=srt.index[:k]            # most negative funding
        shorts=srt.index[-k:]          # most positive funding
        nr=R.iloc[d+1]
        rl=nr[longs].mean()
        if longshort:
            rs=nr[shorts].mean(); pnl=(rl-rs)/2.0 - COST  # ~1 turnover/day each side
        else:
            pnl=rl - COST
        out.append((idx[d+1],pnl if pd.notna(pnl) else 0.0))
    return pd.Series(dict(out))
xs_ls=xs_ret(True); xs_lo=xs_ret(False)

# baselines
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()
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
xs_ls=xs_ls.reindex(IDX).fillna(0); xs_lo=xs_lo.reindex(IDX).fillna(0)
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
print("\ncorrelations (daily):")
print(pd.DataFrame({"trend":trend,"flush":flush,"fund_LS":xs_ls,"fund_LO":xs_lo}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("fund_LS (long-short) standalone", xs_ls)
row("fund_LO (long-only neg) standalone", xs_lo)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/fundLS15", 0.6*trend+0.25*flush+0.15*xs_ls)
row("trend60/flush25/fundLO15", 0.6*trend+0.25*flush+0.15*xs_lo)
print("\nfunding cost itself NOT added to LS pnl (we COLLECT funding on the right side -> conservative).")
print("DECISION: keep if corr<~0.3 to both AND OOS Sharpe>0 AND lifts blend OOS Sharpe.")
