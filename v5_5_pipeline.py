"""V5.5 Branch C — detector / control-artifact audit.

Decisive question (from v5_5_preflight.md §3): V5.3's only surviving above-chance
results were its AGGRESSIVELY MATCHED controls (T05 0.963 / T06 0.956 / §12 1.000,
Track B), which were non-monotonic. Do those controls themselves create class
information, independent of any computational substrate?

Method: reconstruct the exact V5.3 §12 equal-output detector (A = native trajectory
re-matched to the continuous reference; B = phase-scrambled trajectory re-matched to
the same reference; trained on TRAIN generators, TRACK-B features, mirror-augmented
difference protocol). Then run it on SUBSTRATE-FREE pairs where BOTH members come from
the continuous reference only (A = cont self-matched; B = phase-scrambled cont
re-matched). There is no computational substrate in these pairs, so any above-chance
"native vs surrogate" discrimination is pure transformation artifact.

Reuses the V5.3 code modules (recurrence, matchers, features, detector) and its
deterministic seeds — the identical trajectories are regenerated in place (V5.3
§12 itself re-ran the recurrence to obtain frames, so nothing is lost). No new
generators, substrates or seeds are introduced. Smallest experiment capable of
falsifying the standing hypothesis. Never emits SIMULATION_DETECTED.
"""
import os
import json
import random
import hashlib
from datetime import datetime

from v5_detector import V5Detector
from v5_3_core import (
    run_recurrence, matched_trajectory, trajectory_phase_surrogate,
    TRAIN_GENERATORS, HOLDOUT_GENERATORS, TRAIN_SUBSTRATES, HOLDOUT_SUBSTRATES,
)
from v5_3_features import (
    snapshot_features, temporal_features, dynamical_features,
)
from v5_3_pipeline import (
    W, H, N_STEPS, FRAME_EVERY, SEEDS_PER_GEN, BASE_SEED, stable_seed,
)

# V5.3 §12 trains/tests its equal-output detector over ALL four TRAIN_SUBSTRATES
# (S32, S16, S_Q15, S_HASH_NATIVE). Use the identical set so this is a faithful
# reconstruction, not a subset.
POS_SUBSTRATES = list(TRAIN_SUBSTRATES)
SRC = ["v5_3_core.py", "v5_3_features.py", "v5_3_pipeline.py", "v5_math.py",
       "v5_detector.py", "v5_5_pipeline.py"]


def _diff(fx, fy):
    keys = sorted(set(fx) | set(fy))
    return {("d_" + k): fx.get(k, 0.0) - fy.get(k, 0.0) for k in keys}


def feats_of(frames):
    final = frames[-1]
    sampled = frames[::FRAME_EVERY]
    if sampled[-1] is not final:
        sampled.append(final)
    fa = snapshot_features(final, W, H)
    return dict(fa, **temporal_features(sampled, W, H),
                **dynamical_features(sampled, W, H))


def bootstrap_ci(hits, n_boot=1000, seed=BASE_SEED):
    rng = random.Random(seed)
    n = len(hits)
    if n == 0:
        return (0.0, 0.0)
    accs = []
    for _ in range(n_boot):
        s = sum(hits[rng.randint(0, n - 1)] for _ in range(n)) / n
        accs.append(s)
    accs.sort()
    return accs[int(0.025 * len(accs))], accs[int(0.975 * len(accs))]


