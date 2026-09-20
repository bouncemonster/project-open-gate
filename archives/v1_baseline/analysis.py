"""
PROOF OF SIMULATION — Analysis Module
Diagnostic metrics, summary queries, and data analysis.
"""
import json
import sys
import os
import math

import db


def summary(conn, run_id=None):
    """Print max 30-line summary: best, controls, uplifts, null, validation, next action."""
    best = db.get_best(conn, run_id)
    if not best:
        print("No evaluations yet.")
        return

    lines = []
    lines.append(f"Best Score:  {best['score']:.6f}")
    lines.append(f"Best C:      {best['cr']:.6f} + {best['ci']:.6f}i")
    lines.append(f"Best Model:  {best['model_id']}")
    lines.append(f"Best Driver: {best['driver']}")
    lines.append(f"Total Evals: {db.count_evaluations(conn, run_id)}")
    lines.append("")

    # Controls: get evaluations at best cr/ci with different models
    evals = db.get_all_evaluations(conn, run_id)
    control_scores = {}
    for e in evals:
        if (abs(e["cr"] - best["cr"]) < 1e-6 and
            abs(e["ci"] - best["ci"]) < 1e-6):
            control_scores[e["model_id"]] = e["score"]

    if control_scores:
        lines.append("Controls at best point:")
        for model, score in sorted(control_scores.items()):
            lines.append(f"  {model}: {score:.6f}")

    # Uplifts
    v0 = control_scores.get("V0_NONE", 0)
    v1 = control_scores.get("V1_INV_PI", best["score"])
    v2 = control_scores.get("V2_SMOOTH", 0)
    v5 = control_scores.get("V5_SHUFFLED", 0)
    if v0 or v2:
        lines.append(f"Prime Uplift:    {v1 - max(v0, v2):.4f}")
    if v5:
        lines.append(f"Order Uplift:    {v1 - v5:.4f}")
        lines.append(f"Shuffle Degrad:  {v1 - v5:.4f}")
    lines.append("")

    # Null summary
    nulls = db.get_null_runs(conn)
    if nulls:
        null_scores = [n["best_score"] for n in nulls if n["best_score"] is not None]
        if null_scores:
            null_max = max(null_scores)
            null_mean = sum(null_scores) / len(null_scores)
            lines.append(f"Null Runs: {len(null_scores)}")
            lines.append(f"Null Max:  {null_max:.6f}")
            lines.append(f"Null Mean: {null_mean:.6f}")
            p_emp = (1 + sum(1 for s in null_scores if s >= best["score"])) / (1 + len(null_scores))
            lines.append(f"Empirical p: {p_emp:.4f}")
    lines.append("")

    # Validation summary
    vals = db.get_validations(conn)
    if vals:
        lines.append(f"Validations: {len(vals)}")
        for v in vals[-5:]:
            lines.append(f"  {v['validation_type']}: score={v['score']:.6f} ({v['status']})")

    # Trim to 30 lines
    for line in lines[:30]:
        print(line)


def show_best(conn, run_id=None):
    """Show detailed best result."""
    best = db.get_best(conn, run_id)
    if not best:
        print("No evaluations yet.")
        return
    print(json.dumps(best, indent=2, default=str))


def show_controls(conn, run_id=None):
    """Show control model results."""
    best = db.get_best(conn, run_id)
    if not best:
        print("No evaluations yet.")
        return

    evals = db.get_all_evaluations(conn, run_id)
    print(f"{'Model':<30} {'Score':>8} {'Pearson':>8} {'Spectral':>8} {'Gradient':>8} {'AutoCor':>8}")
    print("-" * 80)
    seen = set()
    for e in evals:
        if (abs(e["cr"] - best["cr"]) < 1e-6 and
            abs(e["ci"] - best["ci"]) < 1e-6 and
            e["model_id"] not in seen):
            seen.add(e["model_id"])
            print(f"{e['model_id']:<30} {e['score']:>8.6f} {e['pearson01']:>8.6f} "
                  f"{e['spectral01']:>8.6f} {e['gradient01']:>8.6f} {e['autocorrelation01']:>8.6f}")


def show_null(conn):
    """Show null run results."""
    nulls = db.get_null_runs(conn)
    if not nulls:
        print("No null runs yet.")
        return
    print(f"{'Type':<30} {'Seed':>6} {'Best Score':>10} {'Best CR':>10} {'Best CI':>10} {'Model':<20}")
    print("-" * 90)
    for n in nulls:
        print(f"{n['null_type']:<30} {n['seed']:>6} {n['best_score']:>10.6f} "
              f"{n['best_cr']:>10.6f} {n['best_ci']:>10.6f} {n['model_id'] or '':<20}")

    scores = [n["best_score"] for n in nulls if n["best_score"] is not None]
    if scores:
        print(f"\nNull Max:  {max(scores):.6f}")
        print(f"Null Mean: {sum(scores)/len(scores):.6f}")
        if len(scores) > 1:
            var = sum((s - sum(scores)/len(scores))**2 for s in scores) / (len(scores) - 1)
            print(f"Null Std:  {math.sqrt(var):.6f}")


def show_validations(conn):
    """Show validation results."""
    vals = db.get_validations(conn)
    if not vals:
        print("No validations yet.")
        return
    print(f"{'Type':<25} {'Target':<15} {'Resolution':<10} {'MaxIter':>8} {'Score':>8} {'Status':<10}")
    print("-" * 80)
    for v in vals:
        print(f"{v['validation_type']:<25} {v['target_id'] or '':<15} "
              f"{v['resolution'] or '':<10} {v['max_iter'] or 0:>8} "
              f"{v['score']:>8.6f} {v['status']:<10}")


def show_benchmarks(conn):
    """Show benchmark results."""
    benchmarks = db.get_benchmarks(conn)
    if not benchmarks:
        print("No benchmarks yet.")
        return
    worlds = {}
    for b in benchmarks:
        wt = b["world_type"]
        if wt not in worlds:
            worlds[wt] = {"train": [], "holdout": []}
        worlds[wt][b["split"]].append(b)

    print(f"{'World':<35} {'Train':>6} {'Holdout':>8} {'Label':<15}")
    print("-" * 70)
    for wt in sorted(worlds.keys()):
        n_train = len(worlds[wt]["train"])
        n_holdout = len(worlds[wt]["holdout"])
        label = ""
        if n_train > 0:
            try:
                label = json.loads(worlds[wt]["train"][0]["feature_json"]).get("label", "")
            except Exception:
                pass
        print(f"{wt:<35} {n_train:>6} {n_holdout:>8} {label:<15}")


def export_csv(conn, table, path):
    """Export a table to CSV."""
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return
    cols = rows[0].keys()
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for row in rows:
            vals = []
            for c in cols:
                v = row[c]
                if v is None:
                    vals.append("")
                elif isinstance(v, str) and "," in v:
                    vals.append(f'"{v}"')
                else:
                    vals.append(str(v))
            f.write(",".join(vals) + "\n")


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analysis.py [summary|best|controls|null|validations|benchmarks]")
        sys.exit(1)

    cmd = sys.argv[1]
    conn = db.get_connection()

    if cmd == "summary":
        summary(conn)
    elif cmd == "best":
        show_best(conn)
    elif cmd == "controls":
        show_controls(conn)
    elif cmd == "null":
        show_null(conn)
    elif cmd == "validations":
        show_validations(conn)
    elif cmd == "benchmarks":
        show_benchmarks(conn)
    else:
        print(f"Unknown command: {cmd}")
