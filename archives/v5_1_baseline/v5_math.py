"""V5 Math: Fingerprint extraction and detector mathematics."""
import math
import hashlib
import struct
from typing import List, Dict, Tuple, Optional

# ============================================================================
# SPLITMIX64 PRNG (reused from V4)
# ============================================================================

class SplitMix64:
    """Deterministic PRNG for reproducibility."""
    
    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFFFFFFFFFF
    
    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF
    
    def next_double(self) -> float:
        return (self.next_u64() >> 11) / (1 << 53)
    
    def next_int(self, lo: int, hi: int) -> int:
        return lo + (self.next_u64() % (hi - lo))


# ============================================================================
# SPATIAL FINGERPRINTS
# ============================================================================

def compute_entropy(field: List[float], nbins: int = 32) -> float:
    """Shannon entropy of field histogram."""
    if not field:
        return 0.0
    fmin, fmax = min(field), max(field)
    if fmax == fmin:
        return 0.0
    bins = [0] * nbins
    for v in field:
        idx = min(int((v - fmin) / (fmax - fmin) * nbins), nbins - 1)
        bins[idx] += 1
    n = len(field)
    entropy = 0.0
    for c in bins:
        if c > 0:
            p = c / n
            entropy -= p * math.log2(p)
    return entropy


def compute_histogram_moments(field: List[float]) -> Dict[str, float]:
    """Mean, variance, skewness, kurtosis of field."""
    n = len(field)
    if n == 0:
        return {"mean": 0, "var": 0, "skew": 0, "kurt": 0}
    mean = sum(field) / n
    var = sum((x - mean) ** 2 for x in field) / n if n > 1 else 0
    std = math.sqrt(var) if var > 0 else 0
    skew = sum((x - mean) ** 3 for x in field) / (n * std ** 3) if std > 0 else 0
    kurt = sum((x - mean) ** 4 for x in field) / (n * var ** 2) - 3 if var > 0 else 0
    return {"mean": mean, "var": var, "skew": skew, "kurt": kurt}


def compute_autocorrelation_2d(field: List[float], width: int, height: int,
                                max_lag: int = 5) -> List[float]:
    """2D spatial autocorrelation at multiple lags."""
    acf = []
    mean = sum(field) / len(field) if field else 0
    var = sum((x - mean) ** 2 for x in field) / len(field) if field else 0
    if var == 0:
        return [0.0] * max_lag
    for lag in range(1, max_lag + 1):
        s = 0.0
        count = 0
        for y in range(height):
            for x in range(width):
                x2 = x + lag
                if x2 < width:
                    idx1 = y * width + x
                    idx2 = y * width + x2
                    s += (field[idx1] - mean) * (field[idx2] - mean)
                    count += 1
        acf.append(s / (count * var) if count > 0 else 0)
    return acf


def compute_gradient_stats(field: List[float], width: int, height: int) -> Dict[str, float]:
    """Gradient magnitude statistics."""
    gx, gy = [], []
    for y in range(height - 1):
        for x in range(width - 1):
            idx = y * width + x
            gx.append(field[idx + 1] - field[idx])
            gy.append(field[idx + width] - field[idx])
    if not gx:
        return {"grad_mean": 0, "grad_std": 0}
    all_g = [abs(v) for v in gx + gy]
    mean_g = sum(all_g) / len(all_g)
    var_g = sum((v - mean_g) ** 2 for v in all_g) / len(all_g)
    return {"grad_mean": mean_g, "grad_std": math.sqrt(var_g)}


def compute_laplacian_stats(field: List[float], width: int, height: int) -> Dict[str, float]:
    """Laplacian (second derivative) statistics."""
    lap = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            idx = y * width + x
            center = field[idx]
            neighbors = (field[idx - 1] + field[idx + 1] +
                        field[idx - width] + field[idx + width])
            lap.append(neighbors - 4 * center)
    if not lap:
        return {"lap_mean": 0, "lap_std": 0}
    mean_l = sum(lap) / len(lap)
    var_l = sum((v - mean_l) ** 2 for v in lap) / len(lap)
    return {"lap_mean": mean_l, "lap_std": math.sqrt(var_l)}


