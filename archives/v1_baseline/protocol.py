"""
PROOF OF SIMULATION — Protocol Locking & Hashing
Manages the frozen experiment protocol and source hashes.
"""
import hashlib
import json
import os
import platform

PROTOCOL_PATH = "protocol.json"
STATE_PATH = "state.json"
CONTEXT_PATH = "agent_context.json"
CONTEXT_MD_PATH = "context.md"
FEEDBACK_PATH = "feedback.json"

PROTOCOL_VERSION = "1.0.0"

# Frozen protocol parameters
DEFAULT_PROTOCOL = {
    "protocol_version": PROTOCOL_VERSION,
    "grid": {
        "width": 60,
        "height": 30,
        "x_min": -1.8,
        "x_max": 1.8,
        "y_min": -1.0,
        "y_max": 1.0
    },
    "targets": {
        "TARGET_A": "abs(sin(pi*u)*cos(pi*v))",
        "TARGET_B": "sin(pi*u)^2 * cos(pi*v)^2",
        "TARGET_PHASE": "abs(sin(pi*(u+0.07))*cos(pi*(v-0.11)))",
        "eigenmode_range": [1, 2, 3, 4],
        "primary_target": "TARGET_A"
    },
    "score_formula": {
        "weights": {
            "pearson01": 0.25,
            "spearman01": 0.15,
            "mae01": 0.15,
            "gradient01": 0.15,
            "spectral01": 0.15,
            "autocorrelation01": 0.15
        }
    },
    "models": {
        "V0_NONE": {"driver": "V0_NONE", "description": "Baseline Julia (no forcing)"},
        "V1_INV_PI": {"driver": "V1_INV_PI", "description": "1/pi(k) forcing"},
        "V2_SMOOTH": {"driver": "V2_SMOOTH", "description": "Smooth surrogate"},
        "V3_CENTERED_INV_PI": {"driver": "V3_CENTERED_INV_PI", "description": "Centered 1/pi(k)"},
        "V4_PRIME_RESIDUAL": {"driver": "V4_PRIME_RESIDUAL", "description": "Prime residual (1/pi - smooth)"},
        "V5_SHUFFLED": {"driver": "V5_SHUFFLED", "description": "Shuffled 1/pi(k)", "seed": 7331},
        "V6_REVERSED": {"driver": "V6_REVERSED", "description": "Reversed 1/pi(k)"},
        "V7_IMAGINARY": {"driver": "V7_IMAGINARY", "description": "Forcing on imaginary component"},
        "V8_PHASE_RANDOMIZED": {"driver": "V8_PHASE_RANDOMIZED", "description": "Phase-randomized surrogate"}
    },
    "search_range": {
        "cr_min": -1.5,
        "cr_max": 1.0,
        "ci_min": -1.2,
        "ci_max": 1.2
    },
    "default_params": {
        "cr": -0.7,
        "ci": 0.27015,
        "alpha": 1.0,
        "degree": 2,
        "channel": 0,
        "max_iter": 200
    },
    "seeds": {
        "shuffle_seed": 7331,
        "mutation_seed": 133742
    },
    "search_budget": {
        "max_logical_steps": 100,
        "evaluations_per_step": 9,
        "initial_step": 0.02,
        "min_step": 0.00001,
        "max_step": 0.20,
        "step_growth": 1.15,
        "step_decay": 0.5,
        "plateau_threshold": 15,
        "multi_start_after": 20,
        "restart_points": [
            [-0.7, 0.27015],
            [-0.5, 0.27015],
            [-0.9, 0.27015],
            [-0.7, 0.47015],
            [-0.7, 0.07015],
            [-0.25, 0.0],
            [-0.75, 0.0],
            [-1.0, 0.30]
        ],
        "coarse_scout_max": 2,
        "coarse_scout_grid": 11
    },
    "time_budget": {
        "default_seconds": 900,
        "max_seconds": 3600
    },
    "null_budget": {
        "default_null_runs": 8,
        "extended_null_runs": 12,
        "steps_per_null": 30,
        "extended_steps_per_null": 50
    },
    "validation": {
        "depth_levels": [200, 500, 1000, 1500, 2000],
        "resolution_levels": ["60x30", "120x60"],
        "reproducibility_runs": 3
    },
    "benchmark": {
        "seeds_per_world": 20,
        "train_seeds": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "holdout_seeds": [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        "acceptance_accuracy": 0.75
    },
    "research_tracks": {
        "TRACK_A": "V1_INV_PI",
        "TRACK_B": "V4_PRIME_RESIDUAL"
    },
    "alpha_sensitivity": [0.25, 0.50, 1.00, 2.00],
    "thresholds": {
        "search_success": 0.85,
        "strong_result": 0.90,
        "target_score": 0.95,
        "prime_uplift_strong": 0.05,
        "order_uplift_strong": 0.05,
        "shuffle_degradation_strong": 0.05
    }
}


def generate_protocol(path=None):
    """Generate and save protocol.json."""
    p = path or PROTOCOL_PATH
    _atomic_write_json(p, DEFAULT_PROTOCOL)
    return DEFAULT_PROTOCOL


def load_protocol(path=None):
    """Load protocol from file."""
    p = path or PROTOCOL_PATH
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def protocol_hash(path=None):
    """Compute SHA-256 of canonically sorted protocol JSON."""
    proto = load_protocol(path)
    if proto is None:
        return None
    canonical = json.dumps(proto, sort_keys=True, separators=(",", ": "))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_hash(base_dir="."):
    """Compute SHA-256 of all source files."""
    files = [
        "kernel.c",
        "agent_loop.py",
        "controller.py",
        "analysis.py",
        "worldforge.py",
        "protocol.py",
        "db.py",
        "ui.py",
        "report.py"
    ]
    h = hashlib.sha256()
    for fname in sorted(files):
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                h.update(fname.encode("utf-8"))
                h.update(f.read())
    return h.hexdigest()


def load_state(path=None):
    """Load state from state.json."""
    p = path or STATE_PATH
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state, path=None):
    """Atomically save state.json."""
    p = path or STATE_PATH
    _atomic_write_json(p, state)


