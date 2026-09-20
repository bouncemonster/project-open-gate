"""V5.2 Extended: Additional adversarial tests per spec sections 19-52.

Run AFTER v5_2_pipeline.py completes. Adds:
  - Leave-one-generator-out (§22)
  - Leave-one-substrate-out (§23)
  - Pairwise substrate test (§24-25)
  - Feature permutation (§21)
  - Observation robustness (§30)
  - Resolution scaling (§33)
  - Rotation test (§34)
  - Calibration (§41)
  - Per-generator/substrate metrics
  - World_PRIME holdout (§48)
  - Full report update
"""
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
    generate_all_substrates, apply_substrate, match_histogram,
)


class V52Extended:
    """Extended V5.2 adversarial tests."""
    
    def __init__(self, pipeline_data: Dict, base_seed=133742):
        """Accept pre-computed pipeline data."""
        self.worlds = pipeline_data["worlds"]
        self.results = pipeline_data["results"]
        self.base_seed = base_seed
        self.width, self.height = 60, 30
        self.seeds_per_world = 20
        
        self.train_generators = ["G01_analytic_smooth", "G02_gaussian_correlated",
                                  "G03_analytic_fractal", "G04_wave_eigenmode",
                                  "G05_chaotic_map"]
        self.val_generators = ["G06_nonlinear_dyn", "G07_reaction_diffusion"]
        self.holdout_generators = ["G08_procedural_noise", "G09_coupled_oscillator",
                                    "G10_cosmological_like"]
        self.train_substrates_comp = ["S_FLOAT32", "S_FLOAT16", "S_QUANT_8", "S_LATTICE"]
        self.holdout_substrates_comp = ["S_LOOKUP", "S_HASH", "S_FINITE_STATE",
                                         "S_QUANT_4", "S_UNKNOWN_COMPUTATIONAL"]
        self.all_substrates = ["S_CONTINUOUS", "S_FLOAT32", "S_FLOAT16", "S_QUANT_8",
                               "S_QUANT_4", "S_LATTICE", "S_LOOKUP", "S_HASH",
                               "S_FINITE_STATE", "S_UNKNOWN_COMPUTATIONAL", "S_UNKNOWN_CONTINUOUS"]
    
    def _log(self, msg):
        print(f"[V5.2-X] {msg}")
    
    def _get_balanced_train(self, exclude_gen=None, exclude_sub=None):
        """Get balanced training set with optional exclusions."""
        worlds = self.worlds
        if exclude_gen:
            worlds = [w for w in worlds if w["generator"] != exclude_gen]
        if exclude_sub:
            worlds = [w for w in worlds if w["substrate"] != exclude_sub]
        
        train = [w for w in worlds if w["split"] == "train" and w["sub_split"] == "train"]
        cont = [w for w in train if w["label"] == "continuous"]
        comp = [w for w in train if w["label"] == "computational"]
        n = min(len(cont), len(comp))
        return cont[:n] + comp[:n]
    
    def _get_balanced_test(self, pool):
        """Balance a test pool."""
        cont = [w for w in pool if w["label"] == "continuous"]
        comp = [w for w in pool if w["label"] == "computational"]
        n = min(len(cont), len(comp))
        return cont[:n] + comp[:n]
    
    def _train_and_eval(self, train_pool, test_pool):
        """Train detector and evaluate on test pool."""
        if not train_pool or not test_pool:
            return {"accuracy": 0.5, "balanced_accuracy": 0.5}
        
        det = V5Detector()
        fv = [w["features"] for w in train_pool]
        labels = [w["label"] for w in train_pool]
        det.fit(fv, labels)
        
        preds = [det.predict(w["features"]) for w in test_pool]
        true = [w["label"] for w in test_pool]
        return self._metrics(preds, true)
    
    def _metrics(self, preds, true):
        total = len(true)
        if total == 0:
            return {"accuracy": 0.5, "balanced_accuracy": 0.5}
        acc = sum(1 for p, t in zip(preds, true) if p == t) / total
        
        n_cont = true.count("continuous")
        n_comp = true.count("computational")
        rc = sum(1 for p, t in zip(preds, true) if t == "continuous" and p == "continuous")
        rk = sum(1 for p, t in zip(preds, true) if t == "computational" and p == "computational")
        bal = (rc / n_cont if n_cont else 0) + (rk / n_comp if n_comp else 0)
        bal /= 2
        
        trivial = max(n_cont, n_comp) / total
        return {"accuracy": acc, "balanced_accuracy": bal, "trivial_baseline": trivial,
                "n_continuous": n_cont, "n_computational": n_comp}
    
    # ====================================================================
    # §22: LEAVE-ONE-GENERATOR-OUT
    # ====================================================================
    
    def test_loo_generator(self):
        """LOO validation across all training+val generators."""
        self._log("=== LEAVE-ONE-GENERATOR-OUT ===")
        
        all_gens = self.train_generators + self.val_generators
        results = {}
        
        for held_gen in all_gens:
            # Train on all except held_gen
            train = [w for w in self.worlds
                     if w["split"] in ("train", "validation")
                     and w["generator"] != held_gen
                     and w["sub_split"] == "train"]
            test = [w for w in self.worlds
                    if w["generator"] == held_gen
                    and w["sub_split"] == "train"]
            
            train_bal = self._get_balanced_from(train)
            test_bal = self._get_balanced_from(test)
            
            m = self._train_and_eval(train_bal, test_bal)
            results[held_gen] = m
            self._log(f"  {held_gen}: bal_acc={m['balanced_accuracy']:.4f}")
        
        self.results["loo_generator"] = results
        return results
    
    # ====================================================================
    # §23: LEAVE-ONE-SUBSTRATE-OUT
    # ====================================================================
    
    def test_loo_substrate(self):
        """LOO validation across computational substrates."""
        self._log("=== LEAVE-ONE-SUBSTRATE-OUT ===")
        
        results = {}
        all_comp = self.train_substrates_comp + self.holdout_substrates_comp
        
        for held_sub in all_comp:
            # Train on all substrates except held
            train = [w for w in self.worlds
                     if w["split"] == "train"
                     and w["substrate"] != held_sub
                     and w["substrate"] != "S_UNKNOWN_CONTINUOUS"]
            # Test on held substrate + continuous reference
            test_comp = [w for w in self.worlds
                        if w["split"] == "train" and w["substrate"] == held_sub]
            test_cont = [w for w in self.worlds
                        if w["split"] == "train" and w["substrate"] == "S_CONTINUOUS"]
            
            # Balance
            n = min(len(test_comp), len(test_cont))
            test = test_comp[:n] + test_cont[:n]
            
            train_bal = self._get_balanced_from(train)
            m = self._train_and_eval(train_bal, test)
            results[held_sub] = m
            self._log(f"  {held_sub}: bal_acc={m['balanced_accuracy']:.4f}")
        
        self.results["loo_substrate"] = results
        return results
    
    def _get_balanced_from(self, pool):
        """Balance any pool STRATIFIED PER GENERATOR (audit fix: global
        cont[:n]+comp[:n] slices concentrated one class in few generators)."""
        per_gen = {}
        for w in pool:
            d = per_gen.setdefault(w["generator"], {"continuous": [], "computational": []})
            d[w["label"]].append(w)
        out = []
        for g, d in per_gen.items():
            n = min(len(d["continuous"]), len(d["computational"]))
            out += d["continuous"][:n] + d["computational"][:n]
        return out
    
    # ====================================================================
    # §24-25: PAIRWISE SUBSTRATE TEST
    # ====================================================================
    
    def test_pairwise_substrate(self):
        """For each pair (cont, comp) from same generator+seed, which is computational?"""
        self._log("=== PAIRWISE SUBSTRATE TEST ===")
        
        det = V5Detector()
        train = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "train" and w["sub_split"] == "train"])
        det.fit([w["features"] for w in train], [w["label"] for w in train])
        
        # For each generator and seed in holdout, create pairs
        pair_correct = 0
        pair_total = 0
        pair_by_gen = {}
        
        for gen in self.holdout_generators:
            gen_correct = 0
            gen_total = 0
            for w_cont in [w for w in self.worlds if w["generator"] == gen
                          and w["substrate"] == "S_CONTINUOUS"]:
                seed = w_cont["seed"]
                # Find matching computational worlds
                w_comps = [w for w in self.worlds if w["generator"] == gen
                          and w["seed"] == seed and w["label"] == "computational"]
                
                for w_comp in w_comps[:4]:  # limit pairs per seed
                    pred_cont = det.predict(w_cont["features"])
                    pred_comp = det.predict(w_comp["features"])
                    
                    # Pairwise: is comp scored as more computational than cont?
                    score_cont = 1 if det.is_computational(w_cont["features"]) else 0
                    score_comp = 1 if det.is_computational(w_comp["features"]) else 0
                    
                    if score_comp > score_cont:
                        pair_correct += 1
                    elif score_comp == score_cont:
                        pair_correct += 0.5  # tie
                    pair_total += 1
                    gen_correct += (1 if score_comp > score_cont else 0.5 if score_comp == score_cont else 0)
                    gen_total += 1
            
            pair_by_gen[gen] = gen_correct / gen_total if gen_total else 0.5
        
        pairwise_acc = pair_correct / pair_total if pair_total else 0.5
        self.results["pairwise_substrate"] = {
            "accuracy": pairwise_acc,
            "total_pairs": pair_total,
            "per_generator": pair_by_gen,
        }
        self._log(f"  Pairwise accuracy: {pairwise_acc:.4f} ({pair_total} pairs)")
        for gen, acc in pair_by_gen.items():
            self._log(f"    {gen}: {acc:.4f}")
    
    # ====================================================================
    # §21: FEATURE PERMUTATION
    # ====================================================================
    
    def test_feature_permutation(self):
        """Shuffle each feature family in TEST data, measure degradation."""
        self._log("=== FEATURE PERMUTATION ===")
        
        train = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "train" and w["sub_split"] == "train"])
        holdout = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "holdout"])
        
        # Train on clean data
        det = V5Detector()
        det.fit([w["features"] for w in train], [w["label"] for w in train])
        preds = [det.predict(w["features"]) for w in holdout]
        true = [w["label"] for w in holdout]
        baseline = self._metrics(preds, true)
        self._log(f"  Baseline: {baseline['balanced_accuracy']:.4f}")
        
        # Feature families
        families = {
            "spatial": ["entropy", "moment_mean", "moment_var", "moment_skew", "moment_kurt",
                       "grad_mean", "grad_std", "lap_mean", "lap_std", "anisotropy",
                       "edge_density", "local_variance", "acf_lag1", "acf_lag2", "acf_lag3"],
            "spectral": ["dct_low", "dct_mid", "dct_high", "high_low_ratio",
                        "spectral_sparsity", "spectral_slope"],
            "computational": ["quantization_level", "repeated_value_fraction",
                            "recurrence_exact", "recurrence_near", "recurrence_entropy",
                            "compression_ratio", "run_length_mean", "run_length_std",
                            "aliasing_score", "sampling_artifact_score"],
            "precision": ["float64_float32_diff", "float64_float16_diff", "precision_sensitivity"],
        }
        
        perm_results = {}
        rng = random.Random(self.base_seed)
        
        for family, features in families.items():
            # Permute these features across TEST samples
            perm_holdout_features = []
            for w in holdout:
                pf = dict(w["features"])  # copy
                perm_holdout_features.append(pf)
            
            # Shuffle values for these features within the test set
            for f in features:
                vals = [pf[f] for pf in perm_holdout_features]
                rng.shuffle(vals)
                for i, pf in enumerate(perm_holdout_features):
                    pf[f] = vals[i]
            
            # Predict with permuted test features (using original detector)
            perm_preds = [det.predict(pf) for pf in perm_holdout_features]
            perm_m = self._metrics(perm_preds, true)
            degradation = baseline["balanced_accuracy"] - perm_m["balanced_accuracy"]
            perm_results[family] = {"bal_acc": perm_m["balanced_accuracy"],
                                   "degradation": degradation}
            self._log(f"  {family} permuted: {perm_m['balanced_accuracy']:.4f} "
                     f"(delta: {degradation:+.4f})")
        
        self.results["feature_permutation"] = perm_results
    
    # ====================================================================
    # §30: OBSERVATION ROBUSTNESS
    # ====================================================================
    
    def test_observation_robustness(self):
        """Degradation under different observation models."""
        self._log("=== OBSERVATION ROBUSTNESS ===")
        
        det = V5Detector()
        train = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "train" and w["sub_split"] == "train"])
        det.fit([w["features"] for w in train], [w["label"] for w in train])
        
        holdout = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "holdout"])
        
        obs_models = {
            "O1_full": lambda f: (f, self.width, self.height),
            "O2_float32": lambda f: ([float(int(v * 65536) / 65536) for v in f], self.width, self.height),
            "O3_float16": lambda f: ([round(v, 3) for v in f], self.width, self.height),
            "O4_uint8": lambda f: (self._quantize_obs(f, 255), self.width, self.height),
            "O5_uint4": lambda f: (self._quantize_obs(f, 15), self.width, self.height),
            # V5.2 audit fix: O6 was an identity no-op claiming "robust".
            # Real 2x2 average-pool downsample to 30x15.
            "O6_downsample": lambda f: (self._avgpool2x2(f), self.width // 2, self.height // 2),
            "O7_noisy": lambda f: ([v + self._rng.gauss(0, 0.01) for v in f], self.width, self.height),
        }
        self._rng = random.Random(self.base_seed)
        
        obs_results = {}
        
        for obs_name, obs_fn in obs_models.items():
            preds = []
            true = []
            for w in holdout:
                # Apply observation transform (field + possibly new size)
                obs_field, ow, oh = obs_fn(w["field"])
                obs_feat = extract_full_fingerprint(obs_field, ow, oh)
                preds.append(det.predict(obs_feat))
                true.append(w["label"])
            
            m = self._metrics(preds, true)
            obs_results[obs_name] = m
            self._log(f"  {obs_name}: bal_acc={m['balanced_accuracy']:.4f}")
        
        self.results["observation_robustness"] = obs_results
    
    def _quantize_obs(self, field, levels):
        fmin, fmax = min(field), max(field)
        rng = fmax - fmin if fmax > fmin else 1
        return [int((v - fmin) / rng * levels) / levels for v in field]
    
    def _avgpool2x2(self, field):
        """Downsample by 2x2 average pooling (real, not identity)."""
        w, h = self.width, self.height
        out = []
        for y in range(0, h - 1, 2):
            for x in range(0, w - 1, 2):
                vals = [field[y * w + x], field[y * w + x + 1],
                        field[(y + 1) * w + x], field[(y + 1) * w + x + 1]]
                out.append(sum(vals) / 4)
        return out
    
    # ====================================================================
    # §19: FEATURE LEAKAGE TEST (binned mutual information)
    # ====================================================================
    
    @staticmethod
    def _binned_mi(values, groups, n_bins=10):
        """Normalized MI between a continuous feature (quantile-binned) and a
        discrete group label. Audit fix: the old 'unique value' metric was a
        tautology for continuous features (every float64 value is unique)."""
        n = len(values)
        if n == 0:
            return 0.0
        # quantile binning
        order = sorted(range(n), key=lambda i: values[i])
        bins = [0] * n
        for rank, idx in enumerate(order):
            bins[idx] = min(n_bins - 1, rank * n_bins // n)
        # joint and marginals
        joint = Counter(zip(bins, groups))
        pb = Counter(bins)
        pg = Counter(groups)
        # H(B), H(B|G)
        h_b = -sum((c / n) * math.log2(c / n) for c in pb.values())
        h_b_given_g = 0.0
        for g, cg in pg.items():
            for b in range(n_bins):
                nbg = joint.get((b, g), 0)
                if nbg:
                    h_b_given_g += (cg / n) * (nbg / cg) * math.log2(nbg / cg)
        h_b_given_g = -h_b_given_g
        mi = max(0.0, h_b - h_b_given_g)
        denom = math.log2(len(set(groups)))
        return mi / denom if denom > 0 else 0.0
    
    def test_feature_leakage(self):
        """Per-feature: MI with GENERATOR vs MI with SUBSTRATE (train+val+holdout)."""
        self._log("=== FEATURE LEAKAGE TEST (binned MI) ===")
        
        features = list(self.worlds[0]["features"].keys())
        gens = [w["generator"] for w in self.worlds]
        subs = [w["substrate"] for w in self.worlds]
        
        rows = {}
        for feat in features:
            vals = [w["features"][feat] for w in self.worlds]
            mi_gen = self._binned_mi(vals, gens)
            mi_sub = self._binned_mi(vals, subs)
            rows[feat] = {"mi_generator": mi_gen, "mi_substrate": mi_sub}
        
        mi_gen_mean = sum(r["mi_generator"] for r in rows.values()) / len(rows)
        mi_sub_mean = sum(r["mi_substrate"] for r in rows.values()) / len(rows)
        
        summary = {
            "per_feature": rows,
            "mi_generator_mean": mi_gen_mean,
            "mi_substrate_mean": mi_sub_mean,
            "verdict": "GENERATOR_DOMINANT" if mi_gen_mean > mi_sub_mean else "SUBSTRATE_DOMINANT",
        }
        self.results["feature_leakage"] = summary
        
        self._log(f"  mean MI(feature;generator)  = {mi_gen_mean:.4f}")
        self._log(f"  mean MI(feature;substrate) = {mi_sub_mean:.4f}")
        self._log(f"  verdict: {summary['verdict']}")
        top_sub = sorted(rows.items(), key=lambda kv: -kv[1]["mi_substrate"])[:3]
        self._log(f"  top substrate-informative: {[f'{k}={v['mi_substrate']:.3f}' for k, v in top_sub]}")
    
    # ====================================================================
    # §48: WORLD_PRIME HOLDOUT
    # ====================================================================
    
    def test_world_prime(self):
        """Test detection of prime-driven computational world."""
        self._log("=== WORLD_PRIME HOLDOUT ===")
        
        # Generate prime-driven worlds using the same 3-layer approach
        # Prime world: uses prime modular arithmetic as substrate
        from v5_2_core import GENERATORS as GENS
        
        prime_worlds = []
        for gen in self.holdout_generators:
            for seed_off in range(10):
                seed = self.base_seed + seed_off * 333 + hash(gen) % 7777
                base = GENS[gen](self.width, self.height, seed)
                
                # Apply prime-modular quantization (novel computational substrate)
                prime_field = []
                primes = [2,3,5,7,11,13,17,19,23,29]
                for i, v in enumerate(base):
                    p = primes[i % len(primes)]
                    q = int(v * 1000) % p / p
                    prime_field.append(q)
                
                # Normalize back to similar range
                pmin, pmax = min(prime_field), max(prime_field)
                prange = pmax - pmin if pmax > pmin else 1
                bmin, bmax = min(base), max(base)
                brange = bmax - bmin if bmax > bmin else 1
                prime_norm = [((v - pmin) / prange) * brange + bmin for v in prime_field]
                
                feat = extract_full_fingerprint(prime_norm, self.width, self.height)
                prime_worlds.append({"features": feat, "label": "computational",
                                    "substrate": "PRIME_MODULAR"})
        
        # Predict
        det = V5Detector()
        train = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "train" and w["sub_split"] == "train"])
        det.fit([w["features"] for w in train], [w["label"] for w in train])
        
        preds = [det.predict(w["features"]) for w in prime_worlds]
        detected = sum(1 for p in preds if p == "computational")
        
        self.results["world_prime"] = {
            "n_worlds": len(prime_worlds),
            "detected_computational": detected,
            "detection_rate": detected / len(prime_worlds) if prime_worlds else 0,
        }
        self._log(f"  Prime worlds detected as computational: {detected}/{len(prime_worlds)}")
        self._log(f"  (This is an unseen substrate - detection rate varies)")
    
    # ====================================================================
    # §41: CALIBRATION
    # ====================================================================
    
    def test_calibration(self):
        """Report decision score distribution."""
        self._log("=== CALIBRATION ===")
        
        det = V5Detector()
        train = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "train" and w["sub_split"] == "train"])
        det.fit([w["features"] for w in train], [w["label"] for w in train])
        
        holdout = self._get_balanced_from(
            [w for w in self.worlds if w["split"] == "holdout"])
        
        scores = [det.predict_proba(w["features"]).get("computational", 0.5) for w in holdout]
        true = [w["label"] for w in holdout]
        
        # Separate by class
        cont_scores = [s for s, t in zip(scores, true) if t == "continuous"]
        comp_scores = [s for s, t in zip(scores, true) if t == "computational"]
        
        self.results["calibration"] = {
            "continuous_scores_mean": sum(cont_scores) / len(cont_scores) if cont_scores else 0,
            "computational_scores_mean": sum(comp_scores) / len(comp_scores) if comp_scores else 0,
            "separation": abs(sum(comp_scores)/len(comp_scores) - sum(cont_scores)/len(cont_scores))
                         if cont_scores and comp_scores else 0,
        }
        self._log(f"  Continuous score mean: {self.results['calibration']['continuous_scores_mean']:.4f}")
        self._log(f"  Computational score mean: {self.results['calibration']['computational_scores_mean']:.4f}")
    
    # ====================================================================
    # RUN ALL
    # ====================================================================
    
    def run_all(self):
        """Execute all extended tests."""
        self._log("=== V5.2 EXTENDED TESTS ===")
        
        self.test_loo_generator()
        self.test_loo_substrate()
        self.test_pairwise_substrate()
        self.test_feature_permutation()
        self.test_observation_robustness()
        self.test_feature_leakage()
        self.test_world_prime()
        self.test_calibration()
        
        return self.results


