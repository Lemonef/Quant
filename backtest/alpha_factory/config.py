"""Alpha Factory configuration — the ONLY place tunables live (no magic numbers in modules)."""
HORIZONS = (1, 5, 20)          # forward-return horizons (days) for IC/decay
REBALANCE_PERIODS = HORIZONS   # each factor judged at each horizon's natural trading speed; single source of truth is HORIZONS (a factor traded every R days captures the R-day horizon)
N_FOLDS = 4                    # purged walk-forward OOS folds
EMBARGO_DAYS = 10              # gap dropped between folds (leak purge)
FDR_Q = 0.10                   # Benjamini-Hochberg false-discovery rate
K_FRAC = 0.2                   # long/short top/bottom fraction of universe (K = max(2, int(n*K_FRAC)))
TAKER_FEE = 0.0006             # per side, mirrors alphas.py xsmom cost
SLIPPAGE = 0.0005              # per side haircut, mirrors engine.SLIP
BORROW_ANNUAL = 0.10           # short-leg borrow cost per year, mirrors alphas.py
DPY = 365                      # crypto trades every day
DECAY_MIN_RATIO = 0.25         # decay gate: same-sign IC at the next-higher horizon >= this fraction of the traded-horizon IC
DSR_MIN_PROB = 0.5             # deflated-Sharpe probability floor
MIN_OBS_DAYS = 250             # min daily observations for a factor to be judged
OOS_SPLIT = 0.6                # incumbent-book OOS split point, mirrors alphas.py
EVAL_WINDOW_START = "2023-01-01"  # universe additions must be listed before this date
SURVIVORSHIP_CAVEAT = (
    "Universe selected from currently-liquid Binance pairs listed before "
    f"{EVAL_WINDOW_START}; coins delisted before today are absent, so absolute "
    "levels are modestly inflated. Rankings between factors remain comparable."
)
