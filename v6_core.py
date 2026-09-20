"""V6 core — active black-box response-operator benchmark.

Hypothesis (different in kind from the CLOSED passive V5.x line): can hidden
computational constraints be detected from the system's RESPONSE TO CONTROLLED
INTERVENTIONS rather than from passive observation?

Honesty of the design:

* Generators are linear, constant-preserving 3x3 stencils (integer weights /16,
  sum == 16) on a torus. A *constant* field is an exact fixed point.
* Every computational mechanism only re-represents the DEVIATION from that
  constant and fixes deviation == 0, so the unperturbed baseline is BITWISE
  IDENTICAL across mechanisms -> the baseline-matched null (C6) is verifiable at
  chance, not assumed.
* The only difference is how an injected perturbation propagates = the RESPONSE
  OPERATOR. Continuous mechanisms are exactly linear and live in an uncountable
  state space (superposition holds, responses never repeat exactly, response
  space is full-rank). Computational mechanisms quantise the deviation onto a
  finite lattice -> measurable superposition error, exact response recurrence,
  response-space collapse and collisions.

No post-hoc histogram/spectrum/rank matching or phase scrambling is used (spec
§6): the intervention is the causal probe. stdlib-only, deterministically seeded.
"""
import zlib

# ---- configuration -------------------------------------------------------
W, H = 16, 16
N = W * H
N_STEPS = 24
BASELINE = 1.0
BASE_SEED = 20260920

# generators: 3x3 stencil, integer weights /16 (sum == 16 -> constant fixed point,
# dyadic -> exactly representable so an "independent implementation" of the same
# system reproduces bitwise-identical responses).
GENERATORS = {
    "G01_isotropic":   (16, [[0, 1, 0], [1, 12, 1], [0, 1, 0]]),   # mild diffusion
    "G02_anisotropic": (16, [[0, 0, 0], [4, 8, 4], [0, 0, 0]]),   # horizontal only
    "G03_drift":       (16, [[0, 0, 8], [0, 8, 0], [0, 0, 0]]),   # advection (persists)
    "G04_sustained":   (16, [[0, 0, 0], [1, 14, 1], [0, 0, 0]]),  # near-identity + spread
}
TRAIN_GENERATORS = ["G01_isotropic", "G02_anisotropic"]
HOLDOUT_GENERATORS = ["G03_drift", "G04_sustained"]
ALL_GENERATORS = TRAIN_GENERATORS + HOLDOUT_GENERATORS

TRAIN_MECHANISMS = ["fixed_point", "finite_state"]   # known computational
UNSEEN_MECHANISMS = ["modular", "unknown_trunc"]     # held-out mechanism (C5)
ALL_COMPUTATIONAL = TRAIN_MECHANISMS + UNSEEN_MECHANISMS
CONTINUOUS_MECHS = ["continuous", "continuous_alt"]

# Feature groups (spec §3 / §7 / core rule).
# The GATED signal must be carried by the response OPERATOR, not by ordinary
# response amplitudes (which a linear observer also sees). So the primary set
# excludes magnitude-family features.
ALGEBRA_FEATS = ["superposition_err", "superposition_path", "symmetry_err",
                 "composition_err", "path_dependence", "repeatability_err"]
STRUCT_FEATS = ["recurrence", "collision", "eff_rank"]
AMPLITUDE_FEATS = ["mag_final", "energy", "decay", "locality", "speed"]
OPERATOR_FEATS = ALGEBRA_FEATS + STRUCT_FEATS
RESPONSE_FEATS = OPERATOR_FEATS + AMPLITUDE_FEATS
BASELINE_FEATS = ["b_mean", "b_var", "b_min", "b_max", "b_range"]
# roles that carry a whole trajectory (permutable intervention identities)
TRAJ_ROLES = ["single", "opposite", "A", "B", "AB", "C", "ABC",
              "ABthenC", "far", "small", "large"]


def stable_seed(gen, off):
    return (BASE_SEED + off * 1000 + zlib.crc32(gen.encode())) % (2 ** 31)


# ---- linear operator (acts on deviation field; constant-preserving) ------
def apply_operator(dev, denom, kern, rev=False):
    """3x3 stencil, torus. rev=True reverses tap accumulation order only ->
    a mathematically identical but independently written implementation (C1)."""
    taps = [(a, b, kern[a + 1][b + 1])
            for a in (-1, 0, 1) for b in (-1, 0, 1) if kern[a + 1][b + 1]]
    if rev:
        taps = taps[::-1]
    out = [0.0] * N
    for j in range(H):
        for i in range(W):
            acc = 0.0
            for a, b, wgt in taps:
                acc += wgt * dev[((j + a) % H) * W + ((i + b) % W)]
            out[j * W + i] = acc / denom
    return out