def compute_anisotropy(field: List[float], width: int, height: int) -> float:
    """Directional anisotropy: variance ratio of horizontal vs vertical gradients."""
    gx, gy = [], []
    for y in range(height - 1):
        for x in range(width - 1):
            idx = y * width + x
            gx.append(field[idx + 1] - field[idx])
            gy.append(field[idx + width] - field[idx])
    if not gx or not gy:
        return 0.0
    var_x = sum(v ** 2 for v in gx) / len(gx)
    var_y = sum(v ** 2 for v in gy) / len(gy)
    if var_x + var_y == 0:
        return 0.0
    return abs(var_x - var_y) / (var_x + var_y)


def compute_edge_density(field: List[float], width: int, height: int,
                         threshold: float = 0.1) -> float:
    """Fraction of pixels with large gradient magnitude."""
    edges = 0
    total = 0
    for y in range(height - 1):
        for x in range(width - 1):
            idx = y * width + x
            gx = abs(field[idx + 1] - field[idx])
            gy = abs(field[idx + width] - field[idx])
            if gx + gy > threshold:
                edges += 1
            total += 1
    return edges / total if total > 0 else 0.0


def compute_local_variance(field: List[float], width: int, height: int,
                           window: int = 3) -> float:
    """Mean local variance in sliding windows."""
    variances = []
    for y in range(height - window + 1):
        for x in range(width - window + 1):
            block = []
            for dy in range(window):
                for dx in range(window):
                    block.append(field[(y + dy) * width + (x + dx)])
            mean_b = sum(block) / len(block)
            var_b = sum((v - mean_b) ** 2 for v in block) / len(block)
            variances.append(var_b)
    return sum(variances) / len(variances) if variances else 0.0


def compute_connected_component_stats(field: List[float], width: int, height: int,
                                       threshold: float = 0.5) -> Dict[str, float]:
    """Statistics of connected components above threshold."""
    visited = [False] * len(field)
    components = []
    
    def flood_fill(start_idx: int) -> int:
        stack = [start_idx]
        size = 0
        while stack:
            idx = stack.pop()
            if visited[idx]:
                continue
            visited[idx] = True
            size += 1
            y, x = divmod(idx, width)
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    nidx = ny * width + nx
                    if not visited[nidx] and field[nidx] >= threshold:
                        stack.append(nidx)
        return size
    
    for i, v in enumerate(field):
        if v >= threshold and not visited[i]:
            components.append(flood_fill(i))
    
    if not components:
        return {"n_components": 0, "mean_size": 0, "max_size": 0}
    return {
        "n_components": len(components),
        "mean_size": sum(components) / len(components),
        "max_size": max(components)
    }


# ============================================================================
# SPECTRAL FINGERPRINTS
# ============================================================================

def compute_dct_1d(x: List[float]) -> List[float]:
    """Type-II DCT (naive implementation)."""
    N = len(x)
    if N == 0:
        return []
    result = []
    for k in range(N):
        s = 0.0
        for n in range(N):
            s += x[n] * math.cos(math.pi * k * (2 * n + 1) / (2 * N))
        result.append(s)
    return result


def compute_dct_energy(field: List[float], width: int, height: int) -> Dict[str, float]:
    """DCT energy distribution: low/mid/high frequency bands."""
    # Apply DCT to each row, then each column
    row_dcts = []
    for y in range(height):
        row = [field[y * width + x] for x in range(width)]
        row_dcts.append(compute_dct_1d(row))
    
    # Compute energy per frequency band
    total_energy = 0
    low_energy = 0
    mid_energy = 0
    high_energy = 0
    N = width
    low_cutoff = N // 4
    mid_cutoff = N // 2
    
    for row_dct in row_dcts:
        for k, v in enumerate(row_dct):
            e = v * v
            total_energy += e
            if k < low_cutoff:
                low_energy += e
            elif k < mid_cutoff:
                mid_energy += e
            else:
                high_energy += e
    
    if total_energy == 0:
        return {"dct_low": 0, "dct_mid": 0, "dct_high": 0, "high_low_ratio": 0}
    
    return {
        "dct_low": low_energy / total_energy,
        "dct_mid": mid_energy / total_energy,
        "dct_high": high_energy / total_energy,
        "high_low_ratio": high_energy / low_energy if low_energy > 0 else 0
    }


