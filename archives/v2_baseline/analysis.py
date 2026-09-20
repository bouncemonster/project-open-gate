"""
PROOF OF SIMULATION — Analysis Module
Diagnostic metrics, summary queries, and data analysis.
"""
import json
import sys
import os
import math

import db


def summary(conn, run_id=None):
    """Print max 30-line summary: best, controls, uplifts, null, validation, next action."""
    best = db.get_best(conn, run_id)
    if not best:
        print("No evaluations yet.")
        return

    lines = []
    lines.append(f"Best Score:  {best['score']:.6f}")
    lines.append(f"Best C:      {best['cr']:.6f} + {best['ci']:.6f}i")
    lines.append(f"Best Model:  {best['model_id']}")
    lines.append(f"Best Driver: {best['driver']}")
    lines.append(f"Total Evals: {db.count_evaluations(conn, run_id)}")
    lines.append("")

    # Controls: get evaluations at best cr/ci with different models
    evals = db.get_all_evaluations(conn, run_id)
    control_scores = {}
    for e in evals:
        if (abs(e["cr"] - best["cr"]) < 1e-6 and
            abs(e["ci"] - best["ci"]) < 1e-6):
            control_scores[e["model_id"]] = e["score"]

    if control_scores:
        lines.append("Controls at best point:")
        for model, score in sorted(control_scores.items()):
            lines.append(f"  {model}: {score:.6f}")

    # Uplifts
    v0 = control_scores.get("V0_NONE", 0)
    v1 = control_scores.get("V1_INV_PI", best["score"])
    v2 = control_scores.get("V2_SMOOTH", 0)
    v5 = control_scores.get("V5_SHUFFLED", 0)
    if v0 or v2:
        lines.append(f"Prime Uplift:    {v1 - max(v0, v2):.4f}")
    if v5:
        lines.append(f"Order Uplift:    {v1 - v5:.4f}")
        lines.append(f"Shuffle Degrad:  {v1 - v5:.4f}")
    lines.append("")

    # Null summary
    nulls = db.get_null_runs(conn)
    if nulls:
        null_scores = [n["best_score"] for n in nulls if n["best_score"] is not None]
        if null_scores:
            null_max = max(null_scores)
            null_mean = sum(null_scores) / len(null_scores)
            lines.append(f"Null Runs: {len(null_scores)}")
            lines.append(f"Null Max:  {null_max:.6f}")
            lines.append(f"Null Mean: {null_mean:.6f}")
            p_emp = (1 + sum(1 for s in null_scores if s >= best["score"])) / (1 + len(null_scores))
            lines.append(f"Empirical p: {p_emp:.4f}")
    lines.append("")

    # Validation summary
    vals = db.get_validations(conn)
    if vals:
        lines.append(f"Validations: {len(vals)}")
        for v in vals[-5:]:
            lines.append(f"  {v['validation_type']}: score={v['score']:.6f} ({v['status']})")

    # Trim to 30 lines
    for line in lines[:30]:
        print(line)


def show_best(conn, run_id=None):
    """Show detailed best result."""
    best = db.get_best(conn, run_id)
    if not best:
        print("No evaluations yet.")
        return
    print(json.dumps(best, indent=2, default=str))


def show_controls(conn, run_id=None):
    """Show control model results."""
    best = db.get_best(conn, run_id)
    if not best:
        print("No evaluations yet.")
        return

    evals = db.get_all_evaluations(conn, run_id)
    print(f"{'Model':<30} {'Score':>8} {'Pearson':>8} {'Spectral':>8} {'Gradient':>8} {'AutoCor':>8}")
    print("-" * 80)
    seen = set()
    for e in evals:
        if (abs(e["cr"] - best["cr"]) < 1e-6 and
            abs(e["ci"] - best["ci"]) < 1e-6 and
            e["model_id"] not in seen):
            seen.add(e["model_id"])
            print(f"{e['model_id']:<30} {e['score']:>8.6f} {e['pearson01']:>8.6f} "
                  f"{e['spectral01']:>8.6f} {e['gradient01']:>8.6f} {e['autocorrelation01']:>8.6f}")


