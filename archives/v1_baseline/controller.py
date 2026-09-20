"""
PROOF OF SIMULATION — Search Controller
Hill climbing with 8-direction local search, multi-start, and coarse scout.
"""
import subprocess
import json
import os
import time
import math
import sys

import db
import protocol


def _kernel_env(kernel_path):
    """Return env dict with compiler bin dir in PATH for kernel DLL resolution."""
    env = dict(os.environ)
    # If kernel is in a known location, add its dir to PATH
    kdir = os.path.dirname(os.path.abspath(kernel_path))
    env["PATH"] = kdir + os.pathsep + env.get("PATH", "")
    # Also try to find the compiler's bin dir
    import shutil
    cc = shutil.which("gcc")
    if not cc:
        # Search WinLibs
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            base = os.path.join(local, "Microsoft", "WinGet", "Packages")
            if os.path.isdir(base):
                for d in os.listdir(base):
                    if "WinLibs" in d or "winlibs" in d:
                        candidate = os.path.join(base, d, "mingw64", "bin")
                        if os.path.exists(os.path.join(candidate, "gcc.exe")):
                            env["PATH"] = candidate + os.pathsep + env["PATH"]
                            break
    elif os.path.sep in cc:
        cc_dir = os.path.dirname(os.path.abspath(cc))
        env["PATH"] = cc_dir + os.pathsep + env["PATH"]
    return env

# SplitMix64 implemented in Python for mutation PRNG
class SplitMix64:
    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF

    def uniform(self, lo=0.0, hi=1.0):
        v = self.next_u64() >> 11
        return lo + (hi - lo) * (v / (1 << 53))


# 8 search directions (cardinal + diagonal)
DIRECTIONS = [
    (1, 0), (-1, 0), (0, 1), (0, -1),
    (1, 1), (1, -1), (-1, 1), (-1, -1)
]

# Normalize diagonal directions
NORM = 1.0 / math.sqrt(2.0)
DIR_NORMS = [1, 1, 1, 1, NORM, NORM, NORM, NORM]


class SearchTrack:
    """One research track (V1 or V4)."""
    def __init__(self, model_id, driver, cr, ci, step=0.02):
        self.model_id = model_id
        self.driver = driver
        self.cr = cr
        self.ci = ci
        self.step = step
        self.best_score = 0.0
        self.best_result = None
        self.steps_without_improvement = 0
        self.total_steps = 0
        self.history = []
        self.evaluated = set()  # (cr, ci) tuples already tested

    def point_key(self, cr, ci, model_id, alpha, degree, channel, max_iter):
        return (round(cr, 8), round(ci, 8), model_id, alpha, degree, channel, max_iter)