# ---- mechanisms: finite-lattice re-representation of the deviation --------
def mech_identity(dev):
    return dev                                   # continuous: exact linear step


def _snap(x, s):
    return round(x / s) * s


def mech_fixed_point(dev):
    s = 0.008                                    # uniform lattice, nearest rounding
    return [_snap(x, s) for x in dev]


def mech_finite_state(dev):
    levels, span = 21, 1.0                       # coarse finite alphabet incl. 0
    step = (2 * span) / (levels - 1)
    out = []
    for x in dev:
        k = max(0, min(levels - 1, round((x + span) / step)))
        out.append(-span + k * step)
    return out


def mech_modular(dev):
    s = 0.05                                     # coarser lattice; periodic fold only
    out = []                                     # beyond a wide bound (collisions)
    for x in dev:
        r = _snap(x, s)
        if abs(r) > 0.6:
            r = _snap(((r + 0.6) % 1.2) - 0.6, s)
        out.append(r)
    return out


def mech_unknown_trunc(dev):
    # NEW held-out mechanism: finite binary MANTISSA (relative precision limit,
    # like a shortened float format). Keeps 0 fixed, preserves amplitude at every
    # scale (never collapses), and is nonlinear under superposition because two
    # different-amplitude deviations quantise on different exponent grids.
    import math
    k = 5
    out = []
    for x in dev:
        if x == 0.0:
            out.append(0.0)
            continue
        m, e = math.frexp(x)                       # m in [0.5,1), x = m*2**e
        m = math.ldexp(math.floor(math.ldexp(m, k)), -k)   # truncate mantissa to k bits
        out.append(math.ldexp(m, e))
    return out


def mech_cont_nonlinear(dev):
    # CONTINUOUS (uncountable-state) but NON-ADDITIVE probe. Fixes 0 (baseline stays
    # bitwise identical) and is odd (preserves +P/-P symmetry), yet f(x+y) != f(x)+f(y).
    # A genuine nonlinearity with no finite lattice, no exact recurrence and no
    # collisions -> if it is classified as 'computational' the detector is measuring
    # non-additivity, not computation.
    return [x / (1.0 + abs(x)) for x in dev]


def mech_finite_additive(dev):
    # FINITE representation (bounded 40-bit mantissa lattice) whose truncation is
    # lossless across the whole probing window, so the step map stays additive to
    # ~1e-12: superposition/recurrence/collapse are indistinguishable from the
    # continuous reference. Isolates 'finiteness without measurable non-additivity'.
    import math
    k = 40
    out = []
    for x in dev:
        if x == 0.0:
            out.append(0.0)
            continue
        m, e = math.frexp(x)
        m = math.ldexp(math.floor(math.ldexp(m, k)), -k)
        out.append(math.ldexp(m, e))
    return out


MECHANISMS = {
    "continuous": mech_identity,
    "continuous_alt": mech_identity,
    "fixed_point": mech_fixed_point,
    "finite_state": mech_finite_state,
    "modular": mech_modular,
    "unknown_trunc": mech_unknown_trunc,
    "cont_nonlinear": mech_cont_nonlinear,
    "finite_additive": mech_finite_additive,
}

# Adversarial probes (spec §9 falsifiability). These are NEVER used to train the
# primary detector nor included in ALL_COMPUTATIONAL / CONTINUOUS_MECHS; they are
# held-out characterisation cells that decouple the class LABEL from the measured
# PROPERTY. Together they test whether the response operator keys on non-additivity
# (a real dynamical property) or merely on the pre-assigned computational label.
#
#   cont_nonlinear : UNCOUNTABLE state (continuous) but NON-ADDITIVE -> if the
#                    detector calls it "computational" the signature is of
#                    non-additivity, not of computation/finiteness (false positive).
#   finite_additive: bounded finite representation (40-bit lattice) whose truncation
#                    is lossless within the probing window -> superposition holds to
#                    ~1e-12; a valid detector cannot separate it from continuous
#                    (finiteness below intervention resolution is invisible).
ADVERSARIAL_MECHS = ["cont_nonlinear", "finite_additive"]


def _is_alt(mech):
    return mech == "continuous_alt"


