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

## Failure modes & guards (every "what if X" gets a named guard)
_None of these change the trading logic — they only fire on bad-data/bugs/failures. Proven strat-neutral by the byte-identical migration diff (any guard that alters a historical result = fix the guard, not the strat)._

| Failure mode | Guard | v1? | Strat-impact |
|---|---|---|---|
| Duplicate buy on a retried run | Idempotent `client_order_id` (#3) | v1 | none (only on retry) |
| Bot "forgets" it traded / state lost | Reconcile-or-halt (#4) | v1 | none (only on mismatch) |
| **Glitch tick → fake breakout (buy) or fake stop (sell)** | **Bad-tick gate:** reject a bar deviating wildly from prior close BEFORE it drives a signal (same idea as the RCAT $14.98 stock fix) | v1 | removes false signals (improves, doesn't break) |
| Intrabar whipsaw | **Closed-bar only:** act on last *finished* 4h bar (`i=-2`), never the forming bar — locked as a rule | v1 | none (already does this) |
| **Noisy signal → buy-then-instant-sell churn** | **Anti-flip:** block enter+exit of the same coin on the SAME bar from a tick. Designed to NOT delay a legit *next-bar* stop. | v1 | none on legit moves (tuned + diff-verified) |
| A bug tries to trade everything at once | **Per-run trade cap = ALERT, not hard-block** (set above the legit crash-rebound mass-entry max) → halts only on clearly-broken behavior | v1 | none (sits above legit max) |
| Sizing-math bug dumps account into one coin | **Max-notional-per-order/coin** sanity cap | v1.1 | none (above legit size) |
| Bad / stale / gapped price data | **Data-quality gate:** fetch-fail or stale/missing bars → skip run, trade nothing (DATA-UNAVAILABLE) | v1 | none (skips only on bad data) |
| Order call errors / times out | **Order-failure confirmation:** never assume — query by `client_order_id` for true state | v1 | none |
| Crash mid-state-write corrupts the book | **Atomic write:** temp file → rename | v1 | none |
| Cascading bug / flash crash drains equity | **Run drawdown breaker:** equity drop >X%/run → halt + alert | v1.1 | none (only on extreme) |
| **Price gaps BELOW stop between 4h runs** | **Soft-stop = (a)** 4h-check for paper/shadow (matches the validated backtest); **(b) resting exchange stop-orders = REQUIRED before the first real order** → 24/7 gap protection while the bot sleeps | (a) v1 / **(b) = go-live gate** | (a) matches backtest; (b) added only at real-money, never on paper |

**Soft-stop decision (locked):** (a) 4h soft-stop during paper/shadow — simple + keeps paper honest vs the 4h-bar backtest. **(b) resting stop orders at the exchange become mandatory the moment real money is funded** (listed in the go-live checklist below), so by the time a cent is live, stops are 24/7 — not dependent on the 4h cadence. Paper never runs (b) (it would diverge from the validated numbers).

## ⚠️ Adversarial audit findings (Fable + Codex — BOTH independently converged; all 5 are CORRECT and folded in)
A two-model adversarial pass found 5 holes the original guards missed or got wrong. Both auditors flagged the *same* five and the *same* #1 addition — high confidence. These OVERRIDE the naive guard wording above where they conflict.

1. **Idempotency as written is FACTUALLY WRONG for Binance market orders.** Binance only enforces `newClientOrderId` uniqueness among *open* orders — a market order fills in ms, frees the ID, and a re-send is accepted as a NEW order → double-buy. Also: hashing the ID off `run_timestamp` breaks under GH cron drift (a retried run gets a different time → different ID). **Fix:** key the ID off the **closed decision-bar timestamp** (not run time); idempotency is **client-side** — before placing, `fetch_order(clientOrderId)`; if it exists in ANY terminal state → skip. Never trust the exchange to reject the dup. Prove the real behavior on **Binance testnet** before live.
2. **Guards must NEVER block a risk-REDUCING order.** The staleness collar (#5), per-run cap, anti-flip, data-gate, min-notional skip, drawdown breaker, even HALT — as written they're symmetric and can refuse a STOP/EXIT during the exact crash they should fire in (rides the position to zero while the guard "congratulates itself"). **Fix:** every order is tagged `risk_increasing` (entry) or `risk_reducing` (exit/stop/flatten). **Entry-guards apply to entries only; exits always execute** (log the deviation, don't block). Only exchange/account sanity checks gate an exit.
3. **Resting stops contradict two guards + a stop-fill bricks the bot.** Resting stop orders (go-live req) = open orders → the open-orders-assertion (#6) aborts every run forever; and when a stop *fills* at 3am (normal!), reconcile sees balances≠JSON → sticky HALT, remaining positions unmanaged. **Fix:** state tracks the bot's own resting-stop order IDs; #6 allowlists exactly those; reconcile queries the exchange for fills matching the bot's OWN client/stop IDs since last run and **adopts** them as expected transitions (recognizing your own orders ≠ auto-repairing unknown corruption). Inject a fake stop-fill in shadow to test this path.
4. **The real commit point is `git push`, which races/rejects — atomic write protects the wrong thing.** Fill succeeds → runner evicted/timeout (or `cancel-in-progress: true` kills it) before push, OR push rejected non-fast-forward because another run pushed first → fill exists, origin doesn't know → next run reconciles stale JSON → sticky halt + naked position. **Fix:** GH Actions `concurrency: { group: bot, cancel-in-progress: FALSE }` (queue, never kill a run that may have ordered). Per-trade order: place → confirm fill → place resting stop → commit+push → only THEN next trade. Push reject = pull/rebase/retry, **never force, never proceed to another order while unpushed** (halt if push fails).
5. **Exits below min_notional strand you INSIDE a loser; dust + delisting compound it.** A position bleeds until notional < min_notional → the symmetric skip rejects the SELL → rides to zero. Round-trip dust accumulates; a delisted/halted coin fails `get_price` → the data-gate freezes (maybe the whole portfolio). **Fix:** exits sell the **entire free base balance** (rounded down), **exempt from the min-notional skip**; size entries so the stop-level notional stays > min_notional×1.5; reconcile **ignores sub-min-notional dust**; data-quality gate is **per-symbol**; a held coin that's unsellable → `dust_position` (excluded from sizing) + alert, plus a delist-watch that escalates to forced-exit, never silent-skip.

**🔑 THE #1 ADDITION (both auditors): an execution ledger + HALT recovery state machine.** Holes 1/3/4/5 all dead-end at "reconcile halts, no auto-repair, nothing after the alert" — under real money the dominant danger is **holding unmanaged positions while the bot refuses to run.** Required:
- **Append-only execution ledger:** every intended order → exchange ack → fill query → balance snapshot → state commit → git SHA, logged immutably. On startup, rebuild truth from **exchange + ledger** before trading.
- **Explicit HALT states** (not one boolean): `HALTED_NEEDS_RECONCILE`, `HALTED_MANUAL`, `FLATTEN_ONLY`.
- **Human-confirmed `adopt-exchange-state` recovery tool + written runbook:** pull exchange truth + the bot's own order history by client-ID, diff vs JSON, show the human exactly what changed, require explicit confirmation, write the adopted state, re-arm resting stops, clear the halt. Without this, "reconcile-or-halt" is a dead-man trap with a notification.
- **Fault-injection go-live gates** (shadow structurally CAN'T test these): fake stop-fill, killed run post-fill, rejected push, sub-min-notional exit, >1.5%-gap exit. Each must be exercised before real money.

## Real-money operational safety (beyond the in-code guards)
These are NOT code guards — they're the operational/key/ops layer. **The first one is the single most important real-money protection.**
- **🔑 API key = TRADE + READ only, WITHDRAW PERMANENTLY DISABLED.** Even if the key leaks (GitHub breach, log slip), an attacker **cannot move your funds out** — only trade within the account. This is non-negotiable. Also: no margin/futures permission on the key (reinforces spot-only at the key level).
- **Secrets in GitHub Actions encrypted secrets only** — never in code, never committed, never logged. The bot reads keys from env; a config-validator refuses to run `LIVE` if keys are absent/malformed.
- **IP allowlist the key** if feasible (GitHub Actions IPs rotate → may need a static-IP proxy, or accept no-IP-lock *because* withdraw is already disabled).
- **Dead-man's switch / heartbeat:** the bot pings each run; a separate monitor alerts if **no run in >X hours** (a silently-failed GitHub Action = you'd never know the bot stopped managing real positions).
- **Emergency-flatten procedure:** a tested, one-command `flatten.py` (sell all to stablecoin) + written manual steps, so "get me out NOW" doesn't require debugging at midnight.
- **Exposure caps (portfolio-level):** max % of account in one coin, max # open positions, max total deployed (idle-cash floor). Separate from per-order max-notional.
- **Config validation at startup:** refuse to run on a half-valid config (e.g. `LIVE=True` + no keys, or `DRY_RUN` unset) — fail loud, do nothing.
- **Dependency pinning:** `requirements.txt` with pinned versions (ccxt, pandas, numpy, requests) so an auto-update can't silently break or compromise the live bot.
- **Deliberate go-live friction:** flipping `LIVE=True` is a separate, dated commit (not bundled with code changes) + a cooldown — no same-impulse "let's go live right now."
- **Audit trail:** every decision + order appended to an immutable log (`trades.csv` + a decision log) for post-mortems.

## Shadow mode + go-live exit criteria (written NOW, not by vibes)
LiveBroker runs in dry-run alongside the paper bot for weeks, logging intended orders + measuring **real** tradeable price vs the 8bps assumption. Graduate to a live flip ONLY when ALL hold:
- ≥ N intended orders logged (enough to be meaningful — set N when first orders appear).
- 0 lot-size / min-notional rejections that weren't handled cleanly.
- 0 reconcile mismatches across the shadow window.
- Measured slippage+fee < the assumed 8bps (or paper P&L re-derated to the real number).
- AND the separate strategy gauntlet cleared (3-6mo paper + one regime change survived).

### Go-live checklist (all required BEFORE the first real order)
- [ ] **🔑 Binance API key created with WITHDRAW DISABLED + trade/read only + no margin** (the #1 protection).
- [ ] Keys in GitHub Actions secrets; config-validator refuses `LIVE` without valid keys.
- [ ] Dead-man's-switch heartbeat alert wired (alert if no run in >X h).
- [ ] `flatten.py` emergency exit tested in shadow.
- [ ] Exposure caps + dependency pin (`requirements.txt`) in place.
- [ ] Reconcile-or-halt built + tested (deliberately edit JSON → bot halts).
- [ ] **Execution ledger + HALT state machine + `adopt-exchange-state` recovery tool + runbook** (the #1 audit add).
- [ ] **Order classification wired** — exits/stops/flatten bypass entry-guards (audit #2).
- [ ] **Idempotency = decision-bar ID + query-before-place, proven on Binance testnet** (audit #1).
- [ ] **GH Actions `concurrency: cancel-in-progress: false` + push-or-halt** (audit #4).
- [ ] **Fault-injection gates passed** — fake stop-fill, killed-run-post-fill, rejected push, sub-min-notional exit, gap exit (audit).
- [ ] **(b) Resting exchange stop-orders wired** — 24/7 gap protection, replaces the 4h soft-stop for real money.
- [ ] Run drawdown breaker + max-notional cap (the v1.1 guards) in place.
- [ ] 3-lock live gate + HALT kill switch verified.
- [ ] Shadow exit criteria above all green.
- [ ] Strategy gauntlet cleared (3-6mo paper + a regime change survived).
- [ ] Start with a tiny real stake; scale only after live ≈ paper.

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

## YOUR real-money runbook (human steps, when the day comes)
1. Don't rush — only after the gauntlet clears (3-6mo paper + one regime flip survived live) AND shadow passed.
2. Fund small — barbell money only; a tiny slice for the first real weeks.
3. THB → Binance TH (Gulf Binance): KYC, deposit THB → convert to USDT.
4. 🔑 API key WITHDRAW DISABLED, trade+read only, no margin (#1 rule).
5. Keys → GitHub Actions secrets (BINANCE_KEY/BINANCE_SECRET), never in code.
6. Telegram (BotFather) token+chat id → heartbeat + halt alerts to phone.
7. Shadow mode weeks — confirm fills/slippage match, 0 reconcile mismatches.
8. Flip LIVE deliberately — separate dated commit (LIVE=true, DRY_RUN=false) after go-live checklist all green.
9. Babysit daily early — heartbeat + positions match.
10. Scale slowly — add money only after live ≈ paper holds.
11. Off-switches: HALT flag → flatten.py → delete API key (nuclear).
