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
BOOT_N = 1000                  # block-bootstrap resamples for survivor Sharpe/DD CIs
BOOT_CI = 0.90                 # central CI mass for the bootstrap Sharpe interval
BOOT_SEED = 20260724           # fixed seed: scoreboard must be reproducible run-to-run
NOISE_N = 5                    # seeded price-noise re-runs per survivor (median Sharpe reported); noise sigma = SLIPPAGE — perturb at execution-uncertainty scale, no separate tunable
CSCV_BLOCKS = 12               # contiguous time blocks for CSCV/PBO (must be even — pbo_cscv raises otherwise; C(12,6)=924 balanced splits)
BOOT_DD_Q = 0.95               # worst-plausible drawdown quantile; the maxdd_p95 column name mirrors this — change together
ML_MAX_ITER = 200              # HistGB boosting rounds — small on purpose; the ranker must survive validation, not win in-sample
ML_LEARNING_RATE = 0.05        # HistGB shrinkage
ML_MAX_DEPTH = 3               # shallow trees: interactions allowed, memorization not
ML_MIN_TRAIN_DAYS = 250        # skip a fold with less history; mirrors MIN_OBS_DAYS — change together
META_TIMEOUT_D = 10            # meta-label max holding days (sleeve-faithful timeout exit)
META_MIN_EVENTS = 200          # kill-test line: minimum OOS entries before precision means anything
META_MIN_TRAIN_EVENTS = 100    # skip a walk-forward fold trained on fewer labeled entries
META_Z = 1.645                 # one-sided 95% z: bet-subset precision must beat base significantly, not by luck
OOS_SPLIT = 0.6                # incumbent-book OOS split point, mirrors alphas.py
EVAL_WINDOW_START = "2023-01-01"  # universe additions must be listed before this date
SURVIVORSHIP_CAVEAT = (
    "Universe selected from currently-liquid Binance pairs listed before "
    f"{EVAL_WINDOW_START}; coins delisted before today are absent, so absolute "
    "levels are modestly inflated. Rankings between factors remain comparable."
)
