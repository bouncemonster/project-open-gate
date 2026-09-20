"""
PROOF OF SIMULATION — Synthetic World Generator (WorldForge)
Creates artificial worlds with known generators for benchmark validation.
"""
import math
import json
import os

WIDTH = 60
HEIGHT = 30
NCELLS = WIDTH * HEIGHT

# SplitMix64 PRNG
class SplitMix64:
    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF

    def uniform(self, lo=0.0, hi=1.0):
        v = self.next_u64() >> 11
        return lo + (hi - lo) * (v / (1 << 53))

    def gauss(self, mu=0.0, sigma=1.0):
        u1 = self.uniform(1e-10, 1.0)
        u2 = self.uniform(0.0, 1.0)
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return mu + sigma * z


def _is_prime(n):
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def _pi_count(k):
    """Count primes <= k with convention pi(0)=1, pi(1)=1."""
    if k <= 1:
        return 1
    c = 1  # count 1 as per convention
    for n in range(2, k + 1):
        if _is_prime(n):
            c += 1
    return c


# ================================================================
# World generators
# ================================================================

def world_analytic(seed):
    """Smooth analytical field without grid algorithm."""
    rng = SplitMix64(seed)
    ax = rng.uniform(0.5, 3.0)
    ay = rng.uniform(0.5, 3.0)
    px = rng.uniform(0, math.pi)
    py = rng.uniform(0, math.pi)
    field = []
    for row in range(HEIGHT):
        for col in range(WIDTH):
            u = col / (WIDTH - 1)
            v = row / (HEIGHT - 1)
            val = 0.5 + 0.3 * math.sin(ax * math.pi * u + px) * math.cos(ay * math.pi * v + py)
            field.append(max(0.0, min(1.0, val)))
    return field


def world_random_iid(seed):
    """Independent random values."""
    rng = SplitMix64(seed)
    return [rng.uniform(0, 1) for _ in range(NCELLS)]


def world_gaussian(seed):
    """Correlated random field with preset correlation length."""
    rng = SplitMix64(seed)
    corr_len = 5.0
    # Generate white noise first
    white = [rng.gauss() for _ in range(NCELLS)]
    # Apply Gaussian blur approximation
    field = []
    sigma = corr_len
    r = int(math.ceil(2 * sigma))
    kernel = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            kernel.append((dx, dy, math.exp(-(dx*dx + dy*dy) / (2 * sigma * sigma))))
    ksum = sum(w for _, _, w in kernel)
    for row in range(HEIGHT):
        for col in range(WIDTH):
            val = 0
            for dx, dy, w in kernel:
                nr, nc = row + dy, col + dx
                nr = max(0, min(HEIGHT - 1, nr))
                nc = max(0, min(WIDTH - 1, nc))
                val += white[nr * WIDTH + nc] * w
            field.append(val / ksum)
    # Normalize to [0, 1]
    fmin, fmax = min(field), max(field)
    if fmax - fmin < 1e-15:
        return [0.5] * NCELLS
    return [(v - fmin) / (fmax - fmin) for v in field]


def world_fractal_analytic(seed):
    """Smooth fractal-like field via analytical formula (no cellular automaton)."""
    rng = SplitMix64(seed)
    n_octaves = 4
    freqs = [rng.uniform(1, 4) for _ in range(n_octaves)]
    phases = [rng.uniform(0, 2 * math.pi) for _ in range(n_octaves)]
    amps = [1.0 / (i + 1) for i in range(n_octaves)]
    field = []
    for row in range(HEIGHT):
        for col in range(WIDTH):
            u = col / (WIDTH - 1)
            v = row / (HEIGHT - 1)
            val = 0
            for i in range(n_octaves):
                val += amps[i] * math.sin(freqs[i] * math.pi * u + phases[i]) * \
                               math.cos(freqs[i] * math.pi * v + phases[i])
            field.append(val)
    fmin, fmax = min(field), max(field)
    if fmax - fmin < 1e-15:
        return [0.5] * NCELLS
    return [(v - fmin) / (fmax - fmin) for v in field]


