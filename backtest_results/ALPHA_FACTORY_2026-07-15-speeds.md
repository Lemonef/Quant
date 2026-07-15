# Alpha Factory scoreboard — 2026-07-15

> Universe selected from currently-liquid Binance pairs listed before 2023-01-01; coins delisted before today are absent, so absolute levels are modestly inflated. Rankings between factors remain comparable.

Config: `{'BORROW_ANNUAL': 0.1, 'DECAY_MIN_RATIO': 0.25, 'DPY': 365, 'DSR_MIN_PROB': 0.5, 'EMBARGO_DAYS': 10, 'EVAL_WINDOW_START': '2023-01-01', 'FDR_Q': 0.1, 'HORIZONS': (1, 5, 20), 'K_FRAC': 0.2, 'MIN_OBS_DAYS': 250, 'N_FOLDS': 4, 'OOS_SPLIT': 0.6, 'REBALANCE_PERIODS': (1, 5, 20), 'SLIPPAGE': 0.0005, 'TAKER_FEE': 0.0006}`
Factors tested: 306 · SURVIVED: 0 · REJECTED: 306

## SURVIVED (sorted by deflated-Sharpe probability)

| factor | family | rebal | prov | IC1 | ICIR1 | LS Sharpe | folds | DSRp | maxCorr | ΔSharpe | ΔDD | IMPROVES BOOK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## REJECTED — count by reason

-  196 × failed FDR
-  110 × negative OOS fold

Full per-factor table: `ALPHA_FACTORY_2026-07-15.csv`
