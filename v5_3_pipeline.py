"""V5.3 Pipeline: Native Computational Fingerprint Benchmark.

Primary question (§12): when the substrate participates NATIVELY in the
recurrence and visible single-frame statistics are aggressively controlled,
can a detector still identify computational fingerprints?

Tracks (§6): A = single final snapshot; B = temporal trajectory (64 steps).
Primary metric (§5): balanced pairwise accuracy on same-generator/same-seed
counterfactual pairs. Null: 50%.

Headline pairs are TRAIN-substrate vs S64 on TRAIN generators, tested on
UNSEEN generators (T01/T03); substrate-disjoint tests T02/T12; matched
controls T04-T06; nulls T07/T08; leakage audit T09 (auto-blacklist);
ablation T10; degradation T11; equal-output control §12.

Memory policy: trajectories are generated, features extracted immediately,
frames discarded; matched-control phases REGENERATE frames deterministically
(same seeds) so memory stays bounded.
"""
import os
import json
import math
import zlib
import time
import random
import hashlib
from collections import Counter
from datetime import datetime
from typing import List, Dict, Tuple

from v5_detector import V5Detector
from v5_3_core import (
    run_recurrence, ALL_SUBSTRATES, SUBSTRATES_COMPUTATIONAL,
    TRAIN_SUBSTRATES, HOLDOUT_SUBSTRATES,
    TRAIN_GENERATORS, HOLDOUT_GENERATORS, LOO_GENERATORS,
    match_histogram, match_spectrum, trajectory_phase_surrogate,
    matched_trajectory,
)
from v5_3_features import (
    snapshot_features, temporal_features, dynamical_features,
    family_of, TEMPORAL_PREFIX, DYNAMICAL_PREFIX,
)

W, H = 60, 30
N_STEPS = 64
FRAME_EVERY = 4          # keep frames 0,4,8,...,64 -> 17 samples
SEEDS_PER_GEN = 20
BASE_SEED = 20260919


def stable_seed(gen_name: str, seed_off: int) -> int:
    """Deterministic across processes (unlike python hash())."""
    return (BASE_SEED + seed_off * 1000 + zlib.crc32(gen_name.encode())) % (2 ** 31)


