# Proof of Simulation — Experimental Report

Generated: 2026-09-19 02:39:29

## 1. Executive Summary

The experiment completed with a best resonance score of **0.830429** using model **V1_INV_PI** at c = 0.983188 + -0.005867i.
Total evaluations: 3242.

## 2. Research Question

Can prime-arithmetic forcing in a non-autonomous Julia set system
produce reproducible spatial resonance patterns that cannot be explained
by smooth forcing, random coincidence, or ordinary Julia dynamics?

## 3. Exact Protocol

- Protocol version: 1.0.0
- Protocol hash: `aefd85c1b24cfbe51d67454cb37fbc0e839c21cfe260d215f08c4bd2e29dfea8`
- Source hash: `e521421d5d037200b3ad2e2bababebc78cad835990a15673ecad597755c37c2c`
- Grid: 60x30 (1800 cells)
- Score weights: Pearson=0.25, Spearman=0.15, MAE=0.15, Gradient=0.15, Spectral=0.15, AutoCorr=0.15
- Search budget: 100 logical steps (~900 evaluations)
- Time budget: 300s

## 4. Computational Environment

- OS: Windows 10
- Python: 3.12.10
- CPU: Intel64 Family 6 Model 63 Stepping 2, GenuineIntel
- Machine: AMD64

## 5. Mathematical Model

Base equation: z_{n+1} = z_n^2 + c + alpha * D(k)

where D(k) is a deterministic forcing function dependent on iteration number k.

## 6. Prime Arithmetic Drivers

| Driver | Description |
|--------|-------------|
| V0_NONE | Baseline Julia (no forcing) |
| V1_INV_PI | D(k) = 1/pi(k) |
| V2_SMOOTH | Smooth surrogate matched to V1 mean/std |
| V3_CENTERED_INV_PI | D(k) = 1/pi(k) - mean |
| V4_PRIME_RESIDUAL | D(k) = (1/pi(k) - smooth) / std |
| V5_SHUFFLED | Shuffled 1/pi(k) (seed=7331) |
| V6_REVERSED | Reversed 1/pi(k) |
| V7_IMAGINARY | Forcing on imaginary component |
| V8_PHASE_RANDOMIZED | Phase-randomized surrogate |

## 7. Target Functions

- TARGET_A: |sin(pi*u) * cos(pi*v)| (primary optimization target)
- TARGET_B: sin^2(pi*u) * cos^2(pi*v) (holdout)
- TARGET_PHASE: |sin(pi*(u+0.07)) * cos(pi*(v-0.11))| (holdout)
- T_nm: sin^2(n*pi*u) * sin^2(m*pi*v) for n,m in {1,2,3,4} (16 holdout eigenmodes)

## 8. Resonance Metric

Composite score = 0.25*Pearson01 + 0.15*Spearman01 + 0.15*MAE01 + 0.15*Gradient01 + 0.15*Spectral01 + 0.15*Autocorrelation01

## 9. Search Procedure

- Algorithm: Hill Climbing + 8-direction local search + deterministic mutation
- Two research tracks: TRACK_A (V1_INV_PI), TRACK_B (V4_PRIME_RESIDUAL)
- Initial point: cr=-0.7, ci=0.27015
- Initial step: 0.02, min: 0.00001, max: 0.20
- Multi-start after 20 steps without improvement
- Coarse scout: max 2x, 11x11 grid

## 10. Best Found Point

| Parameter | Value |
|-----------|-------|
| Best score | 0.830429 |
| Best cr | 0.983188 |
| Best ci | -0.005867 |
| Best model | V1_INV_PI |
| Best driver | V1 |
| Degree | 2 |
| Alpha | 1.0 |
| Max iter | 200 |
| Total evaluations | 3242 |
| Protocol hash | `aefd85c1b24cfbe51d67454cb37fbc0e839c21cfe260d215f08c4bd2e29dfea8` |

## 11. Spatial Evidence

| Metric | Value |
|--------|-------|
| Pearson01 | 0.891802 |
| Spearman01 | 0.890916 |
| MAE01 | 0.602684 |
| Gradient01 | 0.644090 |
| Spectral01 | 0.912882 |
| Autocorrelation01 | 0.999284 |

