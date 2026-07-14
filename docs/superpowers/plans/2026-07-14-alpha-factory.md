# Alpha Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command that computes ~100-160 candidate factors over the crypto panel, evaluates each with purged walk-forward + IC statistics, applies deflated-Sharpe/FDR multiple-testing control, benchmarks survivors against the incumbent 5-alpha book, and writes a ranked SURVIVED/REJECTED scoreboard.

**Architecture:** New pure-pandas package `backtest/alpha_factory/` beside the existing flat scripts; reuses `engine.load` and the `alphas.py` data conventions. No new platform: numpy + pandas + pytest only (stdlib `statistics.NormalDist` for normal CDF/inv-CDF — no scipy). The harness validates itself on synthetic GBM data before touching real data.

**Tech Stack:** Python 3 (repo-local `.venv`), numpy, pandas, pytest, requests (data fetch only).

**Spec:** `docs/superpowers/specs/2026-07-14-alpha-factory-design.md` (approved 2026-07-14).

## Global Constraints

- No magic numbers in module code: every tunable lives in `backtest/alpha_factory/config.py` (single source of truth; the CLI prints the active config into the report header).
- No same-bar fills anywhere: portfolio execution always `shift(1)`.
- Costs everywhere: taker fee 0.0006/side + slippage 0.0005/side (mirrors `engine.SLIP`) on turnover, short-borrow 0.10/yr on the short leg (mirrors `alphas.py` xsmom costs).
- Survival requires ALL of: BH-FDR pass at `FDR_Q=0.10` + positive net L/S Sharpe in EVERY fold + decay rule + deflated Sharpe > 0.5 probability.
- Improvement gate: survivors are additionally reported vs the incumbent book — correlation per sleeve + ensemble OOS Sharpe/maxDD WITH vs WITHOUT (`IMPROVES BOOK: yes/no (ΔSharpe, ΔDD)`).
- Survivorship-bias: universe additions must have been Binance-listed before the evaluation window start (2023-01-01); the report header carries the survivorship caveat verbatim from config.
- Nothing under `live_bot/` or `web/` is touched.
- Working directory for all commands: `~/Quant/backtest`; interpreter: `../.venv/bin/python`.
- Every factor definition carries `family` and `provenance` metadata.
- Commit after every green test cycle. Conventional Commits.

## File Structure

```
.venv/                                  # repo-local env (gitignored)
backtest/alpha_factory/
  __init__.py
  config.py        # ALL tunables (one place)
  ops.py           # rolling/cross-sectional operator library
  panel.py         # Panel dataclass + build_panel(data_dir) + build_synth_panel()
  zoo.py           # Factor dataclass + build_zoo() -> list[Factor] (>=100)
  evaluate.py      # IC/decay, quantile L/S with costs, purged folds
  stats.py         # p-values, BH-FDR, deflated Sharpe, verdict
  bench.py         # incumbent 5-alpha sleeves + ensemble improvement gate
  report.py        # scoreboard dataframe -> markdown + csv
  __main__.py      # CLI: python -m alpha_factory
  tests/
    conftest.py    # sys.path bootstrap + shared fixtures
    test_ops.py
    test_panel.py
    test_zoo.py
    test_evaluate.py
    test_stats.py
    test_bench.py
    test_end_to_end.py
    test_real_data.py   # integration; auto-skips when backtest/data absent
```

`python backtest/alpha_factory.py` from the spec is realized as `python -m alpha_factory` (a module named `alpha_factory.py` cannot coexist with the package directory); the spec intent (one command) is preserved.

---

### Task 1: Environment + package scaffold

**Files:**
- Create: `backtest/alpha_factory/__init__.py`, `backtest/alpha_factory/config.py`, `backtest/alpha_factory/tests/conftest.py`, `backtest/alpha_factory/tests/test_ops.py` (scaffold assert only)
- Modify: `.gitignore` (add `.venv/`)

**Interfaces:**
- Produces: `config.py` constants used by every later task:
  `HORIZONS=(1,5,20)`, `N_FOLDS=4`, `EMBARGO_DAYS=10`, `FDR_Q=0.10`,
  `K_FRAC=0.2`, `TAKER_FEE=0.0006`, `SLIPPAGE=0.0005`, `BORROW_ANNUAL=0.10`,
  `DPY=365`, `DECAY_CHECK_HORIZON=5`, `DECAY_MIN_RATIO=0.25`,
  `DSR_MIN_PROB=0.5`, `MIN_OBS_DAYS=250`, `OOS_SPLIT=0.6`,
  `EVAL_WINDOW_START="2023-01-01"`, `SURVIVORSHIP_CAVEAT` (string)

- [ ] **Step 1: Create venv + install deps**

```bash
cd ~/Quant && python3 -m venv .venv && .venv/bin/pip -q install numpy pandas pytest requests
```
Expected: exit 0. Verify: `.venv/bin/python -c "import pandas, numpy; print('ok')"` → `ok`.

- [ ] **Step 2: Add `.venv/` to `.gitignore`** (append below the `__pycache__/` line):

```
.venv/
```

- [ ] **Step 3: Write scaffold files**

`backtest/alpha_factory/__init__.py`: empty file.

`backtest/alpha_factory/config.py`:
```python
"""Alpha Factory configuration — the ONLY place tunables live (no magic numbers in modules)."""
HORIZONS = (1, 5, 20)          # forward-return horizons (days) for IC/decay
N_FOLDS = 4                    # purged walk-forward OOS folds
EMBARGO_DAYS = 10              # gap dropped between folds (leak purge)
FDR_Q = 0.10                   # Benjamini-Hochberg false-discovery rate
K_FRAC = 0.2                   # long/short top/bottom fraction of universe (K = max(2, int(n*K_FRAC)))
TAKER_FEE = 0.0006             # per side, mirrors alphas.py xsmom cost
SLIPPAGE = 0.0005              # per side haircut, mirrors engine.SLIP
BORROW_ANNUAL = 0.10           # short-leg borrow cost per year, mirrors alphas.py
DPY = 365                      # crypto trades every day
DECAY_CHECK_HORIZON = 5        # days: signal must still be alive here...
DECAY_MIN_RATIO = 0.25         # ...with same-sign IC >= this fraction of the 1d IC
DSR_MIN_PROB = 0.5             # deflated-Sharpe probability floor
MIN_OBS_DAYS = 250             # min daily observations for a factor to be judged
OOS_SPLIT = 0.6                # incumbent-book OOS split point, mirrors alphas.py
EVAL_WINDOW_START = "2023-01-01"  # universe additions must be listed before this date
SURVIVORSHIP_CAVEAT = (
    "Universe selected from currently-liquid Binance pairs listed before "
    f"{EVAL_WINDOW_START}; coins delisted before today are absent, so absolute "
    "levels are modestly inflated. Rankings between factors remain comparable."
)
```

`backtest/alpha_factory/tests/conftest.py`:
```python
import sys
from pathlib import Path
# make `import engine` (backtest/) and `import alpha_factory.*` resolvable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
```

`backtest/alpha_factory/tests/test_ops.py` (scaffold only, real tests in Task 2):
```python
def test_scaffold_imports():
    import alpha_factory.config as cfg
    assert cfg.FDR_Q == 0.10 and cfg.N_FOLDS == 4
```

