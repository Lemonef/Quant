# Broker Adapter — Phase 1 (Refactor + Paper + Strat-Neutral Guards) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `live_bot/paper_bot.py`'s inline simulated execution into a `Broker` + `Sizer` abstraction (paper behavior byte-identical to today) and wire the strat-neutral, paper-testable safety guards — so the live layer (Phase 2) can drop in later with zero strategy risk.

**Architecture:** Extract the inline fill math (`cs["cash"] -= u*price*(1±COST)`) behind a `Broker` interface with a `PaperBroker` that reproduces today's sim exactly (returns a `FillReport`). Extract the per-sleeve position sizing behind a `Sizer` interface with an `EqualWeightSizer`. Add a config module (paper-default, live-locked) + guards that only fire on bad data/bugs. A **golden-master test** (capture today's outputs on frozen data, assert identical after refactor) is the safety net for every task.

**Tech Stack:** Python 3.12, pandas/numpy, pytest (new), CCXT (Phase 2 only — not this plan). No live exchange, no real money in Phase 1.

**Scope boundary:** Phase 2 (separate plan) = `LiveBroker`, idempotency, reconcile-or-halt, execution ledger, HALT recovery, resting stops, shadow mode. NOT in this plan.

---

## File structure (Phase 1)
- Create `live_bot/broker.py` — `Broker` ABC + `FillReport` dataclass + `PaperBroker`.
- Create `live_bot/sizer.py` — `Sizer` ABC + `EqualWeightSizer`.
- Create `live_bot/botconfig.py` — env-driven config (`LIVE`, `DRY_RUN`, `HALT`, broker/sizer selection) + `validate()`.
- Create `live_bot/guards.py` — `bad_tick_ok()`, `data_quality_ok()`, `atomic_write_json()`.
- Modify `live_bot/paper_bot.py` — route fills through the broker, sizing through the sizer, wire guards + config; strategy logic unchanged.
- Create `requirements.txt` (root) — pinned deps.
- Create `tests/` — `conftest.py`, `test_golden_master.py`, `test_broker.py`, `test_sizer.py`, `test_guards.py`, `test_config.py`.
- Create `tests/fixtures/` — frozen input klines + captured baseline outputs.

---

### Task 0: Test harness + pinned deps + golden-master baseline

**Files:**
- Create: `requirements.txt`
- Create: `tests/conftest.py`, `tests/fixtures/README.md`
- Create: `tests/capture_baseline.py`

- [ ] **Step 1: Pin dependencies**

Create `requirements.txt` (root):
```
pandas==2.2.3
numpy==2.1.3
requests==2.32.3
pytest==8.3.4
# ccxt pinned in Phase 2 when LiveBroker lands
```

- [ ] **Step 2: Install + confirm the bot still runs**

Run: `pip install -r requirements.txt && cd live_bot && python -c "import paper_bot"`
Expected: imports clean, no error.

- [ ] **Step 3: Freeze an input snapshot + capture baseline outputs (golden master)**

Create `tests/capture_baseline.py` — runs the CURRENT bot logic against a frozen set of klines and saves the resulting state JSONs + `data.json` as fixtures. Because the live bot fetches from Binance, the capture monkeypatches `fetch` to read committed CSVs from `backtest/data/` for a fixed COIN set and a fixed as-of bar, and points state paths at a temp dir.

```python
# tests/capture_baseline.py — run ONCE to create fixtures, re-run only to intentionally rebaseline
import json, shutil, os
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
FIX.mkdir(exist_ok=True)

def frozen_fetch(coin, _cache={}):
    # deterministic: last 400 4h bars from the committed backtest CSV
    df = pd.read_csv(ROOT / "backtest" / "data" / f"{coin}_4h.csv")
    df = df.rename(columns={"close":"c","high":"h","low":"l","open":"o","volume":"v"})
    df["t"] = pd.to_datetime(df[df.columns[0]], unit="ms", utc=True)
    return df.set_index("t").tail(400)

def run_capture(tag, out_dir):
    import importlib, sys
    sys.path.insert(0, str(ROOT / "live_bot"))
    import paper_bot as pb
    importlib.reload(pb)
    pb.fetch = frozen_fetch                      # deterministic input
    pb.HERE = out_dir; out_dir.mkdir(parents=True, exist_ok=True)
    # redirect state + web output into out_dir
    pb.cycle()
    snap = {}
    for p in sorted(out_dir.glob("state_*.json")):
        snap[p.name] = json.loads(p.read_text())
    dj = out_dir / ".." / "web" / "data.json"
    return snap

if __name__ == "__main__":
    base = FIX / "baseline_state"
    if base.exists(): shutil.rmtree(base)
    snap = run_capture("baseline", base)
    (FIX / "baseline_snapshot.json").write_text(json.dumps(snap, indent=2, sort_keys=True))
    print(f"baseline captured: {len(snap)} state files")
```