def world_lattice(seed):
    """Deterministic cellular system with local rules."""
    rng = SplitMix64(seed)
    # Initialize grid
    grid = [[rng.uniform(0, 1) for _ in range(WIDTH)] for _ in range(HEIGHT)]
    # Apply local averaging rules for several iterations
    for _ in range(10):
        new_grid = [[0.0] * WIDTH for _ in range(HEIGHT)]
        for r in range(HEIGHT):
            for c in range(WIDTH):
                s = grid[r][c]
                n = 1
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < HEIGHT and 0 <= nc < WIDTH:
                        s += grid[nr][nc]
                        n += 1
                new_grid[r][c] = s / n
        grid = new_grid
    field = []
    for r in range(HEIGHT):
        for c in range(WIDTH):
            field.append(grid[r][c])
    return field


def world_quantized(seed):
    """Smooth field after bit quantization."""
    base = world_analytic(seed)
    bits = 4  # 4-bit quantization
    levels = 2 ** bits
    return [math.floor(v * levels) / (levels - 1) for v in base]


def world_prng(seed):
    """Field created by deterministic PRNG."""
    rng = SplitMix64(seed)
    # Generate with some spatial correlation
    field = []
    prev = rng.uniform(0, 1)
    for _ in range(NCELLS):
        val = 0.7 * prev + 0.3 * rng.uniform(0, 1)
        field.append(max(0, min(1, val)))
        prev = val
    return field


def world_hash(seed):
    """Field generated via deterministic coordinate hash."""
    field = []
    for row in range(HEIGHT):
        for col in range(WIDTH):
            h = seed ^ (col * 374761393 + row * 668265263)
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
            h = (h ^ (h >> 16)) & 0xFFFFFFFF
            field.append((h & 0xFFFF) / 65535.0)
    return field


def world_prime(seed):
    """Field built on prime indicator / pi(k) / prime gaps."""
    rng = SplitMix64(seed)
    field = []
    # Use prime gaps to create spatial structure
    primes = [n for n in range(2, 200) if _is_prime(n)]
    for row in range(HEIGHT):
        for col in range(WIDTH):
            idx = row * WIDTH + col
            k = idx + 1
            pi_k = _pi_count(k)
            val = 1.0 / pi_k
            field.append(val)
    # Normalize
    fmin, fmax = min(field), max(field)
    if fmax - fmin < 1e-15:
        return [0.5] * NCELLS
    return [(v - fmin) / (fmax - fmin) for v in field]


def world_smooth_highly_compressed(seed):
    """Very smooth field that compresses well — adversarial for detector."""
    rng = SplitMix64(seed)
    freq = rng.uniform(0.5, 1.5)
    field = []
    for row in range(HEIGHT):
        for col in range(WIDTH):
            u = col / (WIDTH - 1)
            v = row / (HEIGHT - 1)
            val = 0.5 + 0.4 * math.sin(freq * math.pi * u) * math.sin(freq * math.pi * v)
            field.append(max(0, min(1, val)))
    return field


def world_fractal_highly_compressed(seed):
    """Fractal-like but highly compressible — adversarial."""
    rng = SplitMix64(seed)
    freq = rng.uniform(1, 3)
    field = []
    for row in range(HEIGHT):
        for col in range(WIDTH):
            u = col / (WIDTH - 1)
            v = row / (HEIGHT - 1)
            val = 0.5 + 0.3 * math.sin(freq * math.pi * u) + 0.2 * math.cos(freq * 2 * math.pi * v)
            field.append(max(0, min(1, val)))
    return field


# World class registry
WORLD_CLASSES = {
    "WORLD_ANALYTIC": world_analytic,
    "WORLD_RANDOM_IID": world_random_iid,
    "WORLD_GAUSSIAN": world_gaussian,
    "WORLD_FRACTAL_ANALYTIC": world_fractal_analytic,
    "WORLD_LATTICE": world_lattice,
    "WORLD_QUANTIZED": world_quantized,
    "WORLD_PRNG": world_prng,
    "WORLD_HASH": world_hash,
    "WORLD_PRIME": world_prime,
    "WORLD_SMOOTH_HIGHLY_COMPRESSED": world_smooth_highly_compressed,
    "WORLD_FRACTAL_HIGHLY_COMPRESSED": world_fractal_highly_compressed,
}

# Natural-like vs computational classification
NATURAL_LIKE = ["WORLD_ANALYTIC", "WORLD_GAUSSIAN", "WORLD_FRACTAL_ANALYTIC"]
COMPUTATIONAL = ["WORLD_LATTICE", "WORLD_QUANTIZED", "WORLD_PRNG", "WORLD_HASH"]
HOLDOUT_COMPUTATIONAL = ["WORLD_PRIME"]


