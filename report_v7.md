# Proof of Simulation — V7: Real-Data Lattice-Signature Test (engine)

- **Branch:** `empirical_lattice_signature` (frontier, opened from V6)
- **Base seed:** `20260921` · stdlib-only · deterministic
- **Status:** `V7_ENGINE_VALID_READY_FOR_REAL_DATA` — control-gated test built &
  validated on synthetic skies; **not yet run on observational data.**
- **Never claimed:** that the universe *is* a simulation. This tests one narrow,
  falsifiable physical hypothesis only.

## What this actually is
V6's power comes from *intervening* on a system. We cannot intervene on the
Universe — only observe it. So the honest path "toward proof" is not a toy model
but a **falsifiable signature test on real data**. The best-known such signature
(Beane, Davoudi & Savage, *Constraints on the Universe as a Numerical
Simulation*, 2012): if space is a finite **hypercubic lattice** (as lattice QCD
uses), continuous rotational symmetry breaks to the cubic group, and
ultra-high-energy cosmic rays would arrive **preferentially along the 6
face-normal axes** of the lattice frame. Detecting that is evidence for a
discrete substrate; not detecting it places an upper bound on the lattice
spacing. Either way it is real, publishable science — and crucially, *a null is
the expected result*, matching the current experimental state of the art.

## The test (preregistered before any data)
- **Statistic:** axis-clustering score — mean over events of a Gaussian kernel
  (δ = 8°) in the angular distance to the nearest of the 6 face-normal axes of a
  trial cubic frame.
- **Unknown orientation:** maximise the score over a fixed pool of 120 random
  SO(3) rotations (look-elsewhere handled, see below).
- **Null:** 300 isotropic uniform spheres scored with the **same** maximisation;
  p-value = fraction of nulls ≥ observed. Because the null embeds the same
  orientation search, the multiple-comparison / look-elsewhere bias is
  controlled by construction — the honest way to do this.

## Control gate (why the engine can be trusted)
| control | sky | stat | z | p | required |
|---|---|---|---|---|---|
| Positive | known 4° lattice, 85% on-axis | 0.703 | **+117.6** | 0.003 | must fire (p < 0.05) |
| Null | isotropic | 0.092 | +1.57 | 0.086 | must stay silent (p > 0.05) |

Both hold → the statistic has **power** (sees a real lattice) **and specificity**
(says nothing when there is none). The gate `positive_fires AND null_silent` is
what makes any future real-data number meaningful instead of noise.

## Scope & honesty
- A detection would bound **a coarse cubic-lattice substrate**, not prove a
  simulator, and would demand the orientation/energy systematics be exhausted
  first. A null (the likely outcome) is a **limit**, reproducing/extending
  published Auger isotropy bounds — not a refutation of the simulation idea,
  which is largely unfalsifiable in this strong sense.
- This is deliberately far more conservative than popular "is the universe a
  simulation?" framing; that conservatism *is* the contribution.

## Next step (bounded, concrete)
Ingest a public UHECR event catalogue (Pierre Auger Observatory / Telescope
Array, arrival directions + energy), apply the **frozen** statistic + null above
to events above a preregistered energy cut, and report the p-value as a bound.
This needs an external data download (a distinct task), so it is proposed rather
than silently performed.

## Reproduce
`python v7_lattice.py` → prints the gate and writes `v7_artifacts/v7_controls.json`.
