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

    # Gate: the test is trustworthy only if positive fires AND null stays silent.
    valid = (lat_p["p_value"] < SIGNIFICANCE_ALPHA) and (iso_p["p_value"] > SIGNIFICANCE_ALPHA)
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
        "engine_status": status,
    }
    with open(os.path.join(artifacts_dir, "v7_controls.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"[V7] status: {status}")
    print(f"[V7] null     (isotropic sky):   stat={iso_obs:.4f} p={iso_p['p_value']:.3f} z={iso_p['z']:+.2f}")
    print(f"[V7] positive (known lattice):   stat={lat_obs:.4f} p={lat_p['p_value']:.4f} z={lat_p['z']:+.2f}")
    print(f"[V7] gate (positive fires AND null silent): {valid}")
    print(f"[V7] wrote {os.path.join(artifacts_dir, 'v7_controls.json')}")
    return result


if __name__ == "__main__":
    run()
