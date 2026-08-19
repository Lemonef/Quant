"""
basis_carry_test.py — quarterly cash-and-carry basis: per-contract kill test (PATTERN-SYNTHESIS build #1).

MECHANISM (law L2 "someone pays" + settlement anchor): long spot / short the dated quarterly
future; the exchange settles the future to the spot index at delivery, so the entry basis is
LARGELY earned regardless of path (residual = terminal-basis noise if exiting early). It is
a risk premium (crowd pays for leveraged long exposure), not a prediction. Independent
external replication: boyam01/crypto-carry-research (~3%/yr unlevered, OOS Sharpe ~2.9,
20 settled contracts all positive in-sample; exits 5d pre-delivery). We test it OURSELVES,
per contract, with our costs, before believing any of that.

DATA: Binance Vision monthly 1d klines per delivery contract BTCUSDT_YYMMDD (2021-06 →) +
spot BTCUSDT 1d from our panel data. Cached under data/basis/. Keyless, public.

RULE (declared, no search):
  - Contract universe: every settled quarterly (delivery date < today − 7d).
  - Entry: the FIRST trading day on which the contract has >= 20 days to delivery AND
    annualized basis b = (F/S − 1) × 365/DTE  exceeds the ROUND-TRIP COST HURDLE
    (4 legs × (TAKER_FEE + SLIPPAGE) annualized over the remaining DTE) — i.e. enter when
    the premium pays for itself; earlier of the contract's life preferred (max carry).
  - Exit: EXIT_DTE = 5 days before delivery (boyam01 convention; avoids settlement-print
    noise) — declared, not tuned; the "hold to delivery" variant is ALSO reported.
  - P&L per contract (unlevered, on the SPOT notional): (F_entry − F_exit)/S_entry [short
    future] + (S_exit − S_entry)/S_entry [long spot] − 4 legs cost. Funding on the spot
    leg = none (spot). No leverage → no liquidation path modeled (declared limitation:
    real deployments lever the short leg; margin risk is operational).
  - Kill line: >= 80% of settled contracts positive net AND mean annualized net > 0 with
    a positive bootstrap-CI lower bound (contract-level, 10k) AND the OOS half (contracts
    2024+) also mean-positive. n_trials = 1 rule (+ hold-to-delivery variant reported).

Usage: python backtest/basis_carry_test.py  → backtest_results/BASIS_CARRY_<date>.md
"""
import csv, datetime as dt, io, sys, time, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from alpha_factory import config as cfg

DATA = HERE / "data" / "basis"
RESULTS = HERE.parent / "backtest_results"
BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
SYM = sys.argv[1].upper() if len(sys.argv) > 1 and sys.argv[1].upper().endswith("USDT") else "BTCUSDT"
MIN_DTE_ENTRY = 20
EXIT_DTE = 5
LEGS = 4                                # spot buy, fut sell, fut buy, spot sell
COST_LEG = cfg.TAKER_FEE + cfg.SLIPPAGE
OOS_FROM = dt.date(2024, 1, 1)
SEED = cfg.BOOT_SEED


def quarterly_deliveries(y0=2021, y1=2026):
    out = []
    for y in range(y0, y1 + 1):
        for m in (3, 6, 9, 12):
            d = dt.date(y, m, 28)
            while d.month == m:
                d += dt.timedelta(days=1)
            d -= dt.timedelta(days=1)
            while d.weekday() != 4:
                d -= dt.timedelta(days=1)
            out.append(d)
    return out


def fetch_contract(code, delivery):
    """All 1d klines of BTCUSDT_<code> from Vision monthly zips (cached CSV)."""
    DATA.mkdir(parents=True, exist_ok=True)
    p = DATA / f"{SYM}_{code}_1d.csv"
    if p.exists():
        return pd.read_csv(p, parse_dates=["date"]).set_index("date")
    rows = []
    m = dt.date(delivery.year, delivery.month, 1)
    for _ in range(12):                                   # contracts list ~9 months early
        ym = m.strftime("%Y-%m")
        url = f"{BASE}/{SYM}_{code}/1d/{SYM}_{code}-1d-{ym}.zip"
        try:
            with urlopen(Request(url, headers={"User-Agent": "quant/1.0"}), timeout=30) as r:
                raw = r.read()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                with z.open(z.namelist()[0]) as f:
                    for line in io.TextIOWrapper(f, encoding="utf-8"):
                        if line.startswith("open_time"):
                            continue
                        c = line.strip().split(",")
                        rows.append((int(c[0]), float(c[4])))
        except HTTPError as e:
            if e.code != 404:
                raise
        m = (m.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        time.sleep(0.15)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "close"]).drop_duplicates("ts").sort_values("ts")
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
    df = df.drop(columns="ts").set_index("date")
    df.to_csv(p)
    return df


def spot_series():
    from alpha_factory.panel import build_panel
    panel = build_panel(HERE / "data")
    s = panel.close[SYM]
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return s


