# Proof of Simulation — V7: Real-Data Lattice-Signature Test (engine)

- **Branch:** `empirical_lattice_signature` (frontier, opened from V6) · **V7.1**
- **Base seed:** `20260921` · stdlib-only · deterministic
- **Status:** `V7_ENGINE_VALID_READY_FOR_REAL_DATA` — control-gated, with
  **measured** type-I calibration and a sensitivity floor (V7.1); **not yet run
  on observational data.**
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

## V7.1 — measured calibration & sensitivity (no longer assumed)

V7 *assumed* its Monte-Carlo p-values were honest and had *no* power analysis. A
single isotropic sky passing the null is ~95% likely by luck, so that was not
verification. V7.1 measures both. The engine gate now also requires calibration
and power to hold.

**Type-I (false-positive) calibration** — 150 fresh isotropic skies scored against
the shared null:

| nominal level | empirical false-positive rate |
|---|---|
| 0.01 | 0.027 |
| 0.05 (= α) | **0.053** |
| 0.10 | 0.113 |
| median p | **0.475** (≈ 0.5 ⇒ p-values uniform) |

FPR tracks the nominal levels and the median p sits at 0.5, so the
orientation-maximisation (look-elsewhere) is **correctly absorbed by the null** —
the test is not biased toward spurious detections. This is the detector-bias
control the earlier version lacked.

**Sensitivity / power** — 30 realisations per point (N=256, δ_kernel=8°):

- vs lattice **sharpness** (on-axis scatter, 85% on axes): power = 1.00 for every
  scatter from 4° to 45° — the detector is robust to how tightly events pack the
  axes when the on-axis *fraction* is high.
- vs **dilution** (fraction on axes, 4° scatter): 0.05→**0.40**, 0.10→**0.87**,
  0.15→1.00, ≥0.20→1.00. The **50%-detection floor is ≈6%** of events on axes.

This floor is what makes a real-data null quantitative rather than absolute: *we
would exclude a cubic-lattice signal that puts ≳6–15% of above-threshold events on
its axes*; a deeper lattice signal we simply cannot see at N≈256 would also read
null, and **must not** be reported as "no discreteness."

## Interpreting a positive vs a systematic (required before any physics claim)

A p < α from this engine is **necessary, not sufficient.** The #1 way to fake the
signal is **not** new physics but **non-uniform detector exposure** (Auger/TA
cover limited declination bands; a survey anisotropy can project onto the cubic
axis statistic). A candidate detection is only credible after: (1) re-running
against an **exposure-weighted null** (sample from the observed right-ascension /
declination acceptance, not a uniform sphere); (2) confirming the best-fit axes
are **not** aligned with the detector, Galactic, or Ecliptic frame (a frame
coincidence flags a coordinate systematic); (3) stability across energy bins
(the true signature grows with energy; an exposure artifact usually does not).
The engine reports the statistic and p; steps (1)-(3) are the analysis gate on
real data and are called out in `v7_realdata.json`'s verdict string
(`... (investigate systematics)`).

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
