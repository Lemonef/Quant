"""
basis_margin_engine.py — the gate basis_carry_v2 left open: what does the trade cost in CAPITAL,
and what does it return on that capital once a margin account has to survive the path?

WHY (2026-10-15). basis_carry_v2 PASSED its kill test at +10.1%/yr unlevered, 8/8 contracts
positive. But that return is per unit of SPOT NOTIONAL. A cash-and-carry also needs collateral
behind the short futures leg, and v2's own table shows the short leg went up to +105% against
(BTC roughly doubled mid-hold) with 4 of 8 contracts liquidated at 3x. On a venue that does NOT
count the spot leg as futures collateral (Binance USD-M isolated/cross without Portfolio Margin),
the futures account must SURVIVE that path on its own. v2 flagged this as "a real margin engine
is the gauntlet's job". This is that engine.

WHAT IT DOES. Re-uses v2's entry/exit rules verbatim (same signal, same next-open fills, DTE-5
exit) and walks each held contract DAY BY DAY under declared collateral policies:

  ISOLATED, collateral ratio c (futures margin posted = c × notional), decided EX ANTE:
    liquidated on the first day the futures HIGH rises >= c - MAINT above entry.
    On liquidation: futures collateral lost (c x N, conservative), a declared LIQ_FEE charged,
    spot leg unwound at that day's close (an operator would not hold a now-naked long).
    Capital tied up = N x (1 + c). Return on capital = realised / (1 + c).
  PORTFOLIO MARGIN (upper bound): spot counts as collateral, the hedged pair carries only a
    small residual margin PM_MARGIN x N. Capital = N x (1 + PM_MARGIN).

THE HURDLE that matters is not zero, it is CASH: capital that sits in a carry trade could sit
in a USD yield instead. CASH_YIELD is declared, not fitted. A carry that cannot beat it on the
capital it actually consumes is a worse version of a savings account with tail risk attached.

Declared, not searched: every constant below. Daily HIGH of the last-traded futures price is a
PROXY for the mark price (intraday marks can be worse, liquidation engines use mark) - so
liquidation counts here are a LOWER bound.

Usage: python backtest/basis_margin_engine.py [BTCUSDT|ETHUSDT]
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))

import basis_carry_v2 as v2                       # SYM is read from argv inside v2
from basis_carry_test import quarterly_deliveries

for _s in (sys.stdout, sys.stderr):              # cp874 consoles must not silence a result
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

EXIT_DTE = 5                                      # v2's headline exit
COLLATERAL_POLICIES = (0.25, 0.5, 1.0, 1.5, 2.0)  # c, as a fraction of futures notional
PM_MARGIN = 0.10                                  # residual margin for a hedged pair under PM (assumption)
LIQ_FEE = 0.010                                   # liquidation/clearance fee on notional (declared conservative)
CASH_YIELD = 0.045                                # USD cash/T-bill/stablecoin-lending yield 2023-26 (declared)
MAINT = v2.MAINT
RESULTS = HERE.parent / "backtest_results"


def walk(fut, spot, delivery):
    """v2's entry/exit, then the daily path. Returns None if v2 would not have entered."""
    r = v2.replay(fut, spot, delivery, EXIT_DTE)
    if not r or not r.get("entered") or r.get("partial"):
        return None
    df = fut.join(spot, how="inner", lsuffix="_f", rsuffix="_s").dropna()
    e, x = pd.Timestamp(r["entry"]), pd.Timestamp(r["exit"])
    path = df.loc[e:x]
    Fe, Se = path["open_f"].iloc[0], path["open_s"].iloc[0]
    return r, path, Fe, Se


def isolated(r, path, Fe, Se, c):
    """Isolated short with collateral c. Returns (realised_on_notional, liquidated, days_held)."""
    trigger = c - MAINT
    for t, row in path.iterrows():
        if row["high_f"] / Fe - 1.0 >= trigger:
            spot_gain = row["close_s"] / Se - 1.0
            # one spot round trip + the futures entry leg (the exit leg is the liquidation itself)
            costs = 2 * v2.SPOT_COST_LEG + v2.FUT_COST_LEG
            realised = spot_gain - c - LIQ_FEE - costs
            return realised, True, max(1, (t - path.index[0]).days)
    return r["net"], False, r["days"]


