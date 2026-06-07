"""Is RSI14<25 oversold-reversion a NEW sleeve or redundant with flush? Correlations + blend test."""
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
def rsi(c,n):
    d=c.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-d).clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    return (100-100/(1+up/dn.replace(0,np.nan))).fillna(50)
# trend
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index
# flush (config D)
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
# rsi14<25 reversion: enter rsi<25, exit rsi>50 or 6 bars
def rsirev_coin(s):
    c=M[s].close; rv=rsi(c,14).values; cv=c.values
    p=np.zeros(len(c)); held=0
    for i in range(1,len(c)):
        if held>0:
            p[i]=1.0
            if rv[i]>50 or held>=6: held=0
            else: held+=1
            continue
        if rv[i]<25: p[i]=1.0; held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*0.0006).rename(s)
rsirev=((1+pd.concat([rsirev_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)

def met(pr):
    pr=pr.dropna()
    if pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return (eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY)
oo=int(len(IDX)*0.6)
print("correlations:")
print(pd.DataFrame({"trend":trend,"flush":flush,"rsirev":rsirev}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:26s} FULL Sh{f[2]:.2f} DD{f[1]:5.1f}% | OOS C{o[0]:5.1f}% DD{o[1]:5.1f}% Sh{o[2]:.2f}")
print("\nsleeves + blends:")
row("rsirev standalone", rsirev)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/rsirev15", 0.6*trend+0.25*flush+0.15*rsirev)
row("trend55/flush25/rsirev20", 0.55*trend+0.25*flush+0.20*rsirev)
