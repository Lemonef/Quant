"""
Lightweight vectorised-ish backtest engine (pure pandas/numpy).
Long-only. Bar-by-bar execution on close (process_orders_on_close style).

Strategies:
  donchian   - N-high breakout, exit prior M-low or ATR stop (+ optional chandelier), opt ADX filter
  qb_hybrid  - ADX regime: trending->Donchian breakout, ranging->Bollinger+RSI reversion
  meanrev    - Bollinger + RSI oversold reversion only
  qb_v1      - ADX regime: trending->Supertrend+RSI momentum, ranging->Bollinger reversion

Sizing: risk_pct of equity / (atr*stop_mult) units, notional capped at leverage*equity.
Optional pyramiding (Turtle add-units on new highs).

NOTE: stops/exits evaluated on close (not intrabar) -> drawdowns slightly understated vs a
live intrabar stop. Consistent across all configs, so technique comparisons are valid.
"""
import numpy as np
import pandas as pd
from pathlib import Path

COMM = 0.001      # 0.1% per side
SLIP = 0.0005     # 0.05% slippage per side
BARS_PER_YEAR = {"1h": 24*365, "2h": 12*365, "4h": 6*365, "6h": 4*365,
                 "12h": 2*365, "1d": 365}


# ---------- indicators ----------
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

def atr(df, n=14):
    h, l, c = df.high, df.low, df.close
    pc = c.shift()
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return rma(tr, n)

def rsi(s, n=14):
    d = s.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma((-d).clip(lower=0), n)
    rs = up / dn.replace(0, np.nan)
    return (100 - 100/(1+rs)).fillna(50)

def adx(df, n=14):
    h, l, c = df.high, df.low, df.close
    up = h.diff(); dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr_ = rma(tr, n)
    pdi = 100 * rma(pd.Series(plus, index=df.index), n) / atr_.replace(0, np.nan)
    mdi = 100 * rma(pd.Series(minus, index=df.index), n) / atr_.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return rma(dx.fillna(0), n)

def bollinger(s, n=20, mult=2.0):
    basis = s.rolling(n).mean()
    dev = mult * s.rolling(n).std(ddof=0)
    return basis, basis+dev, basis-dev

def supertrend(df, n=10, mult=3.0):
    hl2 = (df.high+df.low)/2
    a = atr(df, n)
    upper = hl2 + mult*a
    lower = hl2 - mult*a
    st = pd.Series(index=df.index, dtype=float)
    dir_ = pd.Series(index=df.index, dtype=int)
    fu = upper.copy(); fl = lower.copy()
    for i in range(len(df)):
        if i == 0:
            st.iloc[i] = upper.iloc[i]; dir_.iloc[i] = -1; continue
        fu.iloc[i] = min(upper.iloc[i], fu.iloc[i-1]) if df.close.iloc[i-1] <= fu.iloc[i-1] else upper.iloc[i]
        fl.iloc[i] = max(lower.iloc[i], fl.iloc[i-1]) if df.close.iloc[i-1] >= fl.iloc[i-1] else lower.iloc[i]
        if df.close.iloc[i] > fu.iloc[i-1]:
            dir_.iloc[i] = 1
        elif df.close.iloc[i] < fl.iloc[i-1]:
            dir_.iloc[i] = -1
        else:
            dir_.iloc[i] = dir_.iloc[i-1]
        st.iloc[i] = fl.iloc[i] if dir_.iloc[i] == 1 else fu.iloc[i]
    return dir_  # +1 bullish, -1 bearish


# ---------- data ----------
def load(sym, iv, data_dir):
    p = Path(data_dir) / f"{sym}_{iv}.csv"
    df = pd.read_csv(p)
    df["dt"] = pd.to_datetime(df.open_time, unit="ms", utc=True)
    df = df.set_index("dt")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


# ---------- signals ----------
def build_signals(df, cfg):
    out = pd.DataFrame(index=df.index)
    a = atr(df, cfg.get("atr_len", 14))
    out["atr"] = a
    strat = cfg["strat"]
    don_hi = df.high.rolling(cfg.get("entry", 20)).max()
    don_lo = df.low.rolling(cfg.get("exit", 10)).min()
    out["don_hi_prev"] = don_hi.shift()
    out["don_lo_prev"] = don_lo.shift()
    ad = adx(df, cfg.get("adx_len", 14))
    out["trending"] = ad > cfg.get("adx_trend", 25)
    out["ranging"] = ad < cfg.get("adx_range", 20)
    basis, up, lo = bollinger(df.close, cfg.get("bb_len", 20), cfg.get("bb_mult", 2.0))
    out["bb_basis"] = basis; out["bb_lo"] = lo; out["bb_up"] = up
    r = rsi(df.close, cfg.get("rsi_len", 14))
    out["rsi"] = r
    if strat == "qb_v1":
        out["st_bull"] = supertrend(df, 10, 3.0) == 1
    maf = cfg.get("ma_filter", 0)
    mok = (df.close > df.close.rolling(maf).mean()) if maf else pd.Series(True, index=df.index)
    reg = cfg.get("btc_regime")          # external master regime (e.g. BTC>200MA), gates all entries
    if reg is not None:
        mok = mok & reg.reindex(df.index).ffill().fillna(False)
    out["mkt_ok"] = mok
    out["close"] = df.close
    out["high"] = df.high
    out["low"] = df.low
    return out


