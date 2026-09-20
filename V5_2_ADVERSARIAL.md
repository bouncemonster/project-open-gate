# V5.2 Adversarial Benchmark — Protocol & Audit Response

This is the **protocol/methodology** document for V5.2. It deliberately contains
**no result numbers**: all metrics live in exactly two places to prevent drift —
- `report_v5_2.md` — the human-readable §64 report (Revision 2, post self-audit)
- `v5_2_artifacts/benchmark/v5_2_results.json` — the machine-readable ground truth

Final status: **QUANTIZATION_DETECTOR** (gate §67 NOT passed). See report §23.

## 1. Purpose

V5.1 reported 97.5% balanced accuracy for "computational substrate detection".
Per §53 this number must not be overinterpreted. V5.2 asks the adversarial
question: is that accuracy a genuine substrate signature, or trivial
distribution-shift detection between quantized and continuous histograms?

Success is defined by §54 as **survival of the controls**, not by any accuracy
threshold. The status vocabulary (§55) never permits "SIMULATION_DETECTED".

## 2. Architecture (§3-§5)

Three causal layers, never conflated:

```
GENERATOR (mathematical content)  ->  SUBSTRATE (implementation precision)  ->  OBSERVATION (detector input)
```

- 10 generator families G01–G10, splits disjoint at generator level (§8):
  train G01–G05, validation G06–G07, holdout G08–G10.
- 11 substrates (§4-§5): 2 continuous (float64 reference, tanh float64),
  9 computational (float32, float16, quant8, quant4, lattice, lookup, hash,
  finite-state, XOR-modular). Substrate-disjoint split (§9): train sees
  {FLOAT32, FLOAT16, QUANT_8, LATTICE}; holdout {QUANT_4, LOOKUP, HASH,
  FINITE_STATE, UNKNOWN_COMPUTATIONAL}.
- Counterfactual pairs (§3): same generator, same seed, same resolution
  (60x30), same observation model; only the substrate differs.
- W15_PRIME is kept as a blind holdout, never tuned on (§48).

## 3. Test battery

| Test | Spec | Implementation | What passing means |
|------|------|----------------|--------------------|
| Generator-disjoint holdout | §7-§8 | `V52Pipeline.phase_generator_holdout` (stratified 40/40 per generator) | above-chance on unseen math |
| Substrate-disjoint holdout | §9 | `phase_substrate_holdout` (balanced 100:100) | generalizes to unseen mechanisms |
| Label-permutation null | §20 | `phase_label_permutation` (20 permutations, mean) | mean at chance => no leakage |
| Identical-observation null | §26 | `phase_identical_observation_null` (lossless lookup-table roundtrip, bitwise-identical, asserted) | exactly chance (information-theoretic ceiling) |
| Matched-statistic adversarial | §12-§18 | `phase_matched_statistics`, TWO variants: monotonic (quantized) and non-monotonic (S_HASH), rank-matched histograms | substrate signal survives statistic matching |
| Feature ablation / permutation | §21, §45 | `phase_ablation` + `V52Extended.test_feature_permutation` (frozen detector, test-side permutation) | identifies driving feature family |
| Bootstrap CI | §52 | `phase_bootstrap` (1000 resamples) | CI reported with every headline |
| LOO generator / substrate | §22-§23 | `V52Extended.test_loo_generator / test_loo_substrate` | uniformity across families/mechanisms |
| Pairwise substrate | §24-§25 | `test_pairwise_substrate` (240 same-gen/same-seed pairs) | above-chance pairing power |
| Observation robustness O1-O7 | §30 | `test_observation_robustness` (real 2x2 avgpool for O6) | survives degraded observation |
| Feature leakage | §19 | `test_feature_leakage` (quantile-binned MI, normalized) | substrate MI not dominated by generator MI |
| World_PRIME / unknown substrates | §16-§17, §48 | `test_world_prime`, substrate holdout recall | novel mechanisms detected blind |
| Calibration | §47 | `test_calibration` (score means per true class) | confidence separation |

Detector constraint (§40): interpretable only — nearest-centroid + LDA via
`V5Detector` (reused unchanged from V5.1). No neural networks, no sklearn,
standard library only.

## 4. Status decision logic (§55)

`V52Pipeline.determine_status` evaluates:
1. generator holdout > 0.6, 2. substrate holdout > 0.6,
3. label-permutation mean within ±0.1 of 0.5,
4. identical-obs within ±0.02 of 0.5,
5. BOTH matched-statistic variants > 0.6.
All pass -> VALID_COMPUTATIONAL_SIGNATURE; failure of (5) with (1)-(4) ok ->
QUANTIZATION_DETECTOR; other failure modes map to GENERATOR_CONFOUNDED /
NO_GENERALIZATION / BENCHMARK_INVALID / UNRESOLVED.

## 5. Self-audit response (Revision 2)

The first V5.2 run was audited and 7 defects were corrected in code before the
final numbers were produced. Full defect/effect table: `report_v5_2.md` §0.
Summary of the corrections now baked into this protocol:

1. **Stratified selection** — `_get_training_worlds` / `_get_holdout_worlds`
   (and `V52Extended._get_balanced_from`) balance PER GENERATOR. Global list
   slicing was invalid because worlds are ordered gen -> seed -> substrate.
2. **Real downsampling** — O6 applies 2x2 average pooling and re-extracts
   features on the (field, w, h) result.
3. **Two matched-statistic variants** — monotonic rank-matching of a
   quantized field nearly recovers the original, so a non-monotonic S_HASH
   matched variant is mandatory.
4. **Balanced substrate holdout** — 20 per holdout substrate vs 100
   continuous references (1:1 in aggregate).
5. **20-permutation label null** — a single permutation is a polarity coin
   flip; only the mean is interpretable.
6. **Bitwise-identical §26 null** — histogram-matched is NOT identical;
   the null now uses a lossless lookup-table roundtrip with an assert.
7. **Documentation single-sourcing** — metrics live in the results JSON and
   the report only; this protocol file carries none. The pipeline's
   `phase_report` writes an auto-dump to `v5_2_artifacts/report_v5_2_auto.md`
   and can no longer clobber the human-owned report.

Also completed post-audit: §58 entry points in `agent_loop.py`
(`auto`/`resume --mode v5.2-deep`), §59 per-phase checkpoints, and the §60
SQLite layer (`v5_2_db.py` -> `history_v5_2.sqlite3`).

## 6. Reproducibility

```
Protocol hash:   c3deb202db7f2d47   (sha256[0:16] over v5_2_core.py,
                                     v5_2_pipeline.py, v5_math.py, v5_detector.py)
Base seed:       133742
Worlds:          2200 (60x30, 20 seeds/generator)
Entry point:     python3 agent_loop.py auto --mode v5.2-deep --time-budget 14400
Resume:          python3 agent_loop.py resume --mode v5.2-deep
Artifacts:       v5_2_artifacts/ (checkpoint.json, benchmark/, predictions/)
Database:        history_v5_2.sqlite3
V5.1 preserved:  archives/v5_1_baseline/
```

## 7. Verdict and next gate

V5.2's controls defeat the detector (§9 matched statistics, §17 pairwise,
§13 low-precision observation — all collapse to chance; see report for values).
Per §67, **real-world data analysis is NOT authorized**. Any future attempt
needs features whose substrate information survives histogram matching, or a
native (not post-hoc) computational implementation.

---
*Revision 2 (post self-audit): 2026-09-19*
