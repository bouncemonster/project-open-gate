# -*- coding: utf-8 -*-
"""_stress.py — long, deep validation battery for the Proof-of-Simulation stack.

Durable regression harness (run via `make stress`). The underscore prefix keeps it
OUT of verify.py's module compile/import scan (it is a test, not a shipped module),
while still being version-controlled so the exact long tests are reproducible. It
stresses the MATH and the plumbing of V6 and V7 far beyond the normal pipeline run
(rotation SO(3) validity, sphere uniformity, loader round-trips, Monte-Carlo type-I
calibration convergence, power-vs-N, V6 feature algebra, determinism, and the
bitwise fixed-point premise) and prints PASS/FAIL with numbers so log analysis can
catch real errors. stdlib only. Deterministic seeds. Full run ~11 min.
"""
import sys, time, math, random, traceback
import v6_core as V6
import v7_lattice as V7

RESULTS = []          # (name, ok:bool, detail:str)
WARNINGS = []         # non-fatal observations


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} :: {detail}")


def warn(msg):
    WARNINGS.append(msg)
    print(f"[WARN] {msg}")


# =============================================================================
# A. V7 geometry correctness: rotations must be proper SO(3) (orthonormal, det+1)
#    and the derived cubic face-axes must be mutually ORTHOGONAL (a hypercubic
#    lattice has 90-degree axes). If not, the statistic is NOT testing a cube.
# =============================================================================
def _gram(m):
    return [[sum(m[i][k] * m[j][k] for k in range(3)) for j in range(3)] for i in range(3)]


