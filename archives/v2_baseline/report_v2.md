# Proof of Simulation V2 — Corrected Arithmetic Isolation Report

Generated: 2026-09-19 03:41:53

## 1. Executive Summary

The V2 experiment completed with a best resonance score of **0.858321** using driver V1_INV_PI at c = 2.000000 + 0.011132i (track: TRACK_A).

Total search evaluations: 3540 across 3 tracks.

## 2. Provenance and Hashes

| Item | Hash |
|------|------|
| Protocol V2 | `3dcfe1daf0c73a63a0fd6b5fa5c1aa07e543b785bfa48e3a240c103edfb84309` |
| Source V2 | `c45e316f7938d1b79d7f066cce8797abfb8a060cbbc41ee55d7909e1440a4c06` |
| Binary V2 | `fcc9372b307fb16204735571a2ecdd4ecc5cef26e60a74a33f2a53c1be7a2384` |
| OS | Windows 10 |
| Python | 3.12.10 |
| CPU | Intel64 Family 6 Model 63 Stepping 2, GenuineIntel |

## 3. V1 Forensic Audit Summary

V1 baseline preserved at `archives/v1_baseline/` (29 files, SHA-256 verified).
Key V1 findings:
- **Conclusion-changing bug**: Short driver aliases (V1/V4) silently fell back to V0_NONE
- **Benchmark leakage**: WORLD_PRIME seeds entered training data
- **Null mismatch**: V1 null used different search budget than primary
- V1 does not establish a prime-specific advantage

## 4. V2 Preregistered Protocol

- Domain: [-2,2]^2 (expanded from V1 [-1.5,1.0]x[-1.2,1.2])
- Dynamics: z(k) = z(k-1)^2 + c + alpha*D(k), alpha=1, k starts at 1
- Grid: 60x30, bounded 2..512; iterations 1..20000
- 16 drivers: V0-V13 + S1 + S2
- Primary target: TARGET_A = |sin(pi*u)*cos(pi*v)|
- Score weights: Pearson=0.25, Spearman=MAE=Gradient=Spectral=AutoCorr=0.15
- Search: 17x17 scout (289) + 100 steps x 9 candidates = 1189 per run
- Tracks: A=V1_INV_PI, B=V10_PRIME_RESIDUAL, C=V9_PRIME_EVENT
- Seeds: 133742 (primary), 233742, 333742 (repeats)
- Null: 8 runs, DCT sign surrogates (seeds 1001-1008)

## 5. Search Results

| Track | Driver | Seed | Best Score | Best CR | Best CI |
|-------|--------|------|------------|---------|---------|
| TRACK_A | V1_INV_PI | 133742 | 0.858321 | 2.000000 | 0.011132 |
| TRACK_B | V10_PRIME_RESIDUAL | 133742 | 0.844929 | 1.995784 | 0.516689 |
| TRACK_C | V9_PRIME_EVENT | 133742 | 0.852335 | 1.508228 | 0.000000 |

## 6. Control Models at Best Point

Best point: c = 2.000000 + 0.011132i

| Driver | Score | Pearson | Spearman | MAE | Gradient | Spectral | AutoCorr |
|--------|-------|---------|----------|-----|----------|----------|----------|
| V0_NONE | 0.820852 | 0.876000 | 0.871193 | 0.598471 | 0.660884 | 0.884972 | 0.996830 |
| V1_INV_PI | 0.858321 | 0.910834 | 0.901247 | 0.596870 | 0.793863 | 0.914198 | 0.997907 |
| V2_SMOOTH | 0.858862 | 0.911167 | 0.901814 | 0.596758 | 0.796207 | 0.914511 | 0.997844 |
| V3_CENTERED_INV_PI | 0.852436 | 0.909002 | 0.900375 | 0.596969 | 0.759614 | 0.913149 | 0.997794 |
| V4_PRIME_RESIDUAL | 0.843952 | 0.901081 | 0.892157 | 0.600307 | 0.727241 | 0.907354 | 0.997484 |
| V5_SHUFFLED | 0.808165 | 0.858326 | 0.854424 | 0.598350 | 0.638608 | 0.869511 | 0.996333 |
| V6_REVERSED | 0.815566 | 0.868416 | 0.863241 | 0.598456 | 0.653377 | 0.877940 | 0.996733 |
| V8_PHASE_RANDOMIZED | 0.834976 | 0.890631 | 0.886554 | 0.598649 | 0.702275 | 0.897346 | 0.997296 |
| V9_PRIME_EVENT | 0.820852 | 0.876000 | 0.871193 | 0.598471 | 0.660884 | 0.884972 | 0.996830 |
| V10_PRIME_RESIDUAL | 0.843952 | 0.901081 | 0.892157 | 0.600307 | 0.727241 | 0.907354 | 0.997484 |
| S1_ANALYTIC | 0.858321 | 0.910834 | 0.901247 | 0.596870 | 0.793863 | 0.914198 | 0.997907 |
| S2_DATA_SMOOTHED | 0.851991 | 0.908495 | 0.900094 | 0.597011 | 0.758245 | 0.912653 | 0.997782 |