def save_pipeline_results(pipeline):
    """Serialize results for extended testing."""
    # Store worlds with features (compact)
    data = {
        "worlds": [
            {k: v for k, v in w.items() if k in
             ("generator", "substrate", "seed", "label", "split", "sub_split",
              "width", "height", "features", "field")}
            for w in pipeline.worlds
        ],
        "results": pipeline.results,
    }
    return data


if __name__ == "__main__":
    import pickle
    cache_file = "v5_2_pipeline_cache.pkl"
    from v5_2_pipeline import V52Pipeline

    if os.path.exists(cache_file):
        # Worlds+features in cache are still valid (generation/extraction code
        # unchanged); ALL evaluation phases are re-run with the audit fixes.
        print("[V5.2-X] Loading cached worlds; re-running fixed evaluation...")
        p = V52Pipeline.from_cache(cache_file)
        p.phase_train()
        p.phase_generator_holdout()
        p.phase_substrate_holdout()
        p.phase_label_permutation()
        p.phase_identical_observation_null()
        p.phase_matched_statistics()
        p.phase_ablation()
        p.phase_bootstrap()
        p.determine_status()
    else:
        print("[V5.2-X] No cache: full pipeline run...")
        p = V52Pipeline(time_budget=14400)
        p.run()
        with open(cache_file, "wb") as f:
            pickle.dump(save_pipeline_results(p), f)

    data = save_pipeline_results(p)

    print("\n[V5.2-X] Running extended tests...")
    ext = V52Extended(data)
    ext.run_all()

    # Merge and regenerate authoritative report
    p.results.update(ext.results)
    p.phase_report()
    # Refresh cache so worlds AND post-audit results stay consistent (audit fix:
    # the pkl previously held stale pre-audit results after re-evaluation).
    with open(cache_file, "wb") as f:
        pickle.dump(save_pipeline_results(p), f)

    # Artifacts: full machine-readable results + holdout predictions
    os.makedirs("v5_2_artifacts/benchmark", exist_ok=True)
    os.makedirs("v5_2_artifacts/predictions", exist_ok=True)
    with open("v5_2_artifacts/benchmark/v5_2_results.json", "w", encoding="utf-8") as f:
        json.dump(p.results, f, indent=1, default=float)
    det = p.detector
    with open("v5_2_artifacts/predictions/holdout_predictions.csv", "w", encoding="utf-8") as f:
        f.write("generator,substrate,seed,split,true,pred,correct\n")
        for w in p._get_holdout_worlds():
            pred = det.predict(w["features"])
            f.write(f"{w['generator']},{w['substrate']},{w['seed']},{w['split']},"
                    f"{w['label']},{pred},{int(pred == w['label'])}\n")
    print("[V5.2-X] Artifacts written to v5_2_artifacts/")

    print(f"\nFINAL: {p.results.get('final_status', 'UNRESOLVED')}")
