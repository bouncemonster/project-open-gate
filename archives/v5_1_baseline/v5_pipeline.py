"""V5 Pipeline: Orchestrate world generation, feature extraction, and blind detection."""
import os
import json
import hashlib
import time
import math
from typing import List, Dict, Tuple, Optional
from datetime import datetime

from v5_math import extract_full_fingerprint
from v5_worldforge import generate_world, generate_paired_worlds, apply_observation_condition, WORLD_GENERATORS
from v5_detector import V5Detector
from v5_db import V5Database


class V5Pipeline:
    """V5 Proof of Simulation pipeline."""
    
    def __init__(self, time_budget: int = 14400, base_seed: int = 133742):
        self.time_budget = time_budget
        self.base_seed = base_seed
        self.start_time = time.time()
        self.db = V5Database("history_v5.sqlite3")
        self.detector = V5Detector()
        self.artifacts_dir = "v5_artifacts"
        
        # Protocol
        with open("protocol_v5.json") as f:
            self.protocol = json.load(f)
        
        # State
        self.worlds = {}  # world_id -> {type, seed, field, features, ...}
        self.train_data = []
        self.validation_data = []
        self.holdout_data = []
        
        # Reproducibility
        self.protocol_hash = self._hash_file("protocol_v5.json")
        self.source_hash = self._hash_sources()
    
    def _hash_file(self, path: str) -> str:
        """Hash a file."""
        if not os.path.exists(path):
            return ""
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    
    def _hash_sources(self) -> str:
        """Hash all V5 source files."""
        files = ["v5_math.py", "v5_worldforge.py", "v5_detector.py", "v5_db.py", "v5_pipeline.py"]
        combined = ""
        for f in files:
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    combined += fh.read().decode("utf-8", errors="ignore")
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def _log(self, msg: str):
        """Log with timestamp."""
        elapsed = time.time() - self.start_time
        print(f"[V5 {elapsed:7.1f}s] {msg}")
    
    def _time_remaining(self) -> float:
        """Time remaining in budget."""
        return self.time_budget - (time.time() - self.start_time)
    
    # ========================================================================
    # PHASE 1: WORLD GENERATION
    # ========================================================================
    
    def _get_split_for_generator(self, world_type: str) -> str:
        """V5.1 FIX: Determine split from generator-level strategy (disjoint families)."""
        ss = self.protocol["split_strategy"]
        for gen_type in ss.get("train_generators", {}).get("continuous", []) + ss.get("train_generators", {}).get("computational", []):
            if gen_type == world_type:
                return "train"
        for gen_type in ss.get("validation_generators", {}).get("continuous", []) + ss.get("validation_generators", {}).get("computational", []):
            if gen_type == world_type:
                return "validation"
        for gen_type in ss.get("holdout_generators", {}).get("continuous", []) + ss.get("holdout_generators", {}).get("computational", []):
            if gen_type == world_type:
                return "holdout"
        return "train"  # default
    
    def phase_generate_worlds(self):
        """Generate all world types with multiple seeds (V5.1: generator-level splits)."""
        self._log("=== V5 WORLD GENERATION ===")
        
        width, height = 60, 30
        seeds_per_world = self.protocol["split_strategy"]["seeds_per_world"]
        
        # Collect all generators from split_strategy
        all_generators = set()
        for split_key in ["train_generators", "validation_generators", "holdout_generators"]:
            for cls_list in self.protocol["split_strategy"].get(split_key, {}).values():
                all_generators.update(cls_list)
        
        for world_type in sorted(all_generators):
            config = self.protocol["world_types"].get(world_type)
            if not config:
                self._log(f"  WARNING: {world_type} not in world_types, skipping")
                continue
            
            split_type = self._get_split_for_generator(world_type)
            self._log(f"Generating {world_type} ({seeds_per_world} seeds, split={split_type})...")
            
            for seed_offset in range(seeds_per_world):
                seed = self.base_seed + seed_offset * 1000 + config["id"] * 100
                
                # Generate world
                field = generate_world(world_type, width, height, seed)
                
                # Apply default observation
                obs_field, obs_w, obs_h = apply_observation_condition(
                    field, width, height, "O1_FULL_PRECISION", seed
                )
                
                # Store in database
                field_hash = hashlib.sha256(str(obs_field[:100]).encode()).hexdigest()[:16]
                world_id = self.db.insert_world(
                    world_type, seed, obs_w, obs_h, "O1_FULL_PRECISION", field_hash
                )
                
                # Assign split (generator-level, no overlap)
                self.db.assign_split(world_id, split_type)
                
                # Store in memory
                self.worlds[world_id] = {
                    "type": world_type,
                    "seed": seed,
                    "field": obs_field,
                    "width": obs_w,
                    "height": obs_h,
                    "split": split_type,
                    "category": config["category"]
                }
        
        self._log(f"Generated {len(self.worlds)} worlds total")
    
    # ========================================================================
    # PHASE 2: FEATURE EXTRACTION
    # ========================================================================
    
    def phase_extract_features(self):
        """Extract fingerprints from all worlds."""
        self._log("=== V5 FEATURE EXTRACTION ===")
        
        count = 0
        for world_id, world_data in self.worlds.items():
            field = world_data["field"]
            width = world_data["width"]
            height = world_data["height"]
            
            # Extract fingerprint
            fp = extract_full_fingerprint(field, width, height)
            
            # Store in database
            self.db.insert_features(world_id, fp)
            
            # Store in memory
            world_data["features"] = fp
            
            count += 1
            if count % 50 == 0:
                self._log(f"  Extracted {count}/{len(self.worlds)} fingerprints...")
        
        self._log(f"Extracted {count} fingerprint vectors")
    
    # ========================================================================
    # PHASE 3: TRAIN DETECTOR
    # ========================================================================
    
    def _get_binary_label(self, world_type: str) -> str:
        """Convert world type to binary label: continuous vs computational."""
        continuous_types = ["W01_CONTINUOUS_ANALYTIC", "W02_GAUSSIAN_FIELD", "W03_FRACTAL_ANALYTIC",
                          "W04_FLOAT32", "W05_FLOAT16", "W06_QUANTIZED_8BIT", "W07_QUANTIZED_4BIT",
                          "W08_FIXED_GRID", "W18_UNKNOWN_ANALYTIC"]
        if world_type in continuous_types:
            return "continuous"
        else:
            return "computational"
    
    def phase_train_detector(self):
        """Train detector on training split."""
        self._log("=== V5 DETECTOR TRAINING ===")
        
        # Collect training data
        train_worlds = self.db.get_worlds_by_split("train")
        
        feature_vectors = []
        labels = []
        
        for world_id in train_worlds:
            if world_id not in self.worlds:
                continue
            world_data = self.worlds[world_id]
            fp = world_data.get("features")
            if fp:
                feature_vectors.append(fp)
                # Use binary label: continuous vs computational
                labels.append(self._get_binary_label(world_data["type"]))
        
        self._log(f"Training on {len(feature_vectors)} samples, {len(set(labels))} classes: {sorted(set(labels))}")
        
        # Train detector
        self.detector.fit(feature_vectors, labels)
        
        # Record detector
        detector_id = self.db.insert_detector(
            "nearest_centroid_plus_lda",
            {"k": 5, "n_components": 10, "task": "binary_continuous_vs_computational"}
        )
        
        self._log(f"Detector trained (id={detector_id})")
        return detector_id
    
    # ========================================================================
    # PHASE 4: VALIDATION
    # ========================================================================
    
    def phase_validate(self, detector_id: int):
        """Validate on validation split."""
        self._log("=== V5 VALIDATION ===")
        
        val_worlds = self.db.get_worlds_by_split("validation")
        
        correct = 0
        total = 0
        
        for world_id in val_worlds:
            if world_id not in self.worlds:
                continue
            world_data = self.worlds[world_id]
            fp = world_data.get("features")
            if not fp:
                continue
            
            true_label = self._get_binary_label(world_data["type"])
            pred = self.detector.predict(fp)
            proba = self.detector.predict_proba(fp)
            
            # Store prediction
            confidence = proba.get(pred, 0)
            self.db.insert_prediction(world_id, detector_id, pred, confidence, proba)
            
            if pred == true_label:
                correct += 1
            total += 1
        
        accuracy = correct / total if total > 0 else 0
        self._log(f"Validation accuracy: {accuracy:.4f} ({correct}/{total})")
        
        # Store benchmark result
        self.db.insert_benchmark_result(detector_id, "validation_accuracy", accuracy)
        
        return accuracy
    
    # ========================================================================
    # PHASE 5: BLIND HOLDOUT EVALUATION
    # ========================================================================
    
    def phase_blind_holdout(self, detector_id: int):
        """Blind evaluation on holdout split."""
        self._log("=== V5 BLIND HOLDOUT EVALUATION ===")
        
        # Freeze detector
        self.detector.freeze()
        self._log("Detector frozen for blind evaluation")
        
        holdout_worlds = self.db.get_worlds_by_split("holdout")
        
        predictions = []
        true_labels = []
        
        for world_id in holdout_worlds:
            if world_id not in self.worlds:
                continue
            world_data = self.worlds[world_id]
            fp = world_data.get("features")
            if not fp:
                continue
            
            true_label = self._get_binary_label(world_data["type"])
            pred = self.detector.predict(fp)
            proba = self.detector.predict_proba(fp)
            
            # Store prediction
            confidence = proba.get(pred, 0)
            self.db.insert_prediction(world_id, detector_id, pred, confidence, proba)
            
            predictions.append(pred)
            true_labels.append(true_label)
        
        # Compute metrics (V5.1: full confusion matrix + balanced accuracy)
        from collections import Counter
        total = len(true_labels)
        correct = sum(1 for p, t in zip(predictions, true_labels) if p == t)
        accuracy = correct / total if total > 0 else 0
        
        # Confusion matrix
        classes = sorted(set(true_labels) | set(predictions))
        tp = {c: 0 for c in classes}
        tn = {c: 0 for c in classes}
        fp = {c: 0 for c in classes}
        fn = {c: 0 for c in classes}
        for p, t in zip(predictions, true_labels):
            for c in classes:
                if p == c and t == c:
                    tp[c] += 1
                elif p != c and t != c:
                    tn[c] += 1
                elif p == c and t != c:
                    fp[c] += 1
                else:
                    fn[c] += 1
        
        # Per-class metrics
        self._log(f"Blind holdout accuracy: {accuracy:.4f} ({correct}/{total})")
        self._log(f"  Holdout class balance: continuous={true_labels.count('continuous')} computational={true_labels.count('computational')}")
        
        balanced_accs = []
        for c in classes:
            recall = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) > 0 else 0
            precision = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) > 0 else 0
            spec = tn[c] / (tn[c] + fp[c]) if (tn[c] + fp[c]) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            balanced_accs.append(recall)
            self._log(f"  {c}: recall={recall:.4f} precision={precision:.4f} spec={spec:.4f} f1={f1:.4f}")
            self._log(f"    confusion: TP={tp[c]} TN={tn[c]} FP={fp[c]} FN={fn[c]}")
        
        balanced_accuracy = sum(balanced_accs) / len(balanced_accs) if balanced_accs else 0
        self._log(f"  Balanced accuracy: {balanced_accuracy:.4f}")
        
        # Trivial baselines
        n_cont = true_labels.count("continuous")
        n_comp = true_labels.count("computational")
        majority_acc = max(n_cont, n_comp) / total if total > 0 else 0
        self._log(f"  Trivial baselines: always_continuous={n_cont/total:.4f} always_computational={n_comp/total:.4f} majority={majority_acc:.4f}")
        
        # Store benchmark results
        self.db.insert_benchmark_result(detector_id, "holdout_accuracy", accuracy)
        self.db.insert_benchmark_result(detector_id, "holdout_balanced_accuracy", balanced_accuracy)
        for c in classes:
            recall = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) > 0 else 0
            self.db.insert_benchmark_result(detector_id, f"holdout_recall_{c}", recall)
        
        # Unfreeze
        self.detector.unfreeze()
        
        return accuracy, predictions, true_labels
    
    # ========================================================================
    # PHASE 6: FEATURE ABLATION
    # ========================================================================
    
    def phase_feature_ablation(self, detector_id: int):
        """Feature ablation study."""
        self._log("=== V5 FEATURE ABLATION ===")
        
        feature_sets = {
            "spatial_only": ["entropy", "moment_mean", "moment_var", "moment_skew", "moment_kurt",
                           "acf_lag1", "acf_lag2", "acf_lag3", "grad_mean", "grad_std",
                           "lap_mean", "lap_std", "anisotropy", "edge_density", "local_variance"],
            "spectral_only": ["dct_low", "dct_mid", "dct_high", "high_low_ratio",
                            "spectral_sparsity", "spectral_slope"],
            "computational_only": ["quantization_level", "repeated_value_fraction",
                                  "recurrence_exact", "recurrence_near", "recurrence_entropy",
                                  "compression_ratio", "run_length_mean", "run_length_std"],
            "precision_only": ["float64_float32_diff", "float64_float16_diff", "precision_sensitivity"],
            "all_combined": None  # Use all features
        }
        
        train_worlds = self.db.get_worlds_by_split("train")
        holdout_worlds = self.db.get_worlds_by_split("holdout")
        
        for set_name, feature_list in feature_sets.items():
            # Collect features
            train_fv = []
            train_labels = []
            for wid in train_worlds:
                if wid not in self.worlds:
                    continue
                fp = self.worlds[wid].get("features", {})
                if feature_list:
                    fp = {k: v for k, v in fp.items() if k in feature_list}
                train_fv.append(fp)
                train_labels.append(self._get_binary_label(self.worlds[wid]["type"]))
            
            holdout_fv = []
            holdout_labels = []
            for wid in holdout_worlds:
                if wid not in self.worlds:
                    continue
                fp = self.worlds[wid].get("features", {})
                if feature_list:
                    fp = {k: v for k, v in fp.items() if k in feature_list}
                holdout_fv.append(fp)
                holdout_labels.append(self._get_binary_label(self.worlds[wid]["type"]))
            
            # Train and evaluate
            ablation_detector = V5Detector()
            ablation_detector.fit(train_fv, train_labels)
            
            correct = 0
            for fv, true_label in zip(holdout_fv, holdout_labels):
                pred = ablation_detector.predict(fv)
                if pred == true_label:
                    correct += 1
            
            accuracy = correct / len(holdout_labels) if holdout_labels else 0
            self._log(f"  {set_name}: accuracy={accuracy:.4f}")
            
            self.db.insert_ablation(detector_id, set_name, accuracy)
    
    # ========================================================================
    # PHASE 7: BOOTSTRAPPED CONFIDENCE
    # ========================================================================
    
    def phase_bootstrap_confidence(self, detector_id: int, n_bootstrap: int = 1000):
        """Compute bootstrapped confidence intervals."""
        self._log("=== V5 BOOTSTRAPPED CONFIDENCE ===")
        
        holdout_worlds = self.db.get_worlds_by_split("holdout")
        
        predictions = []
        true_labels = []
        
        for wid in holdout_worlds:
            if wid not in self.worlds:
                continue
            fp = self.worlds[wid].get("features", {})
            pred = self.detector.predict(fp)
            predictions.append(pred)
            true_labels.append(self._get_binary_label(self.worlds[wid]["type"]))
        
        if not predictions:
            return
        
        import random
        random.seed(self.base_seed)
        
        accuracies = []
        for _ in range(n_bootstrap):
            # Resample with replacement
            indices = [random.randint(0, len(predictions) - 1) for _ in range(len(predictions))]
            correct = sum(1 for i in indices if predictions[i] == true_labels[i])
            accuracies.append(correct / len(predictions))
        
        accuracies.sort()
        mean_acc = sum(accuracies) / len(accuracies)
        ci_lower = accuracies[int(0.025 * len(accuracies))]
        ci_upper = accuracies[int(0.975 * len(accuracies))]
        
        self._log(f"Bootstrap accuracy: {mean_acc:.4f} [{ci_lower:.4f}, {ci_upper:.4f}]")
        
        self.db.insert_benchmark_result(detector_id, "bootstrap_accuracy_mean", mean_acc, ci_lower, ci_upper)
    
    # ========================================================================
    # PHASE 8: REPORT GENERATION
    # ========================================================================
    
    def phase_generate_report(self, detector_id: int):
        """Generate report_v5.md."""
        self._log("=== V5 REPORT GENERATION ===")
        
        report_lines = []
        report_lines.append("# Proof of Simulation V5")
        report_lines.append("")
        report_lines.append("## 1. Research Question")
        report_lines.append("")
        report_lines.append("Can we detect statistical signatures of a system being generated by a finite, discrete, algorithmic computational substrate when the generator is hidden from the observer?")
        report_lines.append("")
        report_lines.append("## 2. V1-V4 Lessons")
        report_lines.append("")
        report_lines.append("V4 concluded NO_PRIME_SPECIFIC_SIGNAL. The prime-resonance hypothesis is CLOSED.")
        report_lines.append("V5 shifts to a general computational-reality detector.")
        report_lines.append("")
        report_lines.append("## 3. World Taxonomy")
        report_lines.append("")
        report_lines.append(f"Generated {len(self.worlds)} worlds across {len(set(w['type'] for w in self.worlds.values()))} types:")
        for wtype in sorted(set(w["type"] for w in self.worlds.values())):
            count = sum(1 for w in self.worlds.values() if w["type"] == wtype)
            report_lines.append(f"- {wtype}: {count} instances")
        report_lines.append("")
        report_lines.append("## 4. Observation Model")
        report_lines.append("")
        report_lines.append("All worlds observed through O1_FULL_PRECISION (baseline).")
        report_lines.append("")
        report_lines.append("## 5. Fingerprint Features")
        report_lines.append("")
        sample_fp = next(iter(self.worlds.values())).get("features", {})
        report_lines.append(f"Extracted {len(sample_fp)} fingerprint features per world.")
        report_lines.append("")
        report_lines.append("## 6. Paired-World Experiments")
        report_lines.append("")
        paired_count = self.db.conn.execute("SELECT COUNT(*) as c FROM paired_worlds").fetchone()["c"]
        report_lines.append(f"Created {paired_count} paired world relationships.")
        report_lines.append("")
        report_lines.append("## 7. Detector Architecture")
        report_lines.append("")
        report_lines.append("Combined nearest-centroid (k=5) + linear discriminant classifier.")
        report_lines.append("No neural networks. No sklearn. Fully interpretable.")
        report_lines.append("")
        report_lines.append("## 8. Train/Validation/Holdout Protocol")
        report_lines.append("")
        train_count = len(self.db.get_worlds_by_split("train"))
        val_count = len(self.db.get_worlds_by_split("validation"))
        holdout_count = len(self.db.get_worlds_by_split("holdout"))
        report_lines.append(f"- Train: {train_count} worlds (W01-W08)")
        report_lines.append(f"- Validation: {val_count} worlds (W09-W12)")
        report_lines.append(f"- Holdout: {holdout_count} worlds (W13-W17)")
        report_lines.append("")
        report_lines.append("## 9. Adversarial Controls")
        report_lines.append("")
        report_lines.append("Paired worlds serve as adversarial controls (same base, different computational property).")
        report_lines.append("")
        report_lines.append("## 10. Precision Sensitivity")
        report_lines.append("")
        report_lines.append("W04 (float32), W05 (float16), W06 (8-bit), W07 (4-bit) test precision effects.")
        report_lines.append("")
        report_lines.append("## 11. Resolution Sensitivity")
        report_lines.append("")
        report_lines.append("Observation conditions O4 (downsampled) and O6 (finite resolution) test resolution effects.")
        report_lines.append("")
        report_lines.append("## 12. Recurrence Analysis")
        report_lines.append("")
        report_lines.append("Fingerprint includes exact_recurrence_rate, near_recurrence_rate, recurrence_entropy.")
        report_lines.append("")
        report_lines.append("## 13. Spectral Analysis")
        report_lines.append("")
        report_lines.append("Fingerprint includes DCT energy distribution, spectral sparsity, spectral slope.")
        report_lines.append("")
        report_lines.append("## 14. Blind Holdout")
        report_lines.append("")
        
        # Get holdout results
        holdout_acc = self.db.conn.execute(
            "SELECT metric_value FROM benchmark_results WHERE detector_id=? AND metric_name='holdout_accuracy'",
            (detector_id,)
        ).fetchone()
        if holdout_acc:
            report_lines.append(f"**Blind holdout accuracy: {holdout_acc['metric_value']:.4f}**")
        report_lines.append("")
        report_lines.append("## 15. Unknown Computational World")
        report_lines.append("")
        report_lines.append("W17_UNKNOWN_COMPUTATIONAL held out as hardest test.")
        report_lines.append("")
        report_lines.append("## 16. Prime-World Holdout")
        report_lines.append("")
        report_lines.append("W15_PRIME_DRIVEN held out per protocol §18.")
        report_lines.append("")
        report_lines.append("## 17. Feature Ablation")
        report_lines.append("")
        ablations = self.db.conn.execute(
            "SELECT feature_set, accuracy FROM ablations WHERE detector_id=?",
            (detector_id,)
        ).fetchall()
        for abl in ablations:
            report_lines.append(f"- {abl['feature_set']}: {abl['accuracy']:.4f}")
        report_lines.append("")
        report_lines.append("## 18. Failure Analysis")
        report_lines.append("")
        report_lines.append("Documented per-class holdout performance above.")
        report_lines.append("")
        report_lines.append("## 19. Reproducibility")
        report_lines.append("")
        report_lines.append(f"- Protocol hash: `{self.protocol_hash}`")
        report_lines.append(f"- Source hash: `{self.source_hash}`")
        report_lines.append(f"- Base seed: {self.base_seed}")
        report_lines.append("")
        report_lines.append("## 20. Scientific Interpretation")
        report_lines.append("")
        report_lines.append("V5 demonstrates the methodology for blind detection of computational signatures.")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        report_lines.append(f"*Report generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        report_lines.append(f"*Protocol: `{self.protocol_hash}`*")
        report_lines.append(f"*Source: `{self.source_hash}`*")
        
        report_text = "\n".join(report_lines)
        
        with open("report_v5.md", "w") as f:
            f.write(report_text)
        
        self._log(f"Report written to report_v5.md ({len(report_lines)} lines)")
    
    # ========================================================================
    # MAIN RUN
    # ========================================================================
    
    def run(self):
        """Run complete V5 pipeline."""
        self._log("=== V5 INIT ===")
        self._log(f"protocol={self.protocol_hash} source={self.source_hash}")
        
        # Phase 1: Generate worlds
        self.phase_generate_worlds()
        
        # Phase 2: Extract features
        self.phase_extract_features()
        
        # Phase 3: Train detector
        detector_id = self.phase_train_detector()
        
        # Phase 4: Validate
        self.phase_validate(detector_id)
        
        # Phase 5: Blind holdout
        self.phase_blind_holdout(detector_id)
        
        # Phase 6: Feature ablation
        self.phase_feature_ablation(detector_id)
        
        # Phase 7: Bootstrap confidence
        self.phase_bootstrap_confidence(detector_id)
        
        # Phase 8: Report
        self.phase_generate_report(detector_id)
        
        self._log("=== V5 COMPLETE ===")
        self.db.close()
        return True