Run: `python tests/capture_baseline.py`
Expected: prints "baseline captured: 12 state files" (3 strats × 3 lev + blends), writes `tests/fixtures/baseline_snapshot.json`.

- [ ] **Step 4: Golden-master test that re-runs and diffs**

Create `tests/test_golden_master.py`:
```python
import json
from pathlib import Path
from tests.capture_baseline import run_capture, FIX

def test_outputs_identical_to_baseline(tmp_path):
    baseline = json.loads((FIX / "baseline_snapshot.json").read_text())
    fresh = run_capture("check", tmp_path / "state")
    # normalize floats to 8dp to ignore FP noise, then exact-diff
    def norm(o):
        if isinstance(o, float): return round(o, 8)
        if isinstance(o, dict): return {k: norm(v) for k, v in o.items()}
        if isinstance(o, list): return [norm(x) for x in o]
        return o
    assert norm(fresh) == norm(baseline), "refactor changed paper-bot output — investigate before proceeding"
```

- [ ] **Step 5: Run it — must PASS before any refactor**

Run: `pytest tests/test_golden_master.py -v`
Expected: PASS (the bot vs its own baseline). This is the regression guard for every later task.

- [ ] **Step 6: Commit**
```bash
git add requirements.txt tests/ && git commit -m "test: golden-master harness + pinned deps for broker-adapter refactor"
```

---

### Task 1: `FillReport` + `Broker` interface + `PaperBroker` (fills only)

**Files:**
- Create: `live_bot/broker.py`
- Test: `tests/test_broker.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_broker.py
from live_bot.broker import PaperBroker, FillReport

def test_paper_buy_matches_inline_math():
    b = PaperBroker(cost=0.0008)
    # buying `units` at `price` should debit cash by units*price*(1+cost)
    fill = b.fill(side="BUY", price=100.0, units=2.0)
    assert isinstance(fill, FillReport)
    assert fill.side == "BUY"
    assert fill.filled_qty == 2.0
    assert fill.avg_fill_price == 100.0
    assert round(fill.cash_delta, 8) == round(-2.0*100.0*(1+0.0008), 8)   # -200.16

def test_paper_sell_matches_inline_math():
    b = PaperBroker(cost=0.0008)
    fill = b.fill(side="SELL", price=100.0, units=2.0)
    assert round(fill.cash_delta, 8) == round(2.0*100.0*(1-0.0008), 8)     # +199.84
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_broker.py -v`
Expected: FAIL — `No module named 'live_bot.broker'`.

- [ ] **Step 3: Implement `broker.py`**
```python
# live_bot/broker.py
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class FillReport:
    side: str            # "BUY" | "SELL"
    filled_qty: float
    avg_fill_price: float
    cash_delta: float    # signed change to cash (negative on buy, positive on sell)
    fee_paid: float
    status: str = "filled"

class Broker(ABC):
    @abstractmethod
    def fill(self, side: str, price: float, units: float) -> FillReport: ...

class PaperBroker(Broker):
    """Reproduces the inline sim EXACTLY: buy debits units*price*(1+cost); sell credits units*price*(1-cost)."""
    def __init__(self, cost: float = 0.0008):
        self.cost = cost
    def fill(self, side, price, units) -> FillReport:
        if side == "BUY":
            gross = units * price; fee = gross * self.cost
            return FillReport("BUY", units, price, -(gross + fee), fee)
        elif side == "SELL":
            gross = units * price; fee = gross * self.cost
            return FillReport("SELL", units, price, (gross - fee), fee)
        raise ValueError(side)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_broker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add live_bot/broker.py tests/test_broker.py && git commit -m "feat: Broker interface + PaperBroker (fill math extracted, not yet wired)"
```

---

### Task 2: Wire the 3 sleeves' fills through `PaperBroker` — golden-master must stay identical

