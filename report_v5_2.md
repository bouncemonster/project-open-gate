# Proof of Simulation V5.2 — Adversarial Benchmark (Post-Audit, Corrected)

**Revision 2.** All numbers in this report come from the post-audit run recorded in
`v5_2_artifacts/benchmark/v5_2_results.json`. The first V5.2 run contained 7 method
defects found by self-audit; they are documented in §0 and the numbers below are the
corrected ones. The pre-audit headline (77.08%) was inflated by a slicing bug and is
**retracted**.

## 0. Self-Audit Corrections (what was wrong and what changed)

| # | Defect | Effect before fix | Fix |
|---|--------|------------------|-----|
| 1 | Holdout/training slices `cont[:n] + comp[:n]` were not stratified by generator (worlds list is ordered gen -> seed -> substrate) | ALL 120 computational holdout samples came from G08; G09 "95%" and G10 "100%" were computed on ZERO computational examples. Headline 77.08% invalid | Per-generator stratified selection; headline corrected 77.08% -> **61.25%** |
| 2 | `O6_downsample` was an identity lambda | Falsely reported "robust to downsampling" (0.7708) | Real 2x2 average pooling; result 0.5833 |
| 3 | Histogram-matched control used monotonic quantization: rank-match nearly recovers the original field | Control was near-degenerate (not a real control) | Added non-monotonic S_HASH matched variant |
| 4 | Substrate holdout test set was 500 comp vs 100 cont (5:1) | Raw accuracy meaningless (trivial baseline 83%, not 50%) | Balanced 100:100 (20 per holdout substrate vs 100 continuous refs) |
| 5 | Label permutation judged from a SINGLE permutation | "22.08%" was a coin flip on cluster polarity (any value in ~22–78% is compatible with chance) | 20 permutations; judge by mean |
| 6 | §26 "identical observation" used histogram-matched (NOT identical) fields | Spec §26 test was not actually run | Lossless lookup-table roundtrip; bitwise-identical observations, with assert |
| 7 | `protocol_v5_2.json` loo_substrate mean reported 0.4890 vs actual 0.4928 | Arithmetic slip in documentation | Machine-readable protocol regenerated from results JSON |

