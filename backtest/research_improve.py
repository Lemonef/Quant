"""
RESEARCH-DRIVEN improvement + critique stress-test.
A) Donchian lookback ENSEMBLE (Concretum 'Catching Crypto Trends' idea): average signals from
   multiple lookbacks (20/10, 55/20, 100/40) instead of single 55/20. Averaging = less param risk,
   non-overfit. Does it beat/robustify single 55/20?
B) CRITIQUE STRESS TEST: run the improved book (trend.55/flush.25/crash.20) through the 2022 BEAR
   (the dip-buying sleeves flush+crashreb may knife-catch in a grind-down). Check bear DD/return.
   Also full-period + each year. 4h, 25 coins, 2021-2026.
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
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean(); alts=[c for c in coins if c!="BTCUSDT"]
def met(pr):
    pr=pr.dropna()
    if len(pr)<5 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
def trend_cfg(entry,exit):
    cfg=dict(strat="donchian",entry=entry,exit=exit,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
    return pd.concat([backtest(M[s],cfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
t55=trend_cfg(55,20); IDX=t55.index; oo=int(len(IDX)*0.6)
t20=trend_cfg(20,10).reindex(IDX).fillna(0); t100=trend_cfg(100,40).reindex(IDX).fillna(0)
tens=(t20+t55+t100)/3

print("=== A) Donchian ensemble vs single 55/20 ===")
for nm,sr in [("single 55/20",t55),("ens 20+55+100",tens),("lookback 20/10",t20),("lookback 100/40",t100)]:
    f=met(sr); o=met(sr.iloc[oo:]); print(f"  {nm:16s} FULL Sh{f[2]:.2f} CAGR{f[0]:5.1f}% DD{f[1]:6.1f}% | OOS Sh{o[2]:.2f} DD{o[1]:6.1f}%")

# sleeves for the book
def flush_var(HOLD):
    def fc(s):
        df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
        p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
        for i in range(1,len(c)):
            if held>0:
                p[i]=size
                if hv[i]/ep-1>=0.05 or held>=HOLD: held=0;size=0.0
                else: held+=1
                continue
            if r[i-1]<-0.08 and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([fc(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
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
flush=flush_var(2); crash=crash_var(-0.05,3)
book=0.55*t55+0.25*flush+0.20*crash
book_ens=0.55*tens+0.25*flush+0.20*crash

print("\n=== B) CRITIQUE STRESS TEST: improved book by year (does it survive 2022 bear?) ===")
print("  (flush+crash = dip-buyers; 2022 = grind-down bear)")
for yr in [2021,2022,2023,2024,2025,2026]:
    sl=book[book.index.year==yr]
    if len(sl)<20: continue
    f=met(sl); print(f"  {yr}: book CAGR{f[0]:6.1f}% DD{f[1]:6.1f}% Sh{f[2]:5.2f}")
print("\n  sleeve behaviour in 2022 bear (isolate the dip-buyers):")
for nm,sr in [("trend55",t55),("flush",flush),("crashreb",crash),("BOOK",book),("BOOK+ensemble",book_ens)]:
    sl=sr[sr.index.year==2022]; f=met(sl); print(f"   {nm:14s} 2022 CAGR{f[0]:7.1f}% DD{f[1]:6.1f}% Sh{f[2]:5.2f}")
print("\n=== full + OOS: book (single) vs book (ensemble trend) ===")
for nm,sr in [("BOOK single",book),("BOOK ensemble",book_ens)]:
    f=met(sr); o=met(sr.iloc[oo:]); print(f"  {nm:14s} FULL Sh{f[2]:.2f} CAGR{f[0]:5.1f}% DD{f[1]:6.1f}% | OOS Sh{o[2]:.2f} DD{o[1]:6.1f}%")
