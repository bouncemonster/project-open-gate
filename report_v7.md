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

## Ingestion path is wired and self-tested
`load_events()` reads a real catalogue (CSV or whitespace; `ra,dec[,energy]` in
degrees/eV, or `x,y,z`), applies an energy cut, and feeds the SAME frozen
statistic + null. `python v7_lattice.py` also runs an **ingestion self-test**
that writes two synthetic catalogue files and scores them through the parser:

| check | result |
|---|---|
| parser round-trip (256 rows → 256 unit vectors) | pass |
| energy cut (9×10¹⁹ eV) filters 256 → 127 | pass |
| lattice CSV (read from disk) fires | z = +117.6, p = 0.003 |
| isotropic CSV (read from disk) silent | p = 0.086 |

So `READY_FOR_REAL_DATA` is verified end-to-end, not asserted.

## Scope & honesty
- A detection would bound **a coarse cubic-lattice substrate**, not prove a
  simulator, and would demand the orientation/energy systematics be exhausted
  first. A null (the likely outcome) is a **limit**, reproducing/extending
  published Auger isotropy bounds — not a refutation of the simulation idea,
  which is largely unfalsifiable in this strong sense.
- This is deliberately far more conservative than popular "is the universe a
  simulation?" framing; that conservatism *is* the contribution.

## Next step (bounded, concrete)
Obtain a public UHECR event catalogue (Pierre Auger Observatory / Telescope
Array: arrival directions + energy), then run the frozen test directly:

```
python v7_lattice.py <catalogue.csv> [energy_cut_eV]
```

It prints the p-value and writes `v7_artifacts/v7_realdata.json`. Expected
honest outcome: **no detection** — a bound on the lattice spacing, reproducing
the published Auger isotropy limits. (This environment's shell policy forbids
curl/wget downloads, so acquiring the catalogue is a separate, authorised step;
the analysis side is complete and validated.)

## Reproduce
`python v7_lattice.py` → prints the control gate + ingestion self-test and writes
`v7_artifacts/v7_controls.json`. Score a real catalogue with
`python v7_lattice.py <catalogue.csv> [energy_cut_eV]`.