- [ ] **Step 4: Run**: `cd ~/Quant/backtest && ../.venv/bin/python -m pytest alpha_factory/tests -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**
```bash
cd ~/Quant && git add .gitignore backtest/alpha_factory && git commit -m "feat(factory): scaffold package + single-source config"
```

---

### Task 2: Operator library (`ops.py`)

**Files:**
- Create: `backtest/alpha_factory/ops.py`
- Test: `backtest/alpha_factory/tests/test_ops.py` (extend)

**Interfaces:**
- Produces (all take/return pd.DataFrame indexed by day, columns = coins):
  `ts_mean(df,w)`, `ts_std(df,w)`, `ts_sum(df,w)`, `ts_rank(df,w)`,
  `delta(df,w)`, `decay(df,w)`, `ts_corr(a,b,w)`, `cs_rank(df)`, `cs_z(df)`,
  `ewma(df,span)`, `rolling_skew(df,w)`, `rolling_kurt(df,w)`, `rsi(df,n)`

- [ ] **Step 1: Write failing tests** (append to `test_ops.py`):

```python
import numpy as np, pandas as pd

def toy():
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    return pd.DataFrame({"A": [1., 2, 3, 4, 5, 6], "B": [6., 5, 4, 3, 2, 1]}, index=idx)

def test_ts_ops():
    from alpha_factory import ops
    df = toy()
    assert ops.ts_mean(df, 2).iloc[-1, 0] == 5.5           # mean of 5,6
    assert ops.delta(df, 3).iloc[-1, 0] == 3.0             # 6-3
    assert ops.ts_rank(df, 3).iloc[-1, 0] == 1.0           # 6 is max of (4,5,6)
    w = np.array([1, 2, 3]) / 6                            # decay weights, newest heaviest
    assert abs(ops.decay(df, 3).iloc[-1, 0] - (4*w[0] + 5*w[1] + 6*w[2])) < 1e-9

def test_cs_ops():
    from alpha_factory import ops
    df = toy()
    r = ops.cs_rank(df)
    assert r.iloc[-1, 0] == 1.0 and r.iloc[-1, 1] == 0.0   # A top, B bottom
    z = ops.cs_z(df)
    assert abs(z.iloc[-1].mean()) < 1e-12                  # zero-mean rows

def test_ts_corr_sign():
    from alpha_factory import ops
    df = toy()
    c = ops.ts_corr(df[["A"]], df[["B"]].rename(columns={"B": "A"}), 4)
    assert c.iloc[-1, 0] < -0.99                           # perfectly anti-correlated
```

- [ ] **Step 2: Run to verify fail**: `../.venv/bin/python -m pytest alpha_factory/tests/test_ops.py -q` → FAIL (`No module named 'alpha_factory.ops'`).

- [ ] **Step 3: Implement `ops.py`**

```python
"""Composable operators on wide frames (index=UTC days, columns=coins). Pure pandas."""
import numpy as np, pandas as pd

def ts_mean(df, w): return df.rolling(w).mean()
def ts_std(df, w):  return df.rolling(w).std()
def ts_sum(df, w):  return df.rolling(w).sum()
def delta(df, w):   return df - df.shift(w)
def ewma(df, span): return df.ewm(span=span, adjust=False).mean()
def rolling_skew(df, w): return df.rolling(w).skew()
def rolling_kurt(df, w): return df.rolling(w).kurt()

def ts_rank(df, w):
    """Percentile (0..1) of today's value within the trailing w-window."""
    return df.rolling(w).rank(pct=True)

def decay(df, w):
    """Linear-decay weighted mean over w bars, newest heaviest (weights 1..w normalized)."""
    wts = np.arange(1, w + 1, dtype=float); wts /= wts.sum()
    return df.rolling(w).apply(lambda x: float(np.dot(x, wts)), raw=True)

def ts_corr(a, b, w):
    return a.rolling(w).corr(b)

def cs_rank(df):
    """Cross-sectional percentile rank per day, 0..1."""
    return df.rank(axis=1, pct=True) - 1.0 / (2 * df.count(axis=1)).values.reshape(-1, 1) * 0  # plain pct rank
def cs_rank(df):  # noqa: F811 — keep the simple, exact definition
    n = df.count(axis=1)
    return (df.rank(axis=1) - 1).div(n - 1, axis=0)

def cs_z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)

def rsi(df, n):
    d = df.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50)
```
(Note: keep only the second `cs_rank` — the first stub must not appear in the final file; final file defines each function once.)

- [ ] **Step 4: Run**: same command → all `test_ops.py` tests PASS.

- [ ] **Step 5: Commit**: `git add -A backtest/alpha_factory && git commit -m "feat(factory): operator library"`

---

### Task 3: Panel — real-data loader + synthetic generator (`panel.py`)

**Files:**
- Create: `backtest/alpha_factory/panel.py`
- Test: `backtest/alpha_factory/tests/test_panel.py`

**Interfaces:**
- Produces:
  - `@dataclass Panel: open, high, low, close, volume, funding` (all wide daily DataFrames, UTC index; `funding` may contain only a subset of columns) with property `ret` (close.pct_change) and `coins` (list).
  - `build_panel(data_dir: Path) -> Panel` — real CSVs via `engine.load`, `alphas.py` conventions: universe = coins with BOTH `{c}_4h.csv` and `{c}_bear_4h.csv`; merged, deduped (`keep="first"`), sorted; daily resample open=first/high=max/low=min/close=last/volume=sum; funding = per-day sum reindexed, 0-filled.
  - `build_synth_panel(n_coins=8, n_days=800, seed=7, signal_strength=0.0) -> tuple[Panel, pd.DataFrame]` — GBM paths; returns `(panel, planted)` where `planted` is a factor DataFrame that (when `signal_strength>0`) linearly predicts NEXT-day cross-sectional returns.

- [ ] **Step 1: Write failing tests** (`test_panel.py`):

```python
import numpy as np, pandas as pd
from pathlib import Path

def _write_csv(p, start_ms, n, price0):
    rows = ["open_time,open,high,low,close,volume"]
    t, px = start_ms, price0
    for i in range(n):
        o = px; c = px * (1 + 0.001 * ((i % 5) - 2)); h = max(o, c) * 1.001; l = min(o, c) * 0.999
        rows.append(f"{t},{o},{h},{l},{c},{100+i}")
        px = c; t += 4 * 3600 * 1000
    p.write_text("\n".join(rows))

def test_build_panel_merges_and_resamples(tmp_path):
    from alpha_factory.panel import build_panel
    day0 = 1672531200000  # 2023-01-01
    bear0 = day0 - 60 * 24 * 3600 * 1000
    for c in ["AAAUSDT", "BBBUSDT"]:
        _write_csv(tmp_path / f"{c}_4h.csv", day0, 6 * 30, 100.0)
        _write_csv(tmp_path / f"{c}_bear_4h.csv", bear0, 6 * 70, 90.0)   # overlaps 10 days
    (tmp_path / "AAAUSDT_funding.csv").write_text(
        "fundingTime,fundingRate\n" + f"{day0},0.0001\n{day0 + 8*3600*1000},0.0002\n")
    p = build_panel(tmp_path)
    assert p.coins == ["AAAUSDT", "BBBUSDT"]
    assert not p.close.index.duplicated().any()
    assert p.close.index.tz is not None
    assert abs(p.funding["AAAUSDT"].loc["2023-01-01"] - 0.0003) < 1e-12  # same-day sum
    assert (p.high >= p.low).all().all()

def test_synth_panel_reproducible_and_planted():
    from alpha_factory.panel import build_synth_panel
    p1, f1 = build_synth_panel(seed=7, signal_strength=0.5)
    p2, f2 = build_synth_panel(seed=7, signal_strength=0.5)
    assert p1.close.equals(p2.close) and f1.equals(f2)
    # planted factor must predict next-day cross-sectional returns
    fwd = p1.close.pct_change().shift(-1)
    daily_corr = f1.rank(axis=1).corrwith(fwd.rank(axis=1), axis=1)
    assert daily_corr.mean() > 0.1
    p3, _ = build_synth_panel(seed=7, signal_strength=0.0)
    assert not p3.close.isna().all().any() and len(p3.close) == 800
