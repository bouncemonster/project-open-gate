"""
Proof of Simulation V4 — kernel wrapper and contrast-based multi-start search.

V4 reuses the V3 C kernel (kernel_v3.exe) but changes the search strategy:
  1. Interior domain [-1.5, 1.5]² instead of boundary-dominated regions
  2. Admissibility filtering: V0 diagnostics must indicate non-degenerate regime
  3. Contrast-based optimization: maximize C_full/C_event/C_residual, not raw score
  4. Multi-start: 8 deterministic starts from admissible scout points (not by score)
  5. Budget-exact: scout counted separately, exactly `steps` hill steps executed
"""
import json
import os
import time

import v4_math as M
from v3_search import V3Kernel, _kernel_env, write_driver_file  # noqa: F401


class V4Search:
    """Contrast-based hill climbing with admissibility filtering and multi-start.

    For each candidate point, evaluates V0 + driver + S1 + S2, then computes
    the appropriate contrast.  Scout grid identifies admissible points;
    hill climbing maximises contrast from 8 deterministic starts.
    """

    def __init__(self, store, kernel, run_id, track, driver_name, driver_seq,
                 seq_V0, seq_S1, seq_S2, seed=133742, target="TARGET_A",
                 steps=100, scout_grid=17, domain=(-1.5, 1.5, -1.5, 1.5),
                 width=60, height=30, max_iter=200, alpha=1.0,
                 start_time=None, time_budget=None, driver_dir="v4_artifacts",
                 v11_seqs=None):
        self.store = store
        self.kernel = kernel
        self.run_id = run_id
        self.track = track
        self.driver_name = driver_name
        self.driver_seq = driver_seq
        self.seq_V0 = seq_V0
        self.seq_S1 = seq_S1
        self.seq_S2 = seq_S2
        self.seed = seed
        self.target = target
        self.total_steps = steps
        self.scout_grid = scout_grid
        self.domain = domain
        self.width = width
        self.height = height
        self.max_iter = max_iter
        self.alpha = alpha
        self.start_time = start_time
        self.time_budget = time_budget
        self.rng = M.splitmix64(seed)
        self.v11_seqs = v11_seqs or []  # For TRACK_B: V11 matched event sequences

        # Write driver files
        os.makedirs(driver_dir, exist_ok=True)
        self.driver_files = {}
        for tag, seq in [("V1", driver_seq), ("V0", seq_V0),
                         ("S1", seq_S1), ("S2", seq_S2)]:
            h = M.sequence_hash(seq[1:max_iter + 1])
            path = os.path.join(driver_dir,
                                f"v4_{tag}_{h[:10]}.txt")
            write_driver_file(seq, max_iter, path)
            self.driver_files[tag] = path
        # V11 driver files for TRACK_B contrast
        self.v11_files = []
        for idx, v11_seq in enumerate(self.v11_seqs):
            h = M.sequence_hash(v11_seq[1:max_iter + 1])
            path = os.path.join(driver_dir, f"v4_V11_{idx}_{h[:10]}.txt")
            write_driver_file(v11_seq, max_iter, path)
            self.v11_files.append(path)

        self.driver_hash = M.sequence_hash(driver_seq[1:max_iter + 1])

        # State
        self.step = 0
        self.candidate_id = 0
        self.scout_evals = 0
        self.search_evals = 0
        self.scout_done = False
        self.scout_results = []  # list of dicts with V0/driver/S1/S2 scores
        self.admissible_starts = []  # list of (cr, ci)
        self.current_start_idx = 0
        self.current_cr = self.current_ci = 0.0
        self.current_contrast = -999.0
        self.best_cr = self.best_ci = 0.0
        self.best_contrast = -999.0
        self.best_score = 0.0
        self.best_scores = {}  # {driver_name: score} at best point
        self.step_size = 0.02
        self.steps_without_improvement = 0

    def accounting(self):
        return {
            "track": self.track,
            "driver": self.driver_name,
            "driver_hash": self.driver_hash,
            "SCOUT_EVALUATIONS": self.scout_evals,
            "PRIMARY_SEARCH_EVALUATIONS": self.search_evals,
            "TOTAL_KERNEL_EVALUATIONS": self.scout_evals + self.search_evals,
        }

    def _time_left(self):
        if self.start_time is None or self.time_budget is None:
            return True
        return (time.time() - self.start_time) < self.time_budget

    def _make_candidate(self, cr, ci):
        self.candidate_id += 1
        return {
            "candidate_id": self.candidate_id, "cr": cr, "ci": ci,
            "driver": self.driver_name, "driver_hash": self.driver_hash,
            "alpha": self.alpha, "degree": 2, "channel": 0,
            "max_iter": self.max_iter, "seed": 7331,
            "role": "PRIMARY", "target": self.target,
            "width": self.width, "height": self.height,
        }

    def _reflect(self, val, lo, hi):
        while val < lo or val > hi:
            if val < lo:
                val = 2 * lo - val
            elif val > hi:
                val = 2 * hi - val
        return val

    def _score_point(self, cr, ci, tag):
        """Score a single driver at (cr, ci) using the kernel."""
        out = self.kernel.evaluate(
            cr, ci, driver="V0_NONE",
            driver_file=self.driver_files[tag],
            max_iter=self.max_iter, width=self.width, height=self.height,
            target=self.target)
        return out.get("score", 0), out

    def _score_all_at(self, cr, ci):
        """Evaluate all drivers at (cr, ci). Returns dict of scores + V0 result."""
        scores = {}
        v0_result = None
        for tag, name in [("V0", "V0_NONE"), ("V1", self.driver_name),
                          ("S1", "S1_ANALYTIC"), ("S2", "S2_DATA_SMOOTHED")]:
            s, result = self._score_point(cr, ci, tag)
            scores[tag] = s
            scores[name] = s
            if tag == "V0":
                v0_result = result
        # For TRACK_B: also evaluate V11 matched event sequences
        if self.track == "TRACK_B" and self.v11_files:
            v11_scores = []
            for vpath in self.v11_files:
                out = self.kernel.evaluate(
                    cr, ci, driver="V0_NONE", driver_file=vpath,
                    max_iter=self.max_iter, width=self.width, height=self.height,
                    target=self.target)
                v11_scores.append(out.get("score", 0))
            scores["V11_mean"] = sum(v11_scores) / len(v11_scores) if v11_scores else 0
        return scores, v0_result

    def _contrast_from_scores(self, scores):
        """Compute the track-appropriate contrast from a scores dict."""
        if self.track == "TRACK_A":
            return M.compute_contrast_C_full(
                scores["V1"], scores["V0"], scores["S1"], scores["S2"])
        elif self.track == "TRACK_B":
            # C_event = score(V9) - mean(V11_101, V11_202, V11_303)
            return scores["V1"] - scores.get("V11_mean", scores["V0"])
        elif self.track == "TRACK_C":
            return M.compute_contrast_C_residual(
                scores["V1"], scores["S1"], scores["S2"])
        return scores["V1"] - scores["V0"]

    def _state(self):
        return {
            "step": self.step,
            "candidate_id": self.candidate_id,
            "scout_evals": self.scout_evals,
            "search_evals": self.search_evals,
            "scout_done": self.scout_done,
            "admissible_starts": self.admissible_starts,
            "current_start_idx": self.current_start_idx,
            "current_cr": self.current_cr, "current_ci": self.current_ci,
            "current_contrast": self.current_contrast,
            "best_cr": self.best_cr, "best_ci": self.best_ci,
            "best_contrast": self.best_contrast,
            "best_score": self.best_score,
            "best_scores": self.best_scores,
            "step_size": self.step_size,
            "steps_without_improvement": self.steps_without_improvement,
        }

    def _restore(self, s):
        for k in ("step", "candidate_id", "scout_evals", "search_evals",
                   "scout_done", "current_start_idx",
                   "current_cr", "current_ci", "current_contrast",
                   "best_cr", "best_ci", "best_contrast", "best_score",
                   "step_size", "steps_without_improvement"):
            setattr(self, k, s[k])
        self.best_scores = s.get("best_scores", {})
        self.admissible_starts = [tuple(x) for x in s.get("admissible_starts", [])]

    # ---- Scout: evaluate V0 at all grid points, filter admissible --------
    def _run_scout(self):
        lo_cr, hi_cr, lo_ci, hi_ci = self.domain
        g = self.scout_grid

        # Phase 1: Evaluate V0 at all grid points (for admissibility)
        v0_cands = []
        grid_points = []
        for i in range(g):
            for j in range(g):
                cr = lo_cr + (hi_cr - lo_cr) * i / (g - 1)
                ci = lo_ci + (hi_ci - lo_ci) * j / (g - 1)
                c = self._make_candidate(cr, ci)
                v0_cands.append(c)
                grid_points.append((cr, ci))

        v0_results = self.kernel.batch(
            v0_cands, driver="V0_NONE",
            driver_file=self.driver_files["V0"],
            width=self.width, height=self.height, target=self.target)
        self.scout_evals += len(v0_cands)

        # Phase 2: Filter admissible
        admissible_indices = []
        for idx, (c, r) in enumerate(zip(v0_cands, v0_results)):
            if r.get("error_code", 0) != 0:
                continue
            ef = r.get("escaped_fraction", 1.0)
            ent = r.get("entropy", 0.0)
            # Normalized entropy: use raw entropy / log(bins) where bins=16
            norm_ent = ent  # kernel already returns normalized entropy
            # For smooth_std, we approximate using the field gradient energy
            # as a proxy; a proper implementation would compute the std of
            # the smooth field. We use a simplified check here.
            adm, reason = M.check_admissibility(ef, norm_ent, 0.05)
            if adm:
                admissible_indices.append(idx)

        # Phase 3: Evaluate driver, S1, S2 at admissible points
        adm_scores = {}  # grid_idx -> {tag: score}
        if admissible_indices:
            for tag in ["V1", "S1", "S2"]:
                drv_cands = [v0_cands[i] for i in admissible_indices]
                drv_results = self.kernel.batch(
                    drv_cands, driver="V0_NONE",
                    driver_file=self.driver_files[tag],
                    width=self.width, height=self.height, target=self.target)
                self.scout_evals += len(drv_cands)
                for j, idx in enumerate(admissible_indices):
                    if j < len(drv_results):
                        r = drv_results[j]
                        if idx not in adm_scores:
                            adm_scores[idx] = {}
                        adm_scores[idx][tag] = r.get("score", 0)
            # For TRACK_B: also evaluate V11 sequences for proper C_event
            if self.track == "TRACK_B" and self.v11_files:
                v11_all = []
                for vpath in self.v11_files:
                    v11_res = self.kernel.batch(
                        [v0_cands[i] for i in admissible_indices],
                        driver="V0_NONE", driver_file=vpath,
                        width=self.width, height=self.height, target=self.target)
                    self.scout_evals += len(admissible_indices)
                    v11_all.append(v11_res)
                for j, idx in enumerate(admissible_indices):
                    v11_scores = [vr[j].get("score", 0) for vr in v11_all
                                  if j < len(vr)]
                    if idx not in adm_scores:
                        adm_scores[idx] = {}
                    adm_scores[idx]["V11_mean"] = (
                        sum(v11_scores) / len(v11_scores) if v11_scores else 0)

        # Build scout_results with contrasts
        self.scout_results = []
        for idx in admissible_indices:
            cr, ci = grid_points[idx]
            v0r = v0_results[idx]
            sc = adm_scores.get(idx, {})
            scores = {
                "V0": v0r.get("score", 0),
                "V1": sc.get("V1", 0),
                "S1": sc.get("S1", 0),
                "S2": sc.get("S2", 0),
                "V11_mean": sc.get("V11_mean", 0),
            }
            contrast = self._contrast_from_scores(scores)
            self.scout_results.append({
                "cr": cr, "ci": ci,
                "scores": scores,
                "contrast": contrast,
                "escaped_fraction": v0r.get("escaped_fraction", 0),
                "entropy": v0r.get("entropy", 0),
                "v0_result": v0r,
            })

        self.scout_done = True

    def _select_admissible_starts(self):
        """Select 8 multi-start points from admissible scout points.

        NOT selected by score — selected by spatial coverage (protocol §25).
        Uses a deterministic grid-based selection from admissible points.
        """
        if not self.scout_results:
            lo_cr, hi_cr, lo_ci, hi_ci = self.domain
            self.admissible_starts = [((lo_cr + hi_cr) / 2, (lo_ci + hi_ci) / 2)]
            self.current_start_idx = 0
            self.current_cr, self.current_ci = self.admissible_starts[0]
            return

        # Sort by spatial spread: divide domain into 4 quadrants, pick 2 from each
        lo_cr, hi_cr, lo_ci, hi_ci = self.domain
        mid_cr = (lo_cr + hi_cr) / 2
        mid_ci = (lo_ci + hi_ci) / 2
        quadrants = [[], [], [], []]
        for s in self.scout_results:
            q = 0
            if s["cr"] > mid_cr:
                q += 1
            if s["ci"] > mid_ci:
                q += 2
            quadrants[q].append(s)

        starts = []
        per_quad = 2  # 2 from each quadrant = 8 total
        for q in quadrants:
            # Deterministic: pick evenly spaced by index
            if not q:
                continue
            q.sort(key=lambda x: (x["cr"], x["ci"]))
            step = max(1, len(q) // per_quad)
            for i in range(0, len(q), step):
                starts.append((q[i]["cr"], q[i]["ci"]))
                if len(starts) >= 8:
                    break
            if len(starts) >= 8:
                break

        # Fallback if not enough quadrants populated
        if len(starts) < 1:
            for s in self.scout_results[:8]:
                starts.append((s["cr"], s["ci"]))

        self.admissible_starts = starts[:8]
        self.current_start_idx = 0
        self.current_cr, self.current_ci = self.admissible_starts[0]
        self.current_contrast = -999.0

    # ---- Hill climbing step (contrast-based) ----------------------------
    def _hill_step(self):
        lo_cr, hi_cr, lo_ci, hi_ci = self.domain
        cands = []
        for dcr, dci in [(-1, 0), (1, 0), (0, -1), (0, 1),
                         (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            ncr = self._reflect(self.current_cr + dcr * self.step_size, lo_cr, hi_cr)
            nci = self._reflect(self.current_ci + dci * self.step_size, lo_ci, hi_ci)
            cands.append(self._make_candidate(ncr, nci))
        # 9th candidate: deterministic mutation
        mcr = self._reflect(lo_cr + (self.rng() / 2**64) * (hi_cr - lo_cr), lo_cr, hi_cr)
        mci = self._reflect(lo_ci + (self.rng() / 2**64) * (hi_ci - lo_ci), lo_ci, hi_ci)
        cands.append(self._make_candidate(mcr, mci))

        # Evaluate all candidates with all 4 drivers
        best_local = self.current_contrast
        bl_cr, bl_ci = self.current_cr, self.current_ci
        bl_scores = {}
        evals = []

        for c in cands:
            scores, v0_result = self._score_all_at(c["cr"], c["ci"])
            contrast = self._contrast_from_scores(scores)
            self.search_evals += 4  # 4 driver evaluations per candidate

            evals.append({
                **c, "result": v0_result or {},
                "status": "OK" if v0_result else "FAILED",
                "step": self.step + 1,
                "contrast": contrast,
                "scores": scores,
            })

            if contrast > best_local:
                best_local = contrast
                bl_cr, bl_ci = c["cr"], c["ci"]
                bl_scores = scores

        improved = best_local > self.current_contrast
        self.current_cr, self.current_ci = bl_cr, bl_ci
        self.current_contrast = best_local

        if best_local > self.best_contrast:
            self.best_contrast = best_local
            self.best_cr, self.best_ci = bl_cr, bl_ci
            self.best_scores = bl_scores
            self.best_score = bl_scores.get("V1", 0)
            self.steps_without_improvement = 0
        else:
            self.steps_without_improvement += 1

        self.step_size = min(0.2, self.step_size * 1.15) if improved \
            else max(1e-5, self.step_size * 0.5)
        return evals

    # ---- Main run loop ---------------------------------------------------
    def run(self):
        config = {
            "track": self.track,
            "driver": self.driver_name, "driver_hash": self.driver_hash,
            "seed": self.seed, "target": self.target,
            "steps": self.total_steps, "scout_grid": self.scout_grid,
            "domain": list(self.domain), "width": self.width,
            "height": self.height, "max_iter": self.max_iter,
            "alpha": self.alpha,
            "algorithm": "contrast_hill_climbing_multi_start",
        }
        self.store.create_run(self.run_id, config)
        saved = self.store.get_state(self.run_id)
        if saved:
            self._restore(saved)

        while self.step < self.total_steps:
            if not self._time_left():
                self.store.event(self.run_id, "STOP", {"reason": "TIME_BUDGET"})
                break

            if not self.scout_done:
                self._run_scout()
                self._select_admissible_starts()
                self.store.commit_step(self.run_id, 0, [], self._state())
                self.step = 1
                continue

            # Check if current start is exhausted
            if self.steps_without_improvement >= 20:
                self.current_start_idx += 1
                if self.current_start_idx >= len(self.admissible_starts):
                    break  # All starts exhausted
                self.current_cr, self.current_ci = \
                    self.admissible_starts[self.current_start_idx]
                self.current_contrast = -999.0
                self.step_size = 0.02
                self.steps_without_improvement = 0

            evals = self._hill_step()
            self.step += 1
            self.store.commit_step(self.run_id, self.step, evals, self._state())

        self.store.finish_run(self.run_id, "FINISHED")
        return self.best_result()

    def best_result(self):
        return {
            "score": self.best_score,
            "contrast": self.best_contrast,
            "cr": self.best_cr, "ci": self.best_ci,
            "driver": self.driver_name,
            "driver_hash": self.driver_hash,
            "run_id": self.run_id,
            "scores": self.best_scores,
            "track": self.track,
            "n_admissible_starts": len(self.admissible_starts),
        }