## 7. Primary Contrasts

| Contrast | Value |
|----------|-------|
| V1_minus_V0 | +0.037469 |
| V1_minus_max_S1_S2 | +0.000000 |
| V9_minus_mean_V11 | +0.000067 |
| V9_minus_mean_V12 | -0.004844 |
| V10_minus_max_S1_S2 | -0.014369 |
| residual_uplift_V10_S1 | -0.014369 |
| shuffle_degradation | +0.050156 |

## 8. Search-Aware Null

- Observed best: 0.858321
- Null runs: 8
- Null mean: 0.721818
- Null std: 0.120333
- Null median: 0.665709
- Null max: 0.882989
- Observed minus null mean: +0.136504
- Observed minus null max: -0.024667
- Percentile: 75.0%
- Empirical search null: 0.3333333333333333
- Minimum attainable: 0.1111111111111111
- Null maxima: 0.849110, 0.882989, 0.860268, 0.614604, 0.599429, 0.636722, 0.666385, 0.665033

## 9. Validation

### 9.1 Depth Stability

- Depth 200: 0.858321
- Depth 500: 0.858045
- Depth 1000: 0.857952
- Depth 1500: 0.857922
- Depth 2000: 0.857906
- Range: 0.000415 (STABLE)

### 9.2 Resolution Stability

- 60x30: 0.858321
- 120x60: 0.854984

### 9.3 Alpha Sensitivity

- Alpha 0.25: 0.824233
- Alpha 0.5: 0.837476
- Alpha 1.0: 0.858321
- Alpha 2.0: 0.862832

### 9.4 Local Stability

- (+0.0010, +0.0000): 0.858328
- (-0.0010, +0.0000): 0.858311
- (+0.0000, +0.0010): 0.858315
- (+0.0000, -0.0010): 0.858319

### 9.5 Holdout Targets

- TARGET_B: 0.889939
- TARGET_PHASE: 0.820305

Eigenmode holdouts (T_nm, n,m=1..4):

  T_1_1: 0.717107
  T_1_2: 0.750486
  T_1_3: 0.744047
  T_1_4: 0.755549
  T_2_1: 0.588459
  T_2_2: 0.608571
  T_2_3: 0.596981
  T_2_4: 0.583515
  T_3_1: 0.588467
  T_3_2: 0.607949
  T_3_3: 0.593570
  T_3_4: 0.579314
  T_4_1: 0.577507
  T_4_2: 0.598023
  T_4_3: 0.580459
  T_4_4: 0.567212

### 9.6 Reproducibility

- Run 1: 0.858321
- Run 2: 0.858321
- Run 3: 0.858321
- **Identical across all runs**

## 10. Temporal Analysis

Temporal analysis at c = -0.700000 + 0.270150i (interior point, 1000 iterations, 60x30 grid).

### V1_INV_PI

- Status: OK
- Pair count: 166
- Mean difference: -0.005 (baseline-adjusted contrast)
- Effect size: -0.082
- Bootstrap 95% CI: [-0.021, 0.007]
- Permutation p (two-sided): 0.267
- Interpretation: No significant temporal signal; CI includes zero

### V9_PRIME_EVENT

- Status: OK
- Pair count: 158
- Mean difference: +0.001
- Effect size: +0.019
- Bootstrap 95% CI: [-0.029, 0.039]
- Permutation p (two-sided): 0.807
- Interpretation: No significant temporal signal; CI includes zero

### V10_PRIME_RESIDUAL

- Status: INSUFFICIENT_ACTIVE_DATA
- V10 driver produces different escape dynamics; insufficient active pairs at this point

## 11. Synthetic World Benchmark V2

- train: accuracy=0.8571428571428571
- validation: accuracy=0.8571428571428571
- holdout: accuracy=0.6285714285714286
- Prime detection: 1/20 (5%)
- Distinct prime hashes: 20
- Adversarial accuracy: 0.8666666666666667

## 12. Status Determination

**Status: GENERIC_RESONANCE**

Score above 0.6 but no consistent matched-control evidence for prime specificity.

## 13. Limitations

- Only 8 null runs; minimum attainable empirical p is 1/9
- Hill climbing may miss global optima in [-2,2]^2
- Single primary target (TARGET_A) drives optimization
- Temporal analysis assumes exchangeable within-pair labels
- No external ML detection (by design)
- Multiplicity unadjusted across tracks and contrasts
- With only eight nulls, strength is exploratory
- Maximum at <5% of boundary is flagged

## 14. Conclusion

This experiment does not establish that physical reality is simulated.
It establishes, at most, the presence or absence of a reproducible
computational pattern within the tested mathematical systems.

V2 corrects the V1 driver dispatch bug, benchmark leakage, and null mismatch.
All V2 results are independently reproducible from the hashes above.