def backtest(df, cfg):
    s = build_signals(df, cfg)
    s = s.dropna()
    strat = cfg["strat"]
    risk = cfg.get("risk", 5.0)/100
    stop_mult = cfg.get("stop_mult", 2.5)
    lev = cfg.get("leverage", 1.0)
    use_trail = cfg.get("trail", False)
    trail_mult = cfg.get("trail_mult", 3.0)
    pyr_max = cfg.get("pyramid", 0)
    rsi_os = cfg.get("rsi_os", 30); rsi_exit = cfg.get("rsi_exit", 55)
    rsi_lo, rsi_hi = cfg.get("rsi_lo", 40), cfg.get("rsi_hi", 70)

    equity = 10000.0
    eq_cash = equity
    entry_equity = equity
    units = 0.0; entry = 0.0; stop = 0.0; peak = 0.0; leg = None; adds = 0
    eq_curve = []; trades = []
    idx = s.index
    c = s.close.values; hi = s.high.values; lo = s.low.values
    av = s.atr.values
    dhp = s.don_hi_prev.values; dlp = s.don_lo_prev.values
    tr = s.trending.values; rg = s.ranging.values
    bb_lo = s.bb_lo.values; bb_basis = s.bb_basis.values
    rv = s.rsi.values
    stbull = s.st_bull.values if "st_bull" in s else np.zeros(len(s), bool)
    mok = s.mkt_ok.values.astype(bool) if "mkt_ok" in s else np.ones(len(s), bool)

    def trend_entry(i): return c[i] > dhp[i]
    def trend_exit(i):  return c[i] < dlp[i]

    for i in range(len(s)):
        price = c[i]
        if units > 0:
            peak = max(peak, hi[i])
            chand = peak - av[i]*trail_mult
            exit_now = False
            if leg == "trend":
                if trend_exit(i): exit_now = True
                if use_trail and price < chand: exit_now = True
            else:
                if price >= bb_basis[i] or rv[i] > rsi_exit: exit_now = True
            if price < stop: exit_now = True
            # pyramiding: add unit on new breakout (trend leg only)
            if not exit_now and leg == "trend" and pyr_max > 0 and adds < pyr_max and trend_entry(i) and av[i] > 0:
                cur_eq = eq_cash + units*price
                add_units = (cur_eq*risk)/(av[i]*stop_mult)
                notional_cap = lev*cur_eq/price
                add_units = min(add_units, max(0.0, notional_cap - units))
                max_by_cash = eq_cash/(price*(1+COMM+SLIP))   # can't spend cash you don't have
                add_units = min(add_units, max(0.0, max_by_cash))
                if add_units > 0:
                    eq_cash -= add_units*price*(1+COMM+SLIP)   # pay notional + fees (was the bug)
                    new_units = units + add_units
                    entry = (entry*units + price*add_units)/new_units
                    units = new_units; adds += 1
                    stop = entry - av[i]*stop_mult
            if exit_now:
                proceeds = units*price*(1-COMM-SLIP)
                equity = eq_cash + proceeds
                trades.append(equity - entry_equity)
                units = 0; leg = None; adds = 0; peak = 0
        # entries (flat only)
        if units == 0 and mok[i]:
            do_trend = False; do_range = False
            if strat == "donchian":
                do_trend = trend_entry(i) and (tr[i] if cfg.get("adx_filter", True) else True)
            elif strat == "qb_hybrid":
                if tr[i] and trend_entry(i): do_trend = True
                elif rg[i] and c[i] <= bb_lo[i] and rv[i] < rsi_os: do_range = True
            elif strat == "meanrev":
                if c[i] <= bb_lo[i] and rv[i] < rsi_os: do_range = True
            elif strat == "qb_v1":
                if tr[i] and stbull[i] and rv[i] > 50: do_trend = True
                elif rg[i] and c[i] <= bb_lo[i] and rv[i] < rsi_os: do_range = True
            if do_trend or do_range:
                sz = (equity*risk)/(av[i]*stop_mult) if av[i] > 0 else 0
                sz = min(sz, lev*equity/price)
                if sz > 0:
                    cost = sz*price*(COMM+SLIP)
                    entry_equity = equity
                    eq_cash = equity - sz*price - cost
                    units = sz; entry = price; peak = hi[i]
                    stop = entry - av[i]*stop_mult
                    leg = "trend" if do_trend else "range"; adds = 0
        # mark equity
        cur = (eq_cash + units*price) if units > 0 else equity
        eq_curve.append(cur)

    eq = pd.Series(eq_curve, index=idx)
    return eq, trades


def metrics(eq, trades, iv):
    if len(eq) < 2:
        return dict(CAGR=0, MaxDD=0, Sharpe=0, WR=0, PF=0, n=0, final=eq.iloc[-1] if len(eq) else 0)
    years = len(eq)/BARS_PER_YEAR[iv]
    ret_total = eq.iloc[-1]/eq.iloc[0]
    cagr = ret_total**(1/years)-1 if ret_total > 0 else -1
    roll_max = eq.cummax()
    dd = (eq/roll_max - 1).min()
    rets = eq.pct_change().dropna()
    sharpe = (rets.mean()/rets.std()*np.sqrt(BARS_PER_YEAR[iv])) if rets.std() > 0 else 0
    wins = [t for t in trades if t > 0]; losses = [t for t in trades if t <= 0]
    wr = len(wins)/len(trades) if trades else 0
    pf = (sum(wins)/abs(sum(losses))) if losses and sum(losses) != 0 else (np.inf if wins else 0)
    return dict(CAGR=cagr*100, MaxDD=dd*100, Sharpe=sharpe, WR=wr*100,
                PF=pf, n=len(trades), final=eq.iloc[-1])
