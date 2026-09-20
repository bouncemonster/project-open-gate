# Proof of Simulation V4

## 1. Executive Summary

**Experiment**: V4_INTERIOR_DYNAMICS_PRIME_CONTRAST  
**Final Status**: **NO_PRIME_SPECIFIC_SIGNAL**  
**Best contrast**: 0.079369 (track TRACK_A)  
**Best score**: 0.818943 at c = 0.190559 + -0.398827i  
**Protocol hash**: `1ef8fb7fec1a685d…`  
**Source hash**: `6480c16cb7e5ac92…`  
**Binary hash**: `b9da9d6d75498e44…`  

## 2. V3 Audit

V3 established STATUS = BOUNDARY_ARTIFACT with best score 0.858321 at cr=2.0.  
V3 key findings:  
- V1_INV_PI = 0.858321, V0_BASELINE = 0.820852, S1_SMOOTH = 0.858321  
- V9 vs matched events ≈ 0  
- V2 best on boundary cr=2 (monotone increasing)  
V4 addresses this by searching the interior regime [-1.5, 1.5]².

## 3. Interior Regime Definition

### Admissibility criteria (protocol §5)

- escaped_fraction ∈ [0.05, 0.95]
- normalized_entropy ≥ 0.2
- std(F_smooth) ≥ 0.05

### Interior scout results

- Total scout points: 289
- Admissible points: 39
- Domain: [-1.5, 1.5, -1.5, 1.5]

### S1 audit

- Riemann R stability at small k: OK
- S1 vs V1 max_abs_diff: N/A
- S1 vs V1 correlation: N/A

## 4. Search Domain

- Domain: [-1.5, 1.5, -1.5, 1.5]
- Scout grid: 17×17
- Search steps: 100
- Multi-start count: 8
- Search seeds: [133742, 233742, 333742, 433742, 533742]

## 5. Prime Drivers

| Driver | RMS | Nonzero | Hash |
|--------|-----|---------|------|
| V1_FULL | N/A | N/A | `…` |
| V9_EVENT | N/A | N/A | `…` |
| V10_RESIDUAL | N/A | N/A | `…` |
| S1_ANALYTIC | N/A | N/A | `…` |
| S2_DATA_SMOOTHED | N/A | N/A | `…` |

## 6. Matched Event Controls

### V11_MATCHED_EVENT (permuted positions)

- 101: score = 0.739356
- 202: score = 0.739252
- 303: score = 0.739573
- **mean**: 0.739394

### V12_SHIFTED_EVENT (circular shifts)

- 1: score = 0.748849
- 11: score = 0.740404
- 5: score = 0.740407
- **mean**: 0.743220

### V13_GAP_MATCHED_EVENT (gap-permuted)

- 101: score = 0.746161
- 202: score = 0.747834
- 303: score = 0.744881
- **mean**: 0.746292

## 7. Track-Local Results

### TRACK_A

- Best c: 0.190559 + -0.398827i
- Best contrast: 0.079369
- Best score: 0.818943
- V0=0.739574 V1=0.818943 S1=0.707230 V9=0.747182 V10=0.739666
- C_full=0.079369 C_event=0.007789 C_residual=0.022548
- Boundary distance: 0.367 (interior)

### TRACK_B

- Best c: 0.109480 + -0.597245i
- Best contrast: 0.067671
- Best score: 0.776019
- V0=0.722667 V1=0.742792 S1=0.754778 V9=0.776019 V10=0.721867
- C_full=-0.066746 C_event=0.067671 C_residual=-0.087672
- Boundary distance: 0.301 (interior)

### TRACK_C

- Best c: 0.117588 + -0.213159i
- Best contrast: 0.063868
- Best score: 0.749230
- V0=0.725286 V1=0.673499 S1=0.671530 V9=0.721212 V10=0.749230
- C_full=-0.051787 C_event=-0.002522 C_residual=0.063868
- Boundary distance: 0.429 (interior)

## 8. Boundary Diagnostics

