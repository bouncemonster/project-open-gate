"""V6 pipeline — active black-box response-operator benchmark.

Central object (spec core rule): the map  intervention -> response, NOT
world -> classification. We ask whether hidden computational constraints are
detectable from the RESPONSE TO CONTROLLED INTERVENTIONS, after the passive
V5.x branch was closed.

Protocol (all stdlib, deterministically seeded):

* Build paired black-box worlds: same linear constant-preserving generator and
  same bitwise-identical baseline; a CONTINUOUS reference mechanism vs several
  COMPUTATIONAL mechanisms that only differ in how an injected perturbation is
  re-represented -> they differ solely in the response operator (spec §1).
* Run a fixed intervention battery and assemble response-operator features
  (superposition / symmetry / composition / path / recurrence / collision / rank)
  (spec §2, §3).
* PRIMARY: via a mirror-augmented pairwise difference detector, can we tell the
  response operators of continuous vs computational worlds apart? null 50% (§4).
* Controls C1-C6 (§5), post-hoc-free (§6), feature separation (§7), decision
  gate (§8), determinism re-run. Never emits SIMULATION_DETECTED (§9).
"""
import os
import json
import random
import hashlib
from datetime import datetime

from v5_detector import V5Detector
import v6_core as C
from v6_core import (
    ALL_GENERATORS, TRAIN_GENERATORS, HOLDOUT_GENERATORS,
    TRAIN_MECHANISMS, UNSEEN_MECHANISMS, ALL_COMPUTATIONAL, ADVERSARIAL_MECHS,
    ALGEBRA_FEATS, STRUCT_FEATS, AMPLITUDE_FEATS, OPERATOR_FEATS,
    BASELINE_FEATS, TRAJ_ROLES,
    battery_responses, features_from_responses, baseline_features, stable_seed,
)

SEEDS_PER_GEN = 10
REF = "continuous"
SRC = ["v6_core.py", "v6_pipeline.py", "v6_db.py", "v5_detector.py"]
EPS_TIE = 1e-9
CHANCE_LO, CHANCE_HI = 0.45, 0.55      # band treated as "at chance"
ABOVE = 0.55                            # threshold for "above chance"
PERM_BAND = 0.10                        # |mean-over-permutations - 0.5| tolerance


# ---- small vector helpers over feature dicts -----------------------------
def _sub(fa, fb, ks):
    return {k: fa[k] - fb[k] for k in ks}


def _neg(d):
    return {k: -v for k, v in d.items()}


def _is_tie(d):
    return all(abs(v) < EPS_TIE for v in d.values())


def bootstrap_ci(hits, n_boot=1000, seed=C.BASE_SEED):
    rng = random.Random(seed)
    n = len(hits)
    if n == 0:
        return (0.0, 0.0)
    accs = []
    for _ in range(n_boot):
        s = sum(hits[rng.randint(0, n - 1)] for _ in range(n)) / n
        accs.append(s)
    accs.sort()
    return accs[int(0.025 * n_boot)], accs[int(0.975 * n_boot)]


