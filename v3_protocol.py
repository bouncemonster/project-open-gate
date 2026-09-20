"""
Proof of Simulation V3 — protocol freeze and provenance hashing.

The V3 protocol is fixed before any V3 search. Its canonical JSON, the V3
source set (including the driver registry) and the V3 binary are all hashed and
recorded, so the report can prove which code produced which numbers.
"""
import hashlib
import json
import os
import platform
import sys

PROTOCOL_V3_PATH = "protocol_v3.json"
REPRO_V3_PATH = "reproducibility_v3.json"

# Source files whose exact bytes are part of the V3 source hash.
V3_SOURCE_FILES = [
    "kernel_v3.c",
    "v3_math.py",
    "v3_protocol.py",
    "v3_store.py",
    "v3_search.py",
    "v3_pipeline.py",
]

DEFAULT_PROTOCOL_V3 = {
    "experiment": "V3_DEEP_ARITHMETIC_ISOLATION",
    "model_id": "V3_ARITHMETIC_ISOLATION",
    "kernel_binary": "kernel_v3",
    "dynamics": {
        "equation": "z(k)=z(k-1)^2+c+alpha*D(k)",
        "k_start": 1,
        "alpha_primary": 1.0,
        "degree_primary": 2,
        "channel_primary": 0,
        "z0_grid": [[-1.8, 1.8], [-1.0, 1.0]],
        "escape_radius_sq": 4.0,
        "selectable_drivers": ["EXTERNAL_DRIVER_FILE"],
    },
    "domains": {
        "main": [-2.0, 2.0, -2.0, 2.0],
        "expanded": [-3.0, 3.0, -3.0, 3.0],
        "note": "expanded is a diagnostic comparison; it never replaces main",
    },
    "grid": {"width": 60, "height": 30, "max_iter_primary": 200},
    "score": {
        "weights": {"pearson01": 0.25, "spearman01": 0.15, "mae01": 0.15,
                    "gradient01": 0.15, "spectral01": 0.15, "autocorrelation01": 0.15},
        "frozen": True,
    },
    "search": {
        "algorithm": "hill_climbing",
        "logical_steps": 100,
        "candidates_per_step": 9,
        "scout_grid": 17,
        "expected_per_run": 289 + 100 * 9,
        "seeds": [133742, 233742, 333742],
        "multi_start_points": [[-0.7, 0.27015], [0.285, 0.01], [-0.8, 0.156],
                               [0.285, 0.0], [-1.0, 0.0]],
    },
    "tracks": {
        "TRACK_A": "V1_FULL",
        "TRACK_B": "V9_EVENT",
        "TRACK_C": "V10_RESIDUAL",
    },
    "drivers": {
        "V0_NONE": "D(k)=0",
        "V1_FULL": "D(k)=P(k)=1/max(pi(k),1), P(0)=1",
        "S1_ANALYTIC": "D(k)=1/max(R(k),1), Riemann R, k<=2 protected",
        "S2_DATA_SMOOTHED": "D(k)=moving average of P, window fixed in advance",
        "V9_EVENT": "D(k)=E(k)=P(k)-P(k-1)",
        "V9_MATCHED": "E centered, rescaled to reference RMS(E)",
        "V9_ENERGY_MATCHED": "E scaled so reference RMS equals RMS(P-centered)",
        "V10_RESIDUAL": "D(k)=standardize(P-S1_riemann) over first 200",
        "V10_MATCHED": "V10 scaled so reference RMS equals RMS(P-centered)",
        "V11_MATCHED_EVENT": "real event amplitudes/count, permuted positions",
        "V12_SHIFTED_EVENT": "exact E circularly shifted",
        "V13_GAP_MATCHED_EVENT": "event count/amplitudes, permuted circular gaps",
        "V5_SHUFFLED": "P shuffled with SplitMix64(7331)",
        "V14_CONSTANT_FIELD": "field control F=0.5 (not a temporal driver)",
        "V15_X_RAMP": "field control F=u",
        "V16_Y_RAMP": "field control F=v",
        "V17_BILINEAR_RAMP": "field control F=u*v",
        "V18_RADIAL_GRADIENT": "field control F=hypot(u-0.5,v-0.5)",
    },
    "matched_event": {"seeds": [101, 202, 303, 404, 505]},
    "shifted_event": {"shifts": [1, 2, 3, 5, 7, 11, 13, 17, 19, 23]},
    "s2_windows": [3, 5, 9],
    "targets": {
        "primary": "TARGET_A",
        "holdout_fields": ["TARGET_B", "TARGET_PHASE"],
        "spectral_surrogates": 10,
        "spectral_surrogate_seeds": [9001, 9002, 9003, 9004, 9005,
                                     9006, 9007, 9008, 9009, 9010],
        "low_frequency_controls": ["L1_u", "L2_v", "L3_uv", "L4_abs_sin_pi_u",
                                    "L5_abs_cos_pi_v", "L6_sin_sin"],
        "highpass_keep_modes": 3,
    },
    "boundary": {
        "cr_values": [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0],
        "ci_offsets": [-0.05, -0.01, 0.0, 0.01, 0.05],
        "gradient_step": 0.001,
    },
    "null": {
        "type": "random_search_null",
        "standard_runs": 32,
        "preferred_runs": 48,
        "same_budget_as_primary": True,
        "search_seeds": list(range(5001, 5049)),
        "exceedance_formula": "(1+count(null_best>=observed_best))/(1+N_null)",
    },
    "validation": {
        "depths": [200, 500, 1000, 1500, 2000],
        "resolutions": [[60, 30], [120, 60]],
        "alpha_values": [0.25, 0.5, 1.0, 2.0],
        "local_offsets": [[0.001, 0], [-0.001, 0], [0, 0.001], [0, -0.001]],
        "repeat_seeds": [133742, 233742, 333742],
    },
    "temporal": {
        "depths_full": 5000,
        "depths_light": 1000,
        "drivers": ["V0_NONE", "V1_FULL", "V9_EVENT", "V10_RESIDUAL"],
        "detrend_window": 21,
        "matching_radius": 10,
        "minimum_pairs": 20,
        "circular_shifts": [1, 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31],
        "block_bootstrap_block": 21,
        "bootstrap_resamples": 1000,
        "bootstrap_seed": 424242,
    },
    "benchmark": {
        "policy": "WORLD_PRIME is holdout only; detector frozen as DETECTOR_V1",
        "prime_seeds": list(range(1, 21)),
        "feature_audit_cohorts": ["WORLD_PRIME", "WORLD_LATTICE", "WORLD_PRNG",
                                   "WORLD_HASH", "WORLD_ANALYTIC"],
    },
    "status_values": ["GENERIC_RESONANCE", "NO_PRIME_SPECIFIC_SIGNAL",
                      "PRIME_CANDIDATE_SIGNAL", "ROBUST_PRIME_SPECIFIC_SIGNAL",
                      "BOUNDARY_ARTIFACT", "CONTROL_IMPLEMENTATION_ERROR",
                      "METHODOLOGICAL_ARTIFACT", "IMPLEMENTATION_ERROR"],
    "forbidden_claims": [
        "The universe is a simulation.", "This proves simulation.",
        "Prime numbers are the code of reality.", "This is quantum evidence.",
    ],
}


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def protocol_v3_hash(proto=None):
    proto = proto or DEFAULT_PROTOCOL_V3
    return hashlib.sha256(canonical_json(proto).encode("utf-8")).hexdigest()


def save_protocol_v3(path=PROTOCOL_V3_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_PROTOCOL_V3, f, indent=2, ensure_ascii=False, sort_keys=True)
    return DEFAULT_PROTOCOL_V3


def load_protocol_v3(path=PROTOCOL_V3_PATH):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def source_v3_hash(base_dir="."):
    h = hashlib.sha256()
    for name in sorted(V3_SOURCE_FILES):
        p = os.path.join(base_dir, name)
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(name.encode("utf-8"))
                h.update(f.read())
    return h.hexdigest()


def binary_v3_hash(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def environment():
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "machine": platform.machine(),
    }
