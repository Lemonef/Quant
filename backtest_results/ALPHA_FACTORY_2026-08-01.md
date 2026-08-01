# Alpha Factory scoreboard — 2026-08-01

> Universe selected from currently-liquid Binance pairs listed before 2023-01-01; coins delisted before today are absent, so absolute levels are modestly inflated. Rankings between factors remain comparable.

Config: `{'BOOT_CI': 0.9, 'BOOT_DD_Q': 0.95, 'BOOT_N': 1000, 'BOOT_SEED': 20260724, 'BORROW_ANNUAL': 0.1, 'CSCV_BLOCKS': 12, 'DECAY_MIN_RATIO': 0.25, 'DPY': 365, 'DSR_MIN_PROB': 0.5, 'EMBARGO_DAYS': 10, 'EVAL_WINDOW_START': '2023-01-01', 'FDR_Q': 0.1, 'HORIZONS': (1, 5, 20), 'K_FRAC': 0.2, 'MIN_OBS_DAYS': 250, 'ML_LEARNING_RATE': 0.05, 'ML_MAX_DEPTH': 3, 'ML_MAX_ITER': 200, 'ML_MIN_TRAIN_DAYS': 250, 'NOISE_N': 5, 'N_FOLDS': 4, 'OOS_SPLIT': 0.6, 'REBALANCE_PERIODS': (1, 5, 20), 'SLIPPAGE': 0.0005, 'TAKER_FEE': 0.0006}`
Factors tested: 324 · SURVIVED: 0 · REJECTED: 324
Run-level PBO (CSCV, 12 blocks): 0.24 — probability the best in-sample pick underperforms the OOS median
Hansen SPA p (best row vs zero, whole search): 0.298

## SURVIVED (sorted by deflated-Sharpe probability)

| factor | family | rebal | prov | IC1 | ICIR1 | LS Sharpe | Sharpe CI | DD p95 | folds | DSRp | maxCorr | ΔSharpe | ΔDD | IMPROVES BOOK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## REJECTED — count by reason

-  212 × failed FDR
-  112 × negative OOS fold

Full per-factor table: `ALPHA_FACTORY_2026-08-01.csv`
