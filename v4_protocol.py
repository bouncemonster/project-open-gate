"""
Proof of Simulation V4 — protocol specification, hashing and provenance.

V4 protocol: Interior Dynamics, Prime-Specific Contrast and Deep Temporal Response.
80 sections defining the complete experimental protocol.
"""
import hashlib
import json
import os
import platform
import sys
import time


def v4_spec():
    """Return the V4 protocol specification as a dict."""
    return {
        "version": "V4",
        "name": "INTERIOR_DYNAMICS_PRIME_CONTRAST",
        "sections": 80,

        # §3: search domain
        "domain": [-1.5, 1.5, -1.5, 1.5],  # cr_lo, cr_hi, ci_lo, ci_hi

        # §4-5: admissibility thresholds (frozen, not tunable)
        "admissibility": {
            "escaped_fraction_min": 0.05,
            "escaped_fraction_max": 0.95,
            "normalized_entropy_min": 0.20,
            "smooth_std_min": 0.05,
        },

        # §8-9: interior scout
        "scout_grid": 17,
        "scout_domain": [-1.5, 1.5, -1.5, 1.5],

        # §11: tracks
        "tracks": {
            "TRACK_A": "V1_FULL",
            "TRACK_B": "V9_EVENT",
            "TRACK_C": "V10_RESIDUAL",
        },

        # §12: contrast objectives
        "contrasts": {
            "TRACK_A": "C_full = score(V1) - max(score(V0), score(S1), score(S2))",
            "TRACK_B": "C_event = score(V9) - mean(V11_MATCHED_EVENT)",
            "TRACK_C": "C_residual = score(V10) - max(score(S1), score(S2))",
        },

        # §13: control seeds
        "search_control_seeds": [101, 202, 303],
        "holdout_control_seeds": [404, 505, 606, 707, 809],

        # §15-16: matched event seeds (search)
        "matched_event_seeds_search": [101, 202, 303],
        "shifted_event_shifts_search": [1, 5, 11],
        "shifted_event_shifts_holdout": [2, 3, 7, 13, 17, 19, 23],

        # §23-24: search algorithm
        "search": {
            "algorithm": "8-direction hill climbing + deterministic mutation + multi-start",
            "logical_steps": 100,
            "scout_grid": 17,
            "multi_start_count": 8,
        },

        # §25-26: multi-start and search seeds
        "search_seeds": [133742, 233742, 333742, 433742, 533742],

        # §27-29: null
        "null": {
            "standard_runs": 32,
            "preferred_runs": 48,
            "random_param_runs": 32,
            "exceedance_formula": "(1 + count(null_best >= observed_best)) / (1 + N_null)",
            "search_seeds": [133742, 233742, 333742, 433742, 533742,
                             633742, 733742, 833742],
        },

        # §33: boundary distance threshold
        "boundary_suspect_threshold": 0.05,

        # §41: temporal
        "temporal": {
            "Z_CAP": 1e6,
            "max_iter_values": [200, 1000, 5000],
            "circular_shifts": [1, 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47],
            "detrend_window": 10,
            "minimum_pairs": 5,
            "block_bootstrap_block": 5,
            "bootstrap_resamples": 2000,
            "bootstrap_seed": 42,
        },

        # §49: V9 magnitude audit depths
        "v9_audit_depths": [200, 1000, 5000],

        # §57: spectral surrogates
        "spectral_surrogates": 100,
        "spectral_surrogate_seeds": list(range(1000, 1100)),

        # §63: computational budget
        "time_budget": 14400,

        # §64: priority order
        "priority_order": [
            "driver correctness",
            "interior scout",
            "track-local contrasts",
            "matched-event controls",
            "boundary audit",
            "temporal field response",
            "32-48 null runs",
            "100 spectral surrogates",
            "depth/resolution",
            "WORLD_PRIME diagnostics",
        ],

        # §67: holdout targets
        "holdout_targets": ["TARGET_B", "TARGET_PHASE"],
        "holdout_eigenmodes": [(n, m) for n in range(1, 5) for m in range(1, 5)],

        # §69: reproducibility repeats
        "reproducibility_runs": 3,

        # §71: database
        "database": "history_v4.sqlite3",

        # §74: report sections
        "report_sections": [
            "Executive Summary",
            "V3 Audit",
            "Interior Regime Definition",
            "Search Domain",
            "Prime Drivers",
            "Matched Event Controls",
            "Track-Local Results",
            "Boundary Diagnostics",
            "Prime-Specific Contrasts",
            "Difference-Field Analysis",
            "High-Pass Analysis",
            "Temporal Prime Response",
            "Search-Aware Null",
            "Spectral Target Null",
            "Holdout Targets",
            "Reproducibility",
            "WORLD_PRIME Detector",
            "V1/V2/V3/V4 Comparison",
            "Limitations",
            "Final Scientific Conclusion",
        ],

        # §76: final statuses
        "statuses": [
            "NO_PRIME_SPECIFIC_SIGNAL",
            "GENERIC_RESONANCE",
            "BOUNDARY_ARTIFACT",
            "DYNAMICAL_REGIME_ARTIFACT",
            "PRIME_CANDIDATE_SIGNAL",
            "ROBUST_PRIME_SPECIFIC_SIGNAL",
            "METHODOLOGICAL_ARTIFACT",
            "IMPLEMENTATION_ERROR",
            "UNRESOLVED",
        ],

        # S2 window
        "s2_windows": [3, 5, 7],

        # Validation
        "validation": {
            "depths": [100, 200, 500, 1000],
            "resolutions": [(30, 15), (60, 30), (120, 60)],
            "alpha_values": [0.5, 1.0, 2.0],
            "local_offsets": [(-0.01, 0), (0.01, 0), (0, -0.01), (0, 0.01),
                              (-0.01, -0.01), (0.01, 0.01), (-0.01, 0.01), (0.01, -0.01)],
            "repeat_seeds": [7331, 8331, 9331],
        },

        # Generic geometry controls (§56)
        "generic_controls": [
            "constant", "x_ramp", "y_ramp", "bilinear", "radial",
            "low_frequency_analytic",
        ],

        # Kernel parameters
        "kernel": {
            "width": 60,
            "height": 30,
            "max_iter": 200,
            "alpha": 1.0,
            "degree": 2,
            "channel": 0,
            "seed": 7331,
            "target": "TARGET_A",
        },
    }


def protocol_v4_hash(proto=None):
    """SHA-256 of the canonical V4 protocol JSON."""
    if proto is None:
        proto = v4_spec()
    raw = json.dumps(proto, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def source_v4_hash():
    """SHA-256 over all V4 Python source files."""
    h = hashlib.sha256()
    for fn in sorted(["v4_pipeline.py", "v4_search.py", "v4_math.py",
                       "v4_store.py", "v4_protocol.py", "report_v4.py"]):
        path = os.path.join(os.path.dirname(__file__) or ".", fn)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                h.update(fn.encode())
                h.update(f.read())
    return h.hexdigest()


def binary_v4_hash(exe_path):
    """SHA-256 of the compiled kernel binary."""
    h = hashlib.sha256()
    with open(exe_path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def environment():
    """Capture runtime environment for provenance."""
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "cpu": platform.processor() or "unknown",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def save_protocol_v4():
    """Save the V4 protocol JSON and return it."""
    proto = v4_spec()
    path = "protocol_v4.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(proto, f, indent=2, sort_keys=True, ensure_ascii=False)
    return proto
