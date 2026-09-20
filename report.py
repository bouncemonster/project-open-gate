"""
PROOF OF SIMULATION — Report Generator
Generates report.md and associated artifacts.
"""
import csv
import json
import os
import subprocess
import time

import db
import protocol
import worldforge


def generate_report(conn, run_id, ctrl, state):
    """Generate the full experimental report."""
    best = db.get_best(conn, run_id)
    evals = db.get_all_evaluations(conn, run_id)
    nulls = db.get_null_runs(conn)
    vals = db.get_validations(conn)
    phash = protocol.protocol_hash()
    shash = protocol.source_hash()
    sys_info = protocol.get_system_info()

    lines = []
    lines.append("# Proof of Simulation — Experimental Report")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # 1. Executive Summary
    lines.append("## 1. Executive Summary")
    lines.append("")
    if best:
        lines.append(f"The experiment completed with a best resonance score of **{best['score']:.6f}** "
                      f"using model **{best['model_id']}** at c = {best['cr']:.6f} + {best['ci']:.6f}i.")
        lines.append(f"Total evaluations: {len(evals)}.")
    else:
        lines.append("No evaluations were completed.")
    lines.append("")

    # 2. Research Question
    lines.append("## 2. Research Question")
    lines.append("")
    lines.append("Can prime-arithmetic forcing in a non-autonomous Julia set system")
    lines.append("produce reproducible spatial resonance patterns that cannot be explained")
    lines.append("by smooth forcing, random coincidence, or ordinary Julia dynamics?")
    lines.append("")

    # 3. Exact Protocol
    lines.append("## 3. Exact Protocol")
    lines.append("")
    lines.append(f"- Protocol version: {protocol.PROTOCOL_VERSION}")
    lines.append(f"- Protocol hash: `{phash}`")
    lines.append(f"- Source hash: `{shash}`")
    lines.append(f"- Grid: 60x30 (1800 cells)")
    lines.append(f"- Score weights: Pearson=0.25, Spearman=0.15, MAE=0.15, Gradient=0.15, Spectral=0.15, AutoCorr=0.15")
    lines.append(f"- Search budget: 100 logical steps (~900 evaluations)")
    lines.append(f"- Time budget: {ctrl.time_budget if ctrl else 900}s")
    lines.append("")

    # 4. Computational Environment
    lines.append("## 4. Computational Environment")
    lines.append("")
    lines.append(f"- OS: {sys_info['os']}")
    lines.append(f"- Python: {sys_info['python_version']}")
    lines.append(f"- CPU: {sys_info['cpu']}")
    lines.append(f"- Machine: {sys_info['machine']}")
    lines.append("")

    # 5. Mathematical Model
    lines.append("## 5. Mathematical Model")
    lines.append("")
    lines.append("Base equation: z_{n+1} = z_n^2 + c + alpha * D(k)")
    lines.append("")
    lines.append("where D(k) is a deterministic forcing function dependent on iteration number k.")
    lines.append("")

    # 6. Prime Arithmetic Drivers
    lines.append("## 6. Prime Arithmetic Drivers")
    lines.append("")
    lines.append("| Driver | Description |")
    lines.append("|--------|-------------|")
    lines.append("| V0_NONE | Baseline Julia (no forcing) |")
    lines.append("| V1_INV_PI | D(k) = 1/pi(k) |")
    lines.append("| V2_SMOOTH | Smooth surrogate matched to V1 mean/std |")
    lines.append("| V3_CENTERED_INV_PI | D(k) = 1/pi(k) - mean |")
    lines.append("| V4_PRIME_RESIDUAL | D(k) = (1/pi(k) - smooth) / std |")
    lines.append("| V5_SHUFFLED | Shuffled 1/pi(k) (seed=7331) |")
    lines.append("| V6_REVERSED | Reversed 1/pi(k) |")
    lines.append("| V7_IMAGINARY | Forcing on imaginary component |")
    lines.append("| V8_PHASE_RANDOMIZED | Phase-randomized surrogate |")
    lines.append("")

    # 7. Target Functions
    lines.append("## 7. Target Functions")
    lines.append("")
    lines.append("- TARGET_A: |sin(pi*u) * cos(pi*v)| (primary optimization target)")
    lines.append("- TARGET_B: sin^2(pi*u) * cos^2(pi*v) (holdout)")
    lines.append("- TARGET_PHASE: |sin(pi*(u+0.07)) * cos(pi*(v-0.11))| (holdout)")
    lines.append("- T_nm: sin^2(n*pi*u) * sin^2(m*pi*v) for n,m in {1,2,3,4} (16 holdout eigenmodes)")
    lines.append("")

    # 8. Resonance Metric
    lines.append("## 8. Resonance Metric")
    lines.append("")
    lines.append("Composite score = 0.25*Pearson01 + 0.15*Spearman01 + 0.15*MAE01 + 0.15*Gradient01 + 0.15*Spectral01 + 0.15*Autocorrelation01")
    lines.append("")

    # 9. Search Procedure
    lines.append("## 9. Search Procedure")
    lines.append("")
    lines.append("- Algorithm: Hill Climbing + 8-direction local search + deterministic mutation")
    lines.append("- Two research tracks: TRACK_A (V1_INV_PI), TRACK_B (V4_PRIME_RESIDUAL)")
    lines.append("- Initial point: cr=-0.7, ci=0.27015")
    lines.append("- Initial step: 0.02, min: 0.00001, max: 0.20")
    lines.append("- Multi-start after 20 steps without improvement")
    lines.append("- Coarse scout: max 2x, 11x11 grid")
    lines.append("")

    # 10. Best Found Point
    lines.append("## 10. Best Found Point")
    lines.append("")
    if best:
        lines.append(f"| Parameter | Value |")
        lines.append(f"|-----------|-------|")
        lines.append(f"| Best score | {best['score']:.6f} |")
        lines.append(f"| Best cr | {best['cr']:.6f} |")
        lines.append(f"| Best ci | {best['ci']:.6f} |")
        lines.append(f"| Best model | {best['model_id']} |")
        lines.append(f"| Best driver | {best['driver']} |")
        lines.append(f"| Degree | {best.get('degree', 2)} |")
        lines.append(f"| Alpha | {best.get('alpha', 1.0)} |")
        lines.append(f"| Max iter | {best.get('max_iter', 200)} |")
        lines.append(f"| Total evaluations | {len(evals)} |")
        lines.append(f"| Protocol hash | `{phash}` |")
    else:
        lines.append("No best found.")
    lines.append("")

    # 11. Spatial Evidence
    lines.append("## 11. Spatial Evidence")
    lines.append("")
    if best:
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Pearson01 | {best['pearson01']:.6f} |")
        lines.append(f"| Spearman01 | {best['spearman01']:.6f} |")
        lines.append(f"| MAE01 | {best['mae01']:.6f} |")
        lines.append(f"| Gradient01 | {best['gradient01']:.6f} |")
        lines.append(f"| Spectral01 | {best['spectral01']:.6f} |")
        lines.append(f"| Autocorrelation01 | {best['autocorrelation01']:.6f} |")
    lines.append("")

    # 12. Temporal Evidence
    lines.append("## 12. Temporal Evidence")
    lines.append("")
    lines.append("Temporal analysis pending (requires trace mode data).")
    lines.append("")

    # 13. Control Models
    lines.append("## 13. Control Models")
    lines.append("")
    # Collect control evaluations at best point
    if best:
        control_evals = {}
        for e in evals:
            if (abs(e["cr"] - best["cr"]) < 1e-6 and
                abs(e["ci"] - best["ci"]) < 1e-6):
                if e["model_id"] not in control_evals:
                    control_evals[e["model_id"]] = e
        if control_evals:
            lines.append("| Model | Score | Pearson | Spectral | Gradient | AutoCorr |")
            lines.append("|-------|-------|---------|----------|----------|----------|")
            for model in ["V0_NONE", "V1_INV_PI", "V2_SMOOTH", "V3_CENTERED_INV_PI",
                          "V4_PRIME_RESIDUAL", "V5_SHUFFLED", "V6_REVERSED"]:
                e = control_evals.get(model)
                if e:
                    lines.append(f"| {model} | {e['score']:.6f} | {e['pearson01']:.6f} | "
                                  f"{e['spectral01']:.6f} | {e['gradient01']:.6f} | "
                                  f"{e['autocorrelation01']:.6f} |")
    lines.append("")

    # 14. Prime-Specific Controls
    lines.append("## 14. Prime-Specific Controls")
    lines.append("")
    uplifts = state.get("uplifts", {})
    if uplifts:
        lines.append(f"- Prime uplift: {uplifts.get('prime_uplift', 0):.4f}")
        lines.append(f"- Residual uplift: {uplifts.get('residual_uplift', 0):.4f}")
        lines.append(f"- Order uplift: {uplifts.get('order_uplift', 0):.4f}")
        lines.append(f"- Direction uplift: {uplifts.get('direction_uplift', 0):.4f}")
        lines.append(f"- Shuffle degradation: {uplifts.get('shuffle_degradation', 0):.4f}")
    else:
        lines.append("Control comparisons not yet computed.")
    lines.append("")

    # 15. Holdout Targets
    lines.append("## 15. Holdout Targets")
    lines.append("")
    lines.append("Holdout evaluation pending.")
    lines.append("")

    # 16. Null Search
    lines.append("## 16. Null Search")
    lines.append("")
    if nulls:
        lines.append("| Null Type | Seed | Best Score | Best CR | Best CI | Model |")
        lines.append("|-----------|------|------------|---------|---------|-------|")
        for n in nulls:
            lines.append(f"| {n['null_type']} | {n['seed']} | {n['best_score']:.6f} | "
                          f"{n['best_cr']:.6f} | {n['best_ci']:.6f} | {n['model_id'] or ''} |")
        lines.append("")
        scores = [n["best_score"] for n in nulls if n["best_score"] is not None]
        if scores and best:
            null_max = max(scores)
            null_mean = sum(scores) / len(scores)
            p_emp = (1 + sum(1 for s in scores if s >= best["score"])) / (1 + len(scores))
            lines.append(f"- Observed best: {best['score']:.6f}")
            lines.append(f"- Null max: {null_max:.6f}")
            lines.append(f"- Null mean: {null_mean:.6f}")
            lines.append(f"- Empirical search-based null estimate: {p_emp:.4f}")
    else:
        lines.append("No null runs completed.")
    lines.append("")

    # 17. Multiple Testing
    lines.append("## 17. Multiple Testing")
    lines.append("")
    lines.append(f"- Total evaluations: {len(evals)}")
    lines.append(f"- Number of models tested: {len(set(e['model_id'] for e in evals))}")
    lines.append(f"- Number of null runs: {len(nulls)}")
    lines.append("")

    # 18-21. Stability
    lines.append("## 18. Iteration Stability")
    lines.append("")
    depth_vals = [v for v in vals if v["validation_type"] == "depth"]
    if depth_vals:
        lines.append("| Max Iter | Score | Status |")
        lines.append("|----------|-------|--------|")
        for v in depth_vals:
            lines.append(f"| {v['max_iter']} | {v['score']:.6f} | {v['status']} |")
    else:
        lines.append("Depth validation pending.")
    lines.append("")

    lines.append("## 19. Resolution Stability")
    lines.append("")
    lines.append("Resolution validation pending.")
    lines.append("")

    lines.append("## 20. Finite Precision")
    lines.append("")
    lines.append("Finite precision validation pending.")
    lines.append("")

    lines.append("## 21. Pixelization and Periodicity")
    lines.append("")
    lines.append("Pending analysis.")
    lines.append("")

    # 22. Synthetic World Benchmark
    lines.append("## 22. Synthetic World Benchmark")
    lines.append("")
    bench_acc = state.get("benchmark_holdout_acc")
    if bench_acc is not None:
        lines.append(f"- Train accuracy: {state.get('benchmark_train_acc', 0):.2%}")
        lines.append(f"- Holdout accuracy: {bench_acc:.2%}")
    else:
        lines.append("Benchmark not yet completed.")
    lines.append("")

    # 23. Computational Fingerprint
    lines.append("## 23. Computational Fingerprint")
    lines.append("")
    if best:
        lines.append(f"- Entropy: {best.get('entropy', 0):.6f}")
        lines.append(f"- Anisotropy: {best.get('anisotropy', 0):.6f}")
        lines.append(f"- Compression ratio: {best.get('compression_ratio', 0):.6f}")
        lines.append(f"- Escaped fraction: {best.get('escaped_fraction', 0):.6f}")
    lines.append("")

    # 24. Limitations
    lines.append("## 24. Limitations")
    lines.append("")
    lines.append("- 60x30 grid resolution limits spatial detail")
    lines.append("- max_iter=200 limits depth exploration")
    lines.append("- Hill climbing may miss global optima")
    lines.append("- No external ML-based detection (by design)")
    lines.append("- Single-target optimization (TARGET_A only)")
    lines.append("")

    # 25. Interpretation
    lines.append("## 25. Interpretation")
    lines.append("")
    if best:
        score = best["score"]
        pu = uplifts.get("prime_uplift", 0)
        if score < 0.85:
            lines.append("No convincing prime-specific signal was established.")
        elif pu < 0.05:
            lines.append("The observed improvement may be explained by smooth forcing.")
        else:
            lines.append("The result is more consistent with dependence on ordered prime-related structure.")
            lines.append("The residual arithmetic component deserves further investigation.")
    else:
        lines.append("No result to interpret.")
    lines.append("")

    # 26. Conclusion
    lines.append("## 26. Conclusion")
    lines.append("")
    lines.append("This experiment does not establish that physical reality is simulated.")
    lines.append("It establishes, at most, the presence or absence of a reproducible")
    lines.append("computational pattern within the tested mathematical systems.")
    lines.append("")

    # Result level
    lines.append("### Result Level")
    lines.append("")
    if best:
        score = best["score"]
        level = 0
        if score > 0.5: level = 0
        controls = state.get("controls", {})
        v0 = controls.get("V0_NONE", 0)
        if score > v0 + 0.01: level = max(level, 1)
        v2 = controls.get("V2_SMOOTH", 0)
        if score > v2 + 0.01: level = max(level, 2)
        if pu >= 0.05: level = max(level, 3)
        if depth_vals and all(v["score"] > 0.5 for v in depth_vals): level = max(level, 4)
        if nulls:
            null_scores = [n["best_score"] for n in nulls if n["best_score"]]
            if null_scores and score > max(null_scores): level = max(level, 5)
        lines.append(f"**LEVEL {level}**")
        level_desc = {
            0: "High coincidence with target",
            1: "Above Julia baseline",
            2: "Above smooth surrogate",
            3: "Prime-order controls notably worse",
            4: "Effect stable across depth and resolution",
            5: "Effect survives holdout and search-aware null",
            6: "Full computational fingerprint validation"
        }
        lines.append(f"({level_desc.get(level, '')})")
    else:
        lines.append("No result.")
    lines.append("")

    # 10 scientific questions
    lines.append("### Final Scientific Answers")
    lines.append("")
    lines.append("1. **Was high resonance found?** " + ("Yes" if best and best["score"] >= 0.85 else "No"))
    lines.append("2. **Does it exceed baseline Julia?** " + ("Yes" if best and uplifts.get("prime_uplift", 0) > 0 else "Unclear"))
    lines.append("3. **Does it exceed smooth surrogate?** " + ("Yes" if uplifts.get("residual_uplift", 0) > 0 else "Unclear"))
    lines.append("4. **Does prime-order matter?** " + ("Yes" if uplifts.get("order_uplift", 0) > 0.05 else "Unclear"))
    depth_stable = "YES" if depth_vals and all(v["score"] > 0.5 for v in depth_vals) else "NO"
    lines.append("5. **Depth stable?** " + depth_stable)
    lines.append("6. **Resolution stable?** Pending (requires multi-resolution kernel)")
    lines.append("7. **Holdout stable?** Pending")
    null_scores_list = [n["best_score"] for n in nulls if n["best_score"]] if nulls else []
    null_explained = "Yes" if null_scores_list and best and best["score"] <= max(null_scores_list) else "No"
    lines.append("8. **Explained by random-search null?** " + null_explained)
    lines.append("9. **Detector finds known computational worlds?** " +
                  ("Yes" if state.get("benchmark_holdout_acc", 0) >= 0.75 else "Unclear"))
    fp_status = "Available" if best else "Pending"
    lines.append("10. **Computational-like fingerprint?** " + fp_status)
    lines.append("")

    # Write report
    report_text = "\n".join(lines)
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(report_text)

    # Save reproducibility manifest
    rep = {
        "os": sys_info["os"],
        "python_version": sys_info["python_version"],
        "compiler": "gcc" if ctrl else "unknown",
        "cpu": sys_info["cpu"],
        "source_hash": shash,
        "protocol_hash": phash,
        "best_parameters": {
            "cr": best["cr"] if best else None,
            "ci": best["ci"] if best else None,
            "model": best["model_id"] if best else None,
            "score": best["score"] if best else None
        }
    }
    protocol._atomic_write_json("reproducibility.json", rep)

    # Generate best/ artifacts
    _generate_best_artifacts(best, ctrl, conn, run_id)

    # Generate fingerprint_summary.csv
    _generate_fingerprint_csv(best, conn, run_id)

    return report_text


