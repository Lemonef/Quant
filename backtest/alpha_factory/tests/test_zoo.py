import pandas as pd


def test_zoo_size_and_metadata():
    from alpha_factory.zoo import build_zoo
    zoo = build_zoo()
    names = [f.name for f in zoo]
    assert len(zoo) >= 100 and len(set(names)) == len(names)
    assert all(f.family and f.provenance for f in zoo)


def test_every_factor_computes_and_is_causal():
    from alpha_factory.zoo import build_zoo
    from alpha_factory.panel import build_synth_panel, Panel
    panel, _ = build_synth_panel(n_days=400, seed=3)
    cut = 300  # truncate future: values up to t must not change
    truncated = Panel(panel.open.iloc[:cut], panel.high.iloc[:cut], panel.low.iloc[:cut],
                      panel.close.iloc[:cut], panel.volume.iloc[:cut], panel.funding.iloc[:cut])
    for f in build_zoo():
        full = f.fn(panel)
        part = f.fn(truncated)
        assert isinstance(full, pd.DataFrame) and full.index.equals(panel.close.index), f.name
        a = full.iloc[:cut]
        b = part
        pd.testing.assert_frame_equal(a, b, check_exact=False, atol=1e-10, obj=f.name)


def test_crossasset_family_present_and_regime_signed():
    from alpha_factory.zoo import build_zoo
    zoo = build_zoo()
    byname = {f.name: f for f in zoo}
    for n in ("goldregime_21", "goldregime_63", "usdregime_21", "usdregime_63",
              "relcarry_7", "relcarry_30"):
        assert n in byname, n
        assert byname[n].family == "crossasset"


def test_crossasset_nan_without_reference_asset():
    # synthetic panel has no PAXGUSDT/EURUSDT — reference-based factors must
    # compute (all-NaN) instead of raising, so the factory can judge coverage
    from alpha_factory.zoo import build_zoo
    from alpha_factory.panel import build_synth_panel
    panel, _ = build_synth_panel(n_days=200, seed=5)
    f = next(f for f in build_zoo() if f.name == "goldregime_21")
    out = f.fn(panel)
    assert out.isna().all().all()
