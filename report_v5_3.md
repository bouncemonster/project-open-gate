# Proof of Simulation — V5.3 Native Computational Fingerprint Benchmark

**Final status: `STATISTICAL_ARTIFACT`**

- Protocol hash: `61194be46d415f0f`
- Base seed: `20260919` (all seeds `zlib.crc32`-derived, deterministic across processes)
- Grid 60×30 · 64 recurrence steps · 17 sampled frames · 20 seeds/generator
- 8 generators × 8 substrates = **1280 worlds** · 68 features/world
- Predecessor V5.2 is CLOSED as `QUANTIZATION_DETECTOR`. V5.3 tests a strictly
  narrower hypothesis and is **not** a simulation detector. `SIMULATION_DETECTED`
  is never emitted.

Authoritative numbers live in `v5_3_results.json` / `history_v5_3.sqlite3`.
This document is the human-readable interpretation only.

### Revision 2 — self-audit correction
A code defect introduced during the matched-phase optimization was found and fixed:
the TRACK-A reference vector in `phase_matched` used the computational world's own
snapshot (`comp["featsA"]`) instead of the continuous reference (`cont["featsA"]`),
so the diff was `matched_comp − raw_comp` rather than the trained-on
`matched_comp − cont`. This corrupted only the T04/T05/T06 **Track A** numbers
(previously 0.006 / 0.031 / 0.875 → now **0.550 / 0.731 / 1.000**). Track B used the
correct reference throughout and is **byte-identical** before and after the fix, so the
§13 decision and `final_status` are **unchanged**. A subsequent full run reproduced the
corrected Track-B values exactly (determinism check). The interpretation in §4 is
updated accordingly: the earlier "below-chance" Track-A anomaly was a bug, not a
property of the matching transforms.

---

## 0. Hypothesis under test

> Can a detector identify fingerprints of a computational **substrate** when the
> substrate participates **natively in the recurrence** (during evolution), while
> visible single-frame statistics are aggressively controlled?

V5.3 removes the V5.1/V5.2 failure mode: no post-hoc quantization of a completed
float64 trajectory. Every substrate below is an *execution mechanism* applied to
the recurrence state at **each step** (per-step arithmetic kernel / state snap /
in-step hash term), so two substrates under the same generator, seed, parameters,
initial state, resolution and observation model produce *different trajectories*.

## 1. Architecture (causal layers)

```
GENERATOR (fixed math rule)  →  SUBSTRATE (execution mechanism of the recurrence)  →  OBSERVATION
```

Detector never sees generator id, substrate id, seed, implementation or precision
metadata, nor any feature that encodes the true class.

### Substrates (§3)

| id | mechanism (native, per-step) | split |
|----|------------------------------|-------|
| S64 | float64 reference | reference |
| S32 | IEEE-754 single rounding of every stored state each step | train |
| S16 | IEEE-754 half rounding each step | train |
| S_Q15 | 16-bit signed fixed-point add/mul each step (saturation is native); transcendentals via documented float fallback | train |
| S_FSM | 13-state lattice snap every step (state count hidden) | holdout |
| S_MOD | Z_100003 residue-ring recurrence, ×1000 integer coefficients | holdout |
| S_HASH_NATIVE | SplitMix64 chain term added **inside** each step (0.05·u_hash) | train |
| S_UNKNOWN | top-2-mantissa-bit truncation of every state (novel, never trained on) | holdout |

### Generators (§4) — generator-disjoint splits

- **train**: G01 smooth nonlinear · G02 chaotic · G03 coupled oscillator · G04 reaction-diffusion-like
- **holdout** (unseen until final): G05 wave/eigenmode · G06 procedural dynamical field
- **loo** (extra robustness): G07 logistic field · G08 diffusion+mixing

Primary unit (§5): same generator / same seed / same params / same initial state /
same resolution / same observation model, **different substrate**. Metric: balanced
pairwise accuracy via a mirror-augmented protocol (difference vector labelled "A",
its negation labelled "B"), which guarantees exactly 50 % for zero-information pairs.

---

## 2. Headline results (§14 reporting)

