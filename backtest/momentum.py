"""
Research-backed momentum strategies (the pro playbook):
  TSMOM  - time-series momentum: long coins with positive trailing return, vol-targeted
  XSMOM  - cross-sectional momentum: each rebalance long the top-K trailing performers
  combo  - TSMOM applied to cross-sectional winners
Daily bars from merged 2021-2026. Vol-targeting to a chosen annual vol. Walk-forward OOS.
Refs: AUT crypto momentum study (TSMOM Sharpe ~1.5); vol-filtering ~1.2.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load

DATA = Path(__file__).parent / "data"
BASKET = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOGEUSDT"]
DPY = 365

def daily_close(sym):
    df = pd.concat([load(f"{sym}_bear","4h",DATA), load(sym,"4h",DATA)])
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df.close.resample("1D").last().dropna()

px = pd.DataFrame({s: daily_close(s) for s in BASKET}).dropna(how="all")
ret = px.pct_change().fillna(0.0)

def met(pr, tag=""):
    pr = pr.dropna()
    if len(pr) < 30 or pr.std() == 0: return dict(CAGR=0,DD=0,Sharpe=0,Sortino=0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    cagr=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    dn=pr[pr<0].std(); so=pr.mean()/dn*np.sqrt(DPY) if dn>0 else 0
    return dict(CAGR=cagr*100,DD=dd*100,Sharpe=sh,Sortino=so)

def voltarget(pr, target=0.40, win=30):
    rv = pr.rolling(win).std()*np.sqrt(DPY)
    scale = (target/rv).clip(upper=3.0).shift(1).fillna(0.0)
    return pr*scale

def tsmom(lookback=28, vt=0.40):
    sig = (px/px.shift(lookback) - 1)
    pos = (sig > 0).astype(float).shift(1).fillna(0.0)     # long if trailing return positive
    pos = pos.div(pos.sum(axis=1).replace(0,np.nan), axis=0).fillna(0.0)  # equal-weight active
    pr = (pos*ret).sum(axis=1)
    return voltarget(pr, vt)

def xsmom(lookback=28, k=3, vt=0.40):
    sig = (px/px.shift(lookback) - 1)
    rank = sig.rank(axis=1, ascending=False)
    pos = (rank <= k).astype(float).shift(1).fillna(0.0)
    pos = pos.div(pos.sum(axis=1).replace(0,np.nan), axis=0).fillna(0.0)
    pr = (pos*ret).sum(axis=1)
    return voltarget(pr, vt)

def combo(lookback=28, k=5, vt=0.40):
    sig=(px/px.shift(lookback)-1)
    rank=sig.rank(axis=1, ascending=False)
    pos=((rank<=k) & (sig>0)).astype(float).shift(1).fillna(0.0)  # top-K AND positive
    pos=pos.div(pos.sum(axis=1).replace(0,np.nan),axis=0).fillna(0.0)
    pr=(pos*ret).sum(axis=1)
    return voltarget(pr, vt)

def show(name, pr):
    n=len(pr); cut=int(n*0.6)
    f=met(pr); tr=met(pr.iloc[:cut]); te=met(pr.iloc[cut:])
    print(f"{name:16s} FULL C{f['CAGR']:6.1f}% DD{f['DD']:6.1f}% Sh{f['Sharpe']:.2f} | TRAIN Sh{tr['Sharpe']:.2f} | TEST(OOS) C{te['CAGR']:6.1f}% DD{te['DD']:6.1f}% Sh{te['Sharpe']:.2f}")

print(f"daily bars: {len(px)} (~2021-2026)\n")
print("=== momentum families (vol-target 40%) ===")
show("TSMOM lb28", tsmom(28))
show("TSMOM lb14", tsmom(14))
show("TSMOM lb56", tsmom(56))
show("XSMOM lb28 k3", xsmom(28,3))
show("XSMOM lb28 k5", xsmom(28,5))
show("combo lb28 k5", combo(28,5))
show("combo lb14 k5", combo(14,5))

print("\n=== robustness plateau: TSMOM lookback scan (full Sharpe) ===")
for lb in [10,14,20,28,40,56,80]:
    print(f"  lb={lb:3d}: Sharpe {met(tsmom(lb))['Sharpe']:.2f}")

print("\n=== leverage/vol-target sweep on best TSMOM lb28 ===")
for vt in [0.2,0.4,0.6,0.8,1.0]:
    f=met(tsmom(28,vt)); print(f"  vt={vt:.1f}: CAGR {f['CAGR']:7.1f}%  DD {f['DD']:7.1f}%  Sharpe {f['Sharpe']:.2f}")