# ================================================================
# Feature extraction
# ================================================================

def extract_features(field):
    """Extract feature vector from a world field."""
    features = {}

    # Entropy (16 bins)
    bins = [0] * 16
    for v in field:
        b = int(v * 16)
        b = max(0, min(15, b))
        bins[b] += 1
    H = 0
    for c in bins:
        if c > 0:
            p = c / len(field)
            H -= p * math.log(p)
    features["entropy"] = H / math.log(16)

    # Compression estimate (RLE)
    runs = 1
    quantized = [int(v * 10) for v in field]
    for i in range(1, len(quantized)):
        if quantized[i] != quantized[i-1]:
            runs += 1
    features["compression"] = runs / len(field)

    # Anisotropy
    mean_f = sum(field) / len(field)
    var_f = sum((v - mean_f) ** 2 for v in field) / len(field)
    if var_f > 1e-15:
        corr_h, corr_v, corr_d = 0, 0, 0
        nh, nv, nd = 0, 0, 0
        for row in range(HEIGHT):
            for col in range(WIDTH):
                idx = row * WIDTH + col
                v0 = field[idx] - mean_f
                if col + 1 < WIDTH:
                    corr_h += v0 * (field[idx + 1] - mean_f)
                    nh += 1
                if row + 1 < HEIGHT:
                    corr_v += v0 * (field[idx + WIDTH] - mean_f)
                    nv += 1
                if col + 1 < WIDTH and row + 1 < HEIGHT:
                    corr_d += v0 * (field[idx + WIDTH + 1] - mean_f)
                    nd += 1
        if nh: corr_h /= (nh * var_f)
        if nv: corr_v /= (nv * var_f)
        if nd: corr_d /= (nd * var_f)
        max_dir = max(abs(corr_h), abs(corr_v), abs(corr_d))
        mean_dir = (abs(corr_h) + abs(corr_v) + abs(corr_d)) / 3
        features["anisotropy"] = max(0, min(1, max_dir - mean_dir))
    else:
        features["anisotropy"] = 0

    # Quantization
    levels = len(set(int(v * 100) for v in field))
    features["quantization"] = levels / min(len(field), 100)

    # Spectral sparsity (simple: count significant DCT modes)
    # Use a few low-frequency modes
    coeffs = []
    for u in range(4):
        for v in range(4):
            if u == 0 and v == 0:
                continue
            s = 0
            for row in range(HEIGHT):
                for col in range(WIDTH):
                    cu = math.cos(math.pi * u * (2 * col + 1) / (2 * WIDTH))
                    cv = math.cos(math.pi * v * (2 * row + 1) / (2 * HEIGHT))
                    s += field[row * WIDTH + col] * cu * cv
            coeffs.append(abs(s))
    threshold = max(coeffs) * 0.1 if coeffs else 0
    significant = sum(1 for c in coeffs if c > threshold)
    features["spectral_sparsity"] = significant / len(coeffs) if coeffs else 0

    # Autocorrelation (lag 1)
    if var_f > 1e-15:
        ac = 0
        n = 0
        for row in range(HEIGHT):
            for col in range(WIDTH):
                idx = row * WIDTH + col
                if col + 1 < WIDTH:
                    ac += (field[idx] - mean_f) * (field[idx + 1] - mean_f)
                    n += 1
        features["autocorrelation"] = (ac / n) / var_f if n else 0
    else:
        features["autocorrelation"] = 0

    # Recurrence (simple: fraction of cells with similar neighbors)
    threshold_r = 0.1
    rec = 0
    total_r = 0
    for row in range(HEIGHT):
        for col in range(WIDTH):
            idx = row * WIDTH + col
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc
                if 0 <= nr < HEIGHT and 0 <= nc < WIDTH:
                    nidx = nr * WIDTH + nc
                    if abs(field[idx] - field[nidx]) < threshold_r:
                        rec += 1
                    total_r += 1
    features["recurrence"] = rec / total_r if total_r else 0

    # Finite precision sensitivity (compare quantized vs original entropy)
    q8 = [math.floor(v * 256) / 255 for v in field]
    bins_q = [0] * 16
    for v in q8:
        b = int(v * 16)
        b = max(0, min(15, b))
        bins_q[b] += 1
    H_q = 0
    for c in bins_q:
        if c > 0:
            p = c / len(field)
            H_q -= p * math.log(p)
    features["finite_precision_sensitivity"] = abs(H - H_q) / math.log(16) if H > 0 else 0

    return features