**Files:**
- Modify: `live_bot/paper_bot.py` (buy/sell blocks at ~L439, L447, L456, L465, L474, L483)

- [ ] **Step 1: Instantiate the broker once**

In `paper_bot.py`, near the config constants (after `COST=...`), add:
```python
from broker import PaperBroker
BROKER = PaperBroker(cost=COST)
```

- [ ] **Step 2: Replace the trend SELL fill (was `cs["cash"]+=cs["units"]*price*(1-COST)`)**

Replace (L439 area):
```python
pnl=cs["units"]*price*(1-COST)-cs["units"]*cs["entry"]*(1+COST); cs["cash"]+=cs["units"]*price*(1-COST)
```
with:
```python
f=BROKER.fill("SELL",price,cs["units"]); cs["cash"]+=f.cash_delta
pnl=f.cash_delta-cs["units"]*cs["entry"]*(1+COST)
```

- [ ] **Step 3: Replace the trend BUY fill (was `cs["cash"]-=u*price*(1+COST)`)**

Replace (L447 area):
```python
cs["cash"]-=u*price*(1+COST); cs.update(units=u,entry=price,stop=price-sd,peak=high,trough=low,bars=0)
```
with:
```python
f=BROKER.fill("BUY",price,u); cs["cash"]+=f.cash_delta
cs.update(units=u,entry=price,stop=price-sd,peak=high,trough=low,bars=0)
```

- [ ] **Step 4: Repeat the same BUY/SELL substitution for flush (L456, L465) and crashreb (L474, L483)**

Apply the identical pattern: SELL → `f=BROKER.fill("SELL",price,units); cash+=f.cash_delta; pnl=f.cash_delta-units*entry*(1+COST)`; BUY → `f=BROKER.fill("BUY",price,u); cash+=f.cash_delta`. (Same math, so numbers are unchanged.)

- [ ] **Step 5: Run the golden master — MUST still be identical**

Run: `pytest tests/test_golden_master.py -v`
Expected: PASS (byte-identical). If it fails, a substitution changed a number — diff and fix before continuing.

- [ ] **Step 6: Commit**
```bash
git add live_bot/paper_bot.py && git commit -m "refactor: route all sleeve fills through PaperBroker (byte-identical)"
```

---

### Task 3: `Sizer` interface + `EqualWeightSizer` + wire it

**Files:**
- Create: `live_bot/sizer.py`
- Test: `tests/test_sizer.py`
- Modify: `live_bot/paper_bot.py` (sizing at L445 trend, L463 flush, L481 crashreb)

- [ ] **Step 1: Write the failing test**
```python
# tests/test_sizer.py
from live_bot.sizer import EqualWeightSizer

def test_trend_size_matches_inline():
    s = EqualWeightSizer()
    # trend: u = L*(cash*risk_pct/100)/stop_dist, capped at cash*0.95*L/price
    u = s.trend_units(cash=1000.0, risk_pct=5.0, stop_dist=2.0, lev=1, price=100.0)
    raw = 1*(1000.0*5.0/100)/2.0            # 25
    cap = 1000.0*0.95*1/100.0               # 9.5
    assert round(u, 8) == round(min(raw, cap), 8)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_sizer.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `sizer.py`** (lift the exact formulas from L445/L463/L481)
```python
# live_bot/sizer.py
from abc import ABC, abstractmethod

class Sizer(ABC):
    @abstractmethod
    def trend_units(self, cash, risk_pct, stop_dist, lev, price) -> float: ...
    @abstractmethod
    def flush_units(self, cash, r_prev, lev, price) -> float: ...
    @abstractmethod
    def crash_units(self, cash, lev, price) -> float: ...

