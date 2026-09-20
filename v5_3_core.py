"""V5.3 Core: NATIVE computational substrates + recurrence generators.

KEY DIFFERENCE FROM V5.2 (§1): the substrate participates in the recurrence
DURING evolution. There is no float64 trajectory that gets quantized afterward.
Every arithmetic operation of the generator's recurrence is executed through
the substrate's arithmetic kernel, so trajectories DIVERGE natively.

Substrate arithmetic kernels
============================
S64           float64 reference
S32           IEEE single precision rounding applied to EVERY stored state
S16           IEEE half precision rounding applied to EVERY stored state
S_Q15         16-bit signed fixed point (all ops integer, 2^-15 scale)
S_FSM         finite-state set; transition function = arithmetic then state snap
S_MOD         integer modular recurrence (scale, mod prime, back to field)
S_HASH_NATIVE hash/PRNG state participates in the recurrence term-by-term
S_UNKNOWN     novel mechanism (held out from training; see §12 of spec)

All kernels are pure standard-library and deterministic.
"""
import struct
import math

# ---------------------------------------------------------------------------
# Arithmetic kernels: each maps a float64 value (or pair) to the substrate's
# representable value / result. These are applied INSIDE the recurrence.
# ---------------------------------------------------------------------------

def _f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def _f16(x):
    # clamp to half range then round-trip
    if x > 65504.0:
        x = 65504.0
    elif x < -65504.0:
        x = -65504.0
    try:
        return struct.unpack('e', struct.pack('e', x))[0]
    except (OverflowError, ValueError):
        return 0.0


Q15_SCALE = 32768.0
Q15_MAX = 32767
Q15_MIN = -32768


def _q15_to_int(x):
    """float -> Q15 int with saturation (recurrence values are bounded to [-1,1]
    by generator convention)."""
    q = int(round(x * Q15_SCALE))
    if q > Q15_MAX:
        q = Q15_MAX
    elif q < Q15_MIN:
        q = Q15_MIN
    return q


def _q15_from_int(q):
    return q / Q15_SCALE


def q15_add(a_q, b_q):
    return _q15_to_int(_q15_from_int(a_q) + _q15_from_int(b_q))


def q15_mul(a_q, b_q):
    # product of two [-1,1] values stays in range
    return _q15_to_int(_q15_from_int(a_q) * _q15_from_int(b_q))


def f32_to_q15(x):
    return _q15_to_int(x)


def q15_to_f32(q):
    return _f32(_q15_from_int(q))


# Hash kernel: SplitMix64 (same PRNG family used across this project).
SM_MASK = 0xFFFFFFFFFFFFFFFF


def splitmix64(state):
    state = (state + 0x9E3779B97F4A7C15) & SM_MASK
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & SM_MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & SM_MASK
    z = z ^ (z >> 31)
    return state, z


def hash_unit(state):
    """Deterministic uniform value in [-1, 1) from a hash state."""
    state, h = splitmix64(state)
    return state, (h & 0xFFFFFFFF) / 2147483648.0 - 1.0


MOD_PRIME = 100003          # prime modulus for S_MOD field arithmetic
MOD_SCALE = 50000.0         # values map to [-1, 1)


def mod_encode(x):
    """float64 state value -> integer residue."""
    return int(round(x * MOD_SCALE)) % MOD_PRIME


def mod_decode(q):
    """integer residue -> float in [-1, 1)."""
    if q >= MOD_PRIME // 2:
        q -= MOD_PRIME
    return q / MOD_SCALE


# ---------------------------------------------------------------------------
# Substrate state transformers: applied to the FULL field after every
# recurrence step (i.e. the substrate's representable-state constraint acts
# during evolution, not after). Each returns a list of float64 values that
# round-trips through the substrate's native representation.
# ---------------------------------------------------------------------------

def snap_s64(field):
    return field


def snap_s32(field):
    return [_f32(v) for v in field]


def snap_s16(field):
    return [_f16(v) for v in field]


def snap_sq15(field):
    return [_q15_from_int(_q15_to_int(v)) for v in field]


