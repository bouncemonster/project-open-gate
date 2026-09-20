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


# ================================================================
# V2 CONTROLLER — SplitMix64, V2Kernel, V2Search
# ================================================================

class SplitMix64:
    """Deterministic PRNG matching kernel SplitMix64."""
    def __init__(self, seed):
        self.state = int(seed) & 0xFFFFFFFFFFFFFFFF

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF

    def random(self):
        return (self.next_u64() >> 11) / (1 << 53)

    def randint(self, lo, hi):
        """Uniform integer in [lo, hi]."""
        return lo + (self.next_u64() % (hi - lo + 1))

    def shuffle(self, lst):
        """Fisher-Yates shuffle in place."""
        for i in range(len(lst) - 1, 0, -1):
            j = self.next_u64() % (i + 1)
            lst[i], lst[j] = lst[j], lst[i]
        return lst


def _find_kernel_bin():
    """Find WinLibs mingw64/bin for DLL resolution."""
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        base = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(base):
            for d in os.listdir(base):
                if "WinLibs" in d or "winlibs" in d:
                    candidate = os.path.join(base, d, "mingw64", "bin")
                    if os.path.isdir(candidate):
                        return candidate
    return None


def _v2_kernel_env():
    """Return env with mingw64/bin in PATH for kernel_v2 DLL resolution."""
    env = dict(os.environ)
    bindir = _find_kernel_bin()
    if bindir:
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    return env


