# Proof of Simulation

An autonomous scientific computing research system that investigates whether prime-arithmetic forcing in non-autonomous Julia set dynamics produces reproducible spatial resonance patterns.

## What This Project Tests

This project tests whether a deterministic Julia set iteration with prime-number-based forcing (`z_{n+1} = z_n² + c + α·D(k)`) produces spatial patterns that:

1. Resonate with analytically defined target functions
2. Are distinguishable from smooth, random, or shuffled forcing
3. Show reproducible structure across iteration depths and resolutions
4. Cannot be explained by null models (random search, shuffled targets, phase-randomized surrogates)

## What This Project Does NOT Prove

- This is **not** a proof that reality is a simulation
- This is **not** a test of consciousness or subjective experience
- Results are computational patterns; physical interpretation requires independent evidence
- Statistical significance is bounded by the search budget and multiple-testing correction

## Research Versions & Current Status

| Version | Question | Status | Docs |
|---------|----------|--------|------|
| V1–V2 | Prime-arithmetic Julia forcing (kernel.c) | baselines preserved | `report.md`, `V2_PROTOCOL.md`, `V2_AUDIT.md` |
| V3–V4 | Blind benchmarks, matched controls | preserved in `archives/` | `v3_*`, `v4_*` |
| V5/V5.1 | Continuous vs computational worlds | 97.5% bal. acc. (flagged: overinterpretation risk) | `archives/v5_1_baseline/` |
| **V5.2** | Is V5.1's signal a genuine substrate signature? | **QUANTIZATION_DETECTOR — CLOSED; NO real-world analysis authorized** | `report_v5_2.md`, `V5_2_ADVERSARIAL.md`, `protocol_v5_2.json` |
| **V5.3** | Do *natively-executed* substrates leave a fingerprint under aggressive statistical control? | **STATISTICAL_ARTIFACT — no established native-substrate signal; NOT a simulation detector** | `report_v5_3.md`, `v5_3_protocol.json`, `v5_3_results.json` |
| **V5.5** | Are V5.3's surviving matched-control results real signal or control artifacts? (Branch C audit; V5.4 never existed) | **BRANCH_CLOSED — matched-control "signal" reproduced with NO substrate (1.000); it is a transformation artifact** | `report_v5_5.md`, `v5_5_preflight.md`, `v5_5_results.json`, `v5_5_protocol.json` |
| **V6** | Can hidden computational constraints be detected from the **response to controlled interventions** (the response operator), not from passive observation? (Active black-box benchmark; synthetic only) | **ACTIVE_COMPUTATIONAL_SIGNATURE (bounded) — baseline matched to chance (C6 0.500); out-of-sample response-operator discrimination 1.000 survives unseen generators (C4) and an unseen mechanism (C5); all causal controls collapse to chance (C1 0.500, C2 0.515, C3 0.540). §9: detector keys on non-additivity, not computation; §9b: operator separation is multi-feature/redundant, not one scalar. NOT a simulation detector; synthetic-only** | `report_v6.md`, `v6_results.json`, `v6_protocol.json`, `v6_core.py`, `v6_pipeline.py`, `history_v6.sqlite3` |
| **V7** | Is there a **falsifiable real-data signature** of a discrete (hypercubic-lattice) spacetime substrate? (UHECR axis-anisotropy test) | **V7_ENGINE_VALID_READY_FOR_REAL_DATA — control-gated statistic built & validated on synthetic skies (positive z=+117.6 p=0.003 fires; isotropic null p=0.086 silent) and the real-data ingestion path is self-tested (file parser round-trip + energy cut); NOT yet run on observational data; a null is the expected outcome. Bounds a lattice substrate, cannot prove a simulator** | `report_v7.md`, `v7_lattice.py`, `v7_artifacts/v7_controls.json` |

V5.2 verdict (post self-audit, revision 2): under matched statistics, pairwise
same-generator controls and unseen-substrate holdout, the detector collapses to
chance. Run via `python3 agent_loop.py auto --mode v5.2-deep`.

