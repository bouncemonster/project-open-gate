# Proof of Simulation — V6 Report

## Active Black-Box Response Benchmark

- **Branch:** `active_response_operator`
- **Protocol hash:** `99054d610b0d588f` (V6.2 — falsifiability probes + feature-ablation audit)
- **Base seed:** `20260920` · grid 16×16 · 24 intervention steps · 10 seeds/generator · 320 black-box worlds (8 mechanisms × 40 worlds)
- **Final status:** `ACTIVE_COMPUTATIONAL_SIGNATURE` — **bounded**: the response operator detects **non-additivity**, not computation per se (see §9)
- **Never emitted:** `SIMULATION_DETECTED`

Reproduce with `python v6_pipeline.py`. Deliverables: `v6_results.json`,
`v6_protocol.json`, `history_v6.sqlite3`, `v6_artifacts/`.

---

### What V6 asks (and why it is a different kind of question)

V5.1–V5.5 probed **passive** observation of a substrate fingerprint and every
branch closed. V6 abandons that entirely. The single hypothesis is:

> Can hidden computational constraints be detected from the system's **response
> to controlled interventions**, rather than from passive snapshots?

The central object is the map `intervention → response` (the **response
operator**), *not* `world → classification`. No static-field classifier, no
quantization detector, no histogram/spectrum matching, no phase-scramble
surrogate, and no post-hoc transform is applied to already-generated response
data (spec §6). The intervention itself is the causal probe.

### How the worlds are built (honesty of the matched baseline)

Every world is a linear, constant-preserving 3×3 torus stencil with integer
weights /16 (four generators: isotropic diffusion, anisotropic, drift,
sustained). A **constant field is an exact fixed point of every mechanism**, and
each computational mechanism only re-represents the *deviation* from that
constant while fixing deviation = 0. Consequence: the unperturbed baseline is
**bitwise identical** across the continuous and every computational mechanism.
The worlds are therefore genuinely indistinguishable *before* intervention — the
matching is forced by construction and then **verified**, not asserted (C6).

Six core mechanisms share each baseline (plus two **adversarial probes**, §9):

| mechanism | family | continuous reference? |
|---|---|---|
| `continuous` | exact linear float update | yes |
| `continuous_alt` | same math, reversed tap order (independent impl, C1) | yes |
| `fixed_point` | deviation snapped to a uniform lattice (0.008) | no |
| `finite_state` | deviation snapped to a 21-level alphabet | no |
| `modular` | coarse lattice + periodic fold (wrap-around collisions) | no |
| `unknown_trunc` | **unseen** mechanism: finite binary **mantissa** truncation (frexp/ldexp, 5 bits) | no |
| `cont_nonlinear` | **probe (§9):** continuous (uncountable) `x/(1+|x|)`, non-additive | labelled continuous, non-additive |
| `finite_additive` | **probe (§9):** finite 40-bit lattice, additive within the window | labelled finite, additive |

The observer only ever sees `intervention → response trajectory`; the
implementation is never revealed.

### Intervention battery & response-operator features (spec §2–§3)

A fixed, deterministically-seeded battery is run on every world: single-cell,
opposite-sign, two simultaneous (collinear, unequal amplitudes), repeated,
different-location, different-time, staged vs simultaneous composition, and an
amplitude sweep. From it we assemble **response-operator** features (the gated
signal):

- superposition error `R(A+B) − R(A) − R(B)` (final + pathwise),
- response symmetry `R(+P)` vs `R(−P)`,
- composition / associativity error, path dependence,
- repeatability,
- exact recurrence of response states, collisions of distinct interventions,
- effective rank of the response space.

Ordinary response **amplitudes** (magnitude, energy, decay, locality, speed)
are measured and reported separately as `amplitude_only` — they are *not* part
of the gated signal, because a linear observer can see amplitudes too.

---

## Answers to the seven mandated questions

**1. Were the baseline worlds indistinguishable?**
**Yes.** C6 (pre-intervention baseline, continuous vs computational) =
**0.500** (n=160), expected chance. Baselines are bitwise-identical by the
shared-fixed-point construction, so this is a hard, not merely statistical,
match. The benchmark is valid (not `BENCHMARK_INVALID`).

