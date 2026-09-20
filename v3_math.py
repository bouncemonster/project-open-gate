"""
Proof of Simulation V3 — arithmetic sequences, controls and spectral utilities.

Standard-library only. Every sequence is deterministic and documented so that
V3 can compare "exact prime arithmetic" against statistically and
mathematically matched alternatives. Nothing here mutates V1/V2 state.
"""
import math
import hashlib
import struct


# ---------------------------------------------------------------- primes
def sieve_is_prime(n):
    """Return a bytearray p where p[k] == 1 iff k is prime, for 0..n."""
    if n < 0:
        raise ValueError("n must be >= 0")
    p = bytearray(b"\x01") * (n + 1)
    p[0] = 0
    if n >= 1:
        p[1] = 0
    for i in range(2, math.isqrt(n) + 1):
        if p[i]:
            p[i * i:n + 1:i] = b"\x00" * (((n - i * i) // i) + 1)
    return p


def pi_counts(n):
    """pi(k) = number of primes <= k for k = 0..n. Standard pi(0)=pi(1)=0."""
    p = sieve_is_prime(n)
    out = [0] * (n + 1)
    c = 0
    for k in range(2, n + 1):
        if p[k]:
            c += 1
        out[k] = c
    return out


def sequence_hash(values):
    """SHA-256 over IEEE-754 float64 little-endian values (V3 driver identity)."""
    return hashlib.sha256(struct.pack("<" + "d" * len(values), *values)).hexdigest()


# ---------------------------------------------------------------- Ei / li / R
def ei(x):
    """Exponential integral Ei(x) for x>0 via convergent series
    gamma + ln(x) + sum_{m>=1} x^m/(m*m!)."""
    if x <= 0:
        return 0.0
    if x > 50.0:
        s, t = 1.0, 1.0
        for k in range(1, 80):
            t *= k / x
            if t < 1e-16:
                break
            s += t
        return math.exp(x) / x * s
    gamma = 0.577215664901532860606512090082402431
    total = gamma + math.log(x)
    term = 1.0
    for m in range(1, 200):
        term *= x / m
        add = term / m
        total += add
        if abs(add) < 1e-16 * abs(total):
            break
    return total


def li(x):
    """Logarithmic integral li(x)=Ei(log x) for x>=2; 0 for x<2."""
    if x < 2.0:
        return 0.0
    return ei(math.log(x))


def mobius(n):
    """Moebius mu(n) by trial division (n small in V3 usage)."""
    if n == 1:
        return 1
    mu = 1
    m = n
    d = 2
    while d * d <= m:
        if m % d == 0:
            m //= d
            if m % d == 0:
                return 0
            mu = -mu
        d += 1
    if m > 1:
        mu = -mu
    return mu


def riemann_R(x):
    """Riemann R(x) = sum_{m>=1} mu(m)/m * li(x^(1/m)). Smooth approximation
    to pi(x); R(2)=0 exactly (li(2)=li(sqrt2)=0)."""
    if x < 2.0:
        return 0.0
    total = 0.0
    m = 1
    while m <= 64:
        root = x ** (1.0 / m)
        if root < 2.0 and m > 1:
            break
        mu = mobius(m)
        if mu:
            total += mu / m * li(root)
        m += 1
    return total


# ---------------------------------------------------------------- sequences
def seq_P(pi, max_iter):
    """P(k) = 1/max(pi(k),1), P(0)=1. Full inverse-prime signal (V1_FULL)."""
    P = [0.0] * (max_iter + 1)
    P[0] = 1.0
    for k in range(1, max_iter + 1):
        P[k] = 1.0 / max(pi[k], 1)
    return P


def seq_E(P, max_iter):
    """E(k) = P(k) - P(k-1). Prime indicator event train (V9_EVENT)."""
    return [0.0] + [P[k] - P[k - 1] for k in range(1, max_iter + 1)]


def seq_residual(P, S1, max_iter):
    """R(k) = P(k) - S1(k) (prime residual before standardisation)."""
    return [0.0] + [P[k] - S1[k] for k in range(1, max_iter + 1)]


def seq_S1_riemann(max_iter):
    """S1_ANALYTIC (V3): 1/max(R(k),1) using Riemann R, k<=2 protected to 1."""
    out = [0.0] * (max_iter + 1)
    for k in range(1, max_iter + 1):
        if k <= 2:
            out[k] = 1.0
        else:
            out[k] = 1.0 / max(riemann_R(float(k)), 1.0)
    return out


def seq_S2(P, max_iter, window):
    """S2_DATA_SMOOTHED: centered uniform moving average of P (window fixed
    in advance). Boundary clamps k to [1,max_iter]; no future truncation."""
    hw = window // 2
    out = [0.0] * (max_iter + 1)
    for k in range(1, max_iter + 1):
        s = 0.0
        c = 0
        for j in range(k - hw, k + hw + 1):
            jj = 1 if j < 1 else (max_iter if j > max_iter else j)
            s += P[jj]
            c += 1
        out[k] = s / c
    return out


def mean(values, max_iter, ref=200):
    n = min(max_iter, ref)
    return sum(values[k] for k in range(1, n + 1)) / n


def rms(values, max_iter, ref=200):
    n = min(max_iter, ref)
    return math.sqrt(sum(values[k] * values[k] for k in range(1, n + 1)) / n)


def standardize(values, max_iter, ref=200):
    """Zero-mean / unit-RMS over a fixed first-`ref` reference window; applied
    to the whole sequence. Zero variance => all zeros."""
    n = min(max_iter, ref)
    m = sum(values[1:n + 1]) / n
    var = sum((values[k] - m) ** 2 for k in range(1, n + 1)) / n
    if var < 1e-15:
        return [0.0] * (max_iter + 1)
    sd = math.sqrt(var)
    return [0.0] + [(values[k] - m) / sd for k in range(1, max_iter + 1)]


def center(values, max_iter, ref=200):
    m = mean(values, max_iter, ref)
    return [0.0] + [values[k] - m for k in range(1, max_iter + 1)]


def scale_to_rms(values, max_iter, target_rms, ref=200):
    """Rescale a zero-mean sequence so its reference RMS equals target_rms."""
    r = rms(values, max_iter, ref)
    if r < 1e-15:
        return [0.0] * (max_iter + 1)
    f = target_rms / r
    return [0.0] + [values[k] * f for k in range(1, max_iter + 1)]


# ---------------------------------------------------------------- matched events
def splitmix64(seed):
    state = seed & 0xFFFFFFFFFFFFFFFF

    def nxt():
        nonlocal state
        state = (state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF
    return nxt


def event_positions_amplitudes(E, max_iter):
    pos, amp = [], []
    for k in range(1, max_iter + 1):
        if abs(E[k]) > 1e-18:
            pos.append(k)
            amp.append(E[k])
    return pos, amp


def seq_V11_matched_event(E, max_iter, seed):
    """Same event amplitudes and count, positions permuted deterministically
    into distinct slots over the finite window. No position optimisation."""
    pos, amp = event_positions_amplitudes(E, max_iter)
    out = [0.0] * (max_iter + 1)
    nev = len(pos)
    if nev == 0:
        return out
    nxt = splitmix64(seed)
    slots = list(range(1, max_iter + 1))
    for i in range(len(slots) - 1, 0, -1):
        j = nxt() % (i + 1)
        slots[i], slots[j] = slots[j], slots[i]
    for i in range(nev):
        out[slots[i]] = amp[i]
    return out
# ---------------------------------------------------------------- 2D DCT
def dct2_matrix(n):
    """DCT-II orthonormal basis matrix (n x n)."""
    M = [[0.0] * n for _ in range(n)]
    for u in range(n):
        cu = math.sqrt(1.0 / n) if u == 0 else math.sqrt(2.0 / n)
        for x in range(n):
            M[u][x] = cu * math.cos(math.pi * (2 * x + 1) * u / (2 * n))
    return M


def dct2(field, W, H):
    """2D orthonormal DCT-II coefficients, row-major (H rows, W cols)."""
    MX = dct2_matrix(W)
    MY = dct2_matrix(H)
    tmp = [[0.0] * W for _ in range(H)]
    for y in range(H):
        row = field[y * W:(y + 1) * W]
        for u in range(W):
            Mu = MX[u]
            tmp[y][u] = sum(Mu[x] * row[x] for x in range(W))
    out = [[0.0] * W for _ in range(H)]
    for u in range(W):
        col = [tmp[y][u] for y in range(H)]
        for v in range(H):
            Mv = MY[v]
            out[v][u] = sum(Mv[y] * col[y] for y in range(H))
    return out


def dct_low_energy(field, W, H, keep=3):
    C = dct2(field, W, H)
    tot = sum(c * c for row in C for c in row)
    low = sum(C[v][u] ** 2 for v in range(min(keep, H)) for u in range(min(keep, W)))
    return low, tot - low


def dct_lowpass_field(field, W, H, keep=3, highpass=False):
    """Field reconstructed from the fixed keep x keep low-frequency DCT block
    (highpass=True removes that block). The primary score is never modified."""
    C = dct2(field, W, H)
    MX = dct2_matrix(W)
    MY = dct2_matrix(H)
    for v in range(H):
        for u in range(W):
            in_block = (v < keep and u < keep)
            if (highpass and in_block) or ((not highpass) and not in_block):
                C[v][u] = 0.0
    out = [0.0] * (W * H)
    for y in range(H):
        for x in range(W):
            s = 0.0
            for v in range(H):
                Myv = MY[v][y]
                if Myv == 0.0:
                    continue
                row = C[v]
                s += Myv * sum(MX[u][x] * row[u] for u in range(W))
            out[y * W + x] = s
    return out


def dct_sign_surrogate(field, W, H, seed):
    """Deterministic surrogate preserving |DCT coefficients| (spectral
    envelope) while randomising signs; DC sign is fixed so the mean is kept."""
    C = dct2(field, W, H)
    nxt = splitmix64(seed)
    for v in range(H):
        for u in range(W):
            if u == 0 and v == 0:
                continue
            if nxt() & 1:
                C[v][u] = -C[v][u]
    MX = dct2_matrix(W)
    MY = dct2_matrix(H)
    out = [0.0] * (W * H)
    for y in range(H):
        for x in range(W):
            s = 0.0
            for v in range(H):
                Myv = MY[v][y]
                if Myv == 0.0:
                    continue
                row = C[v]
                s += Myv * sum(MX[u][x] * row[u] for u in range(W))
            out[y * W + x] = s
    return out


def seq_V12_shifted_event(E, max_iter, shift):
    """Exact E(k) circularly shifted by `shift` over the finite window."""
    s = shift % max_iter
    out = [0.0] * (max_iter + 1)
    for k in range(1, max_iter + 1):
        src = (k - 1 - s) % max_iter + 1
        out[k] = E[src]
    return out


# ---------------------------------------------------------------- field controls
def field_constant(W, H, value=0.5):
    return [value] * (W * H)


def field_x_ramp(W, H):
    return [x / (W - 1) if W > 1 else 0.5 for _ in range(H) for x in range(W)]


def field_y_ramp(W, H):
    return [y / (H - 1) if H > 1 else 0.5 for y in range(H) for _ in range(W)]


def field_bilinear(W, H):
    out = []
    for y in range(H):
        v = y / (H - 1) if H > 1 else 0.5
        for x in range(W):
            u = x / (W - 1) if W > 1 else 0.5
            out.append(u * v)
    return out


def field_radial(W, H):
    out = []
    for y in range(H):
        v = y / (H - 1) if H > 1 else 0.5
        for x in range(W):
            u = x / (W - 1) if W > 1 else 0.5
            out.append(math.hypot(u - 0.5, v - 0.5))
    return out


def low_frequency_family(W, H):
    """L1..L6 fixed smooth separable fields (holdout validation only)."""
    fam = {}
    fam["L1_u"] = field_x_ramp(W, H)
    fam["L2_v"] = field_y_ramp(W, H)
    fam["L3_uv"] = field_bilinear(W, H)
    fam["L4_abs_sin_pi_u"] = [abs(math.sin(math.pi * (x / (W - 1) if W > 1 else 0.5)))
                              for _ in range(H) for x in range(W)]
    fam["L5_abs_cos_pi_v"] = [abs(math.cos(math.pi * (y / (H - 1) if H > 1 else 0.5)))
                              for y in range(H) for _ in range(W)]
    fam["L6_sin_sin"] = [math.sin(math.pi * (x / (W - 1)))
                         * math.sin(math.pi * (y / (H - 1)))
                         for y in range(H) for x in range(W)]
    return fam


# ---------------------------------------------------------------- field features
def mean_flat(v):
    return sum(v) / len(v)


def std_flat(v):
    m = mean_flat(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / len(v))


def field_entropy(field, bins=16):
    n = len(field)
    lo, hi = min(field), max(field)
    if hi <= lo:
        return 0.0
    counts = [0] * bins
    for v in field:
        b = int((v - lo) / (hi - lo) * bins)
        if b >= bins:
            b = bins - 1
        counts[b] += 1
    ent = 0.0
    for c in counts:
        if c:
            p = c / n
            ent -= p * math.log(p)
    return ent / math.log(bins)


def _pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def field_autocorr(field, W, H):
    return _pearson(field[:-1], field[1:]) if len(field) > 1 else 0.0


def field_gradient_energy(field, W, H):
    s = 0.0
    for y in range(H):
        for x in range(W):
            v = field[y * W + x]
            if x + 1 < W:
                d = field[y * W + x + 1] - v
                s += d * d
            if y + 1 < H:
                d = field[(y + 1) * W + x] - v
                s += d * d
    return s


def field_anisotropy(field, W, H):
    gh = sum((field[y * W + x + 1] - field[y * W + x]) ** 2
             for y in range(H) for x in range(W - 1))
    gv = sum((field[(y + 1) * W + x] - field[y * W + x]) ** 2
             for y in range(H - 1) for x in range(W))
    tot = gh + gv
    return (gh / tot) if tot > 0 else 0.5


def target_features(field, W, H):
    low, high = dct_low_energy(field, W, H, keep=3)
    return {
        "mean": mean_flat(field),
        "std": std_flat(field),
        "entropy": field_entropy(field),
        "dct_low_energy": low,
        "dct_high_energy": high,
        "anisotropy": field_anisotropy(field, W, H),
        "autocorrelation": field_autocorr(field, W, H),
        "gradient_energy": field_gradient_energy(field, W, H),
    }


# ---------------------------------------------------------------- temporal nulls
def circular_shift(values, shift):
    n = len(values)
    s = shift % n
    return values[s:] + values[:s]


def block_bootstrap_ci(pairs, block, iters, seed):
    """Moving-block bootstrap CI for the mean of a paired contrast series."""
    n = len(pairs)
    if n == 0:
        return (0.0, 0.0)
    nxt = splitmix64(seed)
    means = []
    for _ in range(iters):
        acc, cnt = 0.0, 0
        while cnt < n:
            start = nxt() % n
            for j in range(block):
                acc += pairs[(start + j) % n]
                cnt += 1
                if cnt >= n:
                    break
        means.append(acc / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[min(iters - 1, int(0.975 * iters))]
    return (lo, hi)


def seq_V13_gap_matched(E, max_iter, seed):
    """Preserve event count, amplitudes and the circular gap multiset, but
    permute the gaps deterministically. No position optimisation."""
    pos, amp = event_positions_amplitudes(E, max_iter)
    out = [0.0] * (max_iter + 1)
    nev = len(pos)
    if nev < 2:
        for i in range(nev):
            out[pos[i]] = amp[i]
        return out
    gaps = [pos[i + 1] - pos[i] for i in range(nev - 1)]
    gaps.append(max_iter - pos[-1] + pos[0])
    nxt = splitmix64(seed)
    for i in range(len(gaps) - 1, 0, -1):
        j = nxt() % (i + 1)
        gaps[i], gaps[j] = gaps[j], gaps[i]
    new_pos = [pos[0]]
    for i in range(1, nev):
        new_pos.append((new_pos[-1] + gaps[i - 1] - 1) % max_iter + 1)
    for i in range(nev):
        out[new_pos[i]] = amp[i]
    return out


def seq_V5_shuffled(P, max_iter, seed):
    """Full inverse-prime values shuffled with SplitMix64 (legacy V5)."""
    out = [0.0] + [P[k] for k in range(1, max_iter + 1)]
    nxt = splitmix64(seed)
    for k in range(max_iter, 1, -1):
        j = 1 + nxt() % k
        out[k], out[j] = out[j], out[k]
    return out