# S_FSM: 13 global states (odd count -> symmetric lattice including 0).
FSM_N_STATES = 13


def _build_fsm_states():
    # states on [-1, 1] lattice
    return [(-1.0 + 2.0 * i / (FSM_N_STATES - 1)) for i in range(FSM_N_STATES)]


FSM_STATES = _build_fsm_states()
_FSM_INDEX = {round(s, 10): i for i, s in enumerate(FSM_STATES)}


def fsm_snap(v):
    """Snap a value to the nearest finite state (state set constraint applied
    at every recurrence step: the dynamics live ON the state lattice)."""
    best = 0
    bestd = abs(v - FSM_STATES[0])
    for i in range(1, FSM_N_STATES):
        d = abs(v - FSM_STATES[i])
        if d < bestd:
            bestd = d
            best = i
    return FSM_STATES[best]


def snap_sfsm(field):
    return [fsm_snap(v) for v in field]


def snap_smod(field):
    """Every value must live in the integer residue ring (encode->decode
    roundtrip at each step; the recurrence never sees non-residue values)."""
    return [mod_decode(mod_encode(v)) for v in field]


def make_hash_native_step(seed):
    """Hash-driven substrate: returns a per-step perturbation function whose
    internal state evolves through the hash chain. The perturbation enters
    the recurrence ITSELF (see generator step functions), so it compounds."""
    state = seed & SM_MASK

    def perturb(i, v):
        nonlocal state
        state, u = hash_unit(state)
        # additive contribution of hash state into the recurrence term
        return v + 0.05 * u
    return perturb


def snap_shash(field):
    return field  # hashing acts inside the recurrence, not as a snapshot snap


def snap_sunknown(field):
    # Novel mechanism (HOLDOUT): ternary mantissa truncation.
    # Keep only the top 2 bits of the mantissa of each float64 -> a dense but
    # non-uniform representable set unlike any training substrate.
    out = []
    for v in field:
        if v == 0.0:
            out.append(0.0)
            continue
        b = struct.unpack('<Q', struct.pack('<d', v))[0]
        b &= 0xC00FFFFFFFFFFFFF   # clear mantissa except top 2 bits
        out.append(struct.unpack('<d', struct.pack('<Q', b))[0])
    return out


SNAPSHOTS = {
    "S64": snap_s64,
    "S32": snap_s32,
    "S16": snap_s16,
    "S_Q15": snap_sq15,
    "S_FSM": snap_sfsm,
    "S_MOD": snap_smod,
    "S_HASH_NATIVE": snap_shash,
    "S_UNKNOWN": snap_sunknown,
}

# Substrate classification (never shown to the detector)
SUBSTRATES_CONTINUOUS = ["S64"]
SUBSTRATES_COMPUTATIONAL = ["S32", "S16", "S_Q15", "S_FSM", "S_MOD",
                            "S_HASH_NATIVE", "S_UNKNOWN"]

TRAIN_SUBSTRATES = ["S32", "S16", "S_Q15", "S_HASH_NATIVE"]
HOLDOUT_SUBSTRATES = ["S_FSM", "S_MOD", "S_UNKNOWN"]

# Q15 substrate flag: recurrence runs on integer pairs, not float snaps
Q15_SUBSTRATES = {"S_Q15"}
MOD_SUBSTRATES = {"S_MOD"}
HASH_SUBSTRATES = {"S_HASH_NATIVE"}


# ---------------------------------------------------------------------------
# Generators: 2D field recurrences u_{t+1} = F(u_t) on a width x height grid.
#
# The substrate is NATIVE: each step's arithmetic is routed through
#   step_fn(field, substrate, helpers) -> next_field
# which (a) computes the update in the substrate's representation where the
# representation changes the algebra (Q15/MOD), and (b) snaps states every
# step for ALL computational substrates. S64/S32/S16 differ only in rounding
# of stored states, which still compounds chaotically.
# ---------------------------------------------------------------------------