```

- [ ] **Step 2: Run to verify fail** → `No module named 'alpha_factory.panel'`.

- [ ] **Step 3: Implement `panel.py`**

```python
"""Data panel: real CSVs (engine.load + alphas.py conventions) or synthetic GBM for tests."""
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np, pandas as pd
from engine import load

@dataclass
class Panel:
    open: pd.DataFrame; high: pd.DataFrame; low: pd.DataFrame
    close: pd.DataFrame; volume: pd.DataFrame; funding: pd.DataFrame
    @property
    def ret(self): return self.close.pct_change().fillna(0.0)
    @property
    def coins(self): return list(self.close.columns)

def _merged(c, data_dir):
    df = pd.concat([load(f"{c}_bear", "4h", data_dir), load(c, "4h", data_dir)])
    return df[~df.index.duplicated(keep="first")].sort_index()

def build_panel(data_dir):
    data_dir = Path(data_dir)
    coins = sorted({p.stem[:-3] for p in data_dir.glob("*_4h.csv")
                    if not p.stem.endswith("_bear")
                    and (data_dir / f"{p.stem[:-3]}_bear_4h.csv").exists()})
    frames = {c: _merged(c, data_dir) for c in coins}
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    daily = {k: pd.DataFrame({c: frames[c][k].resample("1D").agg(v) for c in coins}).dropna(how="all")
             for k, v in agg.items()}
    idx = daily["close"].index
    fund = {}
    for c in coins:
        fp = data_dir / f"{c}_funding.csv"
        if fp.exists():
            f = pd.read_csv(fp); f["dt"] = pd.to_datetime(f.fundingTime, unit="ms", utc=True)
            fund[c] = f.set_index("dt").fundingRate.astype(float).resample("1D").sum()
    funding = pd.DataFrame(fund).reindex(idx).fillna(0.0) if fund else pd.DataFrame(index=idx)
    return Panel(daily["open"], daily["high"], daily["low"], daily["close"], daily["volume"], funding)