Also fixed: §58 `agent_loop.py auto/resume --mode v5.2-deep` integration was missing;
the feature-leakage metric was tautological (unique-float64-value counting -> "31/39
leaking") and was replaced by binned mutual information.

## 1. Research Question

> Given two observationally similar worlds generated from the same underlying
> mathematical content, can an observer distinguish whether the underlying
> computation used a continuous idealized substrate or a finite/discrete
> computational substrate?

This is strictly harder than V5.1's question ("continuous worlds vs computational
worlds") because the generator, statistics, and observation model are controlled.

## 2. V5.1 Baseline

V5.1 achieved 97.5% balanced accuracy on a class-balanced, generator-disjoint holdout.
However, V5.1 conflated:
- Generator type (smooth vs hash vs CA)
- Numerical precision (float64 vs float32)
- Quantization (continuous vs 4-bit)
- Observation representation
- Computational substrate

V5.2 separates these into three explicit layers (GENERATOR -> SUBSTRATE -> OBSERVATION)
and tests them independently. Per §53, the 97.5% is treated as a hypothesis to attack,
not an achievement to preserve.

## 3. Counterfactual World Design

For every base world, paired realizations share:
- Same generator family and mathematical rule
- Same seed and parameters
- Same resolution (60x30)
- Same observation model

Only the SUBSTRATE differs (float64 reference vs one of 9 computational
implementations). This isolates substrate information from all other variables.

## 4. Generator Taxonomy

10 independent mathematical families; no generator family crosses splits:

```
TRAIN:    G01 analytic_smooth     G02 gaussian_correlated   G03 analytic_fractal
          G04 wave_eigenmode      G05 chaotic_map
VALIDATE: G06 nonlinear_dyn       G07 reaction_diffusion
HOLDOUT:  G08 procedural_noise    G09 coupled_oscillator    G10 cosmological_like
```

## 5. Substrate Taxonomy

**Continuous (2):** S_CONTINUOUS (float64 reference), S_UNKNOWN_CONTINUOUS (tanh-scaled float64)

**Computational (9):** S_FLOAT32, S_FLOAT16, S_QUANT_8 (256 levels), S_QUANT_4 (16 levels),
S_LATTICE (4x4 block snapping), S_LOOKUP (16-entry table), S_HASH (coordinate hashing),
S_FINITE_STATE (12-level hysteresis), S_UNKNOWN_COMPUTATIONAL (10-bit XOR modular)

**Substrate splits:** train = {FLOAT32, FLOAT16, QUANT_8, LATTICE};
holdout = {QUANT_4, LOOKUP, HASH, FINITE_STATE, UNKNOWN_COMPUTATIONAL}

## 6. Observation Model

- Primary: 60x30 float64 array (full precision)
- Robustness tests O1–O7: float32, float16, uint8, uint4, real 2x2 downsample, additive noise
- Detector sees ONLY the observation, never generator/substrate metadata

## 7. Generator-Disjoint Benchmark (primary)

Tested on 3 completely unseen generator families, stratified 40/40 per generator:

| Metric | Value |
|--------|-------|
| Balanced accuracy | **61.25%** (was 77.08% pre-audit — retracted, see §0/1) |
| Bootstrap 95% CI | [55.42%, 67.50%] |
| Trivial baseline | 50.00% |
| Holdout size | 240 (120 continuous + 120 computational, balanced per generator) |

Per-generator breakdown (audit-corrected; every generator now has real test both classes):

| Generator | Accuracy | cont/comp | Interpretation |
|-----------|----------|-----------|----------------|
| G08_procedural_noise | 45.0% | 40/40 | BELOW chance — generator-confounded |
| G09_coupled_oscillator | 77.5% | 40/40 | Real but generator-specific signal |
| G10_cosmological_like | 61.3% | 40/40 | Smooth fields quantize visibly |

**V5.1 -> V5.2**: 97.5% -> 61.25%. The pre-audit "G09=95%, G10=100%" figures were
computed on zero computational samples and are void.

## 8. Substrate-Disjoint Benchmark

Trained on known computational substrates, tested on 5 unseen mechanisms,
balanced 100 comp vs 100 continuous (audit-corrected ratio):

| Substrate | Detection Rate (n=20 each) |
|-----------|---------------------------|
| S_QUANT_4 | 100% |
| S_LOOKUP | 100% |
| S_FINITE_STATE | 100% |
| S_HASH | **0%** (pre-audit "8%" was from the unbalanced test) |
| S_UNKNOWN_COMPUTATIONAL | **0%** |
| Overall balanced accuracy | 70.0% |

**Critical**: the detector generalizes only to substrates producing the SAME artifact
type (discrete value levels). Novel mechanisms defeat it entirely.

## 9. Matched-Statistic Adversarial Worlds

Two variants (audit fix: monotonic matching alone was near-degenerate):

| Variant | Accuracy |
|---------|----------|
| Monotonic (quantized, rank-matched) | **50.00%** |
| Non-monotonic (S_HASH, rank-matched) | **50.00%** |
| Unmatched reference (generator holdout) | 61.25% |

The detector is **completely defeated** by histogram matching under both variants:
its remaining 61.25% power rides entirely on distributional differences between
quantized and non-quantized value sets.

## 10. Identical-Observation Null (§26)

Observations now **bitwise identical** (lossless lookup-table reconstruction path,
asserted), not merely statistic-matched:

| Metric | Value |
|--------|-------|
| Accuracy | **exactly 0.5000** (28/60 + 32/60) |
| Expected (information-theoretic ceiling) | 0.5000 |
| Verdict | **PASS** |

The detector correctly returns chance when zero information exists.

## 11. Label-Permutation Null

20 independent permutations (audit fix: a single permutation is a coin flip):

| Metric | Value |
|--------|-------|
| Mean permuted accuracy | **0.5215** |
| Min / Max over 20 perms | 0.4542 / 0.6792 |
| Verdict | **PASS** (mean at chance; single-perm spread confirms why n=1 was invalid) |

No information leakage through the training pipeline.

## 12. Feature Ablation & Permutation

Ablation (balanced accuracy on stratified holdout):

| Feature Set | Balanced Accuracy |
|-------------|------------------|
| Computational features only | **77.50%** |
| All features | 61.25% |
| Spatial only | 60.42% |
| Spectral only | 48.33% |
| Precision only | 48.33% |

Feature permutation on the frozen detector (degradation when shuffled):

| Family | Degradation |
|--------|-------------|
| Computational | **+17.92%** (sole driver; pre-audit 8.75% was baseline-inflated) |
| Spatial | 0.00% |
| Precision | -0.83% |
| Spectral | -3.75% |

The computational family (quantization_level, repeated_value_fraction, recurrence,
compression_ratio) is the only informative subset — consistent with a quantization
counter, not a substrate detector.

## 13. Observation Robustness

| Observation Model | Balanced Accuracy |
|------------------|------------------|
| O1: Full float64 | 0.6125 |
| O2: float32 | 0.6125 |
| O3: float16 | 0.5750 |
| O4: uint8 | **0.5000** |
| O5: uint4 | **0.5000** |
| O6: 2x2 downsample (real avgpool) | 0.5833 (pre-audit 0.7708 was an identity-op bug) |
| O7: additive noise | 0.4125 |

Any observation channel that masks value discreteness (8-bit, 4-bit, noise) destroys
all detection power. The pre-audit claim of noise-robustness was an artifact of the
O6 identity bug and imbalance.

## 14. Resolution and Rotation Tests

Not executed in V5.2 (requires multi-resolution infrastructure). Partially covered by
O6 downsampling. Planned for V5.3 only if a genuine signature ever survives §9–§13.

## 15. Temporal Worlds

Not executed in V5.2. G05–G07 carry temporal structure in field layout but no explicit
time-series dynamics were tested.

## 16. LOO Generator / LOO Substrate

Leave-One-Generator-Out (train on 8, test on held-out family, balanced 40/40):

| Held-out | Bal. acc | | Held-out substrate | Bal. acc |
|----------|----------|-|--------------------|----------|
| G01 | 0.750 | | S_FLOAT32 | 0.490 |
| G02 | 0.875 | | S_FLOAT16 | 0.510 |
| G03 | 0.500 | | S_QUANT_8 | 0.515 |
| G04 | 0.750 | | S_LATTICE | 0.740 |
| G05 | 0.500 | | S_LOOKUP | 0.795 |
| G06 | 0.500 | | S_HASH | 0.425 |
| G07 | 0.500 | | S_FINITE_STATE | 0.795 |
| mean | 0.625 | | S_QUANT_4 | 0.785 |
| range | 0.500–0.875 | | S_UNKNOWN_COMPUTATIONAL | 0.570 |
| | | | mean | 0.625 |
| | | | range | 0.425–0.795 |

**Interpretation**: performance is highly non-uniform. Precision-level substrates
(FLOAT32/FLOAT16/QUANT_8) are undetectable within their own family (≈chance), while
strong-quantization substrates are "detected" only because quantization is visible —
again the levels, not the computation.

## 17. Pairwise Substrate Test (§24-25)

Same generator, same seed, same statistics budget, only substrate differs — 240 pairs:

| Metric | Value |
|--------|-------|
| Pairwise accuracy | **50.00%** |
| G08 / G09 / G10 | 50% / 50% / 50% |

The cleanest test in the benchmark: with everything except substrate controlled, the
detector has **zero** discriminative power.

## 18. Feature Leakage (binned mutual information)

Audit replaced the tautological unique-value count with quantile-binned MI
(39 features, normalized):

| Metric | Value |
|--------|-------|
| Mean MI(feature; generator) | **0.3623** |
| Mean MI(feature; substrate) | 0.1466 |
| Verdict | **GENERATOR_DOMINANT** |

Features carry ~2.5x more information about WHICH generator produced the world than
about the substrate. Notable extremes:
- `float64_float16_diff`: MI(generator) = **1.00** — this single feature identifies the
  generator family perfectly (pure leakage; it should be excluded from any substrate claim).
- `repeated_value_fraction`: MI(substrate) = 0.495 — the only strong substrate-carrying
  feature, and it is a quantization counter.
- `quantization_level`: MI(generator) 0.497 > MI(substrate) 0.345 — even the "smoking
  gun" feature leaks generator more than substrate.

## 19. World_PRIME Holdout (§48 blind)

Prime-modular world: `int(v*1000) % p / p` over 10 small primes, min-max normalized
back to the base range. Blind test, never tuned on:

| Metric | Value |
|--------|-------|
| Worlds tested | 30 |
| Detected as computational | **30/30 (100%)** |

**Honest reading of the reversal** (pre-audit run said 0/30; stratification fixed the
training balance and the direction flipped). This is NOT a success of substrate
detection and does NOT contradict the QUANTIZATION_DETECTOR status:
- The prime-modular map collapses the field onto a short ladder of at most ~222
  distinct fractional values (k/p for p in the prime set). Min-max normalization
  preserves that discreteness.
- The detector fires for exactly the reason it fires on S_QUANT_4: visible discrete
  value levels. The test is not statistic-matched, so it never tested "primality".
- Conclusion: World_PRIME is detected **as quantization**, confirming the failure mode
  rather than refuting it. A true prime-substrate signature would have to survive §9
  histogram matching; §9 says nothing prime-specific survives.

## 20. Unknown Substrates

- S_UNKNOWN_COMPUTATIONAL (XOR modular): **0%** detection (balanced test)
- S_HASH: **0%** detection
- S_UNKNOWN_CONTINUOUS (tanh float64): not flagged in calibration (correct)

Novel computational mechanisms that preserve the value distribution are invisible —
the symmetric failure that defines a quantization-level detector.

## 21. Calibration

| Metric | Value |
|--------|-------|
| Mean score (true continuous) | 0.5114 |
| Mean score (true computational) | 0.6311 |
| Separation | 0.1197 (weak; pre-audit 0.2756 was baseline-inflated) |

Confidence carries little real information: continuous worlds already score near the
decision boundary.

## 22. Failure Analysis

Primary: **QUANTIZATION_DETECTOR** — decision boundary ≈
`quantization_level / repeated_value_fraction / compression_ratio > threshold`.
Captures only substrates that leave discrete value levels; blind to hash, XOR,
float32-vs-float64.

Secondary: **GENERATOR_CONFOUNDED** (partial) — MI leakage is generator-dominant
(0.36 vs 0.15), one feature identifies the generator perfectly, and G08 sits below
chance on the holdout.

The pairwise test (50% on 240 controlled pairs) is the single most decisive result.

## 23. Reproducibility, Gate, Conclusion

```
Protocol hash:   c3deb202db7f2d47   (post-audit sources)
Base seed:       133742
Total worlds:    2200 (60x30, 20 seeds/generator)
Database:        history_v5_2.sqlite3 (worlds, features, results, generators, substrates)
Results JSON:    v5_2_artifacts/benchmark/v5_2_results.json
Predictions:     v5_2_artifacts/predictions/holdout_predictions.csv
Checkpoints:     v5_2_artifacts/checkpoint.json (per-phase, §59)
Entry point:     python3 agent_loop.py auto --mode v5.2-deep --time-budget 14400
Resume:          python3 agent_loop.py resume --mode v5.2-deep
Runtime:         generation ~15 min; cached re-evaluation ~6 min
Python:          3.12 (standard library only; no sklearn/NN per §40)
```

Source files: `v5_2_core.py` (generators/substrates/pairs), `v5_2_pipeline.py`
(benchmark phases), `v5_2_extended.py` (LOO/pairwise/robustness/leakage/prime),
`v5_2_db.py` (SQLite layer), `protocol_v5_2.json` (machine-readable results).

**Final status: QUANTIZATION_DETECTOR**

Gate assessment (§67):

| Gate | Result |
|------|--------|
| Generator-disjoint survives (>0.6) | PASS, marginal (0.6125; CI lower bound 0.5542) |
| Substrate-disjoint survives (>0.6) | PASS (0.70) but 2/5 novel substrates at 0% |
| Label permutation collapses | PASS (mean 0.5215) |
| Identical-observation null at chance | PASS (exactly 0.5000) |
| Matched-statistics survives | **FAIL** (0.5000 both variants) |
| Pairwise substrate discrimination | **FAIL** (0.5000) |
| Unknown computational detection | **FAIL** (0%) |
| Observation robustness | **FAIL** (0.5000 at uint8) |

**GATE NOT PASSED. Do NOT proceed to real-world data (§67).**

The V5.1 signal (97.5%) is fully explained by trivial distribution-shift detection.
Within this framework — these features, this resolution, these generators — no
substrate-detectable computation signature exists once statistics are controlled.
This is a valid negative result; it does not prove computational substrates are
undetectable in principle.

---
*Revision 2 (post self-audit): 2026-09-19*
*V5.2 Adversarial Benchmark*
*Status: QUANTIZATION_DETECTOR*
*Gate: NOT PASSED*