V5.3 verdict: substrates now participate natively in the recurrence (per-step
arithmetic/state/hash kernels, no post-hoc quantization). Raw same-generator
pairwise hits 1.00/0.99, but the signal is carried by marginal (F3) features and
collapses once the value distribution is histogram-matched (T04 ≤ chance); the
novel held-out substrate is at chance and leakage is generator-dominant. Hence
`STATISTICAL_ARTIFACT`, not `NATIVE_SUBSTRATE_SIGNAL`. Run via
`python agent_loop.py auto --mode v5.3-deep`.

V5.5 verdict (Branch C — detector/control-artifact audit): V5.3's only surviving
above-chance numbers (T05 0.96 / T06 0.96 / §12 1.00, Track B) were non-monotonic,
leaving open whether the matching transforms themselves create class information.
Re-running the §12 detector on **substrate-free** pairs (both members continuous
S64, differing only by the phase-scramble transform) reproduces accuracy **1.000**,
while a proper class-free control (scramble-vs-scramble) sits at **0.500**. The
"signal" is therefore the transform, not the computation → `BRANCH_CLOSED`. Note:
the V5.5 brief referenced a V5.4 that does not exist in this workspace; the audit
was run against the real V5→V5.1→V5.2→V5.3 lineage. Run via `python v5_5_pipeline.py`.

V6 verdict (active black-box response benchmark — a different kind of question):
instead of passively reading a substrate fingerprint, V6 probes the **response
operator** (`intervention → response`). Paired worlds share a *bitwise-identical*
baseline (a constant field is an exact fixed point of every mechanism), so they
are indistinguishable before intervention (C6 = 0.500). Under a fixed
intervention battery, the continuous reference is exactly linear
(`superposition_err ≈ 1e-16`) while every computational mechanism (fixed-point,
finite-state, modular, and a fully held-out finite-mantissa-truncation
mechanism) breaks additivity. Out-of-sample discrimination of the response
operator = **1.000** and survives unseen generators (C4) and an unseen
mechanism (C5), while all causal artifact controls collapse to chance —
equivalent-implementation C1 = 0.500, intervention-permutation C2 = 0.502,
response-surrogate C3 = 0.472 — and the tempting amplitude cue is shown to be
generator-confounded (1.000 in-sample, 0.500 out-of-sample). Hence
`ACTIVE_COMPUTATIONAL_SIGNATURE`: on synthetic worlds, controlled interventions
reveal a reproducible, generalisable difference between additive and
non-additive hidden update rules that passive observation of the matched
baseline cannot. **Falsifiability probes (V6.1, §9)** make the claim testable and
bound its meaning: a *continuous-but-nonlinear* mechanism is misclassified as
computational (measured false positive) while a *finite-but-additive* one is
indistinguishable from continuous (false negative avoided) — so the detector keys
on **non-additivity**, not on computation or finiteness per se. This says **nothing** about whether any real universe is
simulated. Run via `python v6_pipeline.py`.

## Requirements

- **C Compiler**: GCC (≥7) or Clang with C11 support
- **Python**: 3.8+ (stdlib only — no NumPy, SciPy, or external packages)
- **OS**: Windows, Linux, or macOS
- **Disk**: source + reports are small; the working evidentiary databases
  (`history*.sqlite3`, dominated by the closed-branch V2/V3/V4 stores) total
  ~1.1 GB on disk. Heavy stores and generated artifact trees are reproducible
  and excluded from version control — see *Repository Hygiene & Entrypoints*.

## Installation

### Windows (WinLibs GCC)

```powershell
winget install BrechtSanders.WinLibs.POSIX.UCRT
# Then add the mingw64\bin directory to PATH, or set CC explicitly
```

### Linux / macOS

```bash
sudo apt install gcc python3   # Debian/Ubuntu
# or
xcode-select --install           # macOS
```

## Quick Start

