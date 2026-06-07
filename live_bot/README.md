# Paper-trading bot — validated trend basket

Forward-tests the validated strategy with **no real money**: Donchian 55/20 + 200-MA filter,
long-only, ATR stop, ATR-risk sizing, ~20-coin Binance basket (each coin = equal-capital sub-account).

## Files
- `paper_bot.py` — runs one trading cycle (fetch → signals → paper fills → save/log).
- `status.py` — snapshot of what the bot sees (regime, breakout distance, open positions).
- `state.json` — persisted paper account (auto-created; gitignored).
- `equity_log.csv`, `trades.csv` — running logs (gitignored).

## Run
```
python paper_bot.py          # one cycle (run this every 4h)
python paper_bot.py --loop   # run forever, cycles every 4h
python status.py             # see current signals + equity
```
No API key needed (public Binance data, read-only). It never places real orders.

## Schedule on the Azure VPS (Windows) — one-click
On the VPS, inside this folder:
1. `setup.bat`           — installs Python libs + runs a test cycle.
2. `register_task.bat`   — (Run as administrator) schedules it every 4h via Task Scheduler.
That's it. To watch: `python status.py`. Logs: `bot_run.log`, `equity_log.csv`, `trades.csv`.

Manual alternatives:
- `run.bat`      — one cycle (what the scheduler calls).
- `run_loop.bat` — runs forever, cycles every 4h (keep the window open instead of scheduling).
- Remove task:   `schtasks /Delete /TN QuantPaperBot /F`

## Config (top of paper_bot.py)
- `LEVERAGE = 1.0` → set `2.0` for the aggressive sweet spot (≈half-Kelly; ~2× CAGR & DD).
- `RISK_PCT`, `ATR_STOP`, `ENTRY/EXIT`, `MA_LEN`, `COINS` — all editable.

## How to read it
- **All coins below 200-MA → 0 positions, 100% cash.** Correct: the strategy sits out downtrends.
- It buys a coin when: closes above its 55-bar high **and** ADX>25 **and** price>200-MA.
- Exits on: close below 20-bar low **or** ATR(2.5) stop.

## Goal of this phase
Run 1-3 months. Confirm live behavior matches the backtest (entries/exits/equity path). If it
tracks, graduate to real capital (swap paper fills for CCXT live orders + API keys). **Do not skip
the paper phase.**
