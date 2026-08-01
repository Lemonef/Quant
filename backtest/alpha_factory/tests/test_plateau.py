"""Robustness gauntlet stage 3: parameter-plateau check from same-run sibling rows."""
import numpy as np
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel
from alpha_factory.zoo import build_zoo, Factor


def test_param_key_parses_zoo_naming():
    from alpha_factory.robust import param_key
    assert param_key("mom_21") == ("mom", (21,))
    assert param_key("volratio_10_63") == ("volratio", (10, 63))
    assert param_key("spread_kalman") == ("spread_kalman", None)
    assert param_key("streak") == ("streak", None)


def _row(name, rebal, sharpe):
    return dict(name=name, rebal=rebal, ls_sharpe=sharpe)


def test_plateau_pass_when_adjacent_windows_hold():
    from alpha_factory.robust import plateau_check
    rows = [_row("mom_10", 1, 0.8), _row("mom_21", 1, 1.2), _row("mom_28", 1, 0.5),
            _row("mom_63", 1, -0.4)]
    assert plateau_check("mom_21", 1, rows) is True      # neighbors 10 and 28 both > 0


def test_plateau_cliff_when_neighbor_dies():
    from alpha_factory.robust import plateau_check
    rows = [_row("mom_10", 1, 0.8), _row("mom_21", 1, 1.2), _row("mom_28", 1, -0.1)]
    assert plateau_check("mom_21", 1, rows) is False


def test_plateau_ignores_other_speeds_and_stems():
    from alpha_factory.robust import plateau_check
    rows = [_row("mom_10", 5, -2.0), _row("mom_10", 1, 0.5), _row("mom_21", 1, 1.0),
            _row("rev_21", 1, -3.0)]
    assert plateau_check("mom_21", 1, rows) is True      # rebal-5 and rev_* rows invisible


def test_plateau_neighbors_differ_in_exactly_one_param():
    from alpha_factory.robust import plateau_check
    # (10,126) differs from (21,63) in BOTH coordinates — not a grid neighbor and
    # must not decide the verdict; the only true neighbor (10,63) holds
    rows = [_row("volratio_10_63", 1, 0.9), _row("volratio_21_63", 1, 1.1),
            _row("volratio_10_126", 1, -2.0)]
    assert plateau_check("volratio_21_63", 1, rows) is True


def test_plateau_not_applicable():
    from alpha_factory.robust import plateau_check
    rows = [_row("spread_kalman", 1, 1.0), _row("planted", 1, 2.0)]
    assert plateau_check("spread_kalman", 1, rows) is None   # param-free
    assert plateau_check("planted", 1, rows) is None         # no siblings


def test_survivor_cliff_annotated_end_to_end():
    from alpha_factory.report import run_factory
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    # planted_20 is the anti-signal: same stem, adjacent window, deeply negative —
    # the surviving planted_10 must be flagged as a parameter cliff
    zoo = build_zoo()[:10] + [
        Factor("planted_10", "test", "synthetic", lambda p: planted),
        Factor("planted_20", "test", "synthetic", lambda p: -planted),
    ]
    df = run_factory(panel, zoo, cfg)
    row = df[df.name == "planted_10"].iloc[0]
    assert row.verdict == "SURVIVED"
    assert row.plateau_pass == False  # noqa: E712 — column holds True/False/NaN
    assert "CLIFF" in row.reason
    rej = df[df.verdict == "REJECTED"]
    assert rej.plateau_pass.isna().all()
