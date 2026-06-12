"""
CAPACITY + SLIPPAGE-SENSITIVITY analysis for the deployed book.
Answers: (1) how much $ can each strategy absorb before its own orders move the
market, (2) how fast does the edge decay as cost rises. Retail-honest.

Method:
- ADV(USD) per coin = median daily dollar volume (volume*close summed per day) over the data.
- Equal-weight basket: a coin in-position holds ~1/N of AUM. A single entry order = that slug.
- Capacity ceiling = the AUM at which the per-coin entry slug hits a participation cap
  (1% conservative / 5% aggressive) of the LEAST-liquid coin's ADV. Binding coin caps the book.
  (Trend is slow → a slug can be TWAP'd over hours, so this is a floor; note that.)
- Turnover per strategy = annualized sum of |dposition| (how many times capital churns/yr).
- Slippage sweep: re-run the trend basket net at COST = 5/10/20/40/80 bps, report CAGR/Sharpe.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest
DATA = Path(__file__).parent / "data"; DPY = 365

def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins = sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df = pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)])
    return df[~df.index.duplicated(keep="first")].sort_index()
M = {s: merged(s) for s in coins}
N = len(coins)
btc = M["BTCUSDT"].close; reg = btc > btc.rolling(200).mean()

# ---------- 1. ADV (USD) per coin ----------
def adv_usd(s):
    df = M[s]; dollar = (df.volume * df.close)              # per-4h-bar $ volume
    daily = dollar.resample("1D").sum()
    daily = daily[daily > 0].tail(365)                      # last ~yr, drop empty days
    return float(daily.median()) if len(daily) else 0.0
ADV = {s: adv_usd(s) for s in coins}
advs = pd.Series(ADV).sort_values()

# ---------- 2. Turnover per strategy (annualized) ----------
def trend_pos(s):
    cfg = dict(strat="donchian", entry=55, exit=20, risk=5, stop_mult=2.5,
               adx_filter=True, ma_filter=200, btc_regime=reg)
    eq = backtest(M[s], cfg)[0]                             # equity curve; derive exposure proxy
    return eq
# position proxy: use the daily returns' nonzero pattern is hard; instead measure turnover from
# the canonical donchian position the engine exposes if available, else approximate via the
# equity-implied exposure. We approximate per-coin turnover by the breakout hold length (55/20).
# Annualized basket turnover for a Donchian 55/20 4h ~ a few round-trips/yr/coin (documented low).
# We report it empirically from position diffs if the engine returns positions.

bars_per_year = DPY * 6                                     # 4h bars
def turnover_of(posfunc, syms):
    tot = []
    for s in syms:
        p = posfunc(s)
        if p is None: continue
        d = p.diff().abs().fillna(0.0)
        tot.append(d.sum() / (len(p)/bars_per_year))        # annualized |dpos| sum
    return float(np.mean(tot)) if tot else float("nan")

# self-contained Donchian 55/20 long-only position (0/1), gated by BTC-regime + price>MA200.
# (the live book risk-sizes; 0/1 is the conservative turnover/capacity proxy — same trade timing.)
def trend_position_series(s):
    c = M[s].close
    hi = c.rolling(55).max().shift(1); lo = c.rolling(20).min().shift(1)
    ma = c.rolling(200).mean()
    rg = reg.reindex(c.index).fillna(False)
    pos = np.zeros(len(c)); held = 0
    cv = c.values; hiv = hi.values; lov = lo.values; mav = ma.values; rgv = rg.values
    for i in range(1, len(c)):
        if held:
            pos[i] = 1.0
            if cv[i] < lov[i] or not rgv[i]: held = 0; pos[i] = 0.0
        else:
            if rgv[i] and cv[i] > (hiv[i] or 1e18) and cv[i] > (mav[i] or 1e18): held = 1; pos[i] = 1.0
    return pd.Series(pos, index=c.index)

trend_turn = turnover_of(trend_position_series, coins)

# flush / crashreb position series (from book_final logic)
def flush_pos(s, THR=-0.08, TP=0.05, HOLD=2):
    df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
    p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
    for i in range(1,len(c)):
        if held>0:
            p[i]=size
            if hv[i]/ep-1>=TP or held>=HOLD: held=0; size=0.0
            else: held+=1
            continue
        if r[i-1]<THR and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10); p[i]=size; ep=cv[i]; held=1
    return pd.Series(p, index=c.index)
def crash_pos(s, THR=-0.05, H2=3):
    c=M[s].close; cv=c.values; hv=M[s].high.values; brv=btc.pct_change().reindex(c.index).values
    p=np.zeros(len(c)); ep=0.0; held=0
    for i in range(1,len(c)):
        if held>0:
            p[i]=1.0
            if hv[i]/ep-1>=0.05 or held>=H2: held=0
            else: held+=1
            continue
        if brv[i-1]<THR: p[i]=1.0; ep=cv[i]; held=1
    return pd.Series(p, index=c.index)
flush_turn = turnover_of(flush_pos, coins)
crash_turn = turnover_of(crash_pos, [c for c in coins if c!="BTCUSDT"])

# ---------- 3. Capacity ceilings ----------
# equal-weight: a coin in-position holds ~1/N of AUM; entry slug = (1/N)*AUM.
# slug <= part*ADV_coin  ->  AUM <= part*ADV_coin*N.  Binding coin = min ADV.
def cap(part):  # AUM ceiling using the LEAST liquid coin
    return part * advs.iloc[0] * N
def cap_median(part):  # using median-ADV coin (looser, if you drop the thinnest names)
    return part * advs.median() * N

# ---------- 4. Slippage sensitivity (trend basket) ----------
def trend_ret_at_cost(costbps):
    cost = costbps/10000.0
    def one(s):
        pos = trend_position_series(s)
        c = M[s].close
        return (pos.shift(1).fillna(0)*c.pct_change() - pos.diff().abs().fillna(0)*cost).rename(s)
    cols = [one(s) for s in coins]; cols=[x for x in cols if x is not None]
    basket = pd.concat(cols, axis=1).fillna(0.0).mean(axis=1).resample("1D").sum()
    return basket
def metrics(pr):
    pr=pr.dropna()
    if len(pr)<30 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(pr)/DPY
    cagr=(eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100
    dd=(eq/eq.cummax()-1).min()*100
    sh=pr.mean()/pr.std()*np.sqrt(DPY)
    return (round(cagr,1),round(dd,1),round(sh,2))

# ---------- REPORT ----------
print(f"UNIVERSE: {N} coins, data {M['BTCUSDT'].index.min().date()}..{M['BTCUSDT'].index.max().date()}\n")
print("ADV (median daily $ volume), least->most liquid:")
for s,v in advs.items(): print(f"  {s:12s} ${v/1e6:10.1f}M")
print(f"\n  thinnest coin: {advs.index[0]} ${advs.iloc[0]/1e6:.1f}M  |  median ${advs.median()/1e6:.1f}M")

print("\nANNUALIZED TURNOVER (x capital churned/yr, per-coin avg):")
print(f"  trend (Donchian 55/20)   {trend_turn:.1f}x")
print(f"  flush                    {flush_turn:.1f}x")
print(f"  crashreb                 {crash_turn:.1f}x")

print("\nCAPACITY CEILING (equal-weight, single entry slug vs coin ADV):")
print("  binding = THINNEST coin in the universe")
for part,lbl in [(0.01,"1% ADV (conservative, no-TWAP)"),(0.05,"5% ADV (TWAP'd, aggressive)")]:
    print(f"  @ {lbl:32s}: ~${cap(part)/1e6:8.2f}M   (drop-thin-names/median-coil: ~${cap_median(part)/1e6:.1f}M)")

print("\nSLIPPAGE SENSITIVITY — trend basket net at rising cost:")
print("  cost(bps/side)  CAGR%   maxDD%   Sharpe")
for cb in [5,10,20,40,80]:
    c,d,s = metrics(trend_ret_at_cost(cb))
    print(f"     {cb:3d}          {c:6.1f}  {d:7.1f}   {s:5.2f}")