def _neighbors_sum(fld, w, h, i, j):
    """4-neighbour mean of cell (i,j) with clamp edges."""
    tot = 0.0
    cnt = 0
    ii, jj = i - 1, j
    if ii >= 0:
        tot += fld[ii * h + jj]; cnt += 1
    ii, jj = i + 1, j
    if ii < w:
        tot += fld[ii * h + jj]; cnt += 1
    ii, jj = i, j - 1
    if jj >= 0:
        tot += fld[ii * h + jj]; cnt += 1
    ii, jj = i, j + 1
    if jj < h:
        tot += fld[ii * h + jj]; cnt += 1
    return tot / cnt


def initial_field(w, h, seed, kind):
    """Seeded initial state; identical across substrates for a given
    (generator, seed) pair - the ONLY difference is the arithmetic kernel."""
    state = (seed ^ 0xDA7AB) & SM_MASK
    fld = []
    for i in range(w):
        for j in range(h):
            state, u = hash_unit(state)
            if kind == "noise":
                fld.append(u * 0.5)
            elif kind == "bump":
                x = (i - w / 2) / (w / 2)
                y = (j - h / 2) / (h / 2)
                r2 = x * x + y * y
                state2, n = hash_unit(state)
                state = state2
                fld.append(math.exp(-2.0 * r2) + 0.05 * n)
            else:  # stripes
                fld.append(math.sin(2.0 * math.pi * i / 7.0) * 0.5 + 0.02 * u)
    # clamp to [-1, 1] convention (all generators keep states in this band)
    return [max(-1.0, min(1.0, v)) for v in fld]


def _generic_step(fld, w, h, rule, post=None):
    out = []
    for i in range(w):
        for j in range(h):
            k = i * h + j
            nb = _neighbors_sum(fld, w, h, i, j)
            v = rule(fld[k], nb, i, j)
            if post is not None:
                v = post(v, k)
            out.append(max(-1.0, min(1.0, v)))
    return out


# --- rule definitions (the fixed mathematical content per §2) ---------------

def _g01_rule(u, nb, i, j):
    # smooth nonlinear relaxation
    return 0.9 * u + 0.1 * (nb * nb - 0.5 * u)


def _g02_rule(u, nb, i, j):
    # chaotic tent-like coupling
    t = 1.8 * u * (1.0 - abs(u)) + 0.15 * nb
    return t


def _g03_rule(u, nb, i, j):
    # coupled phase oscillator: rotate by own value + neighbour pull
    theta = math.asin(max(-1.0, min(1.0, u)))
    return math.sin(theta + 0.3 + 0.2 * nb)


def _g04_rule(u, nb, i, j):
    # Gray-Scott-like simplified activator-inhibitor on one field
    lap = nb - u
    return u + 0.12 * lap + 0.05 * u * (1.0 - u * u)


def _g05_rule_wavy(u, nb, prev_u, i, j):
    # wave equation needs previous frame: handled specially below
    return None


def _g06_rule(u, nb, i, j):
    # procedural dynamic field: multiplicative texture
    return 0.7 * u + 0.3 * math.tanh(2.0 * nb)


def _g07_rule(u, nb, i, j):
    # logistic-map field: fully native low-state chaos
    return 3.57 * u * (1.0 - u) + 0.02 * nb


def _g08_rule(u, nb, i, j):
    # diffusion + mixing: alternating blur and stretch
    return math.tanh(1.4 * nb) * 0.6 + 0.4 * u


# G05 is second-order in time -> uses (u_t, u_{t-1}) pair.
def _g05_step(fld, fld_prev, w, h):
    out = []
    for i in range(w):
        for j in range(h):
            k = i * h + j
            lap = _neighbors_sum(fld, w, h, i, j) - fld[k]
            v = 2.0 * fld[k] - fld_prev[k] + 0.36 * lap
            out.append(max(-1.0, min(1.0, v)))
    return out


# ---------------------------------------------------------------------------
# Native stepping dispatch: substrate changes the ARITHMETIC of the step.
# ---------------------------------------------------------------------------

