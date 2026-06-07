"""
FAMILY: lead-lag BTC->alts. Mechanism: BTC moves first (deepest liquidity), alts underreact same
bar and catch up next 1-2 bars. Directional, SHORT horizon -> may be orthogonal to slow Donchian
trend. Test: when BTC makes a big 4h move, go long alts next bar(s); measure edge + corr to book.
Variants: (a) follow-through after BTC pump; (b) laggards = alts that under-moved vs BTC catch up.
long-only (matches book). 4h, 25 coins, merged 2021-2026.
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
btc=M["BTCUSDT"].close; br=btc.pct_change(); reg=btc>btc.rolling(200).mean()
alts=[c for c in coins if c!="BTCUSDT"]

# expectancy first: alt fwd-1bar return conditional on BTC last-bar move buckets
print("alt next-bar return vs BTC last-bar move (pooled, all alts):")
rows=[]
for s in alts:
    c=M[s].close; r=c.pct_change()
    d=pd.DataFrame({"alt_fwd":r.shift(-1),"btc":br.reindex(c.index)}).dropna()
    rows.append(d)
A=pd.concat(rows); base=A.alt_fwd.mean()
for lo,hi,lab in [(-1,-0.05,"BTC<-5%"),(-0.05,-0.02,"-5..-2%"),(-0.02,0.02,"flat"),(0.02,0.05,"+2..5%"),(0.05,1,"BTC>+5%")]:
    v=A[(A.btc>=lo)&(A.btc<hi)].alt_fwd
    print(f"  {lab:9s} n={len(v):6d} alt_next {v.mean()*100:7.3f}%  edge {(v.mean()-base)*100:7.3f}%")

THR,H,COST=0.03,1,0.0008
def ll_coin(s):  # follow-through: BTC pumped >THR last bar AND bull regime -> long s for H bars
    c=M[s].close; cv=c.values; brv=br.reindex(c.index).values; bull=reg.reindex(c.index).ffill().fillna(False).values
    p=np.zeros(len(c)); held=0
    for i in range(1,len(c)):
        if held>0: p[i]=1.0; held-=1; continue
        if bull[i] and brv[i-1]>THR: p[i]=1.0; held=H-1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
ll=((1+pd.concat([ll_coin(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
ntr=sum(int(((ll_coin(s)!=0).astype(int).diff()==1).sum()) for s in alts)

def crash_coin(s):  # BTC-crash rebound: BTC dumped < -THR last bar -> long alt, exit +5% or H2 bars
    c=M[s].close; cv=c.values; hv=M[s].high.values; brv=br.reindex(c.index).values
    p=np.zeros(len(c)); ep=0.0; held=0; H2=2
    for i in range(1,len(c)):
        if held>0:
            p[i]=1.0
            if hv[i]/ep-1>=0.05 or held>=H2: held=0
            else: held+=1
            continue
        if brv[i-1]<-0.05: p[i]=1.0; ep=cv[i]; held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
crash=((1+pd.concat([crash_coin(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)

def lag_coin(s):  # laggard catch-up: BTC up >THR but alt under-moved (alt_ret < btc_ret*0.5) -> long next
    c=M[s].close; cv=c.values; ar=c.pct_change().values; brv=br.reindex(c.index).values; bull=reg.reindex(c.index).ffill().fillna(False).values
    p=np.zeros(len(c)); held=0
    for i in range(1,len(c)):
        if held>0: p[i]=1.0; held-=1; continue
        if bull[i] and brv[i-1]>THR and ar[i-1]<brv[i-1]*0.5: p[i]=1.0; held=H-1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
lag=((1+pd.concat([lag_coin(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)

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
ll=ll.reindex(IDX).fillna(0); lag=lag.reindex(IDX).fillna(0); crash=crash.reindex(IDX).fillna(0)
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
print(f"\nfollow-through entries ~{ntr}")
print("\ncorrelations (daily):")
print(pd.DataFrame({"trend":trend,"flush":flush,"leadlag":ll,"laggard":lag,"crashreb":crash}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("leadlag (follow-through)", ll)
row("laggard (catch-up)", lag)
row("crashreb (BTC-crash bounce)", crash)
row("flush standalone", flush)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/leadlag15", 0.6*trend+0.25*flush+0.15*ll)
row("trend60/flush25/crashreb15", 0.6*trend+0.25*flush+0.15*crash)
row("trend60/flush20/crashreb20", 0.6*trend+0.20*flush+0.20*crash)
print("\nDECISION: keep if corr<~0.3 to both AND lifts blend OOS Sharpe above 1.05.")