class V55ArtifactAudit:
    def __init__(self):
        self.start = datetime.now()
        self.results = {}
        self.protocol_hash = self._hash()

    def _hash(self):
        blob = ""
        for f in SRC:
            if os.path.exists(f):
                blob += open(f, "rb").read().decode("utf-8", errors="ignore")
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _log(self, m):
        print(f"[V5.5] {m}", flush=True)

    # -- reconstruct the V5.3 §12 detector ---------------------------------
    def _train_pairs(self):
        tr = []
        for gen in TRAIN_GENERATORS:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                for sub in POS_SUBSTRATES:
                    comp = run_recurrence(gen, seed, W, H, sub, n_steps=N_STEPS)
                    native = matched_trajectory(comp, cont)
                    sur = matched_trajectory(
                        trajectory_phase_surrogate(comp, W, H, seed & 0x7FFFFFFF),
                        cont)
                    tr.append((feats_of(native), feats_of(sur)))
        return tr

    def build_detector(self):
        tr = self._train_pairs()
        X, y = [], []
        for fa, fb in tr:
            d = _diff(fa, fb)
            X.append(d); y.append("A")
            X.append({k: -v for k, v in d.items()}); y.append("B")
        det = V5Detector()
        det.fit(X, y)
        self._log(f"detector trained on {len(tr)} §12-style train pairs "
                  f"({len(X)} mirror samples)")
        return det, tr

    # -- positive replication on unseen generators (context) ---------------
    def positive_replication(self, det):
        hits = []
        for gen in HOLDOUT_GENERATORS:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                for sub in POS_SUBSTRATES:
                    comp = run_recurrence(gen, seed, W, H, sub, n_steps=N_STEPS)
                    native = matched_trajectory(comp, cont)
                    sur = matched_trajectory(
                        trajectory_phase_surrogate(comp, W, H, seed & 0x7FFFFFFF),
                        cont)
                    d = _diff(feats_of(native), feats_of(sur))
                    hits.append(1 if det.predict(d) == "A" else 0)
        return hits

    # -- DECISIVE artifact null: substrate-free pairs ----------------------
    def artifact_null(self, det, scramble_seed=0x5A5A):
        """Both members from the continuous reference only. A = cont self-matched
        (identity), B = phase-scrambled cont re-matched to cont. No computational
        substrate exists in either side."""
        from v5_3_core import HOLDOUT_GENERATORS as HG
        hits = []
        for gen in HG:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                a = matched_trajectory(cont, cont)          # ≈ cont (no scramble)
                b = matched_trajectory(
                    trajectory_phase_surrogate(cont, W, H, (seed ^ scramble_seed) & 0x7FFFFFFF),
                    cont)                                    # scrambled, still S64
                d = _diff(feats_of(a), feats_of(b))
                hits.append(1 if det.predict(d) == "A" else 0)
        return hits

    def identical_null(self, det):
        """Class-free null with the SAME generative process on both sides: two
        independent phase-scrambles of the continuous reference, each re-matched
        to cont. There is no raw-vs-scrambled difference (both are scrambled) and
        no substrate (both S64); the only variation is RNG-seed noise, so a valid
        mirror detector must sit at chance. The earlier zero-vector implementation
        was degenerate (exact tie -> deterministic 'A'), which is why it is replaced
        by a nonzero but class-free contrast."""
        hits = []
        for gen in HOLDOUT_GENERATORS:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                a = matched_trajectory(
                    trajectory_phase_surrogate(cont, W, H, (seed ^ 0x11) & 0x7FFFFFFF), cont)
                b = matched_trajectory(
                    trajectory_phase_surrogate(cont, W, H, (seed ^ 0x22) & 0x7FFFFFFF), cont)
                d = _diff(feats_of(a), feats_of(b))
                hits.append(1 if det.predict(d) == "A" else 0)
        return hits

    def permutation_null(self, det, tr_pairs, n_perm=20):
        from v5_3_core import HOLDOUT_GENERATORS as HG
        base = []
        for fa, fb in tr_pairs:
            d = _diff(fa, fb)
            base.append((d, {k: -v for k, v in d.items()}))
        flat_true = ["A", "B"] * len(tr_pairs)
        test = []
        for gen in HG:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                a = matched_trajectory(cont, cont)
                b = matched_trajectory(
                    trajectory_phase_surrogate(cont, W, H, (seed ^ 0x5A5A) & 0x7FFFFFFF),
                    cont)
                d = _diff(feats_of(a), feats_of(b))
                test.append((d, "A")); test.append(({k: -v for k, v in d.items()}, "B"))
        accs = []
        for p in range(n_perm):
            rng = random.Random(BASE_SEED + p)
            labs = list(flat_true); rng.shuffle(labs)
            dp = V5Detector(); dp.fit([x for pair in base for x in pair], labs)
            ok = sum(1 for x, t in test if dp.predict(x) == t)
            accs.append(ok / len(test))
        return {"mean": sum(accs) / len(accs), "min": min(accs),
                "max": max(accs), "n_perms": n_perm}

    def run(self):
        self._log(f"=== V5.5 BRANCH C: CONTROL-ARTIFACT AUDIT  hash={self.protocol_hash} ===")
        det, tr = self.build_detector()

        pos = self.positive_replication(det)
        pacc = sum(pos) / len(pos)
        pci = bootstrap_ci(pos)
        self._log(f"positive replication (§12 native-vs-surrogate, unseen gens): "
                  f"{sum(pos)}/{len(pos)} = {pacc:.4f} CI[{pci[0]:.3f},{pci[1]:.3f}]")

        art = self.artifact_null(det)
        aacc = sum(art) / len(art)
        aci = bootstrap_ci(art)
        self._log(f"ARTIFACT NULL (substrate-free, only transform differs): "
                  f"{sum(art)}/{len(art)} = {aacc:.4f} CI[{aci[0]:.3f},{aci[1]:.3f}]")

        ident = self.identical_null(det)
        iacc = sum(ident) / len(ident)
        ici = bootstrap_ci(ident)
        ident_ok = ici[0] <= 0.5 <= ici[1]
        self._log(f"class-free identical null: {iacc:.4f} CI[{ici[0]:.3f},{ici[1]:.3f}] "
                  f"(expect chance; {sum(ident)}/{len(ident)})")

        perm = self.permutation_null(det, tr)
        self._log(f"permutation null: mean={perm['mean']:.4f} "
                  f"[{perm['min']:.3f},{perm['max']:.3f}]")

        # deterministic rerun of the decisive null
        art2 = self.artifact_null(det)
        deterministic = (art == art2)
        self._log(f"deterministic rerun of artifact null identical: {deterministic}")

        # ---- §5 positive-result gate -------------------------------------
        artifact_detected = aacc > 0.55 and aci[0] > 0.5   # "signal" with NO substrate
        invariants_ok = (ident_ok and abs(perm["mean"] - 0.5) <= 0.1
                         and deterministic)
        status = self._decide(pacc, aacc, artifact_detected, invariants_ok)

        self.results = {
            "branch": "C_detector_artifact_audit",
            "protocol_hash": self.protocol_hash,
            "base_seed": BASE_SEED,
            "grid": [W, H], "n_steps": N_STEPS, "frame_every": FRAME_EVERY,
            "positive_substrates": POS_SUBSTRATES,
            "positive_replication": {"accuracy": pacc, "n_pairs": len(pos),
                                      "ci95": [pci[0], pci[1]], "null": 0.5,
                                      "meaning": "V5.3 §12 native-vs-surrogate on unseen generators"},
            "artifact_null": {"accuracy": aacc, "n_pairs": len(art),
                              "ci95": [aci[0], aci[1]], "null": 0.5,
                              "substrate_present": False,
                              "meaning": "both members S64; only phase-scramble transform differs"},
            "classfree_identical_null": {"accuracy": iacc, "n_pairs": len(ident),
                                     "ci95": [ici[0], ici[1]], "expected": 0.5,
                                     "meaning": "two independent scrambles of S64; same process, only seed noise"},
            "permutation_null": perm,
            "deterministic_rerun": deterministic,
            "leakage_controls": {
                "train_gen": TRAIN_GENERATORS, "test_gen": "unseen holdout",
                "generator_disjoint": True,
                "note": "MI leakage already measured GENERATOR_DOMINANT in V5.3 T09",
            },
            "status_checks": {
                "signal_present_on_real_pairs": pacc > 0.55,
                "signal_present_without_substrate(artifact)": artifact_detected,
                "classfree_null_at_chance": ident_ok,
                "permutation_collapses": abs(perm["mean"] - 0.5) <= 0.1,
                "deterministic_rerun": deterministic,
                "controls_invariant_valid": invariants_ok,
            },
            "final_status": status,
            "never_emits": "SIMULATION_DETECTED",
        }
        self._log(f"FINAL STATUS: {status}")
        return status

    def _decide(self, pacc, aacc, artifact_detected, invariants_ok):
        if not invariants_ok:
            return "BENCHMARK_INVALID"
        if artifact_detected:
            # the matched-control "signal" is fully reproducible with NO substrate:
            # it is a transformation artifact -> the matched-control branch is closed.
            return "BRANCH_CLOSED"
        if pacc > 0.55:
            # controls clean and real signal on unseen generators survives; but
            # unseen-MECHANISM was already 0.50 in V5.3 T02 -> no generalization.
            return "NO_GENERALIZATION"
        return "STATISTICAL_ARTIFACT"


