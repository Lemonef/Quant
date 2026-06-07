"""
FAMILY: volatility-regime squeeze breakout. Mechanism: vol compresses (Bollinger-width in a low
percentile = "squeeze"), then price breaks the range -> ride the expansion. Tests whether timing
breakouts by vol-compression beats plain trend, AND whether it's uncorrelated. Expectation: this is
a momentum/breakout family -> likely CORRELATES with trend (so judge it as a trend *improver*, not a
new sleeve). long-only, btc-bull gated, ATR stop. 4h, 25 coins, merged 2021-2026.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest, atr as ATR
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()

# baselines
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

# squeeze breakout: BBW percentile low -> break 20-high; exit 10-low or 3*ATR stop; bull gated
BB,BBN,PCT,ENT,EXT,STOP,COST=20,100,0.25,20,10,3.0,0.0008
regH=reg
def sq_coin(s):
    df=M[s]; c=df.close; cv=c.values; hi=df.high; lo=df.low
    ma=c.rolling(BB).mean(); sd=c.rolling(BB).std(); bbw=(2*sd/ma)
    sq=(bbw<=bbw.rolling(BBN).quantile(PCT)).values
    up=hi.rolling(ENT).max().shift(1).values; dn=lo.rolling(EXT).min().shift(1).values
    a=ATR(df,14).values
    bull=regH.reindex(c.index).ffill().fillna(False).values
    p=np.zeros(len(c)); ep=0.0; inpos=False
    for i in range(BBN+1,len(c)):
        if inpos:
            p[i]=1.0
            if cv[i]<dn[i] or cv[i]<ep-STOP*a[i]: inpos=False
            continue
        if bull[i] and sq[i-1] and cv[i]>up[i]:   # was squeezed, now breaks out
            inpos=True; ep=cv[i]; p[i]=1.0
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
sq=((1+pd.concat([sq_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
ntr=sum(int(((sq_coin(s)!=0).astype(int).diff()==1).sum()) for s in coins)

def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
print(f"squeeze-breakout entries (all coins): ~{ntr}")
print("\ncorrelations (daily):")
print(pd.DataFrame({"trend":trend,"flush":flush,"squeeze":sq}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("squeeze standalone", sq)
row("trend standalone", trend)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/squeeze15", 0.6*trend+0.25*flush+0.15*sq)
row("squeeze50/flush50", 0.5*sq+0.5*flush)
print("\nDECISION: if corr-to-trend high -> it's a trend variant; keep only if it beats trend's own OOS Sharpe.")
