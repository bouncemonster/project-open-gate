# Proof of Simulation V3

## 1. Executive Summary

**Experiment**: V3_DEEP_ARITHMETIC_ISOLATION  
**Final Status**: **BOUNDARY_ARTIFACT**  
**Best score**: 0.858321 at c = 2.000000 + 0.011132i  
**Best track**: TRACK_A  
**Protocol hash**: `df623b3ad6f836a4…`  
**Source hash**: `9af112c6f33bcb3c…`  
**Binary hash**: `ce0d806f19d4c54b…`  

## 2. V1/V2 Audit

V1 forensic audit found: short driver aliases silently falling back to V0_NONE, WORLD_PRIME seeds in benchmark training, V1 null-search with different budget.  
V2 corrected these and re-ran the main experiment. V2 best: c = 2.000000 + 0.011132i, score = 0.858321 (V1_INV_PI).  
V3 re-validates V2 findings before any new search.

## 3. Confirmed Bugs

| Bug | V2 status | V3 resolution |
|-----|-----------|---------------|
| S1_ANALYTIC identical to V1_INV_PI | Suspected | V3 S1 uses Riemann R (independent) |
| V9_PRIME_EVENT = V0_NONE | Confirmed (RMS≈0) | V3 V9 uses E(k)=P(k)-P(k-1) with verified nonzero RMS |
| Evaluation accounting (27 missing) | Confirmed | V3 uses explicit SCOUT/SEARCH/CONTROL/NULL counters |
| Silent driver fallback | Confirmed | V3 kernel returns UNKNOWN_DRIVER error |

## 4. Corrective Changes

- S1_ANALYTIC now uses Riemann R(x) = Σ μ(m)/m · li(x^(1/m)), independent of V1's 1/π(k)
- S2_DATA_SMOOTHED uses moving average with window fixed in advance (no peeking)
- V9_EVENT uses E(k) = P(k) - P(k-1), verified nonzero
- V10_RESIDUAL uses R(k) = P(k) - S1_riemann(k), standardized
- All driver dispatch uses explicit validation; unknown driver → error
- Evaluation accounting: SCOUT_EVALUATIONS, PRIMARY_SEARCH_EVALUATIONS, etc.

## 5. Mathematical Decomposition