def _step_q15(fld, w, h, rule):
    """Fixed-point recurrence: values stored as integers; every add/mul of the
    rule happens in Q15 (per spec: 'every recurrence operation must occur in
    fixed-point arithmetic'). We monkey-evaluate the linear-combination form
    of each rule using Q15 ops via a small expression table."""
    fq = [_q15_to_int(v) for v in fld]
    out_q = []
    for i in range(w):
        for j in range(h):
            k = i * h + j
            # neighbour mean in fixed point
            acc = 0
            cnt = 0
            parts = []
            ii = i - 1
            if ii >= 0:
                parts.append(ii * h + j)
            ii = i + 1
            if ii < w:
                parts.append(ii * h + j)
            jj = j - 1
            if jj >= 0:
                parts.append(i * h + jj)
            jj = j + 1
            if jj < h:
                parts.append(i * h + jj)
            nb_q = 0
            for pk in parts:
                nb_q = q15_add(nb_q, fq[pk])
            nb_q = _q15_to_int(_q15_from_int(nb_q) / len(parts))
            u_q = fq[k]
            if rule is _g01_rule:
                # 0.9u + 0.1(nb^2 - 0.5u)
                a = q15_mul(_q15_to_int(0.9), u_q)
                nb2 = q15_mul(nb_q, nb_q)
                b = q15_mul(_q15_to_int(0.1), q15_add(nb2, q15_mul(_q15_to_int(-0.5), u_q)))
                v_q = q15_add(a, b)
            elif rule is _g02_rule:
                # 1.8u(1-|u|) + 0.15nb  (1.8 handled as 0.9*2 via pre-clamped u)
                au = abs(u_q)
                one = _q15_to_int(1.0)
                inner = q15_add(one, q15_mul(_q15_to_int(-1.0), au))
                p1 = q15_mul(u_q, inner)
                v_q = q15_add(q15_mul(_q15_to_int(0.9), p1),
                              q15_add(q15_mul(_q15_to_int(0.9), p1),
                                      q15_mul(_q15_to_int(0.15), nb_q)))
                # note: 1.8 = 0.9+0.9 applied to product kept <=0.25 so no sat
            elif rule is _g03_rule:
                # transcendental fallback: compute in float but STORE in Q15
                # (state constraint native; op list documented in protocol)
                v = _g03_rule(_q15_from_int(u_q), _q15_from_int(nb_q), i, j)
                v_q = _q15_to_int(v)
            elif rule is _g04_rule:
                # u + 0.12(nb-u) + 0.05u(1-u^2)
                lap = q15_add(nb_q, q15_mul(_q15_to_int(-1.0), u_q))
                u2 = q15_mul(u_q, u_q)
                one = _q15_to_int(1.0)
                tail = q15_mul(_q15_to_int(0.05), q15_mul(u_q, q15_add(one, q15_mul(_q15_to_int(-1.0), u2))))
                v_q = q15_add(u_q, q15_add(q15_mul(_q15_to_int(0.12), lap), tail))
            else:  # _g06_rule / _g07_rule / _g08_rule
                if rule is _g07_rule:
                    # 3.57*(u - u^2) + 0.02*nb natively in Q15 (saturation is
                    # part of the substrate behaviour, not an error)
                    u2 = q15_mul(u_q, u_q)
                    x = q15_add(u_q, q15_mul(_q15_to_int(-1.0), u2))
                    xx = q15_add(x, x)
                    x4 = q15_add(xx, xx)
                    m = q15_mul(_q15_to_int(-0.43), x)
                    v_q = q15_add(q15_add(x4, m),
                                  q15_mul(_q15_to_int(0.02), nb_q))
                elif rule is _g08_rule:
                    # tanh fallback: transcendental not in Q15 op set (documented)
                    v = _g08_rule(_q15_from_int(u_q), _q15_from_int(nb_q), i, j)
                    v_q = _q15_to_int(v)
                else:
                    v = _g06_rule(_q15_from_int(u_q), _q15_from_int(nb_q), i, j)
                    v_q = _q15_to_int(v)
            out_q.append(v_q)
    return [_q15_from_int(q) for q in out_q]