def compute_spectral_sparsity(dct_coeffs: List[float], threshold: float = 0.01) -> float:
    """Fraction of DCT coefficients above threshold."""
    if not dct_coeffs:
        return 0.0
    max_c = max(abs(c) for c in dct_coeffs) if dct_coeffs else 0
    if max_c == 0:
        return 0.0
    significant = sum(1 for c in dct_coeffs if abs(c) / max_c > threshold)
    return significant / len(dct_coeffs)


def compute_spectral_slope(dct_coeffs: List[float]) -> float:
    """Spectral slope: log-energy vs log-frequency."""
    if len(dct_coeffs) < 2:
        return 0.0
    log_freqs = []
    log_energies = []
    for k, c in enumerate(dct_coeffs[1:], 1):  # Skip DC
        if abs(c) > 1e-10:
            log_freqs.append(math.log(k))
            log_energies.append(math.log(c * c))
    if len(log_freqs) < 2:
        return 0.0
    n = len(log_freqs)
    mean_f = sum(log_freqs) / n
    mean_e = sum(log_energies) / n
    cov = sum((f - mean_f) * (e - mean_e) for f, e in zip(log_freqs, log_energies)) / n
    var_f = sum((f - mean_f) ** 2 for f in log_freqs) / n
    return cov / var_f if var_f > 0 else 0.0


# ============================================================================
# COMPUTATIONAL FINGERPRINTS
# ============================================================================

def compute_quantization_level(field: List[float]) -> int:
    """Estimate quantization level by counting unique values."""
    unique = len(set(field))
    if unique <= 16:
        return 4
    elif unique <= 256:
        return 8
    elif unique <= 65536:
        return 16
    return 32


def compute_repeated_value_fraction(field: List[float]) -> float:
    """Fraction of values that are exact duplicates."""
    if not field:
        return 0.0
    counts = {}
    for v in field:
        counts[v] = counts.get(v, 0) + 1
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / len(field)


def compute_recurrence_rate(field: List[float], precision: int = 8) -> Dict[str, float]:
    """Exact and near recurrence rates after quantization."""
    if len(field) < 2:
        return {"exact": 0, "near": 0, "entropy": 0}
    
    # Quantize to controlled precision
    scale = 2 ** precision
    quantized = [int(v * scale) for v in field]
    
    # Exact recurrence
    seen = {}
    exact_recurrences = 0
    for v in quantized:
        if v in seen:
            exact_recurrences += 1
        seen[v] = seen.get(v, 0) + 1
    
    # Near recurrence (within ±1)
    near_recurrences = 0
    for i, v in enumerate(quantized):
        for j in range(i + 1, len(quantized)):
            if abs(quantized[j] - v) <= 1:
                near_recurrences += 1
                break
    
    # Recurrence entropy
    counts = list(seen.values())
    total = sum(counts)
    entropy = -sum((c / total) * math.log2(c / total) for c in counts if c > 0) if total > 0 else 0
    
    return {
        "exact": exact_recurrences / len(field),
        "near": near_recurrences / len(field),
        "entropy": entropy
    }


def compute_compression_ratio(field: List[float]) -> float:
    """Simple compression ratio estimate using run-length encoding."""
    if not field:
        return 1.0
    
    # Quantize for compression
    quantized = [int(v * 256) & 0xFF for v in field]
    
    # RLE
    runs = 1
    for i in range(1, len(quantized)):
        if quantized[i] != quantized[i - 1]:
            runs += 1
    
    original_bits = len(quantized) * 8
    compressed_bits = runs * 16  # (value, count) pairs
    return compressed_bits / original_bits if original_bits > 0 else 1.0


def compute_run_length_stats(field: List[float]) -> Dict[str, float]:
    """Run-length statistics."""
    if not field:
        return {"mean": 0, "std": 0}
    
    quantized = [int(v * 256) & 0xFF for v in field]
    runs = []
    current_run = 1
    
    for i in range(1, len(quantized)):
        if quantized[i] == quantized[i - 1]:
            current_run += 1
        else:
            runs.append(current_run)
            current_run = 1
    runs.append(current_run)
    
    if not runs:
        return {"mean": 0, "std": 0}
    
    mean_r = sum(runs) / len(runs)
    var_r = sum((r - mean_r) ** 2 for r in runs) / len(runs)
    return {"mean": mean_r, "std": math.sqrt(var_r)}


def compute_aliasing_score(field: List[float], width: int, height: int) -> float:
    """Detect aliasing artifacts by checking for high-frequency energy."""
    dct_energy = compute_dct_energy(field, width, height)
    return dct_energy.get("high_low_ratio", 0)