class V2Kernel:
    """Wrapper around kernel_v2.exe subprocess calls."""

    def __init__(self, kernel_path=None):
        if kernel_path is None:
            kernel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kernel_v2.exe")
        if not os.path.isfile(kernel_path):
            raise FileNotFoundError(f"kernel_v2.exe not found: {kernel_path}")
        self.kernel_path = os.path.abspath(kernel_path)

    def _run(self, args, stdin_data=None, timeout=120):
        """Run kernel subprocess, return (stdout, stderr, returncode)."""
        env = _v2_kernel_env()
        try:
            proc = subprocess.run(
                [self.kernel_path] + args,
                capture_output=True, text=True, timeout=timeout, env=env,
                input=stdin_data
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", "TIMEOUT", -1
        except Exception as e:
            return "", str(e), -1

    def evaluate(self, cr, ci, driver, alpha=1.0, degree=2, channel=0,
                 max_iter=200, seed=7331, width=60, height=30,
                 target='TARGET_A', target_file=None, window=5, offset=1):
        """Single evaluation returning JSON dict with score, metrics, fields."""
        args = ['--evaluate',
                '--cr', f'{cr:.17g}', '--ci', f'{ci:.17g}',
                '--driver', str(driver),
                '--alpha', f'{alpha:.17g}',
                '--degree', str(degree),
                '--channel', str(channel),
                '--max-iter', str(max_iter),
                '--seed', str(seed),
                '--width', str(width), '--height', str(height),
                '--target', target,
                '--window', str(window), '--offset', str(offset)]
        if target_file:
            args += ['--target-file', target_file]
        stdout, stderr, rc = self._run(args)
        if rc != 0 or not stdout.strip():
            return {"error": stderr.strip() or f"exit {rc}", "error_code": 1, "score": 0}
        try:
            return json.loads(stdout.strip())
        except json.JSONDecodeError:
            return {"error": "invalid JSON", "raw": stdout[:500], "error_code": 1, "score": 0}

    def batch(self, candidates, width=60, height=30, target='TARGET_A',
              target_file=None, window=5, offset=1, timeout=300):
        """Batch evaluate list of candidate dicts. Returns list of result dicts."""
        args = ['--batch',
                '--width', str(width), '--height', str(height),
                '--target', target,
                '--window', str(window), '--offset', str(offset)]
        if target_file:
            args += ['--target-file', target_file]
        lines = []
        for c in candidates:
            lines.append(f"{c['candidate_id']} {c['cr']:.17g} {c['ci']:.17g} "
                        f"V2_EXPANDED_DOMAIN {c['driver']} {c.get('alpha',1.0):.17g} "
                        f"{c.get('degree',2)} {c.get('channel',0)} "
                        f"{c.get('max_iter',200)} {c.get('seed',7331)}")
        stdin_data = '\n'.join(lines) + '\n'
        stdout, stderr, rc = self._run(args, stdin_data=stdin_data, timeout=timeout)
        results = []
        for line in stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) < 16:
                results.append({"error": f"short line: {line[:100]}", "error_code": 1})
                continue
            results.append({
                "candidate_id": int(parts[0]),
                "score": float(parts[1]),
                "pearson01": float(parts[2]), "spearman01": float(parts[3]),
                "mae01": float(parts[4]), "gradient01": float(parts[5]),
                "spectral01": float(parts[6]), "autocorrelation01": float(parts[7]),
                "entropy": float(parts[8]), "anisotropy": float(parts[9]),
                "compression_ratio": float(parts[10]),
                "quantization_levels": int(parts[11]),
                "quantization_dom_frac": float(parts[12]),
                "escaped_fraction": float(parts[13]),
                "runtime_ms": float(parts[14]),
                "error_code": int(parts[15]),
            })
        return results

    def target_field(self, target_id, width=60, height=30):
        """Return flat list of target field values."""
        args = ['--target-field', '--target', target_id,
                '--width', str(width), '--height', str(height)]
        stdout, stderr, rc = self._run(args)
        if rc != 0:
            raise RuntimeError(f"target_field failed: {stderr}")
        return json.loads(stdout.strip())

    def driver_values(self, driver, max_iter=200, seed=7331, window=5, offset=1):
        """Return dict with 'values' and 'pi' arrays."""
        args = ['--driver-values', '--driver', driver,
                '--max-iter', str(max_iter), '--seed', str(seed),
                '--window', str(window), '--offset', str(offset)]
        stdout, stderr, rc = self._run(args)
        if rc != 0:
            raise RuntimeError(f"driver_values failed: {stderr}")
        return json.loads(stdout.strip())

    def score_fields(self, field, target, width, height):
        """Score two flat field arrays, return metrics dict."""
        args = ['--score-fields', '--width', str(width), '--height', str(height)]
        stdin_data = ' '.join(f'{v:.17g}' for v in field) + ' ' + ' '.join(f'{v:.17g}' for v in target) + '\n'
        stdout, stderr, rc = self._run(args, stdin_data=stdin_data)
        if rc != 0:
            raise RuntimeError(f"score_fields failed: {stderr}")
        return json.loads(stdout.strip())

    def trace(self, cr, ci, driver, max_iter=5000, alpha=1.0, degree=2, channel=0,
              seed=7331, width=60, height=30, window=5, offset=1):
        """Return list of per-iteration trace dicts."""
        args = ['--trace',
                '--cr', f'{cr:.17g}', '--ci', f'{ci:.17g}',
                '--driver', driver,
                '--alpha', f'{alpha:.17g}',
                '--degree', str(degree), '--channel', str(channel),
                '--max-iter', str(max_iter),
                '--seed', str(seed),
                '--width', str(width), '--height', str(height),
                '--window', str(window), '--offset', str(offset)]
        stdout, stderr, rc = self._run(args, timeout=300)
        if rc != 0:
            raise RuntimeError(f"trace failed: {stderr}")
        lines = stdout.strip().split('\n')
        header = lines[0].split('\t')
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split('\t')
            row = {}
            for i, h in enumerate(header):
                v = parts[i] if i < len(parts) else '0'
                # Map kernel column names to analysis.py expectations
                if h == 'iter':
                    row['iter1based'] = int(v)
                elif h in ('prime',):
                    row[h] = int(v)
                else:
                    row[h] = float(v)
            rows.append(row)
        return rows