def show_null(conn):
    """Show null run results."""
    nulls = db.get_null_runs(conn)
    if not nulls:
        print("No null runs yet.")
        return
    print(f"{'Type':<30} {'Seed':>6} {'Best Score':>10} {'Best CR':>10} {'Best CI':>10} {'Model':<20}")
    print("-" * 90)
    for n in nulls:
        print(f"{n['null_type']:<30} {n['seed']:>6} {n['best_score']:>10.6f} "
              f"{n['best_cr']:>10.6f} {n['best_ci']:>10.6f} {n['model_id'] or '':<20}")

    scores = [n["best_score"] for n in nulls if n["best_score"] is not None]
    if scores:
        print(f"\nNull Max:  {max(scores):.6f}")
        print(f"Null Mean: {sum(scores)/len(scores):.6f}")
        if len(scores) > 1:
            var = sum((s - sum(scores)/len(scores))**2 for s in scores) / (len(scores) - 1)
            print(f"Null Std:  {math.sqrt(var):.6f}")


def show_validations(conn):
    """Show validation results."""
    vals = db.get_validations(conn)
    if not vals:
        print("No validations yet.")
        return
    print(f"{'Type':<25} {'Target':<15} {'Resolution':<10} {'MaxIter':>8} {'Score':>8} {'Status':<10}")
    print("-" * 80)
    for v in vals:
        print(f"{v['validation_type']:<25} {v['target_id'] or '':<15} "
              f"{v['resolution'] or '':<10} {v['max_iter'] or 0:>8} "
              f"{v['score']:>8.6f} {v['status']:<10}")


def show_benchmarks(conn):
    """Show benchmark results."""
    benchmarks = db.get_benchmarks(conn)
    if not benchmarks:
        print("No benchmarks yet.")
        return
    worlds = {}
    for b in benchmarks:
        wt = b["world_type"]
        if wt not in worlds:
            worlds[wt] = {"train": [], "holdout": []}
        worlds[wt][b["split"]].append(b)

    print(f"{'World':<35} {'Train':>6} {'Holdout':>8} {'Label':<15}")
    print("-" * 70)
    for wt in sorted(worlds.keys()):
        n_train = len(worlds[wt]["train"])
        n_holdout = len(worlds[wt]["holdout"])
        label = ""
        if n_train > 0:
            try:
                label = json.loads(worlds[wt]["train"][0]["feature_json"]).get("label", "")
            except Exception:
                pass
        print(f"{wt:<35} {n_train:>6} {n_holdout:>8} {label:<15}")


def export_csv(conn, table, path):
    """Export a table to CSV."""
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return
    cols = rows[0].keys()
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for row in rows:
            vals = []
            for c in cols:
                v = row[c]
                if v is None:
                    vals.append("")
                elif isinstance(v, str) and "," in v:
                    vals.append(f'"{v}"')
                else:
                    vals.append(str(v))
            f.write(",".join(vals) + "\n")


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analysis.py [summary|best|controls|null|validations|benchmarks]")
        sys.exit(1)

    cmd = sys.argv[1]
    conn = db.get_connection()

    if cmd == "summary":
        summary(conn)
    elif cmd == "best":
        show_best(conn)
    elif cmd == "controls":
        show_controls(conn)
    elif cmd == "null":
        show_null(conn)
    elif cmd == "validations":
        show_validations(conn)
    elif cmd == "benchmarks":
        show_benchmarks(conn)
    else:
        print(f"Unknown command: {cmd}")


# V2 analysis is deliberately separate from the preserved V1 CLI above.
from functools import lru_cache


def _v2_integer(value, name, minimum, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, int) or
            value < minimum or (maximum is not None and value > maximum)):
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _v2_finite(value, name):
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _v2_shape(width, height, minimum=1):
    _v2_integer(width, "width", minimum, 512)
    _v2_integer(height, "height", minimum, 512)


def _v2_field(values, width, height):
    _v2_shape(width, height)
    result = [_v2_finite(value, "field/coefficient") for value in values]
    if len(result) != width * height:
        raise ValueError("flat field/coefficient length must equal width * height")
    return result


def target_field(target_id, width=60, height=30, kernel=None):
    """Read the C target generator through V2Kernel; never duplicate formulas.

    Dimensions are 2..512. kernel may be a V2Kernel-compatible object or an
    executable path. The default is kernel_v2[.exe] beside this module.
    """
    _v2_shape(width, height, minimum=2)
    if not isinstance(target_id, str) or not target_id:
        raise ValueError("target_id must be a nonempty C target identifier")
    if kernel is None or isinstance(kernel, (str, bytes, os.PathLike)):
        from controller import V2Kernel
        path = kernel if kernel is not None else os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "kernel_v2.exe" if os.name == "nt" else "kernel_v2")
        kernel = V2Kernel(path)
    return _v2_field(kernel.target_field(target_id, width, height), width, height)