- TRACK_A: distance=0.367 nearest_edge=ci_lo ok
- TRACK_B: distance=0.301 nearest_edge=ci_lo ok
- TRACK_C: distance=0.429 nearest_edge=ci_lo ok

## 9. Prime-Specific Contrasts

| Contrast | Value |
|----------|-------|
| C_full | 0.079369 |
| C_event | 0.007789 |
| C_residual | 0.022548 |
| C_event_all | 0.007511 |
| C_shift_search | 0.003962 |
| C_shift_all | 0.007410 |
| C_gap_search | 0.000890 |
| C_gap_all | -0.000468 |
| V1_minus_V0 | 0.079369 |
| V1_minus_max_S1_S2 | 0.101825 |

## 10. Difference-Field Analysis

| Driver | RMS | Entropy | DCT low | DCT high | Autocorr | Corr w/ target |
|--------|-----|---------|---------|----------|----------|----------------|
| V1_FULL | 0.466936 | 0.234691 | 453.537770 | 148.904361 | 0.909899 | 0.788211 |
| V9_EVENT | 0.234219 | 0.188060 | 1.242702 | 97.671507 | 0.422469 | 0.308752 |
| V10_RESIDUAL | 0.467621 | 0.231732 | 451.922361 | 149.388645 | 0.910084 | 0.786176 |

## 11. High-Pass Analysis

| Driver | Full score | Pearson (high-pass) |
|--------|-----------|---------------------|
| V0_NONE | 0.739574 | -0.076375 |
| V1_FULL | 0.818943 | -0.201967 |
| V9_EVENT | 0.747182 | -0.056895 |
| V10_RESIDUAL | 0.739666 | 0.453431 |

## 12. Temporal Prime Response

### TRACK_A_best

c = 0.190559 + -0.398827i  
- V0_NONE: status=OK, effect_size=0.040545, pairs=669
- V1_FULL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=4
- V9_EVENT: status=OK, effect_size=0.054152, pairs=669
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=2
- V11_matched: status=OK, effect_size=0.044636, pairs=669
- V12_shifted: status=OK, effect_size=0.016934, pairs=669

### TRACK_B_best

c = 0.109480 + -0.597245i  
- V0_NONE: status=OK, effect_size=0.048753, pairs=669
- V1_FULL: status=OK, effect_size=0.418700, pairs=21
- V9_EVENT: status=OK, effect_size=0.064501, pairs=669
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=2
- V11_matched: status=OK, effect_size=0.008166, pairs=669
- V12_shifted: status=OK, effect_size=0.037804, pairs=669

### TRACK_C_best

c = 0.117588 + -0.213159i  
- V0_NONE: status=OK, effect_size=0.032274, pairs=669
- V1_FULL: status=OK, effect_size=0.059319, pairs=669
- V9_EVENT: status=OK, effect_size=0.037250, pairs=669
- V10_RESIDUAL: status=INSUFFICIENT_ACTIVE_DATA, effect_size=N/A, pairs=2
- V11_matched: status=OK, effect_size=0.041623, pairs=669
- V12_shifted: status=OK, effect_size=0.023431, pairs=669

### Circular-shift null

- shift 1: status=OK, effect_size=0.016934
- shift 2: status=OK, effect_size=0.062216
- shift 3: status=OK, effect_size=0.002888
- shift 5: status=OK, effect_size=0.005711
- shift 7: status=OK, effect_size=0.003213
- shift 11: status=OK, effect_size=0.006899
- shift 13: status=OK, effect_size=0.017797
- shift 17: status=OK, effect_size=0.031026
- shift 19: status=OK, effect_size=0.002323
- shift 23: status=OK, effect_size=0.026908
- shift 29: status=OK, effect_size=0.002863
- shift 31: status=OK, effect_size=0.037043
- shift 37: status=OK, effect_size=0.022301
- shift 41: status=OK, effect_size=0.026208
- shift 43: status=OK, effect_size=0.012983
- shift 47: status=OK, effect_size=0.032068

## 13. Search-Aware Null