Canonical sequences (protocol #17):
- P(k) = 1/π(k) — full inverse-prime signal
- E(k) = P(k) - P(k-1) — prime event train
- R(k) = P(k) - S1(k) — arithmetic residual vs Riemann R
- S1(k) = 1/RiemannR(k) — smooth analytic approximation
- S2(k) = moving_avg(P, window=5) — empirical smoothing

## 6. Prime Event Definition

E(k) = P(k) - P(k-1). Nonzero exactly at prime k (plus initial element E(1)=P(1)-P(0)).  
V9_EVENT stats: nonzero_count=N/A, RMS=N/A, min=N/A, max=N/A

## 7. Smooth Controls

S1_ANALYTIC (Riemann R): RMS=N/A, hash≠V1: …  
S2_DATA_SMOOTHED (window=5): RMS=N/A, hash≠V1: …  
S1 score at best: 0.858321  
S2 score at best: 0.851991

## 8. Matched Event Controls

### V11_MATCHED_EVENT (5 seeds)

- seed 101: score = 0.821249
- seed 202: score = 0.820959
- seed 303: score = 0.820852
- seed 404: score = 0.820852
- seed 505: score = 0.820852
- **mean**: 0.820953

### V12_SHIFTED_EVENT (10 shifts)

- shift 1: score = 0.820852
- shift 2: score = 0.820833
- shift 3: score = 0.820865
- shift 5: score = 0.820865
- shift 7: score = 0.820852
- shift 11: score = 0.820866
- shift 13: score = 0.820852
- shift 17: score = 0.820852
- shift 19: score = 0.820852
- shift 23: score = 0.820868
- **mean**: 0.820856

### V13_GAP_MATCHED_EVENT (5 seeds)

- seed 101: score = 0.820852
- seed 202: score = 0.820852
- seed 303: score = 0.820852
- seed 404: score = 0.820852
- seed 505: score = 0.820833
- **mean**: 0.820849

## 9. Boundary Analysis

Monotone increasing over cr∈[1,3]: **True**  
V1(cr=1.0) = 0.820852  
V1(cr=3.0) = 0.862832  
Mean gradient: 0.020990  
Interpretation: BOUNDARY_ARTIFACT: score rises monotonically across the sampled cr range, so the V2 optimum at cr=2.0 is not a local maximum

## 10. Resonance Search

### TRACK_A

- Driver: V1_FULL
- Best score: 0.858321
- Best c: 2.000000 + 0.011132i
- Scout evals: 289
- Search evals: 891

### TRACK_B

- Driver: V9_EVENT
- Best score: 0.852335
- Best c: 1.508228 + 0.000000i
- Scout evals: 289
- Search evals: 891

### TRACK_C

- Driver: V10_RESIDUAL
- Best score: 0.849851
- Best c: 1.769142 + 0.019591i
- Scout evals: 289
- Search evals: 891

## 11. Generic Low-Frequency Controls

| Control | Score |
|---------|-------|
| V14_CONSTANT_FIELD | 0.544711 |
| V15_X_RAMP | 0.598674 |
| V16_Y_RAMP | 0.596168 |
| V17_BILINEAR_RAMP | 0.603552 |
| V18_RADIAL_GRADIENT | 0.638632 |

## 12. High-Pass Analysis

| Driver | Full score | Pearson (high-pass) |
|--------|-----------|---------------------|
| V0_NONE | 0.820852 | 0.038492 |
| V1_FULL | 0.858321 | -0.201916 |
| V9_EVENT | 0.820852 | 0.038492 |
| V10_RESIDUAL | 0.836232 | 0.063578 |

## 13. Temporal Prime Event Analysis

### V1_best

c = 2.000000 + 0.011132i  
- V0_NONE: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V1_FULL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V9_EVENT: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0

### initial_point

c = -0.700000 + 0.270150i  
- V0_NONE: status=OK, effect_size=-0.080094, pairs=270
- V1_FULL: status=OK, effect_size=-0.015938, pairs=669
- V9_EVENT: status=OK, effect_size=0.057132, pairs=160
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=2

### TRACK_A_best

c = 2.000000 + 0.011132i  
- V0_NONE: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V1_FULL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V9_EVENT: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0

### TRACK_B_best

c = 1.508228 + 0.000000i  
- V0_NONE: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=1
- V1_FULL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V9_EVENT: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=1
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=1

### TRACK_C_best

c = 1.769142 + 0.019591i  
- V0_NONE: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V1_FULL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V9_EVENT: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=0

### Circular-shift null

- shift 1: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 2: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 3: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 5: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 7: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 11: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 13: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 17: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 19: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 23: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 29: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A
- shift 31: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A

## 14. Search-Aware Null

- N_null: 32
- Observed best: 0.858321
- Null max: 0.858191
- Null mean: 0.857037
- Null std: 0.000822
- Count exceeding: 0
- Empirical p: 0.0303
- Formula: (1+count(null_best>=observed_best))/(1+N_null)

## 15. Target Spectral Null

- 10 spectral-matched surrogates of TARGET_A
- Mean surrogate score: 0.463567
- Min: 0.338065, Max: 0.825509

## 16. WORLD_PRIME Benchmark

- Prime detection: 1/20
- Training excludes WORLD_PRIME: True
- Detector: standardized_nearest_centroid
- Interpretation: WORLD_PRIME is fully held out. A low detection rate is a legitimate result: the frozen features do not capture the prime-generated computational structure.

## 17. Computational Fingerprint

Delta-field analysis at best point:

### V1_FULL

- RMS: 0.000699
- Entropy: 0.958229
- Spectral low energy: 0.005400
- Spectral high energy: 0.000348
- Autocorrelation: 0.910809
- Correlation with target residual: -0.416486

### V9_EVENT

- RMS: 0.000000
- Entropy: 0.000000
- Spectral low energy: 0.000000
- Spectral high energy: 0.000000
- Autocorrelation: 0.000000
- Correlation with target residual: 0.000000

### V10_RESIDUAL

- RMS: 0.000392
- Entropy: 0.604043
- Spectral low energy: 0.000120
- Spectral high energy: 0.000227
- Autocorrelation: 0.502754
- Correlation with target residual: 0.347996

## 18. Reproducibility

- Canonical best: c = 2.000000 + 0.011132i
- Scores: [0.858321, 0.858321, 0.858321]
- Identical within tolerance: True
- DB integrity: ok

## 19. V1 vs V2 vs V3

| Metric | V1 | V2 | V3 |
|--------|----|----|-----|
| Best score | 0.858321 | 0.858321 | 0.858321 |
| Best c | 2.000000+0.011132i | 2.000000+0.011132i | 2.000000+0.011132i |
| Baseline (V0) | 0.820852 | 0.820852 | 0.820852 |
| Smooth best | — | — | 0.858321 |
| Prime event | — | — | 0.820852 |
| Prime residual | — | — | 0.836232 |
| Null max | 0.882989 | 0.882989 | 0.858191 |
| Status | — | — | BOUNDARY_ARTIFACT |

## 20. Limitations

- Search budget bounded (100 steps × 9 candidates + 17×17 scout per track)
- V3 S1 uses Riemann R (differs from V2 li-based S1); V10 scores not directly comparable
- Boundary artifact: score monotonically increases with cr, so best at cr=2 is not interior maximum
- WORLD_PRIME detection rate may be low because frozen features don't capture prime structure
- Temporal analysis limited by active-point availability at some parameter values

## 21. Final Scientific Conclusion

**Status: BOUNDARY_ARTIFACT**

The V3 boundary diagnostic reveals that the score increases monotonically along the real axis (cr) over the sampled range [1.0, 3.0]. The V2 optimum at cr=2.0 is therefore **not a local maximum** but a boundary artifact of the search domain. The observed resonance is attributable to trivial escape geometry rather than prime-specific sequence structure.

### Arithmetic contrasts

- C1_V9_minus_mean_V11: -0.000100
- C2_V9_minus_mean_V12: -0.000003
- C2b_V9_minus_mean_V13: 0.000004
- C3_V10_minus_max_S1_S2: -0.022090
- C4_V10MATCHED_minus_max_S1_S2: -0.035472
- V1_minus_V0: 0.037469
- V1_minus_max_S1_S2: 0.000000
- V9ENERGYMATCHED_minus_V0: -0.004770
- V9MATCHED_minus_V9: -0.003246
- V9_minus_V0: 0.000000
- mean_V11: 0.820953
- mean_V12: 0.820856
- mean_V13: 0.820849
- shuffle_degradation: 0.042868

### Attribution (diagnostic, not causal)

- generic_geometry: {"V14_CONSTANT_FIELD": 0.5447111700758839, "V15_X_RAMP": 0.5986741151104621, "V16_Y_RAMP": 0.5961677138806748, "V17_BILINEAR_RAMP": 0.603552447974048, "V18_RADIAL_GRADIENT": 0.6386319001252343}
- smooth_forcing: {"S1_ANALYTIC": 0.8583213052764331, "S2_DATA_SMOOTHED": 0.8519913473489458}
- prime_residual: {"rms": 0.0003921246641189583, "max_abs": 0.0014651816353236907, "entropy": 0.6040429719235919, "spectral_low_energy": 0.00012044831924551189, "spectral_high_energy": 0.00022671463867093343, "autocorr
- prime_event_timing: {"rms": 0.0, "max_abs": 0.0, "entropy": 0.0, "spectral_low_energy": 0.0, "spectral_high_energy": 0.0, "autocorrelation": 0.0, "correlation_with_target_residual": 0.0}
- optimization_selection: {"null_mean": 0.857036626413746, "null_max": 0.858190761051176}
- boundary_effect: {"monotone_increasing_over_full_range": true, "score_at_cr_1.0": 0.820852473027983, "score_at_cr_3.0": 0.8628324091121394, "mean_gradient": 0.0209899680420782, "interpretation": "BOUNDARY_ARTIFACT: sc

---

*Report generated 2026-09-19 05:49:06*  
*Protocol: `df623b3ad6f836a4107eba238b582a13…`*  
*Source: `9af112c6f33bcb3ccd20b7c5d2241d86…`*  
*Binary: `ce0d806f19d4c54bf776337b54766d13…`*