```bash
# 1. Compile the C kernel
make
# or manually:
gcc -O3 -std=c11 -Wall -Wextra -Wpedantic kernel.c -lm -o kernel

# 2. Initialize the experiment
python3 agent_loop.py init

# 3. Run self-test
python3 agent_loop.py self-test

# 4. Single evaluation
python3 agent_loop.py once --cr -0.7 --ci 0.27015

# 5. Run synthetic world benchmark
python3 agent_loop.py benchmark

# 6. Full automated pipeline
python3 agent_loop.py auto
```

### Repository self-check

`python verify.py` (or `make verify`) runs a read-only consistency audit across
the whole project: source compilation, local-import resolution, the full report
lineage, V6 deliverables + frozen protocol-hash reproducibility, and SQLite
integrity of every `history*.sqlite3`. Exit 0 = operationally ready. Flags:
`--quick` (fast `quick_check`), `--skip-db` (source/deliverables only).

## CLI Reference

| Command | Description |
|---------|-------------|
| `init` | Create directory structure, SQLite DB, compile kernel, write protocol |
| `self-test` | Verify kernel correctness (prime sieve, targets, metrics, determinism) |
| `once --cr X --ci Y` | Single evaluation at parameter c = X + Yi |
| `benchmark` | Run Synthetic World Benchmark (11 world classes, 20 seeds each) |
| `auto` | Full pipeline: init → self-test → benchmark → search → controls → validation → null → report |
| `resume` | Continue from last checkpoint |
| `validate` | Run validation suite on best found parameters |
| `report` | Generate report.md and artifacts |

### Research-pipeline entry points (standalone)

V5.5, V6 and V7 are self-contained scripts, **not** wired into the `agent_loop.py`
`--mode` dispatcher (which covers V1/V2 plus `deep-v3`, `deep-v4`, `v5.2-deep`,
`v5.3-deep`). Run them directly:

