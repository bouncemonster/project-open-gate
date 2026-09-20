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