# ---- forward evolution of one injected perturbation ----------------------
def _evolve(dev0, gen, mech, n_steps=N_STEPS, start_offset=0, staged=None):
    step_fn = MECHANISMS[mech]
    denom, kern = GENERATORS[gen]
    rev = _is_alt(mech)
    dev = [0.0] * N
    traj = []
    for t in range(n_steps + 1):
        if t == start_offset:
            dev = list(dev0)
        elif t > start_offset:
            dev = step_fn(apply_operator(dev, denom, kern, rev))
            if staged and t == staged[2]:
                dev = list(dev)
                dev[staged[0]] += staged[1]
        traj.append(dev)
    return traj


# ---- vector helpers ------------------------------------------------------
def _norm(v):
    return sum(x * x for x in v) ** 0.5


def _add(a, b):
    return [x + y for x, y in zip(a, b)]


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _final(traj):
    return traj[-1]


def _cell(x, y):
    return y * W + x


# ---- the fixed intervention battery --------------------------------------
def _dev_from(pert):
    v = [0.0] * N
    for c, a in pert:
        v[c] += a
    return v


def make_battery():
    A = _cell(7, 7)
    Cp = _cell(9, 9)          # separate site for composition / locality tests
    Far = _cell(1, 14)
    d = 0.5
    # UNEQUAL collinear amplitudes so the sum a+b is NOT a power-of-two multiple
    # of either part -> breaks the exact degree-1 homogeneity of finite-mantissa
    # truncation while keeping the test a pure linearity probe. Linear systems
    # still give exactly 0; ANY finite-lattice / finite-precision quantiser is
    # non-additive here regardless of spatial overlap -> generator-independent.
    a, b = 0.5, 0.3
    return {
        "single":    [(A, +d)],
        "opposite":  [(A, -d)],
        "A_only":     [(A, +a)],
        "B_only":     [(A, +b)],
        "two_simult": [(A, a + b)],
        "C_only":     [(Cp, +d)],
        "ABC":        [(A, a + b), (Cp, +d)],
        "far":        [(Far, +d)],
        "small":      [(A, 0.05)],
        "large":      [(A, 1.0)],
        "late":       [(A, +d)],
        "amp1":       [(A, 0.07)],
        "amp2":       [(A, 0.11)],
        "amp3":       [(A, 0.16)],
    }


def response_of(gen, mech, pert, start_offset=0, staged=None):
    return _evolve(_dev_from(pert), gen, mech, start_offset=start_offset, staged=staged)


# ---- response-operator features (spec §3) --------------------------------
# The battery is run once and its named response trajectories are returned so
# the pipeline can REASSEMBLE features under controls that intervene on the
# intervention->response pairing (C2 permutation, C3 surrogate) without ever
# applying post-hoc transforms to the measured responses themselves (spec §6).
def battery_responses(gen, mech, seed):
    bat = make_battery()
    R = {}
    R["single"] = response_of(gen, mech, bat["single"])
    R["opposite"] = response_of(gen, mech, bat["opposite"])
    R["late"] = response_of(gen, mech, bat["late"], start_offset=8)  # different time
    R["rep1"] = response_of(gen, mech, bat["single"])
    R["rep2"] = response_of(gen, mech, bat["single"])
    R["A"] = response_of(gen, mech, bat["A_only"])
    R["B"] = response_of(gen, mech, bat["B_only"])
    R["AB"] = response_of(gen, mech, bat["two_simult"])
    R["C"] = response_of(gen, mech, bat["C_only"])
    R["ABC"] = response_of(gen, mech, bat["ABC"])
    R["ABthenC"] = response_of(gen, mech, bat["two_simult"],
                               staged=(_cell(9, 9), 0.5, 8))          # staged 2nd pulse
    R["far"] = response_of(gen, mech, bat["far"])
    R["small"] = response_of(gen, mech, bat["small"])
    R["large"] = response_of(gen, mech, bat["large"])
    R["coll"] = [response_of(gen, mech, [(_cell(6, 6), a)])
                 for a in (0.04, 0.06, 0.09, 0.12, 0.2, 0.3, 0.4, 0.6)]
    return R