def _det(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def test_rotations(n=50000):
    rng = random.Random(12345)
    worst_orth = 0.0
    dmin = dmax = 1.0
    worst_axis_angle_err = 0.0
    for _ in range(n):
        m = V7.rotation_matrix(rng)
        G = _gram(m)
        for i in range(3):
            for j in range(3):
                worst_orth = max(worst_orth, abs(G[i][j] - (1.0 if i == j else 0.0)))
        d = _det(m)
        dmin, dmax = min(dmin, d), max(dmax, d)
        ns = V7.face_normals(m)          # [+x,-x,+y,-y,+z,-z]
        for a, b in ((0, 2), (0, 4), (2, 4)):
            dot = max(-1.0, min(1.0, sum(ns[a][k] * ns[b][k] for k in range(3))))
            worst_axis_angle_err = max(worst_axis_angle_err,
                                       abs(math.degrees(math.acos(dot)) - 90.0))
    check("V7 rotations orthonormal (|MM^T-I|<1e-9)", worst_orth < 1e-9,
          f"max residual={worst_orth:.2e}")
    check("V7 rotations proper det=+1", abs(dmin - 1) < 1e-9 and abs(dmax - 1) < 1e-9,
          f"det in [{dmin:.6f},{dmax:.6f}]")
    check("V7 cubic face-axes orthogonal (90deg)", worst_axis_angle_err < 1e-6,
          f"max |angle-90|={worst_axis_angle_err:.2e} deg")


# B. rand_direction must be uniform on the sphere: mean~0, E[x_i^2]~1/3, cov~I/3.
def test_uniform_sphere(n=300000):
    rng = random.Random(999)
    sx = sy = sz = sxx = syy = szz = sxy = sxz = syz = 0.0
    for _ in range(n):
        x, y, z = V7.rand_direction(rng)
        sx += x; sy += y; sz += z
        sxx += x * x; syy += y * y; szz += z * z
        sxy += x * y; sxz += x * z; syz += y * z
    mean = (sx / n, sy / n, sz / n)
    cov = (sxx / n, syy / n, szz / n)
    off = (sxy / n, sxz / n, syz / n)
    mean_err = max(abs(m) for m in mean)
    diag_err = max(abs(c - 1 / 3) for c in cov)
    off_err = max(abs(c) for c in off)
    check("V7 sphere uniform: |mean| small", mean_err < 0.02, f"max|mean|={mean_err:.4f}")
    check("V7 sphere uniform: E[x^2]~1/3", diag_err < 0.02, f"max|E[xi^2]-1/3|={diag_err:.4f}")
    check("V7 sphere uniform: cov off-diag ~0", off_err < 0.02, f"max|off|={off_err:.4f}")


# C. Loader round-trip + header/x-y-z/energy-cut/malformed handling.
def _ang_deg(a, b):
    # Well-conditioned angle between (near-identical) unit vectors via chord
    # length: acos(dot) is numerically ill-conditioned near dot=1 and would
    # report ~1e-6 deg even for an exact round-trip.
    chord = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return 2.0 * math.degrees(math.asin(min(1.0, chord / 2.0)))


def test_loader():
    import os, tempfile
    lat = V7.lattice_sky(500, 7, delta_true_deg=3.0, frac_axis=0.9)
    d = tempfile.mkdtemp()
    p = os.path.join(d, "cat.csv")
    V7.write_catalogue(p, lat, 11)
    ev, ntot = V7.load_events(p)
    maxang = max(_ang_deg(a, b) for a, b in zip(lat, ev))
    # ra/dec are written at 6 decimals of a degree -> ~1e-6 deg quantization is
    # the correct, expected floor; require only a physically-tight 1e-3 deg.
    check("V7 loader ra/dec/energy round-trip", ntot == 500 and len(ev) == 500
          and maxang < 1e-3, f"n={len(ev)} max ang err={maxang:.2e} deg")
    ev2, _ = V7.load_events(p, energy_cut_ev=9e19)
    check("V7 loader energy cut filters", len(ev2) < 500, f"kept {len(ev2)}/500 at 9e19 eV")
    p2 = os.path.join(d, "xyz.csv")
    with open(p2, "w") as f:
        f.write("x,y,z,energy\n")
        for v in lat:
            f.write(f"{v[0]!r},{v[1]!r},{v[2]!r},{8e19}\n")
    ev3, _ = V7.load_events(p2)
    maxang3 = max(_ang_deg(a, b) for a, b in zip(lat, ev3))
    check("V7 loader x/y/z header path", len(ev3) == 500 and maxang3 < 1e-9,
          f"n={len(ev3)} maxerr={maxang3:.2e} deg")
    p3 = os.path.join(d, "messy.csv")
    with open(p3, "w") as f:
        f.write("# comment\n\nra,dec,energy\n10.0,20.0,7e19\nfoo,bar,baz\n"
                "30.0,-45.0,6e19\n,,,,\n")
    try:
        ev4, nt4 = V7.load_events(p3)
        check("V7 loader tolerates malformed lines", len(ev4) == 2,
              f"parsed {len(ev4)} valid of rows")
    except Exception as e:
        check("V7 loader tolerates malformed lines", False, f"raised {e!r}")


# D. Statistic sanity: isotropic score << known-lattice score.
def test_statistic_orders():
    rot = V7.build_rotations(120, V7.BASE_SEED)
    iso = V7.isotropic_sky(V7.N_EVENTS, 1)
    lat = V7.lattice_sky(V7.N_EVENTS, 2, delta_true_deg=4.0, frac_axis=0.85)
    si = V7.alignment_statistic(iso, rot)
    sl = V7.alignment_statistic(lat, rot)
    check("V7 stat: lattice >> isotropic", sl > si + 0.2, f"iso={si:.3f} lat={sl:.3f}")


# E. Type-I calibration convergence across orientation-pool sizes.
def test_calibration_convergence(ntries=160):
    for R in (60, 120, 240):
        rot = V7.build_rotations(R, V7.BASE_SEED)
        null = V7.build_null_scores(rot, V7.BASE_SEED + 50, n_null=200, n_events=128)
        rng = random.Random(7)
        fpr05 = fpr10 = 0
        med = []
        for _ in range(ntries):
            sky = [V7.rand_direction(rng) for _ in range(128)]
            p = V7.pvalue_from_null(V7.alignment_statistic(sky, rot), null)["p_value"]
            med.append(p)
            if p < 0.05: fpr05 += 1
            if p < 0.10: fpr10 += 1
        med.sort()
        e05, e10 = fpr05 / ntries, fpr10 / ntries
        ok = e05 <= 0.10 and e10 <= 0.18 and e05 <= e10
        check(f"V7 calibration @R={R} not over-rejecting", ok,
              f"FPR.05={e05:.3f} FPR.10={e10:.3f} medp={med[ntries//2]:.3f}")


# F. Power vs N at fixed weak dilution: monotone increasing (detectability grows).
def test_power_vs_N(reps=25):
    prev = -1.0
    mono = True
    detail = []
    for N in (64, 128, 256, 512):
        rot = V7.build_rotations(120, V7.BASE_SEED)
        null = V7.build_null_scores(rot, V7.BASE_SEED + 60, n_null=200, n_events=N)
        rng = random.Random(N)
        det = 0
        for _ in range(reps):
            sky = V7.lattice_sky(N, rng.randrange(1 << 30), delta_true_deg=4.0, frac_axis=0.10)
            if V7.pvalue_from_null(V7.alignment_statistic(sky, rot), null)["p_value"] < 0.05:
                det += 1
        pw = det / reps
        detail.append(f"N={N}:{pw:.2f}")
        if pw < prev - 0.10:      # allow MC noise, flag real non-monotonicity
            mono = False
        prev = max(prev, pw)
    check("V7 power grows with N (weak 10% lattice)", mono, " ".join(detail))


# G. V6 feature math over the full mechanism x generator grid: finite, correctly
#    ranged, and the continuous/computational separation holds on superposition.
#    NOTE: the *_err / superposition_path features are RELATIVE ratios in [0,~2]
#    (not [0,1] fractions) -- superposition_err > 1 legitimately means the
#    response to a sum deviates by more than the sum-response itself.
UNIT_BOUNDED = {"recurrence", "collision", "eff_rank", "locality"}


def test_v6_features():
    mechs = list(V6.MECHANISMS.keys())
    gens = V6.ALL_GENERATORS
    nan_inf = 0
    range_err = []
    neg_err = []
    cont_sup = []
    comp_sup = []
    adv_sup = {}
    for gen in gens:
        for mech in mechs:
            f = V6.compute_response_features(gen, mech, V6.stable_seed(gen, 1))
            for k, v in f.items():
                if v is None or math.isnan(v) or math.isinf(v):
                    nan_inf += 1
                elif v < 0.0:
                    neg_err.append(f"{gen}/{mech}/{k}={v:.3g}")
            for frac in UNIT_BOUNDED:
                if not (0.0 - 1e-12 <= f[frac] <= 1.0 + 1e-12):
                    range_err.append(f"{gen}/{mech}/{frac}={f[frac]:.3g}")
            sup = f["superposition_err"]
            if mech in V6.CONTINUOUS_MECHS:
                cont_sup.append(sup)
            elif mech in V6.ALL_COMPUTATIONAL:
                comp_sup.append(sup)
            elif mech in V6.ADVERSARIAL_MECHS:
                adv_sup.setdefault(mech, []).append(sup)
    check("V6 features: no NaN/inf", nan_inf == 0, f"bad={nan_inf}")
    check("V6 features: non-negative", not neg_err, f"{len(neg_err)} negative")
    check("V6 unit-fraction features in [0,1]", not range_err,
          f"{len(range_err)} out-of-range e.g. {range_err[:3]}")
    check("V6 continuous superposition~0", max(cont_sup) < 1e-9,
          f"max cont sup_err={max(cont_sup):.2e}")
    check("V6 computational superposition>0", min(comp_sup) > 1e-3,
          f"min comp sup_err={min(comp_sup):.3e}")
    check("V6 adversarial cont_nonlinear is NON-additive",
          min(adv_sup.get("cont_nonlinear", [0])) > 1e-3,
          f"min sup_err={min(adv_sup.get('cont_nonlinear',[float('nan')])):.3e}")
    fa = adv_sup.get("finite_additive", [float('nan')])
    check("V6 adversarial finite_additive is ADDITIVE (invisible)",
          max(fa) < 1e-6, f"max sup_err={max(fa):.2e}")


# H. V6 determinism: same (gen,mech,seed) -> identical feature vector, twice.
def test_v6_determinism():
    ident = True
    for gen in V6.ALL_GENERATORS:
        for mech in ("fixed_point", "continuous", "unknown_trunc"):
            a = V6.compute_response_features(gen, mech, 4242)
            b = V6.compute_response_features(gen, mech, 4242)
            if a != b:
                ident = False
    check("V6 feature computation deterministic", ident, "12 combos recomputed equal")


# I. V6 bitwise baseline fixed point: every mechanism maps the constant field to
#    an identical baseline (the C6 premise). Verify at the mechanism level.
def test_v6_baseline_fixed_point():
    dev0 = [0.0] * V6.N           # deviation from BASELINE is 0 everywhere
    bad = []
    for mech in V6.MECHANISMS:
        out = V6.MECHANISMS[mech](dev0)
        if any(x != 0.0 for x in out):
            bad.append(mech)
    check("V6 zero-deviation fixed for every mechanism", not bad,
          f"violators={bad}")


def main():
    t0 = time.time()
    tests = [
        ("rotations", lambda: test_rotations()),
        ("uniform_sphere", lambda: test_uniform_sphere()),
        ("loader", test_loader),
        ("statistic_orders", test_statistic_orders),
        ("calibration_convergence", test_calibration_convergence),
        ("power_vs_N", test_power_vs_N),
        ("v6_features", test_v6_features),
        ("v6_determinism", test_v6_determinism),
        ("v6_baseline_fp", test_v6_baseline_fixed_point),
    ]
    for name, fn in tests:
        try:
            print(f"\n--- {name} ---")
            fn()
        except Exception:
            check(name + " (raised)", False, "see traceback")
            print(traceback.format_exc())
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    nfail = len(RESULTS) - npass
    dt = time.time() - t0
    print("\n" + "=" * 66)
    print(f"STRESS SUMMARY: {npass} passed / {nfail} failed "
          f"of {len(RESULTS)} checks in {dt:.1f}s")
    if WARNINGS:
        print(f"WARNINGS: {len(WARNINGS)}")
    if nfail:
        print("FAILURES:")
        for nm, ok, det in RESULTS:
            if not ok:
                print(f"  - {nm}: {det}")
    print("=" * 66)
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