Null = 0.50. n_pairs = 160 unless noted (2 holdout generators × 20 seeds × 4 train substrates).

### Primary — T03 same-generator/same-seed pairwise, generator-disjoint

| track | acc | 95 % CI | per-substrate | per-generator |
|-------|-----|---------|---------------|---------------|
| A (single snapshot) | **1.000** | [1.000, 1.000] | S32 1.00 · S16 1.00 · S_Q15 1.00 · S_HASH 1.00 | G05 1.00 · G06 1.00 |
| B (temporal, 64) | **0.994** | [0.981, 1.000] | S32 1.00 · S16 1.00 · S_Q15 1.00 · S_HASH 0.975 | G05 1.00 · G06 0.988 |

T01 world-level generator holdout (not pairwise): balanced accuracy **0.853** (40 cont / 160 comp).

### T02 substrate-disjoint · T12 double-disjoint (unseen gen + unseen sub)

| substrate | T02-A | T02-B | T12-A | T12-B |
|-----------|-------|-------|-------|-------|
| S_FSM | 1.000 | 0.875 | 0.925 | 0.900 |
| S_MOD | 1.000 | 1.000 | 1.000 | 1.000 |
| **S_UNKNOWN** | **0.500** | **0.525** | 1.000 | 1.000 |

The **held-out novel mechanism (S_UNKNOWN) is at chance on same-generator pairwise** (T02). It is only "detected" in the double-disjoint cell (T12), i.e. after a full re-train on holdout-generator data — not a clean transfer of a learned substrate concept.

### Matched-statistics controls (TRACK B headline; T04 also TRACK A)

| control | Track A | Track B |
|---------|---------|---------|
| T04 histogram-matched | 0.550 | **0.438** |
| T05 spectrum-matched | 0.731 | 0.963 |
| T06 temporal-statistic-matched | 1.000 | 0.956 |
| §12 equal-output (native vs surrogate, both matched) | — | 1.000 |

### Nulls

| test | result | expected |
|------|--------|----------|
| T07 identical-observation | **exactly 0.500** | 0.500 |
| T08 label-permutation (20 perms) | mean **0.474**, min 0.144, max 0.988 | ≈0.500 |

Both nulls behave correctly → the benchmark machinery is internally valid.

### T09 leakage audit (§10)

Verdict: **`GENERATOR_DOMINANT`** — mean MI(feature; generator) = **0.592** vs MI(feature; substrate) = **0.188**.
Auto-blacklist (`GENERATOR_LEAK`, mi_g ≥ 0.8 ∧ mi_s < 0.2): `float64_float16_diff`.
Highest generator-MI features: `float64_float32_diff`, `grad_mean`, `precision_sensitivity` (mi_g 0.847), `float64_float16_diff` (mi_g 0.822, mi_s 0.00). After blacklisting, T03 clean rerun = 0.994 (only 1 feature dropped → the collapse is not explained by a single leak).

### T10 feature-family ablation (pairwise Track B)

| set | acc |
|-----|-----|
| **marginal only (F3)** | **1.000** |
| all | 0.994 |
| temporal+dynamical | 0.975 |
| dynamical (F5) | 0.900 |
| temporal (F4) | 0.750 |
| spatial (F1) | 0.700 |
| spectral (F2) | 0.688 |

**Marginal-only features alone reach 1.000** — the same axis V5.2 was closed for.

### T11 observation degradation (Track A pairwise)

float32 0.888 · uint8 0.900 · downsample2×2 0.875 · float16 0.725 · noisy(σ0.02) 0.669. Signal is broadly degradation-robust (>0.55), so `OBSERVATION_CONFOUNDED` is not the binding failure.

---

## 3. Decision (§13)

`NATIVE_SUBSTRATE_SIGNAL` requires **all 10** conditions. Failed conditions:

| # | condition | state |
|---|-----------|-------|
| 2 | histogram-matched > chance | **FAIL** (T04-B 0.438, T04-A 0.550) |
| 5 | unknown native substrate > chance | **FAIL** (T02 S_UNKNOWN 0.50/0.525) |
| 7 | generator leakage controlled | **FAIL** (`GENERATOR_DOMINANT`) |