class V53Pipeline:
    def __init__(self, time_budget=14400):
        self.time_budget = time_budget
        self.start = time.time()
        self.worlds = []          # {gen, seed, sub, label, field, featsA, featsB}
        self.results = {}
        self.protocol_hash = self._hash_sources()
        self.ck_path = os.path.join("v5_3_artifacts", "checkpoint.json")
        self.cache_path = "v5_3_pipeline_cache.pkl"

    # -- infra ------------------------------------------------------------
    def _hash_sources(self):
        files = ["v5_3_core.py", "v5_3_features.py", "v5_3_pipeline.py",
                 "v5_math.py", "v5_detector.py"]
        blob = ""
        for f in files:
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    blob += fh.read().decode("utf-8", errors="ignore")
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _log(self, msg):
        print(f"[V5.3 {time.time() - self.start:7.1f}s] {msg}", flush=True)

    def _checkpoint(self, phase):
        os.makedirs("v5_3_artifacts", exist_ok=True)
        with open(self.ck_path, "w", encoding="utf-8") as f:
            json.dump({"completed_phase": phase,
                       "results": self.results,
                       "n_worlds": len(self.worlds),
                       "timestamp": datetime.now().isoformat()}, f, indent=1)

    # ====================================================================
    # PHASE 1+2: GENERATE + EXTRACT (frames streamed, then discarded)
    # ====================================================================
    def phase_generate(self):
        self._log("=== V5.3 NATIVE WORLD GENERATION ===")
        gens = TRAIN_GENERATORS + HOLDOUT_GENERATORS + LOO_GENERATORS
        for gen in gens:
            split = ("train" if gen in TRAIN_GENERATORS else
                     "holdout" if gen in HOLDOUT_GENERATORS else "loo")
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                for sub in ALL_SUBSTRATES:
                    frames = run_recurrence(gen, seed, W, H, sub, n_steps=N_STEPS)
                    final = frames[-1]
                    sampled = frames[::FRAME_EVERY]
                    if sampled[-1] is not final:
                        sampled.append(final)
                    fa = snapshot_features(final, W, H)
                    fb = dict(fa)
                    fb.update(temporal_features(sampled, W, H))
                    fb.update(dynamical_features(sampled, W, H))
                    self.worlds.append({
                        "generator": gen, "substrate": sub, "seed": seed,
                        "label": "continuous" if sub == "S64" else "computational",
                        "split": split, "field": final,
                        "featsA": fa, "featsB": fb,
                    })
            self._log(f"  {gen} done ({len(self.worlds)} worlds)")
        self._log(f"  Total worlds: {len(self.worlds)}")

    # ====================================================================
    # PAIRWISE MACHINERY (§5)
    # ====================================================================
    def _world_index(self):
        idx = {}
        for w in self.worlds:
            idx[(w["generator"], w["seed"], w["substrate"])] = w
        return idx

    @staticmethod
    def _diff(fx, fy, feature_names=None):
        keys = feature_names if feature_names else sorted(set(fx) | set(fy))
        return {("d_" + k): fx.get(k, 0.0) - fy.get(k, 0.0) for k in keys}

    def _train_samples(self, pairs, track, feat_filter=None):
        """pairs: list of (cont_world, comp_world). Mirror-augmented:
        label 'A' = first member is computational, 'B' = second.
        feat_filter: iterable of RAW feature names (no d_ prefix) or None."""
        key = "featsA" if track == "A" else "featsB"
        names = list(feat_filter) if feat_filter else None
        X, y = [], []
        for c, k in pairs:
            d = self._diff(k[key], c[key], names)
            X.append(d); y.append("A")
            X.append({kk: -vv for kk, vv in d.items()}); y.append("B")
        return X, y

    def _train_detector(self, pairs, track, feat_filter=None):
        X, y = self._train_samples(pairs, track, feat_filter)
        det = V5Detector()
        det.fit(X, y)
        return det

    def _eval_pairwise(self, det, pairs, track, feat_filter=None):
        """Returns (#pairs, #correct) on true orientation."""
        key = "featsA" if track == "A" else "featsB"
        names = list(feat_filter) if feat_filter else None
        n_ok = 0
        for c, k in pairs:
            d = self._diff(k[key], c[key], names)
            if det.predict(d) == "A":
                n_ok += 1
        return len(pairs), n_ok

    def _pairs_for(self, gens, comp_subs, idx):
        pairs = []
        for gen in gens:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = idx.get((gen, seed, "S64"))
                if not cont:
                    continue
                for sub in comp_subs:
                    comp = idx.get((gen, seed, sub))
                    if comp:
                        pairs.append((cont, comp))
        return pairs

    # ====================================================================
    # T03 + T01: primary generator-disjoint tests
    # ====================================================================
    def phase_primary(self):
        self._log("=== T03/T01 PRIMARY (generator-disjoint) ===")
        idx = self._world_index()
        train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
        test_pairs = self._pairs_for(HOLDOUT_GENERATORS, TRAIN_SUBSTRATES, idx)
        self._log(f"  train pairs={len(train_pairs)} test pairs={len(test_pairs)}")

        out = {}
        for track in ("A", "B"):
            det = self._train_detector(train_pairs, track)
            det.freeze()
            n, ok = self._eval_pairwise(det, test_pairs, track)
            acc = ok / n if n else 0.0
            # per-generator and per-substrate breakdown (§14)
            per_gen, per_sub = {}, {}
            for (c, k) in test_pairs:
                d = self._diff(k["featsA" if track == "A" else "featsB"],
                               c["featsA" if track == "A" else "featsB"])
                hit = 1 if det.predict(d) == "A" else 0
                pg = per_gen.setdefault(k["generator"], [0, 0])
                ps = per_sub.setdefault(k["substrate"], [0, 0])
                pg[0] += hit; pg[1] += 1
                ps[0] += hit; ps[1] += 1
            ci = self._bootstrap_ci([1 if self._eval_pairwise_one(det, [(c, k)], track) else 0
                                     for c, k in test_pairs])
            out[f"track_{track}"] = {
                "pairwise_accuracy": acc, "n_pairs": n,
                "ci95": [ci[0], ci[1]],
                "per_generator": {g: v[0] / v[1] for g, v in per_gen.items()},
                "per_substrate": {s: v[0] / v[1] for s, v in per_sub.items()},
                "null": 0.5,
            }
            det.unfreeze()
            self._log(f"  Track {track}: pairwise acc={acc:.4f} CI[{ci[0]:.3f},{ci[1]:.3f}]")
            self._log(f"    per-gen: { {g: round(v[0]/v[1],3) for g,v in per_gen.items()} }")
        # store a reusable trained detector for later control phases
        self.primary_det_A = self._train_detector(train_pairs, "A")
        self.primary_det_B = self._train_detector(train_pairs, "B")
        self._log("  T01 world-level generator holdout:")
        t01 = self._t01_world_level(idx)
        out["t01_world_level"] = t01
        self.results["T03_pairwise_primary"] = out

    def _eval_pairwise_one(self, det, pair, track):
        key = "featsA" if track == "A" else "featsB"
        c, k = pair[0]
        d = self._diff(k[key], c[key])
        return det.predict(d) == "A"

    def _bootstrap_ci(self, hits, n_boot=1000):
        rng = random.Random(BASE_SEED)
        n = len(hits)
        if n == 0:
            return (0.0, 0.0)
        accs = []
        for _ in range(n_boot):
            idxs = [rng.randint(0, n - 1) for _ in range(n)]
            accs.append(sum(hits[i] for i in idxs) / n)
        accs.sort()
        return accs[int(0.025 * len(accs))], accs[int(0.975 * len(accs))]

    def _t01_world_level(self, idx):
        cont_train = [w for w in self.worlds if w["split"] == "train" and w["substrate"] == "S64"]
        comp_train = [w for w in self.worlds if w["split"] == "train"
                      and w["substrate"] in TRAIN_SUBSTRATES]
        n = min(len(cont_train), len(comp_train))
        # stratify per generator (V5.2 audit lesson)
        train = []
        by_gen_c, by_gen_k = {}, {}
        for w in cont_train:
            by_gen_c.setdefault(w["generator"], []).append(w)
        for w in comp_train:
            by_gen_k.setdefault(w["generator"], []).append(w)
        for g in TRAIN_GENERATORS:
            m = min(len(by_gen_c.get(g, [])), len(by_gen_k.get(g, [])))
            train += by_gen_c.get(g, [])[:m] + by_gen_k.get(g, [])[:m]
        det = V5Detector()
        det.fit([w["featsB"] for w in train], [w["label"] for w in train])
        test = [w for w in self.worlds if w["split"] == "holdout"
                and (w["substrate"] == "S64" or w["substrate"] in TRAIN_SUBSTRATES)]
        preds = [det.predict(w["featsB"]) for w in test]
        trues = [w["label"] for w in test]
        nc, nk = trues.count("continuous"), trues.count("computational")
        rc = sum(1 for p, t in zip(preds, trues) if t == "continuous" and p == "continuous") / max(1, nc)
        rk = sum(1 for p, t in zip(preds, trues) if t == "computational" and p == "computational") / max(1, nk)
        bal = (rc + rk) / 2
        self._log(f"  T01 world-level bal_acc={bal:.4f} (cont={nc}, comp={nk})")
        return {"balanced_accuracy": bal, "n_continuous": nc, "n_computational": nk}

    # ====================================================================
    # T02 / T12: substrate-disjoint + unknown mechanism
    # ====================================================================
    def phase_substrate_disjoint(self):
        self._log("=== T02/T12 SUBSTRATE-DISJOINT + UNKNOWN ===")
        idx = self._world_index()
        train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
        out = {}
        for track in ("A", "B"):
            det = self._train_detector(train_pairs, track)
            per_sub = {}
            for sub in HOLDOUT_SUBSTRATES:
                tp = self._pairs_for(TRAIN_GENERATORS, [sub], idx)
                n, ok = self._eval_pairwise(det, tp, track)
                per_sub[sub] = ok / n if n else 0.0
                self._log(f"  Track {track} {sub}: {ok}/{n} = {ok/n if n else 0:.4f}")
            out[f"track_{track}"] = per_sub
        self.results["T02_substrate_disjoint"] = out
        # §16 also test unknown on UNSEEN generators (double-disjoint)
        dd = {}
        for track in ("A", "B"):
            det = self._train_detector(train_pairs, track)
            per = {}
            for sub in HOLDOUT_SUBSTRATES:
                tp = self._pairs_for(HOLDOUT_GENERATORS, [sub], idx)
                n, ok = self._eval_pairwise(det, tp, track)
                per[sub] = ok / n if n else 0.0
            dd[f"track_{track}"] = per
        self.results["T12_double_disjoint"] = dd

    # ====================================================================
    # T04/T05/T06: matched pairwise controls (frames regenerated on demand)
    # ====================================================================
    def phase_matched(self):
        """T04-T06 in ONE pass: per (gen,seed) regenerate cont frames once,
        per substrate regenerate comp frames once, derive all three matched
        variants from that single trajectory, extract features once per
        variant (Track B temporal+dynamical implies Track A snapshot), and
        score both tracks. Avoids the 3x2 recurrence/extraction redundancy."""
        self._log("=== T04-T06 MATCHED PAIRWISE CONTROLS (single pass) ===")
        idx = self._world_index()
        train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
        dets = {t: self._train_detector(train_pairs, t) for t in ("A", "B")}
        hits = {vn + t: 0 for vn in ("T04", "T05", "T06") for t in ("A", "B")}
        tot = 0

        def feats_of(frames):
            final = frames[-1]
            sampled = frames[::FRAME_EVERY]
            if sampled[-1] is not final:
                sampled.append(final)
            fa = snapshot_features(final, W, H)
            return fa, dict(fa, **temporal_features(sampled, W, H),
                            **dynamical_features(sampled, W, H))

        for gen in HOLDOUT_GENERATORS:
            for off in range(SEEDS_PER_GEN):
                seed = stable_seed(gen, off)
                cont = idx.get((gen, seed, "S64"))
                if not cont:
                    continue
                cont_frames = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                for sub in TRAIN_SUBSTRATES:
                    comp = idx.get((gen, seed, sub))
                    if not comp:
                        continue
                    comp_frames = run_recurrence(gen, seed, W, H, sub, n_steps=N_STEPS)
                    native_m = matched_trajectory(comp_frames, cont_frames)
                    sur_m = matched_trajectory(
                        trajectory_phase_surrogate(comp_frames, W, H, 12345),
                        cont_frames)
                    variants = {
                        "T04": native_m,
                        "T05": [match_spectrum(a, b) for a, b in
                                zip(native_m, cont_frames)],
                        "T06": sur_m,
                    }
                    for vn, alt in variants.items():
                        fA, fB = feats_of(alt)
                        for track in ("A", "B"):
                            # detector trained on diff = comp - cont, so the
                            # reference for BOTH tracks is the continuous (S64)
                            # world; cur is the matched computational variant.
                            ref = cont["featsA"] if track == "A" else cont["featsB"]
                            cur = fA if track == "A" else fB
                            d = self._diff(cur, ref)
                            if dets[track].predict(d) == "A":
                                hits[vn + track] += 1
                tot += len(TRAIN_SUBSTRATES)
            self._log(f"  {gen}: {tot} pair-evaluations done")
        n = max(1, tot)
        res = {}
        for vn, nm_full in (("T04", "T04_histogram_matched"),
                            ("T05", "T05_spectrum_matched"),
                            ("T06", "T06_temporal_matched")):
            for track in ("A", "B"):
                acc = hits[vn + track] / n
                res[f"{nm_full}_{track}"] = {"accuracy": acc,
                                              "n_pairs": tot, "null": 0.5}
                self._log(f"  {nm_full} Track {track}: "
                          f"{hits[vn + track]}/{n} = {acc:.4f}")
        self.results.update(res)

    # ====================================================================
    # §12 EQUAL-OUTPUT CONTROL (primary V5.3 question, TRACK B)
    # ====================================================================
    def phase_equal_output(self):
        self._log("=== §12 EQUAL-OUTPUT CONTROL ===")
        idx = self._world_index()
        # build matched-vs-surrogate PAIRS (both members statistically
        # identical to the continuous frame; only native dynamics differ)
        def build_pairs(gens):
            tr, te = [], []
            for gen in gens:
                for off in range(SEEDS_PER_GEN):
                    seed = stable_seed(gen, off)
                    cont = idx.get((gen, seed, "S64"))
                    if not cont:
                        continue
                    cont_frames = run_recurrence(gen, seed, W, H, "S64", n_steps=N_STEPS)
                    for sub in TRAIN_SUBSTRATES:
                        comp = idx.get((gen, seed, sub))
                        if not comp:
                            continue
                        comp_frames = run_recurrence(gen, seed, W, H, sub, n_steps=N_STEPS)
                        native = matched_trajectory(comp_frames, cont_frames)
                        sur = trajectory_phase_surrogate(comp_frames, W, H,
                                                         seed & 0x7FFFFFFF)
                        sur_m = matched_trajectory(sur, cont_frames)
                        pair = (native, sur_m, gen, sub)
                        (tr if gen in TRAIN_GENERATORS else te).append(pair)
            return tr, te

        tr, te = build_pairs(TRAIN_GENERATORS + HOLDOUT_GENERATORS)
        self._log(f"  native-vs-surrogate pairs: train={len(tr)} test={len(te)}")

        def feats_of(frames):
            final = frames[-1]
            sampled = frames[::FRAME_EVERY]
            if sampled[-1] is not final:
                sampled.append(final)
            fa = snapshot_features(final, W, H)
            return dict(fa, **temporal_features(sampled, W, H),
                        **dynamical_features(sampled, W, H))

        X, y = [], []
        for native, sur, _, _ in tr:
            fn_, fs = feats_of(native), feats_of(sur)
            d = self._diff(fn_, fs)
            X.append(d); y.append("A")
            X.append({k: -v for k, v in d.items()}); y.append("B")
        det = V5Detector()
        det.fit(X, y)
        ok = 0
        for native, sur, _, _ in te:
            d = self._diff(feats_of(native), feats_of(sur))
            ok += 1 if det.predict(d) == "A" else 0
        acc = ok / len(te) if te else 0.0
        self._log(f"  Equal-output (Track B): {ok}/{len(te)} = {acc:.4f}")
        self.results["S12_equal_output"] = {"accuracy": acc, "n_pairs": len(te), "null": 0.5}

    # ====================================================================
    # T07 identical null / T08 permutation
    # ====================================================================
    def phase_nulls(self):
        self._log("=== T07/T08 NULLS ===")
        idx = self._world_index()
        train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
        test_pairs = self._pairs_for(HOLDOUT_GENERATORS, TRAIN_SUBSTRATES, idx)
        # T07: identical observations (S64 vs S64 same world): zero diff,
        # mirror protocol guarantees exactly 50% under any symmetric detector
        det = self._train_detector(train_pairs, "B")
        ident_pairs = []
        for g in HOLDOUT_GENERATORS:
            for o in range(SEEDS_PER_GEN):
                w = idx.get((g, stable_seed(g, o), "S64"))
                if w:
                    ident_pairs.append((w, w))
        # evaluate on both orientations explicitly
        ok = 0
        tot = 0
        for a, b in ident_pairs:
            d = self._diff(a["featsB"], b["featsB"])   # zero vector
            ok += 1 if det.predict(d) == "A" else 0
            tot += 1
            dn = {k: -v for k, v in d.items()}
            ok += 1 if det.predict(dn) == "B" else 0
            tot += 1
        ident_acc = ok / tot if tot else 0
        self._log(f"  T07 identical obs: {ok}/{tot} = {ident_acc:.4f} (expect exactly 0.5)")
        self.results["T07_identical_null"] = {"accuracy": ident_acc, "expected": 0.5}

        # T08: 20 label permutations on the pairwise task
        key = "featsB"
        base_X = []
        for c, k in train_pairs:
            d = self._diff(k[key], c[key])
            base_X.append((d, {kk: -vv for kk, vv in d.items()}))
        true_lab = ["A", "B"] * len(train_pairs)
        test_X = []
        for c, k in test_pairs:
            d = self._diff(k[key], c[key])
            test_X.append((d, "A"))
            test_X.append(({kk: -vv for kk, vv in d.items()}, "B"))
        accs = []
        for pi in range(20):
            rng = random.Random(BASE_SEED + pi)
            labs = list(true_lab)
            rng.shuffle(labs)
            detp = V5Detector()
            flat = [x for pair in base_X for x in pair]
            detp.fit(flat, labs)
            okp = sum(1 for x, t in test_X if detp.predict(x) == t)
            accs.append(okp / len(test_X))
        mean_acc = sum(accs) / len(accs)
        self._log(f"  T08 perm null: mean={mean_acc:.4f} "
                  f"min={min(accs):.4f} max={max(accs):.4f} (20 perms)")
        self.results["T08_label_permutation"] = {"mean_accuracy": mean_acc,
                                                 "min": min(accs), "max": max(accs),
                                                 "n_perms": 20, "expected": 0.5}

    # ====================================================================
    # T09 leakage audit + auto-blacklist + clean rerun
    # ====================================================================
    @staticmethod
    def _binned_mi(values, groups, n_bins=8):
        n = len(values)
        if n < 8:
            return 0.0
        order = sorted(range(n), key=lambda i: values[i])
        bins = [0] * n
        sz = max(1, n // n_bins)
        for rank, idx in enumerate(order):
            bins[idx] = min(n_bins - 1, rank // sz)
        joint = Counter(zip(bins, groups))
        cb = Counter(bins)
        cg = Counter(groups)
        h_bg = -sum((p / n) * math.log2(p / n) for p in joint.values())
        h_b = -sum((p / n) * math.log2(p / n) for p in cb.values())
        h_g = -sum((p / n) * math.log2(p / n) for p in cg.values())
        mi = h_b + h_g - h_bg
        denom = min(h_b, h_g)
        return max(0.0, mi) / denom if denom > 1e-12 else 0.0

    def phase_leakage(self):
        self._log("=== T09 LEAKAGE AUDIT ===")
        comp = [w for w in self.worlds
                if w["split"] in ("train", "holdout") and w["substrate"] in TRAIN_SUBSTRATES]
        if not comp:
            self._log("  no computational worlds"); return
        names = sorted(set().union(*[set(w["featsB"]) for w in comp[:50]]))
        gen_g = [w["generator"] for w in comp]
        sub_g = [w["substrate"] for w in comp]
        seed_rank = {}
        uniq_seeds = sorted(set(w["seed"] for w in comp))
        pos = {s: i for i, s in enumerate(uniq_seeds)}
        nbin = max(1, len(uniq_seeds) // 5)
        seed_g = [str(pos[w["seed"]] // nbin) for w in comp]
        per_feat = {}
        blacklist = []
        for nm in names:
            vals = [w["featsB"].get(nm, 0.0) for w in comp]
            mi_g = self._binned_mi(vals, gen_g)
            mi_s = self._binned_mi(vals, sub_g)
            mi_sd = self._binned_mi(vals, seed_g)
            per_feat[nm] = {"mi_generator": mi_g, "mi_substrate": mi_s,
                            "mi_seed": mi_sd}
            if mi_g >= 0.8 and mi_s < 0.2:
                blacklist.append(nm)
        mg = sum(v["mi_generator"] for v in per_feat.values()) / len(per_feat)
        ms = sum(v["mi_substrate"] for v in per_feat.values()) / len(per_feat)
        verdict = ("GENERATOR_DOMINANT" if mg > ms * 1.5 else
                   "SUBSTRATE_DOMINANT" if ms > mg * 1.5 else "BALANCED")
        self._log(f"  MI gen={mg:.4f} sub={ms:.4f} -> {verdict}; "
                  f"GENERATOR_LEAK blacklist: {len(blacklist)} features")
        self.results["T09_leakage"] = {
            "mi_generator_mean": mg, "mi_substrate_mean": ms,
            "verdict": verdict, "blacklist": blacklist,
            "per_feature_extreme_gen": sorted(
                per_feat.items(), key=lambda kv: -kv[1]["mi_generator"])[:5],
        }
        # clean rerun of T03 Track B excluding blacklisted diff features
        if blacklist:
            idx = self._world_index()
            allowed_raw = sorted(set(per_feat.keys()) - set(blacklist))
            train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
            test_pairs = self._pairs_for(HOLDOUT_GENERATORS, TRAIN_SUBSTRATES, idx)
            det = self._train_detector(train_pairs, "B", feat_filter=allowed_raw)
            n, ok = self._eval_pairwise(det, test_pairs, "B", feat_filter=allowed_raw)
            self.results["T03_clean_rerun"] = {"accuracy": ok / n if n else 0,
                                               "n_pairs": n,
                                               "excluded": len(blacklist)}
            self._log(f"  T03 clean rerun: {ok}/{n} = {ok/n if n else 0:.4f}")

    # ====================================================================
    # T10 ablation over diff-feature families
    # ====================================================================
    def phase_ablation(self):
        self._log("=== T10 FEATURE-FAMILY ABLATION (pairwise Track B) ===")
        idx = self._world_index()
        train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
        test_pairs = self._pairs_for(HOLDOUT_GENERATORS, TRAIN_SUBSTRATES, idx)
        ref = test_pairs[0][0]["featsB"]
        fam_names = {}
        for kname in ref:
            fam_names.setdefault(family_of(kname), []).append(kname)
        out = {}
        sets = {f: names for f, names in fam_names.items()}
        sets["temporal+dynamical"] = fam_names.get("temporal", []) + fam_names.get("dynamical", [])
        sets["all"] = list(ref)
        for sname, names in sets.items():
            if not names:
                continue
            det = self._train_detector(train_pairs, "B", feat_filter=names)
            n, ok = self._eval_pairwise(det, test_pairs, "B", feat_filter=names)
            out[sname] = ok / n if n else 0.0
            self._log(f"  {sname}: {out[sname]:.4f}")
        self.results["T10_ablation"] = out

    # ====================================================================
    # T11 observation degradation (Track A pairwise)
    # ====================================================================
    def phase_degradation(self):
        self._log("=== T11 OBSERVATION DEGRADATION ===")
        idx = self._world_index()
        train_pairs = self._pairs_for(TRAIN_GENERATORS, TRAIN_SUBSTRATES, idx)
        det = self._train_detector(train_pairs, "A")
        import struct as st

        def f32(v):
            return st.unpack('f', st.pack('f', v))[0]

        def f16(v):
            v = max(-65504.0, min(65504.0, v))
            try:
                return st.unpack('e', st.pack('e', v))[0]
            except (OverflowError, ValueError):
                return 0.0

        models = {
            "float32": lambda f: [f32(v) for v in f],
            "float16": lambda f: [f16(v) for v in f],
            "uint8": lambda f: [round(round((v + 1) / 2 * 255) / 255 * 2 - 1, 6)
                                for v in f],
            "downsample2x2": "AVGPOOL",
            "noisy": None,  # handled with rng below
        }
        out = {}
        rng = random.Random(BASE_SEED)
        for nm, tf in models.items():
            ok = tot = 0
            for gen in HOLDOUT_GENERATORS:
                for off in range(SEEDS_PER_GEN):
                    seed = stable_seed(gen, off)
                    cont = idx.get((gen, seed, "S64"))
                    if not cont:
                        continue
                    for sub in TRAIN_SUBSTRATES:
                        comp = idx.get((gen, seed, sub))
                        if not comp:
                            continue
                        if tf == "AVGPOOL":
                            def deg(f):
                                w2, h2 = W // 2, H // 2
                                out2 = []
                                for i in range(w2):
                                    for j in range(h2):
                                        vals = [f[(2 * i) * H + 2 * j + di * H + dj]
                                                for di in (0, 1) for dj in (0, 1)]
                                        out2.append(sum(vals) / 4)
                                return out2
                            fc, fk = deg(cont["field"]), deg(comp["field"])
                            qc = snapshot_features(fc, W // 2, H // 2)
                            qk = snapshot_features(fk, W // 2, H // 2)
                        elif nm == "noisy":
                            sigma = 0.02
                            fc = [v + rng.gauss(0, sigma) for v in cont["field"]]
                            fk = [v + rng.gauss(0, sigma) for v in comp["field"]]
                            qc = snapshot_features(fc, W, H)
                            qk = snapshot_features(fk, W, H)
                        else:
                            fc, fk = tf(cont["field"]), tf(comp["field"])
                            qc = snapshot_features(fc, W, H)
                            qk = snapshot_features(fk, W, H)
                        d = self._diff(qk, qc)
                        tot += 1
                        if det.predict(d) == "A":
                            ok += 1
            out[nm] = ok / tot if tot else 0.0
            self._log(f"  {nm}: {ok}/{tot} = {out[nm]:.4f}")
        self.results["T11_degradation"] = {"null": 0.5, **out}

    # ====================================================================
    # STATUS (§13) + HARD STOP (§16)
    # ====================================================================
    def determine_status(self):
        self._log("=== V5.3 STATUS ===")
        r = self.results
        pri = r.get("T03_pairwise_primary", {})
        pA = pri.get("track_A", {}).get("pairwise_accuracy", 0.5)
        pB = pri.get("track_B", {}).get("pairwise_accuracy", 0.5)
        t04B = r.get("T04_histogram_matched_B", {}).get("accuracy", 0.5)
        t05B = r.get("T05_spectrum_matched_B", {}).get("accuracy", 0.5)
        t06B = r.get("T06_temporal_matched_B", {}).get("accuracy", 0.5)
        unk = r.get("T02_substrate_disjoint", {}).get("track_B", {})
        unk_min = min(unk.values()) if unk else 0.5
        eqo = r.get("S12_equal_output", {}).get("accuracy", 0.5)
        ident = r.get("T07_identical_null", {}).get("accuracy", 0.0)
        perm = r.get("T08_label_permutation", {}).get("mean_accuracy", 1.0)
        leak = r.get("T09_leakage", {}).get("verdict", "")
        deg = r.get("T11_degradation", {})

        def surv(a):
            return a > 0.55

        checks = {
            "1_pairwise_above_chance": surv(pA) or surv(pB),
            "2_hist_matched_survives": surv(t04B),
            "3_spectrum_matched_survives": surv(t05B),
            "4_temporal_matched_survives": surv(t06B),
            "5_unknown_substrate_survives": surv(unk_min),
            "6_equal_output_survives": surv(eqo),
            "7_leakage_controlled": leak != "GENERATOR_DOMINANT",
            "8_permutation_collapses": abs(perm - 0.5) <= 0.1,
            "9_identical_at_chance": abs(ident - 0.5) <= 0.02,
            "10_observation_robust": all(surv(v) for k, v in deg.items()
                                         if k != "null"),
        }
        for k, v in checks.items():
            self._log(f"  {k}: {'PASS' if v else 'FAIL'}")
        self.results["status_checks"] = checks

        # §16 hard stopping rule
        matched_avg = (t04B + t05B + t06B) / 3
        if (abs(pB - 0.5) <= 0.05 and abs(matched_avg - 0.5) <= 0.05
                and abs(unk_min - 0.5) <= 0.05 and abs(pA - 0.5) <= 0.05):
            self.results["hard_stop_triggered"] = True
            final = "NO_GENERALIZATION"
            self._log("  §16 HARD STOP: no detectable native fingerprint")
        elif all(checks.values()):
            final = "NATIVE_SUBSTRATE_SIGNAL"
        elif not checks["9_identical_at_chance"] or not checks["8_permutation_collapses"]:
            final = "BENCHMARK_INVALID"
        elif checks["1_pairwise_above_chance"] and not (
                checks["2_hist_matched_survives"] and checks["3_spectrum_matched_survives"]):
            final = "STATISTICAL_ARTIFACT"
        elif not checks["7_leakage_controlled"]:
            final = "GENERATOR_CONFOUNDED"
        elif not checks["10_observation_robust"]:
            final = "OBSERVATION_CONFOUNDED"
        elif checks["1_pairwise_above_chance"] and not checks["5_unknown_substrate_survives"]:
            final = "NO_GENERALIZATION"
        else:
            final = "STATISTICAL_ARTIFACT"
        self.results["final_status"] = final
        self._log(f"  FINAL STATUS: {final}")
        return final

    def phase_bootstrap(self):
        pass  # CIs already computed inside primary test

    # ====================================================================
    # ARTIFACTS
    # ====================================================================
    def phase_artifacts(self):
        self._log("=== V5.3 ARTIFACTS ===")
        os.makedirs("v5_3_artifacts/benchmark", exist_ok=True)
        with open("v5_3_results.json", "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=1, default=float)
        with open(os.path.join("v5_3_artifacts", "benchmark", "v5_3_results.json"),
                  "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=1, default=float)
        proto = {
            "protocol": "V5.3_NATIVE_COMPUTATIONAL_FINGERPRINT",
            "version": "5.3.0",
            "created": datetime.now().isoformat(),
            "protocol_hash": self.protocol_hash,
            "base_seed": BASE_SEED,
            "grid": [W, H], "n_steps": N_STEPS, "seeds_per_generator": SEEDS_PER_GEN,
            "generators": {"train": TRAIN_GENERATORS, "holdout": HOLDOUT_GENERATORS,
                           "loo": LOO_GENERATORS},
            "substrates": {"reference": ["S64"], "train": TRAIN_SUBSTRATES,
                           "holdout": HOLDOUT_SUBSTRATES, "all": ALL_SUBSTRATES},
            "substrate_implementations": {
                "S64": "float64 reference",
                "S32": "IEEE754 single rounding of every stored state each step",
                "S16": "IEEE754 half rounding of every stored state each step",
                "S_Q15": "16-bit signed fixed point; add/mul in Q15 each step; "
                         "transcendentals via documented float fallback",
                "S_FSM": "13-state lattice snap every step (state count hidden "
                         "from detector)",
                "S_MOD": "Z_100003 residue-ring recurrence with x1000 integer "
                         "coefficients (constants versioned in source)",
                "S_HASH_NATIVE": "SplitMix64 chain term added INSIDE each "
                                 "recurrence step (0.05*u_hash)",
                "S_UNKNOWN": "top-2-mantissa-bit truncation of every state "
                             "(novel; never trained on)",
            },
            "final_status": self.results.get("final_status"),
        }
        with open("v5_3_protocol.json", "w", encoding="utf-8") as f:
            json.dump(proto, f, indent=1)
        self._log("  v5_3_results.json + v5_3_protocol.json written")

    # ====================================================================
    # RUN
    # ====================================================================
    def run(self, resume_from=None):
        self._log(f"=== V5.3 INIT protocol={self.protocol_hash} ===")
        phases = [
            ("generate", self.phase_generate),
            ("primary", self.phase_primary),
            ("substrate_disjoint", self.phase_substrate_disjoint),
            ("matched", self.phase_matched),
            ("equal_output", self.phase_equal_output),
            ("nulls", self.phase_nulls),
            ("leakage", self.phase_leakage),
            ("ablation", self.phase_ablation),
            ("degradation", self.phase_degradation),
            ("status", self.determine_status),
            ("artifacts", self.phase_artifacts),
        ]
        # resume semantics: None -> run everything; "X" -> run phases AFTER X
        skip = resume_from is not None
        for name, fn in phases:
            if skip:
                if name == resume_from:
                    skip = False
                continue
            fn()
            self._checkpoint(name)
            # worlds are the expensive artifact: persist them immediately
            # after generate so a mid-run stop can resume without redoing
            # the ~35 min recurrence+extraction pass.
            if name == "generate":
                self._save_cache()
        self._save_cache()
        self._log("=== V5.3 COMPLETE ===")
        return self.results.get("final_status", "UNRESOLVED")

    def _save_cache(self):
        import pickle
        try:
            with open(self.cache_path, "wb") as f:
                pickle.dump({"worlds": self.worlds, "results": self.results}, f)
        except Exception as e:
            self._log(f"  cache save skipped: {e}")

    @classmethod
    def from_cache(cls):
        import pickle
        with open(cls().cache_path, "rb") as f:
            data = pickle.load(f)
        p = cls()
        p.worlds = data["worlds"]
        p.results = data.get("results", {})
        return p


def run_deep(time_budget=14400, resume=False):
    """Entry for: python3 agent_loop.py auto --mode v5.3-deep."""
    p = V53Pipeline(time_budget=time_budget)
    resume_from = None
    if resume:
        ck = os.path.join("v5_3_artifacts", "checkpoint.json")
        if os.path.exists(ck):
            with open(ck, encoding="utf-8") as f:
                resume_from = json.load(f).get("completed_phase")
            import pickle
            if os.path.exists(p.cache_path):
                with open(p.cache_path, "rb") as f:
                    p.worlds = pickle.load(f)["worlds"]
                p._log(f"  resumed worlds={len(p.worlds)} from {resume_from}")
    status = p.run(resume_from=resume_from)
    return status is not None


if __name__ == "__main__":
    p = V53Pipeline()
    print("FINAL:", p.run())
