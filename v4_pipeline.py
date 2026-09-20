"""
Proof of Simulation V4 — Interior Dynamics, Prime-Specific Contrast pipeline.

Central question (protocol §79): after removing boundary effects, smooth forcing,
generic low-frequency geometry, event-density effects and search selection bias,
does anything remain that is specifically related to the arithmetic placement of
the prime numbers?

V4 key changes from V3:
  - Interior regime search in [-1.5, 1.5]² (not boundary-dominated)
  - Admissibility filtering on V0 diagnostics
  - Contrast-based optimization (C_full, C_event, C_residual)
  - Multi-start search (8 deterministic starts)
  - Track-local full control matrix
  - Full-field temporal observables with bounded transform
  - 100 spectral surrogates
  - S1 audit, V9 magnitude audit, difference fields, high-pass
"""
import json
import math
import os
import time

import v4_math as M
import v4_protocol as P4
from v4_store import V4Store
from v3_search import V3Kernel, write_driver_file
from v4_search import V4Search

ART = "v4_artifacts"


def build_sequences(max_iter, window=5):
    """Build all V4 driver sequences deterministically."""
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
        "V9_Z": M.seq_V9_Z(E, max_iter),
        "V9_RMS_MATCHED": M.seq_V9_RMS_MATCHED(E, Pc, max_iter),
        "V10_RESIDUAL": V10,
        "V5_SHUFFLED": M.seq_V5_shuffled(P, max_iter, 7331),
    }
    return seq