| Pipeline | Command | Depends on |
|----------|---------|------------|
| V5.5 | `python v5_5_pipeline.py` | `v5_3_*`, `v5_detector.py` |
| V6   | `python v6_pipeline.py`    | `v6_core.py`, `v6_db.py`, `v5_detector.py` |
| V7   | `python v7_lattice.py`     | none (stdlib only) |

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--ui quiet` | Suppress live terminal UI | off |
| `--time-budget N` | Maximum seconds for search phase | 900 |

## Project Structure

```
proof_of_simulation/
├── kernel.c           # C numerical kernel (Julia iteration, metrics, drivers)
├── db.py              # SQLite access layer (8 tables, WAL mode)
├── protocol.py        # Protocol locking & SHA-256 hashing
├── controller.py      # Hill climbing search, batch evaluation, controls
├── worldforge.py      # Synthetic world generation & detection
├── analysis.py        # Diagnostic queries & CSV export
├── ui.py              # Terminal UI (ANSI + fallback)
├── agent_loop.py      # CLI orchestration & phase state machine
├── report.py          # Report generation (report.md + artifacts)
├── Makefile           # Build system
├── README.md          # This file
├── protocol.json      # Frozen protocol parameters (auto-generated)
├── state.json         # Checkpoint for resume (auto-generated)
├── agent_context.json # Machine-readable current state
├── context.md         # Human-readable LLM context (≤120 lines)
├── history.sqlite3   # V1/V2 SQLite evidence store (WAL mode)
├── report.md          # Generated report
├── v6_core.py         # Active black-box response benchmark (V6)
├── v6_pipeline.py     # V6 controls + decision gate
├── v7_lattice.py      # V7 falsifiable real-data lattice-signature test (engine)
├── report_v7.md       # V7 hypothesis, statistic, control gate, scope
├── best/              # Best result artifacts
├── archives/          # Historical snapshots + retired scratch tooling (archives/scratch)
└── .gitignore         # Excludes heavy/regenerable evidence from version control
```

## Protocol

The protocol is frozen after initialization and verified via SHA-256 hash. Key parameters:

- **Grid**: 60×30 (1800 cells), x∈[-1.8, 1.8], y∈[-1.0, 1.0]
- **Score**: 0.25·Pearson + 0.15·Spearman + 0.15·MAE + 0.15·Gradient + 0.15·Spectral + 0.15·AutoCorr
- **Search**: Hill climbing, 100 logical steps, 8 directions + mutation per step
- **Tracks**: V1_INV_PI (Track A), V4_PRIME_RESIDUAL (Track B)
- **Targets**: TARGET_A (primary), TARGET_B, TARGET_PHASE, T_nm eigenmodes (holdouts)
- **Seeds**: SplitMix64 PRNG (shuffle=7331, mutation=133742)

## Drivers (Forcing Functions)

| Driver | Formula |
|--------|---------|
| V0_NONE | D(k) = 0 (baseline Julia) |
| V1_INV_PI | D(k) = 1/π(k) |
| V2_SMOOTH | Smooth surrogate matched to V1 mean/std |
| V3_CENTERED | D(k) = 1/π(k) - mean(1/π) |
| V4_PRIME_RESIDUAL | D(k) = (1/π(k) - smooth(k)) / std |
| V5_SHUFFLED | Shuffled 1/π(k) (seed=7331) |
| V6_REVERSED | Reversed 1/π(k) |
| V7_IMAGINARY | Forcing on imaginary component |
| V8_PHASE_RANDOMIZED | Phase-randomized surrogate (DFT) |

## Reproducibility

All randomness uses deterministic SplitMix64/xorshift64* PRNGs. The protocol hash and source hash are recorded in every run. To reproduce:

```bash
python3 agent_loop.py init
python3 agent_loop.py auto
```

## Data Layout

- **history.sqlite3** (V1/V2) and per-version stores **history_v2 … history_v6.sqlite3**:
  SQLite3, WAL journaling
  - `runs`: experiment metadata
  - `evaluations`: per-candidate results
  - `models`: driver/model definitions
  - `best_snapshots`: best score history
  - `validations`: validation suite results
  - `null_runs`: null model results
  - `benchmark_runs`: synthetic world data
  - `events`: timestamped event log

## Interpretation Guide

Results are classified into levels 0–6:

| Level | Meaning |
|-------|---------|
| 0 | No signal — indistinguishable from null |
| 1 | Weak signal — below null threshold |
| 2 | Marginal — exceeds some nulls but not robust |
| 3 | Moderate — consistent across controls |
| 4 | Strong — passes stability and null tests |
| 5 | Very strong — holds across depths, resolutions, holdouts |
| 6 | Exceptional — all criteria met with high margins |

## Repository Hygiene & Entrypoints

Version control tracks the **durable source of truth**: all Python/C source,
reports (`report*.md`, `V*_.md`), frozen protocol/result JSON, summary CSVs, and
the `archives/` lineage. It **excludes** heavy, regenerable material so history
stays lean while the evidence remains available locally:

- `*.sqlite3` (+ `-wal`/`-shm`) — the sole on-disk evidence stores for closed
  branches V2/V3/V4 and the active V6 store. Their decisive numbers are
  captured by the committed reports/CSV/JSON, so they need not live in history.
- `*.exe` / `*.o` — compiled kernels, rebuilt from `kernel.c` / `kernel_v3.c` via `make`.
- `*.pkl` — pipeline caches, regenerated on the next run.
- `v3_artifacts/ … v5_5_artifacts/` — large generated intermediate trees
  (`v6_artifacts/` is small and **is** tracked as a §11 deliverable).

**Entrypoints.** `agent_loop.py` orchestrates V1/V2 and dispatches the
`--mode` deep pipelines for V3/V4/V5.2/V5.3. V5.5 and V6 are standalone
(`python v5_5_pipeline.py`, `python v6_pipeline.py`). The `Makefile` builds the
V1/V2 kernel and wraps `agent_loop.py` commands only.

**Archived tooling.** Retired one-off diagnostic scripts and driver dumps live
in `archives/scratch/` (kept for provenance, not part of any pipeline).

## License

This is a research project. Use freely for scientific purposes.
