"""
Critique fix #5: 'diversification is fake — coins all dump with BTC.'
Test a BTC MASTER regime filter: only go long ANY coin when BTC > its own 200-MA (4h).
Compare basket WITH vs WITHOUT it. Also test a max-concurrent-positions cap (#exposure).
Full cycle 2021-2026 incl 2022 bear, daily metrics, OOS split.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest

DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})

def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)])
    return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}

# BTC master regime on 4h
btc=M["BTCUSDT"].close
btc_regime = btc > btc.rolling(200).mean()

base=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200)

def basket_daily(cfg):
    rs=[]
    for s in coins:
        eq,_=backtest(M[s],cfg)
        rs.append(eq.resample("1D").last().ffill().pct_change().rename(s))
    df=pd.concat(rs,axis=1)
    return df.fillna(0.0).mean(axis=1)

def met(pr):
    pr=pr.dropna(); eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    cagr=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY) if pr.std()>0 else 0
    return cagr*100,dd*100,sh

without=basket_daily(base)
withf  =basket_daily({**base,"btc_regime":btc_regime})

y22a=pd.Timestamp("2022-01-01",tz="UTC"); y22b=pd.Timestamp("2023-01-01",tz="UTC")
def bear(pr): return pr[(pr.index>=y22a)&(pr.index<y22b)]
def row(t,pr):
    f=met(pr); b=met(bear(pr)); n=len(pr); o=met(pr.iloc[int(n*0.6):])
    print(f"  {t:26s} FULL C{f[0]:6.1f}% DD{f[1]:6.1f}% Sh{f[2]:5.2f} | 2022 C{b[0]:6.1f}% Sh{b[2]:5.2f} | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")

print(f"{len(coins)} coins, full cycle 2021-2026\n")
row("baseline (per-coin MA)", without)
row("+ BTC master regime", withf)