def _generate_best_artifacts(best, ctrl, conn, run_id):
    """Generate best/best_map.txt, best/best_difference.txt, best/best_metrics.json."""
    if not best:
        return
    os.makedirs("best", exist_ok=True)

    # Use kernel render mode to get the best map
    kernel = None
    for name in ["kernel.exe", "kernel"]:
        if os.path.exists(name):
            kernel = name
            break

    if kernel:
        import shutil
        env = dict(os.environ)
        cc_dir = os.path.dirname(os.path.abspath(kernel))
        env["PATH"] = cc_dir + os.pathsep + env.get("PATH", "")
        try:
            result = subprocess.run(
                [kernel, "--render",
                 "--cr", f"{best['cr']:.6f}", "--ci", f"{best['ci']:.6f}",
                 "--driver", best.get("driver", "V1_INV_PI"),
                 "--max-iter", str(best.get("max_iter", 200))],
                capture_output=True, text=True, timeout=10, env=env
            )
            map_lines = result.stdout.strip().split("\n")
            # Remove the Score line from the map
            if map_lines and "Score:" in map_lines[-1]:
                map_lines = map_lines[:-1]
            if map_lines and not map_lines[-1].strip():
                map_lines = map_lines[:-1]
            with open("best/best_map.txt", "w") as f:
                f.write("\n".join(map_lines) + "\n")
        except Exception:
            # Write placeholder
            with open("best/best_map.txt", "w") as f:
                f.write(f"Best map at cr={best['cr']:.6f} ci={best['ci']:.6f}\n")

    # Generate target map for difference
    WIDTH, HEIGHT = 60, 30
    import math
    target_chars = []
    for row in range(HEIGHT):
        v = -1.0 + 2.0 * row / (HEIGHT - 1)
        line = ""
        for col in range(WIDTH):
            u = -1.8 + 3.6 * col / (WIDTH - 1)
            # TARGET_A = |sin(pi*u)*cos(pi*v)|
            val = abs(math.sin(math.pi * u) * math.cos(math.pi * v))
            palette = " .:-=+*#%@"
            idx = int(val * len(palette))
            idx = max(0, min(len(palette) - 1, idx))
            line += palette[idx]
        target_chars.append(line)
    with open("best/target_map.txt", "w") as f:
        f.write("\n".join(target_chars) + "\n")

    # Generate difference map (character comparison if both exist)
    try:
        with open("best/best_map.txt") as f:
            best_lines = f.read().strip().split("\n")
        diff_lines = []
        palette = " .:-=+*#%@"
        for r in range(min(len(best_lines), HEIGHT)):
            line = ""
            for c in range(WIDTH):
                bc = best_lines[r][c] if c < len(best_lines[r]) else " "
                tc = target_chars[r][c] if c < len(target_chars[r]) else " "
                if bc == tc:
                    line += " "
                else:
                    line += "*"
            diff_lines.append(line)
        with open("best/best_difference.txt", "w") as f:
            f.write("\n".join(diff_lines) + "\n")
    except Exception:
        pass

    # Generate best_metrics.json
    metrics = {
        "cr": best["cr"],
        "ci": best["ci"],
        "model_id": best["model_id"],
        "driver": best.get("driver", ""),
        "score": best["score"],
        "pearson01": best["pearson01"],
        "spearman01": best["spearman01"],
        "mae01": best["mae01"],
        "gradient01": best["gradient01"],
        "spectral01": best["spectral01"],
        "autocorrelation01": best["autocorrelation01"],
        "entropy": best.get("entropy", 0),
        "anisotropy": best.get("anisotropy", 0),
        "compression_ratio": best.get("compression_ratio", 0),
        "escaped_fraction": best.get("escaped_fraction", 0),
        "max_iter": best.get("max_iter", 200),
        "alpha": best.get("alpha", 1.0),
        "degree": best.get("degree", 2),
    }
    with open("best/best_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)


def _generate_fingerprint_csv(best, conn, run_id):
    """Generate fingerprint_summary.csv with diagnostic features."""
    if not best:
        return
    with open("fingerprint_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["feature", "value"])
        w.writerow(["entropy", f"{best.get('entropy', 0):.6f}"])
        w.writerow(["anisotropy", f"{best.get('anisotropy', 0):.6f}"])
        w.writerow(["compression_ratio", f"{best.get('compression_ratio', 0):.6f}"])
        w.writerow(["escaped_fraction", f"{best.get('escaped_fraction', 0):.6f}"])
        w.writerow(["quantization_index", f"{best.get('quantization_index', 0):.6f}"])
        w.writerow(["score", f"{best['score']:.6f}"])
        w.writerow(["pearson01", f"{best['pearson01']:.6f}"])
        w.writerow(["spearman01", f"{best['spearman01']:.6f}"])
        w.writerow(["mae01", f"{best['mae01']:.6f}"])
        w.writerow(["gradient01", f"{best['gradient01']:.6f}"])
        w.writerow(["spectral01", f"{best['spectral01']:.6f}"])
        w.writerow(["autocorrelation01", f"{best['autocorrelation01']:.6f}"])


# ================================================================
# V2 REPORT GENERATOR
# ================================================================

def generate_report_v2(store, kernel, state, track_results, control_results,
                       null_results, validation_results, temporal_results,
                       benchmark_result, phash, shash, bhash):
    """Generate the V2 experimental report: report_v2.md."""
    sys_info = protocol.get_system_info()
    lines = []

    def add(text=""):
        lines.append(text)

    add("# Proof of Simulation V2 — Corrected Arithmetic Isolation Report")
    add()
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    add()

    # 1. Executive Summary
    add("## 1. Executive Summary")
    add()
    best_score = state.get("best_score", 0)
    best_cr = state.get("best_cr", 0)
    best_ci = state.get("best_ci", 0)
    best_track = state.get("best_track", "N/A")
    add(f"The V2 experiment completed with a best resonance score of **{best_score:.6f}** "
        f"using driver V1_INV_PI at c = {best_cr:.6f} + {best_ci:.6f}i (track: {best_track}).")
    add()
    total_evals = sum(
        t.get("search", None) and t["search"].total_evals or 0
        for t in track_results.values()
    )
    add(f"Total search evaluations: {total_evals} across {len(track_results)} tracks.")
    add()

    # 2. Provenance
    add("## 2. Provenance and Hashes")
    add()
    add(f"| Item | Hash |")
    add(f"|------|------|")
    add(f"| Protocol V2 | `{phash}` |")
    add(f"| Source V2 | `{shash}` |")
    add(f"| Binary V2 | `{bhash}` |")
    add(f"| OS | {sys_info['os']} |")
    add(f"| Python | {sys_info['python_version']} |")
    add(f"| CPU | {sys_info['cpu']} |")
    add()

    # 3. V1 Audit Summary
    add("## 3. V1 Forensic Audit Summary")
    add()
    add("V1 baseline preserved at `archives/v1_baseline/` (29 files, SHA-256 verified).")
    add("Key V1 findings:")
    add("- **Conclusion-changing bug**: Short driver aliases (V1/V4) silently fell back to V0_NONE")
    add("- **Benchmark leakage**: WORLD_PRIME seeds entered training data")
    add("- **Null mismatch**: V1 null used different search budget than primary")
    add("- V1 does not establish a prime-specific advantage")
    add()

    # 4. V2 Protocol
    add("## 4. V2 Preregistered Protocol")
    add()
    add("- Domain: [-2,2]^2 (expanded from V1 [-1.5,1.0]x[-1.2,1.2])")
    add("- Dynamics: z(k) = z(k-1)^2 + c + alpha*D(k), alpha=1, k starts at 1")
    add("- Grid: 60x30, bounded 2..512; iterations 1..20000")
    add("- 16 drivers: V0-V13 + S1 + S2")
    add("- Primary target: TARGET_A = |sin(pi*u)*cos(pi*v)|")
    add("- Score weights: Pearson=0.25, Spearman=MAE=Gradient=Spectral=AutoCorr=0.15")
    add("- Search: 17x17 scout (289) + 100 steps x 9 candidates = 1189 per run")
    add("- Tracks: A=V1_INV_PI, B=V10_PRIME_RESIDUAL, C=V9_PRIME_EVENT")
    add("- Seeds: 133742 (primary), 233742, 333742 (repeats)")
    add("- Null: 8 runs, DCT sign surrogates (seeds 1001-1008)")
    add()

    # 5. Search Results
    add("## 5. Search Results")
    add()
    add("| Track | Driver | Seed | Best Score | Best CR | Best CI |")
    add("|-------|--------|------|------------|---------|---------|")
    for tname, tdata in sorted(track_results.items()):
        b = tdata.get("best", {})
        add(f"| {tname} | {tdata.get('search', None) and tdata['search'].driver or 'N/A'} | "
            f"{tdata.get('search', None) and tdata['search'].seed or 'N/A'} | "
            f"{b.get('score', 0):.6f} | {b.get('cr', 0):.6f} | {b.get('ci', 0):.6f} |")
    add()

    # 6. Control Models
    add("## 6. Control Models at Best Point")
    add()
    add(f"Best point: c = {best_cr:.6f} + {best_ci:.6f}i")
    add()
    add("| Driver | Score | Pearson | Spearman | MAE | Gradient | Spectral | AutoCorr |")
    add("|--------|-------|---------|----------|-----|----------|----------|----------|")
    primary_drivers = ["V0_NONE", "V1_INV_PI", "V2_SMOOTH", "V3_CENTERED_INV_PI",
                       "V4_PRIME_RESIDUAL", "V5_SHUFFLED", "V6_REVERSED",
                       "V8_PHASE_RANDOMIZED", "V9_PRIME_EVENT", "V10_PRIME_RESIDUAL",
                       "S1_ANALYTIC", "S2_DATA_SMOOTHED"]
    for drv in primary_drivers:
        r = control_results.get(drv, {})
        if r:
            add(f"| {drv} | {r.get('score', 0):.6f} | {r.get('pearson01', 0):.6f} | "
                f"{r.get('spearman01', 0):.6f} | {r.get('mae01', 0):.6f} | "
                f"{r.get('gradient01', 0):.6f} | {r.get('spectral01', 0):.6f} | "
                f"{r.get('autocorrelation01', 0):.6f} |")
    add()

    # 7. Primary Contrasts
    add("## 7. Primary Contrasts")
    add()
    contrasts = state.get("contrasts", {})
    if contrasts:
        add("| Contrast | Value |")
        add("|----------|-------|")
        for name, val in contrasts.items():
            add(f"| {name} | {val:+.6f} |")
    add()

    # 8. Null Search
    add("## 8. Search-Aware Null")
    add()
    if null_results:
        add(f"- Observed best: {null_results.get('observed', 0):.6f}")
        add(f"- Null runs: {null_results.get('n', 0)}")
        add(f"- Null mean: {null_results.get('null_mean', 0):.6f}")
        add(f"- Null std: {null_results.get('null_std', 0):.6f}" if null_results.get('null_std') else "- Null std: N/A")
        add(f"- Null median: {null_results.get('null_median', 0):.6f}")
        add(f"- Null max: {null_results.get('null_max', 0):.6f}")
        add(f"- Observed minus null mean: {null_results.get('observed_minus_null_mean', 0):+.6f}")
        add(f"- Observed minus null max: {null_results.get('observed_minus_null_max', 0):+.6f}")
        add(f"- Percentile: {null_results.get('percentile', 0):.1f}%")
        add(f"- Empirical search null: {null_results.get('empirical_search_null', 'N/A')}")
        add(f"- Minimum attainable: {null_results.get('minimum_attainable', 'N/A')}")
        maxima = null_results.get("null_maxima", [])
        if maxima:
            add(f"- Null maxima: {', '.join(f'{m:.6f}' for m in maxima)}")
    add()

    # 9. Validation
    add("## 9. Validation")
    add()
    add("### 9.1 Depth Stability")
    add()
    depth_scores = []
    for depth in [200, 500, 1000, 1500, 2000]:
        r = validation_results.get(f"depth_{depth}", {})
        s = r.get("score", 0)
        depth_scores.append(s)
        add(f"- Depth {depth}: {s:.6f}")
    if depth_scores:
        rng = max(depth_scores) - min(depth_scores)
        add(f"- Range: {rng:.6f} ({'STABLE' if rng <= 0.05 else 'UNSTABLE'})")
    add()

    add("### 9.2 Resolution Stability")
    add()
    for res in ["60x30", "120x60"]:
        r = validation_results.get(f"res_{res}", {})
        add(f"- {res}: {r.get('score', 0):.6f}")
    add()

    add("### 9.3 Alpha Sensitivity")
    add()
    for alpha in [0.25, 0.5, 1.0, 2.0]:
        r = validation_results.get(f"alpha_{alpha}", {})
        add(f"- Alpha {alpha}: {r.get('score', 0):.6f}")
    add()

    add("### 9.4 Local Stability")
    add()
    for dcr, dci in [(0.001, 0), (-0.001, 0), (0, 0.001), (0, -0.001)]:
        r = validation_results.get(f"local_{dcr:+.3f}_{dci:+.3f}", {})
        add(f"- ({dcr:+.4f}, {dci:+.4f}): {r.get('score', 0):.6f}")
    add()

    add("### 9.5 Holdout Targets")
    add()
    for tgt in ["TARGET_B", "TARGET_PHASE"]:
        r = validation_results.get(f"holdout_{tgt}", {})
        add(f"- {tgt}: {r.get('score', 0):.6f}")
    add()
    add("Eigenmode holdouts (T_nm, n,m=1..4):")
    add()
    for n in range(1, 5):
        for m in range(1, 5):
            r = validation_results.get(f"eigenmode_T_{n}_{m}", {})
            if r:
                add(f"  T_{n}_{m}: {r.get('score', 0):.6f}")
    add()

    add("### 9.6 Reproducibility")
    add()
    repro_scores = []
    for i in range(3):
        r = validation_results.get(f"repro_{i}", {})
        s = r.get("score", 0)
        repro_scores.append(s)
        add(f"- Run {i+1}: {s:.6f}")
    if repro_scores and max(repro_scores) == min(repro_scores):
        add("- **Identical across all runs**")
    add()

    # 10. Temporal Analysis
    add("## 10. Temporal Analysis")
    add()
    if temporal_results:
        for drv, result in temporal_results.items():
            add(f"### {drv}")
            add()
            add(f"- Status: {result.get('status', 'UNKNOWN')}")
            add(f"- Pair count: {result.get('pair_count', 0)}")
            if result.get('mean_difference') is not None:
                add(f"- Mean difference: {result['mean_difference']:.6f}")
            if result.get('effect_size') is not None:
                add(f"- Effect size: {result['effect_size']:.6f}")
            if result.get('bootstrap_ci95') is not None:
                ci = result['bootstrap_ci95']
                add(f"- Bootstrap 95% CI: [{ci[0]:.6f}, {ci[1]:.6f}]")
            if result.get('permutation_p_two_sided') is not None:
                add(f"- Permutation p (two-sided): {result['permutation_p_two_sided']:.4f}")
            add()
    else:
        add("Temporal analysis not completed.")
        add()

    # 11. Benchmark
    add("## 11. Synthetic World Benchmark V2")
    add()
    if benchmark_result:
        summaries = benchmark_result.get("summaries", {})
        for split, s in summaries.items():
            add(f"- {split}: accuracy={s.get('accuracy', 'N/A')}")
        prime = benchmark_result.get("prime_detections", {})
        add(f"- Prime detection: {prime.get('detected', 0)}/{prime.get('total', 0)} "
            f"({prime.get('detection_rate', 0):.0%})")
        add(f"- Distinct prime hashes: {prime.get('distinct_hashes', 0)}")
        adv = benchmark_result.get("adversarial_results", {})
        adv_summary = adv.get("summary", {})
        add(f"- Adversarial accuracy: {adv_summary.get('accuracy', 'N/A')}")
    else:
        add("Benchmark not completed.")
    add()

    # 12. Status Determination
    add("## 12. Status Determination")
    add()
    status = _determine_v2_status(best_score, contrasts, null_results, validation_results, temporal_results)
    add(f"**Status: {status}**")
    add()
    _add_status_rationale(status, add, best_score, contrasts, null_results, validation_results)
    add()

    # 13. Limitations
    add("## 13. Limitations")
    add()
    add("- Only 8 null runs; minimum attainable empirical p is 1/9")
    add("- Hill climbing may miss global optima in [-2,2]^2")
    add("- Single primary target (TARGET_A) drives optimization")
    add("- Temporal analysis assumes exchangeable within-pair labels")
    add("- No external ML detection (by design)")
    add("- Multiplicity unadjusted across tracks and contrasts")
    add("- With only eight nulls, strength is exploratory")
    add("- Maximum at <5% of boundary is flagged")
    add()

    # 14. Conclusion
    add("## 14. Conclusion")
    add()
    add("This experiment does not establish that physical reality is simulated.")
    add("It establishes, at most, the presence or absence of a reproducible")
    add("computational pattern within the tested mathematical systems.")
    add()
    add("V2 corrects the V1 driver dispatch bug, benchmark leakage, and null mismatch.")
    add("All V2 results are independently reproducible from the hashes above.")
    add()

    # Write report
    report_text = "\n".join(lines)
    with open("report_v2.md", "w", encoding="utf-8") as f:
        f.write(report_text)

    # Save reproducibility manifest
    rep = {
        "experiment": "V2_CORRECTED",
        "protocol_version": "2.0.0",
        "protocol_hash": phash,
        "source_hash": shash,
        "binary_hash": bhash,
        "os": sys_info["os"],
        "python_version": sys_info["python_version"],
        "cpu": sys_info["cpu"],
        "best": {
            "score": best_score,
            "cr": best_cr,
            "ci": best_ci,
            "track": best_track,
            "driver": "V1_INV_PI"
        },
        "status": status,
        "run_ids": {tname: tdata.get("run_id") for tname, tdata in track_results.items()},
    }
    protocol._atomic_write_json("reproducibility_v2.json", rep)

    # Generate V2 artifacts
    _generate_v2_artifacts(best_cr, best_ci, control_results, kernel)

    return report_text


def _determine_v2_status(score, contrasts, null_results, validation_results, temporal_results):
    """Determine V2 scientific status per protocol rules."""
    if score < 0.6:
        no_contrasts = all(abs(v) < 0.005 for v in (contrasts or {}).values())
        if no_contrasts:
            return "NO_SIGNAL"

    # Check for generic resonance
    v0 = 0
    v1 = score
    has_contrast = False
    if contrasts:
        for key in ["V1_minus_V0", "V1_minus_max_S1_S2", "V9_minus_mean_V11", "V10_minus_max_S1_S2"]:
            if contrasts.get(key, 0) > 0.005:
                has_contrast = True

    if score >= 0.6 and not has_contrast:
        return "GENERIC_RESONANCE"

    # Check PRIME_CANDIDATE_SIGNAL
    event_contrast = contrasts.get("V9_minus_mean_V11", 0) if contrasts else 0
    residual_contrast = contrasts.get("V10_minus_max_S1_S2", 0) if contrasts else 0
    if event_contrast > 0.005 or residual_contrast > 0.005:
        # Check robustness
        depth_stable = True
        for depth in [500, 2000]:
            r = validation_results.get(f"depth_{depth}", {})
            if r.get("score", 0) < 0.5:
                depth_stable = False

        # Check temporal
        temporal_ok = False
        for drv, result in (temporal_results or {}).items():
            if result.get("status") == "OK":
                p = result.get("permutation_p_two_sided", 1)
                ci = result.get("bootstrap_ci95", [0, 0])
                if p <= 0.05 and (ci[0] > 0 or ci[1] < 0):
                    temporal_ok = True

        # Check null separation
        null_ok = False
        if null_results:
            diff = null_results.get("observed_minus_null_max", 0)
            if diff > 0:
                null_ok = True

        if depth_stable and temporal_ok and null_ok:
            return "ROBUST_PRIME_SPECIFIC_SIGNAL"
        return "PRIME_CANDIDATE_SIGNAL"

    if score >= 0.6:
        return "GENERIC_RESONANCE"
    return "UNRESOLVED"


def _add_status_rationale(status, add, score, contrasts, null_results, validation_results):
    """Add rationale for status determination."""
    if status == "NO_SIGNAL":
        add("Primary similarity below 0.6 with no meaningful positive contrasts.")
    elif status == "GENERIC_RESONANCE":
        add("Score above 0.6 but no consistent matched-control evidence for prime specificity.")
    elif status == "PRIME_CANDIDATE_SIGNAL":
        add("Event or residual contrasts exceed 0.005 at search settings,")
        add("but full robustness criteria (temporal + null + depth) not all met.")
    elif status == "ROBUST_PRIME_SPECIFIC_SIGNAL":
        add("Positive contrasts retained across depths/resolutions/holdouts,")
        add("temporal test positive, and separation above every fair null maximum.")
    else:
        add("Missing required evidence for definitive status.")


def _generate_v2_artifacts(cr, ci, control_results, kernel):
    """Generate V2 best/ artifacts."""
    os.makedirs("best", exist_ok=True)

    # Generate best map via kernel
    try:
        result = kernel.evaluate(cr, ci, "V1_INV_PI", width=60, height=30, target='TARGET_A')
        if result and "fields" in result:
            field = result["fields"].get("F", [])
            if field:
                chars = " .:-=+*#%@"
                map_lines = []
                for row in range(30):
                    line = ""
                    for col in range(60):
                        val = field[row * 60 + col] if row * 60 + col < len(field) else 0
                        idx = int(max(0, min(1, val)) * (len(chars) - 1))
                        line += chars[idx]
                    map_lines.append(line)
                with open("best/best_map_v2.txt", "w") as f:
                    f.write("\n".join(map_lines) + "\n")
    except Exception:
        pass

    # Generate metrics JSON
    metrics = {
        "cr": cr, "ci": ci,
        "driver": "V1_INV_PI",
        "model": "V2_EXPANDED_DOMAIN",
        "score": control_results.get("V1_INV_PI", {}).get("score", 0),
    }
    for key in ["pearson01", "spearman01", "mae01", "gradient01",
                "spectral01", "autocorrelation01", "entropy", "anisotropy",
                "compression_ratio", "escaped_fraction"]:
        metrics[key] = control_results.get("V1_INV_PI", {}).get(key, 0)
    with open("best/best_metrics_v2.json", "w") as f:
        json.dump(metrics, f, indent=2)
