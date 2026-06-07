"""
FAMILY: Fibonacci retracement. Buy pullbacks to the 50%/61.8% fib zone of a recent up-swing, in an
uptrend (bull regime), expecting the trend to resume off "support". Honest prior: fib levels have no
mechanism (arbitrary ratios, at best self-fulfilling like S/R) -> expect weak/dead. Test anyway.
Expectancy by retracement bucket + a tradable sleeve + corr to book. 4h, 25 coins, 2021-2026.
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
L,COST=50,0.0008  # swing lookback

# expectancy: fwd-6bar return vs retracement depth into the prior L-bar swing (bull regime only)
print("fwd-6bar return vs retracement % of L-bar up-swing (bull regime, pooled):")
rows=[]
for s in coins:
    c=M[s].close; sh=c.rolling(L).max(); sl=c.rolling(L).min()
    retr=(sh-c)/(sh-sl)   # 0 = at high, 1 = at low
    bull=reg.reindex(c.index).ffill().fillna(False)
    f=c.shift(-6)/c-1
    rows.append(pd.DataFrame({"fwd":f,"retr":retr,"bull":bull}).dropna())
A=pd.concat(rows); A=A[A.bull]; base=A.fwd.mean()
for lo,hi,lab in [(0,0.236,"0-23.6%"),(0.236,0.382,"23.6-38.2"),(0.382,0.5,"38.2-50"),(0.5,0.618,"50-61.8"),(0.618,0.786,"61.8-78.6"),(0.786,1.01,"78.6-100")]:
    v=A[(A.retr>=lo)&(A.retr<hi)].fwd
    print(f"  {lab:11s} n={len(v):6d} fwd {v.mean()*100:7.3f}%  edge {(v.mean()-base)*100:7.3f}%")

ZLO,ZHI,H,TP=0.5,0.705,6,0.06   # 50-61.8 fib zone
def fib_coin(s):
    c=M[s].close; cv=c.values; r=c.pct_change().values
    sh=c.rolling(L).max().values; sl=c.rolling(L).min().values
    bull=reg.reindex(c.index).ffill().fillna(False).values
    p=np.zeros(len(c)); ep=0.0; held=0; slv=0.0
    for i in range(L,len(c)):
        if held>0:
            p[i]=1.0
            if cv[i]>=sh[i] or cv[i]<slv or held>=H or cv[i]/ep-1>=TP: held=0
            else: held+=1
            continue
        rg=sh[i]-sl[i]
        if rg<=0: continue
        retr=(sh[i]-cv[i])/rg
        if bull[i] and ZLO<=retr<=ZHI and r[i]>0:  # in fib zone + up confirm
            p[i]=1.0; ep=cv[i]; slv=sl[i]; held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
fib=((1+pd.concat([fib_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
ntr=sum(int(((fib_coin(s)!=0).astype(int).diff()==1).sum()) for s in coins)

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
fib=fib.reindex(IDX).fillna(0)
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
print(f"\nfib entries ~{ntr}")
print("\ncorrelations:")
print(pd.DataFrame({"trend":trend,"flush":flush,"fib":fib}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("fib standalone", fib)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/fib15", 0.6*trend+0.25*flush+0.15*fib)
print("\nDECISION: keep only if real edge (OOS Sh>0.5) AND lifts blend. Expect dead (fib=no mechanism).")