§16 hard-stop did **not** trigger (matched tracks are not all ≈0.5). The §13 cascade
resolves to **`STATISTICAL_ARTIFACT`**: raw pairwise detection is far above chance, but
it does **not** survive equalizing the visible value distribution (T04), and the marginal
feature family alone reproduces it (T10).

---

## 4. Interpretation — why this is the honest call

1. **The dominant cue is the marginal distribution.** F3 (marginal) features alone give
   1.00 pairwise accuracy, and histogram-matching — which equalizes exactly that
   distribution — drops the single-snapshot track to chance (T04-A 0.550) and the
   temporal track to/below chance (T04-B 0.438). Native substrates do change the
   trajectory, but under this observation model the detector's workhorse is the visible
   value distribution (repeated-value / discreteness statistics), not a deep computational
   invariant.

2. **The surviving "high" numbers are not clean positive evidence.** On the correct
   Track B, adding *more* statistical matching should *reduce* detectability, yet T05
   (histogram **and** spectrum matched) scores higher (0.963) than T04 (histogram only,
   0.438). This is a real methodological limitation of the controls, not a code defect:
   the magnitude-rank spectrum replacement (keep phase, pad, clamp) and the per-cell
   temporal surrogate followed by re-histogram-matching are **not information-neutral** —
   they imprint substrate-correlated residual structure (and, for T06, the surrogate's own
   spatial scrambling, which is why T06-A reaches 1.000 even though its final frame is
   histogram-matched to the reference). The §12 equal-output score of 1.000 is confounded
   the same way: both pair members pass through `matched_trajectory`, so the classifier
   can be resolving the **matching transform's behavior** rather than a native dynamical
   fingerprint. Because these numbers coexist with a failed histogram-matched test, a
   chance-level novel substrate and generator-dominant leakage, §13 forbids upgrading them.

3. **Generator identity leaks more than substrate identity** (MI 0.592 vs 0.188,
   `GENERATOR_DOMINANT`), which directly weakens any substrate attribution.

4. **The genuinely novel held-out mechanism is invisible** where it matters (T02, same
   generator) — the condition the whole branch was designed to satisfy.

Taken together, the pre-registered §13 logic classifies V5.3 as `STATISTICAL_ARTIFACT`:
no *established* native-substrate fingerprint under aggressive statistical control. The
benchmark is internally valid (exact identity-null, collapsing permutation null, disjoint
splits), but its headline cannot be upgraded to `NATIVE_SUBSTRATE_SIGNAL`. Per §13 this
marginal outcome is **not** converted into a positive scientific claim, and per §17 no
statement is made about the physical universe being simulated.

## 5. Known limitation / next-step note

The matched-control non-monotonicity (item 4.2) is itself a finding: the T05/T06/§12
matching transforms are not information-neutral and must be rebuilt (e.g. verify that a
surrogate vs. surrogate control also scores ≈0.5, and enforce monotone detectability as
matching deepens) before the 0.95-band numbers could carry any evidential weight. This is
recorded rather than exploited — adding features to recover signal is explicitly out of
scope (§16).

---

## 6. Deliverables (§18)

```
report_v5_3.md            this document
v5_3_results.json         authoritative metrics (also in v5_3_artifacts/benchmark/)
v5_3_protocol.json        protocol + substrate implementation descriptions + hash
history_v5_3.sqlite3      1280 worlds, 87040 features, benchmark_results, substrate taxonomy
v5_3_artifacts/           checkpoint.json, benchmark/, feature & pair artifacts
```

Reproduce: `python agent_loop.py auto --mode v5.3-deep --time-budget 14400`
(Worlds are cached to `v5_3_pipeline_cache.pkl` immediately after generation, so an
interrupted run resumes with `... resume --mode v5.3-deep` without redoing the ~35 min
recurrence pass.)

Statuses this branch may emit: `NATIVE_SUBSTRATE_SIGNAL` · `STATISTICAL_ARTIFACT` ·
`GENERATOR_CONFOUNDED` · `OBSERVATION_CONFOUNDED` · `NO_GENERALIZATION` ·
`BENCHMARK_INVALID`. It never emits `SIMULATION_DETECTED`.