class EqualWeightSizer(Sizer):
    def trend_units(self, cash, risk_pct, stop_dist, lev, price):
        u = lev*(cash*risk_pct/100)/stop_dist
        return min(u, cash*0.95*lev/price)
    def flush_units(self, cash, r_prev, lev, price):
        size = min(3.0, abs(r_prev)/0.10)
        u = lev*size*cash*0.95/price
        return min(u, cash*0.95*lev/price)
    def crash_units(self, cash, lev, price):
        return lev*cash*0.95/price
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_sizer.py -v`
Expected: PASS.

- [ ] **Step 5: Wire it in `paper_bot.py`**

Add near the broker init: `from sizer import EqualWeightSizer` / `SIZER = EqualWeightSizer()`.
Replace trend sizing (L445) `sd=av*ATR_STOP; u=L*(cs["cash"]*RISK_PCT/100)/sd; u=min(u,cs["cash"]*0.95*L/price)` with:
```python
sd=av*ATR_STOP; u=SIZER.trend_units(cs["cash"],RISK_PCT,sd,L,price)
```
Replace flush sizing (L463) with `u=SIZER.flush_units(fs["cash"],r_prev,L,price)` (keep the `size=min(3.0,abs(r_prev)/0.10)` line for logging).
Replace crashreb sizing (L481) with `u=SIZER.crash_units(xs["cash"],L,price)`.

- [ ] **Step 6: Golden master — MUST stay identical**

Run: `pytest tests/test_golden_master.py tests/test_sizer.py -v`
Expected: PASS (identical).

- [ ] **Step 7: Commit**
```bash
git add live_bot/sizer.py tests/test_sizer.py live_bot/paper_bot.py && git commit -m "refactor: extract position sizing into EqualWeightSizer (byte-identical)"
```

---

### Task 4: Config module + validation (paper-default, live-locked)

**Files:**
- Create: `live_bot/botconfig.py`
- Test: `tests/test_config.py`
- Modify: `live_bot/paper_bot.py` (read config at top of `cycle()`)

- [ ] **Step 1: Write the failing test**
```python
# tests/test_config.py
import pytest
from live_bot.botconfig import load_config, ConfigError

def test_defaults_are_paper_safe(monkeypatch):
    monkeypatch.delenv("LIVE", raising=False)
    cfg = load_config()
    assert cfg.live is False and cfg.dry_run is True and cfg.halt is False

