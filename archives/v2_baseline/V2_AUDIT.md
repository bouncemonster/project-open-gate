# Proof of Simulation V2 — V1 Forensic Audit

Status: V1 audit reproduced; V2 corrections and experiment pending. No V2 scientific result is claimed here.

## Preserved evidence

`archives/v1_baseline/snapshot_manifest.json` identifies V1_BASELINE. All 29 files passed byte-exact SHA-256 verification. No Git repository existed. The original SQLite database is read-only for this audit and has no integrity or foreign-key violations. Raw command transcripts and machine-readable evidence are in `archives/v2_audit/evidence.json` and the command directory referenced therein. `archives/v2_tools/audit_v1.py` reproduces the audit without changing V1 data. The previous independent source review was dispatched; its detailed response was not retained in the current context. Findings below rely on newly persisted, measured reproductions, not an assumed review outcome.

## Inventory and accounting

There are 9 Python/C source files, totaling 4,746 lines (4,789 including Makefile), not 12 source files and 5,178 lines. README and generated files are not executable sources. The state machine declares 14 phases but the recorded run executed 11; optional/conditional paths must not be described as completed evidence.

SQLite contains 3,243 evaluations; `control_summary.csv` contains exactly those 3,243 records plus its header (3,244 rows). Every CSV evaluation matches SQLite. The completion claim of 3,235 is unsupported. The main run has 3,242 evaluations; a separate single-evaluation run has one. Partition of the stored evidence:

| Role | Rows |
| --- | ---: |
| Primary labeled searches | 1,060 (498 / 562 by track) |
| Explicit controls | 5 |
| Baseline | 1 |
| Validation evaluations | 16 |
| Null candidates | 2,160 |
| Separate single-evaluation run | 1 |

The main-run counter additionally includes 242 scout candidates that were never persisted. Four excess identical parameter records exist (12 after six-decimal kernel serialization). Historical failed-evaluation counts cannot be reconstructed reliably because statuses were not fully persisted. All 18 depth CSV records fail CSV-to-database reconstruction because embedded JSON was not correctly quoted. No manual correction of old CSVs was made.

## Conclusion-changing reproduction: driver dispatch

`controller.py` derives short driver labels, while `kernel.c:driver_from_string` accepts only canonical names and silently falls back to no forcing. Replaying all 3,243 stored evaluations reproduces every saved score and all six component metrics to the six decimals emitted by V1. Thus reproducibility of the stored numbers does not establish correctness of the intended experiment.

At the saved best serialized coordinates `(0.983188, -0.005867)`, alpha 1, degree 2, real channel, depth 200:

| Input | Actual behavior | Score |
| --- | --- | ---: |
| V1 / V4 / NONE | No forcing | 0.830429 |
| V0_NONE | No forcing | 0.830429 |
| V1_INV_PI | Full inverse-prime forcing | 0.823993 |
| V2_SMOOTH | Legacy smooth control | 0.846446 |
| V4_PRIME_RESIDUAL | Legacy residual | 0.857967 |
| V5_SHUFFLED | Shuffled full signal | 0.823638 |
| V6_REVERSED | Reversed full signal | 0.827965 |
| V8_PHASE_RANDOMIZED | Phase control | 0.832805 |

Twelve single/batch comparisons agree. Independent metric reconstruction agrees to rounding. Canonical inverse-prime is 0.022453 below smooth at this point; legacy residual is 0.011521 above it. These are diagnostic comparisons at a point selected by the wrong driver, not corrected search maxima or significance claims. The reported 0.830429 is a best encountered *baseline* score mislabeled as a prime search score.

## Holdouts and boundary

For the same canonical inverse-prime candidate, TARGET_B is 0.848550 and TARGET_PHASE 0.795106. With no forcing they are 0.866907 and 0.799544; with legacy residual they are 0.896384 and 0.826156. The two recorded holdouts therefore do not validate the actual driver used in the original search. The other 16 eigenmode holdouts were not evaluated.

The old best is within 5% of the upper real-parameter bound. Forward/backward probes and points at real parameter 1.05 and 1.10 are recorded in evidence.json. They do not show a uniformly increasing forward score and do not prove an interior global optimum. V2 uses a separately named expanded-domain model and a preregistered coarse scout.

## Null statistics

The eight stored null blocks each contain 270 candidates and reconcile exactly with their maxima. Maximum is 0.851766; the mislabeled primary best is 0.830429; all eight null maxima exceed it. No duplicate maxima were found. The descriptive plus-one exceedance estimate is 1.0. The recorded seeds reconstruct zero of the 2,160 sampled parameter pairs. Search algorithm, driver, and budget differ from the primary search, so this is not a calibrated significance test. Do not pool these runs with V2.

## Benchmark leakage and duplicate worlds

All 220 regenerated feature records match stored values. The historical detector scores 79/80 on training and 80/80 on labeled holdout. However, ten WORLD_PRIME records enter training, and all 20 prime seeds produce exactly one field. Therefore 10/10 prime detection is not evidence of generalization to an unseen prime world. Excluding prime training rows gives 74/80 in a diagnostic rerun; this is not a preregistered replacement benchmark. V2 must freeze features and scaling on non-prime training worlds, reserve all prime worlds, and record distinct field hashes.

## Mathematical and numerical findings

- Standard pi values, protected inverse denominators, complex-square arithmetic, and the existing self-test pass. The first 1,000 prime-trace entries match the intended event indicator/driver.
- V1 self-tests cover Pearson and MAE identity, not all score components, degenerate fields, or metamorphic properties.
- Full inverse-pi mixes a smooth trend with event structure; legacy residual uses only the heuristic log(k+2)/(k+1) surrogate.
- Drivers normalized over the requested depth change their earlier prefix when depth changes. V2 must separate depth from normalization horizon.
- Phase randomization permits an imaginary Nyquist coefficient for even sequence lengths; preserving a real signal requires a real signed Nyquist coefficient.
- Degree-three smoothing still uses log(2); V2 must use log(degree).
- Target generation in artifacts differs from the C scoring target at 1,636/1,800 quantized cells.

## Safety, architecture, and artifacts

NaN/Inf inputs are accepted and score 0.514069; a zero-iteration render timed out; depth 5,000 crashed with access violation. Fixed-length 4,096 driver buffers and stack-sized field arrays cannot support the claimed extended validation. Trace collection repeats trajectories for every time index, making it quadratic in depth. Unknown driver/target/model inputs are not rejected consistently. V2 needs bounded parsing, checked heap allocations, and one-pass traces.

The best map is only a CRLF (2 bytes); the difference map is one row (62 bytes). This is artifact truncation, not a correctly preserved blank 60×30 field. Render and score must share an exported numerical field and preserve whitespace. Existing depth stability does not establish resolution stability. Protocol hashes do not by themselves enforce a frozen run. Checkpoints must atomically include PRNG state and evaluation records; report rows need explicit run/role/target provenance.

## Impact on V1 interpretation

V1 does not establish a prime-specific advantage. Its labeled primary search did not execute the intended prime drivers, the null is not budget-matched or seed-reproducible, and the prime benchmark is not a held-out-world test. The Level 4 claim, especially resolution stability, is unsupported. The historical report remains unchanged for forensic comparison. A corrected interpretation is: “Under the V1 protocol, model family, search domain and control suite, the experiment did not demonstrate a prime-specific structural contribution beyond the tested smooth surrogate models.” This does not imply that prime arithmetic has no effect in all model classes.
