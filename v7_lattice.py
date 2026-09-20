#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V7 — falsifiable test for a hypercubic spacetime-lattice signature.

Motivation (grounded, no overclaim): if space is a finite hypercubic lattice
(as lattice QCD uses), continuous rotational invariance is broken to the cubic
group. A proposed observable consequence (Beane/Davoudi/Savage 2012ff) is that
ultra-high-energy cosmic rays would arrive preferentially along the 6 face-normal
axes of the lattice frame. This module implements a PREREGISTERED, control-gated
test of exactly that hypothesis. It CANNOT and DOESNOT claim "the universe is a
simulation"; it only bounds/rejects a coarse cubic-lattice substrate signature.

Discipline mirrors V6: the statistic is meaningless without a positive control
(can it see a KNOWN lattice?) and a null control (does an isotropic sky stay
silent?). The unknown lattice orientation is handled by maximising over a fixed
pool of random rotations; the SAME maximisation is applied to the Monte-Carlo
isotropy null, so the look-elsewhere effect is controlled by construction.

stdlib only. deterministic. runs on synthetic skies offline; a real public
event catalogue (Auger / Telescope Array) can be supplied via load_events().
"""
import math
import random
import json
import os
import sys

# ---- fixed, preregistered constants (chosen before seeing any data) ----------
BASE_SEED = 20260921        # distinct from V6
N_EVENTS = 256              # events per sky (order of real UHECR above-threshold sets)
N_ROTATIONS = 120          # orientation pool (look-elsewhere handled by null)
N_NULL = 300               # isotropic Monte-Carlo realisations
KERNEL_DELTA_DEG = 8.0     # angular clustering kernel width around an axis
SIGNIFICANCE_ALPHA = 0.05  # preregistered threshold


# ---------------------------- geometry helpers --------------------------------
def rand_direction(rng):
    """Uniform unit vector on the sphere."""
    z = rng.uniform(-1.0, 1.0)
    phi = rng.uniform(0.0, 2.0 * math.pi)
    r = math.sqrt(max(0.0, 1.0 - z * z))
    return (r * math.cos(phi), r * math.sin(phi), z)


def normalize(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def rotation_matrix(rng):
    """Random proper 3D rotation (uniform over SO(3))."""
    # three random Euler angles; uniform-enough for a fixed orientation pool
    a, b, c = rng.uniform(0, 2 * math.pi), rng.uniform(0, math.pi), rng.uniform(0, 2 * math.pi)
    ca, sa = math.cos(a), math.sin(a)
    cb, sb = math.cos(b), math.sin(b)
    cc, sc = math.cos(c), math.sin(c)
    # Rz(a) Ry(b) Rz(c)
    m = [
        [cb * cc, -ca * sc + sa * sb * cc, sa * sc + ca * sb * cc],
        [cb * sc, ca * cc + sa * sb * sc, -sa * cc + ca * sb * sc],
        [-sb, cb * sa, cb * ca],
    ]
    return m


def apply(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def face_normals(m):
    """The 6 face-normal axes of the cubic frame rotated by m (as +/-unit cols)."""
    out = []
    for i in range(3):
        col = normalize((m[0][i], m[1][i], m[2][i]))
        out.append(col)
        out.append((-col[0], -col[1], -col[2]))
    return out


# ------------------------------- skies ----------------------------------------
def isotropic_sky(n, seed):
    rng = random.Random(seed)
    return [rand_direction(rng) for _ in range(n)]


def lattice_sky(n, seed, delta_true_deg=4.0, frac_axis=0.85):
    """POSITIVE CONTROL: events cluster near the 6 axes of a KNOWN orientation."""
    rng = random.Random(seed)
    true_rot = rotation_matrix(rng)
    axes = face_normals(true_rot)
    delta = math.radians(delta_true_deg)
    events = []
    for _ in range(n):
        if rng.random() < frac_axis:
            a = axes[rng.randrange(len(axes))]
            # perturb a toward random tangent by ~delta
            t = rand_direction(rng)
            dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, t))))
            perp = normalize((t[0] - dot * a[0], t[1] - dot * a[1], t[2] - dot * a[2]))
            ang = rng.gauss(0.0, delta)
            v = normalize((a[0] + ang * perp[0], a[1] + ang * perp[1], a[2] + ang * perp[2]))
        else:
            v = rand_direction(rng)
        events.append(v)
    return events


# ------------------------------ statistic -------------------------------------
def _score_for_orientation(events, m, delta_rad):
    """Gaussian-kernel axis-clustering score: sum over events of weight to the
    nearest of the 6 face normals."""
    normals = face_normals(m)
    total = 0.0
    for d in events:
        best = 0.0
        for ax in normals:
            dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(d, ax))))
            theta = math.acos(dot)
            w = math.exp(-0.5 * (theta / delta_rad) ** 2)
            if w > best:
                best = w
        total += best
    return total / len(events)


def alignment_statistic(events, rotations):
    """Max clustering score over the fixed orientation pool (handles unknown frame)."""
    delta = math.radians(KERNEL_DELTA_DEG)
    return max(_score_for_orientation(events, m, delta) for m in rotations)


def build_rotations(n, seed):
    rng = random.Random(seed)
    return [rotation_matrix(rng) for _ in range(n)]


def build_null_scores(rotations, seed, n_null=N_NULL, n_events=N_EVENTS):
    """Isotropy null distribution of the statistic: fresh uniform skies, SAME
    maximisation over the orientation pool -> controls the look-elsewhere effect.
    Computed ONCE and reused for every sky scored against it."""
    rng = random.Random(seed)
    scores = []
    for _ in range(n_null):
        sky = [rand_direction(rng) for _ in range(n_events)]
        scores.append(alignment_statistic(sky, rotations))
    return scores


def pvalue_from_null(observed, null_scores):
    exceed = sum(1 for s in null_scores if s >= observed)
    p = (exceed + 1) / (len(null_scores) + 1)          # avoid a hard zero
    mu = sum(null_scores) / len(null_scores)
    sd = math.sqrt(sum((x - mu) ** 2 for x in null_scores) / len(null_scores)) or 1e-12
    return {"p_value": p, "null_mean": mu, "null_sd": sd, "z": (observed - mu) / sd,
            "n_null": len(null_scores)}


# ----------------------- real-data ingestion path -----------------------------
def radec_to_unit(ra_deg, dec_deg):
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    cd = math.cos(dec)
    return (cd * math.cos(ra), cd * math.sin(ra), math.sin(dec))


def load_events(path, energy_cut_ev=None):
    """Load an observed event catalogue and return unit direction vectors.

    Accepts CSV or whitespace rows. If a header is present, columns named
    (case-insensitive) ra/dec[/energy] or x/y/z[/energy] are used; otherwise the
    first numeric columns are read as (ra_deg, dec_deg[, energy_eV]). Rows below
    `energy_cut_ev` are dropped. This is the single frozen entry point through
    which real data (e.g. an Auger / Telescope Array public list) is scored by
    the SAME statistic + null as the controls -- nothing about the test is tuned
    to the data after the fact.
    """
    events, n_total = [], 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if not lines:
        return events, n_total
    delim = "," if "," in lines[0] else None
    body = lines
    header_cols = None
    first = [c.strip().lower() for c in (lines[0].split(delim) if delim else lines[0].split())]
    if any(c in ("ra", "dec", "x", "y", "z", "energy") for c in first):
        header_cols = first
        body = lines[1:]
    for ln in body:
        parts = [c.strip() for c in (ln.split(delim) if delim else ln.split())]
        try:
            nums = [float(p) for p in parts if p != ""]
        except ValueError:
            continue
        if not nums:
            continue
        n_total += 1
        energy = None
        v = None
        if header_cols:
            if "x" in header_cols and "y" in header_cols and "z" in header_cols:
                i, j, k = (header_cols.index("x"), header_cols.index("y"),
                           header_cols.index("z"))
                if max(i, j, k) < len(nums):
                    v = normalize((nums[i], nums[j], nums[k]))
            elif "ra" in header_cols and "dec" in header_cols:
                i, j = header_cols.index("ra"), header_cols.index("dec")
                if max(i, j) < len(nums):
                    v = radec_to_unit(nums[i], nums[j])
            if "energy" in header_cols:
                e = header_cols.index("energy")
                if e < len(nums):
                    energy = nums[e]
        elif len(nums) >= 3:
            v = radec_to_unit(nums[0], nums[1])
            energy = nums[2]
        elif len(nums) == 2:
            v = radec_to_unit(nums[0], nums[1])
        if v is None:
            continue
        if energy_cut_ev is not None and energy is not None and energy < energy_cut_ev:
            continue
        events.append(v)
    return events, n_total


def unit_to_radec(v):
    ra = math.degrees(math.atan2(v[1], v[0])) % 360.0
    dec = math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))
    return ra, dec


def write_catalogue(path, sky, seed):
    """Dump a synthetic sky to an ra/dec/energy CSV (used only to self-test the
    file parser end-to-end; clearly named selftest_* and never a 'result')."""
    rng = random.Random(seed)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("ra,dec,energy\n")
        for v in sky:
            ra, dec = unit_to_radec(v)
            f.write(f"{ra:.6f},{dec:.6f},{rng.uniform(6e19,1.2e20):.4e}\n")


def score_events(events, source, n_total, energy_cut_ev, artifacts_dir=None):
    """Score a list of unit directions with the frozen statistic + matched null."""
    rotations = build_rotations(N_ROTATIONS, BASE_SEED)
    null_scores = build_null_scores(rotations, BASE_SEED + 2, n_events=len(events))
    obs = alignment_statistic(events, rotations)
    pv = pvalue_from_null(obs, null_scores)
    result = {"source_file": source, "n_total": n_total, "n_used": len(events),
              "energy_cut_ev": energy_cut_ev, "stat": obs, **pv,
              "verdict": ("LATTICE_SIGNATURE_DETECTED (investigate systematics)"
                          if pv["p_value"] < SIGNIFICANCE_ALPHA else
                          "NO_SIGNATURE - consistent with isotropy (places a bound)")}
    if artifacts_dir:
        os.makedirs(artifacts_dir, exist_ok=True)
        with open(os.path.join(artifacts_dir, "v7_realdata.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    print(f"[V7] source={source} n_used={result['n_used']} stat={obs:.4f} "
          f"p={pv['p_value']:.4f} z={pv['z']:+.2f} -> {result['verdict']}")
    return result


def score_catalogue(path, energy_cut_ev=None, artifacts_dir="v7_artifacts"):
    """Run the frozen V7 test on an observed catalogue file."""
    events, n_total = load_events(path, energy_cut_ev)
    if len(events) < 30:
        raise ValueError(f"too few usable events after cut ({len(events)})")
    return score_events(events, os.path.basename(path), n_total, energy_cut_ev,
                        artifacts_dir=artifacts_dir)


# ------------------------------- driver ---------------------------------------
def run(artifacts_dir="v7_artifacts"):
    os.makedirs(artifacts_dir, exist_ok=True)
    rotations = build_rotations(N_ROTATIONS, BASE_SEED)
    null_scores = build_null_scores(rotations, BASE_SEED + 2)  # shared isotropy null

    # Null control: isotropic sky must stay silent.
    iso = isotropic_sky(N_EVENTS, BASE_SEED + 1)
    iso_obs = alignment_statistic(iso, rotations)
    iso_p = pvalue_from_null(iso_obs, null_scores)

    # Positive control: a KNOWN lattice (same N_EVENTS) must be detected.
    lat = lattice_sky(N_EVENTS, BASE_SEED + 3)
    lat_obs = alignment_statistic(lat, rotations)
    lat_p = pvalue_from_null(lat_obs, null_scores)

    # Ingestion self-test: prove a real catalogue FILE is parsed and scored
    # correctly end-to-end (parser round-trip + energy cut), not just in-memory.
    lat_csv = os.path.join(artifacts_dir, "selftest_lattice.csv")
    iso_csv = os.path.join(artifacts_dir, "selftest_isotropic.csv")
    write_catalogue(lat_csv, lat, BASE_SEED + 5)
    write_catalogue(iso_csv, iso, BASE_SEED + 6)
    ev_lat, _ = load_events(lat_csv)
    ev_iso, _ = load_events(iso_csv)
    ev_iso_cut, _ = load_events(iso_csv, energy_cut_ev=9e19)
    ing_lat = score_events(ev_lat, "selftest_lattice.csv", len(ev_lat), None)
    ing_iso = score_events(ev_iso, "selftest_isotropic.csv", len(ev_iso), None)
    ingest_ok = (len(ev_lat) == N_EVENTS and len(ev_iso) == N_EVENTS
                 and ing_lat["p_value"] < SIGNIFICANCE_ALPHA
                 and ing_iso["p_value"] > SIGNIFICANCE_ALPHA
                 and len(ev_iso_cut) < len(ev_iso))

    # Gate: trustworthy only if positive fires, null stays silent, and the
    # real-data ingestion path is verified.
    valid = ((lat_p["p_value"] < SIGNIFICANCE_ALPHA)
             and (iso_p["p_value"] > SIGNIFICANCE_ALPHA) and ingest_ok)
    status = "V7_ENGINE_VALID_READY_FOR_REAL_DATA" if valid else "V7_ENGINE_INVALID"

    result = {
        "protocol": {
            "base_seed": BASE_SEED, "n_events": N_EVENTS, "n_rotations": N_ROTATIONS,
            "n_null": N_NULL, "kernel_delta_deg": KERNEL_DELTA_DEG,
            "alpha": SIGNIFICANCE_ALPHA,
            "hypothesis": "arrival directions cluster along hypercubic face-normal axes",
            "cannot_claim": "proof of a simulator; only bounds/rejects a lattice signature",
        },
        "null_control": {"stat": iso_obs, **iso_p},
        "positive_control": {"stat": lat_obs, **lat_p},
        "ingestion_selftest": {
            "parser_roundtrip": (len(ev_lat) == N_EVENTS and len(ev_iso) == N_EVENTS),
            "lattice_fires": ing_lat["p_value"] < SIGNIFICANCE_ALPHA,
            "isotropic_silent": ing_iso["p_value"] > SIGNIFICANCE_ALPHA,
            "energy_cut_filters": len(ev_iso_cut) < len(ev_iso),
            "passed": ingest_ok,
        },
        "engine_status": status,
    }
    with open(os.path.join(artifacts_dir, "v7_controls.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"[V7] status: {status}")
    print(f"[V7] null     (isotropic sky):   stat={iso_obs:.4f} p={iso_p['p_value']:.3f} z={iso_p['z']:+.2f}")
    print(f"[V7] positive (known lattice):   stat={lat_obs:.4f} p={lat_p['p_value']:.4f} z={lat_p['z']:+.2f}")
    print(f"[V7] gate (positive fires AND null silent): {valid}")
    print(f"[V7] ingestion self-test (file parser + energy cut): passed={ingest_ok} "
          f"(n_parsed={len(ev_lat)}/{len(ev_iso)}, cut->{len(ev_iso_cut)})")
    print(f"[V7] wrote {os.path.join(artifacts_dir, 'v7_controls.json')}")
    return result


if __name__ == "__main__":
    # no arg        -> run the control + ingestion self-test
    # <catalogue.csv> [energy_cut_eV] -> score a real event catalogue with the frozen test
    if len(sys.argv) > 1:
        cut = float(sys.argv[2]) if len(sys.argv) > 2 else None
        score_catalogue(sys.argv[1], energy_cut_ev=cut)
    else:
        run()
