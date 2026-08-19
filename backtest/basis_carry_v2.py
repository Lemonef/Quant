"""
basis_carry_v2.py — quarterly cash-and-carry, POST-CRITIQUE version (Codex 2026-08-19: 3 blockers,
6 majors, 1 minor). Every fix below is declared; nothing was searched. Read alongside
basis_carry_test.py (v1) — v1's numbers are the "same-bar, unlevered, single exit" upper bound.

FIXES
  #1 same-bar look-ahead  → signal on day t CLOSE (kline open_time t → close known at t+1 00:00
     UTC), FILL at day t+1 OPEN of both legs (contract open from Vision klines; spot open from
     our 1d spot file). Entry/exit both next-bar OPEN.
  #4 weak hurdle           → hurdle = 4-leg cost + MIN_NET_ANN (declared 5%/yr) applied to the
     basis EXPECTED TO BE EARNED to the planned exit: entry basis minus a conservative
     terminal-basis allowance TERM_BASIS_ALLOW (0.5% — the 90th pct of |terminal basis at
     DTE5| observed in v1's table, declared here, not re-fitted per run).
  #5 partial-history       → contracts whose first Vision bar is later than DTE 60 are bucketed
     PARTIAL and shown separately; the verdict uses FULL contracts only.
  #6 exit family           → EXIT_DTES = (3, 5, 7, 10) + hold; verdict requires the PLATEAU:
     all four DTE exits positive-mean; the headline is the WORST of the four, not the best.
  #2 margin/liquidation    → for each contract, the max adverse move of the SHORT-future leg
     from entry (daily closes and highs) is reported, and the leverage at which a 3x / 5x
     isolated short would have been liquidated (maintenance ~0.5% + adverse move ≥ 1/L) is
     flagged. This is a daily-close PROXY (intraday marks worse) — declared; a real margin
     engine is the gauntlet's job.
  #8 execution cost        → COST_LEG doubled to 2×(fee+slip) = 0.22%/leg for the futures legs
     (thinner delivery books) — declared conservative haircut, spot legs at 1×.
  #9 CI fragility          → contract-level bootstrap kept + leave-one-YEAR-out means + pre/post
     2024 split (already) reported.
  #10 redundancy           → correlation of per-contract annualized returns with the funding-carry
     sleeve's same-window returns is NOT computable from this file (different clocks); flagged
     for the gauntlet stage. Headline wording per #7: "short basis/liquidity tail-risk premium".

Kill line (declared): FULL contracts, worst-of-exit-family mean annualized net > MIN_NET_ANN AND
≥ 80% positive at DTE5 AND contract-bootstrap CI lo > 0 AND leave-one-year-out means all > 0.
Usage: python backtest/basis_carry_v2.py [BTCUSDT|ETHUSDT]
"""
import datetime as dt, io, sys, time, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from alpha_factory import config as cfg
from basis_carry_test import quarterly_deliveries

DATA = HERE / "data" / "basis"
RESULTS = HERE.parent / "backtest_results"
BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
SYM = sys.argv[1].upper() if len(sys.argv) > 1 and sys.argv[1].upper().endswith("USDT") else "BTCUSDT"
MIN_DTE_ENTRY = 20
EXIT_DTES = (3, 5, 7, 10)
MIN_NET_ANN = 0.05
TERM_BASIS_ALLOW = 0.005
FUT_COST_LEG = 2 * (cfg.TAKER_FEE + cfg.SLIPPAGE)
SPOT_COST_LEG = cfg.TAKER_FEE + cfg.SLIPPAGE
ROUND_TRIP = 2 * FUT_COST_LEG + 2 * SPOT_COST_LEG
PARTIAL_DTE = 60
MAINT = 0.005
LEVS = (3.0, 5.0)
SEED = cfg.BOOT_SEED
OOS_FROM = dt.date(2024, 1, 1)


def fetch_contract_ohlc(code, delivery):
    p = DATA / f"{SYM}_{code}_1d_ohlc.csv"
    if p.exists():
        return pd.read_csv(p, parse_dates=["date"]).set_index("date")
    rows = []
    m = dt.date(delivery.year, delivery.month, 1)
    for _ in range(12):
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
                        rows.append((int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4])))
        except HTTPError as e:
            if e.code != 404:
                raise
        m = (m.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        time.sleep(0.15)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).drop_duplicates("ts").sort_values("ts")
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
    df = df.drop(columns="ts").set_index("date")
    df.to_csv(p)
    return df