def load_context(path=None):
    """Load agent_context.json."""
    p = path or CONTEXT_PATH
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_context(ctx, path=None):
    """Atomically save agent_context.json."""
    p = path or CONTEXT_PATH
    _atomic_write_json(p, ctx)


def save_context_md(ctx, path=None):
    """Save human-readable context.md (max 120 lines)."""
    p = path or CONTEXT_MD_PATH
    lines = []
    lines.append("# Proof of Simulation — Context")
    lines.append("")
    lines.append(f"Phase: {ctx.get('phase', 'UNKNOWN')}")
    lines.append(f"Step: {ctx.get('step', 0)}")
    best = ctx.get("best", {})
    lines.append(f"Best Score: {best.get('score', 0):.6f}")
    lines.append(f"Best C: {best.get('cr', 0):.6f} + {best.get('ci', 0):.6f}i")
    lines.append(f"Best Model: {best.get('model', 'N/A')}")
    lines.append("")
    controls = ctx.get("controls", {})
    if controls:
        lines.append("## Controls")
        for k, v in controls.items():
            lines.append(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
    lines.append("")
    lines.append(f"Prime Uplift: {ctx.get('prime_uplift', 0):.4f}")
    lines.append(f"Shuffle Degradation: {ctx.get('shuffle_degradation', 0):.4f}")
    lines.append(f"Plateau Steps: {ctx.get('plateau_steps', 0)}")
    lines.append("")
    lines.append(f"Next Action: {ctx.get('next_action', 'N/A')}")
    lines.append(f"Reason: {ctx.get('next_reason', 'N/A')}")
    lines.append("")
    events = ctx.get("recent_events", [])
    if events:
        lines.append("## Recent Events")
        for ev in events[-5:]:
            lines.append(f"  - {ev}")
    # Trim to 120 lines
    if len(lines) > 120:
        lines = lines[:120]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def save_feedback(feedback, path=None):
    """Atomically save feedback.json."""
    p = path or FEEDBACK_PATH
    _atomic_write_json(p, feedback)


def get_system_info():
    """Get system information for reproducibility."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "cpu": platform.processor() or "unknown",
        "machine": platform.machine()
    }


def _atomic_write_json(path, data):
    """Atomic JSON write."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)