def generate_benchmark(seeds_per_world=20):
    """Generate benchmark dataset for all world classes."""
    dataset = []
    for world_name, gen_func in WORLD_CLASSES.items():
        for seed in range(1, seeds_per_world + 1):
            field = gen_func(seed)
            features = extract_features(field)
            split = "train" if seed <= 10 else "holdout"
            if world_name in NATURAL_LIKE:
                label = "natural"
            elif world_name in COMPUTATIONAL or world_name in HOLDOUT_COMPUTATIONAL:
                label = "computational"
            else:
                label = "unknown"
            dataset.append({
                "world_type": world_name,
                "seed": seed,
                "split": split,
                "features": features,
                "label": label,
                "field": field
            })
    return dataset


class NearestCentroidDetector:
    """Simple nearest centroid classifier for natural vs computational."""

    def __init__(self):
        self.centroids = {}
        self.feature_names = None

    def train(self, dataset):
        """Train on labeled dataset (train split only)."""
        feature_sums = {"natural": None, "computational": None}
        feature_counts = {"natural": 0, "computational": 0}

        for item in dataset:
            if item["split"] != "train":
                continue
            label = item["label"]
            if label not in feature_sums:
                continue
            feats = item["features"]
            if self.feature_names is None:
                self.feature_names = sorted(feats.keys())
            vec = [feats[k] for k in self.feature_names]
            if feature_sums[label] is None:
                feature_sums[label] = list(vec)
            else:
                for i, v in enumerate(vec):
                    feature_sums[label][i] += v
            feature_counts[label] += 1

        for label in feature_sums:
            if feature_counts[label] > 0:
                self.centroids[label] = [
                    s / feature_counts[label] for s in feature_sums[label]
                ]

    def predict(self, features):
        """Predict label for a feature vector."""
        vec = [features[k] for k in self.feature_names]
        best_label = None
        best_dist = float("inf")
        for label, centroid in self.centroids.items():
            dist = sum((a - b) ** 2 for a, b in zip(vec, centroid))
            if dist < best_dist:
                best_dist = dist
                best_label = label
        return best_label, best_dist

    def evaluate(self, dataset, split="holdout"):
        """Evaluate on a split."""
        correct = 0
        total = 0
        results = []
        for item in dataset:
            if item["split"] != split:
                continue
            if item["label"] == "unknown":
                continue
            pred, dist = self.predict(item["features"])
            is_correct = (pred == item["label"])
            if is_correct:
                correct += 1
            total += 1
            results.append({
                "world_type": item["world_type"],
                "seed": item["seed"],
                "predicted": pred,
                "actual": item["label"],
                "correct": is_correct,
                "distance": dist
            })
        accuracy = correct / total if total > 0 else 0
        return accuracy, results


# ================================================================
# Isolated BENCHMARK V2. All V1 definitions above remain unchanged.
# These choices are fixed before generating V2 benchmark results.
# ================================================================

BENCHMARK_V2_FEATURE_NAMES = (
    "anisotropy", "autocorrelation", "compression", "entropy",
    "finite_precision_sensitivity", "quantization", "recurrence",
    "spectral_sparsity",
)
BENCHMARK_V2_LABELS = ("natural", "computational")  # Fixed tie order.
BENCHMARK_V2_TRAIN_LABELS = {
    "WORLD_ANALYTIC": "natural",
    "WORLD_GAUSSIAN": "natural",
    "WORLD_FRACTAL_ANALYTIC": "natural",
    "WORLD_LATTICE": "computational",
    "WORLD_QUANTIZED": "computational",
    "WORLD_PRNG": "computational",
    "WORLD_HASH": "computational",
}
BENCHMARK_V2_ADVERSARIAL_WORLDS = (
    "WORLD_HIGHLY_COMPRESSED_ANALYTIC",
    "WORLD_SMOOTH_WITH_LATTICE_ARTIFACT",
    "WORLD_FRACTAL_WITH_QUANTIZATION",
)
BENCHMARK_V2_FEATURE_DEFINITIONS = {
    "anisotropy": "V1 max absolute directional correlation minus directional mean",
    "autocorrelation": "V1 horizontal lag-one covariance / population variance",
    "compression": "V1 RLE proxy: runs of int(value*10) / cells; constant = 1/cells",
    "entropy": "V1 clipped 16-bin entropy / log(16)",
    "finite_precision_sensitivity": "V1 absolute entropy change after floor(value*256)/255",
    "quantization": "V1 unique int(value*100) levels / min(cells,100)",
    "recurrence": "V1 directed four-neighbor fraction with absolute difference < 0.1",
    "spectral_sparsity": "V1 15 non-DC 4x4 low-DCT modes: fraction > 0.1*max; exact constant = 0",
}