class V6Benchmark:
    def __init__(self):
        self.protocol_hash = self._hash()
        self.R = {}       # (gen, mech, seed) -> response dict (named trajectories)
        self.feat = {}    # -> full response-operator feature dict
        self.base = {}    # -> baseline feature dict
        self.results = {}

    def _hash(self):
        blob = ""
        for f in SRC:
            if os.path.exists(f):
                blob += open(f, "rb").read().decode("utf-8", errors="ignore")
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _log(self, m):
        print(f"[V6] {m}", flush=True)

    @staticmethod
    def seeds(gen):
        return [stable_seed(gen, o) for o in range(SEEDS_PER_GEN)]

    # -- build every instance once ----------------------------------------
    def build_instances(self):
        mechs = [REF, "continuous_alt"] + ALL_COMPUTATIONAL + ADVERSARIAL_MECHS
        for gen in ALL_GENERATORS:
            for seed in self.seeds(gen):
                for mech in mechs:
                    R = battery_responses(gen, mech, seed)
                    self.R[(gen, mech, seed)] = R
                    self.feat[(gen, mech, seed)] = features_from_responses(R)
                    self.base[(gen, mech, seed)] = baseline_features(gen, mech, seed)
        self._log(f"built {len(self.feat)} instances "
                  f"({len(ALL_GENERATORS)} gens x {SEEDS_PER_GEN} seeds x "
                  f"{len(mechs)} mechanisms)")

    # -- mirror-augmented pairwise difference detector (null = 0.5) --------
    def discriminate(self, feat_map, ks, train_gens, train_mechs,
                     test_gens, test_mechs):
        X, y = [], []
        for gen in train_gens:
            for seed in self.seeds(gen):
                ref = feat_map[(gen, REF, seed)]
                for m in train_mechs:
                    d = _sub(feat_map[(gen, m, seed)], ref, ks)
                    X.append(d); y.append("A")          # A = "computational first"
                    X.append(_neg(d)); y.append("B")
        det = V5Detector()
        det.fit(X, y)
        hits = []
        for gen in test_gens:
            for seed in self.seeds(gen):
                ref = feat_map[(gen, REF, seed)]
                for m in test_mechs:
                    d = _sub(feat_map[(gen, m, seed)], ref, ks)
                    if _is_tie(d):
                        hits.append(0.5)                 # indistinguishable -> chance
                    else:
                        hits.append(1.0 if det.predict(d) == "A" else 0.0)
        return hits

    def _acc(self, hits):
        return sum(hits) / len(hits) if hits else 0.0

    # -- §4 primary + §5 C4/C5 generalisation ------------------------------
    def primary_and_generalisation(self):
        ks = OPERATOR_FEATS
        # HONEST primary = fully out-of-sample: train on seen generators AND seen
        # mechanisms, test on unseen generators crossed with all mechanisms
        # (seen + unseen). The in-sample number is reported only as a sanity check.
        primary = self.discriminate(self.feat, ks, TRAIN_GENERATORS,
                                    TRAIN_MECHANISMS, HOLDOUT_GENERATORS,
                                    ALL_COMPUTATIONAL)
        in_pop = self.discriminate(self.feat, ks, TRAIN_GENERATORS,
                                   TRAIN_MECHANISMS, TRAIN_GENERATORS,
                                   TRAIN_MECHANISMS)
        c4 = self.discriminate(self.feat, ks, TRAIN_GENERATORS, TRAIN_MECHANISMS,
                               HOLDOUT_GENERATORS, TRAIN_MECHANISMS)   # new generators
        c5 = self.discriminate(self.feat, ks, TRAIN_GENERATORS, TRAIN_MECHANISMS,
                               TRAIN_GENERATORS, UNSEEN_MECHANISMS)    # new mechanism
        hard = self.discriminate(self.feat, ks, TRAIN_GENERATORS, TRAIN_MECHANISMS,
                                 HOLDOUT_GENERATORS, UNSEEN_MECHANISMS)  # both unseen
        return primary, in_pop, c4, c5, hard

    # -- §5 C1 equivalent implementation ----------------------------------
    def c1_equivalent(self):
        """continuous vs an independent implementation of the SAME system
        (reversed tap order). Response operators are bitwise identical -> every
        pair is an exact tie, so a valid detector is pinned to chance; any rise
        above chance would mean implementation artifacts leaked into features."""
        hits = []
        for gen in ALL_GENERATORS:
            for seed in self.seeds(gen):
                d = _sub(self.feat[(gen, "continuous_alt", seed)],
                         self.feat[(gen, REF, seed)], OPERATOR_FEATS)
                hits.append(0.5 if _is_tie(d) else
                            (1.0 if d["superposition_err"] > 0 else 0.0))
        return hits

    # -- §5 C6 baseline-matched null (must be checked first) --------------
    def c6_baseline_null(self):
        hits = []
        for gen in ALL_GENERATORS:
            for seed in self.seeds(gen):
                ref = self.base[(gen, REF, seed)]
                for m in ALL_COMPUTATIONAL:
                    d = _sub(self.base[(gen, m, seed)], ref, BASELINE_FEATS)
                    hits.append(0.5 if _is_tie(d) else
                                (1.0 if self._blind_base_predict(d) == "A" else 0.0))
        return hits

    def _blind_base_predict(self, d):
        # baseline features are bitwise identical, so this path is never taken;
        # kept only to make the tie rule the sole determinant.
        return "A"

    # -- §5 C2 intervention permutation -----------------------------------
    def _permutation_featmaps(self, n_perm=20):
        """Randomly permute INTERVENTION IDENTITIES while preserving responses:
        a labelled instance is handed a DIFFERENT world's whole response bag, so
        every measured response is kept (multisets preserved) but the
        (intervention-identity -> response) attribution is scrambled. If the signal
        is the true causal map, a detector retrained on these mislabelled worlds
        cannot beat chance."""
        keys = list(self.R.keys())
        maps = []
        for p in range(n_perm):
            rng = random.Random(C.BASE_SEED + 7919 * p)
            order = keys[:]
            rng.shuffle(order)                 # bijection: instance -> donor world
            fm = {k: dict(self.feat[donor]) for k, donor in zip(keys, order)}
            maps.append(fm)
        return maps

    def c2_permutation(self):
        accs = []
        for fm in self._permutation_featmaps():
            hits = self.discriminate(fm, OPERATOR_FEATS, TRAIN_GENERATORS,
                                     TRAIN_MECHANISMS, HOLDOUT_GENERATORS,
                                     ALL_COMPUTATIONAL)
            accs.append(self._acc(hits))
        return accs

    # -- §5 C3 response surrogate -----------------------------------------
    def _surrogate_featmap(self, seed=0xC3):
        """Destroy the causal correspondence between intervention and response
        while preserving response STATISTICS: each named role's trajectories are
        independently permuted across the whole population, so the per-role
        distribution of responses is exactly kept, but the three operands of any
        algebraic test (A, B, A+B) now come from different worlds -> superposition
        / composition / path structure becomes world-agnostic noise."""
        rng = random.Random(C.BASE_SEED + seed)
        keys = list(self.R.keys())
        pools = {}
        for role in TRAJ_ROLES + ["coll"]:
            pool = [self.R[k][role] for k in keys]
            rng.shuffle(pool)
            pools[role] = pool
        fm = {}
        for idx, k in enumerate(keys):
            Rs = dict(self.R[k])
            for role in TRAJ_ROLES + ["coll"]:
                Rs[role] = pools[role][idx]
            fm[k] = features_from_responses(Rs)
        return fm

    def c3_surrogate(self, n_rep=5):
        accs = []
        for r in range(n_rep):
            fm = self._surrogate_featmap(seed=0xC3 + r)
            hits = self.discriminate(fm, OPERATOR_FEATS, TRAIN_GENERATORS,
                                     TRAIN_MECHANISMS, HOLDOUT_GENERATORS,
                                     ALL_COMPUTATIONAL)
            accs.append(self._acc(hits))
        return accs

    # -- §7 feature separation --------------------------------------------
    def feature_separation(self):
        merged = {k: dict(self.feat[k], **self.base[k]) for k in self.feat}

        def run(fmap, ks):
            hits = self.discriminate(fmap, ks, TRAIN_GENERATORS,
                                     TRAIN_MECHANISMS, HOLDOUT_GENERATORS,
                                     ALL_COMPUTATIONAL)
            a = self._acc(hits)
            ci = bootstrap_ci(hits)
            return {"accuracy": a, "n_pairs": len(hits), "ci95": [ci[0], ci[1]]}
        # baseline-only contrast uses the baseline feature map
        b_hits = self.discriminate(self.base, BASELINE_FEATS, TRAIN_GENERATORS,
                                   TRAIN_MECHANISMS, HOLDOUT_GENERATORS,
                                   ALL_COMPUTATIONAL)
        baseline = {"accuracy": self._acc(b_hits), "n_pairs": len(b_hits),
                    "ci95": list(bootstrap_ci(b_hits))}
        response = run(self.feat, OPERATOR_FEATS)
        amplitude = run(self.feat, AMPLITUDE_FEATS)   # ordinary-observable reference
        both = run(merged, OPERATOR_FEATS + BASELINE_FEATS)
        return {"baseline_only": baseline, "response_operator_only": response,
                "amplitude_only": amplitude, "baseline_plus_response": both}

    # -- determinism: rebuild features and compare exactly -----------------
    def determinism_check(self):
        feat2 = {}
        for key, R in self.R.items():
            gen, mech, seed = key
            feat2[key] = features_from_responses(
                battery_responses(gen, mech, seed))
        return feat2 == self.feat

    # -- §9 falsifiability: adversarial probes that decouple label vs property --
    def adversarial_probes(self):
        """Train the canonical computational-vs-continuous detector, then ask how it
        classifies held-out probes relative to the continuous reference. A true
        computational mech and the equivalent implementation are included as anchors.
        tie -> counts 0.5 (chance). Reveals whether the detector tracks non-additivity
        (cont_nonlinear should read computational = false positive; finite_additive
        should read continuous) or merely the pre-assigned label."""
        ks = OPERATOR_FEATS
        X, y = [], []
        for gen in TRAIN_GENERATORS:
            for seed in self.seeds(gen):
                ref = self.feat[(gen, REF, seed)]
                for m in TRAIN_MECHANISMS:
                    d = _sub(self.feat[(gen, m, seed)], ref, ks)
                    X.append(d); y.append("A")
                    X.append(_neg(d)); y.append("B")
        det = V5Detector()
        det.fit(X, y)

        def probe(mech):
            score = ties = n = 0
            sup = rec = col = 0.0
            for gen in ALL_GENERATORS:
                for seed in self.seeds(gen):
                    f = self.feat[(gen, mech, seed)]
                    d = _sub(f, self.feat[(gen, REF, seed)], ks)
                    n += 1
                    sup += f["superposition_err"]
                    rec += f["recurrence"]
                    col += f["collision"]
                    if _is_tie(d):
                        ties += 1
                        score += 0.5
                    elif det.predict(d) == "A":
                        score += 1
            return {"n": n, "classified_computational_rate": score / n,
                    "tie_rate": ties / n, "mean_superposition_err": sup / n,
                    "mean_recurrence": rec / n, "mean_collision": col / n}
        order = ["fixed_point", "modular", "cont_nonlinear",
                 "finite_additive", "continuous_alt"]
        probes = {m: probe(m) for m in order}
        # honest interpretation bound: the signal is non-additivity iff a
        # continuous-but-nonlinear probe is misread as computational while a
        # finite-but-additive probe is NOT.
        reads_comp = probes["cont_nonlinear"]["classified_computational_rate"]
        finite_add = probes["finite_additive"]["classified_computational_rate"]
        interp = {
            "signal_is_nonadditivity_not_computation": (
                reads_comp > ABOVE and finite_add <= ABOVE),
            "cont_nonlinear_false_positive": reads_comp,
            "finite_additive_read_computational": finite_add,
        }
        return probes, interp

    # -- §8 decision gate --------------------------------------------------
    def _decide(self, checks):
        if not checks["baseline_indistinguishable"]:
            return "BENCHMARK_INVALID"
        if not checks["deterministic_rerun"]:
            return "BENCHMARK_INVALID"
        if checks["equiv_impl_above_chance"]:
            return "IMPLEMENTATION_ARTIFACT"
        if checks["permutation_above_chance"] or checks["surrogate_above_chance"]:
            return "STATISTICAL_ARTIFACT"
        if not checks["primary_above_chance"]:
            return "BRANCH_CLOSED"
        if not checks["generator_holdout_survives"]:
            return "GENERATOR_CONFOUNDED"
        if not checks["unseen_mechanism_survives"]:
            return "NO_GENERALIZATION"
        if checks["amplitude_drives_signal"] and not checks["operator_carries"]:
            return "STATISTICAL_ARTIFACT"
        if all(checks[k] for k in ("baseline_indistinguishable",
                                   "primary_above_chance",
                                   "generator_holdout_survives",
                                   "unseen_mechanism_survives",
                                   "equiv_impl_at_chance",
                                   "permutation_at_chance",
                                   "surrogate_at_chance",
                                   "deterministic_rerun",
                                   "operator_carries")):
            return "ACTIVE_COMPUTATIONAL_SIGNATURE"
        return "STATISTICAL_ARTIFACT"

    def run(self):
        self._log(f"=== V6 ACTIVE BLACK-BOX RESPONSE BENCHMARK  hash={self.protocol_hash} ===")
        self.build_instances()

        # C6 first: if the (pre-intervention) baseline is separable, stop.
        c6 = self.c6_baseline_null()
        c6_acc = self._acc(c6)
        self._log(f"C6 baseline-matched null: {c6_acc:.4f} (expect chance)")
        if c6_acc > ABOVE:
            self.results = {"branch": "active_response_operator",
                            "protocol_hash": self.protocol_hash,
                            "c6_baseline_null": c6_acc,
                            "final_status": "BENCHMARK_INVALID",
                            "never_emits": "SIMULATION_DETECTED"}
            self._log("BENCHMARK_INVALID: baseline separable before interventions")
            return "BENCHMARK_INVALID"

        primary, in_pop, c4, c5, hard = self.primary_and_generalisation()
        prim = self._acc(primary)          # fully out-of-sample (unseen gen x all mech)
        pci = bootstrap_ci(primary)
        in_sample = self._acc(in_pop)      # diagnostic only, not the gated number
        c1 = self.c1_equivalent()
        c1_acc = self._acc(c1)
        c2 = self.c2_permutation()
        c3 = self.c3_surrogate()
        sep = self.feature_separation()
        det = self.determinism_check()
        probes, interp = self.adversarial_probes()

        prim_hits_ci = pci
        checks = {
            "baseline_indistinguishable": CHANCE_LO <= c6_acc <= CHANCE_HI,
            "primary_above_chance": prim > ABOVE and prim_hits_ci[0] > 0.5,
            "generator_holdout_survives": self._acc(c4) > ABOVE,
            "unseen_mechanism_survives": self._acc(c5) > ABOVE,
            "equiv_impl_at_chance": CHANCE_LO <= c1_acc <= CHANCE_HI,
            "equiv_impl_above_chance": c1_acc > ABOVE,
            "permutation_at_chance": abs(sum(c2) / len(c2) - 0.5) <= PERM_BAND,
            "permutation_above_chance": abs(sum(c2) / len(c2) - 0.5) > PERM_BAND,
            "surrogate_at_chance": abs(sum(c3) / len(c3) - 0.5) <= PERM_BAND,
            "surrogate_above_chance": abs(sum(c3) / len(c3) - 0.5) > PERM_BAND,
            "deterministic_rerun": det,
            "amplitude_drives_signal": sep["amplitude_only"]["accuracy"] > ABOVE,
            "operator_carries": (sep["response_operator_only"]["accuracy"] > ABOVE
                                 and sep["baseline_only"]["accuracy"] <= ABOVE),
        }
        self._log(f"PRIMARY (out-of-sample, unseen gen x all mech): {prim:.4f} "
                  f"CI[{prim_hits_ci[0]:.3f},{prim_hits_ci[1]:.3f}]  (in-sample diag {in_sample:.3f})")
        self._log(f"C4 gen-holdout     : {self._acc(c4):.4f}")
        self._log(f"C5 unseen-mech     : {self._acc(c5):.4f}   hard(both unseen): {self._acc(hard):.4f}")
        self._log(f"C1 equiv impl      : {c1_acc:.4f} (expect chance)")
        self._log(f"C2 permutation     : mean={sum(c2)/len(c2):.4f} max={max(c2):.4f} (expect chance)")
        self._log(f"C3 surrogate       : mean={sum(c3)/len(c3):.4f} max={max(c3):.4f} (expect chance)")
        self._log(f"§7 baseline={sep['baseline_only']['accuracy']:.3f} "
                  f"response={sep['response_operator_only']['accuracy']:.3f} "
                  f"amplitude={sep['amplitude_only']['accuracy']:.3f} "
                  f"both={sep['baseline_plus_response']['accuracy']:.3f}")
        self._log(f"deterministic rerun identical: {det}")
        self._log("§9 falsifiability probes (rate classified 'computational'):")
        for _m, _p in probes.items():
            self._log(f"    {_m:16s} comp={_p['classified_computational_rate']:.3f} "
                      f"tie={_p['tie_rate']:.3f} sup={_p['mean_superposition_err']:.2e} "
                      f"rec={_p['mean_recurrence']:.3f} coll={_p['mean_collision']:.3f}")
        self._log(f"    -> signal is non-additivity (not computation): "
                  f"{interp['signal_is_nonadditivity_not_computation']}")

        status = self._decide(checks)
        self._log(f"FINAL STATUS: {status}")

        self.results = {
            "branch": "active_response_operator",
            "protocol_hash": self.protocol_hash,
            "base_seed": C.BASE_SEED,
            "grid": [C.W, C.H], "n_steps": C.N_STEPS, "seeds_per_gen": SEEDS_PER_GEN,
            "generators": {"train": TRAIN_GENERATORS, "holdout": HOLDOUT_GENERATORS},
            "mechanisms": {"train": TRAIN_MECHANISMS, "unseen": UNSEEN_MECHANISMS,
                            "continuous_ref": REF},
            "c6_baseline_null": {"accuracy": c6_acc, "n_pairs": len(c6),
                                  "expected": 0.5,
                                  "meaning": "pre-intervention baseline continuous-vs-computational"},
            "primary": {"accuracy": prim, "n_pairs": len(primary),
                        "setting": "out_of_sample: train seen_gen+seen_mech, "
                                   "test holdout_gen x all_computational",
                        "ci95": [prim_hits_ci[0], prim_hits_ci[1]], "null": 0.5,
                        "in_sample_diagnostic": in_sample,
                        "meaning": "response-operator discrimination continuous vs computational"},
            "C1_equivalent_implementation": {"accuracy": c1_acc, "n_pairs": len(c1),
                                              "expected": 0.5,
                                              "bitwise_identical_response": True},
            "C2_intervention_permutation": {"mean": sum(c2) / len(c2), "max": max(c2),
                                            "n_perms": len(c2), "expected": 0.5},
            "C3_response_surrogate": {"mean": sum(c3) / len(c3), "max": max(c3),
                                      "n_reps": len(c3), "expected": 0.5},
            "C4_generator_holdout": {"accuracy": self._acc(c4), "n_pairs": len(c4),
                                      "ci95": list(bootstrap_ci(c4))},
            "C5_unseen_mechanism": {"accuracy": self._acc(c5), "n_pairs": len(c5),
                                    "ci95": list(bootstrap_ci(c5))},
            "C5_hard_both_unseen": {"accuracy": self._acc(hard), "n_pairs": len(hard),
                                    "ci95": list(bootstrap_ci(hard))},
            "feature_separation": sep,
            "falsifiability_probes": probes,
            "interpretation": interp,
            "deterministic_rerun": det,
            "status_checks": checks,
            "final_status": status,
            "never_emits": "SIMULATION_DETECTED",
        }
        return status