def features_from_responses(R):
    """Pure assembly of the response-operator feature vector from named response
    trajectories. No generator/mechanism access -> controls can feed it permuted
    or surrogate responses to break the causal pairing (spec §5 C2/C3)."""
    single = R["single"]
    f = {}
    # magnitude / decay / locality / propagation speed from the canonical response
    norms = [_norm(r) for r in single]
    f["mag_final"] = norms[-1]
    f["energy"] = sum(norms)
    n0 = norms[1] if norms[1] > 1e-12 else 1e-12
    f["decay"] = norms[-1] / n0
    ax, ay = 6, 6
    fin = single[-1]
    near = sum(abs(x) for k, x in enumerate(fin)
               if max(abs(k % W - ax), abs(k // W - ay)) <= 3)
    tot = sum(abs(x) for x in fin) + 1e-12
    f["locality"] = near / tot
    f["speed"] = max((max(abs(k % W - ax), abs(k // W - ay))
                      for k, x in enumerate(fin) if abs(x) > 1e-4), default=0)

    rA, rB, rAB, rC, rABC = R["A"], R["B"], R["AB"], R["C"], R["ABC"]
    # SUPERPOSITION error  R(A+B) - R(A) - R(B)   (continuous linear -> ~0)
    denAB = _norm(_final(rAB)) + 1e-12
    f["superposition_err"] = _norm(_sub(_final(rAB), _add(_final(rA), _final(rB)))) / denAB
    # full-trajectory superposition error (pathwise, not just final state)
    f["superposition_path"] = sum(
        _norm(_sub(rAB[t], _add(rA[t], rB[t]))) for t in range(len(rAB))
    ) / (sum(_norm(rAB[t]) for t in range(len(rAB))) + 1e-12)

    # response SYMMETRY  R(+P) vs -R(-P)
    f["symmetry_err"] = _norm(_add(_final(single), _final(R["opposite"]))) / (_norm(_final(single)) + 1e-12)

    # path dependence: simultaneous ABC vs staged (AB) then C
    f["path_dependence"] = _norm(_sub(_final(rABC), _final(R["ABthenC"]))) / (_norm(_final(rABC)) + 1e-12)
    # composition / associativity error: R(A+B+C) vs R(A+B)+R(C)
    sum_parts = _add(_final(rAB), _final(rC))
    f["composition_err"] = _norm(_sub(_final(rABC), sum_parts)) / (_norm(_final(rABC)) + 1e-12)

    # repeatability (deterministic -> ~0)
    f["repeatability_err"] = _norm(_sub(_final(R["rep1"]), _final(R["rep2"])))

    # EXACT recurrence of the response state along ONE trajectory, ignoring the
    # settled-to-equilibrium tail (finite state space -> exact revisits; continuous
    # -> asymptotic decay that never repeats exactly).
    seen, rec, tot2 = set(), 0, 0
    for r in single:
        if _norm(r) <= 1e-6:
            continue
        tot2 += 1
        key = tuple(round(x, 9) for x in r)
        if key in seen:
            rec += 1
        seen.add(key)
    f["recurrence"] = rec / tot2 if tot2 else 0.0

    # collision: distinct-amplitude single-cell interventions mapping to
    # identical final responses (finite response set -> merges)
    finals = [_final(t) for t in R["coll"]]
    merged = 0
    flagged = [False] * len(finals)
    for i in range(len(finals)):
        if flagged[i]:
            continue
        for j in range(i + 1, len(finals)):
            if not flagged[j] and _norm(_sub(finals[i], finals[j])) < 1e-9:
                flagged[j] = True
                merged += 1
    f["collision"] = merged / len(finals)

    # effective rank of the response space spanned by the battery finals
    mat = [_final(single), _final(R["opposite"]), _final(rAB), _final(rC),
           _final(rABC), _final(R["far"]), _final(R["small"]), _final(R["large"])]
    f["eff_rank"] = _numeric_rank(mat) / len(mat)
    return f


def compute_response_features(gen, mech, seed):
    return features_from_responses(battery_responses(gen, mech, seed))


def _numeric_rank(rows, eps=1e-9):
    m = [list(r) for r in rows]
    nr, nc = len(m), len(m[0])
    rank = 0
    pr = 0
    for col in range(nc):
        if pr >= nr:
            break
        piv = max(range(pr, nr), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < eps:
            continue
        m[pr], m[piv] = m[piv], m[pr]
        pv = m[pr][col]
        for r in range(pr + 1, nr):
            fac = m[r][col] / pv
            if fac:
                for c in range(col, nc):
                    m[r][c] -= fac * m[pr][c]
        pr += 1
        rank += 1
    return rank


# ---- baseline (pre-intervention) observation features (must stay at chance) --
def baseline_features(gen, mech, seed):
    vals = [BASELINE] * N
    mean = sum(vals) / N
    var = sum((x - mean) ** 2 for x in vals) / N
    return {"b_mean": mean, "b_var": var, "b_min": min(vals),
            "b_max": max(vals), "b_range": max(vals) - min(vals)}
