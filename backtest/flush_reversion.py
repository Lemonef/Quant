"""
NEW MECHANISM (not price-trend): liquidation-flush mean-reversion.
Hypothesis: a violent 4h dump (forced-liquidation cascade) over-shoots -> snaps back.
Step 1: expectancy scan — avg forward return after a flush vs baseline (is there an edge?).
Step 2: if promising, basket backtest + correlation to the trend bot (diversifier?).
Data: existing 25-coin 4h, merged 2021-2026. Long-only, buy the flush, hold H bars.
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

# ---- Step 1: expectancy scan ----
print("=== expectancy: avg forward return after a 4h flush (all coins pooled) ===")
print(f"{'thr':>5s} {'hold':>5s} {'n':>6s} {'avg_fwd%':>9s} {'hit%':>6s} {'baseline%':>10s}")
best=None
for thr in [-0.06,-0.08,-0.10,-0.12,-0.15]:
    for H in [1,3,6,12]:
        fwd=[];
        for s in coins:
            c=M[s].close; r=c.pct_change()
            f=c.shift(-H)/c-1
            mask=r<thr
            vals=f[mask].dropna()
            fwd.append(vals)
        allf=pd.concat(fwd)
        base=pd.concat([M[s].close.pct_change(H).dropna() for s in coins]).mean()  # unconditional H-bar
        if len(allf)>30:
            print(f"{thr*100:5.0f} {H:5d} {len(allf):6d} {allf.mean()*100:9.2f} {(allf>0).mean()*100:6.1f} {base*100:10.2f}")
            edge=allf.mean()-base
            if best is None or edge>best[0]: best=(edge,thr,H)

print(f"\nbest edge: thr={best[1]*100:.0f}% hold={best[2]} bars (edge over baseline {best[0]*100:.2f}%)")

# ---- Step 2: basket backtest of the best flush-reversion config ----
thr,H=best[1],best[2]
def coin_ret(s):
    c=M[s].close; r=c.pct_change()
    entry=(r<thr).shift(1).fillna(False)          # enter bar after a flush
    # hold H bars: position =1 for H bars after each entry (simple, overlapping allowed-> cap at 1)
    pos=pd.Series(0.0,index=c.index)
    e=entry.values; p=np.zeros(len(c))
    hold=0
    for i in range(len(c)):
        if e[i]: hold=H
        if hold>0: p[i]=1.0; hold-=1
    pos=pd.Series(p,index=c.index)
    cost=pos.diff().abs().fillna(0)*0.0008
    return (pos.shift(1).fillna(0)*r - cost).rename(s)
flush=pd.concat([coin_ret(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
flush_d=(1+flush).resample("1D").prod()-1  # to daily

# trend bot daily for correlation
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)

def met(pr):
    pr=pr.dropna();
    if pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    c=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1; dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    return c*100,dd*100,sh
n=len(flush_d); oos=int(n*0.6)
f=met(flush_d); o=met(flush_d.iloc[oos:])
print(f"\n=== flush-reversion basket (thr {thr*100:.0f}%, hold {H} bars) ===")
print(f"  FULL CAGR {f[0]:.1f}% DD {f[1]:.1f}% Sharpe {f[2]:.2f} | OOS CAGR {o[0]:.1f}% DD {o[1]:.1f}% Sharpe {o[2]:.2f}")
corr=flush_d.reindex(trend.index).fillna(0).corr(trend)
print(f"  correlation to trend bot: {corr:.2f}   (low/neg = good diversifier)")

# ---- Step 3: does adding flush as a sleeve help the combined book? ----
fd=flush_d.reindex(trend.index).fillna(0.0)
print("\n=== trend + flush ensemble (fixed weights) ===")
def met2(pr):
    pr=pr.dropna(); n=len(pr); o=pr.iloc[int(n*0.6):]
    def m(x):
        eq=(1+x).cumprod(); yrs=len(eq)/DPY
        return (eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100, (eq/eq.cummax()-1).min()*100, x.mean()/x.std()*np.sqrt(DPY) if x.std()>0 else 0
    return m(pr), m(o)
for wf in [0.0,0.15,0.30,0.50]:
    blend=(1-wf)*trend + wf*fd
    full,oo=met2(blend)
    print(f"  trend{int((1-wf)*100)}/flush{int(wf*100)}: FULL Sh{full[2]:.2f} DD{full[1]:.1f}% | OOS C{oo[0]:.1f}% DD{oo[1]:.1f}% Sh{oo[2]:.2f}")