def build_synth_panel(n_coins=8, n_days=800, seed=7, signal_strength=0.0):
    """GBM closes + derived OHLCV + funding noise. If signal_strength>0, a hidden score
    is mixed into NEXT-day returns and returned as the planted factor."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n_days, freq="D", tz="UTC")
    cols = [f"C{i:02d}USDT" for i in range(n_coins)]
    score = pd.DataFrame(rng.standard_normal((n_days, n_coins)), index=idx, columns=cols)
    noise = rng.standard_normal((n_days, n_coins)) * 0.02
    r = noise.copy()
    if signal_strength > 0:  # today's score moves TOMORROW's return
        r[1:] += signal_strength * 0.02 * score.values[:-1]
    close = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=idx, columns=cols)
    spread = np.abs(rng.standard_normal((n_days, n_coins))) * 0.005
    high = close * (1 + spread); low = close * (1 - spread)
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.DataFrame(1e6 * (1 + np.abs(rng.standard_normal((n_days, n_coins)))), index=idx, columns=cols)
    funding = pd.DataFrame(rng.standard_normal((n_days, n_coins)) * 1e-4, index=idx, columns=cols)
    return Panel(open_, high, low, close, volume, funding), score
```

- [ ] **Step 4: Run** → `test_panel.py` PASS (and previous tests still green).

- [ ] **Step 5: Commit**: `git commit -am "feat(factory): panel loader + synthetic GBM generator"`

---

### Task 4: Factor zoo (`zoo.py`)

**Files:**
- Create: `backtest/alpha_factory/zoo.py`
- Test: `backtest/alpha_factory/tests/test_zoo.py`

**Interfaces:**
- Produces:
  - `@dataclass Factor: name, family, provenance, fn` (fn: `Panel -> pd.DataFrame`)
  - `build_zoo() -> list[Factor]` with `len >= 100`, unique names; families exactly:
    `momentum, reversal, tsrank, volatility, kbar, volume, capitulation, drawdown,
    carry, seasonality, pairs, oscillator, trendvalue, lottery, beta, baseline`

- [ ] **Step 1: Write failing tests** (`test_zoo.py`):

```python
import pandas as pd

def test_zoo_size_and_metadata():
    from alpha_factory.zoo import build_zoo
    zoo = build_zoo()
    names = [f.name for f in zoo]
    assert len(zoo) >= 100 and len(set(names)) == len(names)
    assert all(f.family and f.provenance for f in zoo)

def test_every_factor_computes_and_is_causal():
    from alpha_factory.zoo import build_zoo
    from alpha_factory.panel import build_synth_panel
    panel, _ = build_synth_panel(n_days=400, seed=3)
    cut = 300  # truncate future: values up to t must not change
    from alpha_factory.panel import Panel
    truncated = Panel(panel.open.iloc[:cut], panel.high.iloc[:cut], panel.low.iloc[:cut],
                      panel.close.iloc[:cut], panel.volume.iloc[:cut], panel.funding.iloc[:cut])
    for f in build_zoo():
        full = f.fn(panel); part = f.fn(truncated)
        assert isinstance(full, pd.DataFrame) and full.index.equals(panel.close.index), f.name
        a = full.iloc[:cut]; b = part
        pd.testing.assert_frame_equal(a, b, check_exact=False, atol=1e-10, obj=f.name)
```

- [ ] **Step 2: Run to verify fail** → module missing.

- [ ] **Step 3: Implement `zoo.py`** (parameter-grid generation; every factor reindexed to the close index so truncation math stays aligned):

```python
"""Factor zoo: >=100 formulaic candidates with family + provenance metadata.
Convention: HIGHER factor value = MORE attractive to be LONG. All inputs lagged-safe:
only data up to and including day t is used for the value at t (causality tested)."""
from dataclasses import dataclass
from typing import Callable
import numpy as np, pandas as pd
from . import ops
from .panel import Panel

@dataclass
class Factor:
    name: str; family: str; provenance: str; fn: Callable[[Panel], pd.DataFrame]

def _F(zoo, name, family, prov, fn):
    zoo.append(Factor(name, family, prov, lambda p, _fn=fn: _fn(p).reindex(p.close.index)))

def build_zoo():
    z = []
    Q = "Qlib Alpha158"; J = "Jansen ML4T"; FM = "Financial-Models notebooks (concept-mined)"
    TT = "TikTok lead (validated as candidate)"; IN = "in-repo alphas.py"; FAM = "family lesson"
    # momentum / reversal / ts-rank
    for h in (5, 10, 21, 28, 63, 126):
        _F(z, f"mom_{h}", "momentum", Q, lambda p, h=h: p.close.pct_change(h))
        _F(z, f"mom_vadj_{h}", "momentum", J,
           lambda p, h=h: p.close.pct_change(h) / ops.ts_std(p.ret, h).replace(0, np.nan))
    for h in (1, 2, 3, 5):
        _F(z, f"rev_{h}", "reversal", Q, lambda p, h=h: -p.close.pct_change(h))
    for w in (10, 21, 63):
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
    for w in (1, 5, 21):
        _F(z, f"kbar_body_{w}", "kbar", Q,
           lambda p, w=w: ops.ts_mean((p.close - p.open) / (p.high - p.low).replace(0, np.nan), w))
        _F(z, f"kbar_upshadow_{w}", "kbar", Q,
           lambda p, w=w: -ops.ts_mean((p.high - np.maximum(p.open, p.close)) / (p.high - p.low).replace(0, np.nan), w))
        _F(z, f"kbar_downshadow_{w}", "kbar", Q,
           lambda p, w=w: ops.ts_mean((np.minimum(p.open, p.close) - p.low) / (p.high - p.low).replace(0, np.nan), w))
        _F(z, f"kbar_closepos_{w}", "kbar", Q,
           lambda p, w=w: ops.ts_mean((p.close - p.low) / (p.high - p.low).replace(0, np.nan), w))
    _F(z, "doji_avoid_21", "kbar", FAM,
       lambda p: ops.ts_mean(((p.close - p.open).abs() / (p.high - p.low).replace(0, np.nan)), 21))
    # volume / liquidity
    for w in (10, 21, 63):
        _F(z, f"volz_{w}", "volume", Q,
           lambda p, w=w: (p.volume - ops.ts_mean(p.volume, w)) / ops.ts_std(p.volume, w).replace(0, np.nan))
    for w in (10, 21):
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
    for w in (21, 63, 126):
        _F(z, f"ddown_{w}", "drawdown", TT, lambda p, w=w: -(p.close / p.close.rolling(w).max() - 1))
    # carry / funding
    for w in (3, 7, 30):
        _F(z, f"carry_{w}", "carry", IN,
           lambda p, w=w: ops.ts_mean(p.funding.reindex(columns=p.close.columns), w).fillna(0.0))
    _F(z, "carry_trend_14", "carry", IN,
       lambda p: ops.delta(ops.ts_mean(p.funding.reindex(columns=p.close.columns), 7), 14).fillna(0.0))
    _F(z, "carry_csrank_7", "carry", IN,
       lambda p: ops.cs_rank(ops.ts_mean(p.funding.reindex(columns=p.close.columns), 7)).fillna(0.5))
    # seasonality (per-coin rolling weekday mean return)
    for w in (90, 180):
        def dow_mean(p, w=w):
            r = p.ret; out = pd.DataFrame(np.nan, index=r.index, columns=r.columns)
            for d in range(7):
                m = r.index.dayofweek == d
                out[m] = r[m].rolling(w // 7, min_periods=4).mean().values
            return out
        _F(z, f"dowmean_{w}", "seasonality", "seasonality_scan.py idea", dow_mean)
    # pairs vs BTC anchor (first column as anchor on synth; BTCUSDT if present)
    def _anchor(p): return "BTCUSDT" if "BTCUSDT" in p.close.columns else p.close.columns[0]
    for w, nm in ((63, "spread_ols_63"), (126, "spread_ols_126")):
        def spread(p, w=w):
            a = _anchor(p); la = np.log(p.close); lb = la[a]
            beta = la.rolling(w).cov(lb) / lb.rolling(w).var().replace(0, np.nan)
            s = la.sub(beta.mul(lb, axis=0))
            return -ops.cs_z((s - ops.ts_mean(s, w)) / ops.ts_std(s, w).replace(0, np.nan))
        _F(z, nm, "pairs", FM, spread)
    def kalman_spread(p, q=1e-4):
        a = _anchor(p); la = np.log(p.close); lb = la[a].values
        out = {}
        for c in la.columns:
            y = la[c].values; beta, P = 1.0, 1.0; res = np.full(len(y), np.nan)
            for i in range(len(y)):
                if np.isnan(y[i]) or np.isnan(lb[i]): continue
                P += q; e = y[i] - beta * lb[i]
                K = P * lb[i] / (lb[i] * P * lb[i] + 1e-2)
                beta += K * e; P *= (1 - K * lb[i]); res[i] = e
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
    _F(z, "macd_gap", "oscillator", J, lambda p: (ops.ewma(p.close, 12) - ops.ewma(p.close, 26)) / p.close)
    # trend / value-vs-trend
    for w in (10, 21, 63, 126, 200):
        _F(z, f"px_over_ma_{w}", "trendvalue", IN, lambda p, w=w: p.close / ops.ts_mean(p.close, w) - 1)
    _F(z, "tsmom_sign_28", "trendvalue", IN, lambda p: np.sign(p.close.pct_change(28)))
    # lottery / extremes
    for w in (21, 63):
        _F(z, f"maxret_{w}", "lottery", J, lambda p, w=w: -p.ret.rolling(w).max())
    _F(z, "streak", "lottery", J,
       lambda p: -(np.sign(p.ret) * (np.sign(p.ret).groupby((np.sign(p.ret) != np.sign(p.ret).shift()).cumsum().values).cumcount() + 1)))
    # beta / correlation to anchor
    for w in (21, 63):
        def beta_f(p, w=w):
            a = _anchor(p)
            return -(p.ret.rolling(w).cov(p.ret[a]) / p.ret[a].rolling(w).var().replace(0, np.nan))
        _F(z, f"lowbeta_{w}", "beta", J, beta_f)
        _F(z, f"anchorcorr_{w}", "beta", J, lambda p, w=w: -p.ret.rolling(w).corr(p.ret[_anchor(p)]))
    # baselines (sanity anchors mirroring alphas.py signals)
    _F(z, "base_xsmom_28", "baseline", IN, lambda p: p.close.pct_change(28))
    _F(z, "base_carry_3", "baseline", IN,
       lambda p: ops.ts_mean(p.funding.reindex(columns=p.close.columns), 3).fillna(0.0))
    _F(z, "base_rsi2", "baseline", IN, lambda p: -ops.rsi(p.close, 2))
    _F(z, "base_trend_200", "baseline", IN, lambda p: p.close / ops.ts_mean(p.close, 200) - 1)
    _F(z, "base_tsmom_28", "baseline", IN, lambda p: np.sign(p.close.pct_change(28)))
    return z
```

- [ ] **Step 4: Run** → `test_zoo.py` PASS (zoo ≥ 100: grids above yield ~104; if count lands below 100, extend the momentum/tsrank window grids — e.g. add windows 42, 252 — rather than loosening the test).

- [ ] **Step 5: Commit**: `git commit -am "feat(factory): 100+ factor zoo with provenance + causality test"`

---

### Task 5: Evaluation — IC, decay, quantile L/S, purged folds (`evaluate.py`)

**Files:**
- Create: `backtest/alpha_factory/evaluate.py`
- Test: `backtest/alpha_factory/tests/test_evaluate.py`

**Interfaces:**
- Produces:
  - `daily_ic(factor, fwd) -> pd.Series` (per-day cross-sectional Spearman)
  - `ic_stats(factor, close, horizons) -> dict` keys: `ic_{h}`, `icir_{h}` per horizon + `n_days`
  - `ls_returns(factor, ret, k_frac, fee, slip, borrow_annual, dpy) -> pd.Series` (net daily L/S, `shift(1)` execution)
  - `purged_folds(index, n_folds, embargo_days) -> list[pd.DatetimeIndex]`
  - `fold_sharpes(series, folds, dpy) -> list[float]`

- [ ] **Step 1: Write failing tests** (`test_evaluate.py`):

```python
import numpy as np, pandas as pd
from alpha_factory.panel import build_synth_panel
from alpha_factory import config as cfg

def test_planted_signal_has_positive_ic_and_noise_does_not():
    from alpha_factory.evaluate import ic_stats
    panel, planted = build_synth_panel(seed=11, signal_strength=0.5)
    s = ic_stats(planted, panel.close, (1, 5))
    assert s["ic_1"] > 0.10 and s["icir_1"] > 1.0
    rng = np.random.default_rng(0)
    noise = pd.DataFrame(rng.standard_normal(panel.close.shape),
                         index=panel.close.index, columns=panel.close.columns)
    sn = ic_stats(noise, panel.close, (1,))
    assert abs(sn["ic_1"]) < 0.05

def test_lookahead_factor_is_neutralized_by_shift():
    """A cheating factor (= same-day return) must show ~no NET edge once execution is shift(1)."""
    from alpha_factory.evaluate import ls_returns
    panel, _ = build_synth_panel(seed=5, signal_strength=0.0)
    cheat = panel.ret  # knows today's return "in advance"
    lsr = ls_returns(cheat, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
    sh = lsr.mean() / lsr.std() * np.sqrt(cfg.DPY)
    assert sh < 0.5  # no edge survives the one-day execution lag on iid noise

def test_planted_signal_makes_money_net_of_costs():
    from alpha_factory.evaluate import ls_returns
    panel, planted = build_synth_panel(seed=11, signal_strength=0.5)
    lsr = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
    assert lsr.mean() / lsr.std() * np.sqrt(cfg.DPY) > 1.0

def test_purged_folds_disjoint_with_embargo():
    from alpha_factory.evaluate import purged_folds
    idx = pd.date_range("2023-01-01", periods=400, freq="D", tz="UTC")
    folds = purged_folds(idx, 4, 10)
    assert len(folds) == 4
    for a, b in zip(folds, folds[1:]):
        assert (b[0] - a[-1]).days > 10   # embargo gap
    assert sum(len(f) for f in folds) <= 400 - 3 * 10
```

- [ ] **Step 2: Run to verify fail** → module missing.

- [ ] **Step 3: Implement `evaluate.py`**

```python
"""Per-factor evaluation: cross-sectional IC + decay, net quantile L/S, purged folds."""
import numpy as np, pandas as pd

def daily_ic(factor, fwd):
    fr = factor.rank(axis=1); rr = fwd.rank(axis=1)
    return fr.corrwith(rr, axis=1)

def ic_stats(factor, close, horizons):
    out = {}
    for h in horizons:
        fwd = close.pct_change(h).shift(-h)          # forward h-day return
        ic = daily_ic(factor, fwd).dropna()
        out[f"ic_{h}"] = float(ic.mean())
        out[f"icir_{h}"] = float(ic.mean() / ic.std() * np.sqrt(len(ic))) if ic.std() > 0 else 0.0
        out["n_days"] = int(len(ic))
    return out

def ls_returns(factor, ret, k_frac, fee, slip, borrow_annual, dpy):
    n = factor.count(axis=1)
    k = np.maximum(2, (n * k_frac).astype(int))
    rk = factor.rank(axis=1, ascending=False)
    wl = (rk.le(k, axis=0)).astype(float)
    ws = (rk.gt((n - k), axis=0)).astype(float)
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w = wl - ws
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    gross = (w.shift(1).fillna(0.0) * ret).sum(axis=1)
    return gross - turn * (fee + slip) - ws.shift(1).fillna(0.0).sum(axis=1) * borrow_annual / dpy

def purged_folds(index, n_folds, embargo_days):
    blocks = np.array_split(np.arange(len(index)), n_folds)
    folds = []
    for i, b in enumerate(blocks):
        s = b[embargo_days:] if i > 0 else b        # drop embargo at the leading edge
        folds.append(index[s])
    return folds

def fold_sharpes(series, folds, dpy):
    out = []
    for f in folds:
        s = series.reindex(f).dropna()
        out.append(float(s.mean() / s.std() * np.sqrt(dpy)) if len(s) > 30 and s.std() > 0 else 0.0)
    return out
```

- [ ] **Step 4: Run** → `test_evaluate.py` PASS.

- [ ] **Step 5: Commit**: `git commit -am "feat(factory): IC/decay + net L/S + purged walk-forward"`

---

### Task 6: Anti-fooling statistics (`stats.py`)

**Files:**
- Create: `backtest/alpha_factory/stats.py`
- Test: `backtest/alpha_factory/tests/test_stats.py`

**Interfaces:**
- Produces:
  - `ic_pvalue(ic_mean, ic_std_daily, n_days) -> float` (two-sided, normal approx of the t-stat)
  - `bh_fdr(pvals: list[float], q) -> list[bool]`
  - `deflated_sharpe_prob(sr_annual, n_days, dpy, skew, kurt_excess, n_trials) -> float`
  - `verdict(row: dict, cfg) -> tuple[str, str]` → `("SURVIVED"|"REJECTED", reason)`

- [ ] **Step 1: Write failing tests** (`test_stats.py`):

```python
import numpy as np

def test_bh_fdr_known_case():
    from alpha_factory.stats import bh_fdr
    pv = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    keep = bh_fdr(pv, 0.05)   # classic BH example: first 4 pass at q=.05
    assert keep == [True, True, True, True, False, False, False, False, False, False]

def test_ic_pvalue_scales():
    from alpha_factory.stats import ic_pvalue
    assert ic_pvalue(0.05, 0.2, 900) < 0.01          # strong, long sample
    assert ic_pvalue(0.01, 0.2, 100) > 0.5           # weak, short sample

def test_deflated_sharpe_punishes_trials():
    from alpha_factory.stats import deflated_sharpe_prob
    hi = deflated_sharpe_prob(1.5, 900, 365, 0.0, 0.0, n_trials=1)
    lo = deflated_sharpe_prob(1.5, 900, 365, 0.0, 0.0, n_trials=150)
    assert hi > lo and lo < 0.99

def test_noise_zoo_fdr_bound():
    """~200 pure-noise factors: survivors must be rare (FDR holds)."""
    import pandas as pd
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.evaluate import ic_stats
    from alpha_factory.stats import ic_pvalue, bh_fdr
    panel, _ = build_synth_panel(seed=42, signal_strength=0.0)
    rng = np.random.default_rng(1)
    pvals = []
    for i in range(200):
        f = pd.DataFrame(rng.standard_normal(panel.close.shape),
                         index=panel.close.index, columns=panel.close.columns)
        fwd = panel.close.pct_change().shift(-1)
        ic = f.rank(axis=1).corrwith(fwd.rank(axis=1), axis=1).dropna()
        pvals.append(ic_pvalue(ic.mean(), ic.std(), len(ic)))
    survivors = sum(bh_fdr(pvals, 0.10))
    assert survivors <= 6   # generous statistical bound for q=0.10 under the null
```

- [ ] **Step 2: Run to verify fail** → module missing.

- [ ] **Step 3: Implement `stats.py`**

```python
"""Multiple-testing control: p-values, Benjamini-Hochberg FDR, deflated Sharpe (Bailey & Lopez de Prado).
Metric conventions cross-checked against the open GS-Quant timeseries module."""
import math
from statistics import NormalDist
N = NormalDist()

def ic_pvalue(ic_mean, ic_std_daily, n_days):
    if ic_std_daily <= 0 or n_days < 2: return 1.0
    t = ic_mean / ic_std_daily * math.sqrt(n_days)
    return 2 * (1 - N.cdf(abs(t)))

def bh_fdr(pvals, q):
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh = 0.0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m: thresh = pvals[i]
    return [p <= thresh and thresh > 0 for p in pvals]

def deflated_sharpe_prob(sr_annual, n_days, dpy, skew, kurt_excess, n_trials):
    """P(true SR > 0) given the best-of-n_trials selection bias. Daily-unit SR internally."""
    if n_days < 30: return 0.0
    sr = sr_annual / math.sqrt(dpy)
    e = 0.5772156649
    if n_trials > 1:
        z1 = N.inv_cdf(1 - 1.0 / n_trials); z2 = N.inv_cdf(1 - 1.0 / (n_trials * math.e))
        sr0 = math.sqrt(1.0 / n_days) * ((1 - e) * z1 + e * z2)
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt_excess) / 4.0 * sr * sr))
    return N.cdf((sr - sr0) * math.sqrt(n_days - 1) / denom)

def verdict(row, cfg):
    """row keys: pval_pass, fold_sharpes, ic_1, ic_decay (=ic at DECAY_CHECK_HORIZON), dsr_prob, n_days."""
    if row["n_days"] < cfg.MIN_OBS_DAYS:  return "REJECTED", f"too few observations ({row['n_days']})"
    if not row["pval_pass"]:              return "REJECTED", "failed FDR"
    if min(row["fold_sharpes"]) <= 0:     return "REJECTED", "negative OOS fold"
    same_sign = row["ic_1"] * row["ic_decay"] > 0
    if not (same_sign and abs(row["ic_decay"]) >= cfg.DECAY_MIN_RATIO * abs(row["ic_1"])):
        return "REJECTED", "signal decays too fast"
    if row["dsr_prob"] < cfg.DSR_MIN_PROB: return "REJECTED", f"deflated Sharpe prob {row['dsr_prob']:.2f}"
    return "SURVIVED", "passed FDR + all folds + decay + DSR"
```

- [ ] **Step 4: Run** → `test_stats.py` PASS.

- [ ] **Step 5: Commit**: `git commit -am "feat(factory): FDR + deflated Sharpe + survival verdict"`

---

### Task 7: Incumbent-book improvement gate (`bench.py`)

**Files:**
- Create: `backtest/alpha_factory/bench.py`
- Test: `backtest/alpha_factory/tests/test_bench.py`

**Interfaces:**
- Consumes: `evaluate.ls_returns`, `config`.
- Produces:
  - `incumbent_sleeves(panel, cfg) -> dict[str, pd.Series]` — daily return series named
    `trend, xsmom, carry, rsi2dip, tsmom` (signal logic mirrors `alphas.py`; `trend` uses the
    `base_trend_200` long-only form: hold when close>MA200, equal-weight, with fee+slip on flips —
    NOT the full engine backtest, so bench works on synthetic panels too)
  - `ensemble(sleeves: dict) -> pd.Series` — inverse-vol weights (as `alphas.py`)
  - `improvement(candidate_lsr, sleeves, cfg) -> dict` keys:
    `max_corr` (max |corr| vs any sleeve), `corr_by_sleeve`,
    `base_oos_sharpe, with_oos_sharpe, delta_sharpe, base_maxdd, with_maxdd, delta_maxdd,
     improves (bool), redundant (bool: max_corr > 0.9)`
    OOS = final `1-OOS_SPLIT` fraction of days, mirroring `alphas.py`.

- [ ] **Step 1: Write failing tests** (`test_bench.py`):

```python
import numpy as np, pandas as pd
from alpha_factory.panel import build_synth_panel
from alpha_factory import config as cfg

def test_uncorrelated_edge_improves_book():
    from alpha_factory.bench import incumbent_sleeves, improvement
    from alpha_factory.evaluate import ls_returns
    panel, planted = build_synth_panel(seed=11, signal_strength=0.5)
    sleeves = incumbent_sleeves(panel, cfg)
    assert set(sleeves) == {"trend", "xsmom", "carry", "rsi2dip", "tsmom"}
    lsr = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
    imp = improvement(lsr, sleeves, cfg)
    assert imp["improves"] and imp["delta_sharpe"] > 0 and not imp["redundant"]

def test_clone_of_incumbent_is_redundant():
    from alpha_factory.bench import incumbent_sleeves, improvement
    panel, _ = build_synth_panel(seed=11, signal_strength=0.5)
    sleeves = incumbent_sleeves(panel, cfg)
    clone = sleeves["xsmom"] * 1.0000001
    imp = improvement(clone, sleeves, cfg)
    assert imp["redundant"] and imp["max_corr"] > 0.99
```

- [ ] **Step 2: Run to verify fail** → module missing.

- [ ] **Step 3: Implement `bench.py`**

```python
"""Incumbent book (the 5 alphas.py sleeves, panel-computable form) + improvement gate:
a survivor must make the WITH-ensemble beat the WITHOUT-ensemble out-of-sample."""
import numpy as np, pandas as pd
from . import ops
from .evaluate import ls_returns

def _flip_cost(pos, fee_slip):
    return pos.diff().abs().fillna(0.0) * fee_slip

def incumbent_sleeves(panel, cfg):
    px, ret = panel.close, panel.ret
    fee_slip = cfg.TAKER_FEE + cfg.SLIPPAGE
    ma200 = px.rolling(200).mean()
    # trend: long-only equal-weight when close > MA200 (panel form of the Donchian core's regime)
    pos = (px > ma200).astype(float)
    pos = pos.div(pos.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    trend = (pos.shift(1).fillna(0.0) * ret).sum(axis=1) - _flip_cost(pos, fee_slip).sum(axis=1)
    # xsmom 28d top/bottom 5 (alphas.py lines 44-48)
    m28 = px.pct_change(28); rk = m28.rank(axis=1, ascending=False); n = px.shape[1]
    wl = (rk <= 5).astype(float); ws = (rk >= n - 4).astype(float)
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    turn = (wl - ws).diff().abs().sum(axis=1).fillna(0.0)
    xsmom = ((wl - ws).shift(1).fillna(0.0) * ret).sum(axis=1) - turn * cfg.TAKER_FEE - cfg.BORROW_ANNUAL / cfg.DPY
    # carry (alphas.py lines 53-56)
    fund = panel.funding.reindex(columns=px.columns).fillna(0.0)
    on = (fund.rolling(3).mean() > 0).astype(float)
    carry = (on.shift(1).fillna(0.0) * fund - on.diff().abs().fillna(0.0) * 0.0004).mean(axis=1)
    # rsi2 dip-in-trend (alphas.py lines 59-66)
    r2 = ops.rsi(px, 2); up = px > ma200
    p2 = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    p2[(up) & (r2 < 10)] = 1.0; p2[r2 > 50] = 0.0; p2 = p2.ffill().fillna(0.0)
    rsi2dip = (p2.shift(1).fillna(0.0) * ret - _flip_cost(p2, cfg.TAKER_FEE)).fillna(0.0).mean(axis=1)
    # tsmom (alphas.py lines 68-69)
    sig = (px.pct_change(28) > 0).astype(float).shift(1).fillna(0.0)
    sig = sig.div(sig.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    tsmom = (sig * ret).sum(axis=1)
    return {"trend": trend, "xsmom": xsmom, "carry": carry, "rsi2dip": rsi2dip, "tsmom": tsmom}

def ensemble(sleeves):
    df = pd.DataFrame(sleeves).fillna(0.0)
    vol = df.std().replace(0, np.nan)
    w = (1 / vol) / (1 / vol).sum()
    return (df * w).sum(axis=1)

def _sharpe(s, dpy):
    s = s.dropna()
    return float(s.mean() / s.std() * np.sqrt(dpy)) if len(s) > 30 and s.std() > 0 else 0.0

def _maxdd(s):
    eq = (1 + s.fillna(0.0)).cumprod()
    return float((eq / eq.cummax() - 1).min())

def improvement(candidate_lsr, sleeves, cfg):
    df = pd.DataFrame(sleeves)
    corr = df.corrwith(candidate_lsr).abs()
    base = ensemble(sleeves)
    withc = ensemble({**sleeves, "candidate": candidate_lsr})
    cut = int(len(base) * cfg.OOS_SPLIT)
    b, w = base.iloc[cut:], withc.iloc[cut:]
    out = dict(max_corr=float(corr.max()), corr_by_sleeve=corr.round(2).to_dict(),
               base_oos_sharpe=_sharpe(b, cfg.DPY), with_oos_sharpe=_sharpe(w, cfg.DPY),
               base_maxdd=_maxdd(b), with_maxdd=_maxdd(w))
    out["delta_sharpe"] = out["with_oos_sharpe"] - out["base_oos_sharpe"]
    out["delta_maxdd"] = out["with_maxdd"] - out["base_maxdd"]
    out["redundant"] = out["max_corr"] > 0.9
    out["improves"] = out["delta_sharpe"] > 0 and not out["redundant"]
    return out
```

- [ ] **Step 4: Run** → `test_bench.py` PASS.

- [ ] **Step 5: Commit**: `git commit -am "feat(factory): incumbent-book improvement gate (better-or-worse vs old stats)"`

---

### Task 8: Report + CLI (`report.py`, `__main__.py`)

**Files:**
- Create: `backtest/alpha_factory/report.py`, `backtest/alpha_factory/__main__.py`
- Test: `backtest/alpha_factory/tests/test_end_to_end.py`

**Interfaces:**
- Produces:
  - `run_factory(panel, zoo, cfg, n_trials=None) -> pd.DataFrame` — one row per factor:
    `name, family, provenance, ic_1, icir_1, ic_5, ic_20, ls_sharpe, fold_sharpes,
     pval, dsr_prob, turnover, verdict, reason` + for SURVIVED rows the improvement-gate
    columns `max_corr, delta_sharpe, delta_maxdd, improves_book`
  - `render(df, cfg, out_dir, stamp) -> tuple[Path, Path]` — writes
    `ALPHA_FACTORY_<stamp>.md` (header: config dump + survivorship caveat; sections:
    SURVIVED table sorted by dsr_prob desc with improvement columns, then REJECTED counts
    by reason, then full CSV pointer) and `.csv` (all rows)
  - CLI: `python -m alpha_factory --data-dir data --out ../backtest_results [--synth]`

- [ ] **Step 1: Write failing test** (`test_end_to_end.py`):

```python
import pandas as pd
from alpha_factory import config as cfg

def test_factory_end_to_end_on_synthetic(tmp_path):
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.zoo import build_zoo, Factor
    from alpha_factory.report import run_factory, render
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:20] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    assert set(["name", "verdict", "reason", "dsr_prob"]).issubset(df.columns)
    row = df[df.name == "planted"].iloc[0]
    assert row.verdict == "SURVIVED" and row.improves_book in (True, False)
    md, csv = render(df, cfg, tmp_path, "TEST")
    text = md.read_text()
    assert "SURVIVED" in text and cfg.SURVIVORSHIP_CAVEAT[:40] in text
    assert csv.exists() and len(pd.read_csv(csv)) == len(df)
```

- [ ] **Step 2: Run to verify fail** → module missing.

- [ ] **Step 3: Implement `report.py`**

```python
"""Orchestration + scoreboard rendering."""
from pathlib import Path
import numpy as np, pandas as pd
from . import config as _cfg
from .evaluate import ic_stats, ls_returns, purged_folds, fold_sharpes, daily_ic
from .stats import ic_pvalue, bh_fdr, deflated_sharpe_prob, verdict
from .bench import incumbent_sleeves, improvement

def run_factory(panel, zoo, cfg=_cfg, n_trials=None):
    n_trials = n_trials or len(zoo)
    folds = purged_folds(panel.close.index, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    rows = []
    for f in zoo:
        fac = f.fn(panel)
        s = ic_stats(fac, panel.close, cfg.HORIZONS)
        fwd1 = panel.close.pct_change().shift(-1)
        ic1 = daily_ic(fac, fwd1).dropna()
        lsr = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
        fs = fold_sharpes(lsr, folds, cfg.DPY)
        sr = float(lsr.mean() / lsr.std() * np.sqrt(cfg.DPY)) if lsr.std() > 0 else 0.0
        rows.append(dict(name=f.name, family=f.family, provenance=f.provenance,
                         ic_1=s.get("ic_1", 0.0), icir_1=s.get("icir_1", 0.0),
                         ic_5=s.get("ic_5", 0.0), ic_20=s.get("ic_20", 0.0),
                         ic_decay=s.get(f"ic_{cfg.DECAY_CHECK_HORIZON}", 0.0),
                         n_days=s.get("n_days", 0), ls_sharpe=sr, fold_sharpes=fs,
                         pval=ic_pvalue(float(ic1.mean()), float(ic1.std()), len(ic1)),
                         dsr_prob=deflated_sharpe_prob(sr, len(lsr.dropna()), cfg.DPY,
                                                       float(lsr.skew() or 0), float(lsr.kurt() or 0), n_trials),
                         turnover=float(np.nan_to_num(lsr.abs().mean())), _lsr=lsr))
    keep = bh_fdr([r["pval"] for r in rows], cfg.FDR_Q)
    sleeves = incumbent_sleeves(panel, cfg)
    for r, k in zip(rows, keep):
        r["pval_pass"] = bool(k)
        r["verdict"], r["reason"] = verdict(r, cfg)
        if r["verdict"] == "SURVIVED":
            imp = improvement(r.pop("_lsr"), sleeves, cfg)
            r.update(max_corr=imp["max_corr"], delta_sharpe=round(imp["delta_sharpe"], 3),
                     delta_maxdd=round(imp["delta_maxdd"], 3), improves_book=imp["improves"])
            if imp["redundant"]:
                r["reason"] += " (REDUNDANT vs incumbent sleeve)"
        else:
            r.pop("_lsr"); r.update(max_corr=np.nan, delta_sharpe=np.nan,
                                    delta_maxdd=np.nan, improves_book=False)
    return pd.DataFrame(rows).sort_values(["verdict", "dsr_prob"], ascending=[False, False]).reset_index(drop=True)

def render(df, cfg, out_dir, stamp):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    md, csv = out_dir / f"ALPHA_FACTORY_{stamp}.md", out_dir / f"ALPHA_FACTORY_{stamp}.csv"
    df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore").to_csv(csv, index=False)
    surv = df[df.verdict == "SURVIVED"]
    cfg_dump = {k: getattr(cfg, k) for k in dir(cfg) if k.isupper() and k != "SURVIVORSHIP_CAVEAT"}
    lines = [f"# Alpha Factory scoreboard — {stamp}", "",
             f"> {cfg.SURVIVORSHIP_CAVEAT}", "", f"Config: `{cfg_dump}`",
             f"Factors tested: {len(df)} · SURVIVED: {len(surv)} · REJECTED: {len(df) - len(surv)}", "",
             "## SURVIVED (sorted by deflated-Sharpe probability)", "",
             "| factor | family | prov | IC1 | ICIR1 | LS Sharpe | folds | DSRp | maxCorr | ΔSharpe | ΔDD | IMPROVES BOOK |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in surv.iterrows():
        folds = "/".join(f"{x:.1f}" for x in r.fold_sharpes)
        lines.append(f"| {r['name']} | {r.family} | {r.provenance.split()[0]} | {r.ic_1:.3f} | {r.icir_1:.1f} | "
                     f"{r.ls_sharpe:.2f} | {folds} | {r.dsr_prob:.2f} | {r.max_corr:.2f} | "
                     f"{r.delta_sharpe:+.3f} | {r.delta_maxdd:+.3f} | {'YES' if r.improves_book else 'no'} |")
    lines += ["", "## REJECTED — count by reason", ""]
    for reason, n in df[df.verdict == "REJECTED"].reason.value_counts().items():
        lines.append(f"- {n:4d} × {reason}")
    lines += ["", f"Full per-factor table: `{csv.name}`", ""]
    md.write_text("\n".join(lines))
    return md, csv
```

`backtest/alpha_factory/__main__.py`:
```python
import argparse, datetime as dt
from pathlib import Path
from . import config as cfg
from .zoo import build_zoo
from .report import run_factory, render

def main():
    ap = argparse.ArgumentParser(description="Alpha Factory: test the whole zoo, honestly.")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "backtest_results"))
    ap.add_argument("--synth", action="store_true", help="run on synthetic data (demo/self-check)")
    a = ap.parse_args()
    if a.synth:
        from .panel import build_synth_panel
        panel, _ = build_synth_panel(seed=11, signal_strength=0.3)
    else:
        from .panel import build_panel
        panel = build_panel(a.data_dir)
    zoo = build_zoo()
    print(f"panel: {len(panel.close)} days x {len(panel.coins)} coins · zoo: {len(zoo)} factors")
    df = run_factory(panel, zoo, cfg)
    stamp = dt.date.today().isoformat()
    md, csv = render(df, cfg, a.out, stamp)
    print(f"wrote {md}\nwrote {csv}")
    print(df[df.verdict == "SURVIVED"][["name", "ls_sharpe", "dsr_prob", "delta_sharpe", "improves_book"]]
          .to_string(index=False))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run** → `test_end_to_end.py` PASS, then demo: `../.venv/bin/python -m alpha_factory --synth --out /tmp/af_demo` → prints scoreboard, writes files.

- [ ] **Step 5: Commit**: `git commit -am "feat(factory): scoreboard report + CLI"`

---

### Task 9: Real data — universe expansion + fetch

**Files:**
- Modify: `backtest/fetch_universe.py` (SYMBOLS list), `backtest/fetch_bear.py` (SYMBOLS list)

**Interfaces:**
- Produces: `backtest/data/*.csv` for 20 coins × (4h + bear_4h) + funding CSVs.

- [ ] **Step 1: Extend both SYMBOLS lists** to the same 20 (all Binance-listed before 2023-01-01, per the survivorship rule; the 10 existing plus):

```python
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","DOGEUSDT",
           "LINKUSDT","LTCUSDT","DOTUSDT","ATOMUSDT","UNIUSDT","ETCUSDT","XLMUSDT","FILUSDT",
           "NEARUSDT","SANDUSDT","TRXUSDT","EOSUSDT"]
```

- [ ] **Step 2: Fetch** (network; ~5-10 min, resumable — existing files are skipped):
```bash
cd ~/Quant/backtest && ../.venv/bin/python fetch_universe.py && ../.venv/bin/python fetch_bear.py && ../.venv/bin/python fetch_funding.py
```
Expected: `backtest/data/` contains ≥ 20 `_4h.csv`, ≥ 20 `_bear_4h.csv`, ≥ 15 `_funding.csv`.

- [ ] **Step 3: Sanity-load**:
```bash
../.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from alpha_factory.panel import build_panel
p = build_panel('data'); print(len(p.coins),'coins,',len(p.close),'days, funding cols:',len(p.funding.columns))"
```
Expected: `20 coins, >=1200 days`.

- [ ] **Step 4: Commit** (code only — data stays gitignored):
```bash
git add backtest/fetch_universe.py backtest/fetch_bear.py && git commit -m "feat(factory): expand universe to 20 pre-2023-listed coins"
```

---

### Task 10: Baseline-reproduction validation + first real run

**Files:**
- Create: `backtest/alpha_factory/tests/test_real_data.py`
- Produce: `backtest_results/ALPHA_FACTORY_<date>.md` + `.csv` (committed)

- [ ] **Step 1: Write the integration test** (`test_real_data.py`):

```python
"""Validation #4 (spec): known-alpha anchors on REAL data. Auto-skips when data absent."""
import pytest
from pathlib import Path
DATA = Path(__file__).resolve().parents[2] / "data"
pytestmark = pytest.mark.skipif(not (DATA / "BTCUSDT_4h.csv").exists(), reason="no real data")

