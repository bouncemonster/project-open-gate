"""V5.3 Feature layer: five explicit families (spec §9).

F1 Spatial, F2 Spectral, F3 Marginal  -> extracted from a single snapshot
                                          via v5_math.extract_full_fingerprint
F4 Temporal                            -> TRACK B only, from frame sequences
F5 State-space / dynamical             -> from frame sequences

Feature families are kept separate; headline metrics are reported per
family group (A: snapshot only = conservative; B: + temporal) per spec §6.
"""
import math
from collections import Counter
from typing import List, Dict

from v5_math import extract_full_fingerprint

# Family assignment for the V5.x fingerprint features (F1/F2/F3)
SPATIAL_FEATURES = ["entropy", "moment_mean", "moment_var", "moment_skew",
                    "moment_kurt", "acf_lag1", "acf_lag2", "acf_lag3",
                    "acf_lag4", "acf_lag5", "grad_mean", "grad_std",
                    "lap_mean", "lap_std", "anisotropy", "edge_density",
                    "local_variance", "cc_n_components", "cc_mean_size",
                    "cc_max_size"]
SPECTRAL_FEATURES = ["dct_low", "dct_mid", "dct_high", "high_low_ratio",
                     "spectral_sparsity", "spectral_slope"]
MARGINAL_FEATURES = ["quantization_level", "repeated_value_fraction",
                     "recurrence_exact", "recurrence_near", "recurrence_entropy",
                     "compression_ratio", "run_length_mean", "run_length_std",
                     "aliasing_score", "sampling_artifact_score",
                     "float64_float32_diff", "float64_float16_diff",
                     "precision_sensitivity"]

TEMPORAL_PREFIX = "T_"
DYNAMICAL_PREFIX = "D_"


def snapshot_features(field: List[float], w: int, h: int) -> Dict[str, float]:
    """F1+F2+F3 from one frame (Track A observation set)."""
    return extract_full_fingerprint(field, w, h)


# ---------------------------------------------------------------------------
# F4 Temporal features (TRACK B)
# ---------------------------------------------------------------------------

def _cell_series(frames: List[List[float]], w: int, h: int, n_cells: int = 12):
    """Sample n_cells deterministic cell time-series from the trajectory."""
    total = w * h
    idxs = [int((k + 0.5) * total / n_cells) for k in range(n_cells)]
    return [[fr[k] for fr in frames] for k in idxs]


def _mean_series(frames: List[List[float]]) -> List[float]:
    n = len(frames[0])
    return [sum(fr) / n for fr in frames]


def _autocorr(x: List[float], lag: int) -> float:
    n = len(x)
    mu = sum(x) / n
    var = sum((v - mu) ** 2 for v in x)
    if var < 1e-18 or lag >= n:
        return 0.0
    cov = sum((x[t] - mu) * (x[t + lag] - mu) for t in range(n - lag))
    return cov / var


def _permutation_entropy(x: List[float], order: int = 3) -> float:
    n = len(x)
    if n < order + 1:
        return 0.0
    pats = Counter()
    for t in range(n - order):
        window = x[t:t + order + 1]
        pat = tuple(sorted(range(order + 1), key=lambda i: window[i]))
        pats[pat] += 1
    tot = sum(pats.values())
    ent = -sum((c / tot) * math.log2(c / tot) for c in pats.values() if c)
    return ent / math.log2(math.factorial(order + 1))


def _transition_entropy(series: List[float], nbins: int = 8) -> float:
    """Entropy of discretized state-to-state transitions."""
    if not series:
        return 0.0
    lo, hi = min(series), max(series)
    rng = hi - lo if hi > lo else 1.0
    disc = [min(nbins - 1, max(0, int((v - lo) / rng * nbins))) for v in series]
    trans = Counter(zip(disc, disc[1:]))
    tot = sum(trans.values())
    if tot == 0:
        return 0.0
    return -sum((c / tot) * math.log2(c / tot) for c in trans.values()) / math.log2(tot) \
        if tot > 1 else 0.0


def _cycle_estimate(x: List[float]) -> float:
    """Mean positive-going zero-crossing period (crude but interpretable)."""
    mu = sum(x) / len(x)
    cross = [t for t in range(1, len(x)) if x[t - 1] < mu <= x[t]]
    if len(cross) < 2:
        return float(len(x))
    diffs = [cross[i] - cross[i - 1] for i in range(1, len(cross))]
    return sum(diffs) / len(diffs)


def _temporal_compression(x: List[float]) -> float:
    """Run-length entropy of the sign of first differences (1-bit LZ proxy)."""
    signs = [1 if x[t] >= x[t - 1] else 0 for t in range(1, len(x))]
    runs = []
    cur = 1
    for i in range(1, len(signs)):
        if signs[i] == signs[i - 1]:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    runs.append(cur)
    tot = sum(runs)
    if tot == 0:
        return 0.0
    c = Counter(runs)
    return -sum((v / tot) * math.log2(v / tot) for v in c.values())