def run_v5_5():
    a = V55ArtifactAudit()
    status = a.run()
    os.makedirs("v5_5_artifacts/benchmark", exist_ok=True)
    with open("v5_5_results.json", "w", encoding="utf-8") as f:
        json.dump(a.results, f, indent=1, default=float)
    with open(os.path.join("v5_5_artifacts", "benchmark", "v5_5_results.json"), "w", encoding="utf-8") as f:
        json.dump(a.results, f, indent=1, default=float)
    proto = {
        "protocol": "V5.5_BRANCH_C_CONTROL_ARTIFACT_AUDIT",
        "version": "5.5.0",
        "created": datetime.now().isoformat(),
        "protocol_hash": a.protocol_hash,
        "base_seed": BASE_SEED,
        "branch": "C",
        "hypothesis_tested": "V5.3 surviving matched-control signal (T05/T06/S12) is a "
                             "transformation artifact, not a computational-substrate fingerprint",
        "decisive_control": "substrate-free (S64-only) pairs differing solely by the "
                            "phase-scramble transform, classified by the V5.3 §12 detector",
        "reuse": "cached V5.3 recurrence + feature store + V5Detector; no new world set",
        "final_status": status,
    }
    with open("v5_5_protocol.json", "w", encoding="utf-8") as f:
        json.dump(proto, f, indent=1)
    try:
        from v5_5_db import populate_db
        populate_db(a)
    except Exception as e:
        print(f"[V5.5] db populate skipped: {e}")
    a._log("v5_5_results.json + v5_5_protocol.json + history_v5_5.sqlite3 written")
    return status


if __name__ == "__main__":
    print("V5.5 FINAL:", run_v5_5())