def spot_ohlc():
    df = pd.read_csv(HERE / "data" / f"{SYM}_1d.csv")
    df["date"] = pd.to_datetime(df["open_time"], unit="ms").dt.normalize()
    return df.set_index("date")[["open", "high", "low", "close"]].astype(float)


def replay(fut, spot, delivery, exit_dte):
    d_ts = pd.Timestamp(delivery)
    df = fut.join(spot, how="inner", lsuffix="_f", rsuffix="_s").dropna()
    df["dte"] = (d_ts - df.index).days
    df = df[df["dte"] >= 0]
    if len(df) < 5:
        return None
    first_dte = int(df["dte"].iloc[0])
    # signal on close t; fill next bar OPEN
    basis = df["close_f"] / df["close_s"] - 1.0
    exp_earn = basis - TERM_BASIS_ALLOW - ROUND_TRIP
    ann = exp_earn * 365.0 / df["dte"].clip(lower=1)
    cand = df[(df["dte"] >= MIN_DTE_ENTRY + 1) & (ann > MIN_NET_ANN)]
    if cand.empty:
        return dict(entered=False, first_dte=first_dte)
    sig_i = df.index.get_loc(cand.index[0])
    if sig_i + 1 >= len(df):
        return dict(entered=False, first_dte=first_dte)
    e = df.index[sig_i + 1]
    # exit: signal bar = last bar with dte >= exit_dte+1, fill next open (dte >= exit_dte)
    tail = df[df["dte"] >= exit_dte]
    if len(tail) < 2 or tail.index[-1] <= e:
        return dict(entered=False, first_dte=first_dte)
    x = tail.index[-1]
    Fe, Se = df.loc[e, "open_f"], df.loc[e, "open_s"]
    Fx, Sx = df.loc[x, "open_f"], df.loc[x, "open_s"]
    gross = (Fe - Fx) / Se + (Sx - Se) / Se
    net = gross - ROUND_TRIP
    days = max(1, (x - e).days)
    held = df.loc[e:x]
    adverse_close = float(held["close_f"].max() / Fe - 1.0)     # short leg loses when F rises
    adverse_high = float(held["high_f"].max() / Fe - 1.0)
    liq = {L: bool(adverse_high >= (1.0 / L) - MAINT) for L in LEVS}
    return dict(entered=True, entry=e.date(), exit=x.date(), dte_entry=int(df.loc[e, "dte"]),
                basis_entry=float(basis.loc[cand.index[0]]), gross=float(gross), net=float(net),
                net_ann=float(net * 365.0 / days), days=days, first_dte=first_dte,
                partial=first_dte < PARTIAL_DTE, adverse_close=adverse_close,
                adverse_high=adverse_high, liq3=liq[3.0], liq5=liq[5.0],
                terminal_basis=float(Fx / Sx - 1.0))