def test_baseline_anchors():
    from alpha_factory.panel import build_panel
    from alpha_factory.bench import incumbent_sleeves, _sharpe
    from alpha_factory import config as cfg
    panel = build_panel(DATA)
    sleeves = incumbent_sleeves(panel, cfg)
    cut = int(len(panel.close) * cfg.OOS_SPLIT)
    oos = {k: _sharpe(v.iloc[cut:], cfg.DPY) for k, v in sleeves.items()}
    assert oos["carry"] > 0, f"carry must be positive OOS (documented finding), got {oos}"
    weak = sum(1 for k in ("xsmom", "rsi2dip", "tsmom") if oos[k] < 0.8)
    assert weak >= 2, f"most non-carry alphas are documented weak OOS, got {oos}"
```

- [ ] **Step 2: Run it**: `../.venv/bin/python -m pytest alpha_factory/tests -q` → all pass including real-data anchors. If the anchor test FAILS, STOP — the harness or the data is wrong; do not tune the test to pass. Investigate against `alphas.py`'s own printed output (`../.venv/bin/python alphas.py`).

- [ ] **Step 3: Full real run**:
```bash
../.venv/bin/python -m alpha_factory
```
Expected: scoreboard printed; `backtest_results/ALPHA_FACTORY_<date>.md/.csv` written. Runtime target < 15 min; if slower, profile the zoo loop (decay() is the usual suspect — acceptable to swap `rolling.apply` for a stride-trick dot product, keeping tests green).

- [ ] **Step 4: Commit the report**:
```bash
cd ~/Quant && git add backtest_results/ALPHA_FACTORY_* && git commit -m "feat(factory): first full scoreboard run on the 20-coin panel"
```

---

### Task 11: Documentation + brain pointers

**Files:**
- Modify: `~/Quant/index.md` (Infra/Results section), `~/Quant/CLAUDE.md` (one line under Files), `~/SecondBrain/docs/features-log.md`, `~/SecondBrain/memory/trading-open-items.md` (status), `~/SecondBrain/memory/session-log.md`

- [ ] **Step 1:** Add to `~/Quant/index.md` under Results: `- [[ALPHA_FACTORY_<date>]] — factor-zoo scoreboard (factory: backtest/alpha_factory/)`. Add to `~/Quant/CLAUDE.md` file table: `| backtest/alpha_factory/ | Factor-mining pipeline: python -m alpha_factory (see docs/superpowers/specs/2026-07-14-alpha-factory-design.md) |`
- [ ] **Step 2:** Brain (Rule 9): features-log line `[quant] Alpha Factory SHIPPED — <n> factors, <k> survived, <j> improve book (ΔSharpe listed) → Quant backtest_results/ALPHA_FACTORY_<date>.md`; update the 🏭 block in trading-open-items with the outcome; session-log entry.
- [ ] **Step 3:** Commit + push both repos.

---

## Verification checklist (spec success criteria → tasks)

1. All four validation tests pass → Tasks 3 (planted), 6 (noise/FDR), 5 (leak), 10 (baseline anchors).
2. One command produces the scoreboard → Task 8 CLI, Task 10 real run.
3. No `live_bot/`/web changes → no task touches them.
4. Every factor's verdict carries its reason → Task 6 `verdict()` + Task 8 report.
5. Better-or-worse vs the old book explicitly reported → Task 7 gate, surfaced in Task 8 table (`ΔSharpe/ΔDD/IMPROVES BOOK`).

## Self-review notes

- Spec coverage: panel/zoo/evaluate/stats/report/CLI/validation/universe/survivorship/improvement-gate all mapped to tasks; "Alpha158-adapted families" realized as the 16 families in Task 4 (≥100 factors enforced by test).
- Type consistency: `Factor(name, family, provenance, fn)` used identically in Tasks 4/8; `ls_returns(factor, ret, k_frac, fee, slip, borrow_annual, dpy)` signature identical in Tasks 5/7/8; `cfg` constants referenced only via `config.py`.
- Known deviation from spec wording: CLI is `python -m alpha_factory` (name-clash with the package dir); config lives in `config.py` rather than "top of the CLI" — same single-source intent, testable.
