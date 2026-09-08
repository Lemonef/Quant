# Confidence curve — is the edge concentrated?

pooled bars=8138, base rate=0.1875, round-trip cost=0.1100%

| p_low >= | n | precision | lift vs base | mean fwd5 net | mean fwd10 net | mean fwd20 net |
|---|---:|---:|---:|---:|---:|---:|
| 0.50 | 707 | 0.324 | 1.73x | 0.0438% | -0.3058% | -0.7668% |
| 0.60 | 528 | 0.326 | 1.74x | 0.1250% | -0.0893% | -0.5228% |
| 0.70 | 340 | 0.332 | 1.77x | -0.4312% | -0.4957% | -0.8664% |
| 0.80 | 195 | 0.318 | 1.70x | -0.5762% | -0.6659% | -0.9689% |
| 0.90 | 77 | 0.325 | 1.73x | -1.0967% | -1.0133% | 0.5731% |

READ: if precision AND net forward return both rise with the threshold, the flip machine was wasting the edge by trading everything at 0.5 and there is real headroom. If precision rises but net forward return stays <= 0, the label is detectable and NOT tradeable — the idea is closed on its own evidence.