"""
FIX THE REAL WEAKNESS (from bear stress test): the dip-buying sleeves (flush, crashreb) knife-catch
in bears (2022 Sh -1.10/-0.61). Trend already goes to cash via 200MA; flush/crashreb do NOT. Test
REGIME-GATING the dip-buyers: only fire when BTC is not in a confirmed downtrend. Gates tried:
  raw      : current (no gate)
  ma200    : only when BTC > 200-bar MA (same as trend's filter)
  ma100    : looser (BTC > 100-bar MA)
  notdown  : BTC not below MA AND BTC 30-bar return > -10% (avoid only hard downtrends)
Goal: cut 2022/2026 bear losses WITHOUT killing 2023-24 bull gains. 4h, 25 coins.
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
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index; oo=int(len(IDX)*0.6)

GATES={
 "raw":     lambda idx: pd.Series(True,index=idx),
 "ma200":   lambda idx: (btc>btc.rolling(200).mean()).reindex(idx).ffill().fillna(False),
 "ma100":   lambda idx: (btc>btc.rolling(100).mean()).reindex(idx).ffill().fillna(False),
 "notdown": lambda idx: ((btc>btc.rolling(200).mean())|(btc.pct_change(30)>-0.10)).reindex(idx).ffill().fillna(False),
}
def flush_g(gate):
    def fc(s):
        df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
        g=gate(c.index).values; p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
        for i in range(1,len(c)):
            if held>0:
                p[i]=size
                if hv[i]/ep-1>=0.05 or held>=2: held=0;size=0.0
                else: held+=1
                continue
            if g[i] and r[i-1]<-0.08 and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([fc(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
def crash_g(gate):
    def cc(s):
        c=M[s].close; cv=c.values; hv=M[s].high.values; brv=btc.pct_change().reindex(c.index).values
        g=gate(c.index).values; p=np.zeros(len(c)); ep=0.0; held=0
        for i in range(1,len(c)):
            if held>0:
                p[i]=1.0
                if hv[i]/ep-1>=0.05 or held>=3: held=0
                else: held+=1
                continue
            if g[i] and brv[i-1]<-0.05: p[i]=1.0; ep=cv[i]; held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([cc(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)

print(f"{'gate':8s} | {'2022 bear':>22s} | {'2026 down':>16s} | {'2023-24 bull (OOS-ish)':>14s} | full/OOS book")
print("-"*100)
for gname,gate in GATES.items():
    fl=flush_g(gate); cr=crash_g(gate); book=0.55*trend+0.25*fl+0.20*cr
    b22=met(book[book.index.year==2022]); b26=met(book[book.index.year==2026])
    b23=met(book[book.index.year.isin([2023,2024])]); f=met(book); o=met(book.iloc[oo:])
    print(f"{gname:8s} | 2022 C{b22[0]:6.1f}% DD{b22[1]:6.1f}% Sh{b22[2]:5.2f} | 2026 Sh{b26[2]:5.2f} | 23-24 Sh{b23[2]:5.2f} | FULL Sh{f[2]:.2f} OOS Sh{o[2]:.2f} DD{o[1]:.1f}%")
print("\nWANT: a gate that lifts 2022 & 2026 Sharpe toward 0+ while keeping 23-24 and OOS high.")