**2. Did interventions reveal a difference?**
**Yes.** The primary — *fully out-of-sample* (train on seen generators **and**
seen mechanisms, test on unseen generators × all computational mechanisms) —
response-operator discrimination = **1.000**, 95% CI [1.000, 1.000], null 0.50
(n=80). The in-sample diagnostic is also 1.000 but is reported only for
transparency; the gated number is the held-out one.

**3. What response property carried it?**
The **breakdown of linear superposition** — i.e. the non-additivity of the
response operator — carried it, and it is generator-independent. For every
generator the continuous worlds give `superposition_err ≈ 1e-16` (exact
linearity) while every computational mechanism gives a strictly positive value
(fixed_point ≈ 0.19–0.32, finite_state ≈ 0.29–1.00, modular ≈ 0.33–2.9,
unseen unknown_trunc ≈ 0.03–0.08), reinforced by symmetry / composition / path
violations, exact recurrence, response collisions and response-space rank
collapse. Crucially the tempting "obvious" cue — response **amplitude** — is a
generator-confounded ordinary observable: it is **1.000 in-sample but 0.500
out-of-sample** (0/32 ties), so the transferable signature is relational, not
magnitude-based (see §7 below).

**4. Did the signal survive unseen generators? (C4)**
**Yes.** Generator holdout = **1.000**, CI [1.000, 1.000] (n=40): trained only
on isotropic/anisotropic, tested on the unseen drift/sustained dynamics.

**5. Did it survive an unseen computational mechanism? (C5)**
**Yes.** Unseen-mechanism = **1.000**, CI [1.000, 1.000] (n=40); the hardest
setting — unseen generators **and** unseen mechanisms simultaneously — is also
**1.000**. This includes `unknown_trunc`, a finite-mantissa (floating-point
precision) mechanism held out entirely from training.

**6. Did all artifact controls collapse to chance?**
**Yes.**
- **C1 equivalent implementation** (continuous vs reversed-tap re-implementation
  of the *same* system): **0.500** — response operators are bitwise identical, so
  no implementation artifact leaks into the features.
- **C2 intervention permutation** (intervention identities re-attributed across
  worlds, responses preserved): mean over 20 permutations = **0.502** (max 0.606,
  single-draw noise) — at chance.
- **C3 response surrogate** (each role's trajectories independently reassigned
  across the population: response statistics preserved, causal intervention →
  response correspondence destroyed): mean over 5 reps = **0.472** (max 0.538) —
  at chance.

The signal survives only when the true causal pairing is intact: it is a
property of the response **operator**, not of marginal response statistics or
label memorisation.

**7. Final status.**
`ACTIVE_COMPUTATIONAL_SIGNATURE`. All nine §8 gate conditions hold:

| # | gate condition | result |
|---|---|---|
| 1 | baseline indistinguishable (C6) | 0.500 ✓ |
| 2 | intervention-response discrimination > chance | 1.000 ✓ |
| 3 | unseen generator survives (C4) | 1.000 ✓ |
| 4 | unseen computational mechanism survives (C5) | 1.000 ✓ |
| 5 | equivalent implementation = chance (C1) | 0.500 ✓ |
| 6 | intervention permutation = chance (C2) | 0.502 ✓ |
| 7 | response surrogate = chance (C3) | 0.472 ✓ |
| 8 | deterministic rerun reproduces | identical ✓ |
| 9 | signal carried by response features, not baseline/amplitude | baseline 0.500, operator 1.000, amplitude 0.500 ✓ |

### §7 feature separation

| block | held-out accuracy |
|---|---|
| BASELINE only | 0.500 |
| RESPONSE operator only | **1.000** |
| AMPLITUDE only (ordinary observable) | 0.500 |
| BASELINE + RESPONSE | 1.000 |

A positive is valid only when `baseline ≈ chance AND response > chance`; here
baseline = 0.500 and the response operator = 1.000, and the amplitude-only
contrast additionally proves the result is not an ordinary observable
difference.

### §9 falsifiability — the class label is decoupled from the measured property

A valid detector must be capable of being *wrong*. Two adversarial probes break
the class-label ↔ additivity correlation, then are classified by the canonical
detector trained **only** on the real `fixed_point`/`finite_state` vs `continuous`
contrast. "computational" = classified as the non-additive class; a tie counts as
chance (0.5).

