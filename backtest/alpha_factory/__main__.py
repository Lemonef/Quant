import argparse, datetime as dt
from pathlib import Path
from . import config as cfg
from .zoo import build_zoo
from .report import run_speeds, render

def main():
    ap = argparse.ArgumentParser(description="Alpha Factory: test the whole zoo, honestly.")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "backtest_results"))
    ap.add_argument("--synth", action="store_true", help="run on synthetic data (demo/self-check)")
    a = ap.parse_args()
    if a.synth:
        from .panel import build_synth_panel
        panel, _ = build_synth_panel(seed=11, signal_strength=0.3)
    else:
        from .panel import build_panel
        panel = build_panel(a.data_dir)
    zoo = build_zoo()
    print(f"panel: {len(panel.close)} days x {len(panel.coins)} coins · zoo: {len(zoo)} factors")
    df = run_speeds(panel, zoo, cfg)
    stamp = dt.date.today().isoformat()
    md, csv = render(df, cfg, a.out, stamp)
    print(f"wrote {md}\nwrote {csv}")
    print(df[df.verdict == "SURVIVED"][["name", "rebal", "ls_sharpe", "dsr_prob", "delta_sharpe", "improves_book"]]
          .to_string(index=False))

if __name__ == "__main__":
    main()