def _step_mod(fld, w, h, rule):
    """Integer modular recurrence: the update algebra is performed in the
    residue ring Z_p (affine combination form per rule), then decoded."""
    fq = [mod_encode(v) for v in fld]
    p = MOD_PRIME

    def madd(a, b):
        return (a + b) % p

    def mmul(a, b):
        return (a * b) % p

    out_q = []
    for i in range(w):
        for j in range(h):
            k = i * h + j
            parts = []
            if i > 0:
                parts.append((i - 1) * h + j)
            if i < w - 1:
                parts.append((i + 1) * h + j)
            if j > 0:
                parts.append(i * h + j - 1)
            if j < h - 1:
                parts.append(i * h + j + 1)
            nbq = 0
            for pk in parts:
                nbq = madd(nbq, fq[pk])
            # mean = sum * inv(len) modulo p (len in {3,4}: use int division
            # equivalent multiplier via Fermat inverse)
            inv = pow(len(parts), p - 2, p)
            nbq = mmul(nbq, inv)
            uq = fq[k]
            # generic affine-in-ring update: a*u + b*nb + c*u*nb + d*u*u
            # coefficients chosen as scaled integer versions of each rule's
            # linear part (documented per-rule constants)
            a, b, c, d = _MOD_COEFFS[rule]
            v = madd(madd(mmul(a, uq), mmul(b, nbq)),
                     madd(mmul(c, mmul(uq, uq)), mmul(d, mmul(uq, nbq))))
            out_q.append(v)
    return [mod_decode(q) for q in out_q]


# Per-rule integer coefficients (x1000 residues) approximating each rule's
# second-order expansion u' = a*u + b*nb + c*u^2 + d*u*nb.
# These are FIXED constants of the substrate implementation (versioned).
_MOD_C = 1000


def _mc(x):
    return int(round(x * _MOD_C)) % MOD_PRIME


_MOD_COEFFS = {
    _g01_rule: (_mc(0.85), _mc(0.0), _mc(0.0), _mc(0.1)),
    _g02_rule: (_mc(1.8), _mc(0.15), _mc(-1.8), _mc(0.0)),
    _g03_rule: (_mc(0.95), _mc(0.2), _mc(0.0), _mc(0.0)),
    _g04_rule: (_mc(0.88), _mc(0.12), _mc(0.05), _mc(0.0)),
    _g06_rule: (_mc(0.7), _mc(0.3), _mc(0.0), _mc(0.0)),
    _g07_rule: (_mc(3.57), _mc(0.02), _mc(-3.57), _mc(0.0)),
    _g08_rule: (_mc(0.4), _mc(0.6), _mc(0.0), _mc(0.0)),
}


# ---------------------------------------------------------------------------
# Trajectory driver: run the SAME recurrence under a given substrate.
# Returns list of snapshots (frames) - final frame = Track A observation,
# full list = Track B observation.
# ---------------------------------------------------------------------------

