# Proof of Simulation — V6 Report

## Active Black-Box Response Benchmark

- **Branch:** `active_response_operator`
- **Protocol hash:** `09f32e0dc373fe96`
- **Base seed:** `20260920` · grid 16×16 · 24 intervention steps · 10 seeds/generator · 240 black-box worlds
- **Final status:** `ACTIVE_COMPUTATIONAL_SIGNATURE`
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

Six hidden mechanisms share each baseline:

| mechanism | family | continuous reference? |
|---|---|---|
| `continuous` | exact linear float update | yes |
| `continuous_alt` | same math, reversed tap order (independent impl, C1) | yes |
| `fixed_point` | deviation snapped to a uniform lattice (0.008) | no |
| `finite_state` | deviation snapped to a 21-level alphabet | no |
| `modular` | coarse lattice + periodic fold (wrap-around collisions) | no |
| `unknown_trunc` | **unseen** mechanism: finite binary **mantissa** truncation (frexp/ldexp, 5 bits) | no |

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

1. **The probe is well-matched to the manipulation.** The discriminating feature
   (superposition / additivity error) is the direct signature of exactly the
   nonlinearity injected into the computational mechanisms, so a perfect score is
   partly by construction. The controls (C1–C3) confirm the detection is causal
   and not artifactual, but they cannot make the *choice* of feature
   assumption-free. The genuinely non-trivial empirical content is that the
   relational signature transfers across unseen generators **and** an unseen
   mechanism while the amplitude cue does not.
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
