"""V5.2 Pipeline: Adversarial benchmark for computational substrate detection."""
import os
import json
import hashlib
import time
import math
import random
from typing import List, Dict, Tuple
from collections import Counter
from datetime import datetime

from v5_math import extract_full_fingerprint
from v5_detector import V5Detector
from v5_2_core import (
    GENERATORS, SUBSTRATES_CONTINUOUS, SUBSTRATES_COMPUTATIONAL,
    generate_all_substrates, create_matched_pair, match_histogram,
    apply_substrate
)


class V52Pipeline:
    """V5.2 Adversarial Benchmark Pipeline."""
    
    def __init__(self, time_budget=14400, base_seed=133742):
        self.time_budget = time_budget
        self.base_seed = base_seed
        self.start_time = time.time()
        self.width, self.height = 60, 30
        self.seeds_per_world = 20
        
        # Generator-level splits (§8)
        self.train_generators = ["G01_analytic_smooth", "G02_gaussian_correlated",
                                  "G03_analytic_fractal", "G04_wave_eigenmode",
                                  "G05_chaotic_map"]
        self.val_generators = ["G06_nonlinear_dyn", "G07_reaction_diffusion"]
        self.holdout_generators = ["G08_procedural_noise", "G09_coupled_oscillator",
                                    "G10_cosmological_like"]
        
        # Substrate splits (§9)
        self.train_substrates_comp = ["S_FLOAT32", "S_FLOAT16", "S_QUANT_8", "S_LATTICE"]
        self.holdout_substrates_comp = ["S_LOOKUP", "S_HASH", "S_FINITE_STATE",
                                         "S_QUANT_4", "S_UNKNOWN_COMPUTATIONAL"]
        
        # Data storage
        self.worlds = []  # list of {gen, sub, seed, field, features, label, split}
        self.detector = V5Detector()
        
        # Results
        self.results = {}
        
        # Protocol hash
        self.protocol_hash = self._hash_sources()
    
    def _hash_sources(self):
        files = ["v5_2_core.py", "v5_2_pipeline.py", "v5_math.py", "v5_detector.py"]
        combined = ""
        for f in files:
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    combined += fh.read().decode("utf-8", errors="ignore")
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def _log(self, msg):
        elapsed = time.time() - self.start_time
        print(f"[V5.2 {elapsed:7.1f}s] {msg}")
    
    def _time_remaining(self):
        return self.time_budget - (time.time() - self.start_time)
    
    # ========================================================================
    # PHASE 1: GENERATE WORLDS
    # ========================================================================
    
    def phase_generate(self):
        """Generate worlds for all splits with paired substrates."""
        self._log("=== V5.2 WORLD GENERATION ===")
        
        for split_name, generators in [
            ("train", self.train_generators),
            ("validation", self.val_generators),
            ("holdout", self.holdout_generators),
        ]:
            self._log(f"  {split_name}: {len(generators)} generators")
            for gen_name in generators:
                for seed_off in range(self.seeds_per_world):
                    seed = self.base_seed + seed_off * 1000 + hash(gen_name) % 10000
                    
                    # Generate under all substrates
                    sub_fields = generate_all_substrates(gen_name, seed, self.width, self.height)
                    
                    for sub_name, field in sub_fields.items():
                        # Determine label
                        if sub_name in SUBSTRATES_CONTINUOUS:
                            label = "continuous"
                        elif sub_name in SUBSTRATES_COMPUTATIONAL:
                            label = "computational"
                        else:
                            label = "continuous"
                        
                        # Determine substrate split (§9: holdout substrates)
                        if split_name == "train" and sub_name in self.holdout_substrates_comp:
                            sub_split = "substrate_holdout"
                        else:
                            sub_split = split_name
                        
                        self.worlds.append({
                            "generator": gen_name,
                            "substrate": sub_name,
                            "seed": seed,
                            "field": field,
                            "label": label,
                            "split": split_name,
                            "sub_split": sub_split,
                            "width": self.width,
                            "height": self.height,
                        })
        
        self._log(f"  Total worlds generated: {len(self.worlds)}")
    
    # ========================================================================
    # PHASE 2: FEATURE EXTRACTION
    # ========================================================================
    
    def phase_extract_features(self):
        """Extract fingerprints for all worlds."""
        self._log("=== V5.2 FEATURE EXTRACTION ===")
        
        for i, w in enumerate(self.worlds):
            w["features"] = extract_full_fingerprint(w["field"], w["width"], w["height"])
            if (i + 1) % 200 == 0:
                self._log(f"  {i+1}/{len(self.worlds)} done")
        
        self._log(f"  Extracted {len(self.worlds)} feature vectors")
    
    # ========================================================================
    # PHASE 3: TRAIN DETECTOR
    # ========================================================================
    
    def _get_training_worlds(self):
        """Get balanced training worlds, STRATIFIED PER GENERATOR (audit fix:
        the global comp[:n] slice concentrated all computational examples in
        the first one or two generators)."""
        per_gen = {}
        for w in self.worlds:
            if w["split"] == "train" and w["sub_split"] == "train":
                d = per_gen.setdefault(w["generator"],
                                       {"continuous": [], "computational": []})
                d[w["label"]].append(w)
        out = []
        for gen in self.train_generators:
            d = per_gen.get(gen)
            if not d:
                continue
            n = min(len(d["continuous"]), len(d["computational"]))
            out += d["continuous"][:n] + d["computational"][:n]
        return out
    
    def _get_holdout_worlds(self):
        """Get balanced holdout STRATIFIED PER GENERATOR (V5.2 audit fix:
        naive cont[:n]+comp[:n] sliced all computational from one generator)."""
        per_gen = {}
        for w in self.worlds:
            if w["split"] == "holdout":
                per_gen.setdefault(w["generator"], {"continuous": [], "computational": []})
                per_gen[w["generator"]][w["label"]].append(w)
        selected = []
        for gen in self.holdout_generators:
            d = per_gen.get(gen, {"continuous": [], "computational": []})
            n = min(len(d["continuous"]), len(d["computational"]))
            selected += d["continuous"][:n] + d["computational"][:n]
        return selected
    
    def phase_train(self):
        """Train detector on training split."""
        self._log("=== V5.2 DETECTOR TRAINING ===")
        
        train_worlds = self._get_training_worlds()
        
        # Count classes
        labels = [w["label"] for w in train_worlds]
        self._log(f"  Training: {len(train_worlds)} worlds, "
                  f"continuous={labels.count('continuous')}, "
                  f"computational={labels.count('computational')}")
        
        feature_vectors = [w["features"] for w in train_worlds]
        self.detector.fit(feature_vectors, labels)
        self._log("  Detector trained.")
    
    # ========================================================================
    # PHASE 4: GENERATOR-DISJOINT BENCHMARK (§7-§8)
    # ========================================================================
    
    def phase_generator_holdout(self):
        """Primary benchmark: unseen generators, balanced classes."""
        self._log("=== V5.2 GENERATOR-DISJOINT HOLDOUT ===")
        
        self.detector.freeze()
        holdout = self._get_holdout_worlds()
        
        if not holdout:
            self._log("  ERROR: No holdout worlds!")
            return
        
        predictions = []
        true_labels = []
        
        for w in holdout:
            pred = self.detector.predict(w["features"])
            predictions.append(pred)
            true_labels.append(w["label"])
        
        # Compute metrics
        metrics = self._compute_metrics(predictions, true_labels)
        self.results["generator_holdout"] = metrics
        
        self._log(f"  Accuracy: {metrics['accuracy']:.4f}")
        self._log(f"  Balanced accuracy: {metrics['balanced_accuracy']:.4f}")
        self._log(f"  Holdout: continuous={true_labels.count('continuous')} "
                  f"computational={true_labels.count('computational')}")
        self._log(f"  Trivial baseline: {metrics['trivial_baseline']:.4f}")
        
        # Per-generator breakdown (§42) with class counts (audit: expose balance)
        self._log("  Per-generator:")
        per_gen_metrics = {}
        for gen in self.holdout_generators:
            gen_pairs = [(p, t) for p, t, w in zip(predictions, true_labels, holdout)
                         if w["generator"] == gen]
            if gen_pairs:
                correct = sum(1 for p, t in gen_pairs if p == t)
                nc = sum(1 for _, t in gen_pairs if t == "continuous")
                nk = len(gen_pairs) - nc
                per_gen_metrics[gen] = {"accuracy": correct / len(gen_pairs),
                                        "n_continuous": nc, "n_computational": nk}
                self._log(f"    {gen}: {correct}/{len(gen_pairs)} = {correct/len(gen_pairs):.4f} "
                          f"(cont={nc}, comp={nk})")
        self.results["generator_holdout_per_gen"] = per_gen_metrics
        
        self.detector.unfreeze()
    
    # ========================================================================
    # PHASE 5: SUBSTRATE-DISJOINT BENCHMARK (§9)
    # ========================================================================
    
    def phase_substrate_holdout(self):
        """Train on known substrates, test on unseen substrates."""
        self._log("=== V5.2 SUBSTRATE-DISJOINT HOLDOUT ===")
        
        # Train: only known computational substrates
        train = [w for w in self.worlds if w["split"] == "train"
                 and w["substrate"] in self.train_substrates_comp + ["S_CONTINUOUS"]]
        
        # V5.2 audit fix: balance test 1:1 (was 500 comp vs 100 cont = 5:1,
        # making raw accuracy meaningless). Take equal count per holdout substrate.
        test_per_sub = {}
        for w in self.worlds:
            if w["split"] == "train" and w["substrate"] in self.holdout_substrates_comp:
                test_per_sub.setdefault(w["substrate"], []).append(w)
        n_per = min(len(v) for v in test_per_sub.values()) if test_per_sub else 0
        # balance to available continuous references
        test_cont = [w for w in self.worlds if w["split"] == "train"
                     and w["substrate"] == "S_CONTINUOUS"]
        n_per = min(n_per, len(test_cont) // len(test_per_sub)) if test_per_sub else 0
        test_balanced = []
        for sub, ws in test_per_sub.items():
            test_balanced += ws[:n_per]
        n_total = n_per * len(test_per_sub)
        test_balanced += test_cont[:n_total]

        if not test_balanced:
            self._log("  ERROR: No substrate holdout worlds!")
            return
        
        # Retrain on known substrates
        sub_detector = V5Detector()
        train_fv = [w["features"] for w in train]
        train_labels = [w["label"] for w in train]
        sub_detector.fit(train_fv, train_labels)
        
        # Predict on unseen substrates
        predictions = [sub_detector.predict(w["features"]) for w in test_balanced]
        true_labels = [w["label"] for w in test_balanced]
        
        metrics = self._compute_metrics(predictions, true_labels)
        self.results["substrate_holdout"] = metrics
        
        self._log(f"  Accuracy: {metrics['accuracy']:.4f}")
        self._log(f"  Balanced accuracy: {metrics['balanced_accuracy']:.4f}")
        self._log(f"  Test: continuous={true_labels.count('continuous')} "
                  f"computational={true_labels.count('computational')}")
        
        # Per-substrate breakdown (§43), stored for the report
        per_sub = {}
        self._log("  Per-substrate:")
        for sub in self.holdout_substrates_comp:
            sub_preds = [(p, t) for p, t, w in zip(predictions, true_labels, test_balanced)
                        if w["substrate"] == sub]
            if sub_preds:
                correct = sum(1 for p, t in sub_preds if p == t)
                per_sub[sub] = {"recall": correct / len(sub_preds), "n": len(sub_preds)}
                self._log(f"    {sub}: {correct}/{len(sub_preds)} = {correct/len(sub_preds):.4f}")
        self.results["substrate_holdout_per_sub"] = per_sub
    
    # ========================================================================
    # PHASE 6: LABEL PERMUTATION NULL (§20)
    # ========================================================================
    
    def phase_label_permutation(self, n_perms=20):
        """Train with random labels - should collapse to baseline.
        V5.2 audit fix: a SINGLE permutation is a coin flip (cluster polarity):
        the detector can land at ~78% or ~22% by chance alone. Run n_perms
        permutations and judge by the MEAN (and report min/max)."""
        self._log("=== V5.2 LABEL PERMUTATION NULL ===")
        
        train_worlds = self._get_training_worlds()
        holdout = self._get_holdout_worlds()
        train_fv = [w["features"] for w in train_worlds]
        true_labels = [w["label"] for w in holdout]
        base_labels = [w["label"] for w in train_worlds]
        
        accs = []
        for perm_i in range(n_perms):
            rng = random.Random(self.base_seed + perm_i)
            labels = list(base_labels)
            rng.shuffle(labels)
            perm_detector = V5Detector()
            perm_detector.fit(train_fv, labels)
            predictions = [perm_detector.predict(w["features"]) for w in holdout]
            accs.append(sum(1 for p, t in zip(predictions, true_labels) if p == t) / len(true_labels))
        
        mean_acc = sum(accs) / len(accs)
        metrics = {"accuracy": mean_acc, "n_perms": n_perms,
                   "perm_min": min(accs), "perm_max": max(accs),
                   "trivial_baseline": 0.5}
        self.results["label_permutation"] = metrics
        
        self._log(f"  Permuted accuracy over {n_perms} perms: mean={mean_acc:.4f} "
                  f"min={min(accs):.4f} max={max(accs):.4f}")
        
        if abs(mean_acc - 0.5) > 0.1:
            self._log("  *** WARNING: Label permutation did NOT collapse! Possible leakage! ***")
        else:
            self._log("  PASS: Mean collapsed to chance as expected.")
    
    # ========================================================================
    # PHASE 7: IDENTICAL-OBSERVATION NULL (§26)
    # ========================================================================
    
    def phase_identical_observation_null(self):
        """SPEC-26 FIX: observations must be NUMERICALLY IDENTICAL, produced
        via two different hidden generation paths (analytic vs lossless
        lookup-table reconstruction). Not histogram-matching (that was a bug)."""
        self._log("=== V5.2 IDENTICAL-OBSERVATION NULL ===")
        
        null_worlds = []
        for gen_name in self.holdout_generators:
            for seed_off in range(self.seeds_per_world):
                seed = self.base_seed + seed_off * 1000 + hash(gen_name) % 10000
                from v5_2_core import GENERATORS as GENS
                base = GENS[gen_name](self.width, self.height, seed)
                # Hidden path B: lossless lookup-table storage (finite table of
                # exact values + indices) reconstructs the identical observation.
                uniq = sorted(set(base))
                idx_map = {v: i for i, v in enumerate(uniq)}
                reconstructed = [uniq[idx_map[v]] for v in base]
                assert reconstructed == base, "lossless roundtrip failed"
                
                # Same shared feature vector for both labels: zero information.
                feat = extract_full_fingerprint(base, self.width, self.height)
                null_worlds.append({"features": feat, "label": "continuous"})
                null_worlds.append({"features": feat, "label": "computational"})
        
        # Predict using existing detector
        predictions = [self.detector.predict(w["features"]) for w in null_worlds]
        true_labels = [w["label"] for w in null_worlds]
        
        metrics = self._compute_metrics(predictions, true_labels)
        self.results["identical_obs_null"] = metrics
        
        self._log(f"  Accuracy on identical obs: {metrics['accuracy']:.4f}")
        self._log(f"  Expected: exactly 0.5000 (bitwise-identical inputs)")
        if abs(metrics['accuracy'] - 0.5) > 0.02:
            self._log("  *** WARNING: deviation from chance on identical obs! ***")
        else:
            self._log("  PASS: No information detected (correct).")
    
    # ========================================================================
    # PHASE 8: MATCHED-STATISTIC ADVERSARIAL (§12-§18)
    # ========================================================================
    
    def phase_matched_statistics(self):
        """Histogram-matched adversarial worlds, TWO variants (audit fix):
        - monotonic variant (quantized): rank-match nearly recovers the original
          field (ties aside) -> weak control, must be labeled as such
        - non-monotonic variant (S_HASH): rank-match leaves residual structure
          -> the genuine 'does substrate survive statistic matching' test."""
        self._log("=== V5.2 MATCHED-STATISTIC ADVERSARIAL ===")
        
        from v5_2_core import GENERATORS as GENS, apply_substrate
        matched_worlds = []      # monotonic (quantization) variant
        matched_hash_worlds = []  # non-monotonic (hash) variant
        for gen_name in self.holdout_generators:
            for seed_off in range(self.seeds_per_world):
                seed = self.base_seed + seed_off * 1000 + hash(gen_name) % 10000
                pair = create_matched_pair(gen_name, seed, self.width, self.height)
                matched_worlds.append({
                    "features": extract_full_fingerprint(pair["continuous"], self.width, self.height),
                    "label": "continuous"})
                matched_worlds.append({
                    "features": extract_full_fingerprint(pair["computational_matched"], self.width, self.height),
                    "label": "computational"})
                
                # Hash variant: non-monotonic substrate, then histogram-match
                base = GENS[gen_name](self.width, self.height, seed)
                hash_field = apply_substrate("S_HASH", base, self.width, self.height, seed)
                hash_matched = match_histogram(hash_field, base)
                matched_hash_worlds.append({
                    "features": extract_full_fingerprint(base, self.width, self.height),
                    "label": "continuous"})
                matched_hash_worlds.append({
                    "features": extract_full_fingerprint(hash_matched, self.width, self.height),
                    "label": "computational"})
        
        for name, pool in (("matched_stats", matched_worlds),
                           ("matched_stats_hash", matched_hash_worlds)):
            predictions = [self.detector.predict(w["features"]) for w in pool]
            true_labels = [w["label"] for w in pool]
            metrics = self._compute_metrics(predictions, true_labels)
            self.results[name] = metrics
            self._log(f"  {name}: acc={metrics['accuracy']:.4f} "
                     f"bal_acc={metrics['balanced_accuracy']:.4f}")
        
        self._log("  If matched variants collapse vs generator_holdout ->")
        self._log("  detector was relying on statistic differences, not substrate.")
    
    # ========================================================================
    # PHASE 9: FEATURE ABLATION (§45)
    # ========================================================================
    
    def phase_ablation(self):
        """Feature family ablation on generator-disjoint holdout."""
        self._log("=== V5.2 FEATURE ABLATION ===")
        
        feature_sets = {
            "spatial_only": ["entropy", "moment_mean", "moment_var", "moment_skew",
                           "grad_mean", "grad_std", "lap_mean", "lap_std",
                           "anisotropy", "edge_density", "local_variance"],
            "spectral_only": ["dct_low", "dct_mid", "dct_high", "high_low_ratio",
                            "spectral_sparsity", "spectral_slope"],
            "computational_only": ["quantization_level", "repeated_value_fraction",
                                  "recurrence_exact", "recurrence_near", "recurrence_entropy",
                                  "compression_ratio", "run_length_mean", "run_length_std"],
            "precision_only": ["float64_float32_diff", "float64_float16_diff",
                             "precision_sensitivity"],
            "all_features": None,
        }
        
        train_worlds = self._get_training_worlds()
        holdout = self._get_holdout_worlds()
        
        ablation_results = {}
        for set_name, flist in feature_sets.items():
            # Train detector on subset
            abl_det = V5Detector()
            train_fv = [{k: v for k, v in w["features"].items() if not flist or k in flist}
                       for w in train_worlds]
            train_labels = [w["label"] for w in train_worlds]
            abl_det.fit(train_fv, train_labels)
            
            # Predict on holdout
            hold_fv = [{k: v for k, v in w["features"].items() if not flist or k in flist}
                      for w in holdout]
            preds = [abl_det.predict(fv) for fv in hold_fv]
            true_labels = [w["label"] for w in holdout]
            
            metrics = self._compute_metrics(preds, true_labels)
            ablation_results[set_name] = metrics
            self._log(f"  {set_name}: acc={metrics['accuracy']:.4f} "
                     f"bal_acc={metrics['balanced_accuracy']:.4f}")
        
        self.results["ablation"] = ablation_results
    
    # ========================================================================
    # PHASE 10: BOOTSTRAP CI (§52)
    # ========================================================================
    
    def phase_bootstrap(self, n_bootstrap=1000):
        """Bootstrap confidence intervals for holdout accuracy."""
        self._log("=== V5.2 BOOTSTRAP CI ===")
        
        holdout = self._get_holdout_worlds()
        predictions = [self.detector.predict(w["features"]) for w in holdout]
        true_labels = [w["label"] for w in holdout]
        
        rng = random.Random(self.base_seed)
        accuracies = []
        for _ in range(n_bootstrap):
            indices = [rng.randint(0, len(predictions) - 1) for _ in range(len(predictions))]
            correct = sum(1 for i in indices if predictions[i] == true_labels[i])
            accuracies.append(correct / len(predictions))
        
        accuracies.sort()
        mean = sum(accuracies) / len(accuracies)
        ci_lo = accuracies[int(0.025 * len(accuracies))]
        ci_hi = accuracies[int(0.975 * len(accuracies))]
        
        self.results["bootstrap"] = {"mean": mean, "ci_lower": ci_lo, "ci_upper": ci_hi}
        self._log(f"  Bootstrap accuracy: {mean:.4f} [{ci_lo:.4f}, {ci_hi:.4f}]")
    
    # ========================================================================
    # PHASE 11: FINAL STATUS (§55)
    # ========================================================================
    
    def determine_status(self):
        """Determine final V5.2 status based on all tests."""
        self._log("=== V5.2 FINAL STATUS ===")
        
        gen_hold = self.results.get("generator_holdout", {})
        sub_hold = self.results.get("substrate_holdout", {})
        label_perm = self.results.get("label_permutation", {})
        ident_null = self.results.get("identical_obs_null", {})
        matched = self.results.get("matched_stats", {})
        
        gen_bal = gen_hold.get("balanced_accuracy", 0)
        sub_bal = sub_hold.get("balanced_accuracy", 0)
        perm_acc = label_perm.get("accuracy", 0.5)
        ident_acc = ident_null.get("accuracy", 0.5)
        matched_bal = matched.get("balanced_accuracy", 0)
        matched_hash_bal = self.results.get("matched_stats_hash", {}).get("balanced_accuracy", 0)
        
        # Check criteria (§54)
        checks = {
            "generator_holdout_survives": gen_bal > 0.6,
            "substrate_holdout_survives": sub_bal > 0.6,
            "label_permutation_collapses": abs(perm_acc - 0.5) <= 0.1,
            "identical_obs_collapses": abs(ident_acc - 0.5) <= 0.02,
            "matched_stats_survives": matched_bal > 0.6,
            "matched_hash_survives": matched_hash_bal > 0.6,
        }
        
        for check, result in checks.items():
            status = "PASS" if result else "FAIL"
            self._log(f"  {check}: {status}")
        
        # Determine conclusion
        if all(checks.values()):
            final = "VALID_COMPUTATIONAL_SIGNATURE"
        elif not checks["generator_holdout_survives"]:
            final = "GENERATOR_CONFOUNDED"
        elif not checks["substrate_holdout_survives"]:
            final = "NO_GENERALIZATION"
        elif not checks["label_permutation_collapses"]:
            final = "BENCHMARK_INVALID"
        elif not checks["identical_obs_collapses"]:
            final = "BENCHMARK_INVALID"
        elif not checks["matched_stats_survives"] or not checks["matched_hash_survives"]:
            final = "QUANTIZATION_DETECTOR"
        else:
            final = "UNRESOLVED"
        
        self.results["final_status"] = final
        self._log(f"  FINAL STATUS: {final}")
        return final
    
    # ========================================================================
    # PHASE 12: REPORT (§64)
    # ========================================================================
    
    def phase_report(self):
        """Generate machine-readable metrics dump.
        ORDER (V5.2 audit): the human-owned report_v5_2.md at the project root is
        the authoritative §64 report; this phase writes only the auto dump so a
        re-run cannot clobber curated interpretation."""
        self._log("=== V5.2 REPORT (auto dump) ===")
        
        lines = []
        lines.append("# Proof of Simulation V5.2")
        lines.append("")
        lines.append("## 1. Research Question")
        lines.append("")
        lines.append("Given two observationally similar worlds generated from the same underlying")
        lines.append("mathematical content, can an observer distinguish whether the underlying")
        lines.append("computation used a continuous idealized substrate or a finite/discrete")
        lines.append("computational substrate?")
        lines.append("")
        lines.append("## 2. V5.1 Baseline")
        lines.append("")
        lines.append("V5.1 achieved 97.5% balanced accuracy on generator-disjoint holdout.")
        lines.append("V5.2 tests whether this survives adversarial controls.")
        lines.append("")
        lines.append("## 3. Counterfactual World Design")
        lines.append("")
        lines.append("Same generator, same seed, different substrate (float32/quantized/lattice/etc.)")
        lines.append("Three layers: GENERATOR -> SUBSTRATE -> OBSERVATION")
        lines.append("")
        lines.append("## 4. Generator Taxonomy")
        lines.append("")
        lines.append(f"Train: {', '.join(self.train_generators)}")
        lines.append(f"Validation: {', '.join(self.val_generators)}")
        lines.append(f"Holdout: {', '.join(self.holdout_generators)}")
        lines.append("")
        lines.append("## 5. Substrate Taxonomy")
        lines.append("")
        lines.append(f"Train substrates: {', '.join(self.train_substrates_comp)}")
        lines.append(f"Holdout substrates: {', '.join(self.holdout_substrates_comp)}")
        lines.append("")
        lines.append("## 6. Observation Model")
        lines.append("")
        lines.append(f"All worlds: {self.width}x{self.height}, float64 observation, {self.seeds_per_world} seeds")
        lines.append("")
        lines.append("## 7. Generator-Disjoint Benchmark")
        lines.append("")
        gh = self.results.get("generator_holdout", {})
        lines.append(f"- Accuracy: {gh.get('accuracy', 0):.4f}")
        lines.append(f"- Balanced accuracy: {gh.get('balanced_accuracy', 0):.4f}")
        lines.append(f"- Trivial baseline: {gh.get('trivial_baseline', 0.5):.4f}")
        lines.append("")
        lines.append("## 8. Substrate-Disjoint Benchmark")
        lines.append("")
        sh = self.results.get("substrate_holdout", {})
        lines.append(f"- Accuracy: {sh.get('accuracy', 0):.4f}")
        lines.append(f"- Balanced accuracy: {sh.get('balanced_accuracy', 0):.4f}")
        for sub, m in self.results.get("substrate_holdout_per_sub", {}).items():
            lines.append(f"- {sub}: recall={m['recall']:.4f} (n={m['n']})")
        lines.append("")
        lines.append("## 9. Matched-Statistic Adversarial Worlds")
        lines.append("")
        ms = self.results.get("matched_stats", {})
        msh = self.results.get("matched_stats_hash", {})
        lines.append(f"- Monotonic (quantized) matched: acc={ms.get('accuracy', 0):.4f} "
                     f"bal_acc={ms.get('balanced_accuracy', 0):.4f}")
        lines.append(f"- Non-monotonic (hash) matched:  acc={msh.get('accuracy', 0):.4f} "
                     f"bal_acc={msh.get('balanced_accuracy', 0):.4f}")
        lines.append("")
        lines.append("## 10. Identical-Observation Null")
        lines.append("")
        io = self.results.get("identical_obs_null", {})
        lines.append(f"- Accuracy: {io.get('accuracy', 0):.4f} (bitwise-identical obs, expected exactly 0.50)")
        lines.append("")
        lines.append("## 11. Label-Permutation Null")
        lines.append("")
        lp = self.results.get("label_permutation", {})
        lines.append(f"- Mean over {lp.get('n_perms', 1)} permutations: {lp.get('accuracy', 0):.4f} "
                     f"(min {lp.get('perm_min', 0):.4f}, max {lp.get('perm_max', 0):.4f})")
        lines.append("")
        lines.append("## 12. Feature Ablation")
        lines.append("")
        ab = self.results.get("ablation", {})
        for name, metrics in ab.items():
            lines.append(f"- {name}: bal_acc={metrics.get('balanced_accuracy', 0):.4f}")
        lines.append("")
        lines.append("## 13. Bootstrap CI")
        lines.append("")
        bs = self.results.get("bootstrap", {})
        lines.append(f"- Mean: {bs.get('mean', 0):.4f} [{bs.get('ci_lower', 0):.4f}, {bs.get('ci_upper', 0):.4f}]")
        lines.append("")
        lines.append("## 14. Leave-One-Generator-Out")
        lines.append("")
        loo_gen = self.results.get("loo_generator", {})
        for gen, m in loo_gen.items():
            lines.append(f"- {gen}: bal_acc={m.get('balanced_accuracy', 0):.4f}")
        lines.append("")
        lines.append("## 15. Leave-One-Substrate-Out")
        lines.append("")
        loo_sub = self.results.get("loo_substrate", {})
        for sub, m in loo_sub.items():
            lines.append(f"- {sub}: bal_acc={m.get('balanced_accuracy', 0):.4f}")
        lines.append("")
        lines.append("## 16. Pairwise Substrate Test")
        lines.append("")
        pw = self.results.get("pairwise_substrate", {})
        lines.append(f"- Pairwise accuracy: {pw.get('accuracy', 0):.4f}")
        lines.append(f"- Total pairs: {pw.get('total_pairs', 0)}")
        lines.append("")
        lines.append("## 17. Feature Permutation")
        lines.append("")
        fp = self.results.get("feature_permutation", {})
        for fam, m in fp.items():
            lines.append(f"- {fam}: bal_acc={m['bal_acc']:.4f} (degradation: {m['degradation']:+.4f})")
        lines.append("")
        lines.append("## 18. Observation Robustness")
        lines.append("")
        obs = self.results.get("observation_robustness", {})
        for o, m in obs.items():
            lines.append(f"- {o}: bal_acc={m.get('balanced_accuracy', 0):.4f}")
        lines.append("")
        lines.append("## 19. Feature Leakage (binned MI to generator vs substrate)")
        lines.append("")
        leak = self.results.get("feature_leakage", {})
        if leak and "mi_generator_mean" in leak:
            lines.append(f"- Mean MI(feature;generator) = {leak['mi_generator_mean']:.4f}")
            lines.append(f"- Mean MI(feature;substrate) = {leak['mi_substrate_mean']:.4f}")
            lines.append(f"- Verdict: {leak.get('verdict', 'N/A')} "
                         f"(generator information dominates substrate information)")
        else:
            lines.append("- (not run in this configuration)")
        lines.append("")
        lines.append("## 20. Unknown Computational Holdout")
        lines.append("")
        sh = self.results.get("substrate_holdout", {})
        wp = self.results.get("world_prime", {})
        if wp:
            lines.append(f"- World_PRIME detection rate: {wp.get('detection_rate', 0):.2%}")
        lines.append("")
        lines.append("## 21. Calibration")
        lines.append("")
        cal = self.results.get("calibration", {})
        if cal:
            lines.append(f"- Continuous score mean: {cal.get('continuous_scores_mean', 0):.4f}")
            lines.append(f"- Computational score mean: {cal.get('computational_scores_mean', 0):.4f}")
            lines.append(f"- Separation: {cal.get('separation', 0):.4f}")
        lines.append("")
        lines.append("## 22. Failure Analysis")
        lines.append("")
        final = self.results.get("final_status", "UNRESOLVED")
        lines.append(f"**Final Status: {final}**")
        lines.append("")
        lines.append("## 23. Reproducibility")
        lines.append("")
        lines.append(f"- Protocol hash: `{self.protocol_hash}`")
        lines.append(f"- Base seed: {self.base_seed}")
        lines.append(f"- Total worlds: {len(self.worlds)}")
        lines.append("")
        lines.append("## 24. Scientific Interpretation")
        lines.append("")
        if final == "VALID_COMPUTATIONAL_SIGNATURE":
            lines.append("The detector identifies a computational-substrate signature that survives")
            lines.append("generator holdout, matched-statistic controls, unseen substrate holdout,")
            lines.append("and null tests. This does NOT prove the universe is simulated.")
        elif final == "QUANTIZATION_DETECTOR":
            lines.append("The detector primarily detects quantization artifacts rather than")
            lines.append("computational substrate per se. Matched-statistic controls defeat it.")
        elif final == "GENERATOR_CONFOUNDED":
            lines.append("Performance disappears when generator families are held out.")
            lines.append("The detector learned generator-specific features, not substrate signatures.")
        else:
            lines.append(f"Status: {final}. See detailed results above.")
        lines.append("")
        lines.append("## 25. Limitations")
        lines.append("")
        lines.append("- Synthetic worlds only; no real data tested")
        lines.append("- 2D static fields primarily")
        lines.append("- Detector limited to interpretable methods")
        lines.append("")
        lines.append("## 26. Conclusion")
        lines.append("")
        lines.append(f"**{final}**")
        lines.append("")
        lines.append("---")
        lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append(f"*Protocol: `{self.protocol_hash}`*")
        
        os.makedirs("v5_2_artifacts", exist_ok=True)
        out_path = os.path.join("v5_2_artifacts", "report_v5_2_auto.md")
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        self._log(f"  Auto dump: {out_path} ({len(lines)} lines)")
    
    # ========================================================================
    # UTILITY: METRICS
    # ========================================================================
    
    def _compute_metrics(self, predictions, true_labels):
        """Compute full metrics with confusion matrix."""
        total = len(true_labels)
        if total == 0:
            return {"accuracy": 0, "balanced_accuracy": 0, "trivial_baseline": 0.5}
        
        correct = sum(1 for p, t in zip(predictions, true_labels) if p == t)
        accuracy = correct / total
        
        # Class counts
        n_cont = true_labels.count("continuous")
        n_comp = true_labels.count("computational")
        trivial = max(n_cont, n_comp) / total
        
        # Per-class recall
        cont_correct = sum(1 for p, t in zip(predictions, true_labels) if t == "continuous" and p == "continuous")
        comp_correct = sum(1 for p, t in zip(predictions, true_labels) if t == "computational" and p == "computational")
        recall_cont = cont_correct / n_cont if n_cont > 0 else 0
        recall_comp = comp_correct / n_comp if n_comp > 0 else 0
        balanced_acc = (recall_cont + recall_comp) / 2
        
        # Precision
        pred_cont = sum(1 for p in predictions if p == "continuous")
        pred_comp = sum(1 for p in predictions if p == "computational")
        prec_cont = cont_correct / pred_cont if pred_cont > 0 else 0
        prec_comp = comp_correct / pred_comp if pred_comp > 0 else 0
        
        # Confusion matrix
        tp_cont = cont_correct
        fn_cont = n_cont - cont_correct
        tp_comp = comp_correct
        fn_comp = n_comp - comp_correct
        fp_cont = fn_comp  # predicted continuous but actually computational
        fp_comp = fn_cont  # predicted computational but actually continuous
        
        return {
            "accuracy": accuracy,
            "balanced_accuracy": balanced_acc,
            "trivial_baseline": trivial,
            "recall_continuous": recall_cont,
            "recall_computational": recall_comp,
            "precision_continuous": prec_cont,
            "precision_computational": prec_comp,
            "n_continuous": n_cont,
            "n_computational": n_comp,
            "confusion": {
                "TP_cont": tp_cont, "FN_cont": fn_cont,
                "TP_comp": tp_comp, "FN_comp": fn_comp,
                "FP_cont": fp_cont, "FP_comp": fp_comp,
            }
        }
    
    # ========================================================================
    # MAIN RUN (with §59 checkpointing)
    # ========================================================================
    
    CKPT_PATH = "v5_2_artifacts/checkpoint.json"
    
    def _checkpoint(self, phase_name):
        """Save lightweight checkpoint (results + completed phases) after each phase."""
        os.makedirs("v5_2_artifacts", exist_ok=True)
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items() if k != "field"}
            if isinstance(obj, list):
                return [_clean(v) for v in obj]
            return obj
        state = {"completed_phase": phase_name,
                 "results": _clean(self.results),
                 "n_worlds": len(self.worlds),
                 "timestamp": datetime.now().isoformat()}
        with open(self.CKPT_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
    
    def run(self, resume_from=None):
        """Execute complete V5.2 pipeline with per-phase checkpoints (§59)."""
        self._log("=== V5.2 INIT ===")
        self._log(f"protocol={self.protocol_hash}")
        
        phases = [
            ("generate", self.phase_generate),
            ("extract", self.phase_extract_features),
            ("train", self.phase_train),
            ("generator_holdout", self.phase_generator_holdout),
            ("substrate_holdout", self.phase_substrate_holdout),
            ("label_permutation", self.phase_label_permutation),
            ("identical_obs_null", self.phase_identical_observation_null),
            ("matched_stats", self.phase_matched_statistics),
            ("ablation", self.phase_ablation),
            ("bootstrap", self.phase_bootstrap),
            ("status", self.determine_status),
            ("report", self.phase_report),
        ]
        # Resume semantics (V5.3 smoke audit fix: previous logic skipped ALL
        # phases when resume_from=None): None -> run everything;
        # "X" -> run phases AFTER checkpoint X.
        skip = resume_from is not None
        for name, fn in phases:
            if skip:
                if name == resume_from:
                    skip = False
                continue
            fn()
            self._checkpoint(name)
        
        self._log("=== V5.2 COMPLETE ===")
        return self.results.get("final_status", "UNRESOLVED")
    
    @classmethod
    def from_cache(cls, cache_file="v5_2_pipeline_cache.pkl"):
        """Load a pipeline instance from cached worlds/results (skips generation
        and feature extraction; evaluation phases must be re-run after fixes)."""
        import pickle
        with open(cache_file, "rb") as f:
            data = pickle.load(f)
        p = cls(time_budget=14400)
        p.worlds = data["worlds"]
        p.results = {}  # stale results intentionally discarded
        return p


def run_deep(time_budget=14400, resume=False):
    """Entry point for §58: python3 agent_loop.py auto --mode v5.2-deep."""
    p = V52Pipeline(time_budget=time_budget)
    resume_from = None
    if resume and os.path.exists("v5_2_artifacts/checkpoint.json"):
        with open("v5_2_artifacts/checkpoint.json", encoding="utf-8") as f:
            ckpt = json.load(f)
        resume_from = ckpt.get("completed_phase")
        # reload cached worlds if present so we can skip generation
        if os.path.exists("v5_2_pipeline_cache.pkl"):
            import pickle
            with open("v5_2_pipeline_cache.pkl", "rb") as f:
                p.worlds = pickle.load(f)["worlds"]
    status = p.run(resume_from=resume_from)
    return status is not None


if __name__ == "__main__":
    p = V52Pipeline(time_budget=14400)
    status = p.run()
    print(f"\nFINAL: {status}")
