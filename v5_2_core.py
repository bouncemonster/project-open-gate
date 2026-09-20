"""V5.2: Counterfactual substrate pairs with 3-layer architecture.

Layers:
  GENERATOR: the mathematical rule/content (G01-G10)
  SUBSTRATE: the computational precision/mechanism (continuous vs finite)
  OBSERVATION: what the detector actually sees (resolution, noise, quantization)

The detector classifies SUBSTRATE while controlling for GENERATOR and OBSERVATION.
"""
import math
import struct
import hashlib
from typing import List, Dict, Tuple, Optional
from v5_math import SplitMix64, extract_full_fingerprint


# ============================================================================
# GENERATOR FAMILIES (G01-G10)
# These define the mathematical CONTENT of the world.
# ============================================================================

def gen_G01_analytic_smooth(width, height, seed) -> List[float]:
    """Smooth analytic field: superposition of sinusoids."""
    rng = SplitMix64(seed)
    terms = []
    for _ in range(4):
        a = rng.next_double() * 2 - 1
        fx = rng.next_double() * 4 + 0.5
        fy = rng.next_double() * 4 + 0.5
        phi = rng.next_double() * 2 * math.pi
        terms.append((a, fx, fy, phi))
    field = []
    for y in range(height):
        for x in range(width):
            nx, ny = x / width, y / height
            v = sum(a * math.sin(fx * nx * 2 * math.pi + phi) *
                    math.cos(fy * ny * 2 * math.pi + phi) for a, fx, fy, phi in terms)
            field.append(v)
    return field


