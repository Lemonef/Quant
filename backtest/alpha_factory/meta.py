"""Perfect-model Track A — meta-labeling (Lopez de Prado AFML ch.3): learn WHEN
an incumbent sleeve's entries win, bet/no-bet on top of the existing edge. No new
turnover class is created — the sleeve trades anyway; the model only vetoes.
First target: the rsi2dip sleeve (dip-in-uptrend, behavior-mechanism class).
Entry event = (close > MA200) & (RSI2 < RSI_ENTRY) transition day t, executed
t+1 open per the sleeve; exit = RSI2 > RSI_EXIT or META_TIMEOUT_D days. Labels
are the SLEEVE-FAITHFUL net outcome, not synthetic barriers, so the kill test
answers the deployed question."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from . import ops

RSI_ENTRY = 10     # mirrors bench.incumbent_sleeves rsi2dip entry (r2 < 10) — change together
RSI_EXIT = 50      # mirrors bench.incumbent_sleeves rsi2dip exit (r2 > 50) — change together


def _signals(panel):
    ma200 = panel.close.rolling(200).mean()
    r2 = ops.rsi(panel.close, 2)
    return ma200, r2


def entry_events(panel):
    """[(entry_day, coin)] where the dip-in-uptrend condition TURNS ON."""
    ma200, r2 = _signals(panel)
    cond = (panel.close > ma200) & (r2 < RSI_ENTRY)
    fresh = cond & ~cond.shift(1).fillna(False)
    out = []
    for coin in fresh.columns:
        for t in fresh.index[fresh[coin]]:
            out.append((t, coin))
    out.sort(key=lambda e: (e[0], e[1]))
    return out


def label_events(events, panel, cfg):
    """Sleeve-faithful outcome per event: enter next open, exit at the open after
    RSI2 > RSI_EXIT, or after META_TIMEOUT_D days. ret is net of fee+slip both ways."""
    _, r2 = _signals(panel)
    cost = 2 * (cfg.TAKER_FEE + cfg.SLIPPAGE)
    idx = panel.close.index
    rows = []
    for t, coin in events:
        i = idx.get_loc(t)
        i_in = i + 1
        if i_in >= len(idx):
            rows.append(dict(ret=np.nan, win=False, hold_days=0)); continue
        i_stop = min(i_in + cfg.META_TIMEOUT_D, len(idx) - 1)
        i_out = i_stop
        for j in range(i_in, i_stop):
            if r2.iloc[j][coin] > RSI_EXIT:
                i_out = min(j + 1, len(idx) - 1)   # exit executed the open AFTER the signal
                break
        px_in, px_out = panel.open.iloc[i_in][coin], panel.open.iloc[i_out][coin]
        ret = px_out / px_in - 1 - cost
        rows.append(dict(ret=ret, win=bool(ret > 0), hold_days=i_out - i_in))
    return pd.DataFrame(rows, index=pd.MultiIndex.from_tuples(events, names=["day", "coin"]))


def event_features(events, panel):
    """State at the entry-decision close t (all inputs use data <= t)."""
    ma200, r2 = _signals(panel)
    vol20 = panel.ret.rolling(20).std()
    mom28 = panel.close.pct_change(28)
    dd63 = panel.close / panel.close.rolling(63).max() - 1
    fund3 = panel.funding.reindex(columns=panel.close.columns).rolling(3).mean()
    momrank = mom28.rank(axis=1, pct=True)
    anchor = "BTCUSDT" if "BTCUSDT" in panel.close.columns else panel.close.columns[0]
    anchor_up = (panel.close[anchor] > ma200[anchor]).astype(float)
    rows = []
    for t, coin in events:
        rows.append(dict(
            r2=r2.at[t, coin],
            dist_ma200=panel.close.at[t, coin] / ma200.at[t, coin] - 1,
            vol20=vol20.at[t, coin],
            mom28=mom28.at[t, coin],
            momrank=momrank.at[t, coin],
            dd63=dd63.at[t, coin],
            fund3=(fund3.at[t, coin] if coin in fund3.columns else 0.0),
            anchor_up=anchor_up.at[t],
        ))
    return pd.DataFrame(rows, index=pd.MultiIndex.from_tuples(events, names=["day", "coin"]))


def kill_test(panel, cfg):
    """Expanding walk-forward over event time. Preregistered pass line: the bet
    subset's OOS precision beats the base win rate by >= META_Z standard errors
    (one-sided; raw '>' passes on noise ~half the time) AND expectancy improves,
    on >= META_MIN_EVENTS OOS events. Pure noise must fail this."""
    events = entry_events(panel)
    lab = label_events(events, panel, cfg)
    X = event_features(events, panel)
    ok = lab.ret.notna()
    lab, X = lab[ok], X[ok.to_numpy()]
    n = len(lab)
    days = lab.index.get_level_values(0)
    folds = np.array_split(np.arange(n), cfg.N_FOLDS)
    pred = np.full(n, np.nan)
    for i in range(1, cfg.N_FOLDS):
        tr_end = folds[i][0]
        # embargo: drop trailing train events whose holding window could touch the fold
        cutoff = days[folds[i][0]] - pd.Timedelta(days=cfg.META_TIMEOUT_D + cfg.EMBARGO_DAYS)
        tr = np.arange(tr_end)[days[:tr_end] <= cutoff]
        if len(tr) < cfg.META_MIN_TRAIN_EVENTS:
            continue
        m = HistGradientBoostingClassifier(
            max_iter=cfg.ML_MAX_ITER, learning_rate=cfg.ML_LEARNING_RATE,
            max_depth=cfg.ML_MAX_DEPTH, random_state=cfg.BOOT_SEED)
        m.fit(X.iloc[tr], lab.win.iloc[tr])
        pred[folds[i]] = m.predict_proba(X.iloc[folds[i]])[:, 1]
    oos = ~np.isnan(pred)
    n_oos = int(oos.sum())
    base = float(lab.win[oos].mean()) if n_oos else float("nan")
    bet = oos & (pred > 0.5)
    n_bet = int(bet.sum())
    precision = float(lab.win[bet].mean()) if n_bet else float("nan")
    delta_exp = (float(lab.ret[bet].mean() - lab.ret[oos].mean()) if n_bet else float("nan"))
    if n_bet and 0.0 < base < 1.0:
        z = (precision - base) / np.sqrt(base * (1 - base) / n_bet)
    else:
        z = float("nan")
    passes = bool(n_oos >= cfg.META_MIN_EVENTS and n_bet > 0
                  and z >= cfg.META_Z and delta_exp > 0)
    return dict(n_events=n, n_oos=n_oos, n_bet=n_bet, base_win_rate=base,
                bet_precision=precision, bet_fraction=(n_bet / n_oos if n_oos else 0.0),
                precision_z=float(z), delta_expectancy_r=delta_exp, passes=passes)