def compute_sampling_artifact_score(field: List[float], width: int, height: int) -> float:
    """Detect regular sampling artifacts."""
    # Check for periodic patterns in DCT
    row_dcts = []
    for y in range(height):
        row = [field[y * width + x] for x in range(width)]
        row_dcts.append(compute_dct_1d(row))
    
    # Look for peaks in average spectrum
    avg_dct = [0] * width
    for row_dct in row_dcts:
        for k, v in enumerate(row_dct):
            avg_dct[k] += abs(v)
    
    # Normalize
    max_v = max(avg_dct[1:]) if len(avg_dct) > 1 else 1
    if max_v == 0:
        return 0.0
    
    # Count peaks
    peaks = sum(1 for k in range(1, width - 1)
                if avg_dct[k] > avg_dct[k - 1] and avg_dct[k] > avg_dct[k + 1]
                and avg_dct[k] / max_v > 0.1)
    return peaks / width


# ============================================================================
# PRECISION FINGERPRINTS
# ============================================================================

def compute_precision_sensitivity(field_f64: List[float],
                                   field_f32: Optional[List[float]] = None,
                                   field_f16: Optional[List[float]] = None) -> Dict[str, float]:
    """Sensitivity to precision reduction."""
    if field_f32 is None:
        # Simulate float32 by rounding to ~7 decimal digits
        field_f32 = [float(struct.unpack('f', struct.pack('f', v))[0]) for v in field_f64]
    
    diff_f32 = sum(abs(a - b) for a, b in zip(field_f64, field_f32)) / len(field_f64)
    
    result = {"float64_float32_diff": diff_f32}
    
    if field_f16 is not None:
        diff_f16 = sum(abs(a - b) for a, b in zip(field_f64, field_f16)) / len(field_f64)
        result["float64_float16_diff"] = diff_f16
    else:
        result["float64_float16_diff"] = 0.0
    
    result["precision_sensitivity"] = diff_f32
    return result


# ============================================================================
# FULL FINGERPRINT EXTRACTION
# ============================================================================

def extract_full_fingerprint(field: List[float], width: int, height: int,
                             field_f32: Optional[List[float]] = None) -> Dict[str, float]:
    """Extract complete fingerprint vector."""
    fp = {}
    
    # Spatial
    fp["entropy"] = compute_entropy(field)
    moments = compute_histogram_moments(field)
    fp.update({f"moment_{k}": v for k, v in moments.items()})
    
    acf = compute_autocorrelation_2d(field, width, height)
    for i, v in enumerate(acf):
        fp[f"acf_lag{i+1}"] = v
    
    grad = compute_gradient_stats(field, width, height)
    fp.update(grad)
    
    lap = compute_laplacian_stats(field, width, height)
    fp.update(lap)
    
    fp["anisotropy"] = compute_anisotropy(field, width, height)
    fp["edge_density"] = compute_edge_density(field, width, height)
    fp["local_variance"] = compute_local_variance(field, width, height)
    
    cc = compute_connected_component_stats(field, width, height)
    fp.update({f"cc_{k}": v for k, v in cc.items()})
    
    # Spectral
    dct_e = compute_dct_energy(field, width, height)
    fp.update(dct_e)
    
    row_dct = compute_dct_1d(field[:width]) if width > 0 else []
    fp["spectral_sparsity"] = compute_spectral_sparsity(row_dct)
    fp["spectral_slope"] = compute_spectral_slope(row_dct)
    
    # Computational
    fp["quantization_level"] = compute_quantization_level(field)
    fp["repeated_value_fraction"] = compute_repeated_value_fraction(field)
    
    rec = compute_recurrence_rate(field)
    fp.update({f"recurrence_{k}": v for k, v in rec.items()})
    
    fp["compression_ratio"] = compute_compression_ratio(field)
    
    rl = compute_run_length_stats(field)
    fp.update({f"run_length_{k}": v for k, v in rl.items()})
    
    fp["aliasing_score"] = compute_aliasing_score(field, width, height)
    fp["sampling_artifact_score"] = compute_sampling_artifact_score(field, width, height)
    
    # Precision
    prec = compute_precision_sensitivity(field, field_f32)
    fp.update(prec)
    
    return fp