def replay_contract(fut, spot, delivery, exit_dte):
    """Entry per the declared rule; returns dict or None (never qualified)."""
    d_ts = pd.Timestamp(delivery)
    df = pd.DataFrame({"F": fut["close"]}).join(spot.rename("S"), how="inner").dropna()
    df["dte"] = (d_ts - df.index).days
    df = df[df["dte"] >= exit_dte]
    if df.empty:
        return None
    df["basis_ann"] = (df["F"] / df["S"] - 1.0) * 365.0 / df["dte"].clip(lower=1)
    df["hurdle_ann"] = LEGS * COST_LEG * 365.0 / df["dte"].clip(lower=1)
    cand = df[(df["dte"] >= MIN_DTE_ENTRY) & (df["basis_ann"] > df["hurdle_ann"])]
    if cand.empty:
        return dict(entered=False)
    e = cand.index[0]
    x = df.index[-1]                                       # last bar with dte >= exit_dte
    Fe, Se, Fx, Sx = df.loc[e, "F"], df.loc[e, "S"], df.loc[x, "F"], df.loc[x, "S"]
    gross = (Fe - Fx) / Se + (Sx - Se) / Se
    net = gross - LEGS * COST_LEG
    days = (x - e).days or 1
    return dict(entered=True, entry=e.date(), exit=x.date(), dte_entry=int(df.loc[e, "dte"]),
                basis_ann_entry=float(df.loc[e, "basis_ann"]), gross=float(gross),
                net=float(net), net_ann=float(net * 365.0 / days), days=days,
                terminal_basis=float(Fx / Sx - 1.0))


def main():
    spot = spot_series()
    today = dt.date.today()
    rows = []
    for d in quarterly_deliveries():
        if d > today - dt.timedelta(days=7):
            continue                                       # not settled yet
        code = d.strftime("%y%m%d")
        fut = fetch_contract(code, d)
        if fut is None or len(fut) < 30:
            rows.append(dict(code=code, delivery=d, status="no-data")); continue
        for label, xd in (("exit5", EXIT_DTE), ("hold", 0)):
            r = replay_contract(fut, spot, d, xd)
            rows.append(dict(code=code, delivery=d, variant=label, status="ok",
                             **(r or dict(entered=False))))
        print(f"{code}: bars {len(fut)} · " + " · ".join(
            f"{v['variant']} net {v.get('net', float('nan')):+.4f}" for v in rows[-2:] if v.get('entered')),
            flush=True)

    def stats(variant):
        sub = [r for r in rows if r.get("variant") == variant and r.get("entered")]
        nets = np.array([r["net"] for r in sub]); anns = np.array([r["net_ann"] for r in sub])
        oos = np.array([r["net_ann"] for r in sub if r["delivery"] >= OOS_FROM])
        rng = np.random.default_rng(SEED)
        boots = [anns[rng.integers(0, len(anns), len(anns))].mean() for _ in range(10_000)] if len(anns) else [np.nan]
        return dict(n=len(sub), pos=int((nets > 0).sum()), mean_net=float(nets.mean()) if len(nets) else np.nan,
                    mean_ann=float(anns.mean()) if len(anns) else np.nan,
                    ci_lo=float(np.percentile(boots, 2.5)), ci_hi=float(np.percentile(boots, 97.5)),
                    oos_n=len(oos), oos_mean_ann=float(oos.mean()) if len(oos) else np.nan,
                    worst=float(nets.min()) if len(nets) else np.nan)

    s5, sh = stats("exit5"), stats("hold")
    passes = (s5["n"] > 0 and s5["pos"] / s5["n"] >= 0.8 and s5["mean_ann"] > 0
              and s5["ci_lo"] > 0 and s5["oos_mean_ann"] > 0)
    tdy = today.isoformat()
    p = RESULTS / f"BASIS_CARRY_{SYM}_{tdy}.md"
    L = [f"# Quarterly basis cash-and-carry — {SYM} per-contract kill test — {tdy}", "",
         f"Rule (declared): enter first day with DTE≥{MIN_DTE_ENTRY} and annualized basis > "
         f"{LEGS}-leg cost hurdle ({COST_LEG:.4%}/leg = fee+slip); exit at DTE={EXIT_DTE} "
         "(boyam01 convention) — 'hold' variant to delivery also shown. Unlevered on spot "
         "notional; no margin path modeled (declared).", "",
         "| contract | delivery | variant | entered | entry | DTE | basis@entry (ann) | gross | net | net ann | terminal basis |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("status") != "ok":
            L.append(f"| {r['code']} | {r['delivery']} | – | {r['status']} | | | | | | | |"); continue
        if not r.get("entered"):
            L.append(f"| {r['code']} | {r['delivery']} | {r['variant']} | never qualified | | | | | | | |"); continue
        L.append(f"| {r['code']} | {r['delivery']} | {r['variant']} | ✓ | {r['entry']} | {r['dte_entry']} | "
                 f"{r['basis_ann_entry']:+.1%} | {r['gross']:+.3%} | {r['net']:+.3%} | {r['net_ann']:+.1%} | "
                 f"{r['terminal_basis']:+.3%} |")
    for name, s in (("exit5 (traded rule)", s5), ("hold-to-delivery", sh)):
        L += ["", f"## {name}: n {s['n']} · positive {s['pos']}/{s['n']} · mean net/contract {s['mean_net']:+.3%} · "
              f"mean annualized {s['mean_ann']:+.1%} · CI95 [{s['ci_lo']:+.1%}, {s['ci_hi']:+.1%}] · "
              f"OOS(2024+) n {s['oos_n']} mean ann {s['oos_mean_ann']:+.1%} · worst contract {s['worst']:+.3%}"]
    L += ["", f"## VERDICT (exit5 rule): **{'PASS → full gauntlet + prereg next' if passes else 'DEAD'}**",
          "", "Kill line: ≥80% contracts positive net ∧ mean ann > 0 ∧ CI lo > 0 ∧ OOS mean > 0. "
          "Levels are UNLEVERED; the real product levers the short leg — margin/liquidation risk "
          "is the operational cost this test does not price. Cross-replication: boyam01 reports "
          "~3%/yr unlevered — compare, don't trust."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")
    print("VERDICT:", "PASS" if passes else "DEAD", s5)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