class V2Search:
    """V2 hill-climbing search with coarse scout, multi-start, checkpoint resume.

    Protocol: 17x17 coarse scout (289 evals) → top 5 distinct basin starts →
    20 steps each (100 total steps × 9 candidates = 900 evals).
    Total: 1,189 evaluations per run.
    """

    def __init__(self, store, kernel, run_id, driver, seed=133742,
                 target='TARGET_A', target_file=None, role='PRIMARY',
                 steps=100, scout_grid=17, algorithm='HILL',
                 domain=(-2.0, 2.0, -2.0, 2.0), ui='quiet',
                 width=60, height=30, max_iter=200, alpha=1.0,
                 degree=2, channel=0):
        self.store = store
        self.kernel = kernel
        self.run_id = run_id
        self.driver = driver
        self.seed = seed
        self.target = target
        self.target_file = target_file
        self.role = role
        self.total_steps = steps
        self.scout_grid = scout_grid
        self.algorithm = algorithm
        self.domain = domain
        self.ui = ui
        self.width = width
        self.height = height
        self.max_iter = max_iter
        self.alpha = alpha
        self.degree = degree
        self.channel = 1 if driver == 'V7_IMAGINARY' else channel
        self.rng = SplitMix64(seed)

        # Search state
        self.current_cr = 0.0
        self.current_ci = 0.0
        self.current_score = -1.0
        self.best_cr = 0.0
        self.best_ci = 0.0
        self.best_score = -1.0
        self.step = 0
        self.step_size = 0.02
        self.steps_without_improvement = 0
        self.basin_starts = []
        self.current_basin = 0
        self.basin_steps = 0
        self.scout_done = False
        self.scout_results = []
        self.total_evals = 0
        self.candidate_id = 0

    def _config(self):
        return {
            "driver": self.driver, "seed": self.seed, "target": self.target,
            "role": self.role, "steps": self.total_steps, "scout_grid": self.scout_grid,
            "algorithm": self.algorithm, "domain": list(self.domain),
            "width": self.width, "height": self.height, "max_iter": self.max_iter,
            "alpha": self.alpha, "degree": self.degree, "channel": self.channel,
        }

    def _state(self):
        return {
            "current_cr": self.current_cr, "current_ci": self.current_ci,
            "current_score": self.current_score,
            "best_cr": self.best_cr, "best_ci": self.best_ci,
            "best_score": self.best_score,
            "step": self.step, "step_size": self.step_size,
            "steps_without_improvement": self.steps_without_improvement,
            "basin_starts": self.basin_starts,
            "current_basin": self.current_basin,
            "basin_steps": self.basin_steps,
            "scout_done": self.scout_done,
            "scout_results": self.scout_results,
            "total_evals": self.total_evals,
            "candidate_id": self.candidate_id,
            "rng_state": self.rng.state,
        }

    def _restore(self, state):
        self.current_cr = state["current_cr"]
        self.current_ci = state["current_ci"]
        self.current_score = state["current_score"]
        self.best_cr = state["best_cr"]
        self.best_ci = state["best_ci"]
        self.best_score = state["best_score"]
        self.step = state["step"]
        self.step_size = state["step_size"]
        self.steps_without_improvement = state["steps_without_improvement"]
        self.basin_starts = state["basin_starts"]
        self.current_basin = state["current_basin"]
        self.basin_steps = state["basin_steps"]
        self.scout_done = state["scout_done"]
        self.scout_results = state["scout_results"]
        self.total_evals = state["total_evals"]
        self.candidate_id = state["candidate_id"]
        self.rng.state = state["rng_state"]

    def _reflect(self, val, lo, hi):
        """Reflect value into [lo, hi] domain."""
        while val < lo or val > hi:
            if val < lo:
                val = 2 * lo - val
            elif val > hi:
                val = 2 * hi - val
        return val

    def _make_candidate(self, cr, ci, cid=None):
        if cid is None:
            self.candidate_id += 1
            cid = self.candidate_id
        return {
            "candidate_id": cid,
            "cr": cr, "ci": ci,
            "driver": self.driver,
            "alpha": self.alpha, "degree": self.degree,
            "channel": self.channel,
            "max_iter": self.max_iter,
            "seed": self.seed,
        }

    def _run_scout(self):
        """Coarse 17x17 grid scan."""
        cr_min, cr_max, ci_min, ci_max = self.domain
        candidates = []
        for i in range(self.scout_grid):
            for j in range(self.scout_grid):
                cr = cr_min + (cr_max - cr_min) * i / (self.scout_grid - 1)
                ci = ci_min + (ci_max - ci_min) * j / (self.scout_grid - 1)
                candidates.append(self._make_candidate(cr, ci))
        results = self.kernel.batch(candidates, width=self.width, height=self.height,
                                    target=self.target, target_file=self.target_file)
        self.scout_results = []
        for c, r in zip(candidates, results):
            entry = {**c, "result": r, "status": "OK" if r.get("error_code", 0) == 0 else "FAILED"}
            self.scout_results.append(entry)
        self.total_evals += len(candidates)
        self.scout_done = True

    def _select_basin_starts(self):
        """Top 5 distinct scout points by score."""
        valid = [(e, e["result"].get("score", -1)) for e in self.scout_results
                 if e.get("status") == "OK" and e["result"].get("score", -1) >= 0]
        valid.sort(key=lambda x: x[1], reverse=True)
        seen = set()
        self.basin_starts = []
        for e, s in valid:
            key = (round(e["cr"], 6), round(e["ci"], 6))
            if key not in seen:
                seen.add(key)
                self.basin_starts.append((e["cr"], e["ci"], s))
            if len(self.basin_starts) >= 5:
                break
        if not self.basin_starts:
            # Fallback: center of domain
            cr_min, cr_max, ci_min, ci_max = self.domain
            self.basin_starts = [((cr_min+cr_max)/2, (ci_min+ci_max)/2, 0.0)]
        self.current_basin = 0
        self.basin_steps = 0
        self.current_cr, self.current_ci, self.current_score = self.basin_starts[0]
        self.best_cr, self.best_ci, self.best_score = self.current_cr, self.current_ci, self.current_score

    def _hill_step(self):
        """One hill-climbing step: 8 neighbors + 1 mutation."""
        cr_min, cr_max, ci_min, ci_max = self.domain
        candidates = []
        # 8 compass neighbors
        for dcr, dci in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            ncr = self._reflect(self.current_cr + dcr * self.step_size, cr_min, cr_max)
            nci = self._reflect(self.current_ci + dci * self.step_size, ci_min, ci_max)
            candidates.append(self._make_candidate(ncr, nci))
        # 1 uniform mutation
        mcr = self.rng.random() * (cr_max - cr_min) + cr_min
        mci = self.rng.random() * (ci_max - ci_min) + ci_min
        candidates.append(self._make_candidate(mcr, mci))

        results = self.kernel.batch(candidates, width=self.width, height=self.height,
                                    target=self.target, target_file=self.target_file)
        evals = []
        best_local_score = self.current_score
        best_local_cr, best_local_ci = self.current_cr, self.current_ci
        for c, r in zip(candidates, results):
            status = "OK" if r.get("error_code", 0) == 0 else "FAILED"
            score = r.get("score", -1) if status == "OK" else -1
            evals.append({**c, "result": r, "status": status})
            if status == "OK" and score > best_local_score:
                best_local_score = score
                best_local_cr = c["cr"]
                best_local_ci = c["ci"]

        # Update state
        improved = best_local_score > self.current_score
        self.current_cr = best_local_cr
        self.current_ci = best_local_ci
        self.current_score = best_local_score
        if best_local_score > self.best_score:
            self.best_score = best_local_score
            self.best_cr = best_local_cr
            self.best_ci = best_local_ci
            self.steps_without_improvement = 0
        else:
            self.steps_without_improvement += 1

        # Step size adaptation
        if improved:
            self.step_size = min(0.2, self.step_size * 1.15)
        else:
            self.step_size = max(1e-5, self.step_size * 0.5)

        self.total_evals += len(evals)
        return evals

    def run(self, stop_after_steps=None):
        """Execute search. Returns best evaluation dict."""
        self.store.create_run(self.run_id, self._config())

        # Resume from checkpoint if exists
        saved_state = self.store.get_state(self.run_id)
        if saved_state:
            self._restore(saved_state)

        limit = stop_after_steps if stop_after_steps is not None else self.total_steps

        while self.step < limit:
            if not self.scout_done:
                self._run_scout()
                self._select_basin_starts()
                # Commit scout as step 0
                scout_evals = [{**e, "step": 0} for e in self.scout_results]
                self.store.commit_step(self.run_id, 0, scout_evals, self._state())
                self.step = 1
                if self.step >= limit:
                    break
                continue

            # Check basin transition
            if self.basin_steps >= 20:
                self.current_basin += 1
                self.basin_steps = 0
                if self.current_basin >= len(self.basin_starts):
                    break  # All basins exhausted
                self.current_cr, self.current_ci, self.current_score = self.basin_starts[self.current_basin]
                self.step_size = 0.02
                self.steps_without_improvement = 0

            evals = self._hill_step()
            self.basin_steps += 1
            self.step += 1
            self.store.commit_step(self.run_id, self.step, evals, self._state())

        self.store.finish_run(self.run_id, "FINISHED")

        # Return best evaluation
        rows = self.store.run_rows(self.run_id)
        ok_rows = [r for r in rows if r.get("status") == "OK" and r.get("score", -1) >= 0]
        if not ok_rows:
            return {"score": 0, "cr": 0, "ci": 0, "error": "no successful evaluations"}
        best = max(ok_rows, key=lambda r: r.get("score", 0))
        return best
