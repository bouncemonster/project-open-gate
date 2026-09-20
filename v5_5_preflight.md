# V5.5 Preflight — Forensic Audit of V5.x

Generated 2026-09-20. Read-only audit of every existing V5 report, results JSON,
protocol JSON and source. No new experiment code in this file.

## 0. Existence check (evidence, not the brief)

The V5.5 brief states "V5.1–V5.4 already exist". Verified against the workspace:

- **V5.4 does NOT exist.** No `report_v5_4.md`, `v5_4_results.json`,
  `v5_4_protocol.json` or `v5_4_*.py` anywhere in the tree. The highest completed
  version is **V5.3**.
- This audit therefore runs on what actually exists: **V5, V5.1, V5.2, V5.3**.
  No V5.4 findings are assumed or fabricated.

## 1. Version table

```
version | hypothesis                                   | strongest signal                     | decisive control                                   | result                | unresolved flaw
--------|----------------------------------------------|--------------------------------------|----------------------------------------------------|-----------------------|---------------------------------------------
V5      | continuous vs computational, generator hidden| 62.5-97.5% raw acc                   | none (had CRITICAL one-class holdout + split leak) | not trustworthy       | leakage/imbalance; discarded by V5.1 audit
V5.1    | repaired, class-balanced disjoint holdout    | 97.5% bal acc, CI[95,100]            | feature ablation: spatial 96.7%                    | BENCHMARK_VALID (flagged "known-artifact detection") | conflates generator+precision+quantization+substrate; 97.5% un-attributable
V5.2    | is V5.1 signal substrate or trivial shift?   | 61.25% generator-disjoint (post-audit)| PAIRWISE substrate = 50.00% AND histogram-matched = 50.00% | QUANTIZATION_DETECTOR (gate NOT passed) | residual generator confound (MI gen 0.36 > sub 0.15); only marginal/quantization features informative
V5.3    | NATIVE per-step substrate fingerprint under aggressive matching | T03 pairwise 1.00/0.99; T05/T06/S12 Track B 0.96-1.00 | T04 histogram-matched -> 0.44(B)/0.55(A); T02 S_UNKNOWN = 0.50; leakage GENERATOR_DOMINANT | STATISTICAL_ARTIFACT | matched controls (T05/T06/S12) are NON-MONOTONIC and may themselves create class information
```

## 2. What is already decisively established (do NOT repeat)

- **Marginal / quantization statistics carry the headline signal.** V5.2 §9
  (histogram-matched -> 0.50) and V5.3 T04 (histogram-matched -> 0.44/0.55) plus
  V5.3 T10 ablation (marginal-only -> 1.00) close the "visible discreteness is the
  cue" question. Repeating histogram-matching is not informative.
- **Novel mechanisms are invisible where it matters.** V5.2 S_HASH /
  S_UNKNOWN_COMPUTATIONAL -> 0%; V5.3 T02 S_UNKNOWN -> 0.50 (same-generator).
- **Generator leakage dominates substrate signal** in every version (MI gen >> MI sub).
- **The cleanest pairwise test already fails for real substrate discrimination**
  (V5.2 §17 pairwise = 50.00%).

## 3. The single strongest UNRESOLVED methodological weakness

V5.3 reported surviving above-chance accuracy on its *aggressively matched* controls
(T05 spectrum-matched 0.963, T06 temporal-matched 0.956, §12 equal-output 1.000, all
TRACK B). This is the only place in the entire program where any signal persisted past
statistical matching.

But these controls are **non-monotonic**: removing *more* statistics (T05 = histogram
**and** spectrum matched) yields *higher* accuracy than removing fewer (T04 = histogram
only). Correct statistic-removal must monotonically *reduce* detectability. The only way
detectability can rise as you match more is if the matching/surrogate transforms
themselves **inject class-distinguishing structure** that has nothing to do with the
substrate.

V5.3 flagged this in its own report (§4.2) as an unresolved caveat but never tested it.
Consequently the program **cannot currently distinguish** between two readings of its
strongest surviving numbers:

1. a genuine substrate/dynamical fingerprint, versus
2. the detector simply reading the **transformation artifact** (phase-randomization,
   magnitude-rank replacement, `matched_trajectory` rank reordering) that was applied to
   one class but not the other.

This is a *control-validity* failure, and until it is resolved no positive claim (Branch
A) is admissible and Branch D cannot be honestly declared closed either.

## 4. Branch selection (§2)

**Selected: C — detector artifact audit.**

Trigger condition (verbatim): "Use if previous controls themselves can create class
information." That is exactly §3 above. Branches A/B are inadmissible because they would
build on the possibly-contaminated matched controls; Branch D is not yet honest because the
one surviving-signal result has not had its artifact explanation tested. Branch C is the
gate that lets the program either legitimately advance or legitimately close.

**Do-not-invent rule respected:** C is chosen because it targets a real, documented,
un-tested hole, not to keep the project alive. Its most likely outcome is confirming the
artifact explanation, which then *permanently closes* the matched-control line (Branch D).

## 5. Minimum decisive experiment (§3)

Reconstruct the exact V5.3 §12 equal-output detector (train: `matched_trajectory(comp)`
vs `matched_trajectory(phase_surrogate(comp))`, same-seed/same-generator pairs, on TRAIN
generators; TRACK B features; mirror-augmented diff protocol). Then ask it to classify
pairs in which **no computational substrate exists at all**:

- Build the "native" side as `matched_trajectory(cont, cont)` and the "surrogate" side as
  `matched_trajectory(phase_surrogate(cont), cont)` — **both members derived from the
  continuous reference only.** The only difference between the two sides is the
  phase-scramble transform; the underlying substrate is identical (S64).

- **Decisive falsification:** if the detector separates these substrate-free pairs at the
  same ~1.0 it reported for real native-vs-surrogate pairs, then the "signal" is the
  transform, not the computation → the V5.3 surviving matched-control results are
  transformation artifacts → hypothesis of a fingerprint-in-matched-controls is refuted →
  **BRANCH_CLOSED**.

- If instead the substrate-free pairs collapse to chance (~0.5) while real pairs remain
  above chance, the controls are validated as information-neutral and the surviving signal
  would become a legitimate Branch-A candidate for the next gate.

Reuse: the V5.3 **code** (recurrence, matchers, feature functions, `V5Detector`) and
its deterministic seeds; the identical §12 trajectories are regenerated in place
exactly as V5.3 did, and the SQLite layer records the audit. No new generator,
substrate or seed is introduced. Majority of budget goes to controls (§6), and the
run stops at the decisive falsifier.