def test_live_without_keys_refuses(monkeypatch):
    monkeypatch.setenv("LIVE", "true")
    monkeypatch.delenv("BINANCE_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_config()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `botconfig.py`**
```python
# live_bot/botconfig.py
import os
from dataclasses import dataclass

class ConfigError(Exception): ...

def _b(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")

@dataclass
class BotConfig:
    live: bool; dry_run: bool; halt: bool

def load_config() -> BotConfig:
    live = _b("LIVE", False)
    cfg = BotConfig(live=live, dry_run=_b("DRY_RUN", True), halt=_b("HALT", False))
    if cfg.live:                               # 3-lock gate, part 1 (Phase 2 adds keys+broker)
        if not os.environ.get("BINANCE_KEY") or not os.environ.get("BINANCE_SECRET"):
            raise ConfigError("LIVE=true but BINANCE_KEY/SECRET missing — refusing to run")
    return cfg
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Wire into `cycle()`** — first lines of `cycle()`:
```python
from botconfig import load_config
CFG = load_config()
if CFG.halt:
    print("HALT flag set — doing nothing this run."); return
```

- [ ] **Step 6: Golden master (HALT unset → identical)**

Run: `pytest tests/ -v`
Expected: PASS (all).

- [ ] **Step 7: Commit**
```bash
git add live_bot/botconfig.py tests/test_config.py live_bot/paper_bot.py && git commit -m "feat: config module + validation + HALT kill-switch (paper-default)"
```

---

### Task 5: Strat-neutral guards — bad-tick gate, data-quality, atomic write

**Files:**
- Create: `live_bot/guards.py`
- Test: `tests/test_guards.py`
- Modify: `live_bot/paper_bot.py` (bar read at L427; state write; fetch handling)

- [ ] **Step 1: Write the failing tests**
```python
# tests/test_guards.py
from live_bot.guards import bad_tick_ok, data_quality_ok

def test_bad_tick_rejects_spike():
    # a bar >25% off the prior close with no reason = bad tick
    assert bad_tick_ok(prev_close=100.0, price=100.5) is True
    assert bad_tick_ok(prev_close=100.0, price=140.0) is False   # +40% lone spike
    assert bad_tick_ok(prev_close=100.0, price=60.0) is False    # -40%

def test_data_quality_rejects_short_or_stale():
    import pandas as pd
    good = pd.DataFrame({"c": range(300)})
    assert data_quality_ok(good, min_bars=250) is True
    short = pd.DataFrame({"c": range(10)})
    assert data_quality_ok(short, min_bars=250) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_guards.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `guards.py`**
```python
# live_bot/guards.py
import json, os, tempfile

def bad_tick_ok(prev_close: float, price: float, max_dev: float = 0.25) -> bool:
    """False if price deviates > max_dev from prior close (likely a bad intraday tick — the RCAT $14.98 bug)."""
    if prev_close <= 0: return True
    return abs(price / prev_close - 1) <= max_dev

def data_quality_ok(df, min_bars: int = 250) -> bool:
    """False if the fetched frame is too short/empty to compute MA200 etc. → skip, don't trade on bad data."""
    return df is not None and len(df) >= min_bars

def atomic_write_json(path, obj) -> None:
    """Write to a temp file then rename — a crash mid-write can't corrupt the state file."""
    d = os.path.dirname(str(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_guards.py -v`
Expected: PASS.

- [ ] **Step 5: Wire guards into `paper_bot.py`**

- After `df=fetch(c)` per coin, add: `if not data_quality_ok(df, MA_LEN): print(f"{c}: data-quality skip"); [totals[a].__iadd__... ]; continue` (skip the coin, keep its cash — mirror the existing fetch-fail branch).
- In the bar read (L427 area), before computing signals, gate the price: `if not bad_tick_ok(df.c.iloc[i-1], price): print(f"{c}: bad-tick skip {price}"); continue` (skip acting on a glitch bar).
- Replace the state write (`spath(a).write_text(json.dumps(states[a],indent=2))` at L420) with `atomic_write_json(spath(a), states[a])`.

- [ ] **Step 6: Golden master — clean historical data has no bad ticks/short frames → identical**

Run: `pytest tests/ -v`
Expected: PASS (all, including golden master byte-identical — guards are invisible on clean data).

- [ ] **Step 7: Commit**
```bash
git add live_bot/guards.py tests/test_guards.py live_bot/paper_bot.py && git commit -m "feat: strat-neutral guards (bad-tick gate, data-quality skip, atomic state write)"
```

---

### Task 6: Order-classification scaffold (sets up Phase 2, no behavior change)

**Files:**
- Modify: `live_bot/broker.py` (add `risk_side` to `fill`)
- Test: `tests/test_broker.py` (extend)

- [ ] **Step 1: Extend the test**
```python
def test_fill_tags_risk_side():
    from live_bot.broker import PaperBroker
    b = PaperBroker()
    assert b.fill("BUY", 100.0, 1.0).risk_side == "increasing"
    assert b.fill("SELL", 100.0, 1.0).risk_side == "reducing"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_broker.py::test_fill_tags_risk_side -v`
Expected: FAIL — no `risk_side`.

- [ ] **Step 3: Add `risk_side` to `FillReport` + set it in `PaperBroker.fill`**

Add field `risk_side: str = ""` to `FillReport`; in `fill`, set `risk_side="increasing"` for BUY, `"reducing"` for SELL. (Phase 2's guards use this so no guard ever blocks a `reducing` order.)

- [ ] **Step 4: Run tests + golden master**

Run: `pytest tests/ -v`
Expected: PASS (all; golden master unaffected — it doesn't read `risk_side`).

- [ ] **Step 5: Commit**
```bash
git add live_bot/broker.py tests/test_broker.py && git commit -m "feat: tag fills risk_side (increasing/reducing) — scaffolds Phase-2 exit-always-executes rule"
```

---

## Definition of done (Phase 1)
- All tests green; golden master byte-identical (paper behavior unchanged).
- `paper_bot.py` no longer contains inline fill/sizing math — it calls `BROKER` + `SIZER`.
- Config/HALT/guards in place; `requirements.txt` pinned.
- LiveBroker + real-money layer explicitly NOT present (Phase 2).
- The live daily routine keeps running paper exactly as before.

## Self-review notes
- Spec coverage: this plan covers spec sections "Architecture" (Broker/Sizer), the strat-neutral subset of "Failure modes & guards" (bad-tick, data-quality, atomic write, closed-bar already at i=-2, HALT, config-validation), and "Migration / correctness" (golden master). Live-only guards (idempotency, reconcile, staleness collar, execution ledger, HALT state machine, resting stops) are explicitly deferred to the Phase-2 plan — NOT gaps.
- Golden-master feasibility risk: capturing baseline requires monkeypatching `fetch` + redirecting `HERE`/state paths; if the bot hardcodes paths in a way that resists redirection, Task 0 Step 3 must first parameterize those (add a tiny task). Flagged for the executor.
