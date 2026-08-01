"""Factor zoo: >=100 formulaic candidates with family + provenance metadata.
Convention: HIGHER factor value = MORE attractive to be LONG. All inputs lagged-safe:
only data up to and including day t is used for the value at t (causality tested)."""
from dataclasses import dataclass
from typing import Callable
import numpy as np
import pandas as pd
from . import ops
from .panel import Panel


@dataclass
class Factor:
    name: str
    family: str
    provenance: str
    fn: Callable[[Panel], pd.DataFrame]


def _F(zoo, name, family, prov, fn):
    zoo.append(Factor(name, family, prov, lambda p, _fn=fn: _fn(p).reindex(p.close.index)))


def _anchor(p):
    return "BTCUSDT" if "BTCUSDT" in p.close.columns else p.close.columns[0]


def build_zoo():
    z = []
    Q = "Qlib Alpha158"
    J = "Jansen ML4T"
    FM = "Financial-Models notebooks (concept-mined)"
    TT = "TikTok lead (validated as candidate)"
    IN = "in-repo alphas.py"
    FAM = "family lesson"

    # momentum / reversal / ts-rank
    for h in (5, 10, 21, 28, 42, 63, 126, 252):
        _F(z, f"mom_{h}", "momentum", Q, lambda p, h=h: p.close.pct_change(h))
        _F(z, f"mom_vadj_{h}", "momentum", J,
           lambda p, h=h: p.close.pct_change(h) / ops.ts_std(p.ret, h).replace(0, np.nan))
    for h in (1, 2, 3, 5, 7):
        _F(z, f"rev_{h}", "reversal", Q, lambda p, h=h: -p.close.pct_change(h))
    for w in (10, 21, 63, 126):
        _F(z, f"tsrank_close_{w}", "tsrank", Q, lambda p, w=w: ops.ts_rank(p.close, w))

    # volatility family
    for w in (10, 21, 63):
        _F(z, f"lowvol_{w}", "volatility", J, lambda p, w=w: -ops.ts_std(p.ret, w))
    for a, b in ((10, 63), (21, 63), (10, 126)):
        _F(z, f"volratio_{a}_{b}", "volatility", FM,
           lambda p, a=a, b=b: -(ops.ts_std(p.ret, a) / ops.ts_std(p.ret, b).replace(0, np.nan)))
    for w in (21, 63):
        _F(z, f"volofvol_{w}", "volatility", FM, lambda p, w=w: -ops.ts_std(ops.ts_std(p.ret, 5), w))
        _F(z, f"garchgap_{w}", "volatility", FM,
           lambda p, w=w: -(ops.ewma(p.ret.abs(), 33) / ops.ts_std(p.ret, w).replace(0, np.nan)))
        _F(z, f"skew_{w}", "volatility", J, lambda p, w=w: -ops.rolling_skew(p.ret, w))
    _F(z, "kurt_63", "volatility", J, lambda p: -ops.rolling_kurt(p.ret, 63))

    # k-bar / candle shape
    rng_ = lambda p: (p.high - p.low).replace(0, np.nan)
    for w in (1, 5, 21):
        _F(z, f"kbar_body_{w}", "kbar", Q,
           lambda p, w=w: ops.ts_mean((p.close - p.open) / rng_(p), w))
        _F(z, f"kbar_upshadow_{w}", "kbar", Q,
           lambda p, w=w: -ops.ts_mean((p.high - np.maximum(p.open, p.close)) / rng_(p), w))
        _F(z, f"kbar_downshadow_{w}", "kbar", Q,
           lambda p, w=w: ops.ts_mean((np.minimum(p.open, p.close) - p.low) / rng_(p), w))
        _F(z, f"kbar_closepos_{w}", "kbar", Q,
           lambda p, w=w: ops.ts_mean((p.close - p.low) / rng_(p), w))
    _F(z, "doji_avoid_21", "kbar", FAM,
       lambda p: ops.ts_mean((p.close - p.open).abs() / rng_(p), 21))

    # volume / liquidity
    for w in (10, 21, 63, 126):
        _F(z, f"volz_{w}", "volume", Q,
           lambda p, w=w: (p.volume - ops.ts_mean(p.volume, w)) / ops.ts_std(p.volume, w).replace(0, np.nan))
    for w in (10, 21, 63):
        _F(z, f"pvcorr_{w}", "volume", Q, lambda p, w=w: ops.ts_corr(p.close, p.volume, w))
    _F(z, "amihud_21", "volume", J,
       lambda p: -ops.ts_mean(p.ret.abs() / (p.close * p.volume).replace(0, np.nan), 21))
    _F(z, "volchg_5", "volume", Q, lambda p: p.volume.pct_change(5))

    # capitulation / panic (Williams VIX Fix + variants)
    for w in (22, 66):
        _F(z, f"vixfix_{w}", "capitulation", TT,
           lambda p, w=w: (p.close.rolling(w).max() - p.low) / p.close.rolling(w).max())
        _F(z, f"vixfix_z_{w}", "capitulation", TT,
           lambda p, w=w: ops.cs_z((p.close.rolling(w).max() - p.low) / p.close.rolling(w).max()))

    # drawdown from rolling high
    for w in (21, 63, 126, 252):
        _F(z, f"ddown_{w}", "drawdown", TT, lambda p, w=w: -(p.close / p.close.rolling(w).max() - 1))

    # carry / funding
    def _fund(p):
        return p.funding.reindex(columns=p.close.columns)
    for w in (3, 7, 30):
        _F(z, f"carry_{w}", "carry", IN, lambda p, w=w: ops.ts_mean(_fund(p), w).fillna(0.0))
    _F(z, "carry_trend_14", "carry", IN,
       lambda p: ops.delta(ops.ts_mean(_fund(p), 7), 14).fillna(0.0))
    _F(z, "carry_csrank_7", "carry", IN,
       lambda p: ops.cs_rank(ops.ts_mean(_fund(p), 7)).fillna(0.5))

    # seasonality (per-coin rolling weekday mean return)
    for w in (90, 180):
        def dow_mean(p, w=w):
            r = p.close.pct_change()
            out = pd.DataFrame(np.nan, index=r.index, columns=r.columns)
            for d in range(7):
                m = r.index.dayofweek == d
                out.loc[m] = r.loc[m].rolling(w // 7, min_periods=4).mean().values
            return out
        _F(z, f"dowmean_{w}", "seasonality", "seasonality_scan.py idea", dow_mean)

    # pairs vs anchor (BTC when present)
    for w in (63, 126):
        def spread(p, w=w):
            la = np.log(p.close)
            lb = la[_anchor(p)]
            beta = la.rolling(w).cov(lb).div(lb.rolling(w).var().replace(0, np.nan), axis=0)
            s = la.sub(beta.mul(lb, axis=0))
            return -ops.cs_z((s - ops.ts_mean(s, w)) / ops.ts_std(s, w).replace(0, np.nan))
        _F(z, f"spread_ols_{w}", "pairs", FM, spread)

    def kalman_spread(p, q=1e-4):
        la = np.log(p.close)
        lb = la[_anchor(p)].values
        out = {}
        for c in la.columns:
            y = la[c].values
            beta, P = 1.0, 1.0
            res = np.full(len(y), np.nan)
            for i in range(len(y)):
                if np.isnan(y[i]) or np.isnan(lb[i]):
                    continue
                P += q
                e = y[i] - beta * lb[i]
                K = P * lb[i] / (lb[i] * P * lb[i] + 1e-2)
                beta += K * e
                P *= (1 - K * lb[i])
                res[i] = e
            out[c] = res
        s = pd.DataFrame(out, index=la.index)
        return -ops.cs_z((s - ops.ts_mean(s, 63)) / ops.ts_std(s, 63).replace(0, np.nan))
    _F(z, "spread_kalman", "pairs", FM, kalman_spread)

    # oscillators
    for n in (2, 7, 14):
        _F(z, f"rsi_dip_{n}", "oscillator", IN, lambda p, n=n: -ops.rsi(p.close, n))
    for w in (14, 28):
        _F(z, f"stoch_{w}", "oscillator", J,
           lambda p, w=w: -(p.close - p.low.rolling(w).min()) /
                          (p.high.rolling(w).max() - p.low.rolling(w).min()).replace(0, np.nan))
    _F(z, "macd_gap", "oscillator", J,
       lambda p: (ops.ewma(p.close, 12) - ops.ewma(p.close, 26)) / p.close)

    # trend / value-vs-trend
    for w in (10, 21, 63, 126, 200):
        _F(z, f"px_over_ma_{w}", "trendvalue", IN, lambda p, w=w: p.close / ops.ts_mean(p.close, w) - 1)
    _F(z, "tsmom_sign_28", "trendvalue", IN, lambda p: np.sign(p.close.pct_change(28)))

    # lottery / extremes
    for w in (21, 63):
        _F(z, f"maxret_{w}", "lottery", J, lambda p, w=w: -p.ret.rolling(w).max())

    def streak(p):
        s = np.sign(p.close.pct_change().fillna(0.0))
        out = {}
        for c in s.columns:
            x = s[c]
            grp = (x != x.shift()).cumsum()
            out[c] = x * (x.groupby(grp).cumcount() + 1)
        return -pd.DataFrame(out)
    _F(z, "streak", "lottery", J, streak)

    # beta / correlation to anchor
    for w in (21, 63):
        def beta_f(p, w=w):
            a = _anchor(p)
            return -p.ret.rolling(w).cov(p.ret[a]).div(p.ret[a].rolling(w).var().replace(0, np.nan), axis=0)
        _F(z, f"lowbeta_{w}", "beta", J, beta_f)
        _F(z, f"anchorcorr_{w}", "beta", J, lambda p, w=w: -p.ret.rolling(w).corr(p.ret[_anchor(p)]))

    # cross-asset regime interactions (Zen 2026-07-21 ask; mechanism-backed:
    # risk-off hedge flows via gold, dollar-liquidity via EURUSDT, relative carry
    # vs the anchor). Reference series may be absent (synthetic panels) — factors
    # then compute all-NaN and the factory judges them on coverage, not a crash.
    CA = "Zen 2026-07-21 cross-asset ask"

    def _refret(p, sym):
        return p.ret[sym] if sym in p.close.columns else None

    def _regime(p, sym, w):
        """corr(coin, ref, w) signed by the ref's own 28d trend: when the hedge
        asset trends up (risk-off / dollar-weak), favor coins that move WITH it."""
        r = _refret(p, sym)
        if r is None:
            return pd.DataFrame(np.nan, index=p.close.index, columns=p.close.columns)
        sign = np.sign(p.close[sym].pct_change(28))
        return p.ret.rolling(w).corr(r).mul(sign, axis=0)

    for w in (21, 63):
        _F(z, f"goldregime_{w}", "crossasset", CA, lambda p, w=w: _regime(p, "PAXGUSDT", w))
        _F(z, f"usdregime_{w}", "crossasset", CA, lambda p, w=w: _regime(p, "EURUSDT", w))

    def _relcarry(p, w):
        f = _fund(p)
        a = _anchor(p)
        if a not in f.columns:
            return pd.DataFrame(np.nan, index=p.close.index, columns=p.close.columns)
        return ops.ts_mean(f, w).sub(ops.ts_mean(f[a], w), axis=0).fillna(0.0)

    for w in (7, 30):
        _F(z, f"relcarry_{w}", "crossasset", CA, lambda p, w=w: _relcarry(p, w))

    # baselines (sanity anchors mirroring alphas.py signals)
    _F(z, "base_xsmom_28", "baseline", IN, lambda p: p.close.pct_change(28))
    _F(z, "base_carry_3", "baseline", IN, lambda p: ops.ts_mean(_fund(p), 3).fillna(0.0))
    _F(z, "base_rsi2", "baseline", IN, lambda p: -ops.rsi(p.close, 2))
    _F(z, "base_trend_200", "baseline", IN, lambda p: p.close / ops.ts_mean(p.close, 200) - 1)
    _F(z, "base_tsmom_28", "baseline", IN, lambda p: np.sign(p.close.pct_change(28)))
    return z
