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
- Create `live_bot/guards.py` — `data_quality_ok()`, `atomic_write_json()`. (`bad_tick_ok` deferred to Phase 2 — not strat-neutral on closed 4h bars.)
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

def frozen_fetch(coin, limit=400):               # honor `limit` — write_webdata calls fetch(coin, limit=...)
    df = pd.read_csv(ROOT / "backtest" / "data" / f"{coin}_4h.csv")
    df = df.rename(columns={"close":"c","high":"h","low":"l","open":"o","volume":"v"})
    df["t"] = pd.to_datetime(df[df.columns[0]], unit="ms", utc=True)
    return df.set_index("t").tail(limit)

def isolate(pb, out_dir):
    """Task-0.5 isolation: make a capture run touch NOTHING real (no live ledger, no network, no Telegram, deterministic time)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pb.fetch = frozen_fetch                       # deterministic input, honors limit
    pb.fetch_funding = lambda sym, limit=500: []  # B3: no live HTTP inside write_webdata
    pb.now = lambda: "2026-01-01T00:00:00+00:00"  # B1: freeze time → stable last_run + equity/csv rows + data.json.updated
    pb.TG_TOKEN = ""; pb.TG_CHAT = ""             # B3: never send a real Telegram from a test
    pb.HERE = out_dir                             # redirects spath/epath/web (call-time lookup)
    pb.REGLOG = out_dir / "regime_log.csv"        # B2: these are IMPORT-TIME constants — must reassign
    pb.TRADELOG = out_dir / "trades.csv"          # else the test appends FAKE trades to the real live ledger
    pb.TRADEDETAIL = out_dir / "trades_detail.csv"

def run_capture(out_dir):
    import importlib, sys
    if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
    if str(ROOT / "live_bot") not in sys.path: sys.path.insert(0, str(ROOT / "live_bot"))
    import paper_bot as pb
    importlib.reload(pb)
    isolate(pb, out_dir)
    pb.cycle()
    snap = {}
    for p in sorted(out_dir.glob("state_*.json")):
        snap[p.name] = json.loads(p.read_text())
    return snap                                    # data.json is DE-SCOPED from the golden master (see note)

if __name__ == "__main__":
    base = FIX / "baseline_state"
    if base.exists(): shutil.rmtree(base)
    snap = run_capture(base)
    (FIX / "baseline_snapshot.json").write_text(json.dumps(snap, indent=2, sort_keys=True))
    print(f"baseline captured: {len(snap)} state files")
```

Run: `python tests/capture_baseline.py`
Expected: prints "baseline captured: **9 state files**" (`trend/flush/crashreb × 1x/2x/3x`; blend/bookv2/divblend are DERIVED, no state file), writes `tests/fixtures/baseline_snapshot.json`.

**De-scoped from the golden master:** `data.json` is NOT diffed — it embeds `updated`, funding-source, and live-derived tabs that can't be cleanly frozen. The state files (positions/cash/equity) are the accounting truth we protect. `data.json` correctness is a separate Phase-2 shadow concern.

**Package layout (prevents ModuleNotFoundError):** also create empty `tests/__init__.py` and `live_bot/__init__.py`, and a root `conftest.py`:
```python
# conftest.py (repo root)
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "live_bot"):
    if str(p) not in sys.path: sys.path.insert(0, str(p))
for e in ("LIVE", "HALT", "DRY_RUN", "TG_TOKEN", "TG_CHAT"):   # clean env so a dev's shell can't skew tests
    os.environ.pop(e, None)
```

- [ ] **Step 4: Golden-master test that re-runs and diffs**

Create `tests/test_golden_master.py`:
```python
import json
from pathlib import Path
from tests.capture_baseline import run_capture, FIX

def test_outputs_identical_to_baseline(tmp_path):
    baseline = json.loads((FIX / "baseline_snapshot.json").read_text())
    fresh = run_capture(tmp_path / "state")
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
    def __init__(self, cost: float):        # REQUIRED — no default (live COST=0.0015, not 0.0008; a wrong default is a silent footgun)
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

### Task 5: Strat-neutral guards — data-quality skip + atomic write ONLY

**⚠️ Bad-tick price gate is DEFERRED to Phase 2 (Fable design flag).** The 25% gate is NOT strat-neutral here: flush trades >8% dumps, crashreb >5% BTC bars, and real 4h alt capitulation bars exceed ±25% — a close-to-close 25% gate would VETO the exact bars flush/crashreb monetize. The RCAT-style bad-tick gate belongs on the *live intraday fetch* (Phase 2), not on closed 4h bars. Phase 1 ships only the two genuinely strat-neutral guards below.

**Files:**
- Create: `live_bot/guards.py`
- Test: `tests/test_guards.py`
- Modify: `live_bot/paper_bot.py` (per-coin fetch handling ~L421-425; state write ~L420)

- [ ] **Step 1: Write the failing tests**
```python
# tests/test_guards.py
import pandas as pd, json
from live_bot.guards import data_quality_ok, atomic_write_json

def test_data_quality_rejects_short_or_empty():
    assert data_quality_ok(pd.DataFrame({"c": range(300)}), min_bars=250) is True
    assert data_quality_ok(pd.DataFrame({"c": range(10)}), min_bars=250) is False
    assert data_quality_ok(None, min_bars=250) is False

def test_atomic_write_is_all_or_nothing(tmp_path):
    p = tmp_path / "s.json"
    atomic_write_json(p, {"a": 1})
    assert json.loads(p.read_text()) == {"a": 1}
    assert not list(tmp_path.glob("*.tmp"))   # no temp litter left
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_guards.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `guards.py`**
```python
# live_bot/guards.py
import json, os, tempfile

def data_quality_ok(df, min_bars: int = 250) -> bool:
    """False if the fetched frame is None/too short to compute MA200 etc. → skip the coin, don't trade on bad data."""
    return df is not None and len(df) >= min_bars