@lru_cache(maxsize=8)
def _v2_cosine_factors(size):
    """Cached orthonormal DCT-II matrix and its transpose, not a 2-D matrix."""
    forward = tuple(tuple(
        math.sqrt((1.0 if frequency == 0 else 2.0) / size) *
        math.cos(math.pi * (position + 0.5) * frequency / size)
        for position in range(size)) for frequency in range(size))
    return forward, tuple(zip(*forward))


def _v2_separable(values, width, height, inverse=False):
    horizontal = _v2_cosine_factors(width)[int(inverse)]
    vertical = _v2_cosine_factors(height)[int(inverse)]
    rows = [values[y * width:(y + 1) * width] for y in range(height)]
    intermediate = [[math.fsum(a * b for a, b in zip(row, basis))
                     for basis in horizontal] for row in rows]
    columns = list(zip(*intermediate))
    return [math.fsum(a * b for a, b in zip(column, basis))
            for basis in vertical for column in columns]


def dct2(field, width, height):
    """Orthonormal separable DCT-II, flat order v*width+u, dimensions 1..512.

    Time O(width*height*(width+height)); working storage O(width*height),
    plus bounded cached 1-D matrices. Intended for validation, not search.
    """
    return _v2_separable(_v2_field(field, width, height), width, height)


def idct2(coeff, width, height):
    """Inverse of dct2, returning a flat y*width+x field without clipping."""
    return _v2_separable(_v2_field(coeff, width, height), width, height, True)


def spectral_surrogate(field, width, height, seed):
    """SplitMix64 sign flips of every non-DC coefficient; no renormalization."""
    from controller import SplitMix64
    _v2_integer(seed, "seed", 0, (1 << 64) - 1)
    coeff = dct2(field, width, height)
    rng = SplitMix64(seed)
    for index in range(1, len(coeff)):
        if rng.next_u64() & 1:
            coeff[index] = -coeff[index]
    return idct2(coeff, width, height)


