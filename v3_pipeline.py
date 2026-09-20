"""
Proof of Simulation V3 — deep arithmetic isolation pipeline.

Central question (protocol #124): does replacing prime event timing with a
carefully matched non-prime event process remove a reproducible component of
the observed structure, and does the residual arithmetic component survive
removal of the smooth trend?
"""
import json
import os
import time

import v3_math as M
import v3_protocol as P3
from v3_store import V3Store
from v3_search import V3Kernel, V3Search

ART = "v3_artifacts"

# Canonical driver taxonomy (protocol #18)
TAXONOMY = {
    "V0_NONE": "FULL", "V1_FULL": "FULL", "V5_SHUFFLED": "FULL",
    "S1_ANALYTIC": "SMOOTH", "S2_DATA_SMOOTHED": "SMOOTH",
    "V9_EVENT": "EVENT", "V9_MATCHED": "EVENT",
    "V9_ENERGY_MATCHED": "EVENT",
    "V10_RESIDUAL": "RESIDUAL", "V10_MATCHED": "RESIDUAL",
    "V11_MATCHED_EVENT": "SHUFFLED_EVENT", "V12_SHIFTED_EVENT": "SHIFTED_EVENT",
    "V13_GAP_MATCHED_EVENT": "GAP_MATCHED_EVENT",
    "V14_CONSTANT_FIELD": "CONTROL_FIELD", "V15_X_RAMP": "CONTROL_FIELD",
    "V16_Y_RAMP": "CONTROL_FIELD", "V17_BILINEAR_RAMP": "CONTROL_FIELD",
    "V18_RADIAL_GRADIENT": "CONTROL_FIELD",
}


def build_sequences(max_iter, window=5, seed_events=101, shift=1):
    """Build every V3 temporal driver deterministically for a given depth."""
    pi = M.pi_counts(max_iter)
    P = M.seq_P(pi, max_iter)
    E = M.seq_E(P, max_iter)
    S1 = M.seq_S1_riemann(max_iter)
    R = M.seq_residual(P, S1, max_iter)
    V10 = M.standardize(R, max_iter, 200)
    Pc = M.center(P, max_iter, 200)
    rms_pc = M.rms(Pc, max_iter, 200)
    rms_e = M.rms(E, max_iter, 200)

    seq = {
        "V0_NONE": [0.0] * (max_iter + 1),
        "V1_FULL": P,
        "S1_ANALYTIC": S1,
        "S2_DATA_SMOOTHED": M.seq_S2(P, max_iter, window),
        "V9_EVENT": E,
        "V9_MATCHED": M.scale_to_rms(M.center(E, max_iter, 200), max_iter,
                                     rms_e, 200),
        "V9_ENERGY_MATCHED": M.scale_to_rms(M.center(E, max_iter, 200), max_iter,
                                            rms_pc, 200),
        "V10_RESIDUAL": V10,
        "V10_MATCHED": M.scale_to_rms(V10, max_iter, rms_pc, 200),
        "V11_MATCHED_EVENT": M.seq_V11_matched_event(E, max_iter, seed_events),
        "V12_SHIFTED_EVENT": M.seq_V12_shifted_event(E, max_iter, shift),
        "V13_GAP_MATCHED_EVENT": M.seq_V13_gap_matched(E, max_iter, seed_events),
        "V5_SHUFFLED": M.seq_V5_shuffled(P, max_iter, 7331),
    }
    return seq


def driver_registry(max_iter, window=5):
    """Full registry with hashes, stats and taxonomy (protocol #12/#18/#25)."""
    seq = build_sequences(max_iter, window)
    reg = {}
    for name, values in seq.items():
        reg[name] = {
            "taxonomy": TAXONOMY.get(name, "UNCLASSIFIED"),
            "hash": M.sequence_hash(values[1:max_iter + 1]),
            "length": max_iter,
            "mean": M.mean(values, max_iter, 200),
            "rms": M.rms(values, max_iter, 200),
            "min": min(values[1:max_iter + 1]),
            "max": max(values[1:max_iter + 1]),
            "nonzero_count": sum(1 for k in range(1, max_iter + 1)
                                 if abs(values[k]) > 1e-18),
        }
    return seq, reg


def driver_registry_self_test(seq, reg, max_iter, kernel=None):
    """Detect DRIVER_COLLISION between mathematically distinct drivers and
    cross-validate Python sequences against the C kernel."""
    findings = {"collisions": [], "kernel_cross_check": {}, "ok": True}
    names = sorted(seq)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if reg[a]["hash"] == reg[b]["hash"]:
                findings["collisions"].append({"a": a, "b": b,
                                               "hash": reg[a]["hash"]})
                findings["ok"] = False
    if kernel is not None:
        # Kernel V1/V9 sequences must match the canonical Python definitions.
        pairs = [("V1_FULL", "V1_INV_PI"), ("V9_EVENT", "V9_PRIME_EVENT"),
                 ("V0_NONE", "V0_NONE"), ("S2_DATA_SMOOTHED", "S2_DATA_SMOOTHED")]
        for py_name, k_name in pairs:
            try:
                kv = kernel.driver_values(k_name, max_iter)["values"]
                match = all(abs(kv[k - 1] - seq[py_name][k]) < 1e-12
                            for k in range(1, max_iter + 1))
            except Exception as exc:  # pragma: no cover
                match = False
                findings["kernel_cross_check"][py_name] = {"error": str(exc)}
                continue
            findings["kernel_cross_check"][py_name] = {
                "kernel_driver": k_name, "match": match}
            if not match:
                findings["ok"] = False
        # V10 differs by construction: kernel S1 uses li, V3 uses Riemann R.
        try:
            kv10 = kernel.driver_values("V10_PRIME_RESIDUAL", max_iter)["values"]
            diff = max(abs(kv10[k - 1] - seq["V10_RESIDUAL"][k])
                       for k in range(1, max_iter + 1))
            findings["kernel_cross_check"]["V10_RESIDUAL"] = {
                "kernel_driver": "V10_PRIME_RESIDUAL",
                "max_abs_difference_vs_v3": diff,
                "note": "kernel S1 is li-based; V3 S1 is Riemann R (documented)"}
        except Exception as exc:  # pragma: no cover
            findings["kernel_cross_check"]["V10_RESIDUAL"] = {"error": str(exc)}
    return findings