def temporal_features(frames: List[List[float]], w: int, h: int) -> Dict[str, float]:
    """F4: temporal feature family over the trajectory."""
    ms = _mean_series(frames)
    series = _cell_series(frames, w, h)
    feats = {}
    # mean-field dynamics
    for lag in (1, 2, 4, 8):
        feats[f"{TEMPORAL_PREFIX}acf_mean_lag{lag}"] = _autocorr(ms, lag)
    feats[f"{TEMPORAL_PREFIX}perm_entropy"] = _permutation_entropy(ms)
    feats[f"{TEMPORAL_PREFIX}trans_entropy"] = _transition_entropy(ms)
    feats[f"{TEMPORAL_PREFIX}cycle"] = _cycle_estimate(ms)
    feats[f"{TEMPORAL_PREFIX}compression"] = _temporal_compression(ms)
    feats[f"{TEMPORAL_PREFIX}drift"] = abs(ms[-1] - ms[0])
    feats[f"{TEMPORAL_PREFIX}var_of_var"] = _var([_var(s) for s in series]) \
        if series else 0.0
    # per-cell aggregate statistics (mean over sampled cells)
    ac1 = _mean([_autocorr(s, 1) for s in series])
    ac3 = _mean([_autocorr(s, 3) for s in series])
    pe = _mean([_permutation_entropy(s) for s in series])
    te = _mean([_transition_entropy(s) for s in series])
    mad = _mean([_mean([abs(s[t] - s[t - 1]) for t in range(1, len(s))]) for s in series])
    frozen = _mean([1.0 if max(s) - min(s) < 1e-12 else 0.0 for s in series])
    feats[f"{TEMPORAL_PREFIX}acf_cell_lag1"] = ac1
    feats[f"{TEMPORAL_PREFIX}acf_cell_lag3"] = ac3
    feats[f"{TEMPORAL_PREFIX}perm_cell"] = pe
    feats[f"{TEMPORAL_PREFIX}trans_cell"] = te
    feats[f"{TEMPORAL_PREFIX}mean_abs_step"] = mad
    feats[f"{TEMPORAL_PREFIX}frozen_cell_frac"] = frozen
    # higher-order temporal moment: skew of increments
    incs = [ms[t] - ms[t - 1] for t in range(1, len(ms))]
    feats[f"{TEMPORAL_PREFIX}inc_skew"] = _skew(incs)
    feats[f"{TEMPORAL_PREFIX}inc_kurt"] = _kurt(incs)
    return feats


# ---------------------------------------------------------------------------
# F5 State-space / dynamical features
# ---------------------------------------------------------------------------

def _var(x):
    n = len(x)
    if n < 2:
        return 0.0
    mu = sum(x) / n
    return sum((v - mu) ** 2 for v in x) / (n - 1)


def _mean(x):
    return sum(x) / len(x) if x else 0.0


def _skew(x):
    n = len(x)
    if n < 3:
        return 0.0
    mu = sum(x) / n
    s = math.sqrt(sum((v - mu) ** 2 for v in x) / n)
    if s < 1e-18:
        return 0.0
    return sum(((v - mu) / s) ** 3 for v in x) / n


def _kurt(x):
    n = len(x)
    if n < 4:
        return 0.0
    mu = sum(x) / n
    s = math.sqrt(sum((v - mu) ** 2 for v in x) / n)
    if s < 1e-18:
        return 0.0
    return sum(((v - mu) / s) ** 4 for v in x) / n - 3.0


def _embed(x: List[float], dim: int, delay: int = 2):
    pts = []
    for t in range(len(x) - (dim - 1) * delay):
        pts.append(tuple(x[t + k * delay] for k in range(dim)))
    return pts


def _correlation_sum(pts, r):
    if len(pts) < 2:
        return 0.0
    cnt = 0
    tot = 0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(pts[i], pts[j])))
            cnt += 1 if d < r else 0
            tot += 1
    return cnt / tot if tot else 0.0


def _corr_dim_estimate(x: List[float], dim: int = 3) -> float:
    """Grassberger-Procaccia slope over two radii (estimate, not a claim of
    theoretical dimension; spec §9 requires 'estimated')."""
    pts = _embed(x, dim)
    if len(pts) < 10:
        return 0.0
    scale = math.sqrt(_var(x)) if _var(x) > 0 else 1.0
    r1, r2 = 0.1 * scale, 0.4 * scale
    c1, c2 = _correlation_sum(pts, r1), _correlation_sum(pts, r2)
    if c1 <= 0 or c2 <= 0 or c1 >= c2:
        return 0.0
    return math.log(c2 / c1) / math.log(r2 / r1)


