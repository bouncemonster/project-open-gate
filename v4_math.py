"""
Proof of Simulation V4 — arithmetic sequences, admissibility, contrasts,
S1 audit, V9_Z normalised event driver, and spectral utilities.

Extends v3_math with V4-specific functionality:
  - check_admissibility(): V0 diagnostic filter
  - compute_contrast(): C_full, C_event, C_residual
  - s1_audit(): Riemann R stability check at small k
  - seq_V9_Z(): normalised event driver (mean=0, RMS=1)
  - seq_V9_RMS_matched(): event driver matched to centered-P RMS
"""
import math
import v3_math as M

# Re-export everything from v3_math so callers can use v4_math as drop-in
from v3_math import (  # noqa: F401
    sieve_is_prime, pi_counts, sequence_hash,
    ei, li, mobius, riemann_R,
    seq_P, seq_E, seq_residual, seq_S1_riemann, seq_S2,
    mean, rms, standardize, center, scale_to_rms,
    splitmix64, event_positions_amplitudes,
    seq_V11_matched_event, seq_V12_shifted_event, seq_V13_gap_matched,
    seq_V5_shuffled,
    dct2, dct2_matrix, dct_low_energy, dct_lowpass_field,
    dct_sign_surrogate,
    field_constant, field_x_ramp, field_y_ramp, field_bilinear,
    field_radial, low_frequency_family,
    mean_flat, std_flat, field_entropy, field_autocorr,
    field_gradient_energy, field_anisotropy, target_features,
    circular_shift, block_bootstrap_ci, _pearson,
)


# ---------------------------------------------------------------- V4 admissibility
def check_admissibility(escaped_fraction, normalized_entropy, smooth_std):
    """V4 dynamic admissibility (protocol §5).

    A candidate point is admissible only if V0 diagnostics indicate a
    non-degenerate experimental regime — not all escaping, not all bounded,
    and with sufficient spatial structure.

    Returns (admissible: bool, reason: str).
    """
    if escaped_fraction < 0.05:
        return False, "escaped_fraction < 0.05"
    if escaped_fraction > 0.95:
        return False, "escaped_fraction > 0.95"
    if normalized_entropy < 0.20:
        return False, f"normalized_entropy {normalized_entropy:.4f} < 0.20"
    if smooth_std < 0.05:
        return False, f"smooth_std {smooth_std:.4f} < 0.05"
    return True, "admissible"


# ---------------------------------------------------------------- V4 contrasts
def compute_contrast_C_full(score_V1, score_V0, score_S1, score_S2):
    """C_full = score(V1) - max(score(V0), score(S1), score(S2))."""
    return score_V1 - max(score_V0, score_S1, score_S2)


def compute_contrast_C_event(score_V9, mean_V11):
    """C_event = score(V9) - mean(V11_MATCHED_EVENT)."""
    return score_V9 - mean_V11


def compute_contrast_C_residual(score_V10, score_S1, score_S2):
    """C_residual = score(V10) - max(score(S1), score(S2))."""
    return score_V10 - max(score_S1, score_S2)


# ---------------------------------------------------------------- S1 audit
def s1_audit(max_iter=200):
    """Audit S1_ANALYTIC (Riemann R) for small-k numerical issues (protocol §53-54).

    Checks S1(k) for k=1..max_iter: finite, positive, monotonic enough.
    Special attention to k=1,2,3 where Riemann R has small-x issues.
    Returns dict with audit results.
    """
    S1 = seq_S1_riemann(max_iter)
    issues = []
    values = {}
    for k in range(1, min(max_iter + 1, 21)):
        v = S1[k]
        values[k] = v
        if not math.isfinite(v):
            issues.append(f"k={k}: not finite ({v})")
        if v <= 0:
            issues.append(f"k={k}: not positive ({v})")
    # Check monotonicity over first 20 values (S1 should be roughly decreasing)
    decreasing_count = 0
    for k in range(2, min(21, max_iter + 1)):
        if S1[k] <= S1[k - 1]:
            decreasing_count += 1
    # Check Riemann R values at small k
    R_values = {}
    for k in range(1, 6):
        R_values[k] = riemann_R(float(k))
    return {
        "S1_values_first_20": values,
        "Riemann_R_small_k": R_values,
        "issues": issues,
        "monotonicity_decreasing_fraction": decreasing_count / min(19, max_iter),
        "ok": len(issues) == 0,
    }


