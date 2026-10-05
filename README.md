<div align="center">

# Proof of Simulation

### Project Open Gate

**Falsifiable computational experiments. Explicit controls. Reproducible evidence.**

C11 numerical kernels · Python standard library · SQLite evidence · Frozen protocols

[Research lineage](#research-lineage) · [Run a check](#start-with-a-repository-check) · [Pipelines](#choose-the-right-pipeline) · [Interpretation](#interpreting-results) · [Contributing](AGENTS.md)

</div>

---

This repository investigates whether hidden computational constraints leave detectable patterns, and whether apparent signals survive matched controls, holdouts and adversarial tests. Its research evolved from prime-arithmetic forcing in Julia dynamics to active response-operator experiments and a lattice-signature test engine.

> **The project name is a research question, not a conclusion.** This is not a proof that reality is simulated, not a consciousness test and not an established simulation detector. A computational pattern is not physical evidence. Read each version's scope and negative controls before interpreting a score.

## Read the evidence first

| Your question | Start here |
| --- | --- |
| What has actually been concluded? | [Research lineage](#research-lineage), then the relevant version report. |
| Why were earlier apparent signals rejected? | [V5.2 adversarial audit](V5_2_ADVERSARIAL.md), [V5.3 report](report_v5_3.md), [V5.5 report](report_v5_5.md). |
| What does the active intervention benchmark measure? | [V6 report](report_v6.md), especially its falsifiability probes and claim boundaries. |
| Has observational evidence been established? | [V7 report](report_v7.md): the documented checkpoint concerns the engine and synthetic controls, not a completed observational-data result. |
| How can I check the repository? | [`verify.py`](verify.py), [`_stress.py`](_stress.py) and [stress-test report](report_stress.md). |
| What must an agent preserve? | [Project instructions](AGENTS.md), frozen protocols and the evidence policy below. |

Reports and result files are the evidence record. This README is their index, not an independent replication or a replacement for them.

## Research lineage

| Version | Experiment | Recorded interpretation | Evidence |
| --- | --- | --- | --- |
| V1–V2 | Prime-arithmetic forcing of non-autonomous Julia dynamics. | Historical baselines; interpret alongside later audits. | [Report](report.md), [V2 protocol](V2_PROTOCOL.md), [V2 audit](V2_AUDIT.md). |
| V3–V4 | Blind benchmarks and matched controls. | Preserved research lineage, not a current detection claim. | [V3 report](report_v3.md), [V4 report](report_v4.md), [archives](archives/). |
| V5–V5.1 | Continuous versus computational synthetic worlds. | Earlier high classification scores are subject to the subsequent adversarial findings. | [V5 report](report_v5.md), [V5.1 report](report_v5_1.md), [audit](V5_1_AUDIT.md). |
| V5.2 | Test whether V5.1 detects a substrate rather than quantization. | **QUANTIZATION_DETECTOR — CLOSED.** Matched statistics and unseen-substrate holdouts defeat the interpretation. | [Report](report_v5_2.md), [audit](V5_2_ADVERSARIAL.md), [protocol](protocol_v5_2.json). |
| V5.3 | Natively executed substrates under stronger statistical controls. | **STATISTICAL_ARTIFACT.** No established native-substrate signal. | [Report](report_v5_3.md), [protocol](v5_3_protocol.json), [results](v5_3_results.json). |
| V5.5 | Audit the surviving matched-control results from V5.3. | **BRANCH_CLOSED.** The apparent signal can be reproduced by the matching transformation without a substrate difference. V5.4 did not exist in this lineage. | [Report](report_v5_5.md), [preflight](v5_5_preflight.md), [results](v5_5_results.json). |
| V6 / V6.1 | Controlled interventions against synthetic black boxes with matched passive baselines. | **Bounded active-response signature.** Falsifiability probes identify sensitivity to non-additivity, not computation or finiteness itself. | [Report](report_v6.md), [protocol](v6_protocol.json), [results](v6_results.json). |
| V7 / V7.1 | Control-gated UHECR axis-anisotropy test engine for a hypercubic-lattice hypothesis. | **Engine/control checkpoint, not observational discovery.** The documented engine is calibrated on synthetic data; a lattice bound would not prove a simulator. | [Report](report_v7.md), [engine](v7_lattice.py), [controls](v7_artifacts/v7_controls.json). |

### Why the controls matter

V5.3's strong raw classification did not survive distribution matching and novel-substrate holdout. V5.5 then reproduced a surviving matched-control score using substrate-free pairs: the transformation itself supplied class information. Those branches remain closed; their scores must not be repackaged as positive evidence.

V6 asks a different question: whether controlled interventions reveal differences that a matched passive baseline hides. Its own falsifiability probes limit the interpretation: a continuous nonlinear mechanism can trigger the detector, while a finite additive mechanism need not. The supported distinction is therefore about the response operator in the tested synthetic worlds, not about whether a real universe is simulated.

For exact scores, control definitions, discrepancies between runs and decision gates, use the linked reports and result JSON rather than an isolated accuracy value in a project overview.

## Requirements

The documented baseline is **Python 3.8+** using the standard library, plus **GCC 7+ or another C11 compiler** for the C kernels. The Python research pipelines and the original C-kernel workflow have different entry points.

On Debian/Ubuntu:

```sh
sudo apt install gcc python3
```

On macOS, install the command-line development tools:

```sh
xcode-select --install
```

On Windows, use a C11-capable compiler and make sure its executable is available on `PATH`. The existing setup route is:

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
```

Compiler installation does not automatically establish a valid `PATH`; verify the installed tool before building. No NumPy, SciPy or Python package-install step is required by the documented baseline.

## Start with a repository check

Clone the source and run the repository's own verification entry point before starting a research run:

```sh
git clone https://github.com/bouncemonster/project-open-gate.git
cd project-open-gate
python verify.py --skip-db
```

`--skip-db` checks source and deliverables without requiring local evidence databases, which are intentionally not committed. With the local evidence stores available:

```sh
python verify.py
python verify.py --quick
```

`verify.py` checks compilation, local imports, report lineage, the frozen V6 protocol hash, V7 control artifacts and, unless skipped, SQLite integrity. It is a repository-consistency check, **not validation of the physical hypothesis**. Compilation can create build artifacts even though the audit does not run a new research experiment.

The deeper deterministic validation entry point is:

```sh
python -u _stress.py
```

Read [report_stress.md](report_stress.md) for the recorded run. A committed PASS report describes that run; it does not mean these checks were rerun during a README edit.

## Choose the right pipeline

| Research task | Command | Important boundary |
| --- | --- | --- |
| Original C kernel | `make` | V1/V2 build workflow, not the later Python pipeline suite. |
| Initialize original experiment | `python3 agent_loop.py init` | Creates experiment directories, database and protocol state. |
| Original self-test | `python3 agent_loop.py self-test` | Kernel correctness and determinism. |
| One parameter evaluation | `python3 agent_loop.py once --cr -0.7 --ci 0.27015` | Original Julia experiment. |
| Synthetic world benchmark | `python3 agent_loop.py benchmark` | Original orchestrated benchmark. |
| Full original workflow | `python3 agent_loop.py auto` | Runs multiple phases and produces results; not a read-only check. |
| V5.2 adversarial experiment | `python3 agent_loop.py auto --mode v5.2-deep` | Closed research lineage. |
| V5.3 native-substrate experiment | `python3 agent_loop.py auto --mode v5.3-deep` | Closed research lineage. |
| V5.5 transformation audit | `python v5_5_pipeline.py` | Standalone; depends on V5.3 modules and `v5_detector.py`. |
| V6 active-response benchmark | `python v6_pipeline.py` | Standalone; regenerates protocol, results, database and artifacts. |
| V7 synthetic engine controls | `python v7_lattice.py` | Do not confuse synthetic controls with analysis of observational data. |

V5.5, V6 and V7 are **not** modes of `agent_loop.py`. Use their standalone entry points. `agent_loop.py` dispatches the older `deep-v3`, `deep-v4`, `v5.2-deep` and `v5.3-deep` modes.

If `make` is unavailable, compile the original kernel directly:

```sh
gcc -O3 -std=c11 -Wall -Wextra -Wpedantic kernel.c -lm -o kernel
```

<details>
<summary>Original orchestration commands and options</summary>

Run each command with `python3 agent_loop.py`:

| Command | Purpose |
| --- | --- |
| `init` | Prepare directories, SQLite store, compiled kernel and protocol. |
| `self-test` | Check the prime sieve, targets, metrics and determinism. |
| `once --cr X --ci Y` | Evaluate the specified complex parameter. |
| `benchmark` | Run the synthetic world benchmark. |
| `auto` | Initialize → self-test → benchmark → search → controls → validation → null → report. |
| `resume` | Continue from a saved checkpoint. |
| `validate` | Validate the best parameters found. |
| `report` | Generate the report and artifacts. |

`--ui quiet` suppresses the live terminal UI. `--time-budget N` sets the search-phase budget in seconds; the documented default is 900. These are original CLI options, not universal flags for every standalone script.

</details>

## Repository map

| Component | Responsibility |
| --- | --- |
| [`kernel.c`](kernel.c), [`kernel_v3.c`](kernel_v3.c) | Numerical kernels. |
| [`agent_loop.py`](agent_loop.py), [`controller.py`](controller.py) | Original orchestration, search, controls and phase management. |
| [`protocol.py`](protocol.py), [`db.py`](db.py) | Protocol freezing/hashing and SQLite persistence. |
| [`worldforge.py`](worldforge.py), [`analysis.py`](analysis.py), [`report.py`](report.py) | Synthetic worlds, diagnostic analysis and reporting. |
| [`v6_core.py`](v6_core.py), [`v6_pipeline.py`](v6_pipeline.py), [`v6_db.py`](v6_db.py) | Active black-box response experiments and evidence. |
| [`v7_lattice.py`](v7_lattice.py) | Lattice-signature test engine. |
| [`verify.py`](verify.py), [`_stress.py`](_stress.py) | Repository checks and deeper deterministic validation. |
| [`context.md`](context.md), [`agent_context.json`](agent_context.json) | Human-readable and machine-readable working context. |
| [`archives/`](archives/) | Preserved historical lineage; not an invitation to restart closed branches. |

## Original Julia experiment

The original recurrence is:

```text
z[n + 1] = z[n]^2 + c + alpha * D(k)
```

It tests whether prime-arithmetic forcing produces spatial patterns that match analytical targets, differ from smooth/random/shuffled forcing, persist across depth and resolution, and survive null models.

<details>
<summary>Original protocol and forcing-function reference</summary>

These describe the original experiment, **not** a single shared protocol for V1–V7. Version-specific protocol files take precedence.

| Parameter | Original configuration |
| --- | --- |
| Grid | 60 × 30; x in [-1.8, 1.8], y in [-1.0, 1.0]. |
| Score | 0.25 Pearson + 0.15 Spearman + 0.15 MAE + 0.15 Gradient + 0.15 Spectral + 0.15 AutoCorr. |
| Search | Hill climbing, 100 logical steps, eight directions plus mutation. |
| Tracks | V1_INV_PI and V4_PRIME_RESIDUAL. |
| Targets | TARGET_A, TARGET_B, TARGET_PHASE and T_nm holdouts. |
| Seeds | SplitMix64; shuffle 7331, mutation 133742. |

| Driver | Forcing |
| --- | --- |
| V0_NONE | Zero; baseline Julia dynamics. |
| V1_INV_PI | `1 / pi(k)`. |
| V2_SMOOTH | Smooth surrogate matched to V1 mean and standard deviation. |
| V3_CENTERED | `1 / pi(k) - mean(1 / pi)`. |
| V4_PRIME_RESIDUAL | Standardized residual after subtracting the smooth component. |
| V5_SHUFFLED | Shuffled inverse prime-count sequence; seed 7331. |
| V6_REVERSED | Reversed inverse prime-count sequence. |
| V7_IMAGINARY | Imaginary-component forcing. |
| V8_PHASE_RANDOMIZED | DFT phase-randomized surrogate. |

For complete definitions and evidence structures, read [V2_PROTOCOL.md](V2_PROTOCOL.md), the version protocol JSON and the numerical source.

</details>

## Interpreting results

The original reporting scale runs from 0 (indistinguishable from null) to 6 (all of that protocol's criteria met with high margins). Intermediate levels represent weak, marginal, moderate, strong and very strong computational evidence. **No level establishes a simulated physical reality.**

Deterministic seeds, protocol hashes and source hashes support repeatability. They do not remove model misspecification, generator confounding, search-budget effects or the need for multiple-testing controls. The later adversarial reports are part of the result, not optional footnotes.

## Preserve reproducibility

**Do not casually reformat frozen sources.** `v6_core.py`, `v6_pipeline.py`, `v6_db.py` and `v5_detector.py` contribute to the V6 protocol hash. A source change requires the prescribed rerun and synchronized reporting; see [AGENTS.md](AGENTS.md).

Git tracks source, reports, frozen protocol/result JSON, summary CSVs and historical lineage. Heavy SQLite stores, compiled binaries, pipeline caches and large generated intermediate trees remain outside version control. The small `v6_artifacts/` deliverable is tracked separately.

**Excluded from Git does not mean disposable.** Local closed-branch databases can be the sole copies of detailed evidence. Never delete them as cleanup. `archives/` preserves provenance; retired scratch tools are not active pipeline entry points.

Do not introduce new dataset analysis, restart closed research branches, alter frozen results or regenerate experiments as a side effect of documentation work.

## License

The repository's existing notice is retained: **“This is a research project. Use freely for scientific purposes.”** No additional license or broader grant is introduced by this documentation update.