class V3Pipeline:
    """V3 phase machine: audit -> search -> matched controls -> null ->
    validation -> temporal -> benchmark -> explanation -> report."""

    def __init__(self, time_budget=14400, quiet=False, null_runs=None):
        self.time_budget = time_budget
        self.quiet = quiet
        self.start_time = time.time()
        self.null_runs = null_runs
        self.kernel = None
        self.store = None
        self.proto = None
        self.phash = self.shash = self.bhash = None
        self.run_id = None
        self.state = {}
        self.log_lines = []

    # ---- plumbing ------------------------------------------------------
    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[V3 {ts}] {msg}"
        self.log_lines.append(line)
        if not self.quiet:
            print(line, flush=True)
        try:
            with open("run_v3.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def elapsed(self):
        return time.time() - self.start_time

    def budget_left(self):
        return self.time_budget - self.elapsed()

    def record(self, phase, key, value, score=None):
        self.store.record(phase, key, value, score)

    def save_artifact(self, subdir, name, obj):
        path = os.path.join(ART, subdir)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
        return path

    # ---- phases --------------------------------------------------------
    def phase_init(self):
        self.log("=== V3 INIT ===")
        for sub in ("best", "controls", "matched_events", "boundary", "temporal",
                    "targets", "null", "benchmark", "audit"):
            os.makedirs(os.path.join(ART, sub), exist_ok=True)
        self.proto = P3.save_protocol_v3()
        self.phash = P3.protocol_v3_hash(self.proto)
        self.shash = P3.source_v3_hash()
        # build if binary missing or older than source
        need_build = True
        exe = "kernel_v3.exe" if os.name == "nt" else "kernel_v3"
        src = "kernel_v3.c"
        if os.path.exists(exe) and os.path.exists(src):
            need_build = os.path.getmtime(exe) < os.path.getmtime(src)
        if need_build:
            import subprocess
            cc = "gcc"
            cmd = [cc, "-O3", "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                   "-static", src, "-lm", "-o", exe]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                self.log(f"COMPILATION FAILED: {r.stderr[:400]}")
                return False
            self.log(f"Compiled {exe}")
        self.bhash = P3.binary_v3_hash(exe)
        self.kernel = V3Kernel(exe)
        self.store = V3Store(".", self.phash, self.shash, self.bhash)
        self.run_id = f"V3_DEEP_{int(self.start_time)}"
        self.log(f"protocol={self.phash[:16]} source={self.shash[:16]} "
                 f"binary={self.bhash[:16]}")
        self.record("provenance", "hashes", {
            "protocol_hash": self.phash, "source_hash": self.shash,
            "binary_hash": self.bhash, "environment": P3.environment(),
            "run_id": self.run_id})
        return True

    def phase_self_test(self):
        self.log("=== V3 SELF TEST ===")
        import subprocess
        exe = self.kernel.kernel_path
        r = subprocess.run([exe, "--self-test"], capture_output=True, text=True,
                           env=__import__("v3_search")._kernel_env(), timeout=120)
        ok = r.returncode == 0
        self.log(f"kernel self-test: {'PASSED' if ok else 'FAILED'}")
        seq, reg = driver_registry(200, self.proto["s2_windows"][1])
        findings = driver_registry_self_test(seq, reg, 200, self.kernel)
        self.log(f"driver registry collisions: {len(findings['collisions'])}")
        for name, chk in findings["kernel_cross_check"].items():
            self.log(f"  cross-check {name}: {chk}")
        self.record("self_test", "kernel", {"passed": ok})
        self.record("self_test", "driver_registry", findings)
        self.save_artifact("audit", "driver_registry.json",
                           {"registry": reg, "self_test": findings})
        self.state["registry_ok"] = findings["ok"]
        return ok and findings["ok"]

    def phase_protocol_lock(self):
        self.log("=== V3 PROTOCOL LOCK ===")
        self.record("provenance", "protocol", self.proto)
        self.record("provenance", "phase_order", [
            "INIT", "SELF_TEST", "PROTOCOL_LOCK", "BOUNDARY", "SEARCH",
            "CONTROLS", "NULL", "VALIDATION", "TEMPORAL", "BENCHMARK",
            "EXPLANATION", "REPORT", "REPRODUCIBILITY", "FINISHED"])
        return True

    # ---- boundary diagnostic (before search, protocol #32-#36) ---------
    def phase_boundary(self):
        self.log("=== V3 BOUNDARY DIAGNOSTIC ===")
        import v3_search as S
        seq, _ = driver_registry(200)
        tmp = f"{ART}/boundary/_tmp_drv.txt"
        prof = {}
        for drv_name in ("V1_FULL", "V0_NONE", "V9_EVENT", "V10_RESIDUAL"):
            S.write_driver_file(seq[drv_name], 200, tmp)
            rows = []
            for cr in self.proto["boundary"]["cr_values"]:
                for dci in self.proto["boundary"]["ci_offsets"]:
                    ci = round(0.011132 + dci, 6)
                    out = self.kernel.evaluate(cr, ci, driver="V0_NONE",
                                               driver_file=tmp, max_iter=200)
                    rows.append({"cr": cr, "ci": ci, "score": out.get("score", 0),
                                 "escaped_fraction": out.get("escaped_fraction", 0)})
            prof[drv_name] = rows
        # monotonicity of V1 along cr at ci=0.011132
        v1 = [r for r in prof["V1_FULL"] if abs(r["ci"] - 0.011132) < 1e-9]
        v1_sorted = sorted(v1, key=lambda r: r["cr"])
        scores = [r["score"] for r in v1_sorted]
        monotone = all(b >= a - 1e-12 for a, b in zip(scores, scores[1:]))
        gradient = (scores[-1] - scores[0]) / (v1_sorted[-1]["cr"] - v1_sorted[0]["cr"])
        summary = {
            "monotone_increasing_over_full_range": bool(monotone),
            "score_at_cr_1.0": scores[0], "score_at_cr_3.0": scores[-1],
            "mean_gradient": gradient,
            "interpretation": ("BOUNDARY_ARTIFACT: score rises monotonically "
                               "across the sampled cr range, so the V2 optimum at "
                               "cr=2.0 is not a local maximum" if monotone
                               else "interior structure present"),
            "escaped_fraction_at_best": v1_sorted[4]["escaped_fraction"]
            if len(v1_sorted) > 4 else None,
        }
        self.record("boundary", "profile", {"rows": prof, "summary": summary},
                    score=scores[-1])
        self.save_artifact("boundary", "boundary_profile.json",
                           {"rows": prof, "summary": summary})
        self.log(f"boundary: monotone={monotone} V1(cr=1)={scores[0]:.6f} "
                 f"V1(cr=3)={scores[-1]:.6f}")
        self.state["boundary"] = summary
        return True

    # ---- primary search -------------------------------------------------
    def phase_search(self):
        self.log("=== V3 PRIMARY SEARCH (3 tracks) ===")
        seq, reg = driver_registry(200)
        results = {}
        for track, drv in self.proto["tracks"].items():
            run_id = f"V3_PRIMARY_{track}_{int(time.time())}"
            search = V3Search(self.store, self.kernel, run_id, drv, seq[drv],
                              seed=self.proto["search"]["seeds"][0], role="PRIMARY",
                              steps=self.proto["search"]["logical_steps"],
                              scout_grid=self.proto["search"]["scout_grid"],
                              domain=tuple(self.proto["domains"]["main"]),
                              start_time=self.start_time,
                              time_budget=self.time_budget)
            best = search.run()
            acc = search.accounting()
            results[track] = {"best": best, "accounting": acc, "run_id": run_id}
            self.record("search", track, {"best": best, "accounting": acc},
                        score=best.get("score", 0))
            self.log(f"{track} ({drv}): best={best.get('score',0):.6f} "
                     f"at ({best.get('cr',0):.6f},{best.get('ci',0):.6f}) "
                     f"scout={acc['SCOUT_EVALUATIONS']} search={acc['PRIMARY_SEARCH_EVALUATIONS']}")
            if best.get("score", 0) > self.state.get("best", {}).get("score", -1):
                self.state["best"] = {**best, "track": track}
        # repeat search with independent seeds on the winning track
        best_track = self.state["best"]["track"]
        best_drv = self.proto["tracks"][best_track]
        repeats = []
        for sd in self.proto["search"]["seeds"][1:]:
            run_id = f"V3_REPEAT_{best_track}_s{sd}_{int(time.time())}"
            s = V3Search(self.store, self.kernel, run_id, best_drv, seq[best_drv],
                         seed=sd, role="PRIMARY",
                         steps=self.proto["search"]["logical_steps"],
                         scout_grid=self.proto["search"]["scout_grid"],
                         domain=tuple(self.proto["domains"]["main"]),
                         start_time=self.start_time, time_budget=self.time_budget)
            b = s.run()
            repeats.append({"seed": sd, "best": b})
            self.log(f"  repeat seed {sd}: {b.get('score', 0):.6f}")
        self.record("search", "repeats", {"track": best_track, "runs": repeats})
        self.state["search"] = results
        self.save_artifact("best", "search_results.json",
                           {"tracks": results, "repeats": repeats,
                            "best": self.state["best"]})
        return True

    # ---- matched controls (central V3 experiment) -----------------------
    def _drv_file(self, name, seq, max_iter=200):
        import v3_search as S
        vals = seq[name]
        h = M.sequence_hash(vals[1:max_iter + 1])
        path = os.path.join(ART, "controls", f"_drv_{name}_{h[:10]}.txt")
        if not os.path.exists(path):
            S.write_driver_file(vals, max_iter, path)
        return path

    def score_driver_at(self, cr, ci, drv_name, seq, max_iter=200,
                        width=60, height=30, target="TARGET_A", role="CONTROL"):
        import v3_search as S
        path = self._drv_file(drv_name, seq, max_iter)
        out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                   max_iter=max_iter, width=width, height=height,
                                   target=target)
        return {"score": out.get("score", 0), "pearson01": out.get("pearson01", 0),
                "escaped_fraction": out.get("escaped_fraction", 0),
                "error": out.get("error")}

    def score_sequence_at(self, cr, ci, values, max_iter=200, width=60,
                          height=30, target="TARGET_A"):
        """Score an arbitrary forcing sequence at (cr, ci)."""
        import v3_search as S
        h = M.sequence_hash(values[1:max_iter + 1])
        path = os.path.join(ART, "controls", f"_seq_{h[:12]}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            S.write_driver_file(values, max_iter, path)
        out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                   max_iter=max_iter, width=width, height=height,
                                   target=target)
        return {"score": out.get("score", 0), "pearson01": out.get("pearson01", 0),
                "escaped_fraction": out.get("escaped_fraction", 0),
                "error": out.get("error")}

    def score_field(self, field, width=60, height=30, target="TARGET_A"):
        return self.kernel.score_fields(field, self.kernel.target_field(
            target, width, height), width, height)

    def _contrasts(self, scores):
        """Arithmetic contrasts C1-C4 (protocol #30) - never causal effects."""
        def sc(name):
            return scores.get(name, 0.0)
        return {
            "C1_V9_minus_mean_V11": sc("V9_EVENT") - sc("MEAN_V11"),
            "C2_V9_minus_mean_V12": sc("V9_EVENT") - sc("MEAN_V12"),
            "C3_V10_minus_max_S1_S2": sc("V10_RESIDUAL") - max(
                sc("S1_ANALYTIC"), sc("S2_DATA_SMOOTHED")),
            "C4_V10MATCHED_minus_max_S1_S2": sc("V10_MATCHED") - max(
                sc("S1_ANALYTIC"), sc("S2_DATA_SMOOTHED")),
            "V1_minus_V0": sc("V1_FULL") - sc("V0_NONE"),
            "V1_minus_max_S1_S2": sc("V1_FULL") - max(sc("S1_ANALYTIC"),
                                                      sc("S2_DATA_SMOOTHED")),
            "V9_minus_V0": sc("V9_EVENT") - sc("V0_NONE"),
            "V9MATCHED_minus_V9": sc("V9_MATCHED") - sc("V9_EVENT"),
            "V9ENERGYMATCHED_minus_V0": sc("V9_ENERGY_MATCHED") - sc("V0_NONE"),
            "shuffle_degradation": sc("V1_FULL") - sc("V5_SHUFFLED"),
        }

    def phase_controls(self):
        self.log("=== V3 MATCHED CONTROLS ===")
        seq, reg = driver_registry(200)
        seeds = self.proto["matched_event"]["seeds"]
        shifts = self.proto["shifted_event"]["shifts"]
        controls = {}
        for track, info in self.state["search"].items():
            b = info["best"]
            cr, ci = b["cr"], b["ci"]
            scores = {}
            for drv_name in seq:
                r = self.score_driver_at(cr, ci, drv_name, seq)
                scores[drv_name] = r["score"]
            fam = {"V11": {}, "V12": {}, "V13": {}}
            E = seq["V9_EVENT"]
            for sd in seeds:
                fam["V11"][str(sd)] = self.score_sequence_at(
                    cr, ci, M.seq_V11_matched_event(E, 200, sd))["score"]
                fam["V13"][str(sd)] = self.score_sequence_at(
                    cr, ci, M.seq_V13_gap_matched(E, 200, sd))["score"]
            for sh in shifts:
                fam["V12"][str(sh)] = self.score_sequence_at(
                    cr, ci, M.seq_V12_shifted_event(E, 200, sh))["score"]
            mean_v11 = sum(fam["V11"].values()) / len(fam["V11"])
            mean_v12 = sum(fam["V12"].values()) / len(fam["V12"])
            mean_v13 = sum(fam["V13"].values()) / len(fam["V13"])
            scores["MEAN_V11"] = mean_v11
            scores["MEAN_V12"] = mean_v12
            scores["MEAN_V13"] = mean_v13
            contrasts = self._contrasts(scores)
            del scores["MEAN_V11"], scores["MEAN_V12"], scores["MEAN_V13"]
            contrasts["C1_V9_minus_mean_V11"] = scores["V9_EVENT"] - mean_v11
            contrasts["C2_V9_minus_mean_V12"] = scores["V9_EVENT"] - mean_v12
            contrasts["C2b_V9_minus_mean_V13"] = scores["V9_EVENT"] - mean_v13
            contrasts["mean_V11"] = mean_v11
            contrasts["mean_V12"] = mean_v12
            contrasts["mean_V13"] = mean_v13
            amp = {name: {"rms": M.rms(v, 200, 200), "mean": M.mean(v, 200, 200),
                          "nonzero": sum(1 for k in range(1, 201)
                                         if abs(v[k]) > 1e-18)}
                   for name, v in seq.items()}
            entry = {"point": {"cr": cr, "ci": ci}, "scores": scores,
                     "contrasts": contrasts, "amplitude_fairness": amp,
                     "matched_family": fam}
            controls[track] = entry
            self.record("controls", track, entry)
            self.save_artifact("controls", f"controls_{track}.json", entry)
            self.save_artifact("matched_events", f"matched_{track}.json", fam)
            self.log(f"{track}: V0={scores['V0_NONE']:.6f} V1={scores['V1_FULL']:.6f} "
                     f"S1={scores['S1_ANALYTIC']:.6f} V9={scores['V9_EVENT']:.6f} "
                     f"V10={scores['V10_RESIDUAL']:.6f} "
                     f"C1={contrasts['C1_V9_minus_mean_V11']:+.6f} "
                     f"C3={contrasts['C3_V10_minus_max_S1_S2']:+.6f}")
        # field controls V14-V18 (validation only, never part of search score)
        W, H = 60, 30
        fc = {}
        fc["V14_CONSTANT_FIELD"] = self.score_field(M.field_constant(W, H), W, H)
        fc["V15_X_RAMP"] = self.score_field(M.field_x_ramp(W, H), W, H)
        fc["V16_Y_RAMP"] = self.score_field(M.field_y_ramp(W, H), W, H)
        fc["V17_BILINEAR_RAMP"] = self.score_field(M.field_bilinear(W, H), W, H)
        fc["V18_RADIAL_GRADIENT"] = self.score_field(M.field_radial(W, H), W, H)
        fc_summary = {k: v.get("score", 0) for k, v in fc.items()}
        self.record("controls", "FIELD_CONTROLS", fc_summary)
        self.save_artifact("controls", "field_controls.json", fc)
        self.log(f"field controls: {fc_summary}")
        self.state["controls"] = controls
        self.state["field_controls"] = fc_summary
        return True

    # ---- search-aware null ---------------------------------------------
    def phase_null(self):
        self.log("=== V3 SEARCH-AWARE NULL ===")
        n_runs = self.null_runs or self.proto["null"]["standard_runs"]
        lo_cr, hi_cr, lo_ci, hi_ci = self.proto["domains"]["main"]
        budget = self.proto["search"]["expected_per_run"]
        seq, _ = driver_registry(200)
        best_track = self.state["best"].get("track", "TRACK_A")
        drv = self.proto["tracks"][best_track]
        dpath = os.path.join(ART, "null", f"_null_drv_{drv}.txt")
        import v3_search as S
        S.write_driver_file(seq[drv], 200, dpath)
        maxima = []
        for i in range(n_runs):
            seed = self.proto["null"]["search_seeds"][i % len(self.proto["null"]["search_seeds"])]
            rng = M.splitmix64(seed)
            run_id = f"V3_NULL_r{i}_{int(time.time())}"
            self.store.create_run(run_id, {"role": "NULL", "driver": drv,
                                           "seed": seed, "budget": budget})
            best_score, best_cr, best_ci = -1.0, 0.0, 0.0
            done = 0
            cid = 0
            while done < budget:
                n = min(289, budget - done)
                cands = []
                for _ in range(n):
                    cid += 1
                    cands.append({
                        "candidate_id": cid,
                        "cr": lo_cr + (rng() / 2**64) * (hi_cr - lo_cr),
                        "ci": lo_ci + (rng() / 2**64) * (hi_ci - lo_ci),
                        "max_iter": 200, "seed": 7331, "alpha": 1.0,
                        "degree": 2, "channel": 0})
                results = self.kernel.batch(cands, driver="V0_NONE",
                                            driver_file=dpath, width=60, height=30,
                                            target="TARGET_A")
                evals = []
                for c, r in zip(cands, results):
                    ok = r.get("error_code", 0) == 0
                    evals.append({**c, "result": r, "role": "NULL",
                                  "status": "OK" if ok else "FAILED",
                                  "driver": drv, "driver_hash": ""})
                    if ok and r.get("score", -1) > best_score:
                        best_score, best_cr, best_ci = r["score"], c["cr"], c["ci"]
                self.store.commit_step(run_id, done // 289, evals,
                                       {"null_index": i, "done": done})
                done += n
            self.store.finish_run(run_id, "FINISHED")
            maxima.append({"run": i, "seed": seed, "null_best": best_score,
                           "cr": best_cr, "ci": best_ci})
            if (i + 1) % 4 == 0:
                self.log(f"  null {i+1}/{n_runs}: best so far "
                         f"{max(m['null_best'] for m in maxima):.6f}")
        observed = self.state["best"].get("score", 0.0)
        vals = [m["null_best"] for m in maxima]
        count_exceeding = sum(1 for v in vals if v >= observed)
        n = len(vals)
        stats = {
            "N_null": n,
            "count_exceeding": count_exceeding,
            "null_max": max(vals),
            "null_mean": sum(vals) / n,
            "null_std": M.std_flat(vals),
            "percentile": 100.0 * count_exceeding / n,
            "empirical_search_null": (1 + count_exceeding) / (1 + n),
            "observed_best": observed,
            "formula": self.proto["null"]["exceedance_formula"],
            "runs": maxima,
        }
        self.record("null", "stats", stats, score=stats["null_max"])
        self.save_artifact("null", "null_results.json", stats)
        self.log(f"null: N={n} max={stats['null_max']:.6f} "
                 f"mean={stats['null_mean']:.6f} observed={observed:.6f} "
                 f"p_emp={stats['empirical_search_null']:.4f}")
        self.state["null"] = stats
        return True

    # ---- validation: depth/resolution/alpha/holdouts/high-pass ----------
    def phase_validation(self):
        self.log("=== V3 VALIDATION ===")
        b = self.state["best"]
        cr, ci = b["cr"], b["ci"]
        seq, _ = driver_registry(200)
        drv = self.proto["tracks"].get(b.get("track", "TRACK_A"), "V1_FULL")
        vals = seq[drv]
        res = {"depth": {}, "resolution": {}, "alpha": {}, "local": {},
               "repeat": {}, "holdout_targets": {}, "eigenmodes": {},
               "low_frequency": {}, "spectral_surrogates": {}, "highpass": {}}
        for mi in self.proto["validation"]["depths"]:
            res["depth"][str(mi)] = self.score_sequence_at(
                cr, ci, vals, max_iter=mi)["score"]
        for (w, h) in self.proto["validation"]["resolutions"]:
            res["resolution"][f"{w}x{h}"] = self.score_sequence_at(
                cr, ci, vals, width=w, height=h)["score"]
        for a in self.proto["validation"]["alpha_values"]:
            path = os.path.join(ART, "controls", "_val_drv.txt")
            import v3_search as S
            S.write_driver_file(vals, 200, path)
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                       alpha=a, max_iter=200)
            res["alpha"][str(a)] = out.get("score", 0)
        for (dcr, dci) in self.proto["validation"]["local_offsets"]:
            res["local"][f"{dcr:+.3f}_{dci:+.3f}"] = self.score_sequence_at(
                cr + dcr, ci + dci, vals)["score"]
        for sd in self.proto["validation"]["repeat_seeds"]:
            path = os.path.join(ART, "controls", "_val_drv.txt")
            import v3_search as S
            S.write_driver_file(vals, 200, path)
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                       seed=sd, max_iter=200)
            res["repeat"][str(sd)] = out.get("score", 0)
        depth_scores = list(res["depth"].values())
        res["depth_range"] = max(depth_scores) - min(depth_scores)
        rep_scores = list(res["repeat"].values())
        res["repeat_identical"] = len(set(round(x, 12) for x in rep_scores)) == 1
        # holdout targets (no re-optimisation)
        for tgt in self.proto["targets"]["holdout_fields"]:
            res["holdout_targets"][tgt] = self.score_sequence_at(
                cr, ci, vals, target=tgt)["score"]
        for n in range(1, 5):
            for m in range(1, 5):
                res["eigenmodes"][f"T_{n}_{m}"] = self.score_sequence_at(
                    cr, ci, vals, target=f"T_{n}_{m}")["score"]
        # low-frequency family (holdout only)
        for name, fld in M.low_frequency_family(60, 30).items():
            res["low_frequency"][name] = self.score_field(fld)["score"]
        # 10 spectral-matched surrogates of TARGET_A
        ta = self.kernel.target_field("TARGET_A", 60, 30)
        for sd in self.proto["targets"]["spectral_surrogate_seeds"]:
            sur = M.dct_sign_surrogate(ta, 60, 30, sd)
            path = os.path.join(ART, "targets", f"surrogate_{sd}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(" ".join(f"{v:.17g}" for v in sur) + "\n")
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE",
                                       target_file=path, max_iter=200)
            res["spectral_surrogates"][str(sd)] = out.get("score", 0)
        # high-pass resonance (diagnostic only, never the primary score)
        hp_keep = self.proto["targets"]["highpass_keep_modes"]
        target_hp = M.dct_lowpass_field(ta, 60, 30, keep=hp_keep, highpass=True)
        drivers_hp = {"V0_NONE": seq["V0_NONE"], "V1_FULL": seq["V1_FULL"],
                      "V9_EVENT": seq["V9_EVENT"], "V10_RESIDUAL": seq["V10_RESIDUAL"]}
        for name, v in drivers_hp.items():
            path = os.path.join(ART, "targets", f"_hp_{name}.txt")
            import v3_search as S
            S.write_driver_file(v, 200, path)
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                       max_iter=200)
            fld = out.get("field")
            if not fld:
                res["highpass"][name] = None
                continue
            fld_hp = M.dct_lowpass_field(fld, 60, 30, keep=hp_keep, highpass=True)
            full = self.kernel.score_fields(fld, ta, 60, 30)
            res["highpass"][name] = {
                "full_score": full.get("score", 0),
                "pearson_highpass": M._pearson(fld_hp, target_hp),
            }
        self.record("validation", "summary", res)
        self.save_artifact("best", "validation.json", res)
        self.log(f"validation: depth_range={res['depth_range']:.6f} "
                 f"repeat_identical={res['repeat_identical']} "
                 f"TARGET_B={res['holdout_targets'].get('TARGET_B'):.6f} "
                 f"surr_mean={sum(res['spectral_surrogates'].values())/10:.6f}")
        self.state["validation"] = res
        return True

    # ---- temporal prime-event analysis ----------------------------------
    def phase_temporal(self):
        self.log("=== V3 TEMPORAL ANALYSIS ===")
        seq, _ = driver_registry(1000)
        seq5000, _ = driver_registry(5000)
        shifts = self.proto["temporal"]["circular_shifts"]
        out = {"points": {}, "shift_null": {}, "summary": {}}
        points = {
            "V1_best": (self.state["best"]["cr"], self.state["best"]["ci"]),
            "initial_point": (-0.7, 0.27015),
        }
        for tname, info in self.state["search"].items():
            points[f"{tname}_best"] = (info["best"]["cr"], info["best"]["ci"])
        for pname, (cr, ci) in points.items():
            per_driver = {}
            for dname, dseq1000 in seq.items():
                if dname not in self.proto["temporal"]["drivers"]:
                    continue
                try:
                    rows = self.kernel.trace(cr, ci, driver="V0_NONE",
                                             driver_file=self._tmp_driver(
                                                 f"temp_{dname}", seq5000[dname], 5000),
                                             max_iter=5000)
                except RuntimeError as exc:
                    per_driver[dname] = {"status": "TRACE_FAILED", "error": str(exc)}
                    continue
                per_driver[dname] = self._temporal_stats(rows)
            out["points"][pname] = {"c": {"cr": cr, "ci": ci}, "drivers": per_driver}
            self.log(f"  {pname}: " + ", ".join(
                f"{d}={v.get('effect_size', 'NA') if isinstance(v, dict) else 'NA'}"
                for d, v in per_driver.items()))
        # circular-shift nulls on the V1 best point (block permutation policy)
        cr, ci = self.state["best"]["cr"], self.state["best"]["ci"]
        E = seq5000["V9_EVENT"]
        for sh in shifts:
            shifted = M.seq_V12_shifted_event(E, 5000, sh)
            rows = self.kernel.trace(cr, ci, driver="V0_NONE",
                                     driver_file=self._tmp_driver(
                                         f"shift_{sh}", shifted, 5000),
                                     max_iter=5000)
            out["shift_null"][str(sh)] = self._temporal_stats(rows)
        self.record("temporal", "summary", out)
        self.save_artifact("temporal", "temporal.json", out)
        self.state["temporal"] = out
        return True

    def _tmp_driver(self, tag, values, max_iter):
        import v3_search as S
        path = os.path.join(ART, "temporal", f"_drv_{tag}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        S.write_driver_file(values, max_iter, path)
        return path

    def _temporal_stats(self, rows):
        """Baseline-adjusted after-prime response with circular-shift null."""
        w = self.proto["temporal"]["detrend_window"]
        pairs = []
        for r in rows:
            if r["prime"] and r["active_frac"] > 0:
                k = r["iter"]
                base = [q["mean_abs_z"] for q in rows
                        if not q["prime"] and abs(q["iter"] - k) <= 10
                        and q["active_frac"] > 0]
                if base:
                    pairs.append(r["mean_abs_z"] - sum(base) / len(base))
        n = len(pairs)
        if n < self.proto["temporal"]["minimum_pairs"]:
            return {"status": "INSUFFICIENT_ACTIVE_DATA", "pair_count": n}
        mean = sum(pairs) / n
        sd = M.std_flat(pairs)
        effect = mean / sd if sd > 1e-15 else 0.0
        lo, hi = M.block_bootstrap_ci(
            pairs, self.proto["temporal"]["block_bootstrap_block"],
            self.proto["temporal"]["bootstrap_resamples"],
            self.proto["temporal"]["bootstrap_seed"])
        return {"status": "OK", "pair_count": n, "mean_difference": mean,
                "effect_size": effect, "bootstrap_ci": [lo, hi]}

    # ---- WORLD_PRIME benchmark audit ------------------------------------
    def phase_benchmark(self):
        self.log("=== V3 WORLD_PRIME BENCHMARK AUDIT ===")
        import worldforge
        rows = worldforge.generate_benchmark_v2()
        model = worldforge.fit_benchmark_v2(rows)
        for row in rows:
            row.update(worldforge.predict_benchmark_v2(row["features"], model))
        summaries = {s: worldforge.summarize_benchmark_v2(
            r for r in rows if r["split"] == s)
            for s in ("train", "validation", "holdout")}
        prime = [r for r in rows if r["cohort"] == "prime"]
        detected = [r["seed"] for r in prime if r["prediction"] == "computational"]
        hashes = {r["field_hash"] for r in prime}
        train_keys = model.get("training_keys", [])
        leakage = any(k.get("world_type") == "WORLD_PRIME" for k in train_keys)
        cohorts = self.proto["benchmark"]["feature_audit_cohorts"]
        audit = {}
        for c in cohorts:
            subset = [r for r in rows if r["world_type"] == c]
            if not subset:
                continue
            feats = subset[0]["features"]
            audit[c] = {
                "n": len(subset),
                "distinct_field_hashes": len({r["field_hash"] for r in subset}),
                "feature_means": {k: sum(r["features"][k] for r in subset) / len(subset)
                                  for k in feats},
                "predictions": {p: sum(1 for r in subset if r["prediction"] == p)
                                for p in ("natural", "computational")},
            }
        result = {
            "summaries": {s: {"accuracy": v["accuracy"], "confusion": v["confusion"]}
                          for s, v in summaries.items()},
            "prime_detection": {"detected": len(detected), "total": len(prime),
                                 "detected_seeds": detected,
                                 "distinct_hashes": len(hashes)},
            "training_excludes_world_prime": not leakage,
            "detector": model["algorithm"],
            "feature_cohort_audit": audit,
            "interpretation": (
                "WORLD_PRIME is fully held out. A low detection rate is a "
                "legitimate result: the frozen features do not capture the "
                "prime-generated computational structure."),
        }
        self.record("benchmark", "audit", result,
                    score=result["prime_detection"]["detected"] / max(1, len(prime)))
        self.save_artifact("benchmark", "benchmark_audit.json", result)
        self.log(f"benchmark: train={summaries['train']['accuracy']} "
                 f"holdout={summaries['holdout']['accuracy']} "
                 f"prime={len(detected)}/{len(prime)} leakage={leakage}")
        self.state["benchmark"] = result
        return True

    # ---- delta-field explanation ----------------------------------------
    def phase_explanation(self):
        self.log("=== V3 EXPLANATORY DECOMPOSITION ===")
        seq, _ = driver_registry(200)
        b = self.state["best"]
        cr, ci = b["cr"], b["ci"]
        ta = self.kernel.target_field("TARGET_A", 60, 30)
        fields = {}
        for name in ("V0_NONE", "V1_FULL", "V9_EVENT", "V10_RESIDUAL",
                     "S1_ANALYTIC", "S2_DATA_SMOOTHED"):
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE",
                                       driver_file=self._tmp_driver(
                                           f"expl_{name}", seq[name], 200),
                                       max_iter=200)
            fields[name] = out.get("field")
        deltas, f0 = {}, fields["V0_NONE"]
        if not f0:
            self.log("WARNING: V0_NONE field is None, skipping explanation")
            self.state["explanation"] = {"delta_fields": {}, "attribution": {}}
            return True
        t_centered = [ta[i] - f0[i] for i in range(len(ta))]
        for name in ("V1_FULL", "V9_EVENT", "V10_RESIDUAL"):
            fn = fields.get(name)
            if not fn:
                deltas[name] = {"status": "FIELD_UNAVAILABLE"}
                continue
            d = [fn[i] - f0[i] for i in range(len(f0))]
            low, high = M.dct_low_energy(d, 60, 30, keep=3)
            sd_d, sd_t = M.std_flat(d), M.std_flat(t_centered)
            deltas[name] = {
                "rms": sd_d, "max_abs": max(abs(x) for x in d),
                "entropy": M.field_entropy(d),
                "spectral_low_energy": low, "spectral_high_energy": high,
                "autocorrelation": M.field_autocorr(d, 60, 30),
                "correlation_with_target_residual":
                    M._pearson(d, t_centered) if sd_d > 0 and sd_t > 0 else 0.0,
            }
        track = self.state["best"].get("track", "TRACK_A")
        cscores = self.state.get("controls", {}).get(track, {}).get("scores", {})
        attribution = {
            "generic_geometry": self.state.get("field_controls", {}),
            "smooth_forcing": {k: cscores.get(k) for k in
                               ("S1_ANALYTIC", "S2_DATA_SMOOTHED")},
            "prime_residual": deltas.get("V10_RESIDUAL"),
            "prime_event_timing": deltas.get("V9_EVENT"),
            "optimization_selection": {
                "null_mean": self.state.get("null", {}).get("null_mean"),
                "null_max": self.state.get("null", {}).get("null_max")},
            "boundary_effect": self.state.get("boundary", {}),
        }
        explanation = {
            "delta_fields": deltas, "attribution": attribution,
            "note": "Diagnostic attribution, not causal coefficients. "
                    "No hidden machine learning is used.",
        }
        self.record("explanation", "delta_fields", explanation)
        self.save_artifact("best", "delta_fields.json", deltas)
        with open("v3_explanation.json", "w", encoding="utf-8") as f:
            json.dump(explanation, f, indent=2, ensure_ascii=False, sort_keys=True)
        self.log("v3_explanation.json written")
        self.state["explanation"] = explanation
        return True

    # ---- reproducibility + final status ---------------------------------
    def phase_reproducibility(self):
        self.log("=== V3 REPRODUCIBILITY ===")
        seq, _ = driver_registry(200)
        b = self.state["best"]
        drv = self.proto["tracks"].get(b.get("track", "TRACK_A"), "V1_FULL")
        scores = []
        for i in range(3):
            scores.append(self.score_sequence_at(b["cr"], b["ci"], seq[drv])["score"])
        identical = len(set(round(x, 12) for x in scores)) == 1
        integrity = self.store.integrity()
        res = {"canonical_best": {"cr": b["cr"], "ci": b["ci"], "driver": drv},
               "scores": scores, "identical_within_tolerance": identical,
               "db_integrity": integrity}
        self.record("reproducibility", "canonical", res)
        self.save_artifact("best", "reproducibility.json", res)
        self.log(f"reproducibility: {scores} identical={identical} integrity={integrity}")
        self.state["reproducibility"] = res
        return True

    def final_status(self):
        """Classify V3 outcome from the collected evidence (protocol #101/#120)."""
        b = self.state.get("boundary", {})
        if b.get("monotone_increasing_over_full_range"):
            return "BOUNDARY_ARTIFACT"
        return "GENERIC_RESONANCE"

    # ---- report ----------------------------------------------------------
    def phase_report(self):
        self.log("=== V3 REPORT ===")
        from report_v3 import write_report
        mismatches = write_report(self)
        self.state["report_mismatches"] = mismatches
        return not mismatches

    # ---- orchestration ---------------------------------------------------
    PHASES = ["init", "self_test", "protocol_lock", "boundary", "search",
              "controls", "null", "validation", "temporal", "benchmark",
              "explanation", "reproducibility", "report"]

    def restore_state(self):
        """Restore self.state from the V3 store (for resume)."""
        all_r = self.store.all_results()
        for compound_key, entry in all_r.items():
            phase, key = compound_key.split(":", 1)
            if phase not in self.state:
                self.state[phase] = {}
            if isinstance(self.state.get(phase), dict):
                self.state[phase][key] = entry["value"]
        # Reconstruct best from search results
        if "search" in self.state and "best" not in self.state:
            best_score = -1
            for track, info in self.state["search"].items():
                if isinstance(info, dict) and "best" in info:
                    b = info["best"]
                    if b.get("score", 0) > best_score:
                        best_score = b["score"]
                        self.state["best"] = {**b, "track": track}
        self.log(f"Restored state: {list(self.state.keys())}")

    def run(self, phases=None, resume_from=None):
        order = self.PHASES
        if resume_from:
            idx = order.index(resume_from)
            order = order[idx:]
        order = [p for p in order if (phases is None or p in phases)]
        # If resuming, try to restore state from DB
        if resume_from or (phases is not None and "init" not in (phases or [])):
            try:
                self.restore_state()
            except Exception as exc:
                self.log(f"State restore warning: {exc}")
        for name in order:
            fn = getattr(self, f"phase_{name}", None)
            if fn is None:
                continue
            ok = fn()
            if not ok:
                self.log(f"PHASE {name.upper()} FAILED - stopping")
                return False
            self.state["last_phase"] = name
        self.log(f"=== V3 PIPELINE COMPLETE (status: {self.final_status()}) ===")
        return True


def compile_kernel_v3():
    import subprocess
    exe = "kernel_v3.exe" if os.name == "nt" else "kernel_v3"
    if os.path.exists(exe) and os.path.exists("kernel_v3.c"):
        if os.path.getmtime(exe) >= os.path.getmtime("kernel_v3.c"):
            return exe
    r = subprocess.run(["gcc", "-O3", "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                        "-static", "kernel_v3.c", "-lm", "-o", exe],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kernel_v3 compile failed: {r.stderr[:500]}")
    return exe


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Proof of Simulation V3 pipeline")
    ap.add_argument("--time-budget", type=int, default=14400)
    ap.add_argument("--null-runs", type=int, default=None)
    ap.add_argument("--phases", type=str, default=None,
                    help="comma separated phase names")
    ap.add_argument("--resume-from", type=str, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    phases = args.phases.split(",") if args.phases else None
    p = V3Pipeline(time_budget=args.time_budget, quiet=args.quiet,
                   null_runs=args.null_runs)
    return p.run(phases=phases, resume_from=args.resume_from)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)