def _benchmark_seed_v2(seed):
    if type(seed) is not int or not 1 <= seed <= 20:
        raise ValueError("V2 benchmark seeds must be integers in 1..20")
    return seed


def _prime_parameters_v2(seed):
    seed = _benchmark_seed_v2(seed)
    start = 2 + (seed - 1) * NCELLS
    return {
        "definition_id": "WORLD_PRIME",
        "window_start": start,
        "window_stop_inclusive": start + NCELLS - 1,
        "phase": SplitMix64(seed).next_u64() % NCELLS,
    }


def world_prime_v2(seed):
    """Inverse standard pi on disjoint arithmetic windows, circularly phased.

    For row-major index i, k = 2+(seed-1)*NCELLS+(i+phase)%NCELLS.
    phase is the first existing SplitMix64(seed) uint64 modulo NCELLS.
    pi(0)=pi(1)=0; values are 1/max(pi(k),1), min-max normalized
    within this field only. No seed or label is a detector feature.
    """
    params = _prime_parameters_v2(seed)
    start, stop = params["window_start"], params["window_stop_inclusive"]
    sieve = bytearray(b"\x01") * (stop + 1)
    sieve[0:2] = b"\x00\x00"
    for prime in range(2, math.isqrt(stop) + 1):
        if sieve[prime]:
            count = (stop - prime * prime) // prime + 1
            sieve[prime * prime:stop + 1:prime] = b"\x00" * count
    count = sum(sieve[:start])
    window = []
    for k in range(start, stop + 1):
        count += sieve[k]
        window.append(1.0 / max(count, 1))
    low, high = min(window), max(window)
    if high == low:
        return [0.5] * NCELLS
    phase = params["phase"]
    return [(window[(i + phase) % NCELLS] - low) / (high - low)
            for i in range(NCELLS)]


def world_highly_compressed_analytic_v2(seed):
    """Analytic-origin negative: a smooth one-dimensional sine, repeated by row."""
    rng = SplitMix64(_benchmark_seed_v2(seed))
    frequency, phase = rng.uniform(0.5, 1.5), rng.uniform(0, 2 * math.pi)
    row = [0.5 + 0.4 * math.sin(frequency * math.pi * col / (WIDTH - 1) + phase)
           for col in range(WIDTH)]
    return row * HEIGHT