def main():
    spot = v2.spot_ohlc()
    rows = []
    today = dt.date.today()
    for d in quarterly_deliveries():               # returns delivery dates; v2 derives the code
        if d > today - dt.timedelta(days=7):       # same settled-only rule as v2.main
            continue
        code = d.strftime("%y%m%d")
        try:
            fut = v2.fetch_contract_ohlc(code, d)
        except Exception:
            continue
        if fut is None or len(fut) < 30:
            continue
        w = walk(fut, spot, d)
        if w is None:
            continue
        r, path, Fe, Se = w
        row = dict(contract=code, entry=r["entry"], days=r["days"], net=r["net"],
                   adverse_high=r["adverse_high"])
        for c in COLLATERAL_POLICIES:
            real, liq, days = isolated(r, path, Fe, Se, c)
            row[f"liq_{c}"] = liq
            row[f"roc_{c}"] = real / (1.0 + c) * 365.0 / days
        row["roc_pm"] = r["net"] / (1.0 + PM_MARGIN) * 365.0 / r["days"]
        rows.append(row)

    if not rows:
        print("no FULL contracts entered"); return 1
    df = pd.DataFrame(rows)
    n = len(df)
    lines = [f"# {v2.SYM} basis carry — MARGIN ENGINE (capital-adjusted) — 2026-10-15", "",
             "Same entry/exit as basis_carry_v2 (DTE-5 exit, FULL contracts). Each contract walked day by day "
             "under a collateral policy fixed EX ANTE. Liquidation trigger = futures daily HIGH vs entry >= "
             f"c - maint ({MAINT:.1%}); on liquidation the collateral is lost, a {LIQ_FEE:.1%} fee charged and spot "
             "unwound at that close. Return is on TOTAL capital tied up = spot notional + collateral. "
             f"Hurdle = cash yield {CASH_YIELD:.1%}/yr. Daily high is a proxy for mark price, so liquidation "
             "counts are a LOWER bound.", "",
             f"Contracts: {n} · unlevered headline from v2 (return on spot notional only): "
             f"**{df['net'].mul(365).div(df['days']).mean():+.1%}/yr**", "",
             "| policy | capital per $1 notional | liquidated | mean return ON CAPITAL /yr | worst contract | beats cash? |",
             "|---|---|---|---|---|---|"]
    verdict_rows = []
    for c in COLLATERAL_POLICIES:
        roc = df[f"roc_{c}"]
        liq = int(df[f"liq_{c}"].sum())
        beat = roc.mean() > CASH_YIELD
        verdict_rows.append((c, roc.mean(), liq, beat))
        lines.append(f"| isolated, c={c:.2f} | ${1 + c:.2f} | {liq}/{n} | {roc.mean():+.1%} | "
                     f"{roc.min():+.1%} | {'✅' if beat else '❌'} |")
    pm = df["roc_pm"]
    lines.append(f"| portfolio margin (upper bound) | ${1 + PM_MARGIN:.2f} | 0/{n} (modelled) | "
                 f"{pm.mean():+.1%} | {pm.min():+.1%} | {'✅' if pm.mean() > CASH_YIELD else '❌'} |")

    lines += ["", "## Per contract — max adverse move on the short leg", "",
              "| contract | entry | days | adverse high | " + " | ".join(f"liq c={c}" for c in COLLATERAL_POLICIES) + " |",
              "|---|---|---|---|" + "---|" * len(COLLATERAL_POLICIES)]
    for _, rw in df.iterrows():
        lines.append(f"| {rw['contract']} | {rw['entry']} | {rw['days']} | {rw['adverse_high']:+.1%} | "
                     + " | ".join("⚠" if rw[f"liq_{c}"] else "–" for c in COLLATERAL_POLICIES) + " |")

    safe = [c for c, _, liq, _ in verdict_rows if liq == 0]
    c_safe = min(safe) if safe else None
    lines += ["", "## Reading it", ""]
    if c_safe is not None:
        roc_safe = df[f"roc_{c_safe}"].mean()
        lines.append(f"- Smallest collateral that survived EVERY contract: **c = {c_safe:.2f}** -> "
                     f"${1 + c_safe:.2f} of capital per $1 of carry, returning **{roc_safe:+.1%}/yr on capital** "
                     f"vs cash {CASH_YIELD:.1%}. Note this c is chosen with hindsight of the worst path; an honest "
                     "operator sizes ABOVE it.")
    else:
        lines.append("- No tested collateral level survived every contract.")
    lines.append(f"- Portfolio margin would return {pm.mean():+.1%}/yr on capital — IF the venue offers it to this "
                 "account and counts the spot leg as collateral. That is an access question, not a backtest one.")

    out = RESULTS / f"BASIS_MARGIN_ENGINE_{v2.SYM}_2026-10-15.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