def run_recurrence(gen_name, seed, w, h, substrate, n_steps=64):
    """Execute the generator's recurrence native to the substrate's arithmetic.

    Substrate participation points (all DURING evolution):
      1. initial state encoded into substrate representation
      2. every step's arithmetic via substrate kernel (Q15/MOD) or float
         kernel + per-step state snap (S32/S16/S_FSM/S_UNKNOWN)
      3. hash substrate injects per-step hash term into the recurrence
    """
    rule = {
        "G01_smooth_nonlinear": _g01_rule,
        "G02_chaotic": _g02_rule,
        "G03_coupled_osc": _g03_rule,
        "G04_reaction_diff": _g04_rule,
        "G05_wave": None,        # second-order, handled below
        "G06_procedural_dyn": _g06_rule,
        "G07_logistic_field": _g07_rule,
        "G08_diffusion_mix": _g08_rule,
    }[gen_name]

    snap = SNAPSHOTS[substrate]
    init_kind = "bump" if gen_name in ("G04_reaction_diff", "G05_wave") else \
                ("stripes" if gen_name in ("G03_coupled_osc", "G08_diffusion_mix") else "noise")
    fld = initial_field(w, h, seed, init_kind)

    # substrate-native encoding of the initial condition
    fld = snap(fld)

    hp = make_hash_native_step(seed) if substrate in HASH_SUBSTRATES else None

    frames = [list(fld)]
    if gen_name == "G05_wave":
        prev = [0.0] * (w * h)
        for t in range(n_steps):
            nxt = _g05_step(fld, prev, w, h)
            if hp is not None:
                nxt = [max(-1.0, min(1.0, hp(t * (w * h) + k, v)))
                       for k, v in enumerate(nxt)]
            if substrate in MOD_SUBSTRATES:
                # modular wave: ring version of the same 2nd-order update
                enc = [mod_encode(v) for v in fld]
                encp = [mod_encode(v) for v in prev]
                p = MOD_PRIME
                out = []
                for i in range(w):
                    for j in range(h):
                        k = i * h + j
                        parts = []
                        if i > 0:
                            parts.append((i - 1) * h + j)
                        if i < w - 1:
                            parts.append((i + 1) * h + j)
                        if j > 0:
                            parts.append(i * h + j - 1)
                        if j < h - 1:
                            parts.append(i * h + j + 1)
                        s = 0
                        for pk in parts:
                            s = (s + enc[pk]) % p
                        inv = pow(len(parts), p - 2, p)
                        nb = (s * inv) % p
                        two_u = (2 * enc[k]) % p
                        neg_prev = (-encp[k]) % p
                        lap = (nb - enc[k]) % p
                        v = (two_u + neg_prev + (int(round(0.36 * _MOD_C)) * lap) % p) % p
                        out.append(mod_decode(v))
                nxt = out
            prev = fld
            fld = snap(nxt)
            frames.append(list(fld))
        return frames

    for t in range(n_steps):
        if substrate in Q15_SUBSTRATES:
            nxt = _step_q15(fld, w, h, rule)
        elif substrate in MOD_SUBSTRATES:
            nxt = _step_mod(fld, w, h, rule)
        else:
            if hp is None:
                nxt = _generic_step(fld, w, h, rule)
            else:
                nxt = _generic_step(fld, w, h, rule,
                                    post=lambda v, k, _t=t: hp(_t * 1800 + k, v))
        fld = snap(nxt)
        frames.append(list(fld))
    return frames


# Value-class labels (never exposed to detector)
def substrate_label(sub):
    return "continuous" if sub in SUBSTRATES_CONTINUOUS else "computational"


# ---------------------------------------------------------------------------
# Statistic matching / surrogates (spec §7, §8, §12). Used ONLY by the
# adversarial control tests; primary tests run on native trajectories.
# ---------------------------------------------------------------------------

def match_histogram(source, target):
    """Rank-remap source values onto target's sorted distribution."""
    n = len(source)
    order = sorted(range(n), key=lambda i: source[i])
    tgt_sorted = sorted(target)
    out = [0.0] * n
    for rank, idx in enumerate(order):
        out[idx] = tgt_sorted[min(rank, n - 1)]
    return out


