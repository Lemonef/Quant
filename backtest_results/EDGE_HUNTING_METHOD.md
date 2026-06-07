# Edge-hunting method (repeatable) + scanner results

How to find new edges — the pipeline I used, so it can be repeated forever.

## The pipeline
1. **Hypothesis from a real mechanism** — not a chart shape. (liquidation cascade over-shoots; oversold
   snaps back; funding gets paid; new listings pump.) Mechanism > pattern.
2. **Expectancy scan (cheap first filter)** — `edge_scanner.py`: after the signal, is the pooled avg
   forward return ≫ the unconditional baseline? Big |edge| + decent hit-rate + enough samples → proceed.
3. **Minimal strategy → out-of-sample test** — does the edge survive 2024-26 OOS, not just full-sample?
4. **Correlation to the existing book** ← the decisive filter. Uncorrelated = it adds value even if weak.
5. **Develop** — sizing (magnitude), exits (bounce target), filters (knife/regime) → re-test OOS.
6. **Blend test** — does it raise the combined book's OOS Sharpe / cut DD?

## Scanner results (13 hypotheses, 4h forward 6 bars, 25 coins 2021-2026)
| Signal | n | avg fwd% | hit% | EDGE% (vs base 0.17) |
|---|---|---|---|---|
| flush <−10% (reversion) | 688 | 6.62 | 70.2 | **+6.46** |
| pump >+10% (continues) | 1105 | 3.59 | 50.0 | +3.42 (momentum→overlaps trend) |
| RSI14<25 oversold | 5191 | 1.64 | 59.8 | **+1.48** |
| RSI14>75 | 5726 | 1.29 | 45.0 | +1.12 |
| 3+ATR above MA20 | 6854 | 1.06 | 46.3 | +0.90 |
| vol-spike+red | 2796 | 0.82 | 55.4 | +0.66 |
| 3+ATR below MA20 | 5529 | 0.79 | 58.0 | +0.62 |
| new 50-bar high | 18020 | 0.58 | 46.2 | +0.42 (→trend) |
| RSI2<5 / RSI2>95 / 3-bar / inside-bar | many | ~0.5 | ~50 | <0.4 (noise) |

→ Real edges: **flush** (deep reversion) and **RSI14<25** (frequent oversold reversion). Momentum
signals overlap trend. Most micro-patterns are noise — the scanner separates signal from noise fast.

## New edge developed: RSI14<25 oversold reversion
- Standalone OOS Sharpe **0.96**, but high full DD (24.7% — buys dips incl. in bears; add a knife/regime
  filter to tame standalone).
- **Correlation to trend = 0.00**, to flush = 0.49 (both dip-buyers).
- Adding it: book OOS Sharpe 1.05 → **1.18-1.22**, DD 12.9% → **8.6%**. Genuine improvement.

## Current edge book (OOS, validated)
trend (momentum) + flush (deep-flush reversion) + rsirev (oversold reversion) [+ carry, market-neutral].
Blend OOS Sharpe ~1.2, DD ~9% — vs trend-alone 0.86 / 18%. Each uncorrelated edge stacks.

## Keep hunting
The scanner is the tool — add hypotheses (funding extremes, day-of-week, OI/volume regimes, cross-coin
dispersion, new-listing windows) and re-run. Each real, uncorrelated edge found lifts the whole book.
The work never ends; that's how the edge stays alive as old ones decay.