- N_null: 32
- Observed best: 0.818943
- Null max: 0.852035
- Null mean: 0.851776
- Null std: 0.000191
- Count exceeding: 32
- Empirical p: 1.0000
- Note: exploratory statistic, not confirmatory (protocol §31)

## 14. Spectral Target Null

- N surrogates: 100
- Mean: 0.562291
- Std: 0.184306
- Median: 0.430148
- P90: 0.784049
- P95: 0.793544
- Max: 0.805736

## 15. Holdout Targets

| Target | Score |
|--------|-------|
| TARGET_B | 0.853071 |
| TARGET_PHASE | 0.789648 |
| T_1_1 | 0.695346 |
| T_1_2 | 0.725224 |
| T_1_3 | 0.717784 |
| T_1_4 | 0.729304 |
| T_2_1 | 0.585340 |
| T_2_2 | 0.599946 |
| T_2_3 | 0.589315 |
| T_2_4 | 0.577246 |
| T_3_1 | 0.587733 |
| T_3_2 | 0.601274 |
| T_3_3 | 0.586131 |
| T_3_4 | 0.570806 |
| T_4_1 | 0.571492 |
| T_4_2 | 0.589366 |
| T_4_3 | 0.572249 |
| T_4_4 | 0.555157 |

## 16. Reproducibility

- Canonical best: c = 0.190559 + -0.398827i
- Scores: [0.818943, 0.818943, 0.818943]
- Identical within tolerance: True
- DB integrity: ok

## 17. WORLD_PRIME Detector

- Prime detection: 1/20
- Interpretation: WORLD_PRIME held out; low detection rate is a legitimate detector limitation result.

## 18. V1/V2/V3/V4 Comparison

| Metric | V1 | V2 | V3 | V4 |
|--------|----|----|----|----|
| Best score | 0.858321 | 0.858321 | 0.858321 | 0.818943 |
| Best c | 2+0.011i | 2+0.011i | 2+0.011i | 0.190559+-0.398827i |
| Domain | [-2,2] | [-2,2] | [-2,2] | [-1.5, 1.5, -1.5, 1.5] |
| Objective | raw score | raw score | raw score | contrast |
| Status | — | — | BOUNDARY_ARTIFACT | NO_PRIME_SPECIFIC_SIGNAL |

## 19. Limitations

- Search budget bounded (100 steps × 9 candidates × 4 drivers + scout)
- Interior domain [-1.5, 1.5]² may exclude interesting boundary-adjacent dynamics
- V4 S1 uses Riemann R (differs from kernel li-based S1); V10 not directly comparable to V2
- Temporal analysis limited by active-point availability at some parameter values
- WORLD_PRIME detection rate may be low due to frozen feature limitations
- Contrast-based search is more expensive per step (4× kernel evaluations)

## 20. Final Scientific Conclusion

**Status: NO_PRIME_SPECIFIC_SIGNAL**

After removing boundary effects, smooth forcing, generic low-frequency geometry, event-density effects and search selection bias, no prime-specific component was detected. The observed resonance in V1-V3 is attributable to generic geometric and boundary effects.

### Evidence table

| Evidence | Result |
|----------|--------|
| Interior V1 contrast | 0.079369 |
| Interior V9 contrast | 0.007789 |
| Interior V10 contrast | 0.022548 |
| Matched-event contrast | 0.007511 |
| Shift-event contrast | 0.007410 |
| Gap-matched contrast | -0.000468 |
| High-pass contrast | -0.201967 |
| Temporal prime effect | 0.418700 |
| Null percentile | 100.000000 |
| Spectral-surrogate mean | 0.562291 |
| Depth stability | range=0.820048 |
| Resolution stability | range=0.087839 |

---

*Report generated 2026-09-19 13:00:57*  
*Protocol: `1ef8fb7fec1a685df015098e35fd291d…`*  
*Source: `6480c16cb7e5ac92cce0fedb8f32f0d5…`*  
*Binary: `b9da9d6d75498e44722b127680de179c…`*