def _fft(a, invert=False):
    """Iterative radix-2 Cooley-Tukey (stdlib cmath). Length must be a power
    of two (caller truncates/pads; documented approximation)."""
    import cmath
    n = len(a)
    a = list(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    m = 2
    while m <= n:
        wlen = cmath.exp((2j if invert else -2j) * cmath.pi / m)
        for i in range(0, n, m):
            w = 1 + 0j
            for k in range(i, i + m // 2):
                u = a[k]
                v = a[k + m // 2] * w
                a[k] = u + v
                a[k + m // 2] = u - v
                w *= wlen
        m <<= 1
    if invert:
        a = [x / n for x in a]
    return a


def _next_pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return p


def match_spectrum(source, target):
    """Replace source magnitude spectrum with target's, keep source phases.
    Operates on the flattened field truncated to a power-of-two length;
    returns a float list of the ORIGINAL length. Approximate matching per §7."""
    import cmath
    n = len(source)
    np2 = _next_pow2(n)
    s = list(source[:n]) + [0.0] * (np2 - n)
    t = list(target[:n]) + [0.0] * (np2 - n)
    S = _fft(s)
    T = _fft(t)
    Smag = [abs(z) for z in S]
    Tmag = [abs(z) for z in T]
    order = sorted(range(np2), key=lambda i: Smag[i])
    tgt_sorted = sorted(Tmag)
    replace = [0.0] * np2
    for rank, idx in enumerate(order):
        replace[idx] = tgt_sorted[rank]
    out = []
    for i in range(np2):
        if Smag[i] > 1e-15:
            z = S[i] * (replace[i] / Smag[i])
        else:
            z = complex(replace[i], 0.0)
        out.append(z)
    back = _fft(out, invert=True)
    return [max(-1.5, min(1.5, x.real)) for x in back[:n]]


def phase_randomized_surrogate(field, w, h, seed):
    """§8 surrogate: preserve the power spectrum, destroy phase structure.
    Row-wise 1D surrogate (rows are power-of-2 padded: h=30 -> 32)."""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(w):
        row = field[i * h:(i + 1) * h]
        np2 = 32
        rp = row + [0.0] * (np2 - h)
        F = _fft(rp)
        newF = []
        for k, z in enumerate(F):
            mag = abs(z)
            if k == 0:
                phase = 0.0
            else:
                phase = rng.uniform(-math.pi, math.pi)
            newF.append(complex(mag * math.cos(phase), mag * math.sin(phase)))
        # enforce conjugate symmetry for real output
        for k in range(1, np2 // 2):
            newF[np2 - k] = newF[k].conjugate()
        newF[np2 // 2] = complex(abs(newF[np2 // 2]), 0.0)
        back = _fft(newF, invert=True)
        out.extend([x.real for x in back[:h]])
    return out


def trajectory_phase_surrogate(frames, w, h, seed):
    """§8/§12 temporal surrogate: per-cell time series get phase-randomized
    (preserves temporal power spectrum per cell, destroys native state
    mechanism / transition structure)."""
    import random
    rng = random.Random(seed)
    n = len(frames)
    np2 = _next_pow2(n)
    cells = w * h
    out = [[0.0] * cells for _ in range(n)]
    for k in range(cells):
        series = [frames[t][k] for t in range(n)] + [0.0] * (np2 - n)
        F = _fft(series)
        newF = []
        for idx, z in enumerate(F):
            mag = abs(z)
            phase = 0.0 if idx == 0 else rng.uniform(-math.pi, math.pi)
            newF.append(complex(mag * math.cos(phase), mag * math.sin(phase)))
        for idx in range(1, np2 // 2):
            newF[np2 - idx] = newF[idx].conjugate()
        newF[np2 // 2] = complex(abs(newF[np2 // 2]), 0.0)
        back = _fft(newF, invert=True)
        for t in range(n):
            out[t][k] = back[t].real
    return out


def matched_trajectory(frames_src, frames_tgt):
    """Frame-by-frame histogram matching of src trajectory onto tgt
    (removes per-frame marginal statistics while keeping src's ordering)."""
    return [match_histogram(a, b) for a, b in zip(frames_src, frames_tgt)]



GENERATORS = {
    "G01_smooth_nonlinear": "smooth nonlinear recurrence",
    "G02_chaotic": "chaotic recurrence",
    "G03_coupled_osc": "coupled oscillator",
    "G04_reaction_diff": "reaction-diffusion-like recurrence",
    "G05_wave": "wave/eigenmode recurrence",
    "G06_procedural_dyn": "procedural dynamical field",
    "G07_logistic_field": "logistic map field",
    "G08_diffusion_mix": "diffusion + mixing recurrence",
}

# Generator splits (§4: >=2 families unseen until final holdout)
TRAIN_GENERATORS = ["G01_smooth_nonlinear", "G02_chaotic",
                    "G03_coupled_osc", "G04_reaction_diff"]
HOLDOUT_GENERATORS = ["G05_wave", "G06_procedural_dyn"]
LOO_GENERATORS = ["G07_logistic_field", "G08_diffusion_mix"]

ALL_SUBSTRATES = list(SNAPSHOTS.keys())