def spectral_summary(field, width, height):
    """Population moments and absolute non-DC energies, not search scores.

    Dominant frequencies exclude DC; ties use row-major coefficient order.
    Concentration is the top-ten non-DC energy / all non-DC energy.
    """
    values = _v2_field(field, width, height)
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
    coeff = dct2(values, width, height)
    energies = [value * value for value in coeff]
    # An exactly constant field has no non-DC energy, despite cosine roundoff.
    if min(values) == max(values):
        energies[1:] = [0.0] * (len(values) - 1)
    indices = sorted(range(1, len(coeff)), key=lambda i: (-energies[i], i))[:10]
    low = math.fsum(energies[i] for i in range(1, len(coeff))
                    if i % width < 8 and i // width < 8)
    high = math.fsum(energies[i] for i in range(1, len(coeff))
                     if i % width >= 8 or i // width >= 8)
    total = math.fsum(energies[1:])
    return {
        "mean": mean, "variance": variance,
        "dominant_frequencies": [
            {"u": i % width, "v": i // width, "energy": energies[i]}
            for i in indices],
        "low_frequency_energy": low, "high_frequency_energy": high,
        "total_non_dc_energy": total,
        "dct_energy_concentration": (
            math.fsum(energies[i] for i in indices) / total if total else 0.0),
    }


def null_statistics(observed, null_maxima):
    """Descriptive search-null summary; inclusive exceedances, sample std.

    Percentile is 100 * fraction strictly below observed (ties exceed).
    Fair search budgets/models/domains must be checked by the caller. This
    empirical_search_null is not a calibrated physical-simulation p-value.
    """
    observed = _v2_finite(observed, "observed")
    maxima = [_v2_finite(value, "null maximum") for value in null_maxima]
    n = len(maxima)
    result = {
        "status": "OK" if n else "UNRESOLVED", "observed": observed,
        "n": n, "null_maxima": maxima, "std_ddof": 1,
        "null_mean": None, "null_std": None, "null_median": None,
        "null_max": None, "observed_minus_null_mean": None,
        "observed_minus_null_median": None, "observed_minus_null_max": None,
        "differences": [observed - value for value in maxima],
        "percentile": None, "percentile_convention": "100 * count(null < observed) / n",
        "exceedances": None, "empirical_search_null": None,
        "minimum_attainable": 1.0 / (1 + n) if n else None,
        "interpretation": "Descriptive search-aware exceedance estimate, not a calibrated physical p-value; fairness is not verified here.",
    }
    if not n:
        return result
    mean = math.fsum(maxima) / n
    ordered = sorted(maxima)
    median = (ordered[(n - 1) // 2] + ordered[n // 2]) / 2
    exceedances = sum(value >= observed for value in maxima)
    result.update({
        "null_mean": mean,
        "null_std": math.sqrt(math.fsum((x - mean) ** 2 for x in maxima) / (n - 1)) if n > 1 else None,
        "null_median": median, "null_max": max(maxima),
        "observed_minus_null_mean": observed - mean,
        "observed_minus_null_median": observed - median,
        "observed_minus_null_max": observed - max(maxima),
        "percentile": 100.0 * (n - exceedances) / n,
        "exceedances": exceedances,
        "empirical_search_null": (1 + exceedances) / (1 + n),
    })
    return result


def _v2_trace_rows(trace, require_prime):
    rows = {}
    for row in trace:
        try:
            iteration = _v2_integer(row["iter1based"], "iter1based", 1, 20000)
            active = _v2_finite(row["active_frac"], "active_frac")
            if not 0 <= active <= 1:
                raise ValueError("active_frac must lie in [0, 1]")
            if iteration in rows:
                raise ValueError("duplicate trace iteration")
            prime = row["prime"] if require_prime else row.get("prime", 0)
            if not isinstance(prime, (int, bool)) or prime not in (0, 1):
                raise ValueError("prime must be an integer indicator 0 or 1")
            # Inactive summaries may be null/NaN placeholders: never observe them.
            mean = _v2_finite(row["mean_abs_z"], "mean_abs_z") if active else None
            std = _v2_finite(row.get("std_abs_z", 0.0), "std_abs_z") if active else None
            if active and (mean < 0 or std < 0):
                raise ValueError("magnitude moments must be nonnegative")
            rows[iteration] = (active, mean, std, int(prime))
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("trace rows require iter1based, active_frac, mean_abs_z and forced prime") from exc
    return rows


def _v2_randbelow(rng, bound):
    limit = (1 << 64) - (1 << 64) % bound
    while True:
        value = rng.next_u64()
        if value < limit:
            return value % bound


def _v2_quantile(ordered, probability):
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def temporal_analysis(forced_trace, baseline_trace, seed=424242, permutations=1000):
    """Lag-one, one-to-one, baseline-adjusted matched temporal contrasts.

    Inputs are iterables of trace row mappings, keyed by iter1based (1..20000).
    Matching is chronological greedy, nearest unused control within +/-10,
    lower-iteration tie break, same floor(forced response active_frac*10).
    Detrending subtracts the centered 21-iteration mean of available, active,
    nonzero-magnitude baseline-adjusted samples; no gap filling or padding.
    Both response and predecessor must be observable in both traces. Exact
    zero contrasts are retained, avoiding outcome-dependent pair selection.
    Bootstrap uses 1000 resamples, independent of the positive permutation
    count. No aggregate scientific status or physical interpretation is made.
    """
    from controller import SplitMix64
    _v2_integer(seed, "seed", 0, (1 << 64) - 1)
    _v2_integer(permutations, "permutations", 1)
    forced = _v2_trace_rows(forced_trace, True)
    baseline = _v2_trace_rows(baseline_trace, False)
    bootstrap_seed = (seed + 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
    result = {
        "status": "INSUFFICIENT_ACTIVE_DATA", "reason": None,
        "pair_count": 0, "pairs": [], "mean_difference": None,
        "std_difference": None, "effect_size": None, "std_ddof": 1,
        "bootstrap_ci95": None, "permutation_p_two_sided": None,
        "permutation_exceedances": None, "permutations": permutations,
        "bootstrap_resamples": 1000, "lag": 1, "detrend_window": 21,
        "matching_radius": 10, "active_fraction_bin_width": 0.1,
        "minimum_pairs": 20, "prng": "SplitMix64",
        "seeds": {"sign_permutation": seed, "bootstrap": bootstrap_seed},
        "rng_final_states": None,
        "excluded": {"missing_baseline": 0, "extinct": 0,
                     "zero_magnitude": 0, "unobservable_predecessor": 0},
        "assumptions": [
            "Responses are forced mean_abs_z minus baseline mean_abs_z at the same iteration; survivors may be different pixel populations.",
            "Prime labels come from the preceding forced iteration, including prime 2 even if its driver amplitude is zero.",
            "Both traces must remain active at response and predecessor; extinct and zero-magnitude degenerate samples are not zero-response observations.",
            "Detrending uses only observable samples in a centered 21-iteration window, truncated at endpoints and gaps, without interpolation.",
            "Matching is chronological greedy, nearest unused after-nonprime within +/-10, earlier tie break, same forced-response active-fraction bin.",
            "Sign permutations assume exchangeable within-pair labels (symmetric paired differences) under the null; deterministic arithmetic labels do not establish this.",
            "The percentile bootstrap assumes independent representative pairs; serial dependence and overlapping detrending windows can invalidate coverage and permutation calibration.",
            "Matching does not remove all confounding or selection effects; inference is exploratory, unadjusted for multiplicity, and is not a causal or physical-simulation claim.",
        ],
    }
    adjusted = {}
    for iteration, (active, mean, std, prime) in forced.items():
        other = baseline.get(iteration)
        if other is None:
            result["excluded"]["missing_baseline"] += 1
        elif not active or not other[0]:
            result["excluded"]["extinct"] += 1
        elif (mean == 0 and std == 0) or (other[1] == 0 and other[2] == 0):
            result["excluded"]["zero_magnitude"] += 1
        else:
            adjusted[iteration] = mean - other[1]
    detrended = {}
    for iteration, value in adjusted.items():
        neighbors = [adjusted[k] for k in range(iteration - 10, iteration + 11)
                     if k in adjusted]
        detrended[iteration] = value - math.fsum(neighbors) / len(neighbors)
    responses = {}
    for iteration in sorted(adjusted):
        if iteration - 1 not in adjusted:
            result["excluded"]["unobservable_predecessor"] += 1
            continue
        responses[iteration] = (forced[iteration - 1][3],
                                math.floor(forced[iteration][0] * 10))
    used_controls = set()
    differences = []
    for iteration, (prime, active_bin) in responses.items():
        if not prime:
            continue
        controls = [k for k in range(iteration - 10, iteration + 11)
                    if k in responses and responses[k] == (0, active_bin)
                    and k not in used_controls]
        if not controls:
            continue
        control = min(controls, key=lambda k: (abs(k - iteration), k))
        used_controls.add(control)
        difference = detrended[iteration] - detrended[control]
        differences.append(difference)
        result["pairs"].append({
            "prime_iteration": iteration - 1, "after_prime_iteration": iteration,
            "nonprime_iteration": control - 1, "after_nonprime_iteration": control,
            "active_fraction_bin": active_bin, "difference": difference,
        })
    n = len(differences)
    result["pair_count"] = n
    result["usable_response_count"] = len(responses)
    result["eligible_after_prime_count"] = sum(prime for prime, _ in responses.values())
    if n:
        mean = math.fsum(differences) / n
        std = math.sqrt(math.fsum((x - mean) ** 2 for x in differences) / (n - 1)) if n > 1 else None
        result.update(mean_difference=mean, std_difference=std,
                      effect_size=mean / std if std else None)
    if n < 20:
        result["reason"] = "Fewer than 20 usable one-to-one active pairs; no signal or null conclusion."
        return result
    if not any(differences):
        result["status"] = "DEGENERATE_RESPONSE"
        result["reason"] = "All paired baseline-adjusted contrasts are zero; no inferential test."
        return result
    bootstrap_rng = SplitMix64(bootstrap_seed)
    bootstrap = sorted(math.fsum(differences[_v2_randbelow(bootstrap_rng, n)]
                                for _ in range(n)) / n for _ in range(1000))
    sign_rng = SplitMix64(seed)
    observed = abs(math.fsum(differences))
    exceedances = 0
    for _ in range(permutations):
        statistic = abs(math.fsum(-x if sign_rng.next_u64() & 1 else x
                                  for x in differences))
        exceedances += statistic >= observed
    result.update({
        "status": "OK", "reason": "Matched exploratory test; see exchangeability and dependence assumptions.",
        "bootstrap_ci95": [_v2_quantile(bootstrap, 0.025), _v2_quantile(bootstrap, 0.975)],
        "permutation_exceedances": exceedances,
        "permutation_p_two_sided": (1 + exceedances) / (1 + permutations),
        "rng_final_states": {"bootstrap": bootstrap_rng.state,
                             "sign_permutation": sign_rng.state},
    })
    return result
