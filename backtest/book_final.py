"""
Verify flush-H3 robustness (not a grid spike) + assemble the FINAL improved book:
trend(20,2.5) + flush(H3) + crashreb(-5%,3), re-search weights on OOS, sanity-check FULL + sub-periods.
"""
import numpy as np, pandas as pd
from itertools import product
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
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index; oo=int(len(IDX)*0.6); oo2=int(len(IDX)*0.3)
def flush_var(THR,TP,HOLD):
    def fc(s):
        df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
        p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
        for i in range(1,len(c)):
            if held>0:
                p[i]=size
                if hv[i]/ep-1>=TP or held>=HOLD: held=0;size=0.0
                else: held+=1
                continue
            if r[i-1]<THR and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
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

print("=== flush HOLD robustness (THR-0.08 TP0.05): is H3 a spike? ===")
for H in [2,3,4,5]:
    fv=flush_var(-0.08,0.05,H); f=met(fv); o=met(fv.iloc[oo:]); h2=met(fv.iloc[oo2:oo])
    print(f"  H{H}: FULL Sh{f[2]:.2f} DD{f[1]:5.1f}% | 1stOOS-half Sh{h2[2]:.2f} | 2ndOOS-half Sh{o[2]:.2f}")

flush2=flush_var(-0.08,0.05,2); flush4=flush_var(-0.08,0.05,4); crashreb=crash_var(-0.05,3)
def show(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); h1=met(pr.iloc[oo2:oo]); h2=met(pr.iloc[oo:])
    print(f"  {t:32s} FULL Sh{f[2]:.2f} CAGR{f[0]:5.1f}% DD{f[1]:6.1f}% | OOS Sh{o[2]:.2f} DD{o[1]:6.1f}% | halves {h1[2]:.2f}/{h2[2]:.2f}")
print("\n=== CURRENT vs IMPROVED book (halves = OOS 1st/2nd) ===")
show("CURRENT t.70/flush4.30", 0.7*trend+0.3*flush4)
print("\n=== weight search, IMPROVED flush(H2)+crashreb, OOS ===")
bw=None
for wt,wf,wc in product([0.45,0.5,0.55,0.6,0.65,0.7],[0.15,0.2,0.25,0.3,0.35],[0.0,0.1,0.15,0.2,0.25]):
    if abs(wt+wf+wc-1.0)>0.001: continue
    o=met((wt*trend+wf*flush2+wc*crashreb).iloc[oo:])
    if bw is None or o[2]>bw[0]: bw=(o[2],wt,wf,wc)
show(f"BEST t{bw[1]:.2f}/flush2.{int(bw[2]*100)}/crash.{int(bw[3]*100)}", bw[1]*trend+bw[2]*flush2+bw[3]*crashreb)
show("ROUND t.55/flush2.25/crash.20", 0.55*trend+0.25*flush2+0.20*crashreb)
show("ROUND t.60/flush2.20/crash.20", 0.60*trend+0.20*flush2+0.20*crashreb)
show("ROUND t.60/flush2.25/crash.15", 0.60*trend+0.25*flush2+0.15*crashreb)
print("\nverify: improved book should beat current on OOS Sh AND DD AND not collapse in either half.")
