# Broker Adapter — Design Spec (2026-06-12)

_Separates "decide" from "execute" in the crypto bot so the same strategy runs against a simulated (paper) broker or a real (Binance spot) broker, swappable by config. Reviewed by Fable (architecture pass) — its 7-item punch-list is folded in. **This builds infrastructure only; no real money is funded until the validation gauntlet clears (3-6mo paper + survive one bull↔bear regime change live).**_

## Goal & non-goals
**Goal:** refactor `live_bot/paper_bot.py` so execution lives behind a clean interface, with a money-safe path to real Binance-spot trading later. Default behaviour stays byte-for-byte identical to today's paper bot.

**Non-goals (v1):**
- Going live / funding real money (separate, later, gated on the gauntlet).
- Leverage / margin / perps (spot-only; this is what gives automatic negative-balance protection).
- Multi-exchange abstraction (Binance-shaped is fine; CCXT is just the client lib).
- Maker/limit orders (market only — breakout strategy needs the fill).
- Auto-reconciliation/repair, partial-fill management, full OMS (YAGNI for a 20-coin / few-trades-a-week book).

## Decisions (Fable-validated)
| Choice | Verdict | Why |
|---|---|---|
| Spot, no leverage (1x) | ✅ | Automatic negative-balance protection (can't owe more than deposited); leverage is Sharpe-invariant per our own research. |
| Binance spot via CCXT | ✅ | Licensed Thai route (Gulf Binance), liquid, compliance-friendly. CCXT = client lib, not an agnostic-design goal. |
| Market orders | ✅ | Breakout entry needs the fill; maker would miss breakouts + adverse-select. Slippage test proved edge survives to ~80bps/side. |
| Leverage = never in v1, no stub | ✅ | A present-but-off leverage path is a footgun. LiveBroker has NO leverage concept at all. If ever wanted → new Broker impl + fresh review. |
| "More exposure without leverage" = deploy idle cash via sizing | ✅ | Spot caps at own cash; bigger sizing/concentration is a sizing choice (concentration risk), not leverage. Seam kept, impls deferred. |

## Architecture — two swappable abstractions

### ① `Sizer` — decides HOW MUCH to allocate per signal
```
Sizer.notional_for(signal, free_quote_balance) -> usd_amount
```
- Sizes off **free** quote balance (open positions consume it on spot).
- v1 ships ONE impl: `EqualWeightSizer` (current 1/N behaviour, unchanged).
- The interface is the "adaptable" seam: `ConcentratedSizer` / `RiskPctSizer` can drop in later **once the paper gauntlet validates a sizing change** — NOT pre-built now.
- No `LeveragedSizer`, not even stubbed (deleted per Fable).

### ② `Broker` — EXECUTES the order (Binance-shaped, venue shows through honestly)
```
Broker.get_price(symbol) -> float
Broker.get_balances() -> {asset: free_amount}
Broker.get_positions() -> {symbol: {units, entry, stop, ...}}
Broker.get_open_orders(symbol=None) -> list          # used as an assertion (see safety)
Broker.get_symbol_filters(symbol) -> {step_size, min_notional, ...}   # LiveBroker; PaperBroker returns permissive
Broker.place_market_order(symbol, side, notional, client_order_id, decision_price) -> FillReport
```

**`FillReport`** (the one return shape both brokers produce):
```
{ order_id, client_order_id, symbol, side,
  filled_qty, avg_fill_price, fee_paid, fee_asset, status }   # status: filled | rejected | skipped
```
State updates use the **actual** filled qty/price/fee — never the intended values.

**`PaperBroker`** — extracts today's inline sim:
- Same cash/units bookkeeping currently at `paper_bot.py` ~L358-420, same 8bps cost, same close-based fills.
- Synthesizes a `FillReport` of the same shape so calling code has ONE path.
- Holds the 1x/2x/3x leverage **as a paper-account simulation property** (constructor arg) — leverage stays a paper-only comparison, never touches the live path.

**`LiveBroker`** — CCXT → Binance spot:
- Wraps `fetch_ticker` / `fetch_balance` / `fetch_open_orders` / `create_market_order` with `newClientOrderId`.
- Has **no leverage parameter anywhere** in its signature (physical incapability > config flag).
- Quantizes qty down to `step_size`; rejects/skips orders under `min_notional` (deterministic, logged).
- Lives behind the safety gates below; ships in **dry-run shadow** mode (logs intended orders, sends nothing).

### Data flow
```
strategy detects signal → Sizer.notional_for(...) → Broker.place_market_order(...) → FillReport → state update (actual fill)
```
Strategy logic untouched; sizing + execution both pluggable. The bot picks its broker/sizer from one config block.

## Safety invariants (mandatory; built during shadow, enforced before first real order)
1. **3-lock live gate:** a real order requires `LIVE=True` AND API keys present AND `DRY_RUN=False`. Any missing → log-only.
2. **Spot-only guard:** any notional > free quote balance is rejected pre-flight (local clear log beats a Binance "insufficient balance"). LiveBroker can't express leverage anyway.
3. **Idempotent `client_order_id`** = deterministic hash of (run_timestamp, symbol, side, signal_type). A retried 4h run can't double-buy (Binance rejects the duplicate id).
4. **Reconcile-or-halt** (run start): diff `get_balances()`/`get_positions()` vs the JSON state, tolerance ~1% (fee dust). Match → proceed. Mismatch → **abort run, Telegram alert, place nothing.** No auto-repair. *Must exist before the first real order; tested during shadow by deliberately editing the JSON.*
5. **Price-staleness collar:** `place_market_order` re-fetches the ticker; if it deviates >1.5% from `decision_price` → refuse (catches flash moves + stale-data bugs).
6. **Open-orders assertion:** at run start, `get_open_orders()` must be empty; non-empty → abort (free corruption detector).
7. **`HALT` kill switch:** an env/file flag checked first thing each run → bot does nothing. The phone-at-midnight off button that isn't "delete the API key."

## Shadow mode + go-live exit criteria (written NOW, not by vibes)
LiveBroker runs in dry-run alongside the paper bot for weeks, logging intended orders + measuring **real** tradeable price vs the 8bps assumption. Graduate to a live flip ONLY when ALL hold:
- ≥ N intended orders logged (enough to be meaningful — set N when first orders appear).
- 0 lot-size / min-notional rejections that weren't handled cleanly.
- 0 reconcile mismatches across the shadow window.
- Measured slippage+fee < the assumed 8bps (or paper P&L re-derated to the real number).
- AND the separate strategy gauntlet cleared (3-6mo paper + one regime change survived).

## Migration / correctness
- Pure-refactor checkpoint: after extracting `PaperBroker`, the bot's output (state JSON, equity CSVs, data.json) must be **identical** to pre-refactor on the same input → diff-verified before anything else.
- Default config = `EqualWeightSizer` + `PaperBroker` → nothing changes until a knob is deliberately turned.

## Files (anticipated)
- `live_bot/broker.py` — `Broker` interface + `FillReport` + `PaperBroker` + `LiveBroker`.
- `live_bot/sizer.py` — `Sizer` interface + `EqualWeightSizer`.
- `live_bot/paper_bot.py` — strategy logic kept; inline fill math replaced by `sizer`+`broker` calls; safety gates wired.
- Config block (env-driven): `LIVE`, `DRY_RUN`, `HALT`, broker/sizer selection, `live_mirror` account = 1x only.

## Out of scope / future (seams left, not built)
- `ConcentratedSizer` / `RiskPctSizer` (deploy-idle-cash lever) — add after paper validates a sizing change.
- Real Binance API keys + funding — after shadow + gauntlet pass.
- Any leverage/margin — would be a new Broker impl + fresh review, never a flag.