# ---------------------------------------------------------------- V9 normalised drivers
def seq_V9_Z(E, max_iter):
    """V9_Z: normalised event driver with mean=0, RMS=1 (protocol §51)."""
    # Center
    m = sum(E[k] for k in range(1, max_iter + 1)) / max_iter
    centered = [0.0] + [E[k] - m for k in range(1, max_iter + 1)]
    # Compute RMS
    r = math.sqrt(sum(centered[k] ** 2 for k in range(1, max_iter + 1)) / max_iter)
    if r < 1e-15:
        return [0.0] * (max_iter + 1)
    return [0.0] + [centered[k] / r for k in range(1, max_iter + 1)]


def seq_V9_RMS_MATCHED(E, P_centered, max_iter):
    """V9_RMS_MATCHED: centered E rescaled to match RMS of centered P (protocol §51)."""
    m = sum(E[k] for k in range(1, max_iter + 1)) / max_iter
    centered = [0.0] + [E[k] - m for k in range(1, max_iter + 1)]
    target_rms = M.rms(P_centered, max_iter, 200)
    return scale_to_rms(centered, max_iter, target_rms, 200)


# ---------------------------------------------------------------- Driver audit (protocol §55)
def driver_audit(max_iter=200):
    """Save S1, V1, difference sequences and compute comparison stats (protocol §55)."""
    pi = pi_counts(max_iter)
    P = seq_P(pi, max_iter)
    S1 = seq_S1_riemann(max_iter)
    diff = [0.0] + [P[k] - S1[k] for k in range(1, max_iter + 1)]
    abs_diffs = [abs(diff[k]) for k in range(1, max_iter + 1)]
    return {
        "max_abs_diff": max(abs_diffs),
        "mean_abs_diff": sum(abs_diffs) / len(abs_diffs),
        "RMSE": math.sqrt(sum(d * d for d in abs_diffs) / len(abs_diffs)),
        "correlation": _pearson(
            [P[k] for k in range(1, max_iter + 1)],
            [S1[k] for k in range(1, max_iter + 1)]),
    }


# ---------------------------------------------------------------- V9 driver magnitude audit (protocol §49)
def event_magnitude_audit(E, max_iter):
    """For a given max_iter, report event_count, RMS(E), max_abs(E), min_abs_nonzero(E)."""
    nonzero = [abs(E[k]) for k in range(1, max_iter + 1) if abs(E[k]) > 1e-18]
    rms_e = math.sqrt(sum(E[k] ** 2 for k in range(1, max_iter + 1)) / max_iter)
    return {
        "max_iter": max_iter,
        "event_count": len(nonzero),
        "RMS_E": rms_e,
        "max_abs_E": max(nonzero) if nonzero else 0.0,
        "min_abs_nonzero_E": min(nonzero) if nonzero else 0.0,
    }


# ---------------------------------------------------------------- Boundary distance (protocol §33)
def boundary_distance(cr, ci, domain):
    """Compute fractional distance to nearest domain boundary.

    Returns (distance_frac, nearest_edge) where distance_frac is the
    minimum fractional distance to any edge (0 = on boundary, 0.5 = center).
    """
    lo_cr, hi_cr, lo_ci, hi_ci = domain
    d_lo_cr = (cr - lo_cr) / (hi_cr - lo_cr)
    d_hi_cr = (hi_cr - cr) / (hi_cr - lo_cr)
    d_lo_ci = (ci - lo_ci) / (hi_ci - lo_ci)
    d_hi_ci = (hi_ci - ci) / (hi_ci - lo_ci)
    d = min(d_lo_cr, d_hi_cr, d_lo_ci, d_hi_ci)
    if d == d_lo_cr:
        edge = "cr_lo"
    elif d == d_hi_cr:
        edge = "cr_hi"
    elif d == d_lo_ci:
        edge = "ci_lo"
    else:
        edge = "ci_hi"
    return d, edge


# ---------------------------------------------------------------- Delta field metrics (protocol §37)
def delta_field_metrics(delta_field, target_residual, W, H):
    """Compute RMS, entropy, DCT low/high energy, autocorrelation,
    correlation with target residual for a delta field."""
    rms_val = M.std_flat(delta_field)
    low, high = M.dct_low_energy(delta_field, W, H, keep=3)
    return {
        "RMS": rms_val,
        "max_abs": max(abs(x) for x in delta_field),
        "entropy": M.field_entropy(delta_field),
        "DCT_low_energy": low,
        "DCT_high_energy": high,
        "autocorrelation": M.field_autocorr(delta_field, W, H),
        "correlation_with_target_residual": (
            M._pearson(delta_field, target_residual)
            if rms_val > 0 and M.std_flat(target_residual) > 0 else 0.0),
    }