def gen_G02_gaussian_correlated(width, height, seed) -> List[float]:
    """Correlated Gaussian random field."""
    rng = SplitMix64(seed)
    white = [rng.next_double() * 2 - 1 for _ in range(width * height)]
    sigma = 3.0
    ks = 7
    kernel = []
    for ky in range(-ks // 2, ks // 2 + 1):
        for kx in range(-ks // 2, ks // 2 + 1):
            kernel.append(math.exp(-(kx * kx + ky * ky) / (2 * sigma * sigma)))
    ksum = sum(kernel)
    kernel = [k / ksum for k in kernel]
    smoothed = []
    for y in range(height):
        for x in range(width):
            s, ki = 0.0, 0
            for ky in range(-ks // 2, ks // 2 + 1):
                for kx in range(-ks // 2, ks // 2 + 1):
                    ny = max(0, min(height - 1, y + ky))
                    nx = max(0, min(width - 1, x + kx))
                    s += white[ny * width + nx] * kernel[ki]
                    ki += 1
            smoothed.append(s)
    return smoothed


def gen_G03_analytic_fractal(width, height, seed) -> List[float]:
    """Julia set fractal (analytic iteration)."""
    rng = SplitMix64(seed)
    cr = rng.next_double() * 1.5 - 0.75
    ci = rng.next_double() * 1.5 - 0.75
    max_iter = 100
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


def gen_G04_wave_eigenmode(width, height, seed) -> List[float]:
    """Wave/eigenmode field (standing waves on rectangular domain)."""
    rng = SplitMix64(seed)
    modes = []
    for _ in range(5):
        nx_m = rng.next_u64() % 8 + 1
        ny_m = rng.next_u64() % 8 + 1
        amp = rng.next_double() * 2 - 1
        modes.append((nx_m, ny_m, amp))
    field = []
    for y in range(height):
        for x in range(width):
            nx, ny = x / width, y / height
            v = sum(a * math.sin(nxm * math.pi * nx) * math.sin(nym * math.pi * ny)
                    for nxm, nym, a in modes)
            field.append(v)
    return field


def gen_G05_chaotic_map(width, height, seed) -> List[float]:
    """Logistic map iterates arranged as 2D field."""
    rng = SplitMix64(seed)
    r = 3.9 + rng.next_double() * 0.1
    x0 = rng.next_double() * 0.8 + 0.1
    field = []
    for y in range(height):
        x = x0 + y * 1e-6  # slightly different initial condition per row
        for step in range(width):
            x = r * x * (1 - x)
            field.append(x)
    return field


def gen_G06_nonlinear_dyn(width, height, seed) -> List[float]:
    """Lorenz-like system sampled as time series reshaped to 2D."""
    rng = SplitMix64(seed)
    sigma, rho, beta = 10.0, 28.0, 8.0 / 3
    dt = 0.005
    x, y, z = rng.next_double(), rng.next_double(), rng.next_double()
    field = []
    total = width * height
    for i in range(total):
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta * z
        x += dx * dt
        y += dy * dt
        z += dz * dt
        field.append(z / 50.0)  # normalize
    return field


def gen_G07_reaction_diffusion(width, height, seed) -> List[float]:
    """Gray-Scott reaction-diffusion (simplified, few steps)."""
    rng = SplitMix64(seed)
    # Initialize with random perturbation
    grid = [[0.5 + rng.next_double() * 0.01 for _ in range(width)] for _ in range(height)]
    v_grid = [[0.25 + rng.next_double() * 0.01 for _ in range(width)] for _ in range(height)]
    Da, Dv, F, k = 0.16, 0.08, 0.037, 0.06
    dt = 1.0
    for step in range(50):
        new_u = [[0.0] * width for _ in range(height)]
        new_v = [[0.0] * width for _ in range(height)]
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                lap_u = (grid[y-1][x] + grid[y+1][x] + grid[y][x-1] + grid[y][x+1] - 4 * grid[y][x])
                lap_v = (v_grid[y-1][x] + v_grid[y+1][x] + v_grid[y][x-1] + v_grid[y][x+1] - 4 * v_grid[y][x])
                uvv = grid[y][x] * v_grid[y][x] * v_grid[y][x]
                new_u[y][x] = grid[y][x] + dt * (Da * lap_u - uvv + F * (1 - grid[y][x]))
                new_v[y][x] = v_grid[y][x] + dt * (Dv * lap_v + uvv - (F + k) * v_grid[y][x])
        grid, v_grid = new_u, new_v
    field = []
    for y in range(height):
        for x in range(width):
            field.append(grid[y][x])
    return field


def gen_G08_procedural_noise(width, height, seed) -> List[float]:
    """Multi-octave procedural noise (value noise with interpolation)."""
    rng = SplitMix64(seed)
    octaves = 5
    base_grid_size = 4
    grids = []
    for o in range(octaves):
        gs = base_grid_size * (2 ** o) + 1
        g = [[rng.next_double() for _ in range(gs)] for _ in range(gs)]
        grids.append(g)
    
    field = []
    for y in range(height):
        for x in range(width):
            val = 0.0
            amp = 1.0
            for o in range(octaves):
                gs = base_grid_size * (2 ** o) + 1
                fx = (x / width) * (gs - 1)
                fy = (y / height) * (gs - 1)
                ix, iy = int(fx), int(fy)
                fx -= ix
                fy -= iy
                ix2 = min(ix + 1, gs - 1)
                iy2 = min(iy + 1, gs - 1)
                # Smoothstep
                sx = fx * fx * (3 - 2 * fx)
                sy = fy * fy * (3 - 2 * fy)
                v = (grids[o][iy][ix] * (1-sx) * (1-sy) +
                     grids[o][iy][ix2] * sx * (1-sy) +
                     grids[o][iy2][ix] * (1-sx) * sy +
                     grids[o][iy2][ix2] * sx * sy)
                val += v * amp
                amp *= 0.5
            field.append(val)
    return field


def gen_G09_coupled_oscillator(width, height, seed) -> List[float]:
    """Coupled oscillator field (phase field with spatial coupling)."""
    rng = SplitMix64(seed)
    omega = rng.next_double() * 3 + 1
    coupling = rng.next_double() * 2
    field = []
    for y in range(height):
        for x in range(width):
            nx, ny = x / width, y / height
            phase = omega * nx * 2 * math.pi + coupling * math.sin(ny * 4 * math.pi)
            v = math.sin(phase) * math.cos(ny * 3 * math.pi)
            field.append(v)
    return field


def gen_G10_cosmological_like(width, height, seed) -> List[float]:
    """Synthetic cosmological-like field (power-law spectrum, efficient)."""
    rng = SplitMix64(seed)
    spectral_index = -1.5 - rng.next_double()
    # Use random Fourier modes (limited count for efficiency)
    n_modes = 30
    modes = []
    for _ in range(n_modes):
        kx = (rng.next_u64() % width) - width // 2
        ky = (rng.next_u64() % height) - height // 2
        freq = math.sqrt(kx * kx + ky * ky) + 1
        amp = freq ** (spectral_index / 2)
        phase = rng.next_double() * 2 * math.pi
        modes.append((kx, ky, amp, phase))
    field = []
    for y in range(height):
        for x in range(width):
            v = sum(a * math.cos(2 * math.pi * (kx * x / width + ky * y / height) + ph)
                    for kx, ky, a, ph in modes)
            field.append(v)
    # Normalize
    fmax = max(abs(fv) for fv in field) if field else 1
    if fmax > 0:
        field = [fv / fmax for fv in field]
    return field


GENERATORS = {
    "G01_analytic_smooth": gen_G01_analytic_smooth,
    "G02_gaussian_correlated": gen_G02_gaussian_correlated,
    "G03_analytic_fractal": gen_G03_analytic_fractal,
    "G04_wave_eigenmode": gen_G04_wave_eigenmode,
    "G05_chaotic_map": gen_G05_chaotic_map,
    "G06_nonlinear_dyn": gen_G06_nonlinear_dyn,
    "G07_reaction_diffusion": gen_G07_reaction_diffusion,
    "G08_procedural_noise": gen_G08_procedural_noise,
    "G09_coupled_oscillator": gen_G09_coupled_oscillator,
    "G10_cosmological_like": gen_G10_cosmological_like,
}


# ============================================================================
# SUBSTRATE TRANSFORMS
# These modify the COMPUTATION without changing the generator.
# ============================================================================

def sub_continuous_reference(field: List[float]) -> List[float]:
    """S_CONTINUOUS: float64 reference (no modification)."""
    return field


def sub_float32(field: List[float]) -> List[float]:
    """S_FLOAT32: reduce to float32 precision."""
    return [float(struct.unpack('f', struct.pack('f', v))[0]) for v in field]


def sub_float16(field: List[float]) -> List[float]:
    """S_FLOAT16: reduce to ~float16 precision (3 decimal digits)."""
    return [round(v, 3) for v in field]


def sub_quantize_8bit(field: List[float]) -> List[float]:
    """S_QUANT_8: 8-bit quantization."""
    fmin, fmax = min(field), max(field)
    rng = fmax - fmin if fmax > fmin else 1
    return [int((v - fmin) / rng * 255) / 255.0 for v in field]


def sub_quantize_4bit(field: List[float]) -> List[float]:
    """S_QUANT_4: 4-bit quantization."""
    fmin, fmax = min(field), max(field)
    rng = fmax - fmin if fmax > fmin else 1
    return [int((v - fmin) / rng * 15) / 15.0 for v in field]


def sub_lattice(field: List[float], width: int, height: int) -> List[float]:
    """S_LATTICE: snap coordinates to fixed grid (block quantization)."""
    block = 4
    out = []
    for y in range(height):
        for x in range(width):
            bx = (x // block) * block + block // 2
            by = (y // block) * block + block // 2
            bx = min(bx, width - 1)
            by = min(by, height - 1)
            out.append(field[by * width + bx])
    return out


def sub_lookup_table(field: List[float], width: int, height: int) -> List[float]:
    """S_LOOKUP: quantize values to nearest entry in small LUT."""
    lut_size = 16
    fmin, fmax = min(field), max(field)
    rng = fmax - fmin if fmax > fmin else 1
    lut = [fmin + i * rng / (lut_size - 1) for i in range(lut_size)]
    out = []
    for v in field:
        # Find nearest LUT entry
        idx = round((v - fmin) / rng * (lut_size - 1))
        idx = max(0, min(lut_size - 1, idx))
        out.append(lut[idx])
    return out


def sub_hash_coordinate(field: List[float], width: int, height: int, seed: int) -> List[float]:
    """S_HASH: replace values with hash-derived quantized version."""
    out = []
    for i, v in enumerate(field):
        h = hashlib.md5(f"{seed}:{i}:{v:.10f}".encode()).digest()
        hv = struct.unpack('<I', h[:4])[0] / 0xFFFFFFFF
        # Blend original with hash (preserves structure but adds discrete noise)
        out.append(v * 0.95 + hv * 0.05)
    return out


def sub_finite_state(field: List[float], width: int, height: int) -> List[float]:
    """S_FINITE_STATE: restrict to N discrete levels with hysteresis."""
    n_states = 12
    fmin, fmax = min(field), max(field)
    rng = fmax - fmin if fmax > fmin else 1
    out = []
    prev_level = 0
    for v in field:
        level = int((v - fmin) / rng * n_states)
        level = max(0, min(n_states - 1, level))
        # Hysteresis: only change if different by >= 1
        if abs(level - prev_level) >= 1:
            prev_level = level
        out.append(fmin + prev_level * rng / n_states)
    return out


# Substrate registry
SUBSTRATES_CONTINUOUS = {"S_CONTINUOUS", "S_UNKNOWN_CONTINUOUS"}
SUBSTRATES_COMPUTATIONAL = {
    "S_FLOAT32", "S_FLOAT16", "S_QUANT_8", "S_QUANT_4",
    "S_LATTICE", "S_LOOKUP", "S_HASH", "S_FINITE_STATE",
    "S_UNKNOWN_COMPUTATIONAL"
}


def apply_substrate(name: str, field: List[float], width: int, height: int, seed: int) -> List[float]:
    """Apply substrate transform to a field."""
    if name == "S_CONTINUOUS":
        return sub_continuous_reference(field)
    elif name == "S_FLOAT32":
        return sub_float32(field)
    elif name == "S_FLOAT16":
        return sub_float16(field)
    elif name == "S_QUANT_8":
        return sub_quantize_8bit(field)
    elif name == "S_QUANT_4":
        return sub_quantize_4bit(field)
    elif name == "S_LATTICE":
        return sub_lattice(field, width, height)
    elif name == "S_LOOKUP":
        return sub_lookup_table(field, width, height)
    elif name == "S_HASH":
        return sub_hash_coordinate(field, width, height, seed)
    elif name == "S_FINITE_STATE":
        return sub_finite_state(field, width, height)
    elif name == "S_UNKNOWN_COMPUTATIONAL":
        # Novel computational substrate: modular arithmetic + bit manipulation
        out = []
        for i, v in enumerate(field):
            # Quantize to 10-bit, apply XOR with position
            q = int(v * 1023) & 0x3FF
            q ^= (i * 7) & 0x3FF
            out.append(q / 1023.0)
        return out
    elif name == "S_UNKNOWN_CONTINUOUS":
        # Novel continuous substrate: high-precision but with subtle transformation
        out = []
        for v in field:
            # Apply smooth but non-obvious transformation
            out.append(math.tanh(v * 1.001) / 1.001)
        return out
    else:
        return field


# ============================================================================
# COUNTERFACTUAL PAIR GENERATION
# ============================================================================

def generate_counterfactual_pair(generator_name: str, seed: int,
                                  width: int, height: int) -> Dict:
    """Generate a matched pair: same generator, different substrate."""
    # Generate base field with continuous reference
    base_field = GENERATORS[generator_name](width, height, seed)
    
    # Continuous version (reference)
    continuous_field = sub_continuous_reference(base_field)
    
    # Computational version (float32 as default)
    computational_field = sub_float32(base_field)
    
    return {
        "generator": generator_name,
        "seed": seed,
        "width": width,
        "height": height,
        "continuous_field": continuous_field,
        "computational_field": computational_field,
    }


def generate_all_substrates(generator_name: str, seed: int,
                             width: int, height: int) -> Dict[str, List[float]]:
    """Generate the same world under all substrates."""
    base_field = GENERATORS[generator_name](width, height, seed)
    results = {}
    for sub_name in ["S_CONTINUOUS", "S_FLOAT32", "S_FLOAT16", "S_QUANT_8",
                     "S_QUANT_4", "S_LATTICE", "S_LOOKUP", "S_HASH", "S_FINITE_STATE",
                     "S_UNKNOWN_COMPUTATIONAL", "S_UNKNOWN_CONTINUOUS"]:
        results[sub_name] = apply_substrate(sub_name, base_field, width, height, seed)
    return results


# ============================================================================
# MATCHED-STATISTIC ADVERSARIAL WORLD (§12-§18)
# ============================================================================

def match_histogram(source: List[float], target: List[float]) -> List[float]:
    """Remap source values to match target histogram using monotonic transform."""
    n = len(source)
    # Sort indices
    src_order = sorted(range(n), key=lambda i: source[i])
    tgt_sorted = sorted(target)
    # Map: i-th smallest in source → i-th smallest in target
    result = [0.0] * n
    for rank, idx in enumerate(src_order):
        result[idx] = tgt_sorted[rank]
    return result


def match_spectrum(field: List[float], width: int, height: int,
                   target_field: List[float]) -> List[float]:
    """Preserve target DCT magnitudes while using source phases."""
    # Simplified: just return target (in practice would do phase randomization)
    return target_field


def create_matched_pair(generator_name: str, seed: int,
                        width: int, height: int) -> Dict:
    """Create adversarial pair with matched statistics."""
    base_field = GENERATORS[generator_name](width, height, seed)
    cont_field = sub_continuous_reference(base_field)
    comp_field = sub_quantize_8bit(base_field)
    
    # Match histogram: make computational look like continuous
    comp_matched = match_histogram(comp_field, cont_field)
    
    return {
        "generator": generator_name,
        "seed": seed,
        "continuous": cont_field,
        "computational": comp_field,
        "computational_matched": comp_matched,  # histogram-matched
    }