| probe | label by design | true additivity | classified "computational" | tie rate | mean superposition_err |
|---|---|---|---|---|---|
| `fixed_point` (anchor) | computational | non-additive | 1.000 | 0.000 | 2.4e-01 |
| `modular` (anchor) | computational | non-additive | 1.000 | 0.000 | 1.5e+00 |
| **`cont_nonlinear`** | **continuous** | **non-additive** | **1.000** | 0.000 | 5.5e-01 |
| **`finite_additive`** | **finite** | **additive** | **0.500** | 1.000 | 4.6e-12 |
| `continuous_alt` (anchor) | continuous | additive | 0.500 | 1.000 | 1.6e-16 |

**Result.** A *continuous, uncountable-state* mechanism that is merely non-additive
is classified "computational" **100%** of the time (a deliberate false positive),
while a *genuinely finite-representation* mechanism that stays additive within the
probing window is **never** distinguished from continuous (100% ties,
superposition error 4.6e-12). The detector therefore keys on the **dynamical
property — non-additivity of the response operator** — not on the pre-assigned
label and not on state-space finiteness per se. This falsifies the tautology risk
("computational" merely meant "non-additive") and **bounds** the headline: the
signature certifies *reproducible non-additivity revealed by controlled
interventions*, **not** "this world is computed."

### §9b feature-ablation audit — is the "response operator" real, or one scalar?

The primary contrasts on the whole `OPERATOR_FEATS` block, so a reviewer must be
told whether that framing is reducible. Running the fully out-of-sample primary
on each single feature, and on all-but-one:

| feature | alone | drop-it (keep other 8) |
|---|---|---|
| `superposition_err` | **1.000** | 0.875 |
| `superposition_path` | **1.000** | 0.875 |
| `eff_rank` | **1.000** | 0.625 |
| `collision` | 0.875 | 1.000 |
| `symmetry_err` | 0.750 | 1.000 |
| `recurrence` | 0.688 | 1.000 |
| `composition_err` | 0.500 | 1.000 |
| `repeatability_err` | 0.500 | 1.000 |
| `path_dependence` | 0.375 | 1.000 |

**Conclusion.** Six of nine features individually exceed chance and no
single-feature removal drops the block below **0.625**, so the discrimination is
**not** reducible to one engineered scalar — the "response operator" framing is
robust. The honest caveat: the surviving features are **correlated manifestations
of one cause** (lattice quantisation simultaneously breaks additivity, response
rank, symmetry and exactness of recurrence), not independent lines of evidence —
consistent with §9, where non-additivity alone already sufficed. Three features
(`composition_err`, `repeatability_err`, `path_dependence`) carry essentially no
individual signal, confirming the block is not uniformly informative.

---

## Scope and what this does NOT mean

This is entirely on **synthetic** black-box worlds. No physical or cosmological
data was touched. The conclusion licensed by this run is exactly:

> Controlled interventions reveal a reproducible, generalisable difference
> between classes of hidden dynamical implementations (additive vs non-additive
> update rules) that is invisible in the matched pre-intervention baseline.

It is emphatically **not** evidence that our universe is simulated, and nothing
here should be read that way. `SIMULATION_DETECTED` is never emitted.

### Honest limitations

1. **What the signature certifies is now measured, not assumed.** The
discriminating feature is additivity/superposition error. §9 shows empirically
that the detector tracks **non-additivity**, not the "computational" label: a
continuous-but-nonlinear probe is flagged computational (measured false positive)
and a finite-but-additive probe is not (false negative avoided). This removes the
tautology that "computational" was defined as non-additive — and simultaneously
means the headline must be read as "reproducible non-additivity," not "detection
of computation." C1–C3 confirm the detection is causal; §9 confirms it is specific
to the property rather than to the label.
2. **Toy generators, near-optimally clean signals.** Real substrates embedded in
   unknown dynamics need not present such a tidy separation; here every control
   is designed to be decisive on small, highly-controlled worlds.
3. Only four generators and two held-out mechanisms are used; `1.000` reflects
   the strength of this particular contrast, not a general claim about all
   computational systems.

### Relation to the closed V5.x line

V5.x asked "can a substrate fingerprint be read passively?" and closed each
branch as `STATISTICAL_ARTIFACT` / `BRANCH_CLOSED`. V6 changes the epistemic
object from a passive state to an active causal operator. Whether an *empirical*
(unknown-mechanism, unknown-baseline, noisy) analogue of V6 could ever be run on
real data is a separate and far harder question this report does **not** answer.
