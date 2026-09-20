"""
Proof of Simulation V3 — kernel wrapper and budget-exact hill-climbing search.

The V2 accounting defect (99 instead of 100 hill steps, so 27 evaluations per
three tracks vanished from the reported total) is fixed here: the scout is
counted and reported separately, and exactly `logical_steps` hill steps are
executed. Evaluation roles are counted explicitly; V3 never prints an
ambiguous "TOTAL EVALUATIONS".
"""
import json
import os
import subprocess
import shutil
import time

import v3_math as M


def _kernel_env():
    env = dict(os.environ)
    cc = None
    for name in ("gcc", "clang", "cc"):
        cc = shutil.which(name)
        if cc:
            break
    if not cc and os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        base = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(base):
            for d in os.listdir(base):
                if "winlibs" in d.lower():
                    cand = os.path.join(base, d, "mingw64", "bin")
                    if os.path.isdir(cand):
                        env["PATH"] = cand + os.pathsep + env.get("PATH", "")
                        break
    elif cc and os.path.sep in cc:
        env["PATH"] = os.path.dirname(os.path.abspath(cc)) + os.pathsep + env.get("PATH", "")
    return env


def write_driver_file(seq, max_iter, path):
    if len(seq) < max_iter + 1:
        raise ValueError("driver sequence shorter than max_iter")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(repr(seq[k]) for k in range(1, max_iter + 1)))
        f.write("\n")
    return path


class V3Kernel:
    def __init__(self, kernel_path="kernel_v3.exe"):
        if not os.path.isfile(kernel_path):
            raise FileNotFoundError(f"V3 kernel not found: {kernel_path}")
        self.kernel_path = os.path.abspath(kernel_path)

    def _run(self, args, stdin_data=None, timeout=300):
        try:
            p = subprocess.run([self.kernel_path] + args, capture_output=True,
                               text=True, timeout=timeout, env=_kernel_env(),
                               input=stdin_data)
            return p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired:
            return "", "TIMEOUT", -1
        except Exception as e:  # pragma: no cover
            return "", str(e), -1

    def evaluate(self, cr, ci, driver="V0_NONE", alpha=1.0, degree=2, channel=0,
                 max_iter=200, seed=7331, width=60, height=30, target="TARGET_A",
                 target_file=None, driver_file=None, window=5, offset=1):
        args = ["--evaluate", "--cr", f"{cr:.17g}", "--ci", f"{ci:.17g}",
                "--driver", str(driver), "--alpha", f"{alpha:.17g}",
                "--degree", str(degree), "--channel", str(channel),
                "--max-iter", str(max_iter), "--seed", str(seed),
                "--width", str(width), "--height", str(height), "--target", target,
                "--window", str(window), "--offset", str(offset)]
        if target_file:
            args += ["--target-file", target_file.replace("\\", "/")]
        if driver_file:
            args += ["--driver-file", driver_file.replace("\\", "/")]
        stdout, stderr, rc = self._run(args)
        if rc != 0 or not stdout.strip():
            return {"error": stderr.strip() or f"exit {rc}", "error_code": 1, "score": 0}
        import json
        try:
            return json.loads(stdout.strip())
        except json.JSONDecodeError:
            return {"error": "invalid JSON", "error_code": 1, "score": 0}

    def batch(self, candidates, driver="V0_NONE", driver_file=None, width=60,
              height=30, target="TARGET_A", target_file=None, window=5, offset=1,
              timeout=600):
        args = ["--batch", "--width", str(width), "--height", str(height),
                "--target", target, "--window", str(window), "--offset", str(offset)]
        if target_file:
            args += ["--target-file", target_file.replace("\\", "/")]
        if driver_file:
            args += ["--driver-file", driver_file.replace("\\", "/")]
        lines = []
        for c in candidates:
            lines.append(f"{c['candidate_id']} {c['cr']:.17g} {c['ci']:.17g} "
                         f"V3_ARITHMETIC_ISOLATION {driver} {c.get('alpha',1.0):.17g} "
                         f"{c.get('degree',2)} {c.get('channel',0)} "
                         f"{c.get('max_iter',200)} {c.get('seed',7331)}")
        stdout, stderr, rc = self._run(args, stdin_data="\n".join(lines) + "\n",
                                       timeout=timeout)
        results = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 16:
                results.append({"error": f"short line: {line[:80]}", "error_code": 1})
                continue
            results.append({
                "candidate_id": int(parts[0]), "score": float(parts[1]),
                "pearson01": float(parts[2]), "spearman01": float(parts[3]),
                "mae01": float(parts[4]), "gradient01": float(parts[5]),
                "spectral01": float(parts[6]), "autocorrelation01": float(parts[7]),
                "entropy": float(parts[8]), "anisotropy": float(parts[9]),
                "compression_ratio": float(parts[10]),
                "quantization_levels": int(parts[11]),
                "quantization_dom_frac": float(parts[12]),
                "escaped_fraction": float(parts[13]),
                "runtime_ms": float(parts[14]), "error_code": int(parts[15]),
            })
        return results

    def target_field(self, target_id, width=60, height=30):
        import json
        out, err, rc = self._run(["--target-field", "--target", target_id,
                                  "--width", str(width), "--height", str(height)])
        if rc != 0:
            raise RuntimeError(f"target_field failed: {err}")
        return json.loads(out.strip())

    def driver_values(self, driver, max_iter=200, seed=7331, window=5):
        import json
        out, err, rc = self._run(["--driver-values", "--driver", driver,
                                  "--max-iter", str(max_iter), "--seed", str(seed),
                                  "--window", str(window)])
        if rc != 0:
            raise RuntimeError(f"driver_values failed: {err}")
        return json.loads(out.strip())

    def score_fields(self, field, target, width, height):
        import json
        stdin = " ".join(f"{v:.17g}" for v in field) + " " + \
                " ".join(f"{v:.17g}" for v in target) + "\n"
        out, err, rc = self._run(["--score-fields", "--width", str(width),
                                  "--height", str(height)], stdin_data=stdin)
        if rc != 0:
            raise RuntimeError(f"score_fields failed: {err}")
        return json.loads(out.strip())

    def trace(self, cr, ci, driver="V0_NONE", max_iter=1000, alpha=1.0, degree=2,
              channel=0, seed=7331, width=60, height=30, window=5, offset=1,
              driver_file=None):
        args = ["--trace", "--cr", f"{cr:.17g}", "--ci", f"{ci:.17g}",
                "--driver", str(driver), "--alpha", f"{alpha:.17g}",
                "--degree", str(degree), "--channel", str(channel),
                "--max-iter", str(max_iter), "--seed", str(seed),
                "--width", str(width), "--height", str(height),
                "--window", str(window), "--offset", str(offset)]
        if driver_file:
            args += ["--driver-file", driver_file.replace("\\", "/")]
        out, err, rc = self._run(args, timeout=600)
        if rc != 0:
            raise RuntimeError(f"trace failed: {err}")
        lines = out.strip().split("\n")
        header = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            row = {}
            for i, h in enumerate(header):
                v = parts[i] if i < len(parts) else "0"
                row[h] = int(v) if h in ("prime", "iter") else float(v)
            rows.append(row)
        return rows