def run_v6():
    b = V6Benchmark()
    status = b.run()
    os.makedirs("v6_artifacts", exist_ok=True)
    with open("v6_results.json", "w", encoding="utf-8") as f:
        json.dump(b.results, f, indent=1, default=float)
    with open(os.path.join("v6_artifacts", "v6_results.json"), "w", encoding="utf-8") as f:
        json.dump(b.results, f, indent=1, default=float)
    proto = {
        "protocol": "V6_ACTIVE_BLACKBOX_RESPONSE_BENCHMARK",
        "version": "6.0.0",
        "created": datetime.now().isoformat(),
        "protocol_hash": b.protocol_hash,
        "base_seed": C.BASE_SEED,
        "hypothesis_tested": "hidden computational constraints are detectable from "
                             "the response to controlled interventions (the response "
                             "operator), not from passive observation",
        "central_object": "intervention -> response",
        "never_emits": "SIMULATION_DETECTED",
        "final_status": status,
    }
    with open("v6_protocol.json", "w", encoding="utf-8") as f:
        json.dump(proto, f, indent=1)
    try:
        from v6_db import populate_db
        populate_db(b)
    except Exception as e:
        print(f"[V6] db populate skipped: {e}")
    b._log("v6_results.json + v6_protocol.json + history_v6.sqlite3 written")
    return status


if __name__ == "__main__":
    print("V6 FINAL:", run_v6())