def _recurrence_density(x: List[float], tol_frac: float = 0.1) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mu = sum(x) / n
    s = math.sqrt(sum((v - mu) ** 2 for v in x) / n)
    if s < 1e-18:
        return 1.0
    tol = tol_frac * s
    cnt = 0
    tot = 0
    for i in range(n):
        for j in range(i + 2, n):        # exclude adjacent trivial recurrences
            cnt += 1 if abs(x[i] - x[j]) < tol else 0
            tot += 1
    return cnt / tot if tot else 0.0


def _lyapunov_like(x: List[float]) -> float:
    """Finite-time divergence estimate: mean log growth of successive
    increments. Explicitly an ESTIMATE (spec §9: no theoretical claims)."""
    incs = [abs(x[t] - x[t - 1]) for t in range(1, len(x))]
    logs = [math.log((incs[i + 1] + 1e-15) / (incs[i] + 1e-15))
            for i in range(len(incs) - 1)]
    return _mean(logs) if logs else 0.0


def _state_occupancy(x: List[float], nbins: int = 10) -> float:
    lo, hi = min(x), max(x)
    rng = hi - lo if hi > lo else 1.0
    disc = [min(nbins - 1, max(0, int((v - lo) / rng * nbins))) for v in x]
    c = Counter(disc)
    tot = len(x)
    return -sum((v / tot) * math.log2(v / tot) for v in c.values())


def _return_time_stats(x: List[float]) -> float:
    """Std of inter-recurrence times at coarse quantization (poincare-ish)."""
    lo, hi = min(x), max(x)
    rng = hi - lo if hi > lo else 1.0
    disc = [min(3, max(0, int((v - lo) / rng * 4))) for v in x]
    last = {}
    gaps = []
    for t, s in enumerate(disc):
        if s in last:
            gaps.append(t - last[s])
        last[s] = t
    return math.sqrt(_var([float(g) for g in gaps])) if len(gaps) > 2 else 0.0


def dynamical_features(frames: List[List[float]], w: int, h: int) -> Dict[str, float]:
    """F5: state-space/dynamical family over the trajectory."""
    ms = _mean_series(frames)
    series = _cell_series(frames, w, h, n_cells=6)
    feats = {}
    feats[f"{DYNAMICAL_PREFIX}corr_dim"] = _corr_dim_estimate(ms)
    feats[f"{DYNAMICAL_PREFIX}rec_density"] = _recurrence_density(ms)
    feats[f"{DYNAMICAL_PREFIX}lyap_est"] = _lyapunov_like(ms)
    feats[f"{DYNAMICAL_PREFIX}occupancy"] = _state_occupancy(ms)
    feats[f"{DYNAMICAL_PREFIX}returntime_std"] = _return_time_stats(ms)
    feats[f"{DYNAMICAL_PREFIX}corr_dim_cell"] = _mean([_corr_dim_estimate(s) for s in series])
    feats[f"{DYNAMICAL_PREFIX}rec_density_cell"] = _mean([_recurrence_density(s) for s in series])
    feats[f"{DYNAMICAL_PREFIX}lyap_cell"] = _mean([_lyapunov_like(s) for s in series])
    # local divergence of the field between consecutive frames (Jacobian proxy)
    divs = []
    for t in range(1, len(frames)):
        a, b = frames[t - 1], frames[t]
        step = max(1, (w * h) // 200)
        dv = _mean([abs(b[k] - a[k]) for k in range(0, len(a), step)])
        divs.append(dv)
    feats[f"{DYNAMICAL_PREFIX}local_divergence"] = _mean(divs)
    feats[f"{DYNAMICAL_PREFIX}divergence_var"] = _var(divs) if len(divs) > 2 else 0.0
    # transition sparsity: fraction of cells that did not change at all
    last_a, last_b = frames[-2], frames[-1]
    feats[f"{DYNAMICAL_PREFIX}transition_sparsity"] = \
        sum(1 for a, b in zip(last_a, last_b) if a == b) / len(last_a)
    return feats


# ---------------------------------------------------------------------------
# Family registry
# ---------------------------------------------------------------------------

def full_features_snapshot(field, w, h):
    return snapshot_features(field, w, h)


def full_features_trackb(field_final, frames, w, h):
    f = snapshot_features(field_final, w, h)
    f.update(temporal_features(frames, w, h))
    f.update(dynamical_features(frames, w, h))
    return f


def family_of(name: str) -> str:
    if name.startswith(TEMPORAL_PREFIX):
        return "temporal"
    if name.startswith(DYNAMICAL_PREFIX):
        return "dynamical"
    if name in SPATIAL_FEATURES:
        return "spatial"
    if name in SPECTRAL_FEATURES:
        return "spectral"
    if name in MARGINAL_FEATURES:
        return "marginal"
    return "other"


FEATURE_FAMILIES = ["spatial", "spectral", "marginal", "temporal", "dynamical"]