class Controller:
    """Main search controller."""

    def __init__(self, kernel_path, run_id, proto=None):
        self.kernel_path = kernel_path
        self.run_id = run_id
        self.proto = proto or protocol.load_protocol() or protocol.DEFAULT_PROTOCOL
        self.conn = db.get_connection()
        self.candidate_counter = 0
        self.total_evals = 0

        # Search parameters from protocol
        sb = self.proto["search_budget"]
        self.max_steps = sb["max_logical_steps"]
        self.initial_step = sb["initial_step"]
        self.min_step = sb["min_step"]
        self.max_step = sb["max_step"]
        self.step_growth = sb["step_growth"]
        self.step_decay = sb["step_decay"]
        self.plateau_threshold = sb["plateau_threshold"]
        self.multi_start_after = sb["multi_start_after"]
        self.restart_points = [tuple(p) for p in sb["restart_points"]]
        self.cr_min = self.proto["search_range"]["cr_min"]
        self.cr_max = self.proto["search_range"]["cr_max"]
        self.ci_min = self.proto["search_range"]["ci_min"]
        self.ci_max = self.proto["search_range"]["ci_max"]

        # Default evaluation params
        dp = self.proto["default_params"]
        self.default_alpha = dp["alpha"]
        self.default_degree = dp["degree"]
        self.default_channel = dp["channel"]
        self.default_max_iter = dp["max_iter"]

        # Research tracks
        tracks = self.proto["research_tracks"]
        dp_cr, dp_ci = dp["cr"], dp["ci"]
        self.track_a = SearchTrack(tracks["TRACK_A"], tracks["TRACK_A"].split("_")[0],
                                   dp_cr, dp_ci, self.initial_step)
        self.track_b = SearchTrack(tracks["TRACK_B"], tracks["TRACK_B"].split("_")[0],
                                   dp_cr, dp_ci, self.initial_step)
        self.tracks = [self.track_a, self.track_b]
        self.current_track_idx = 0

        # Global best
        self.global_best_score = 0.0
        self.global_best = None
        self.global_best_snapshot_id = None

        # Mutation PRNG
        self.mutation_rng = SplitMix64(self.proto["seeds"]["mutation_seed"])

        # Timing
        self.start_time = None
        self.time_budget = self.proto["time_budget"]["default_seconds"]

        # Coarse scout
        self.scout_count = 0
        self.scout_max = sb["coarse_scout_max"]
        self.scout_grid = sb["coarse_scout_grid"]

        # Status
        self.phase = "INIT"
        self.status_messages = []

    def evaluate_batch(self, candidates):
        """
        Evaluate a batch of candidates via kernel --batch.
        candidates: list of dicts with keys: cr, ci, model_id, driver, alpha, degree, channel, max_iter
        Returns list of result dicts.
        """
        if not candidates:
            return []

        lines = []
        for c in candidates:
            self.candidate_counter += 1
            cid = self.candidate_counter
            c["candidate_id"] = cid
            line = (f"{cid} {c['cr']:.6f} {c['ci']:.6f} {c['model_id']} "
                    f"{c['driver']} {c.get('alpha', 1.0):.4f} "
                    f"{c.get('degree', 2)} {c.get('channel', 0)} "
                    f"{c.get('max_iter', 200)} {self.proto['seeds']['shuffle_seed']}")
            lines.append(line)

        stdin_data = "\n".join(lines) + "\n"
        timeout = max(5, len(candidates) * 2)

        try:
            result = subprocess.run(
                [self.kernel_path, "--batch"],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_kernel_env(self.kernel_path)
            )
            if result.returncode != 0:
                self._log(f"Kernel error: {result.stderr[:200]}")
                return []
        except subprocess.TimeoutExpired:
            self._log("Kernel timeout")
            return []
        except Exception as e:
            self._log(f"Kernel exception: {e}")
            return []

        results = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 16:
                continue
            try:
                r = {
                    "candidate_id": int(parts[0]),
                    "score": float(parts[1]),
                    "pearson01": float(parts[2]),
                    "spearman01": float(parts[3]),
                    "mae01": float(parts[4]),
                    "gradient01": float(parts[5]),
                    "spectral01": float(parts[6]),
                    "autocorrelation01": float(parts[7]),
                    "entropy": float(parts[8]),
                    "anisotropy": float(parts[9]),
                    "compression_ratio": float(parts[10]),
                    "quantization_levels": int(parts[11]),
                    "quantization_dom_frac": float(parts[12]),
                    "escaped_fraction": float(parts[13]),
                    "runtime_ms": float(parts[14]),
                    "error_code": int(parts[15])
                }
                results.append(r)
            except (ValueError, IndexError):
                continue

        self.total_evals += len(results)
        return results

    def evaluate_single(self, cr, ci, model_id, driver, alpha=1.0, degree=2,
                        channel=0, max_iter=200):
        """Evaluate a single candidate."""
        cands = [{
            "cr": cr, "ci": ci, "model_id": model_id, "driver": driver,
            "alpha": alpha, "degree": degree, "channel": channel, "max_iter": max_iter
        }]
        results = self.evaluate_batch(cands)
        if results:
            r = results[0]
            r["cr"] = cr
            r["ci"] = ci
            r["model_id"] = model_id
            r["driver"] = driver
            r["alpha"] = alpha
            r["degree"] = degree
            r["channel"] = channel
            r["max_iter"] = max_iter
            # Store in DB
            eid = db.insert_evaluation(
                self.conn, self.run_id, 0, r["candidate_id"],
                cr, ci, model_id, driver, degree, channel, alpha, max_iter,
                r["score"], r["pearson01"], r["spearman01"], r["mae01"],
                r["gradient01"], r["spectral01"], r["autocorrelation01"],
                r["entropy"], r["anisotropy"],
                r.get("quantization_dom_frac", 0),
                r["compression_ratio"], r["escaped_fraction"],
                r["runtime_ms"]
            )
            r["evaluation_id"] = eid
            return r
        return None

    def evaluate_single_at_target(self, cr, ci, model_id, driver, target_name,
                                   alpha=1.0, degree=2, channel=0, max_iter=200):
        """Evaluate at a specific target (for holdout tests) using kernel render mode."""
        env = _kernel_env(self.kernel_path)
        try:
            result = subprocess.run(
                [self.kernel_path, "--render",
                 "--cr", f"{cr:.6f}", "--ci", f"{ci:.6f}",
                 "--driver", driver,
                 "--alpha", f"{alpha:.4f}",
                 "--degree", str(degree),
                 "--channel", str(channel),
                 "--max-iter", str(max_iter),
                 "--target", target_name],
                capture_output=True, text=True, timeout=10, env=env
            )
            # Parse the Score line from render output
            for line in result.stdout.strip().split("\n"):
                if "Score:" in line:
                    parts = line.split()
                    score_idx = parts.index("Score:") + 1
                    pearson_idx = parts.index("Pearson01:") + 1
                    score = float(parts[score_idx])
                    pearson = float(parts[pearson_idx])
                    return {
                        "score": score, "pearson01": pearson,
                        "cr": cr, "ci": ci,
                        "model_id": model_id, "driver": driver,
                        "target": target_name,
                        "spearman01": 0, "mae01": 0,
                        "gradient01": 0, "spectral01": 0,
                        "autocorrelation01": 0,
                        "alpha": alpha, "degree": degree, "max_iter": max_iter
                    }
        except Exception as e:
            self._log(f"Holdout eval error: {e}")
        return None

    def _generate_candidates(self, track):
        """Generate 9 candidates: 8 directions + 1 mutation."""
        candidates = []
        step = track.step

        for i, (dx, dy) in enumerate(DIRECTIONS):
            norm = DIR_NORMS[i]
            new_cr = track.cr + dx * step * norm
            new_ci = track.ci + dy * step * norm
            # Clamp to search range
            new_cr = max(self.cr_min, min(self.cr_max, new_cr))
            new_ci = max(self.ci_min, min(self.ci_max, new_ci))
            key = track.point_key(new_cr, new_ci, track.model_id,
                                  self.default_alpha, self.default_degree,
                                  self.default_channel, self.default_max_iter)
            if key not in track.evaluated:
                candidates.append({
                    "cr": new_cr, "ci": new_ci,
                    "model_id": track.model_id, "driver": track.driver,
                    "alpha": self.default_alpha, "degree": self.default_degree,
                    "channel": self.default_channel, "max_iter": self.default_max_iter
                })

        # 1 mutation candidate
        dcr = self.mutation_rng.uniform(-step, step)
        dci = self.mutation_rng.uniform(-step, step)
        mcr = max(self.cr_min, min(self.cr_max, track.cr + dcr))
        mci = max(self.ci_min, min(self.ci_max, track.ci + dci))
        key = track.point_key(mcr, mci, track.model_id,
                              self.default_alpha, self.default_degree,
                              self.default_channel, self.default_max_iter)
        if key not in track.evaluated:
            candidates.append({
                "cr": mcr, "ci": mci,
                "model_id": track.model_id, "driver": track.driver,
                "alpha": self.default_alpha, "degree": self.default_degree,
                "channel": self.default_channel, "max_iter": self.default_max_iter
            })

        return candidates

    def _process_results(self, track, candidates, results, step_num):
        """Process batch results, update track state."""
        if not results:
            return False

        # Map results back to candidates
        cand_map = {c["candidate_id"]: c for c in candidates}
        improved = False

        for r in results:
            cid = r["candidate_id"]
            c = cand_map.get(cid)
            if not c:
                continue

            key = track.point_key(c["cr"], c["ci"], track.model_id,
                                  self.default_alpha, self.default_degree,
                                  self.default_channel, self.default_max_iter)
            track.evaluated.add(key)

            # Store evaluation in DB
            eid = db.insert_evaluation(
                self.conn, self.run_id, step_num, cid,
                c["cr"], c["ci"], track.model_id, track.driver,
                self.default_degree, self.default_channel,
                self.default_alpha, self.default_max_iter,
                r["score"], r["pearson01"], r["spearman01"], r["mae01"],
                r["gradient01"], r["spectral01"], r["autocorrelation01"],
                r["entropy"], r["anisotropy"],
                r.get("quantization_dom_frac", 0),
                r["compression_ratio"], r["escaped_fraction"],
                r["runtime_ms"]
            )
            r["evaluation_id"] = eid
            r["cr"] = c["cr"]
            r["ci"] = c["ci"]

            if r["score"] > track.best_score:
                track.best_score = r["score"]
                track.best_result = r
                track.cr = c["cr"]
                track.ci = c["ci"]
                track.steps_without_improvement = 0
                improved = True

                # Check global best
                if r["score"] > self.global_best_score:
                    self.global_best_score = r["score"]
                    self.global_best = r
                    db.mark_best(self.conn, eid)
                    snap_id = db.insert_best_snapshot(
                        self.conn, self.run_id, step_num, eid,
                        c["cr"], c["ci"], r["score"],
                        track.model_id, track.driver, self.default_max_iter
                    )
                    self.global_best_snapshot_id = snap_id
                    self.status_messages.append(">>> NEW BEST <<<")
                    db.insert_event(self.conn, "NEW_BEST", {
                        "score": r["score"], "cr": c["cr"], "ci": c["ci"],
                        "model": track.model_id
                    })
            else:
                pass  # No improvement

        if not improved:
            track.steps_without_improvement += 1

        track.total_steps += 1
        track.history.append({
            "step": step_num,
            "best_score": track.best_score,
            "cr": track.cr,
            "ci": track.ci
        })

        return improved

    def _adapt_step(self, track, improved):
        """Adapt step size based on improvement."""
        if improved:
            track.step = min(self.max_step, track.step * self.step_growth)
        else:
            track.step = max(self.min_step, track.step * self.step_decay)

    def _should_multi_start(self, track):
        """Check if we should restart from a new point."""
        return track.steps_without_improvement >= self.multi_start_after

    def _multi_start(self, track):
        """Restart from a predefined point."""
        restart_idx = (track.total_steps // self.multi_start_after) % len(self.restart_points)
        pt = self.restart_points[restart_idx]
        track.cr = pt[0]
        track.ci = pt[1]
        track.step = self.initial_step
        track.steps_without_improvement = 0
        self._log(f"Multi-start restart to ({track.cr}, {track.ci})")
        db.insert_event(self.conn, "MODEL_SWITCH", {"action": "multi_start", "cr": track.cr, "ci": track.ci})

    def _coarse_scout(self, track):
        """Run a coarse grid search to find new basins."""
        if self.scout_count >= self.scout_max:
            return False
        self.scout_count += 1
        self._log("Running coarse scout...")
        db.insert_event(self.conn, "SEARCH_START", {"type": "coarse_scout"})

        n = self.scout_grid
        candidates = []
        for iy in range(n):
            for ix in range(n):
                cr = self.cr_min + (self.cr_max - self.cr_min) * ix / (n - 1)
                ci = self.ci_min + (self.ci_max - self.ci_min) * iy / (n - 1)
                candidates.append({
                    "cr": cr, "ci": ci,
                    "model_id": track.model_id, "driver": track.driver,
                    "alpha": self.default_alpha, "degree": self.default_degree,
                    "channel": self.default_channel, "max_iter": self.default_max_iter
                })

        # Evaluate in batches of 64
        batch_size = 64
        all_results = []
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i+batch_size]
            results = self.evaluate_batch(batch)
            all_results.extend(results)

        # Find best
        if all_results:
            best = max(all_results, key=lambda r: r["score"])
            cid_map = {c["candidate_id"]: c for c in candidates}
            best_cand = cid_map.get(best["candidate_id"])
            if best_cand and best["score"] > track.best_score:
                track.cr = best_cand["cr"]
                track.ci = best_cand["ci"]
                track.best_score = best["score"]
                track.step = self.initial_step
                track.steps_without_improvement = 0
                self._log(f"Scout found better point: score={best['score']:.6f}")
                return True

        return False

    def run_search(self, track, max_steps=None, callback=None):
        """Run hill climbing search on a track."""
        steps = max_steps or self.max_steps
        self._log(f"Starting search on {track.model_id}, max_steps={steps}")
        db.insert_event(self.conn, "SEARCH_START", {"track": track.model_id})

        for step_num in range(steps):
            # Check time budget
            if self.start_time and (time.time() - self.start_time) > self.time_budget:
                self._log("Time budget exhausted")
                db.insert_event(self.conn, "STOP", {"reason": "TIME_BUDGET_EXHAUSTED"})
                break

            # Check if we need multi-start
            if self._should_multi_start(track):
                if not self._coarse_scout(track):
                    self._multi_start(track)

            # Generate and evaluate candidates
            candidates = self._generate_candidates(track)
            if not candidates:
                self._log("No new candidates (all evaluated), shrinking step")
                track.step = max(self.min_step, track.step * self.step_decay)
                if track.step <= self.min_step:
                    self._multi_start(track)
                continue

            results = self.evaluate_batch(candidates)
            improved = self._process_results(track, candidates, results, step_num)
            self._adapt_step(track, improved)

            if callback:
                callback(track, step_num, improved)

        db.insert_event(self.conn, "SEARCH_END", {
            "track": track.model_id,
            "best_score": track.best_score,
            "total_steps": track.total_steps
        })

    def run_controls(self):
        """Run control models at the global best point."""
        if not self.global_best:
            self._log("No global best to test controls against")
            return {}

        cr = self.global_best["cr"]
        ci = self.global_best["ci"]
        controls = {}

        control_models = [
            ("V0_NONE", "V0_NONE"),
            ("V2_SMOOTH", "V2_SMOOTH"),
            ("V3_CENTERED_INV_PI", "V3_CENTERED_INV_PI"),
            ("V5_SHUFFLED", "V5_SHUFFLED"),
            ("V6_REVERSED", "V6_REVERSED"),
        ]

        candidates = []
        for model_id, driver in control_models:
            candidates.append({
                "cr": cr, "ci": ci,
                "model_id": model_id, "driver": driver,
                "alpha": self.default_alpha, "degree": self.default_degree,
                "channel": self.default_channel, "max_iter": self.default_max_iter
            })

        results = self.evaluate_batch(candidates)
        for r in results:
            # Find matching model
            cid = r["candidate_id"]
            for c in candidates:
                if c.get("candidate_id") == cid:
                    controls[c["model_id"]] = r
                    # Store in DB
                    db.insert_evaluation(
                        self.conn, self.run_id, 0, cid,
                        cr, ci, c["model_id"], c["driver"],
                        self.default_degree, self.default_channel,
                        self.default_alpha, self.default_max_iter,
                        r["score"], r["pearson01"], r["spearman01"], r["mae01"],
                        r["gradient01"], r["spectral01"], r["autocorrelation01"],
                        r["entropy"], r["anisotropy"],
                        r.get("quantization_dom_frac", 0),
                        r["compression_ratio"], r["escaped_fraction"],
                        r["runtime_ms"]
                    )
                    break

        return controls

    def compute_uplifts(self, controls):
        """Compute prime uplift, order uplift, etc."""
        uplifts = {}
        best_score = self.global_best_score if self.global_best else 0

        v0_score = controls.get("V0_NONE", {}).get("score", 0)
        v1_score = best_score  # The best was found by V1 or V4 track
        v2_score = controls.get("V2_SMOOTH", {}).get("score", 0)
        v5_score = controls.get("V5_SHUFFLED", {}).get("score", 0)
        v6_score = controls.get("V6_REVERSED", {}).get("score", 0)

        uplifts["prime_uplift"] = v1_score - max(v0_score, v2_score)
        uplifts["residual_uplift"] = self.track_b.best_score - v2_score if self.track_b.best_score else 0
        uplifts["order_uplift"] = v1_score - v5_score
        uplifts["direction_uplift"] = v1_score - v6_score
        uplifts["shuffle_degradation"] = v1_score - v5_score

        return uplifts

    def get_state(self):
        """Get current state for checkpointing."""
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "global_best_score": self.global_best_score,
            "global_best": self.global_best,
            "track_a": {
                "cr": self.track_a.cr,
                "ci": self.track_a.ci,
                "step": self.track_a.step,
                "best_score": self.track_a.best_score,
                "steps_without_improvement": self.track_a.steps_without_improvement,
                "total_steps": self.track_a.total_steps
            },
            "track_b": {
                "cr": self.track_b.cr,
                "ci": self.track_b.ci,
                "step": self.track_b.step,
                "best_score": self.track_b.best_score,
                "steps_without_improvement": self.track_b.steps_without_improvement,
                "total_steps": self.track_b.total_steps
            },
            "total_evals": self.total_evals,
            "candidate_counter": self.candidate_counter,
            "scout_count": self.scout_count
        }

    def restore_state(self, state):
        """Restore from checkpoint."""
        self.phase = state.get("phase", "INIT")
        self.global_best_score = state.get("global_best_score", 0)
        self.global_best = state.get("global_best")
        self.total_evals = state.get("total_evals", 0)
        self.candidate_counter = state.get("candidate_counter", 0)
        self.scout_count = state.get("scout_count", 0)

        for track_name in ["track_a", "track_b"]:
            ts = state.get(track_name, {})
            track = getattr(self, track_name)
            track.cr = ts.get("cr", track.cr)
            track.ci = ts.get("ci", track.ci)
            track.step = ts.get("step", track.step)
            track.best_score = ts.get("best_score", 0)
            track.steps_without_improvement = ts.get("steps_without_improvement", 0)
            track.total_steps = ts.get("total_steps", 0)

    def _log(self, msg):
        """Log a message."""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, file=sys.stderr)
        try:
            with open("run.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
