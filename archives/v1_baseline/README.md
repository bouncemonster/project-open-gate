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

## Requirements

- **C Compiler**: GCC (≥7) or Clang with C11 support
- **Python**: 3.8+ (stdlib only — no NumPy, SciPy, or external packages)
- **OS**: Windows, Linux, or macOS
- **Disk**: ~50 MB for database and artifacts

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
├── experiment.db      # SQLite database
├── report.md          # Generated report
├── best/              # Best result artifacts
├── validation/        # Validation results
├── benchmark/         # Benchmark data
└── archives/          # Historical snapshots
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

- **experiment.db**: SQLite3 with WAL journaling
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

## License

This is a research project. Use freely for scientific purposes.