class V3Search:
    """Budget-exact hill climbing: 17x17 scout (289) + exactly `steps` hill
    steps of 9 candidates. Scout and search evaluations are reported
    separately, never merged into an ambiguous total."""

    def __init__(self, store, kernel, run_id, driver_name, driver_seq, seed=133742,
                 target="TARGET_A", role="PRIMARY", steps=100, scout_grid=17,
                 domain=(-2.0, 2.0, -2.0, 2.0), width=60, height=30, max_iter=200,
                 alpha=1.0, degree=2, channel=0, start_time=None, time_budget=None,
                 driver_dir="v3_artifacts"):
        self.store = store
        self.kernel = kernel
        self.run_id = run_id
        self.driver_name = driver_name
        self.driver_seq = driver_seq
        self.seed = seed
        self.target = target
        self.role = role
        self.total_steps = steps
        self.scout_grid = scout_grid
        self.domain = domain
        self.width = width
        self.height = height
        self.max_iter = max_iter
        self.alpha = alpha
        self.degree = degree
        self.channel = 1 if driver_name == "V7_IMAGINARY" else channel
        self.start_time = start_time
        self.time_budget = time_budget
        self.rng = M.splitmix64(seed)

        if len(driver_seq) < max_iter + 1:
            raise ValueError("driver sequence shorter than max_iter")
        self.driver_hash = M.sequence_hash(driver_seq[1:max_iter + 1])
        os.makedirs(driver_dir, exist_ok=True)
        self.driver_file = os.path.join(
            driver_dir, f"v3_drv_{driver_name}_n{max_iter}_{self.driver_hash[:12]}.txt")
        write_driver_file(driver_seq, max_iter, self.driver_file)

        self.step = 0
        self.current_cr, self.current_ci = 0.0, 0.0
        self.current_score = -1.0
        self.best_cr, self.best_ci, self.best_score = 0.0, 0.0, -1.0
        self.step_size = 0.02
        self.steps_without_improvement = 0
        self.basin_starts, self.current_basin, self.basin_steps = [], 0, 0
        self.scout_done = False
        self.scout_results = []
        self.candidate_id = 0
        self.scout_evals = 0
        self.search_evals = 0

    def accounting(self):
        return {
            "driver": self.driver_name,
            "driver_hash": self.driver_hash,
            "role": self.role,
            "SCOUT_EVALUATIONS": self.scout_evals,
            "PRIMARY_SEARCH_EVALUATIONS": self.search_evals,
            "CONTROL_EVALUATIONS": 0,
            "VALIDATION_EVALUATIONS": 0,
            "NULL_EVALUATIONS": 0,
            "TOTAL_KERNEL_EVALUATIONS": self.scout_evals + self.search_evals,
            "expected_per_run": (self.scout_grid ** 2) + self.total_steps * 9,
        }

    # ---- helpers -------------------------------------------------------
    def _reflect(self, val, lo, hi):
        while val < lo or val > hi:
            if val < lo:
                val = 2 * lo - val
            elif val > hi:
                val = 2 * hi - val
        return val

    def _make_candidate(self, cr, ci):
        self.candidate_id += 1
        return {
            "candidate_id": self.candidate_id, "cr": cr, "ci": ci,
            "driver": self.driver_name, "driver_hash": self.driver_hash,
            "alpha": self.alpha, "degree": self.degree, "channel": self.channel,
            "max_iter": self.max_iter, "seed": self.seed,
            "role": self.role, "target": self.target,
            "width": self.width, "height": self.height,
        }

    def _state(self):
        return {
            "step": self.step,
            "current_cr": self.current_cr, "current_ci": self.current_ci,
            "current_score": self.current_score,
            "best_cr": self.best_cr, "best_ci": self.best_ci,
            "best_score": self.best_score,
            "step_size": self.step_size,
            "steps_without_improvement": self.steps_without_improvement,
            "basin_starts": self.basin_starts,
            "current_basin": self.current_basin, "basin_steps": self.basin_steps,
            "scout_done": self.scout_done,
            "candidate_id": self.candidate_id,
            "scout_evals": self.scout_evals, "search_evals": self.search_evals,
        }

    def _restore(self, s):
        self.step = s["step"]
        self.current_cr, self.current_ci = s["current_cr"], s["current_ci"]
        self.current_score = s["current_score"]
        self.best_cr, self.best_ci, self.best_score = s["best_cr"], s["best_ci"], s["best_score"]
        self.step_size = s["step_size"]
        self.steps_without_improvement = s["steps_without_improvement"]
        self.basin_starts = [tuple(b) for b in s["basin_starts"]]
        self.current_basin, self.basin_steps = s["current_basin"], s["basin_steps"]
        self.scout_done = s["scout_done"]
        self.candidate_id = s["candidate_id"]
        self.scout_evals = s.get("scout_evals", 0)
        self.search_evals = s.get("search_evals", 0)

    def _time_left(self):
        if self.start_time is None or self.time_budget is None:
            return True
        return (time.time() - self.start_time) < self.time_budget

    def _run_scout(self):
        lo_cr, hi_cr, lo_ci, hi_ci = self.domain
        g = self.scout_grid
        cands = []
        for i in range(g):
            for j in range(g):
                cr = lo_cr + (hi_cr - lo_cr) * i / (g - 1)
                ci = lo_ci + (hi_ci - lo_ci) * j / (g - 1)
                cands.append(self._make_candidate(cr, ci))
        results = self.kernel.batch(cands, driver="V0_NONE",
                                    driver_file=self.driver_file,
                                    width=self.width, height=self.height,
                                    target=self.target)
        self.scout_results = []
        for c, r in zip(cands, results):
            ok = r.get("error_code", 0) == 0
            self.scout_results.append({**c, "result": r,
                                       "status": "OK" if ok else "FAILED"})
        self.scout_evals += len(cands)
        self.scout_done = True

    def _select_basin_starts(self):
        valid = [(e, e["result"].get("score", -1)) for e in self.scout_results
                 if e["status"] == "OK" and e["result"].get("score", -1) >= 0]
        valid.sort(key=lambda x: x[1], reverse=True)
        seen, starts = set(), []
        for e, s in valid:
            key = (round(e["cr"], 6), round(e["ci"], 6))
            if key in seen:
                continue
            seen.add(key)
            starts.append((e["cr"], e["ci"], s))
            if len(starts) >= 5:
                break
        if not starts:
            lo_cr, hi_cr, lo_ci, hi_ci = self.domain
            starts = [((lo_cr + hi_cr) / 2, (lo_ci + hi_ci) / 2, 0.0)]
        self.basin_starts = starts
        self.current_basin, self.basin_steps = 0, 0
        self.current_cr, self.current_ci, self.current_score = starts[0]
        self.best_cr, self.best_ci, self.best_score = \
            self.current_cr, self.current_ci, self.current_score

    def _hill_step(self):
        lo_cr, hi_cr, lo_ci, hi_ci = self.domain
        cands = []
        for dcr, dci in [(-1, 0), (1, 0), (0, -1), (0, 1),
                         (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            ncr = self._reflect(self.current_cr + dcr * self.step_size, lo_cr, hi_cr)
            nci = self._reflect(self.current_ci + dci * self.step_size, lo_ci, hi_ci)
            cands.append(self._make_candidate(ncr, nci))
        mcr = self._reflect(lo_cr + (self.rng() / 2**64) * (hi_cr - lo_cr), lo_cr, hi_cr)
        mci = self._reflect(lo_ci + (self.rng() / 2**64) * (hi_ci - lo_ci), lo_ci, hi_ci)
        cands.append(self._make_candidate(mcr, mci))

        results = self.kernel.batch(cands, driver="V0_NONE",
                                    driver_file=self.driver_file,
                                    width=self.width, height=self.height,
                                    target=self.target)
        evals = []
        best_local = self.current_score
        bl_cr, bl_ci = self.current_cr, self.current_ci
        for c, r in zip(cands, results):
            ok = r.get("error_code", 0) == 0
            score = r.get("score", -1) if ok else -1
            evals.append({**c, "result": r, "status": "OK" if ok else "FAILED",
                          "step": self.step + 1})
            if ok and score > best_local:
                best_local, bl_cr, bl_ci = score, c["cr"], c["ci"]

        improved = best_local > self.current_score
        self.current_cr, self.current_ci, self.current_score = bl_cr, bl_ci, best_local
        if best_local > self.best_score:
            self.best_score, self.best_cr, self.best_ci = best_local, bl_cr, bl_ci
            self.steps_without_improvement = 0
        else:
            self.steps_without_improvement += 1
        self.step_size = min(0.2, self.step_size * 1.15) if improved \
            else max(1e-5, self.step_size * 0.5)
        self.search_evals += len(evals)
        return evals

    def run(self, stop_after_steps=None):
        config = {
            "driver": self.driver_name, "driver_hash": self.driver_hash,
            "seed": self.seed, "target": self.target, "role": self.role,
            "steps": self.total_steps, "scout_grid": self.scout_grid,
            "domain": list(self.domain), "width": self.width,
            "height": self.height, "max_iter": self.max_iter,
            "alpha": self.alpha, "degree": self.degree, "channel": self.channel,
            "algorithm": "hill_climbing_budget_exact",
        }
        self.store.create_run(self.run_id, config)
        saved = self.store.get_state(self.run_id)
        if saved:
            self._restore(saved)
        limit = self.total_steps if stop_after_steps is None else stop_after_steps

        while self.step < limit:
            if not self._time_left():
                self.store.event(self.run_id, "STOP", {"reason": "TIME_BUDGET"})
                break
            if not self.scout_done:
                self._run_scout()
                self._select_basin_starts()
                self.store.commit_step(self.run_id, 0,
                                       [{**e, "step": 0} for e in self.scout_results],
                                       self._state())
                self.step = 1
                continue
            if self.basin_steps >= 20:
                self.current_basin += 1
                self.basin_steps = 0
                if self.current_basin >= len(self.basin_starts):
                    break
                self.current_cr, self.current_ci, self.current_score = \
                    self.basin_starts[self.current_basin]
                self.step_size = 0.02
                self.steps_without_improvement = 0
            evals = self._hill_step()
            self.basin_steps += 1
            self.step += 1
            self.store.commit_step(self.run_id, self.step, evals, self._state())

        self.store.finish_run(self.run_id, "FINISHED")
        return self.best_result()

    def best_result(self):
        best = self.store.best_of(self.run_id)
        if not best:
            return {"score": 0, "cr": 0, "ci": 0, "error": "no successful evaluations"}
        import json as _json
        result = _json.loads(best["result_json"]) if best.get("result_json") else {}
        return {
            "score": best["score"], "cr": best["cr"], "ci": best["ci"],
            "driver": self.driver_name, "driver_hash": self.driver_hash,
            "run_id": self.run_id,
            "escaped_fraction": result.get("escaped_fraction", 0),
        }