def world_smooth_with_lattice_artifact_v2(seed):
    """Analytic-origin negative with a fixed-amplitude sampling checkerboard."""
    seed = _benchmark_seed_v2(seed)
    base = world_analytic(seed)
    phase = SplitMix64(seed).next_u64() % 2
    return [max(0.0, min(1.0, value + 0.025 *
                        (1 if (i // WIDTH + i % WIDTH + phase) % 2 == 0 else -1)))
            for i, value in enumerate(base)]


def world_fractal_with_quantization_v2(seed):
    """Analytic-origin negative: the V1 analytic fractal rounded to 16 levels."""
    base = world_fractal_analytic(_benchmark_seed_v2(seed))
    return [math.floor(value * 15 + 0.5) / 15 for value in base]


# Explicit registry: neither training eligibility nor feature choice is inferred
# from a generated field, a caller's labels, or the mutable V1 registry.
BENCHMARK_V2_WORLD_GENERATORS = {
    "WORLD_ANALYTIC": world_analytic,
    "WORLD_RANDOM_IID": world_random_iid,
    "WORLD_GAUSSIAN": world_gaussian,
    "WORLD_FRACTAL_ANALYTIC": world_fractal_analytic,
    "WORLD_LATTICE": world_lattice,
    "WORLD_QUANTIZED": world_quantized,
    "WORLD_PRNG": world_prng,
    "WORLD_HASH": world_hash,
    "WORLD_PRIME": world_prime_v2,
    "WORLD_SMOOTH_HIGHLY_COMPRESSED": world_smooth_highly_compressed,
    "WORLD_FRACTAL_HIGHLY_COMPRESSED": world_fractal_highly_compressed,
    "WORLD_HIGHLY_COMPRESSED_ANALYTIC": world_highly_compressed_analytic_v2,
    "WORLD_SMOOTH_WITH_LATTICE_ARTIFACT": world_smooth_with_lattice_artifact_v2,
    "WORLD_FRACTAL_WITH_QUANTIZATION": world_fractal_with_quantization_v2,
}


def _benchmark_field_v2(field):
    values = [float(value) for value in field]
    if len(values) != NCELLS or not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
        raise ValueError("V2 fields must contain exactly NCELLS finite values in [0,1]")
    return values


def field_hash_v2(field):
    """SHA-256 of row-major IEEE-754 float64 little-endian values only."""
    import hashlib
    import struct
    values = _benchmark_field_v2(field)
    return hashlib.sha256(struct.pack("<" + "d" * len(values), *values)).hexdigest()


def extract_features_v2(field):
    """Frozen V1 formulas; avoid interpreting constant-field DCT roundoff as signal."""
    values = _benchmark_field_v2(field)
    features = extract_features(values)
    if min(values) == max(values):
        features["spectral_sparsity"] = 0.0
    return {name: features[name] for name in BENCHMARK_V2_FEATURE_NAMES}


def generate_benchmark_v2():
    """Return all 235 raw feature rows; no fitting, files, or global RNG state."""
    rows = []
    for world_type, generator in BENCHMARK_V2_WORLD_GENERATORS.items():
        adversarial = world_type in BENCHMARK_V2_ADVERSARIAL_WORLDS
        seeds = range(16, 21) if adversarial else range(1, 21)
        for seed in seeds:
            if world_type == "WORLD_PRIME":
                label, split, cohort = "computational", "holdout", "prime"
            elif adversarial:
                label, split, cohort = "natural", "holdout", "adversarial"
            else:
                label = BENCHMARK_V2_TRAIN_LABELS.get(world_type, "unknown")
                split = "train" if seed <= 10 else "validation" if seed <= 15 else "holdout"
                cohort = "ambiguous" if label == "unknown" else "definite"
            field = generator(seed)
            rows.append({
                "world_type": world_type, "seed": seed, "split": split,
                "label": label, "cohort": cohort,
                "features": extract_features_v2(field),
                "field_hash": field_hash_v2(field),
                "generator": (_prime_parameters_v2(seed) if cohort == "prime" else
                              {"definition_id": world_type}),
            })
    return rows


def _benchmark_features_v2(features):
    if set(features) != set(BENCHMARK_V2_FEATURE_NAMES):
        raise ValueError("V2 requires exactly the eight frozen features")
    values = {name: float(features[name]) for name in BENCHMARK_V2_FEATURE_NAMES}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("V2 features must be finite")
    return values


def fit_benchmark_v2(rows):
    """Fit only allowlisted, definitely labeled non-prime seeds 1..10.

    Ineligible rows are ignored before accessing features, even if falsely marked
    train. Validation/holdout cannot supply labels, moments, features or thresholds.
    Population standard deviations use ddof=0; a zero std has unit divisor.
    """
    training = []
    seen = set()
    for row in rows:
        world_type, seed = row.get("world_type"), row.get("seed")
        if (world_type not in BENCHMARK_V2_TRAIN_LABELS or row.get("split") != "train"
                or type(seed) is not int or not 1 <= seed <= 10):
            continue
        label = BENCHMARK_V2_TRAIN_LABELS[world_type]
        if row.get("label") != label:
            raise ValueError("Training label disagrees with the frozen V2 origin label")
        key = (world_type, seed)
        if key in seen:
            raise ValueError("Duplicate V2 training key")
        seen.add(key)
        training.append((key, label, _benchmark_features_v2(row["features"])))
    training.sort(key=lambda item: item[0])
    counts = {label: sum(item[1] == label for item in training)
              for label in BENCHMARK_V2_LABELS}
    if not all(counts.values()):
        raise ValueError("V2 training needs both predetermined classes")
    means, stds, scales = {}, {}, {}
    for name in BENCHMARK_V2_FEATURE_NAMES:
        values = [item[2][name] for item in training]
        means[name] = math.fsum(values) / len(values)
        stds[name] = math.sqrt(math.fsum((v - means[name]) ** 2 for v in values) / len(values))
        scales[name] = stds[name] if stds[name] > 0 else 1.0
    centroids = {
        label: {
            name: math.fsum((features[name] - means[name]) / scales[name]
                            for _, actual, features in training if actual == label) / counts[label]
            for name in BENCHMARK_V2_FEATURE_NAMES
        } for label in BENCHMARK_V2_LABELS
    }
    return {
        "algorithm": "standardized_nearest_centroid", "feature_names": list(BENCHMARK_V2_FEATURE_NAMES),
        "scaling": {"mean": means, "std": stds, "scale": scales, "ddof": 0,
                    "fit_split": "train", "zero_variance_policy": "unit divisor; no clipping"},
        "centroids": centroids, "training_counts": counts,
        "training_keys": [{"world_type": key[0], "seed": key[1]} for key, _, _ in training],
        "distance": "squared Euclidean; equal weight for every frozen feature",
        "tie_order": list(BENCHMARK_V2_LABELS), "thresholds": None,
    }


def normalize_features_v2(features, model):
    """Transform with stored training moments only; do not clip unseen values."""
    values = _benchmark_features_v2(features)
    scaling = model["scaling"]
    return {name: (values[name] - scaling["mean"][name]) / scaling["scale"][name]
            for name in BENCHMARK_V2_FEATURE_NAMES}


def predict_benchmark_v2(features, model):
    """Return the prediction, both distances and normalized features without fitting."""
    normalized = normalize_features_v2(features, model)
    distances = {
        label: math.fsum((normalized[name] - model["centroids"][label][name]) ** 2
                         for name in BENCHMARK_V2_FEATURE_NAMES)
        for label in BENCHMARK_V2_LABELS
    }
    return {"prediction": min(BENCHMARK_V2_LABELS, key=distances.get),
            "distances": distances, "normalized_features": normalized}


def summarize_benchmark_v2(rows):
    """Computational is positive. Undefined ratios are JSON null, never NaN."""
    confusion = {name: 0 for name in ("TP", "TN", "FP", "FN")}
    excluded = 0
    for row in rows:
        label = row["label"]
        if label not in BENCHMARK_V2_LABELS:
            excluded += 1
            continue
        prediction = row["prediction"]
        if prediction not in BENCHMARK_V2_LABELS:
            raise ValueError("Unknown V2 prediction")
        key = ("T" if label == prediction else "F") + ("P" if prediction == "computational" else "N")
        confusion[key] += 1
    tp, tn, fp, fn = (confusion[name] for name in ("TP", "TN", "FP", "FN"))
    total = tp + tn + fp + fn
    return {"total": total, "excluded_unknown": excluded, "positive_label": "computational",
            "confusion": confusion, "accuracy": (tp + tn) / total if total else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def _benchmark_definitions_v2():
    definitions = {name: {"implementation": generator.__name__,
                          "definition": "Unchanged V1 generator; existing SplitMix64 where stochastic"}
                   for name, generator in BENCHMARK_V2_WORLD_GENERATORS.items()}
    definitions["WORLD_PRIME"]["definition"] = (
        "Row-major i: start=2+(seed-1)*NCELLS; phase=first SplitMix64(seed) uint64 % NCELLS; "
        "k=start+(i+phase)%NCELLS; raw=1/max(pi(k),1), standard pi(0)=pi(1)=0; "
        "min-max normalize within each arithmetic window; constant window maps to 0.5. "
        "Windows are disjoint; neither seed nor label is a feature."
    )
    definitions["WORLD_HIGHLY_COMPRESSED_ANALYTIC"]["definition"] = (
        "SplitMix64(seed) draws f in [0.5,1.5), p in [0,2*pi); "
        "value=0.5+0.4*sin(f*pi*col/(WIDTH-1)+p), repeated identically in every row."
    )
    definitions["WORLD_SMOOTH_WITH_LATTICE_ARTIFACT"]["definition"] = (
        "V1 analytic(seed) plus 0.025*(-1)^(row+col+phase), clipped to [0,1]; "
        "phase=first SplitMix64(seed) uint64 % 2. Sampling artifact, not cellular dynamics."
    )
    definitions["WORLD_FRACTAL_WITH_QUANTIZATION"]["definition"] = (
        "V1 fractal_analytic(seed), rounded by floor(value*15+0.5)/15 to 16 levels. "
        "Analytic-origin label is preserved despite quantization."
    )
    return definitions


def run_benchmark_v2():
    """Return a JSON-serializable, deterministic BENCHMARK V2 result, without I/O.

    This API does not tune, persist an experiment, or alter any V1 registry/model.
    All unknown-label worlds receive predictions but never supervised scores.
    """
    rows = generate_benchmark_v2()
    model = fit_benchmark_v2(rows)
    for row in rows:
        row.update(predict_benchmark_v2(row["features"], model))
    summaries = {split: summarize_benchmark_v2(r for r in rows if r["split"] == split)
                 for split in ("train", "validation", "holdout")}
    prime = [r for r in rows if r["cohort"] == "prime"]
    adversarial = [r for r in rows if r["cohort"] == "adversarial"]
    ambiguous = [r for r in rows if r["cohort"] == "ambiguous"]
    detected = [r["seed"] for r in prime if r["prediction"] == "computational"]
    hash_groups = {}
    for row in rows:
        hash_groups.setdefault(row["field_hash"], []).append(
            {name: row[name] for name in ("world_type", "seed", "split")})
    return {
        "benchmark_version": "V2", "rows": rows, "model": model, "summaries": summaries,
        "protocol": {
            "shape": {"width": WIDTH, "height": HEIGHT},
            "train_seeds": list(range(1, 11)), "validation_seeds": list(range(11, 16)),
            "holdout_seeds": list(range(16, 21)), "prime_holdout_seeds": list(range(1, 21)),
            "training_labels": dict(BENCHMARK_V2_TRAIN_LABELS),
            "adversarial_label": "natural", "positive_label": "computational",
            "label_policy": "Frozen V1 definite labels; new adversaries are analytic-origin negatives; unknowns unscored",
            "feature_definitions": dict(BENCHMARK_V2_FEATURE_DEFINITIONS),
            "feature_policy": "Eight V1 formulas frozen before results; exact constant DCT explicitly zero; no selection or tuning",
            "summary_policy": "Per-split scores include all definite labels, prime and adversaries; unknowns excluded",
            "prng": "Existing SplitMix64 uint64 wraparound; uniform from upper 53 bits; no global or system randomness",
            "field_hash_encoding": "SHA-256 of row-major little-endian IEEE-754 float64; no seed/label metadata",
            "generator_definitions": _benchmark_definitions_v2(),
        },
        "prime_detections": {
            "total": len(prime), "detected": len(detected), "detected_seeds": detected,
            "missed_seeds": [r["seed"] for r in prime if r["prediction"] != "computational"],
            "detection_rate": len(detected) / len(prime),
            "distinct_hashes": len({r["field_hash"] for r in prime}),
            "summary": summarize_benchmark_v2(prime),
        },
        "distinct_hashes": {
            "total": len(hash_groups),
            "by_world": {world: len({r["field_hash"] for r in rows if r["world_type"] == world})
                         for world in BENCHMARK_V2_WORLD_GENERATORS},
            "cross_split_duplicates": [{"field_hash": digest, "keys": keys}
                                       for digest, keys in sorted(hash_groups.items())
                                       if len({key["split"] for key in keys}) > 1],
        },
        "adversarial_results": {
            "summary": summarize_benchmark_v2(adversarial),
            "by_world": {
                world: {"summary": summarize_benchmark_v2(r for r in adversarial if r["world_type"] == world),
                        "seeds": [r["seed"] for r in adversarial if r["world_type"] == world],
                        "false_positive_seeds": [r["seed"] for r in adversarial
                                                 if r["world_type"] == world and r["prediction"] == "computational"]}
                for world in BENCHMARK_V2_ADVERSARIAL_WORLDS
            },
        },
        "ambiguous_results": {
            "total": len(ambiguous), "policy": "Predictions only; no supervised scores or fitting",
            "by_world": {
                world: {"total": sum(r["world_type"] == world for r in ambiguous),
                        "predictions_by_split": {
                            split: {label: sum(r["world_type"] == world and r["split"] == split
                                              and r["prediction"] == label for r in ambiguous)
                                    for label in BENCHMARK_V2_LABELS}
                            for split in ("train", "validation", "holdout")}}
                for world in sorted({r["world_type"] for r in ambiguous})
            },
        },
    }
