import pandas as pd
from alpha_factory import config as cfg

def test_factory_end_to_end_on_synthetic(tmp_path):
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.zoo import build_zoo, Factor
    from alpha_factory.report import run_factory, render
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:20] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    assert set(["name", "verdict", "reason", "dsr_prob"]).issubset(df.columns)
    row = df[df.name == "planted"].iloc[0]
    assert row.verdict == "SURVIVED" and row.improves_book in (True, False)
    md, csv = render(df, cfg, tmp_path, "TEST")
    text = md.read_text()
    assert "SURVIVED" in text and cfg.SURVIVORSHIP_CAVEAT[:40] in text
    assert csv.exists() and len(pd.read_csv(csv)) == len(df)


def test_run_speeds_scores_every_factor_at_every_speed(tmp_path):
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.zoo import build_zoo, Factor
    from alpha_factory.report import run_speeds, render
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:20] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_speeds(panel, zoo, cfg)
    assert len(df) == len(zoo) * len(cfg.REBALANCE_PERIODS)      # one row per factor×speed
    assert "rebal" in df.columns and set(df.rebal) == set(cfg.REBALANCE_PERIODS)
    planted1 = df[(df.name == "planted") & (df.rebal == 1)].iloc[0]
    assert planted1.verdict == "SURVIVED"                        # survives the pooled FDR + scaled n_trials
    # pooled BH-FDR still controls false discovery: noise survival within the documented bound
    noise_surv = df[(df.name != "planted") & (df.verdict == "SURVIVED")]
    assert len(noise_surv) <= 6                                  # generous ceiling (empirically 0; FDR_Q bounds the expected rate, not a hard count)
    md, csv = render(df, cfg, tmp_path, "TEST")
    assert "rebal" in md.read_text()
    assert len(pd.read_csv(csv)) == len(df)
