# Validation Horizon Scorecard

Only the leading research candidates and relevant deterministic baselines are
shown. Percentages are balanced accuracy and level-extreme hit rate.

| Candidate | Horizon | Balanced accuracy | Brier | Level-extreme hit | Composite |
|---|---:|---:|---:|---:|---:|
| baseline-momentum-5m | 5m | 42.71% | 0.1949 | 68.69% | 0.5417 |
| empirical-minimal-abstaining-v1 | 5m | 35.38% | 0.2297 | 66.45% | 0.4837 |
| baseline-momentum-5m | 15m | 32.14% | 0.2303 | 54.10% | 0.4440 |
| baseline-no-edge | 15m | 33.33% | 0.2160 | 54.10% | 0.4546 |
| conservative-flow-confirmation-v1 | 15m | 35.94% | 0.2210 | 44.92% | 0.4568 |
| baseline-momentum-5m | 30m | 33.62% | 0.2319 | 45.12% | 0.4398 |
| baseline-no-edge | 30m | 33.33% | 0.2298 | 45.12% | 0.4384 |
| empirical-minimal-abstaining-v1 | 30m | 38.42% | 0.2193 | 45.12% | 0.4736 |

## Interpretation boundary

- No learned 5-minute candidate is competitive with momentum.
- The 15-minute flow candidate is a weak research lead, not an accepted edge.
- The 30-minute empirical candidate is the strongest horizon-specific lead.
- Validation comprises four independent session dates, so these observations
  require session-level stability tests before holdout access.
- The level-extreme metric does not establish support/resistance causality.
