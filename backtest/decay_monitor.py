"""
decay_monitor.py — strategy-rot early warning for the live paper book.

WHY (owner 2026-08-18: "strategies become invalid when time changes — find a way"):
every sleeve was adopted on a backtest expectation; edges decay silently and the human
notices at the blowup. A REGIME GATE that flips positions was tested dead (PM-QUANT
Track C: book 1.79 → gated −1.60 — churn). This is deliberately NOT that: it trades
nothing. It is a MONITOR that compares each live sleeve's rolling record against its own
backtest expectation and flags candidates for human retirement review — the cheapest
form of the fix that cannot hurt the book.

METHOD (per tab × leverage level, from web/data.json live equity series):
  - trailing-window annualized Sharpe + max drawdown over DECAY_WINDOW_D days
  - status ladder, worst wins:
      HEALTHY   — trailing Sharpe >= 0 or window not yet full
      WATCH     — trailing Sharpe < 0 for the full window
      DECAY     — WATCH and live maxDD exceeds the sleeve's own reported backtest-era
                  maxdd by DECAY_DD_MULT (the sleeve is outside its own historical pain)
      STALE-DATA— series hasn't advanced in STALE_D days (data problem, not market)
  - Also reports time-under-water (days since equity high) — the human-legible rot number.
Thresholds are structural constants (0 = the sign boundary, 1.2 = a fifth beyond the
sleeve's own worst), not fitted; nothing is optimized against outcomes.

Output: web/decay.json + a compact stdout block (cron logs). Wire into paper_bot cron
after the data.json build; weekly review reads web/decay.json (scheduled-routines.md).

Usage: python backtest/decay_monitor.py [--data web/data.json]
"""
import argparse, datetime as dt, json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DECAY_WINDOW_D = 60          # trailing window: two months of live record
STALE_D = 3                  # equity series not advancing = data problem
DECAY_DD_MULT = 1.2          # live DD > 1.2x the sleeve's own reported maxdd = outside history
MIN_PTS = 40                 # below this many live points a sleeve is UNRATED (no claim)


def _daily_returns(series):
    """series = [[iso_ts, equity], ...] (multiple points/day) -> last-per-day returns."""
    by_day = {}
    for ts, eq in series:
        by_day[ts[:10]] = float(eq)
    days = sorted(by_day)
    eqs = [by_day[d] for d in days]
    rets = [(b / a - 1.0) for a, b in zip(eqs, eqs[1:]) if a > 0]
    return days, eqs, rets


def _sharpe(rets):
    if len(rets) < 10:
        return None
    m = sum(rets) / len(rets)
    v = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return (m / math.sqrt(v)) * math.sqrt(365) if v > 0 else None


def _maxdd(eqs):
    peak, worst = float("-inf"), 0.0
    for e in eqs:
        peak = max(peak, e)
        worst = min(worst, e / peak - 1.0)
    return worst * 100


def assess(level, today):
    s = level.get("series") or []
    if len(s) < MIN_PTS:
        return dict(status="UNRATED", note=f"only {len(s)} live points")
    days, eqs, rets = _daily_returns(s)
    last_day = dt.date.fromisoformat(days[-1])
    if (today - last_day).days > STALE_D:
        return dict(status="STALE-DATA", note=f"no bar since {days[-1]}")
    w_days = days[-DECAY_WINDOW_D:]
    w_eqs = eqs[-DECAY_WINDOW_D:]
    w_rets = rets[-(DECAY_WINDOW_D - 1):]
    tsh = _sharpe(w_rets)
    tdd = _maxdd(w_eqs)
    peak_i = max(range(len(eqs)), key=lambda i: eqs[i])
    tuw = (today - dt.date.fromisoformat(days[peak_i])).days
    full = len(w_days) >= DECAY_WINDOW_D
    status = "HEALTHY"
    ref_dd = level.get("maxdd")
    if full and tsh is not None and tsh < 0:
        status = "WATCH"
        if ref_dd is not None and abs(tdd) > abs(float(ref_dd)) * DECAY_DD_MULT:
            status = "DECAY"
    return dict(status=status, trailing_sharpe=None if tsh is None else round(tsh, 2),
                trailing_dd_pct=round(tdd, 2), time_under_water_d=tuw,
                window_days=len(w_days), ref_maxdd=ref_dd)


def run(data_path):
    d = json.loads(Path(data_path).read_text(encoding="utf-8"))
    today = dt.date.today()
    out = dict(generated=today.isoformat(), window_d=DECAY_WINDOW_D, sleeves=[])
    worst = {"DECAY": 0, "WATCH": 0, "STALE-DATA": 0}
    for tab in d.get("tabs", []):
        for lv in tab.get("levels", []):
            a = assess(lv, today)
            a.update(tab=tab.get("name"), lev=lv.get("lev"))
            out["sleeves"].append(a)
            if a["status"] in worst:
                worst[a["status"]] += 1
    out["summary"] = worst
    Path(HERE / "web" / "decay.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    flags = [s for s in out["sleeves"] if s["status"] in ("DECAY", "WATCH", "STALE-DATA")]
    print(f"decay-monitor: {len(out['sleeves'])} sleeves · "
          f"DECAY {worst['DECAY']} · WATCH {worst['WATCH']} · STALE {worst['STALE-DATA']}")
    for s in flags:
        print(f"  {s['status']:10} {s['tab']} [{s['lev']}] tSharpe={s.get('trailing_sharpe')} "
              f"tDD={s.get('trailing_dd_pct')}% TUW={s.get('time_under_water_d')}d")
    return out


def selftest():
    today = dt.date.today()
    mk = lambda eqs: {"series": [[(today - dt.timedelta(days=len(eqs) - i)).isoformat() + "T00:00", e]
                                 for i, e in enumerate(eqs)], "maxdd": -5.0, "lev": "1x"}
    up = mk([10000 * (1.001 ** i) for i in range(80)])
    assert assess(up, today)["status"] == "HEALTHY"
    down = mk([10000 * (0.999 ** i) for i in range(80)])
    a = assess(down, today)
    assert a["status"] in ("WATCH", "DECAY"), a
    deep = mk([10000 * (0.996 ** i) for i in range(80)])          # ~-27% > 1.2x the 5% ref
    assert assess(deep, today)["status"] == "DECAY"
    stale = mk([10000.0] * 80)
    stale["series"] = [[(today - dt.timedelta(days=90 + i)).isoformat() + "T00:00", 10000.0]
                       for i in range(80)]
    assert assess(stale, today)["status"] == "STALE-DATA"
    short = {"series": [["2026-01-01T00:00", 10000.0]] * 10, "lev": "1x"}
    assert assess(short, today)["status"] == "UNRATED"
    print("selftest OK: healthy/watch/decay/stale/unrated all classify")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "web" / "data.json"))
    ap.add_argument("cmd", nargs="?", default="run")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    else:
        run(a.data)