def driver_registry(max_iter, window=5):
    """Full registry with hashes, stats and taxonomy."""
    seq = build_sequences(max_iter, window)
    reg = {}
    for name, values in seq.items():
        reg[name] = {
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


class V4Pipeline:
    """V4 phase machine: interior scout → contrast search → controls → null →
    temporal → validation → report."""

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

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[V4 {ts}] {msg}"
        self.log_lines.append(line)
        if not self.quiet:
            print(line, flush=True)
        try:
            with open("run_v4.log", "a", encoding="utf-8") as f:
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

    def _drv_file(self, name, seq, max_iter=200):
        vals = seq[name]
        h = M.sequence_hash(vals[1:max_iter + 1])
        path = os.path.join(ART, "controls", f"_drv_{name}_{h[:10]}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            write_driver_file(vals, max_iter, path)
        return path

    def _tmp_driver(self, tag, values, max_iter):
        path = os.path.join(ART, "temporal", f"_drv_{tag}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_driver_file(values, max_iter, path)
        return path

    def score_driver_at(self, cr, ci, drv_name, seq, max_iter=200,
                        width=60, height=30, target="TARGET_A"):
        path = self._drv_file(drv_name, seq, max_iter)
        out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                   max_iter=max_iter, width=width, height=height,
                                   target=target)
        return {"score": out.get("score", 0), "pearson01": out.get("pearson01", 0),
                "escaped_fraction": out.get("escaped_fraction", 0),
                "field": out.get("field"), "error": out.get("error")}

    def score_sequence_at(self, cr, ci, values, max_iter=200, width=60,
                          height=30, target="TARGET_A"):
        h = M.sequence_hash(values[1:max_iter + 1])
        path = os.path.join(ART, "controls", f"_seq_{h[:12]}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            write_driver_file(values, max_iter, path)
        out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                   max_iter=max_iter, width=width, height=height,
                                   target=target)
        return {"score": out.get("score", 0), "pearson01": out.get("pearson01", 0),
                "escaped_fraction": out.get("escaped_fraction", 0),
                "field": out.get("field"), "error": out.get("error")}

    # ================================================================ PHASES
    def phase_init(self):
        self.log("=== V4 INIT ===")
        for sub in ("best", "controls", "matched_events", "boundary", "temporal",
                    "targets", "null", "benchmark", "audit", "interior",
                    "difference_fields", "surrogates"):
            os.makedirs(os.path.join(ART, sub), exist_ok=True)
        self.proto = P4.save_protocol_v4()
        self.phash = P4.protocol_v4_hash(self.proto)
        self.shash = P4.source_v4_hash()
        import subprocess
        exe = "kernel_v3.exe" if os.name == "nt" else "kernel_v3"
        src = "kernel_v3.c"
        need_build = True
        if os.path.exists(exe) and os.path.exists(src):
            need_build = os.path.getmtime(exe) < os.path.getmtime(src)
        if need_build:
            cc = "gcc"
            cmd = [cc, "-O3", "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                   "-static", src, "-lm", "-o", exe]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                self.log(f"COMPILATION FAILED: {r.stderr[:400]}")
                return False
            self.log(f"Compiled {exe}")
        self.bhash = P4.binary_v4_hash(exe)
        self.kernel = V3Kernel(exe)
        self.store = V4Store(".", self.phash, self.shash, self.bhash)
        self.run_id = f"V4_DEEP_{int(self.start_time)}"
        self.log(f"protocol={self.phash[:16]} source={self.shash[:16]} "
                 f"binary={self.bhash[:16]}")
        self.record("provenance", "hashes", {
            "protocol_hash": self.phash, "source_hash": self.shash,
            "binary_hash": self.bhash, "environment": P4.environment(),
            "run_id": self.run_id})
        return True

    def phase_self_test(self):
        self.log("=== V4 SELF TEST ===")
        import subprocess
        from v3_search import _kernel_env
        exe = self.kernel.kernel_path
        r = subprocess.run([exe, "--self-test"], capture_output=True, text=True,
                           env=_kernel_env(), timeout=120)
        ok = r.returncode == 0
        self.log(f"kernel self-test: {'PASSED' if ok else 'FAILED'}")
        # S1 audit (protocol §53-54)
        audit = M.s1_audit(200)
        self.log(f"S1 audit: ok={audit['ok']} issues={len(audit['issues'])}")
        # Driver registry
        seq, reg = driver_registry(200)
        # Driver collision check
        names = sorted(seq)
        collisions = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if reg[names[i]]["hash"] == reg[names[j]]["hash"]:
                    collisions.append({"a": names[i], "b": names[j]})
        # V9 magnitude audit (protocol §49)
        E = seq["V9_EVENT"]
        v9_audit = {}
        for mi in self.proto["v9_audit_depths"]:
            pi = M.pi_counts(mi)
            P = M.seq_P(pi, mi)
            E_mi = M.seq_E(P, mi)
            v9_audit[mi] = M.event_magnitude_audit(E_mi, mi)
        # Driver audit S1 vs V1 (protocol §55)
        drv_audit = M.driver_audit(200)
        self.record("self_test", "kernel", {"passed": ok})
        self.record("self_test", "s1_audit", audit)
        self.record("self_test", "v9_magnitude", v9_audit)
        self.record("self_test", "driver_audit", drv_audit)
        self.record("self_test", "collisions", collisions)
        # Save driver audit files (protocol §55)
        pi200 = M.pi_counts(200)
        P200 = M.seq_P(pi200, 200)
        S1_200 = M.seq_S1_riemann(200)
        diff_200 = [0.0] + [P200[k] - S1_200[k] for k in range(1, 201)]
        for tag, vals in [("s1_driver", S1_200), ("v1_driver", P200),
                          ("difference_driver", diff_200)]:
            path = os.path.join(ART, "audit", f"{tag}.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(repr(vals[k]) for k in range(1, 201)) + "\n")
        self.save_artifact("audit", "self_test.json", {
            "kernel": ok, "s1_audit": audit, "v9_magnitude": v9_audit,
            "driver_audit": drv_audit, "collisions": collisions,
            "registry": reg})
        self.state["self_test"] = {"kernel_ok": ok, "s1_ok": audit["ok"],
                                   "collisions": len(collisions)}
        return ok

    def phase_protocol_lock(self):
        self.log("=== V4 PROTOCOL LOCK ===")
        self.record("provenance", "protocol", self.proto)
        return True

    def phase_interior_scout(self):
        self.log("=== V4 INTERIOR SCOUT ===")
        seq, _ = driver_registry(200)
        lo_cr, hi_cr, lo_ci, hi_ci = self.proto["scout_domain"]
        g = self.proto["scout_grid"]
        grid = []
        for i in range(g):
            for j in range(g):
                cr = lo_cr + (hi_cr - lo_cr) * i / (g - 1)
                ci = lo_ci + (hi_ci - lo_ci) * j / (g - 1)
                grid.append((cr, ci))
        # Evaluate V0 at all grid points
        cands = [{"candidate_id": idx + 1, "cr": cr, "ci": ci,
                  "max_iter": 200, "seed": 7331, "alpha": 1.0,
                  "degree": 2, "channel": 0}
                 for idx, (cr, ci) in enumerate(grid)]
        v0_path = self._drv_file("V0_NONE", seq, 200)
        results = self.kernel.batch(cands, driver="V0_NONE", driver_file=v0_path,
                                    width=60, height=30, target="TARGET_A")
        scout_data = []
        admissible_count = 0
        for (cr, ci), r in zip(grid, results):
            if r.get("error_code", 0) != 0:
                scout_data.append({"cr": cr, "ci": ci, "admissible": False,
                                   "reason": "kernel_error"})
                continue
            ef = r.get("escaped_fraction", 1.0)
            ent = r.get("entropy", 0.0)
            adm, reason = M.check_admissibility(ef, ent, 0.05)
            if adm:
                admissible_count += 1
            scout_data.append({"cr": cr, "ci": ci, "admissible": adm,
                               "reason": reason,
                               "escaped_fraction": ef, "entropy": ent,
                               "score_V0": r.get("score", 0)})
        self.record("interior_scout", "grid", {
            "total": len(scout_data), "admissible": admissible_count,
            "domain": self.proto["scout_domain"], "grid_size": g})
        self.save_artifact("interior", "interior_map.json", scout_data)
        # Also save interior_map.txt and interior_map.svg (protocol §9)
        txt_path = os.path.join(ART, "interior", "interior_map.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("# Interior Scout Map\n")
            f.write(f"# Domain: {self.proto['scout_domain']}\n")
            f.write(f"# Grid: {g}x{g}, Admissible: {admissible_count}/{len(scout_data)}\n")
            f.write("# cr\tci\tescaped_frac\tentropy\tadmissible\n")
            for sd in scout_data:
                f.write(f"{sd['cr']:.4f}\t{sd['ci']:.4f}\t"
                        f"{sd.get('escaped_fraction', 'N/A')}\t"
                        f"{sd.get('entropy', 'N/A')}\t"
                        f"{sd.get('admissible', False)}\n")
        # SVG visualization
        svg_path = os.path.join(ART, "interior", "interior_map.svg")
        sz = 400
        margin = 20
        dot_r = max(2, (sz - 2 * margin) // (g * 2))
        svg_lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{sz}" height="{sz}">']
        svg_lines.append(f'<rect width="{sz}" height="{sz}" fill="#111"/>')
        lo, hi = self.proto["scout_domain"][0], self.proto["scout_domain"][1]
        for sd in scout_data:
            px = margin + int((sd["cr"] - lo) / (hi - lo) * (sz - 2 * margin))
            py = margin + int((sd["ci"] - lo) / (hi - lo) * (sz - 2 * margin))
            color = "#0f0" if sd.get("admissible") else "#555"
            svg_lines.append(f'<circle cx="{px}" cy="{py}" r="{dot_r}" fill="{color}"/>')
        svg_lines.append(f'<text x="{sz//2}" y="14" fill="white" text-anchor="middle" font-size="12">'
                         f'Interior Scout: {admissible_count}/{len(scout_data)} admissible</text>')
        svg_lines.append('</svg>')
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(svg_lines) + "\n")
        self.log(f"interior scout: {admissible_count}/{len(scout_data)} admissible")
        self.state["interior_scout"] = {
            "total": len(scout_data), "admissible": admissible_count,
            "grid": scout_data}
        return True

    def phase_search(self):
        self.log("=== V4 CONTRAST SEARCH (3 tracks) ===")
        seq, _ = driver_registry(200)
        domain = tuple(self.proto["domain"])
        results = {}
        E = seq["V9_EVENT"]
        # Build V11 sequences for TRACK_B contrast (protocol §18)
        v11_seqs = [M.seq_V11_matched_event(E, 200, sd)
                    for sd in self.proto["search_control_seeds"]]
        track_configs = {
            "TRACK_A": ("V1_FULL", seq["V1_FULL"]),
            "TRACK_B": ("V9_EVENT", seq["V9_EVENT"]),
            "TRACK_C": ("V10_RESIDUAL", seq["V10_RESIDUAL"]),
        }
        for track, (drv_name, drv_seq) in track_configs.items():
            run_id = f"V4_PRIMARY_{track}_{int(time.time())}"
            # Pass V11 seqs only for TRACK_B
            v11_for_track = v11_seqs if track == "TRACK_B" else None
            search = V4Search(
                self.store, self.kernel, run_id, track, drv_name, drv_seq,
                seq_V0=seq["V0_NONE"], seq_S1=seq["S1_ANALYTIC"],
                seq_S2=seq["S2_DATA_SMOOTHED"],
                seed=self.proto["search_seeds"][0], target="TARGET_A",
                steps=self.proto["search"]["logical_steps"],
                scout_grid=self.proto["search"]["scout_grid"],
                domain=domain, start_time=self.start_time,
                time_budget=self.time_budget, driver_dir=ART,
                v11_seqs=v11_for_track)
            best = search.run()
            acc = search.accounting()
            results[track] = {"best": best, "accounting": acc, "run_id": run_id}
            self.record("search", track, {"best": best, "accounting": acc},
                        score=best.get("score", 0))
            self.log(f"{track} ({drv_name}): contrast={best.get('contrast', 0):+.6f} "
                     f"score={best.get('score', 0):.6f} "
                     f"at ({best.get('cr', 0):.6f},{best.get('ci', 0):.6f})")
            if best.get("contrast", -999) > self.state.get("best", {}).get("contrast", -999):
                self.state["best"] = {**best, "track": track}
        self.state["search"] = results
        self.save_artifact("best", "search_results.json",
                           {"tracks": results, "best": self.state.get("best")})
        return True

    def phase_controls(self):
        self.log("=== V4 TRACK-LOCAL CONTROLS ===")
        seq, _ = driver_registry(200)
        search_seeds = self.proto["matched_event_seeds_search"]
        search_shifts = self.proto["shifted_event_shifts_search"]
        holdout_seeds = self.proto["holdout_control_seeds"]
        holdout_shifts = self.proto["shifted_event_shifts_holdout"]
        controls = {}
        E = seq["V9_EVENT"]
        for track, info in self.state["search"].items():
            b = info["best"]
            cr, ci = b["cr"], b["ci"]
            track_drv_name = self.proto["tracks"].get(track, "V1_FULL")
            track_drv_seq = seq[track_drv_name]
            # Full control matrix (protocol §32)
            scores = {}
            for drv_name in ("V0_NONE", "V1_FULL", "S1_ANALYTIC", "S2_DATA_SMOOTHED",
                             "V9_EVENT", "V10_RESIDUAL", "V9_Z", "V9_RMS_MATCHED",
                             "V5_SHUFFLED"):
                r = self.score_driver_at(cr, ci, drv_name, seq)
                scores[drv_name] = r["score"]
            # Matched event families
            fam = {"V11": {}, "V12": {}, "V13": {}}
            for sd in search_seeds:
                fam["V11"][str(sd)] = self.score_sequence_at(
                    cr, ci, M.seq_V11_matched_event(E, 200, sd))["score"]
                fam["V13"][str(sd)] = self.score_sequence_at(
                    cr, ci, M.seq_V13_gap_matched(E, 200, sd))["score"]
            for sh in search_shifts:
                fam["V12"][str(sh)] = self.score_sequence_at(
                    cr, ci, M.seq_V12_shifted_event(E, 200, sh))["score"]
            # Holdout matched events
            fam_holdout = {"V11": {}, "V12": {}, "V13": {}}
            for sd in holdout_seeds:
                fam_holdout["V11"][str(sd)] = self.score_sequence_at(
                    cr, ci, M.seq_V11_matched_event(E, 200, sd))["score"]
                fam_holdout["V13"][str(sd)] = self.score_sequence_at(
                    cr, ci, M.seq_V13_gap_matched(E, 200, sd))["score"]
            for sh in holdout_shifts:
                fam_holdout["V12"][str(sh)] = self.score_sequence_at(
                    cr, ci, M.seq_V12_shifted_event(E, 200, sh))["score"]
            # Compute contrasts
            mean_v11_search = sum(fam["V11"].values()) / max(1, len(fam["V11"]))
            mean_v12_search = sum(fam["V12"].values()) / max(1, len(fam["V12"]))
            mean_v13_search = sum(fam["V13"].values()) / max(1, len(fam["V13"]))
            all_v11 = {**fam["V11"], **fam_holdout["V11"]}
            all_v12 = {**fam["V12"], **fam_holdout["V12"]}
            all_v13 = {**fam["V13"], **fam_holdout["V13"]}
            mean_v11_all = sum(all_v11.values()) / max(1, len(all_v11))
            mean_v12_all = sum(all_v12.values()) / max(1, len(all_v12))
            mean_v13_all = sum(all_v13.values()) / max(1, len(all_v13))
            contrasts = {
                "C_full": M.compute_contrast_C_full(
                    scores["V1_FULL"], scores["V0_NONE"],
                    scores["S1_ANALYTIC"], scores["S2_DATA_SMOOTHED"]),
                "C_event": M.compute_contrast_C_event(
                    scores["V9_EVENT"], mean_v11_search),
                "C_residual": M.compute_contrast_C_residual(
                    scores["V10_RESIDUAL"], scores["S1_ANALYTIC"],
                    scores["S2_DATA_SMOOTHED"]),
                "C_event_all": scores["V9_EVENT"] - mean_v11_all,
                "C_shift_search": scores["V9_EVENT"] - mean_v12_search,
                "C_shift_all": scores["V9_EVENT"] - mean_v12_all,
                "C_gap_search": scores["V9_EVENT"] - mean_v13_search,
                "C_gap_all": scores["V9_EVENT"] - mean_v13_all,
                "V1_minus_V0": scores["V1_FULL"] - scores["V0_NONE"],
                "V1_minus_max_S1_S2": scores["V1_FULL"] - max(
                    scores["S1_ANALYTIC"], scores["S2_DATA_SMOOTHED"]),
            }
            # Boundary distance and gradient (protocol §33)
            dist, edge = M.boundary_distance(cr, ci, tuple(self.proto["domain"]))
            boundary_suspect = dist < self.proto["boundary_suspect_threshold"]
            # Gradient to boundary: finite-difference gradient of score toward nearest edge
            lo_d, hi_d, lo_i, hi_i = self.proto["domain"]
            edge_cr = lo_d if edge == "lo_cr" else (hi_d if edge == "hi_cr" else cr)
            edge_ci = lo_i if edge == "lo_ci" else (hi_i if edge == "hi_ci" else ci)
            grad_dcr = (edge_cr - cr) * 0.01
            grad_dci = (edge_ci - ci) * 0.01
            if abs(grad_dcr) < 1e-12:
                grad_dcr = 0.01
            if abs(grad_dci) < 1e-12:
                grad_dci = 0.01
            sc_at = self.score_sequence_at(cr, ci, track_drv_seq)
            sc_edge = self.score_sequence_at(cr + grad_dcr, ci + grad_dci, track_drv_seq)
            grad_to_boundary = (sc_edge["score"] - sc_at["score"]) / (
                (grad_dcr**2 + grad_dci**2)**0.5 + 1e-15)
            entry = {
                "point": {"cr": cr, "ci": ci},
                "scores": scores, "contrasts": contrasts,
                "matched_family": fam,
                "matched_family_holdout": fam_holdout,
                "boundary_distance": {"fraction": dist, "nearest_edge": edge,
                                      "BOUNDARY_SUSPECT": boundary_suspect,
                                      "gradient_to_boundary": grad_to_boundary},
                "generic_geometry": {},
            }
            # Generic geometry controls (protocol §56)
            N_pix = 60 * 30
            for gtag, gvals in [
                ("constant", [0.0] + [0.0] * 200),
                ("x_ramp", [0.0] + [k / 200.0 for k in range(1, 201)]),
                ("y_ramp", [0.0] + [k / 200.0 for k in range(1, 201)]),
                ("bilinear", [0.0] + [min(k, 201 - k) / 100.0 for k in range(1, 201)]),
                ("radial", [0.0] + [((k - 100) / 100.0) ** 2 for k in range(1, 201)]),
                ("low_freq", [0.0] + [0.5 * math.cos(math.pi * k / 200.0) for k in range(1, 201)]),
            ]:
                entry["generic_geometry"][gtag] = self.score_sequence_at(
                    cr, ci, gvals)["score"]
            controls[track] = entry
            self.record("controls", track, entry)
            self.save_artifact("controls", f"controls_{track}.json", entry)
            self.log(f"{track}: C_full={contrasts['C_full']:+.6f} "
                     f"C_event={contrasts['C_event']:+.6f} "
                     f"C_residual={contrasts['C_residual']:+.6f} "
                     f"boundary_dist={dist:.3f}{' SUSPECT' if boundary_suspect else ''}")
        self.state["controls"] = controls
        return True

    def phase_null(self):
        self.log("=== V4 SEARCH-AWARE NULL ===")
        n_runs = self.null_runs or self.proto["null"]["standard_runs"]
        lo_cr, hi_cr, lo_ci, hi_ci = self.proto["domain"]
        budget = (self.proto["search"]["scout_grid"] ** 2 +
                  self.proto["search"]["logical_steps"] * 9)
        seq, _ = driver_registry(200)
        best_track = self.state.get("best", {}).get("track", "TRACK_A")
        drv = self.proto["tracks"].get(best_track, "V1_FULL")
        dpath = os.path.join(ART, "null", f"_null_drv_{drv}.txt")
        write_driver_file(seq[drv], 200, dpath)
        maxima = []
        for i in range(n_runs):
            seed = self.proto["null"]["search_seeds"][
                i % len(self.proto["null"]["search_seeds"])]
            rng = M.splitmix64(seed)
            run_id = f"V4_NULL_r{i}_{int(time.time())}"
            self.store.create_run(run_id, {"role": "NULL", "driver": drv,
                                           "seed": seed, "budget": budget})
            best_score = -1.0
            best_cr = best_ci = 0.0
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
                        best_score = r["score"]
                        best_cr, best_ci = c["cr"], c["ci"]
                self.store.commit_step(run_id, done // 289, evals,
                                       {"null_index": i, "done": done})
                done += n
            self.store.finish_run(run_id, "FINISHED")
            maxima.append({"run": i, "seed": seed, "null_best": best_score,
                           "cr": best_cr, "ci": best_ci})
            if (i + 1) % 8 == 0:
                self.log(f"  null {i+1}/{n_runs}: max so far "
                         f"{max(m['null_best'] for m in maxima):.6f}")
            if self.budget_left() <= 0:
                break
        observed = self.state.get("best", {}).get("score", 0)
        vals = [m["null_best"] for m in maxima]
        count_exceeding = sum(1 for v in vals if v >= observed)
        n = len(vals)
        stats = {
            "N_null": n, "count_exceeding": count_exceeding,
            "null_max": max(vals) if vals else 0,
            "null_mean": sum(vals) / n if n else 0,
            "null_std": M.std_flat(vals) if n else 0,
            "percentile": 100.0 * count_exceeding / n if n else 0,
            "empirical_search_null": (1 + count_exceeding) / (1 + n),
            "observed_best": observed,
            "formula": self.proto["null"]["exceedance_formula"],
            "runs": maxima,
        }
        self.record("null", "stats", stats, score=stats["null_max"])
        self.save_artifact("null", "null_results.json", stats)
        self.log(f"null: N={n} max={stats['null_max']:.6f} "
                 f"observed={observed:.6f} p_emp={stats['empirical_search_null']:.4f}")
        self.state["null"] = stats
        # Random-parameter null (protocol §29): 32 runs with random alpha/seed
        rp_runs = self.proto["null"].get("random_param_runs", 32)
        rp_maxima = []
        for i in range(rp_runs):
            seed = self.proto["null"]["search_seeds"][
                (i + 100) % len(self.proto["null"]["search_seeds"])]
            rng = M.splitmix64(seed + 9999)
            alpha = 0.1 + (rng() / 2**64) * 1.9  # alpha in [0.1, 2.0]
            run_id = f"V4_RANDPARAM_r{i}_{int(time.time())}"
            self.store.create_run(run_id, {"role": "RANDPARAM_NULL",
                                           "driver": drv, "seed": seed,
                                           "alpha": alpha})
            best_score = -1.0
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
                        "max_iter": 200, "seed": seed, "alpha": alpha,
                        "degree": 2, "channel": 0})
                results = self.kernel.batch(cands, driver="V0_NONE",
                                            driver_file=dpath, width=60, height=30,
                                            target="TARGET_A")
                for r in results:
                    if r.get("error_code", 0) == 0 and r.get("score", -1) > best_score:
                        best_score = r["score"]
                done += n
            self.store.finish_run(run_id, "FINISHED")
            rp_maxima.append({"run": i, "null_best": best_score, "alpha": alpha})
            if self.budget_left() <= 0:
                break
        if rp_maxima:
            rp_vals = [m["null_best"] for m in rp_maxima]
            rp_stats = {
                "N": len(rp_vals),
                "null_max": max(rp_vals),
                "null_mean": sum(rp_vals) / len(rp_vals),
                "null_std": M.std_flat(rp_vals),
                "count_exceeding": sum(1 for v in rp_vals if v >= observed),
                "runs": rp_maxima,
            }
            self.record("null", "random_param", rp_stats)
            self.save_artifact("null", "random_param_null.json", rp_stats)
            self.state["null"]["random_param"] = rp_stats
            self.log(f"random-param null: N={rp_stats['N']} max={rp_stats['null_max']:.6f}")
        return True

    def phase_temporal(self):
        self.log("=== V4 TEMPORAL ANALYSIS ===")
        seq5000, _ = driver_registry(5000)
        shifts = self.proto["temporal"]["circular_shifts"]
        out = {"points": {}, "shift_null": {}, "summary": {}}
        points = {}
        for tname, info in self.state.get("search", {}).items():
            points[f"{tname}_best"] = (info["best"]["cr"], info["best"]["ci"])
        for pname, (cr, ci) in points.items():
            per_driver = {}
            # Protocol §43: V0, V1, V9, V10, V11, V12
            E5k = seq5000["V9_EVENT"]
            temporal_drivers = {
                "V0_NONE": seq5000["V0_NONE"],
                "V1_FULL": seq5000["V1_FULL"],
                "V9_EVENT": seq5000["V9_EVENT"],
                "V10_RESIDUAL": seq5000["V10_RESIDUAL"],
                "V11_matched": M.seq_V11_matched_event(E5k, 5000, 101),
                "V12_shifted": M.seq_V12_shifted_event(E5k, 5000, 1),
            }
            for dname, dseq in temporal_drivers.items():
                try:
                    rows = self.kernel.trace(cr, ci, driver="V0_NONE",
                                             driver_file=self._tmp_driver(
                                                 f"temp_{pname}_{dname}",
                                                 dseq, 5000),
                                             max_iter=5000)
                except RuntimeError as exc:
                    per_driver[dname] = {"status": "TRACE_FAILED", "error": str(exc)}
                    continue
                per_driver[dname] = self._temporal_stats(rows)
            # Prime-event response (§44): Δq(t) between prime and matched non-prime
            prime_response = self._prime_event_response(rows if 'rows' in dir() else [])
            out["points"][pname] = {"c": {"cr": cr, "ci": ci},
                                     "drivers": per_driver,
                                     "prime_event_response": prime_response}
        # Circular-shift nulls
        cr, ci = self.state.get("best", {}).get("cr", 0), \
                 self.state.get("best", {}).get("ci", 0)
        if cr or ci:
            E = seq5000["V9_EVENT"]
            for sh in shifts:  # Use ALL 16 shifts (protocol §46)
                shifted = M.seq_V12_shifted_event(E, 5000, sh)
                try:
                    rows = self.kernel.trace(cr, ci, driver="V0_NONE",
                                             driver_file=self._tmp_driver(
                                                 f"shift_{sh}", shifted, 5000),
                                             max_iter=5000)
                    out["shift_null"][str(sh)] = self._temporal_stats(rows)
                except RuntimeError:
                    out["shift_null"][str(sh)] = {"status": "TRACE_FAILED"}
        self.record("temporal", "summary", out)
        self.save_artifact("temporal", "temporal.json", out)
        self.state["temporal"] = out
        return True

    def _temporal_stats(self, rows):
        """Full-field temporal statistics (protocol §40-47)."""
        w = self.proto["temporal"]["detrend_window"]
        pairs = []
        for r in rows:
            if r["prime"] and r.get("active_frac", 0) > 0:
                k = r["iter"]
                base = [q["mean_abs_z"] for q in rows
                        if not q["prime"] and abs(q["iter"] - k) <= w
                        and q.get("active_frac", 0) > 0]
                if base:
                    pairs.append(r["mean_abs_z"] - sum(base) / len(base))
        n = len(pairs)
        if n < self.proto["temporal"]["minimum_pairs"]:
            return {"status": "INSUFFICIENT_ACTIVE_DATA", "pair_count": n}
        mean_val = sum(pairs) / n
        sd = M.std_flat(pairs)
        effect = mean_val / sd if sd > 1e-15 else 0.0
        lo, hi = M.block_bootstrap_ci(
            pairs, self.proto["temporal"]["block_bootstrap_block"],
            self.proto["temporal"]["bootstrap_resamples"],
            self.proto["temporal"]["bootstrap_seed"])
        return {"status": "OK", "pair_count": n, "mean_difference": mean_val,
                "effect_size": effect, "bootstrap_ci": [lo, hi],
                "observed_delta": mean_val, "null_mean": 0, "null_std": 0}

    def _prime_event_response(self, rows):
        """Prime-event Δq(t) response (protocol §44)."""
        if not rows:
            return {"status": "NO_DATA"}
        w = self.proto["temporal"]["detrend_window"]
        prime_deltas = []
        nonprime_deltas = []
        for r in rows:
            if r.get("active_frac", 0) <= 0:
                continue
            k = r["iter"]
            base = [q["mean_abs_z"] for q in rows
                    if not q["prime"] and abs(q["iter"] - k) <= w
                    and q.get("active_frac", 0) > 0]
            if not base:
                continue
            delta = r["mean_abs_z"] - sum(base) / len(base)
            if r["prime"]:
                prime_deltas.append(delta)
            else:
                nonprime_deltas.append(delta)
        if not prime_deltas or not nonprime_deltas:
            return {"status": "INSUFFICIENT_DATA",
                    "n_prime": len(prime_deltas), "n_nonprime": len(nonprime_deltas)}
        mean_prime = sum(prime_deltas) / len(prime_deltas)
        mean_nonprime = sum(nonprime_deltas) / len(nonprime_deltas)
        return {
            "status": "OK",
            "n_prime": len(prime_deltas),
            "n_nonprime": len(nonprime_deltas),
            "mean_prime_delta": mean_prime,
            "mean_nonprime_delta": mean_nonprime,
            "delta_q": mean_prime - mean_nonprime,
        }

    def phase_validation(self):
        self.log("=== V4 VALIDATION ===")
        b = self.state.get("best", {})
        cr, ci = b.get("cr", 0), b.get("ci", 0)
        seq, _ = driver_registry(200)
        drv = self.proto["tracks"].get(b.get("track", "TRACK_A"), "V1_FULL")
        vals = seq[drv]
        res = {"depth": {}, "resolution": {}, "alpha": {}, "local": {},
               "repeat": {}, "holdout_targets": {}, "local_stability": {}}
        for mi in self.proto["validation"]["depths"]:
            res["depth"][str(mi)] = self.score_sequence_at(
                cr, ci, vals, max_iter=mi)["score"]
        for (w, h) in self.proto["validation"]["resolutions"]:
            res["resolution"][f"{w}x{h}"] = self.score_sequence_at(
                cr, ci, vals, width=w, height=h)["score"]
        for a in self.proto["validation"]["alpha_values"]:
            path = os.path.join(ART, "controls", "_val_drv.txt")
            write_driver_file(vals, 200, path)
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                       alpha=a, max_iter=200)
            res["alpha"][str(a)] = out.get("score", 0)
        for (dcr, dci) in self.proto["validation"]["local_offsets"]:
            res["local"][f"{dcr:+.3f}_{dci:+.3f}"] = self.score_sequence_at(
                cr + dcr, ci + dci, vals)["score"]
        for sd in self.proto["validation"]["repeat_seeds"]:
            path = os.path.join(ART, "controls", "_val_drv.txt")
            write_driver_file(vals, 200, path)
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE", driver_file=path,
                                       seed=sd, max_iter=200)
            res["repeat"][str(sd)] = out.get("score", 0)
        rep_scores = list(res["repeat"].values())
        res["repeat_identical"] = len(set(round(x, 12) for x in rep_scores)) == 1
        # Local stability check (protocol §35): ±eps on cr, ci, diagonals
        eps = 0.005
        stability_offsets = [
            (eps, 0), (-eps, 0), (0, eps), (0, -eps),
            (eps, eps), (-eps, -eps), (-eps, eps), (eps, -eps)]
        for dcr, dci in stability_offsets:
            label = f"{dcr:+.4f}_{dci:+.4f}"
            sc = self.score_sequence_at(cr + dcr, ci + dci, vals)
            # Also compute contrast at ±eps (protocol §35)
            contrasts_eps = {}
            for dn in ("V0_NONE", "V1_FULL", "S1_ANALYTIC", "S2_DATA_SMOOTHED",
                        "V9_EVENT", "V10_RESIDUAL"):
                contrasts_eps[dn] = self.score_driver_at(
                    cr + dcr, ci + dci, dn, seq)["score"]
            contrasts_eps["C_full"] = M.compute_contrast_C_full(
                contrasts_eps["V1_FULL"], contrasts_eps["V0_NONE"],
                contrasts_eps["S1_ANALYTIC"], contrasts_eps["S2_DATA_SMOOTHED"])
            contrasts_eps["C_event"] = M.compute_contrast_C_event(
                contrasts_eps["V9_EVENT"],
                contrasts_eps.get("V11_mean", contrasts_eps["V0_NONE"]))
            contrasts_eps["C_residual"] = M.compute_contrast_C_residual(
                contrasts_eps["V10_RESIDUAL"], contrasts_eps["S1_ANALYTIC"],
                contrasts_eps["S2_DATA_SMOOTHED"])
            res["local_stability"][label] = {
                "score": sc["score"],
                "C_full": contrasts_eps["C_full"],
                "C_event": contrasts_eps["C_event"],
                "C_residual": contrasts_eps["C_residual"],
            }
        # Also compute contrast at center for comparison
        center_scores = self.score_sequence_at(cr, ci, vals)
        center_ctrl = self.state.get("controls", {}).get(
            b.get("track", "TRACK_A"), {}).get("contrasts", {})
        res["local_stability"]["center"] = {
            "score": center_scores["score"],
            "C_full": center_ctrl.get("C_full", 0),
            "C_event": center_ctrl.get("C_event", 0),
            "C_residual": center_ctrl.get("C_residual", 0),
        }
        for tgt in self.proto["holdout_targets"]:
            res["holdout_targets"][tgt] = self.score_sequence_at(
                cr, ci, vals, target=tgt)["score"]
        for n, m in self.proto["holdout_eigenmodes"]:
            res["holdout_targets"][f"T_{n}_{m}"] = self.score_sequence_at(
                cr, ci, vals, target=f"T_{n}_{m}")["score"]
        self.record("validation", "summary", res)
        self.save_artifact("best", "validation.json", res)
        self.state["validation"] = res
        self.log(f"validation: repeat_identical={res['repeat_identical']} "
                 f"depths={list(res['depth'].values())}")
        return True

    def phase_difference_field(self):
        self.log("=== V4 DIFFERENCE FIELD ANALYSIS ===")
        seq, _ = driver_registry(200)
        b = self.state.get("best", {})
        cr, ci = b.get("cr", 0), b.get("ci", 0)
        ta = self.kernel.target_field("TARGET_A", 60, 30)
        fields = {}
        for name in ("V0_NONE", "V1_FULL", "V9_EVENT", "V10_RESIDUAL",
                     "S1_ANALYTIC", "S2_DATA_SMOOTHED"):
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE",
                                       driver_file=self._tmp_driver(
                                           f"diff_{name}", seq[name], 200),
                                       max_iter=200)
            fields[name] = out.get("field")
        deltas = {}
        f0 = fields.get("V0_NONE")
        if not f0:
            self.state["difference_field"] = {}
            return True
        t_centered = [ta[i] - f0[i] for i in range(len(ta))]
        for name in ("V1_FULL", "V9_EVENT", "V10_RESIDUAL"):
            fn = fields.get(name)
            if not fn:
                deltas[name] = {"status": "FIELD_UNAVAILABLE"}
                continue
            d = [fn[i] - f0[i] for i in range(len(f0))]
            deltas[name] = M.delta_field_metrics(d, t_centered, 60, 30)
        self.record("difference_field", "deltas", deltas)
        self.save_artifact("difference_fields", "delta_fields.json", deltas)
        self.state["difference_field"] = deltas
        return True

    def phase_high_pass(self):
        self.log("=== V4 HIGH-PASS ANALYSIS ===")
        seq, _ = driver_registry(200)
        b = self.state.get("best", {})
        cr, ci = b.get("cr", 0), b.get("ci", 0)
        ta = self.kernel.target_field("TARGET_A", 60, 30)
        target_hp = M.dct_lowpass_field(ta, 60, 30, keep=3, highpass=True)
        hp = {}
        for name in ("V0_NONE", "V1_FULL", "V9_EVENT", "V10_RESIDUAL"):
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE",
                                       driver_file=self._tmp_driver(
                                           f"hp_{name}", seq[name], 200),
                                       max_iter=200)
            fld = out.get("field")
            if not fld:
                hp[name] = None
                continue
            fld_hp = M.dct_lowpass_field(fld, 60, 30, keep=3, highpass=True)
            full = self.kernel.score_fields(fld, ta, 60, 30)
            hp[name] = {
                "full_score": full.get("score", 0),
                "pearson_highpass": M._pearson(fld_hp, target_hp),
            }
        self.record("high_pass", "results", hp)
        self.save_artifact("difference_fields", "highpass.json", hp)
        self.state["high_pass"] = hp
        self.log(f"high-pass: V1_hp={hp.get('V1_FULL', {}).get('pearson_highpass', 'N/A')}")
        return True

    def phase_spectral_surrogates(self):
        self.log("=== V4 SPECTRAL SURROGATES (100) ===")
        b = self.state.get("best", {})
        cr, ci = b.get("cr", 0), b.get("ci", 0)
        ta = self.kernel.target_field("TARGET_A", 60, 30)
        surr_scores = {}
        seeds = self.proto["spectral_surrogate_seeds"]
        for idx, sd in enumerate(seeds):
            sur = M.dct_sign_surrogate(ta, 60, 30, sd)
            path = os.path.join(ART, "surrogates", f"surrogate_{sd}.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(" ".join(f"{v:.17g}" for v in sur) + "\n")
            out = self.kernel.evaluate(cr, ci, driver="V0_NONE",
                                       target_file=path, max_iter=200)
            surr_scores[str(sd)] = out.get("score", 0)
            if (idx + 1) % 20 == 0:
                self.log(f"  surrogates {idx+1}/100 done")
        vals = list(surr_scores.values())
        stats = {
            "N": len(vals),
            "mean": sum(vals) / len(vals) if vals else 0,
            "std": M.std_flat(vals) if vals else 0,
            "median": sorted(vals)[len(vals) // 2] if vals else 0,
            "p90": sorted(vals)[int(0.9 * len(vals))] if vals else 0,
            "p95": sorted(vals)[int(0.95 * len(vals))] if vals else 0,
            "max": max(vals) if vals else 0,
            "scores": surr_scores,
        }
        self.record("spectral_surrogates", "stats", stats)
        self.save_artifact("surrogates", "surrogate_stats.json", stats)
        self.state["spectral_surrogates"] = stats
        self.log(f"surrogates: mean={stats['mean']:.6f} max={stats['max']:.6f}")
        return True

    def phase_benchmark(self):
        self.log("=== V4 WORLD_PRIME BENCHMARK ===")
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
        result = {
            "summaries": {s: {"accuracy": v["accuracy"], "confusion": v["confusion"]}
                          for s, v in summaries.items()},
            "prime_detection": {"detected": len(detected), "total": len(prime),
                                "detected_seeds": detected},
            "interpretation": ("WORLD_PRIME held out; low detection rate is a "
                               "legitimate detector limitation result."),
        }
        self.record("benchmark", "audit", result)
        self.save_artifact("benchmark", "benchmark_audit.json", result)
        self.state["benchmark"] = result
        self.log(f"benchmark: prime={len(detected)}/{len(prime)}")
        return True

    def phase_reproducibility(self):
        self.log("=== V4 REPRODUCIBILITY ===")
        seq, _ = driver_registry(200)
        b = self.state.get("best", {})
        drv = self.proto["tracks"].get(b.get("track", "TRACK_A"), "V1_FULL")
        scores = []
        for i in range(self.proto["reproducibility_runs"]):
            scores.append(self.score_sequence_at(b["cr"], b["ci"], seq[drv])["score"])
        identical = len(set(round(x, 12) for x in scores)) == 1
        integrity = self.store.integrity()
        res = {"canonical_best": {"cr": b["cr"], "ci": b["ci"], "driver": drv},
               "scores": scores, "identical_within_tolerance": identical,
               "db_integrity": integrity}
        self.record("reproducibility", "canonical", res)
        self.save_artifact("best", "reproducibility.json", res)
        self.log(f"reproducibility: {scores} identical={identical}")
        self.state["reproducibility"] = res
        return True

    def phase_report(self):
        self.log("=== V4 REPORT ===")
        from report_v4 import write_report
        mismatches = write_report(self)
        self.state["report_mismatches"] = mismatches
        return not mismatches

    def final_status(self):
        """Classify V4 outcome (protocol §76-78). All 9 statuses."""
        b = self.state.get("best", {})
        ctrl = self.state.get("controls", {}) or {}
        best_track = b.get("track", "TRACK_A")
        track_ctrl = ctrl.get(best_track, {}) or {}
        contrasts = track_ctrl.get("contrasts", {}) or {}
        boundary = track_ctrl.get("boundary_distance", {}) or {}
        null = self.state.get("null", {}) or {}
        self_test = self.state.get("self_test", {}) or {}
        scores = track_ctrl.get("scores", {}) or {}

        # IMPLEMENTATION_ERROR
        if not self_test.get("kernel_ok"):
            return "IMPLEMENTATION_ERROR"

        # BOUNDARY_ARTIFACT
        if boundary.get("BOUNDARY_SUSPECT"):
            return "BOUNDARY_ARTIFACT"

        c_full = contrasts.get("C_full", 0)
        c_event = contrasts.get("C_event", 0)
        c_residual = contrasts.get("C_residual", 0)
        p_emp = null.get("empirical_search_null", 1.0)

        # Check temporal signal for robust classification
        temporal = self.state.get("temporal", {}) or {}
        temporal_signal = False
        for pt_data in temporal.get("points", {}).values():
            for drv_data in pt_data.get("drivers", {}).values():
                if isinstance(drv_data, dict) and drv_data.get("effect_size", 0) > 0.1:
                    temporal_signal = True

        # ROBUST_PRIME_SPECIFIC_SIGNAL (protocol §78)
        if (abs(c_full) > 0.01 and abs(c_event) > 0.005 and
                abs(c_residual) > 0.005 and p_emp < 0.1 and temporal_signal):
            return "ROBUST_PRIME_SPECIFIC_SIGNAL"

        # PRIME_CANDIDATE_SIGNAL
        if (abs(c_full) > 0.01 and abs(c_event) > 0.005 and
                abs(c_residual) > 0.005 and p_emp < 0.1):
            return "PRIME_CANDIDATE_SIGNAL"

        # DYNAMICAL_REGIME_ARTIFACT
        if scores.get("V1_FULL", 0) > 0.5 and abs(c_full) < 0.001:
            return "DYNAMICAL_REGIME_ARTIFACT"

        # GENERIC_RESONANCE
        if scores.get("V1_FULL", 0) > 0.5 and abs(c_full) < 0.01:
            return "GENERIC_RESONANCE"

        # METHODOLOGICAL_ARTIFACT
        if not self_test.get("s1_ok"):
            return "METHODOLOGICAL_ARTIFACT"

        return "NO_PRIME_SPECIFIC_SIGNAL"

    # ---- orchestration ---------------------------------------------------
    PHASES = ["init", "self_test", "protocol_lock", "interior_scout",
              "search", "controls", "null", "temporal", "validation",
              "difference_field", "high_pass", "spectral_surrogates",
              "benchmark", "reproducibility", "report"]

    def restore_state(self):
        all_r = self.store.all_results()
        for compound_key, entry in all_r.items():
            phase, key = compound_key.split(":", 1)
            if phase not in self.state:
                self.state[phase] = {}
            if isinstance(self.state.get(phase), dict):
                self.state[phase][key] = entry["value"]
        if "search" in self.state and "best" not in self.state:
            best_contrast = -999
            for track, info in self.state["search"].items():
                if isinstance(info, dict) and "best" in info:
                    b = info["best"]
                    if b.get("contrast", -999) > best_contrast:
                        best_contrast = b["contrast"]
                        self.state["best"] = {**b, "track": track}
        self.log(f"Restored state: {list(self.state.keys())}")

    def run(self, phases=None, resume_from=None):
        order = self.PHASES
        if resume_from:
            idx = order.index(resume_from)
            order = order[idx:]
        order = [p for p in order if (phases is None or p in phases)]
        # If init is not in the order, we need to bootstrap kernel/store/proto
        if "init" not in order:
            self._bootstrap_for_resume()
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
        self.log(f"=== V4 PIPELINE COMPLETE (status: {self.final_status()}) ===")
        return True

    def _bootstrap_for_resume(self):
        """Minimal init for resume: load protocol, open store, find kernel."""
        import json as _json
        # Load protocol
        proto_path = "protocol_v4.json"
        if os.path.exists(proto_path):
            with open(proto_path, "r", encoding="utf-8") as f:
                self.proto = _json.load(f)
        else:
            self.proto = P4.v4_spec()
        self.phash = P4.protocol_v4_hash(self.proto)
        self.shash = P4.source_v4_hash()
        exe = "kernel_v3.exe" if os.name == "nt" else "kernel_v3"
        if os.path.exists(exe):
            self.bhash = P4.binary_v4_hash(exe)
            self.kernel = V3Kernel(exe)
        else:
            self.log("ERROR: kernel not found for resume")
            return
        self.store = V4Store(".", self.phash, self.shash, self.bhash)
        self.run_id = f"V4_RESUME_{int(self.start_time)}"
        self.log(f"Resume bootstrap: protocol={self.phash[:16]}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Proof of Simulation V4 pipeline")
    ap.add_argument("--time-budget", type=int, default=14400)
    ap.add_argument("--null-runs", type=int, default=None)
    ap.add_argument("--phases", type=str, default=None)
    ap.add_argument("--resume-from", type=str, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    phases = args.phases.split(",") if args.phases else None
    p = V4Pipeline(time_budget=args.time_budget, quiet=args.quiet,
                   null_runs=args.null_runs)
    return p.run(phases=phases, resume_from=args.resume_from)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
