"""WorldForge2: Generate synthetic worlds with known generative mechanisms."""
import math
import hashlib
import struct
from typing import List, Dict, Tuple, Optional
from v5_math import SplitMix64


# ============================================================================
# WORLD GENERATORS
# ============================================================================

def generate_W01_continuous_analytic(width: int, height: int, seed: int) -> List[float]:
    """W01: Smooth analytic functions."""
    rng = SplitMix64(seed)
    field = []
    # Random combination of sin/cos/exp
    a1 = rng.next_double() * 2 - 1
    a2 = rng.next_double() * 2 - 1
    a3 = rng.next_double() * 2 - 1
    f1 = rng.next_double() * 4 + 1
    f2 = rng.next_double() * 4 + 1
    phase = rng.next_double() * math.pi * 2
    
    for y in range(height):
        for x in range(width):
            nx = (x / width - 0.5) * 4
            ny = (y / height - 0.5) * 4
            v = (a1 * math.sin(f1 * nx + phase) +
                 a2 * math.cos(f2 * ny + phase) +
                 a3 * math.exp(-(nx*nx + ny*ny) / 4))
            field.append(v)
    return field


def generate_W02_gaussian_field(width: int, height: int, seed: int) -> List[float]:
    """W02: Correlated Gaussian random field with spectral control."""
    rng = SplitMix64(seed)
    # Generate white noise
    white = [rng.next_double() * 2 - 1 for _ in range(width * height)]
    
    # Apply Gaussian smoothing for correlation
    sigma = 2.0
    kernel_size = 5
    kernel = []
    for ky in range(-kernel_size // 2, kernel_size // 2 + 1):
        for kx in range(-kernel_size // 2, kernel_size // 2 + 1):
            kernel.append(math.exp(-(kx*kx + ky*ky) / (2 * sigma * sigma)))
    ksum = sum(kernel)
    kernel = [k / ksum for k in kernel]
    
    # Convolve
    smoothed = []
    for y in range(height):
        for x in range(width):
            s = 0.0
            ki = 0
            for ky in range(-kernel_size // 2, kernel_size // 2 + 1):
                for kx in range(-kernel_size // 2, kernel_size // 2 + 1):
                    ny = max(0, min(height - 1, y + ky))
                    nx = max(0, min(width - 1, x + kx))
                    s += white[ny * width + nx] * kernel[ki]
                    ki += 1
            smoothed.append(s)
    return smoothed


def generate_W03_fractal_analytic(width: int, height: int, seed: int) -> List[float]:
    """W03: Julia set fractal (from V4 kernel logic)."""
    rng = SplitMix64(seed)
    cr = rng.next_double() * 1.5 - 0.75
    ci = rng.next_double() * 1.5 - 0.75
    max_iter = 50
    
    field = []
    for y in range(height):
        for x in range(width):
            zr = (x / width - 0.5) * 3
            zi = (y / height - 0.5) * 3
            n = 0
            while zr * zr + zi * zi < 4 and n < max_iter:
                zr, zi = zr * zr - zi * zi + cr, 2 * zr * zi + ci
                n += 1
            field.append(n / max_iter)
    return field


def generate_W04_float32(width: int, height: int, seed: int) -> List[float]:
    """W04: Float32 precision reduction of analytic field."""
    base = generate_W01_continuous_analytic(width, height, seed)
    return [float(struct.unpack('f', struct.pack('f', v))[0]) for v in base]


def generate_W05_float16(width: int, height: int, seed: int) -> List[float]:
    """W05: Float16 precision reduction of analytic field."""
    base = generate_W01_continuous_analytic(width, height, seed)
    # Simulate float16 by rounding to ~3 decimal digits
    scale = 1000
    return [round(v * scale) / scale for v in base]


def generate_W06_quantized_8bit(width: int, height: int, seed: int) -> List[float]:
    """W06: 8-bit quantized version of analytic field."""
    base = generate_W01_continuous_analytic(width, height, seed)
    fmin, fmax = min(base), max(base)
    rng_val = fmax - fmin
    if rng_val == 0:
        return [0.0] * len(base)
    return [int((v - fmin) / rng_val * 255) / 255.0 for v in base]


def generate_W07_quantized_4bit(width: int, height: int, seed: int) -> List[float]:
    """W07: 4-bit quantized version of analytic field."""
    base = generate_W01_continuous_analytic(width, height, seed)
    fmin, fmax = min(base), max(base)
    rng_val = fmax - fmin
    if rng_val == 0:
        return [0.0] * len(base)
    return [int((v - fmin) / rng_val * 15) / 15.0 for v in base]


def generate_W08_fixed_grid(width: int, height: int, seed: int) -> List[float]:
    """W08: Values computed on fixed regular grid with grid artifacts."""
    rng = SplitMix64(seed)
    field = []
    grid_freq = 8  # Grid frequency
    a1 = rng.next_double() * 2 - 1
    a2 = rng.next_double() * 2 - 1
    
    for y in range(height):
        for x in range(width):
            # Grid-aligned computation
            gx = int(x / grid_freq) * grid_freq
            gy = int(y / grid_freq) * grid_freq
            nx = (gx / width - 0.5) * 4
            ny = (gy / height - 0.5) * 4
            v = a1 * math.sin(nx * 3) + a2 * math.cos(ny * 3)
            field.append(v)
    return field


def generate_W09_cellular_automaton(width: int, height: int, seed: int) -> List[float]:
    """W09: Cellular automaton evolution (Rule 30)."""
    rng = SplitMix64(seed)
    rule = 30  # Rule 30 CA
    
    # Initial row
    row = [rng.next_u64() % 2 for _ in range(width)]
    field = list(row)
    
    for step in range(height - 1):
        new_row = []
        for x in range(width):
            left = row[(x - 1) % width]
            center = row[x]
            right = row[(x + 1) % width]
            idx = (left << 2) | (center << 1) | right
            new_row.append((rule >> idx) & 1)
        row = new_row
        field.extend(row)
    
    return [float(v) for v in field]


def generate_W10_prng(width: int, height: int, seed: int) -> List[float]:
    """W10: PRNG-based field (SplitMix64)."""
    rng = SplitMix64(seed)
    return [rng.next_double() for _ in range(width * height)]


def generate_W11_hash(width: int, height: int, seed: int) -> List[float]:
    """W11: Hash-based procedural generation."""
    field = []
    for y in range(height):
        for x in range(width):
            # Hash coordinates with seed
            data = f"{seed}:{x}:{y}".encode()
            h = hashlib.sha256(data).digest()
            v = struct.unpack('<I', h[:4])[0] / 0xFFFFFFFF
            field.append(v)
    return field


def generate_W12_compressed_procedural(width: int, height: int, seed: int) -> List[float]:
    """W12: Compressed representation with decompression artifacts."""
    # Generate base field
    base = generate_W01_continuous_analytic(width, height, seed)
    
    # Simulate compression by quantizing and adding block artifacts
    block_size = 8
    compressed = []
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            # Quantize to 8-bit
            v = base[idx]
            v = int(v * 255) / 255.0
            # Add block boundary artifact
            if x % block_size == 0 or y % block_size == 0:
                v += 0.01
            compressed.append(v)
    return compressed


def generate_W13_finite_state(width: int, height: int, seed: int) -> List[float]:
    """W13: Finite state machine with limited state space."""
    rng = SplitMix64(seed)
    n_states = 16
    states = [i / (n_states - 1) for i in range(n_states)]
    
    field = []
    state = rng.next_u64() % n_states
    for _ in range(width * height):
        # State transition
        state = (state * 7 + rng.next_u64() % 5) % n_states
        field.append(states[state])
    return field


def generate_W14_lookup_table(width: int, height: int, seed: int) -> List[float]:
    """W14: Precomputed lookup table with bilinear interpolation."""
    rng = SplitMix64(seed)
    # Small lookup table
    lut_size = 8
    lut = [[rng.next_double() for _ in range(lut_size)] for _ in range(lut_size)]
    
    field = []
    for y in range(height):
        for x in range(width):
            # Map to LUT coordinates
            lx = x / width * (lut_size - 1)
            ly = y / height * (lut_size - 1)
            # Bilinear interpolation
            x0, y0 = int(lx), int(ly)
            x1, y1 = min(x0 + 1, lut_size - 1), min(y0 + 1, lut_size - 1)
            fx, fy = lx - x0, ly - y0
            v = (lut[y0][x0] * (1 - fx) * (1 - fy) +
                 lut[y0][x1] * fx * (1 - fy) +
                 lut[y1][x0] * (1 - fx) * fy +
                 lut[y1][x1] * fx * fy)
            field.append(v)
    return field


def generate_W15_prime_driven(width: int, height: int, seed: int) -> List[float]:
    """W15: Prime-driven generation (from V4)."""
    # Simple prime-based field
    primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
    
    field = []
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            # Use prime at position (idx % len(primes))
            p = primes[idx % len(primes)]
            v = math.sin(x * p / 10.0) * math.cos(y * p / 10.0)
            field.append(v)
    return field


def generate_W16_hybrid_computational(width: int, height: int, seed: int) -> List[float]:
    """W16: Hybrid of multiple computational mechanisms."""
    rng = SplitMix64(seed)
    mechanism = rng.next_u64() % 4
    
    if mechanism == 0:
        # CA + quantization
        base = generate_W09_cellular_automaton(width, height, seed)
        return [int(v * 15) / 15.0 for v in base]
    elif mechanism == 1:
        # PRNG + hash
        base1 = generate_W10_prng(width, height, seed)
        base2 = generate_W11_hash(width, height, seed + 1)
        return [(a + b) / 2 for a, b in zip(base1, base2)]
    elif mechanism == 2:
        # Lookup + finite state
        base1 = generate_W14_lookup_table(width, height, seed)
        base2 = generate_W13_finite_state(width, height, seed + 1)
        return [(a + b) / 2 for a, b in zip(base1, base2)]
    else:
        # Compressed + prime
        base1 = generate_W12_compressed_procedural(width, height, seed)
        base2 = generate_W15_prime_driven(width, height, seed + 1)
        return [(a + b) / 2 for a, b in zip(base1, base2)]


def generate_W17_unknown_computational(width: int, height: int, seed: int) -> List[float]:
    """W17: Unknown computational mechanism (runtime generated)."""
    rng = SplitMix64(seed)
    # Novel mechanism: XOR-shift based with modular arithmetic
    state = seed & 0xFFFFFFFF
    field = []
    for _ in range(width * height):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        v = (state % 1000) / 999.0
        field.append(v)
    return field


def generate_W18_unknown_analytic(width: int, height: int, seed: int) -> List[float]:
    """W18: Unknown analytic mechanism (symmetric to W17)."""
    rng = SplitMix64(seed)
    # Novel analytic mechanism: superposition of incommensurate frequencies
    a1 = rng.next_double() * 2 - 1
    a2 = rng.next_double() * 2 - 1
    a3 = rng.next_double() * 2 - 1
    f1 = rng.next_double() * 5 + 0.5
    f2 = rng.next_double() * 5 + 0.5
    f3 = rng.next_double() * 3 + 0.3
    phi = rng.next_double() * math.pi
    field = []
    for y in range(height):
        for x in range(width):
            nx = x / width
            ny = y / height
            v = (a1 * math.sin(f1 * nx * 2 * math.pi + phi) +
                 a2 * math.sin(f2 * ny * 2 * math.pi + phi * 0.7) +
                 a3 * math.cos(f3 * (nx + ny) * math.pi + phi * 1.3) +
                 0.3 * math.exp(-((nx - 0.5)**2 + (ny - 0.5)**2) * 8))
            field.append(v)
    return field


# ============================================================================
# WORLD GENERATION DISPATCH
# ============================================================================

WORLD_GENERATORS = {
    "W01_CONTINUOUS_ANALYTIC": generate_W01_continuous_analytic,
    "W02_GAUSSIAN_FIELD": generate_W02_gaussian_field,
    "W03_FRACTAL_ANALYTIC": generate_W03_fractal_analytic,
    "W04_FLOAT32": generate_W04_float32,
    "W05_FLOAT16": generate_W05_float16,
    "W06_QUANTIZED_8BIT": generate_W06_quantized_8bit,
    "W07_QUANTIZED_4BIT": generate_W07_quantized_4bit,
    "W08_FIXED_GRID": generate_W08_fixed_grid,
    "W09_CELLULAR_AUTOMATON": generate_W09_cellular_automaton,
    "W10_PRNG": generate_W10_prng,
    "W11_HASH": generate_W11_hash,
    "W12_COMPRESSED_PROCEDURAL": generate_W12_compressed_procedural,
    "W13_FINITE_STATE": generate_W13_finite_state,
    "W14_LOOKUP_TABLE": generate_W14_lookup_table,
    "W15_PRIME_DRIVEN": generate_W15_prime_driven,
    "W16_HYBRID_COMPUTATIONAL": generate_W16_hybrid_computational,
    "W17_UNKNOWN_COMPUTATIONAL": generate_W17_unknown_computational,
    "W18_UNKNOWN_ANALYTIC": generate_W18_unknown_analytic,
}


def generate_world(world_type: str, width: int, height: int, seed: int) -> List[float]:
    """Generate a world of the specified type."""
    if world_type not in WORLD_GENERATORS:
        raise ValueError(f"Unknown world type: {world_type}")
    return WORLD_GENERATORS[world_type](width, height, seed)


def generate_paired_worlds(world_type: str, width: int, height: int, seed: int) -> Dict[str, List[float]]:
    """Generate a world and its paired variants."""
    pairs = {}
    
    # Base world
    base = generate_world(world_type, width, height, seed)
    pairs[world_type] = base
    
    # Paired variants based on category
    if world_type in ["W01_CONTINUOUS_ANALYTIC", "W02_GAUSSIAN_FIELD", "W03_FRACTAL_ANALYTIC"]:
        # Add precision pairs
        pairs["W04_FLOAT32"] = generate_W04_float32(width, height, seed)
        pairs["W05_FLOAT16"] = generate_W05_float16(width, height, seed)
        pairs["W06_QUANTIZED_8BIT"] = generate_W06_quantized_8bit(width, height, seed)
        pairs["W07_QUANTIZED_4BIT"] = generate_W07_quantized_4bit(width, height, seed)
    
    return pairs


# ============================================================================
# OBSERVATION CONDITIONS
# ============================================================================

def apply_observation_condition(field: List[float], width: int, height: int,
                                condition: str, seed: int = 0) -> Tuple[List[float], int, int]:
    """Apply observation condition to a world field."""
    if condition == "O1_FULL_PRECISION":
        return field, width, height
    
    elif condition == "O2_8BIT_OBSERVATION":
        fmin, fmax = min(field), max(field)
        rng_val = fmax - fmin if fmax > fmin else 1
        quantized = [int((v - fmin) / rng_val * 255) / 255.0 for v in field]
        return quantized, width, height
    
    elif condition == "O3_4BIT_OBSERVATION":
        fmin, fmax = min(field), max(field)
        rng_val = fmax - fmin if fmax > fmin else 1
        quantized = [int((v - fmin) / rng_val * 15) / 15.0 for v in field]
        return quantized, width, height
    
    elif condition == "O4_DOWNSAMPLED":
        new_w, new_h = width // 2, height // 2
        downsampled = []
        for y in range(new_h):
            for x in range(new_w):
                # Average 2x2 block
                idx = (2 * y) * width + (2 * x)
                v = (field[idx] + field[idx + 1] +
                     field[idx + width] + field[idx + width + 1]) / 4
                downsampled.append(v)
        return downsampled, new_w, new_h
    
    elif condition == "O5_NOISY_OBSERVATION":
        rng = SplitMix64(seed + 999)
        sigma = 0.05
        noisy = [v + rng.next_double() * sigma * 2 - sigma for v in field]
        return noisy, width, height
    
    elif condition == "O6_FINITE_RESOLUTION":
        # Keep at 60x30
        return field, width, height
    
    elif condition == "O7_TEMPORAL_SUBSAMPLE":
        # For static fields, this is a no-op
        return field, width, height
    
    else:
        raise ValueError(f"Unknown observation condition: {condition}")