def main():
    spot = spot_ohlc()
    today = dt.date.today()
    recs = []
    for d in quarterly_deliveries():
        if d > today - dt.timedelta(days=7):
            continue
        code = d.strftime("%y%m%d")
        fut = fetch_contract_ohlc(code, d)
        if fut is None or len(fut) < 30:
            continue
        for xd in EXIT_DTES + (0,):
            r = replay(fut, spot, d, xd)
            if r is None:
                continue
            recs.append(dict(code=code, delivery=d, exit_dte=xd, **r))
    full = [r for r in recs if r.get("entered") and not r["partial"]]
    part = [r for r in recs if r.get("entered") and r["partial"]]

    def agg(sub, xd):
        s = [r for r in sub if r["exit_dte"] == xd]
        if not s:
            return dict(n=0)
        anns = np.array([r["net_ann"] for r in s]); nets = np.array([r["net"] for r in s])
        rng = np.random.default_rng(SEED)
        boots = [anns[rng.integers(0, len(anns), len(anns))].mean() for _ in range(10_000)]
        loyo = {}
        for y in sorted({r["delivery"].year for r in s}):
            rest = [r["net_ann"] for r in s if r["delivery"].year != y]
            loyo[y] = float(np.mean(rest)) if rest else np.nan
        return dict(n=len(s), pos=int((nets > 0).sum()), mean_ann=float(anns.mean()),
                    ci_lo=float(np.percentile(boots, 2.5)), ci_hi=float(np.percentile(boots, 97.5)),
                    worst=float(nets.min()), loyo=loyo,
                    oos=float(np.mean([r["net_ann"] for r in s if r["delivery"] >= OOS_FROM]) if any(r["delivery"] >= OOS_FROM for r in s) else np.nan),
                    liq3=sum(1 for r in s if r["liq3"]), liq5=sum(1 for r in s if r["liq5"]),
                    adv_max=float(max(r["adverse_high"] for r in s)))

    fam = {xd: agg(full, xd) for xd in EXIT_DTES}
    hold = agg(full, 0)
    a5 = fam[5]
    worst_fam = min(v["mean_ann"] for v in fam.values() if v.get("n"))
    passes = (a5.get("n", 0) > 0 and worst_fam > MIN_NET_ANN and a5["pos"] / a5["n"] >= 0.8
              and a5["ci_lo"] > 0 and all(v > 0 for v in a5["loyo"].values()))

    tdy = today.isoformat()
    p = RESULTS / f"BASIS_CARRY_V2_{SYM}_{tdy}.md"
    L = [f"# {SYM} quarterly basis carry — v2 (post-critique) — {tdy}", "",
         "**Headline class: short basis / liquidity tail-risk premium (not alpha).** Signal on close t, "
         f"fill next-bar OPEN both legs. Hurdle: (entry basis − {TERM_BASIS_ALLOW:.1%} terminal allowance − "
         f"{ROUND_TRIP:.2%} round-trip) annualized > {MIN_NET_ANN:.0%}. Futures legs costed at "
         f"{FUT_COST_LEG:.2%}/leg (2× haircut), spot {SPOT_COST_LEG:.2%}. Exit family {EXIT_DTES} + hold; "
         f"verdict on FULL-history contracts (first bar ≥ DTE {PARTIAL_DTE}); PARTIAL bucket shown apart. "
         "Liquidation flags = daily-HIGH proxy for the short leg at 3x/5x isolated with 0.5% maintenance "
         "(intraday marks are WORSE — a real margin engine is the gauntlet's job).", "",
         "## Exit family (FULL contracts)", "",
         "| exit DTE | n | positive | mean ann net | CI95 | worst | OOS≥2024 | LOYO min | liq@3x | liq@5x | max adverse (short leg, high) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for xd in EXIT_DTES + (0,):
        a = hold if xd == 0 else fam[xd]
        if not a.get("n"):
            continue
        L.append(f"| {'hold' if xd == 0 else xd} | {a['n']} | {a['pos']}/{a['n']} | {a['mean_ann']:+.1%} | "
                 f"[{a['ci_lo']:+.1%}, {a['ci_hi']:+.1%}] | {a['worst']:+.3%} | {a['oos']:+.1%} | "
                 f"{min(a['loyo'].values()):+.1%} | {a['liq3']} | {a['liq5']} | {a['adv_max']:+.1%} |")
    L += ["", f"Worst-of-family mean ann net (the headline): **{worst_fam:+.1%}/yr unlevered**",
          "", "## Per-contract (DTE 5 exit)", "",
          "| contract | bucket | entry | DTE | basis@sig | gross | net | net ann | adverse close/high | liq3 | liq5 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted([r for r in recs if r.get("entered") and r["exit_dte"] == 5], key=lambda r: r["delivery"]):
        L.append(f"| {r['code']} | {'PARTIAL' if r['partial'] else 'full'} | {r['entry']} | {r['dte_entry']} | "
                 f"{r['basis_entry']:+.2%} | {r['gross']:+.3%} | {r['net']:+.3%} | {r['net_ann']:+.1%} | "
                 f"{r['adverse_close']:+.1%}/{r['adverse_high']:+.1%} | {'⚠' if r['liq3'] else '–'} | {'⚠' if r['liq5'] else '–'} |")
    never = sorted({r["code"] for r in recs if not r.get("entered")} - {r["code"] for r in recs if r.get("entered")})
    L += ["", f"Never qualified (hurdle not met): {', '.join(never) if never else 'none'} · PARTIAL-history contracts: {len({r['code'] for r in part})}",
          "", f"## VERDICT (FULL contracts, family-worst): **{'PASS → prereg + full gauntlet (margin engine, execution depth, funding-carry overlap, Thai access) BEFORE any shadow' if passes else 'DEAD'}**",
          "", "Blockers still OPEN regardless of verdict (Codex #2/#3): real margin/liquidation engine on mark prices; "
          "Binance USD-M delivery-futures access for a Thai retail account (owner must verify). Not a sleeve until both close."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")
    print("VERDICT:", "PASS" if passes else "DEAD", {k: (v.get("mean_ann"), v.get("pos"), v.get("n")) for k, v in fam.items()})


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