## 12. Temporal Evidence

Temporal analysis pending (requires trace mode data).

## 13. Control Models

| Model | Score | Pearson | Spectral | Gradient | AutoCorr |
|-------|-------|---------|----------|----------|----------|
| V0_NONE | 0.830429 | 0.891802 | 0.912882 | 0.644090 | 0.999284 |
| V1_INV_PI | 0.830429 | 0.891802 | 0.912882 | 0.644090 | 0.999284 |
| V2_SMOOTH | 0.846446 | 0.902398 | 0.907771 | 0.738123 | 0.998002 |
| V3_CENTERED_INV_PI | 0.835258 | 0.890715 | 0.897400 | 0.703647 | 0.997271 |
| V5_SHUFFLED | 0.823638 | 0.881486 | 0.910110 | 0.617602 | 0.998780 |
| V6_REVERSED | 0.827965 | 0.889210 | 0.910954 | 0.636859 | 0.999267 |

## 14. Prime-Specific Controls

- Prime uplift: -0.0160
- Residual uplift: -0.0160
- Order uplift: 0.0068
- Direction uplift: 0.0025
- Shuffle degradation: 0.0068

## 15. Holdout Targets

Holdout evaluation pending.

## 16. Null Search

| Null Type | Seed | Best Score | Best CR | Best CI | Model |
|-----------|------|------------|---------|---------|-------|
| RANDOM_PARAMETER_SEARCH | 10000 | 0.851453 | 0.487626 | -0.175076 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10001 | 0.851138 | 0.564048 | -0.235094 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10002 | 0.849964 | 0.576945 | -0.254557 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10003 | 0.851710 | 0.567679 | -0.076057 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10004 | 0.851031 | 0.549786 | 0.080910 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10005 | 0.851066 | 0.480328 | -0.228243 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10006 | 0.850803 | 0.532995 | -0.116605 | V1_INV_PI |
| RANDOM_PARAMETER_SEARCH | 10007 | 0.851766 | 0.566536 | 0.091804 | V1_INV_PI |

- Observed best: 0.830429
- Null max: 0.851766
- Null mean: 0.851116
- Empirical search-based null estimate: 1.0000

## 17. Multiple Testing

- Total evaluations: 3242
- Number of models tested: 7
- Number of null runs: 8

## 18. Iteration Stability

| Max Iter | Score | Status |
|----------|-------|--------|
| 200 | 0.823993 | OK |
| 500 | 0.823569 | OK |
| 1000 | 0.823428 | OK |
| 1500 | 0.823381 | OK |
| 2000 | 0.823357 | OK |

## 19. Resolution Stability

Resolution validation pending.

## 20. Finite Precision

Finite precision validation pending.

## 21. Pixelization and Periodicity

Pending analysis.

## 22. Synthetic World Benchmark

- Train accuracy: 98.75%
- Holdout accuracy: 100.00%

## 23. Computational Fingerprint

- Entropy: 0.000000
- Anisotropy: 0.033303
- Compression ratio: 0.001111
- Escaped fraction: 1.000000

## 24. Limitations

- 60x30 grid resolution limits spatial detail
- max_iter=200 limits depth exploration
- Hill climbing may miss global optima
- No external ML-based detection (by design)
- Single-target optimization (TARGET_A only)

## 25. Interpretation

No convincing prime-specific signal was established.

## 26. Conclusion

This experiment does not establish that physical reality is simulated.
It establishes, at most, the presence or absence of a reproducible
computational pattern within the tested mathematical systems.

### Result Level

**LEVEL 4**
(Effect stable across depth and resolution)

### Final Scientific Answers

1. **Was high resonance found?** No
2. **Does it exceed baseline Julia?** Unclear
3. **Does it exceed smooth surrogate?** Unclear
4. **Does prime-order matter?** Unclear
5. **Depth stable?** YES
6. **Resolution stable?** Pending (requires multi-resolution kernel)
7. **Holdout stable?** Pending
8. **Explained by random-search null?** Yes
9. **Detector finds known computational worlds?** Yes
10. **Computational-like fingerprint?** Available