def atomic_write_json(path, obj) -> None:
    """Write to a temp file then rename — a crash mid-write can't corrupt the state file."""
    d = os.path.dirname(str(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)
```
(No `bad_tick_ok` — deferred to Phase 2 as an intraday-read guard.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_guards.py -v`
Expected: PASS.

- [ ] **Step 5: Wire the data-quality skip — MUST mirror the existing fetch-fail branch exactly (keep cash in totals)**

The existing fetch-fail branch (L421-425) does: `print fail; for a in accts: totals[a]+=states[a]["coins"][c]["cash"]; continue`. The data-quality skip must do the SAME accounting (add each account's cash for this coin, then `continue`) — a bare `continue` would drop the coin's value from totals = a real equity bug. After `atr,adx,ma,donHi,donLo=indicators(df); i=len(df)-2` succeeds, guard the frame right after `df=fetch(c)`:
```python
        if not data_quality_ok(df, MA_LEN):
            print(f"{c}: data-quality skip (short/empty frame)")
            for a in accts: totals[a]+=states[a]["coins"][c]["cash"]
            continue
```
Then replace the state write (`spath(a).write_text(json.dumps(states[a],indent=2))` at L420) with `atomic_write_json(spath(a), states[a])`.

- [ ] **Step 6: Golden master — clean fixtures are all ≥400 bars → skip never fires → identical**

Run: `pytest tests/ -v`
Expected: PASS (all; golden master byte-identical — data-quality skip is invisible when frames are healthy, atomic write produces the same bytes).

- [ ] **Step 7: Commit**
```bash
git add live_bot/guards.py tests/test_guards.py live_bot/paper_bot.py && git commit -m "feat: strat-neutral guards (data-quality skip mirrors fetch-fail, atomic state write); bad-tick gate deferred to Phase 2"
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
    b = PaperBroker(cost=0.0008)
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

## Self-review notes (Fable plan-review folded in — 6 blockers fixed)
- Spec coverage: covers "Architecture" (Broker/Sizer), the genuinely strat-neutral subset of "Failure modes & guards" (data-quality skip, atomic write, closed-bar already at i=-2, HALT, config-validation), and "Migration / correctness" (golden master on the 9 state files). DEFERRED to Phase 2 (NOT gaps): the bad-tick price gate (not strat-neutral on closed 4h bars — belongs on the live intraday read), idempotency, reconcile-or-halt, staleness collar, execution ledger, HALT state machine, resting stops, `data.json` fidelity.
- **Fable-review blockers resolved:** B1 freeze `now()` (kills the `last_run` nondeterminism), B2 reassign import-time `REGLOG`/`TRADELOG`/`TRADEDETAIL` in `isolate()` (else tests corrupt the live ledger), B3 stub `fetch_funding` + blank `TG_TOKEN/CHAT` (no live HTTP/Telegram from tests), B4 `__init__.py` + root `conftest.py` with sys.path + env-clear, B5 de-scope `data.json` from the golden master + `frozen_fetch(limit=...)`, B6 data-quality skip mirrors the fetch-fail cash accounting (no equity drop) + bad-tick gate removed from Phase 1.
- Wording: "byte-identical" = 8-decimal-identical (the `norm()` rounding absorbs ≤1-ulp FP from re-ordered arithmetic); a 1-ulp diff is NOT a regression.
- Expected state-file count = **9** (trend/flush/crashreb × 1x/2x/3x); blends are derived.
