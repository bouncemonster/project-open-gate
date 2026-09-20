# Proof of Simulation V5.5 — Autonomous Research Gate

**Branch selected: C — detector / control-artifact audit**
**Final status: `BRANCH_CLOSED`**
Protocol hash `eeb3abea8d2fa374` · base seed `20260919` · grid 60×30 · 64 steps · frame_every 4
Never emits `SIMULATION_DETECTED`. No real-world data analyzed.

Preflight audit and branch rationale: see [v5_5_preflight.md](file:///J:/project/project_open_gate/proof_of_simulation/v5_5_preflight.md).
Machine results: [v5_5_results.json](file:///J:/project/project_open_gate/proof_of_simulation/v5_5_results.json) ·
[v5_5_protocol.json](file:///J:/project/project_open_gate/proof_of_simulation/v5_5_protocol.json) ·
DB [history_v5_5.sqlite3](file:///J:/project/project_open_gate/proof_of_simulation/history_v5_5.sqlite3).

---

## 0. Existence correction (evidence over brief)

The brief states "V5.1–V5.4 already exist." Verified against the workspace: **V5.4
does not exist** (no report/protocol/results/source). The program history is
V5 → V5.1 → V5.2 → V5.3. The audit was run on what actually exists; no V5.4
findings were assumed or fabricated.

## 1. What V5.4 established

Nothing — V5.4 does not exist. The operative predecessor is **V5.3**
(`STATISTICAL_ARTIFACT`), which established:

- The headline pairwise substrate signal (T03 1.00/0.99) rides entirely on
  **marginal / quantization statistics** (T10 ablation: marginal-only → 1.00;
  T04 histogram-matching → 0.44/0.55).
- **Generator leakage dominates** substrate information (T09 `GENERATOR_DOMINANT`,
  MI(gen) 0.59 ≫ MI(sub) 0.19).
- A **novel mechanism is invisible where it decides the outcome** (T02 S_UNKNOWN = 0.50).

## 2. What remained unresolved

V5.3's *only* surviving above-chance numbers were its **aggressively matched
controls**: T05 spectrum-matched 0.963, T06 temporal-matched 0.956, §12
equal-output 1.000 (Track B). These are **non-monotonic** — matching *more*
statistics (T05) *increased* detectability over matching fewer (T04). Correct
statistic-removal must monotonically *reduce* detectability. The only way
detectability rises as you remove more is if the matching / surrogate transforms
themselves **inject class structure**. V5.3 flagged this (§4.2) but never tested
it. Until tested, its strongest surviving result is ambiguous between

1. a genuine substrate/dynamical fingerprint, and
2. the detector reading a **transformation artifact**.

This is the single strongest unresolved methodological weakness in the program.

## 3. Why this is the minimum decisive next test

Branch C targets exactly that ambiguity, reusing the V5.3 code (recurrence,
matchers, feature functions, `V5Detector`) and its deterministic seeds — the
identical trajectories are regenerated in place, precisely as V5.3 §12 itself did;
no new generator, substrate or seed is introduced. The experiment reconstructs the
**exact** V5.3 §12 detector (train: `matched_trajectory(comp)` vs
`matched_trajectory(phase_surrogate(comp))`, same-gen/same-seed, TRAIN generators,
**all four TRAIN_SUBSTRATES → 320 train / 160 test pairs**, mirror-augmented
difference) and then asks it to classify pairs in which **no
computational substrate exists at all**: both members are derived from the
continuous S64 reference, differing *only* by the phase-scramble transform.

- If it separates these substrate-free pairs at the same ≈1.0 it reported on real
  pairs → the "signal" is the transform, not the computation → falsifier fires.
- If they collapse to chance while real pairs stay above chance → the controls are
  information-neutral and the surviving signal becomes a legitimate Branch-A target.

This is the cheapest experiment that can prove the current hypothesis wrong, per the
core rule. Decisive adversarial null = the substrate-free transform-only contrast.

## 4. Result

| test | accuracy | n | 95% CI | interpretation |
|---|---|---|---|---|
| Positive replication — §12 native-vs-surrogate, **unseen generators** | **1.000** | 160 | [1.000, 1.000] | reproduces V5.3 §12 = 1.00 at the same n |
| **ARTIFACT NULL — both members continuous (S64), only transform differs** | **1.000** | 40 | [1.000, 1.000] | detector fires at ceiling with **no substrate present** |
| Class-free null — two independent scrambles, same process | **0.500** | 40 | [0.350, 0.650] | instrument is valid; chance when no real difference |
| Label-permutation null (20 perms) | mean 0.466 | 80 | [0.000, 1.000] | collapses to chance |
| Deterministic rerun of artifact null | identical | — | — | reproducible |

The falsifier **fires**: the §12-style detector assigns "native" with accuracy
1.000 to pairs built purely from the continuous reference, where the *only*
difference is that one side was phase-scrambled before re-matching. The
discriminative feature is the **raw-vs-scrambled transform**, not computation —
because there is no computation difference to detect. The class-free control
(scrambled-vs-scrambled → 0.500) proves this is not a scoring artifact: it pinpoints
the transform as the cue.

## 5. Strongest alternative explanation

That the V5.3 T05/T06/§12 surviving accuracies reflect a real substrate/dynamical
fingerprint that survives statistic-matching, i.e. genuine computational signal.

## 6. Whether that explanation survived

**No.** The alternative requires the matched-control accuracy to depend on the
substrate. V5.5 reproduces the identical accuracy (1.000) with the substrate held
constant (both sides S64), so accuracy is invariant to — and therefore not caused
by — the substrate. It depends only on the transform applied to the two class
labels. The surviving-signal reading is refuted; the transformation-artifact reading
is confirmed.

## 7. Final status

`BRANCH_CLOSED`. All §5 positive-result requirements fail at the decisive gate:

```
signal > chance .................. yes (1.000)
unseen generator survives ........ yes (1.000)
unseen mechanism survives ........ NO  (V5.3 T02 S_UNKNOWN = 0.50)
strongest confound control survives NO  (V5.5 artifact null = 1.000 => confound NOT controlled)
leakage controlled ............... NO  (V5.3 T09 GENERATOR_DOMINANT)
independent rerun reproduces ..... yes (deterministic)
```

Two hard requirements fail, and the decisive confound control fails outright. The
result is classified conservatively as **branch closure**, not a signal. Every
anti-leakage invariant (§4) passed, so the benchmark itself is valid
(not `BENCHMARK_INVALID`): train/holdout generator-disjoint, class-free null at
chance, permutation collapse, identical-process control at 0.500, bootstrap CIs,
deterministic rerun. `SIMULATION_DETECTED` is never emitted.

## 8. Exact next gate, or BRANCH_CLOSED

**The matched-control / native-substrate-fingerprint line is permanently closed.**
No signal survives once generator leakage, marginal statistics, and — now proven —
the matching/surrogate transform artifacts are accounted for. Across V5.1→V5.5 the
consistent finding is that apparent detectability is explained by (a) generator
identity, (b) visible quantization / marginal statistics, and (c) transformation
artifacts, never by a substrate that participates natively in the recurrence.

Recommendation: **close this research branch.** Any future gate would have to abandon
"one computational substrate vs another under statistical control" entirely and pose
a different, pre-registered question; re-running statistic-matching or pairwise
substrate tests (already decisively failed here and in V5.2/V5.3) would be
non-informative repetition, which §1 forbids.

---

### Reproduce
```
python v5_5_pipeline.py        # ~25 min; regenerates the deterministic V5.3 §12
                               # trajectories (same seeds), no new world design
```
Sources: `v5_5_pipeline.py` (audit), `v5_5_db.py` (DB), reused
`v5_3_core.py` / `v5_3_features.py` / `v5_3_pipeline.py` / `v5_detector.py`.
Deliverables: `v5_5_results.json`, `v5_5_protocol.json`, `report_v5_5.md`,
`history_v5_5.sqlite3`.
