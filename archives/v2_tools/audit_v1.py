"""Read-only V1 measured reproduction. Writes only new audit evidence and logs."""
import argparse
import ast
import collections
import csv
import datetime
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import sqlite3
import statistics
import struct
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "archives/v1_baseline"
AUDIT = ROOT / "archives/v2_audit"
WINLIBS = Path("C:/Users/zelin/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin")
KERNEL = BASE / "kernel.exe"
METRICS = ["pearson01", "spearman01", "mae01", "gradient01", "spectral01", "autocorrelation01"]
WEIGHTS = [0.25, 0.15, 0.15, 0.15, 0.15, 0.15]
FIELDS = ["candidate_id", "score"] + METRICS + ["entropy", "anisotropy", "compression_ratio", "quantization_levels", "quantization_dom_frac", "escaped_fraction", "runtime_ms", "error_code"]
DRIVERS = ["V0_NONE", "V1_INV_PI", "V2_SMOOTH", "V3_CENTERED_INV_PI", "V4_PRIME_RESIDUAL", "V5_SHUFFLED", "V6_REVERSED", "V7_IMAGINARY", "V8_PHASE_RANDOMIZED"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ro_db(path):
    # Immutable avoids WAL/SHM creation; preflight refuses nonempty WAL files.
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError(f"Nonempty WAL requires separate read-only handling: {wal}")
    conn = sqlite3.connect(Path(path).as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def grouped(items, keys):
    counts = collections.Counter(tuple(r.get(k) for k in keys) for r in items)
    return [dict(zip(keys, key), count=n) for key, n in sorted(counts.items(), key=lambda kv: repr(kv[0]))]


def duplicate_groups(items, keys, transform=None, id_key="evaluation_id"):
    groups = collections.defaultdict(list)
    for item in items:
        key = tuple((transform(k, item.get(k)) if transform else item.get(k)) for k in keys)
        groups[key].append(item[id_key])
    duplicates = [{"key": list(k), "ids": v} for k, v in groups.items() if len(v) > 1]
    return {"key_fields": keys, "unique_keys": len(groups), "duplicate_groups": len(duplicates),
            "excess_rows": sum(len(g["ids"]) - 1 for g in duplicates), "groups": duplicates}


def field_hash(field):
    return sha(struct.pack("<" + "d" * len(field), *field))


def benchmark_worker():
    sys.path.insert(0, str(BASE))
    wf = importlib.import_module("worldforge")
    with ro_db(BASE / "history.sqlite3") as conn:
        stored = rows(conn, "SELECT * FROM benchmark_runs ORDER BY benchmark_id")
    dataset = [{**r, "features": json.loads(r["feature_json"])} for r in stored]
    detector = wf.NearestCentroidDetector()
    detector.train(dataset)
    result = {"source": str(BASE / "worldforge.py"), "stored_rows": len(stored),
              "world_seed_split_label_inventory": [{k: r[k] for k in ("benchmark_id", "world_type", "seed", "split", "label")} for r in stored],
              "world_split_counts": grouped(stored, ["world_type", "split", "label"]),
              "feature_names": detector.feature_names, "centroids": detector.centroids,
              "feature_scaling": "none: raw features and squared Euclidean distance",
              "train_rows_used": [r["benchmark_id"] for r in stored if r["split"] == "train" and r["label"] in ("natural", "computational")],
              "validation_split_count": sum(r["split"] == "validation" for r in stored),
              "declared_holdout_worlds": wf.HOLDOUT_COMPUTATIONAL}
    for split in ("train", "holdout"):
        accuracy, predictions = detector.evaluate(dataset, split)
        confusion = collections.Counter()
        for r in predictions:
            confusion[("T" if r["correct"] else "F") + ("P" if r["predicted"] == "computational" else "N")] += 1
        tp, fp, fn = confusion["TP"], confusion["FP"], confusion["FN"]
        result[split] = {"accuracy": accuracy, "correct": sum(r["correct"] for r in predictions), "total": len(predictions),
                         "confusion": {k: confusion[k] for k in ("TP", "TN", "FP", "FN")},
                         "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
                         "predictions": predictions}
    by_feature = collections.defaultdict(list)
    for r in dataset:
        by_feature[json.dumps(r["features"], sort_keys=True)].append(r)
    result["cross_split_exact_feature_duplicates"] = [
        [{k: r[k] for k in ("benchmark_id", "world_type", "seed", "split")} for r in group]
        for group in by_feature.values() if {r["split"] for r in group} == {"train", "holdout"}]
    started = time.perf_counter()
    fresh = wf.generate_benchmark(seeds_per_world=20)
    stored_map = {(r["world_type"], r["seed"]): r for r in dataset}
    comparisons = []
    for item in fresh:
        old = stored_map.get((item["world_type"], item["seed"]))
        comparisons.append({"world_type": item["world_type"], "seed": item["seed"], "split": item["split"],
                            "field_sha256_float64_le": field_hash(item["field"]), "field_cells": len(item["field"]),
                            "feature_exact_match": bool(old and old["features"] == item["features"]),
                            "label_match": bool(old and old["label"] == item["label"]),
                            "split_match": bool(old and old["split"] == item["split"])})
    result["fresh_generation_seconds"] = time.perf_counter() - started
    result["fresh_generation"] = comparisons
    result["fresh_exact_feature_matches"] = sum(r["feature_exact_match"] for r in comparisons)
    fresh_detector = wf.NearestCentroidDetector()
    fresh_detector.train(fresh)
    result["fresh_accuracies"] = {s: fresh_detector.evaluate(fresh, s)[0] for s in ("train", "holdout")}
    prime = [r for r in comparisons if r["world_type"] == "WORLD_PRIME"]
    result["prime_unique_field_hashes_across_20_seeds"] = len({r["field_sha256_float64_le"] for r in prime})
    result["prime_training_rows"] = [r["benchmark_id"] for r in stored if r["world_type"] == "WORLD_PRIME" and r["split"] == "train"]
    result["prime_count_comparison"] = [{"k": k, "worldforge_pi": wf._pi_count(k),
                                            "standard_pi": sum(wf._is_prime(n) for n in range(2, k + 1))} for k in (0, 1, 2, 3, 5, 10, 100, 1000)]
    # Separate diagnostic, not a patch or a revised V1 benchmark claim.
    without_prime = wf.NearestCentroidDetector()
    without_prime.train([r for r in dataset if r["world_type"] != "WORLD_PRIME"])
    result["diagnostic_excluding_prime_from_training"] = {
        "holdout_accuracy": without_prime.evaluate(dataset, "holdout")[0],
        "prime_predictions": [r for r in without_prime.evaluate(dataset, "holdout")[1] if r["world_type"] == "WORLD_PRIME"]}
    result["impact"] = "Nominal seed holdout is not an unseen WORLD_PRIME holdout: prime contributes to training and all 20 prime fields are identical. Unknown-label worlds are omitted from accuracy. No evidence records historical feature or threshold tuning."
    print(json.dumps(result, allow_nan=False))


def ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    out = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        for k in range(i, j):
            out[order[k]] = (i + 1 + j) / 2
        i = j
    return out


def cosine01(a, b):
    den = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return max(0.0, min(1.0, (1 + sum(x*y for x, y in zip(a, b)) / den) / 2)) if den >= 1e-15 else 0.5


def pearson01(a, b):
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    return cosine01([x-ma for x in a], [x-mb for x in b])


def gradient(field):
    out = []
    for y in range(30):
        for x in range(60):
            i = y * 60 + x
            out.extend([field[i+1 if x < 59 else i] - field[i-1 if x > 0 else i],
                        field[i+60 if y < 29 else i] - field[i-60 if y > 0 else i]])
    return out


def dct(field):
    return [sum(field[y*60+x] * math.cos(math.pi*u*(2*x+1)/120) * math.cos(math.pi*v*(2*y+1)/60)
                for y in range(30) for x in range(60)) for u in range(8) for v in range(8) if u or v]


def autocorrelation(field):
    mean = sum(field) / 1800
    std = math.sqrt(sum((v-mean)**2 for v in field) / 1800)
    if std < 1e-15:
        return [0.0] * 80
    centered = [(v-mean)/std for v in field]
    out = []
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            if not dx and not dy:
                continue
            vals = [centered[y*60+x] * centered[(y+dy)*60+x+dx]
                    for y in range(max(0, -dy), min(30, 30-dy)) for x in range(max(0, -dx), min(60, 60-dx))]
            out.append(sum(vals)/len(vals))
    return out


def target_field(target):
    field = []
    for y in range(30):
        for x in range(60):
            u, v = x/59, y/29
            if target == "TARGET_PHASE":
                u, v = (u + 0.07) % 1, (v - 0.11) % 1
            value = abs(math.sin(math.pi*u) * math.cos(math.pi*v))
            field.append(value * value if target == "TARGET_B" else value)
    return field


def reference_field(cr, ci, driver, alpha=1.0, mi=200):
    primes = [False, False] + [True] * (mi - 1)
    for k in range(2, math.isqrt(mi) + 1):
        if primes[k]:
            for n in range(k*k, mi+1, k):
                primes[n] = False
    count = 0
    raw = []
    for k in range(1, mi+1):
        count += primes[k]
        raw.append(1 / max(1, count))
    forcing = raw
    if driver == "V0_NONE":
        forcing = [0.0]*mi
    elif driver == "V4_PRIME_RESIDUAL":
        smooth = [math.log(k+2)/(k+1) for k in range(1, mi+1)]
        mr, ms = statistics.mean(raw), statistics.mean(smooth)
        sr, ss = statistics.pstdev(raw), statistics.pstdev(smooth)
        residual = [r - (mr + sr*(s-ms)/ss) for r, s in zip(raw, smooth)]
        mean, std = statistics.mean(residual), statistics.pstdev(residual)
        forcing = [(v-mean)/std for v in residual]
    field = []
    for y in range(30):
        for x in range(60):
            zr, zi = -1.8 + 3.6*x/59, -1.0 + 2*y/29
            escaped = False
            for i, force in enumerate(forcing):
                zr, zi = zr*zr - zi*zi + cr + alpha*force, 2*zr*zi + ci
                if zr*zr + zi*zi > 4:
                    escaped = True
                    break
            nu = (i+1) - math.log(math.log(math.hypot(zr, zi))) / math.log(2) if escaped else mi
            field.append(max(0, min(mi, nu))/mi)
    return field


def reference_metrics(field, target):
    values = [pearson01(field, target), pearson01(ranks(field), ranks(target)),
              max(0, min(1, 1-sum(abs(a-b) for a, b in zip(field, target))/1800)),
              cosine01(gradient(field), gradient(target)), cosine01(dct(field), dct(target)),
              cosine01(autocorrelation(field), autocorrelation(target))]
    return dict(zip(METRICS, values), score=sum(v*w for v, w in zip(values, WEIGHTS)))


class Audit:
    def __init__(self, stages):
        AUDIT.mkdir(exist_ok=True)
        self.path = AUDIT / "evidence.json"
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        self.logs = AUDIT / ("v1_commands_" + stamp)
        self.logs.mkdir()
        self.e = {"audit": "V1 forensic measurements only; no application patches", "started_utc": stamp,
                  "requested_stages": stages, "baseline": str(BASE), "workspace": str(ROOT),
                  "python": sys.executable, "python_version": platform.python_version(), "sqlite_version": sqlite3.sqlite_version,
                  "helper_sha256": sha(Path(__file__).read_bytes()), "log_directory": str(self.logs),
                  "database_access": "mode=ro&immutable=1; PRAGMA query_only=ON; no application DB connection factory",
                  "specification_sha256": sha((AUDIT / "input_specification.txt").read_bytes()),
                  "specification_lines": len((AUDIT / "input_specification.txt").read_text(encoding="utf-8").splitlines()),
                  "commands": [], "stage_errors": {}}
        self.env = dict(os.environ)
        self.env["PATH"] = str(WINLIBS) + os.pathsep + self.env.get("PATH", "")
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.manifest = load(BASE / "snapshot_manifest.json")
        self.proto = load(BASE / "protocol.json")
        self.best = load(BASE / "best/best_metrics.json")
        self.state = load(BASE / "state.json")
        self.before = self.capture_files()
        self.e["preservation_before"] = self.before
        self.save()

    def save(self):
        temporary = self.path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.e, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def capture_files(self):
        result = {}
        for directory, label in ((ROOT, "current"), (BASE, "snapshot")):
            for p in directory.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(directory)
                if label == "current" and rel.parts[0] == "archives":
                    continue
                result[label + "/" + rel.as_posix()] = {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
        return result

    def command(self, name, args, stdin=None, timeout=10):
        number = len(self.e["commands"]) + 1
        prefix = self.logs / (f"{number:03d}_" + re.sub(r"[^A-Za-z0-9_-]", "_", name))
        record = {"number": number, "name": name, "argv": [str(a) for a in args], "cwd": str(self.logs),
                  "timeout_seconds": timeout, "environment_overrides": {"PATH_prefix": str(WINLIBS), "PYTHONDONTWRITEBYTECODE": "1"}}
        if stdin is not None:
            p = Path(str(prefix) + ".stdin.log")
            p.write_bytes(stdin.encode("utf-8"))
            record["stdin_path"] = str(p)
        start = time.perf_counter()
        stdout, stderr = b"", b""
        process = None
        try:
            process = subprocess.Popen(record["argv"], cwd=self.logs, env=self.env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            record["pid"] = process.pid
            try:
                stdout, stderr = process.communicate(None if stdin is None else stdin.encode("utf-8"), timeout=timeout)
                record["timed_out"] = False
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                record["timed_out"] = True
                record["killed_and_reaped"] = process.poll() is not None
            record["returncode"] = process.returncode
        except Exception:
            record["exception"] = traceback.format_exc()
        record["elapsed_seconds"] = time.perf_counter() - start
        for kind, data in (("stdout", stdout), ("stderr", stderr)):
            p = Path(str(prefix) + f".{kind}.log")
            p.write_bytes(data)
            record[kind + "_path"] = str(p)
            record[kind + "_bytes"] = len(data)
            record[kind + "_sha256"] = sha(data)
        Path(str(prefix) + ".command.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.e["commands"].append(record)
        self.save()
        return record, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

    def candidate(self, driver, cr=None, ci=None, **kwargs):
        return {"cr": self.best["cr"] if cr is None else cr, "ci": self.best["ci"] if ci is None else ci,
                "model_id": driver, "driver": driver, "alpha": 1.0, "degree": 2, "channel": 0,
                "max_iter": 200, "seed": 7331, **kwargs}

    def batch(self, name, candidates, timeout=15):
        lines = []
        for i, c in enumerate(candidates, 1):
            lines.append(f"{i} {c['cr']:.6f} {c['ci']:.6f} {c['model_id']} {c['driver']} {c['alpha']:.4f} {c['degree']} {c['channel']} {c['max_iter']} {c['seed']}")
        record, stdout, _ = self.command(name, [KERNEL, "--batch"], "\n".join(lines) + "\n", timeout)
        results = []
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 16:
                continue
            values = [float(x) for x in parts]
            row = dict(zip(FIELDS, values))
            for key in ("candidate_id", "quantization_levels", "error_code"):
                row[key] = int(row[key])
            row["command_number"] = record["number"]
            row["input"] = candidates[row["candidate_id"] - 1]
            results.append(row)
        return results

    def render(self, name, c, target="TARGET_A", timeout=5):
        args = [KERNEL, "--render", "--cr", f"{c['cr']:.6f}", "--ci", f"{c['ci']:.6f}", "--driver", c["driver"],
                "--alpha", str(c["alpha"]), "--degree", str(c["degree"]), "--channel", str(c["channel"]),
                "--max-iter", str(c["max_iter"]), "--seed", str(c["seed"]), "--target", target]
        record, stdout, _ = self.command(name, args, timeout=timeout)
        result = {"input": c, "target": target, "command_number": record["number"], "returncode": record.get("returncode")}
        match = re.search(r"Score:\s*(\S+)\s+Pearson01:\s*(\S+)", stdout)
        if match:
            result.update(score=float(match[1]), pearson01=float(match[2]))
            map_lines = stdout.splitlines()[:30]
            result["map"] = {"rows": len(map_lines), "widths": sorted(set(map(len, map_lines))),
                             "nonspace_cells": sum(ch != " " for line in map_lines for ch in line),
                             "sha256_lf": sha(("\n".join(map_lines) + "\n").encode())}
        return result

    def inventory(self):
        verification = []
        for f in self.manifest["files"]:
            archived = self.before.get("snapshot/" + f["path"])
            current = self.before.get("current/" + f["path"])
            verification.append({"path": f["path"], "manifest_sha256": f["sha256"], "manifest_bytes": f["bytes"],
                                 "snapshot": archived, "current": current,
                                 "snapshot_matches": bool(archived and archived["sha256"] == f["sha256"] and archived["bytes"] == f["bytes"]),
                                 "current_matches_snapshot": current == archived})
        sources = []
        for p in sorted(BASE.iterdir()):
            if p.suffix in (".py", ".c") or p.name == "Makefile":
                data = p.read_bytes()
                sources.append({"path": p.name, "bytes": len(data), "lines": len(data.splitlines()), "newline_count": data.count(b"\n"), "sha256": sha(data)})
        tree = ast.parse((BASE / "agent_loop.py").read_text(encoding="utf-8"))
        declared = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PHASE_ORDER" for t in n.targets))
        phase_log = re.findall(r"Starting phase: (\w+)", (BASE / "run.log").read_text(encoding="utf-8"))
        self.e["inventory"] = {"manifest_entries": len(verification), "verified_entries": sum(f["snapshot_matches"] for f in verification),
                               "hash_verification": verification, "sources_and_build_file": sources,
                               "source_count_py_c": sum(f["path"] != "Makefile" for f in sources),
                               "source_lines_py_c": sum(f["lines"] for f in sources if f["path"] != "Makefile"),
                               "source_plus_makefile_lines": sum(f["lines"] for f in sources),
                               "separate_test_files": [p.relative_to(BASE).as_posix() for p in BASE.rglob("test*") if p.is_file()],
                               "declared_phases": declared, "executed_phase_log": phase_log,
                               "artifact_directories": {name: [p.relative_to(BASE).as_posix() for p in (BASE / name).rglob("*") if p.is_file()] for name in ("best", "validation", "benchmark")}}
        source_names = ["kernel.c", "agent_loop.py", "controller.py", "analysis.py", "worldforge.py", "protocol.py", "db.py", "ui.py", "report.py"]
        hashes = {}
        for label, directory in (("snapshot", BASE), ("current", ROOT)):
            hashes[label + "_source_hash"] = sha(b"".join(n.encode() + (directory / n).read_bytes() for n in sorted(source_names)))
            hashes[label + "_protocol_hash"] = sha(json.dumps(load(directory / "protocol.json"), sort_keys=True, separators=(",", ": ")).encode())
        hashes["protocol_hash_convention"] = 'SHA256(json.dumps(sort_keys=True, separators=(",", ": "))), not raw-file SHA256'
        hashes["source_hash_convention"] = "SHA256 concatenated sorted 9 source filenames and raw bytes; excludes Makefile, binary, artifacts"
        hashes["saved_reproducibility"] = load(BASE / "reproducibility.json")
        hashes["saved_report_hash_lines"] = [line for line in (BASE / "report.md").read_text(encoding="utf-8").splitlines() if "hash:" in line.lower()]
        self.e["hash_provenance"] = hashes

    def database(self):
        with ro_db(BASE / "history.sqlite3") as conn:
            tables = rows(conn, "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
            self.evals = rows(conn, "SELECT * FROM evaluations ORDER BY evaluation_id")
            self.nulls = rows(conn, "SELECT * FROM null_runs ORDER BY null_id")
            self.validations = rows(conn, "SELECT * FROM validations ORDER BY validation_id")
            runs = rows(conn, "SELECT * FROM runs ORDER BY started_at, run_id")
            events = rows(conn, "SELECT * FROM events ORDER BY event_id")
            result = {"tables": {t["name"]: conn.execute('SELECT COUNT(*) FROM "' + t["name"] + '"').fetchone()[0] for t in tables},
                      "schemas": tables, "indexes": rows(conn, "SELECT name, sql FROM sqlite_master WHERE type='index'"),
                      "integrity_check": [r[0] for r in conn.execute("PRAGMA integrity_check")],
                      "foreign_key_check": rows(conn, "PRAGMA foreign_key_check"),
                      "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
                      "query_only": conn.execute("PRAGMA query_only").fetchone()[0], "runs": runs, "events": events,
                      "validations": self.validations, "null_runs": self.nulls,
                      "best_snapshots": rows(conn, "SELECT * FROM best_snapshots ORDER BY snapshot_id")}
        self.main = [r for r in self.evals if r["run_id"] == self.state["run_id"]]
        validation_ids = {json.loads(v["metrics_json"])["evaluation_id"] for v in self.validations if v["metrics_json"] and "evaluation_id" in json.loads(v["metrics_json"])}
        null_candidates = sorted([r for r in self.main if r["driver"] == "V1_INV_PI" and r["evaluation_id"] not in validation_ids], key=lambda r: r["candidate_id"])
        expected = sum(n["search_budget"] * 9 for n in self.nulls)
        self.null_candidates = null_candidates[-expected:]
        null_ids = {r["evaluation_id"] for r in self.null_candidates}
        baseline_id = min(r["evaluation_id"] for r in self.main)
        self.roles = {}
        for r in self.evals:
            eid = r["evaluation_id"]
            if r["run_id"] != self.state["run_id"]:
                role = "other_run_single"
            elif eid == baseline_id:
                role = "baseline_default"
            elif r["driver"] in ("V1", "V4"):
                role = "primary_search_stored"
            elif eid in validation_ids:
                role = "validation_evaluation"
            elif eid in null_ids:
                role = "null_random_search"
            else:
                role = "control_at_best"
            self.roles[eid] = role
        tagged = [{**r, "audit_role": self.roles[r["evaluation_id"]]} for r in self.evals]
        result.update(total_evaluations=len(self.evals), per_run=grouped(tagged, ["run_id"]),
                      per_driver_model=grouped(tagged, ["model_id", "driver"]), per_role=grouped(tagged, ["audit_role"]),
                      per_run_driver_role=grouped(tagged, ["run_id", "driver", "audit_role"]),
                      classification_method="Primary=short V1/V4. Validation=metrics_json evaluation_id. Baseline=first main-run row. Null=last sum(budget*9) canonical V1 nonvalidation candidates; blocks verified separately. Remaining main rows=controls.")
        keys = ["run_id", "cr", "ci", "model_id", "driver", "degree", "channel", "alpha", "max_iter"]
        result["duplicates_exact_parameters"] = duplicate_groups(self.evals, keys)
        result["duplicates_kernel_serialization"] = duplicate_groups(self.evals, keys, lambda k, v: round(v, 6) if k in ("cr", "ci") else round(v, 4) if k == "alpha" else v)
        result["duplicates_run_step_candidate"] = duplicate_groups(self.evals, ["run_id", "step", "candidate_id"])
        result["zero_scores"] = [r["evaluation_id"] for r in self.evals if r["score"] == 0]
        result["missing_or_nonfinite_scores"] = [r["evaluation_id"] for r in self.evals if r["score"] is None or not math.isfinite(r["score"])]
        result["seed_missing_count"] = sum(r["seed"] is None for r in self.evals)
        result["error_status_limit"] = "evaluations has no error_code/status column; historical failure counts cannot be proved zero. Kernel parser failures/timeouts are not persisted as evaluations."
        result["error_events"] = [r for r in events if any(s in r["event_type"] for s in ("ERROR", "FAIL", "TIMEOUT"))]
        result["best_by_role"] = {role: max((r for r in tagged if r["audit_role"] == role), key=lambda r: r["score"]) for role in sorted(set(self.roles.values()))}
        result["best_by_driver"] = {driver: max((r for r in tagged if r["driver"] == driver), key=lambda r: r["score"]) for driver in sorted({r["driver"] for r in tagged})}
        result["best_overall_evaluated"] = max(self.evals, key=lambda r: r["score"])
        result["best_flagged"] = max((r for r in self.evals if r["is_best"]), key=lambda r: r["score"])
        result["report_total_lines"] = [s for s in (BASE / "report.md").read_text(encoding="utf-8").splitlines() if "evaluations" in s.lower()]
        result["state_counter"] = self.state["total_evals"]
        present = {r["candidate_id"] for r in self.main}
        missing = sorted(set(range(1, self.state["candidate_counter"] + 1)) - present)
        ranges = []
        for n in missing:
            if ranges and n == ranges[-1][1]+1:
                ranges[-1][1] = n
            else:
                ranges.append([n, n])
        result["missing_main_candidate_ids"] = {"count": len(missing), "ranges": ranges, "coarse_scout_expected": self.state["scout_count"] * self.proto["search_budget"]["coarse_scout_grid"]**2}
        result["primary_steps"] = {driver: sorted({r["step"] for r in self.main if r["driver"] == driver}) for driver in ("V1", "V4")}
        self.e["database"] = result
        self.e["hash_provenance"]["saved_run_hashes"] = [{k: r[k] for k in ("run_id", "protocol_hash", "source_hash", "seed", "command_line")} for r in runs]
        with ro_db(ROOT / "history.sqlite3") as conn:
            self.e["current_database_counts"] = {t["name"]: conn.execute('SELECT COUNT(*) FROM "' + t["name"] + '"').fetchone()[0] for t in tables}

    def csv_trace(self):
        result = {}
        with ro_db(BASE / "history.sqlite3") as conn:
            for filename, table, id_key in (("control_summary.csv", "evaluations", "evaluation_id"), ("null_summary.csv", "null_runs", "null_id"), ("depth_summary.csv", "validations", "validation_id")):
                p = BASE / filename
                reader = csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))
                data = list(reader)
                stored = {str(r[id_key]): r for r in rows(conn, f"SELECT * FROM {table}")}
                trace = []
                for line, row in enumerate(data, 2):
                    old = stored.get(row.get(id_key))
                    differences = []
                    for key, value in row.items():
                        expected = "" if old and old.get(key) is None else str(old.get(key)) if old else None
                        if value != expected:
                            differences.append({"column": key, "csv": value, "sqlite_as_text": expected})
                    trace.append({"csv_line": line, id_key: row.get(id_key), "exact_all_cells": old is not None and not differences,
                                  "differences": differences, "role": self.roles.get(int(row[id_key])) if table == "evaluations" else None})
                result[filename] = {"header": reader.fieldnames, "data_rows": len(data), "physical_newline_count": p.read_bytes().count(b"\n"),
                                    "exact_rows": sum(t["exact_all_cells"] for t in trace), "trace": trace,
                                    "sqlite_ids_not_in_csv": sorted(set(stored) - {r.get(id_key) for r in data}, key=int)}
        history = load(BASE / "history.json")
        mapping = {r["evaluation_id"]: r for r in self.evals}
        aliases = {"model": "model_id"}
        mismatches = []
        for r in history:
            old = mapping.get(r["evaluation_id"])
            diff = [key for key, value in r.items() if not old or old.get(aliases.get(key, key)) != value]
            if diff:
                mismatches.append({"evaluation_id": r["evaluation_id"], "columns": diff})
        result["history.json"] = {"rows": len(history), "mismatches": mismatches}
        result["count_reconciliation"] = {"claimed_evaluations": 3235, "actual_sqlite_total": len(self.evals),
                                            "actual_main_run": len(self.main), "csv_data_rows": result["control_summary.csv"]["data_rows"],
                                            "csv_including_header": result["control_summary.csv"]["data_rows"]+1,
                                            "actual_minus_claim": len(self.evals)-3235,
                                            "note": "The CSV is an all-evaluations export, not controls only. The historical 3235 claim is not a primary-search count. Header and other-run inclusion explain scope differences; no evidence identifies why the completion claim was 3235."}
        self.e["csv_traceability"] = result

    def reproductions(self):
        self.e["self_test"] = self.command("existing_selftest", [KERNEL, "--self-test"], timeout=10)[0]
        self.e["kernel_version"] = self.command("version", [KERNEL, "--version"])[1].strip()
        self.e["compiler_version"] = self.command("gcc_version", [WINLIBS / "gcc.exe", "--version"])[1].strip()
        drivers = DRIVERS + ["V1", "V4", "NONE"]
        batch = self.batch("best_all_drivers", [self.candidate(d) for d in drivers])
        renders = [self.render("best_render_" + d, self.candidate(d)) for d in drivers]
        repeats = self.batch("canonical_and_short_repeats", [self.candidate(d) for d in ("V1_INV_PI", "V1", "V4_PRIME_RESIDUAL", "V4") for _ in range(3)])
        lookup = {r["input"]["driver"]: r for r in batch}
        self.e["driver_reproduction"] = {"stored_best": self.best, "batch": batch, "render": renders, "repeats": repeats,
                                         "batch_render_score_differences": {r["input"]["driver"]: r.get("score", 0)-lookup[r["input"]["driver"]]["score"] for r in renders},
                                         "canonical_v1_minus_smooth": lookup["V1_INV_PI"]["score"]-lookup["V2_SMOOTH"]["score"],
                                         "canonical_v4_minus_smooth": lookup["V4_PRIME_RESIDUAL"]["score"]-lookup["V2_SMOOTH"]["score"],
                                         "impact": "Short driver names silently select V0_NONE. Stored short-name search cannot establish optimization of canonical V1/V4."}
        holdouts = [self.render("holdout_" + d + "_" + t, self.candidate(d), t) for d in ("V0_NONE", "V1_INV_PI", "V4_PRIME_RESIDUAL", "V1", "V4") for t in ("TARGET_B", "TARGET_PHASE")]
        self.e["holdouts"] = {"fresh": holdouts, "stored": [v for v in self.validations if v["validation_type"] == "holdout"],
                               "no_reoptimization": True, "impact": "Compare canonical holdouts to canonical TARGET_A, not to the short-driver stored best."}
        references = []
        for driver in ("V0_NONE", "V1_INV_PI", "V4_PRIME_RESIDUAL"):
            cr, ci = float(f"{self.best['cr']:.6f}"), float(f"{self.best['ci']:.6f}")
            field = reference_field(cr, ci, driver)
            ref = reference_metrics(field, target_field("TARGET_A"))
            references.append({"driver": driver, "serialized_cr": cr, "serialized_ci": ci, "metrics_full_precision": ref,
                               "field_min": min(field), "field_max": max(field), "field_sha256_float64_le": field_hash(field),
                               "difference_vs_binary_6_decimal_output": {k: ref[k]-lookup[driver][k] for k in ["score"] + METRICS}})
        self.e["canonical_scoring"] = {"weights": dict(zip(METRICS, WEIGHTS)), "independent_python_reference": references,
                                       "stored_metric_weighted_sum": sum(self.best[k]*w for k, w in zip(METRICS, WEIGHTS)),
                                       "all_database_weighted_sum_max_abs_error": max(abs(r["score"]-sum(r[k]*w for k, w in zip(METRICS, WEIGHTS))) for r in self.evals),
                                       "precision_note": "Kernel TSV and render expose 6 decimals; exact float field comparisons are not available from its CLI. Python reference uses independent standard-library arithmetic."}
        boundaries = []
        for driver in ("V0_NONE", "V1", "V1_INV_PI", "V4", "V4_PRIME_RESIDUAL"):
            points = [self.best["cr"]+d for d in (-0.05, -0.02, 0, 0.02, 0.05)] + [1.0, 1.05, 1.1]
            boundaries.extend(self.batch("boundary_" + driver, [self.candidate(driver, cr=cr) for cr in points]))
        boundary_rows = [r for r in self.main if r["cr"] == self.proto["search_range"]["cr_max"]]
        self.e["boundary_diagnostic"] = {"distance_to_upper": 1-self.best["cr"], "fraction_of_cr_range": (1-self.best["cr"])/2.5,
                                         "forward_and_backward": boundaries, "stored_cr_upper_boundary_rows": boundary_rows,
                                         "note": "Out-of-domain points are diagnostics only, not a continuation or alteration of frozen V1. Candidate clipping/rejections were not logged; boundary rows alone do not prove an unconstrained optimum."}
        self.e["alpha_zero_equivalence"] = self.batch("alpha_zero", [self.candidate("V0_NONE")] + [self.candidate(d, alpha=0.0) for d in DRIVERS[1:]])
        self.save()

    def replay(self):
        comparisons, errors = [], []
        for offset in range(0, len(self.evals), 128):
            chunk = self.evals[offset:offset+128]
            candidates = [self.candidate(r["driver"], cr=r["cr"], ci=r["ci"], model_id=r["model_id"], alpha=r["alpha"], degree=r["degree"], channel=r["channel"], max_iter=r["max_iter"]) for r in chunk]
            results = self.batch(f"stored_replay_{offset:04d}", candidates)
            lookup = {r["candidate_id"]: r for r in results}
            for i, old in enumerate(chunk, 1):
                fresh = lookup.get(i)
                diffs = {k: fresh[k]-old[k] for k in ["score"]+METRICS if fresh and fresh[k] != old[k]}
                comparisons.append({"evaluation_id": old["evaluation_id"], "role": self.roles[old["evaluation_id"]],
                                    "command_number": fresh["command_number"] if fresh else None, "candidate_id_in_command": i,
                                    "exact_score_and_six_metrics": fresh is not None and not diffs, "differences": diffs,
                                    "error_code": fresh["error_code"] if fresh else None})
                if not fresh or fresh["error_code"]:
                    errors.append(old["evaluation_id"])
        self.e["stored_evaluation_replay"] = {"requested": len(self.evals), "exact_score_and_six_metrics": sum(c["exact_score_and_six_metrics"] for c in comparisons),
                                               "missing_or_kernel_errors": errors, "rows": comparisons,
                                               "seed_policy": "Replay uses protocol shuffle seed 7331 because every historical evaluation seed is NULL; runtime is excluded."}

    def null_audit(self):
        scores = [n["best_score"] for n in self.nulls]
        observed = self.best["score"]
        blocks = []
        offset = 0
        for n in self.nulls:
            count = n["search_budget"] * 9
            block = self.null_candidates[offset:offset+count]
            offset += count
            maximum = max(block, key=lambda r: r["score"])
            rng = random.Random(n["seed"])
            expected = [(rng.uniform(-1.5, 1.0), rng.uniform(-1.2, 1.2)) for _ in block]
            matches = sum((r["cr"], r["ci"]) == pair for r, pair in zip(block, expected))
            blocks.append({"null_id": n["null_id"], "recorded_seed": n["seed"], "stored_budget_steps": n["search_budget"],
                           "candidate_count": len(block), "evaluation_id_range": [block[0]["evaluation_id"], block[-1]["evaluation_id"]],
                           "candidate_id_range": [block[0]["candidate_id"], block[-1]["candidate_id"]],
                           "computed_max": maximum["score"], "stored_max": n["best_score"],
                           "max_and_parameters_match": (maximum["score"], maximum["cr"], maximum["ci"]) == (n["best_score"], n["best_cr"], n["best_ci"]),
                           "max_evaluation_ids": [r["evaluation_id"] for r in block if r["score"] == maximum["score"]],
                           "recorded_seed_random_replay_matches": matches,
                           "first_actual_point": [block[0]["cr"], block[0]["ci"]], "first_recorded_seed_point": expected[0]})
        primary = [r for r in self.main if self.roles[r["evaluation_id"]] == "primary_search_stored"]
        self.e["null_audit"] = {"observed_stored_best": observed, "null_max": max(scores), "null_mean": statistics.mean(scores),
                                "null_std_sample": statistics.stdev(scores), "null_median": statistics.median(scores),
                                "observed_minus_mean": observed-statistics.mean(scores), "observed_minus_max": observed-max(scores),
                                "exceedance_count": sum(s >= observed for s in scores), "null_runs": len(scores),
                                "empirical_search_null_plus_one": (1+sum(s >= observed for s in scores))/(1+len(scores)),
                                "observed_percentile_strict": sum(s < observed for s in scores)/len(scores),
                                "unique_max_scores": len(set(scores)),
                                "duplicate_max_records": duplicate_groups(self.nulls, ["best_score", "best_cr", "best_ci"], id_key="null_id"),
                                "blocks": blocks, "primary_stored_per_driver": grouped(primary, ["driver"]),
                                "protocol_search_budget": self.proto["search_budget"], "protocol_null_budget": self.proto["null_budget"],
                                "primary_unstored_scout_candidates": self.e["database"]["missing_main_candidate_ids"],
                                "seed_traceability": "Null loop records 10000+i but never seeds the module-global random generator. Historical RNG state absent; independent Random(recorded_seed) comparison measured for all points.",
                                "fairness": "Random search has 270 points per run versus 100-step adaptive tracks with scouts. Canonical V1 null forcing differs from short-name V0 primary forcing. Empirical exceedance is descriptive, not a calibrated matched-search p-value."}
        self.e["null_maxima_replay"] = self.batch("null_maxima", [self.candidate(n["model_id"], cr=n["best_cr"], ci=n["best_ci"]) for n in self.nulls])

    def invalid_cli(self):
        tests = [("nan_cr", ["--cr", "NaN"]), ("inf_ci", ["--ci", "Inf"]), ("nonnumeric_cr", ["--cr", "banana"]),
                 ("nonnumeric_ci", ["--ci", "banana"]), ("negative_iter", ["--max-iter", "-1"]),
                 ("zero_iter", ["--max-iter", "0"]), ("too_large_iter", ["--max-iter", "5000"]),
                 ("unknown_driver", ["--driver", "UNKNOWN"]), ("unknown_model", ["--model", "UNKNOWN"]),
                 ("unknown_target", ["--target", "UNKNOWN"]), ("unknown_option", ["--nonsense", "1"]),
                 ("missing_value", ["--cr"]), ("invalid_degree", ["--degree", "-1"]), ("invalid_channel", ["--channel", "9"])]
        records = []
        for name, options in tests:
            record, stdout, stderr = self.command("invalid_render_" + name, [KERNEL, "--render"] + options, timeout=2)
            match = re.search(r"Score:\s*(\S+)", stdout)
            records.append({"name": name, "command_number": record["number"], "returncode": record.get("returncode"),
                            "timed_out": record.get("timed_out"), "score_text": match[1] if match else None,
                            "stderr": stderr, "stdout_bytes": record["stdout_bytes"]})
        batch_cases = [("nan", "1 nan 0 V1_INV_PI V1_INV_PI 1 2 0 200 7331\n"),
                       ("inf", "1 0 inf V1_INV_PI V1_INV_PI 1 2 0 200 7331\n"),
                       ("nonnumeric", "1 banana 0 V1_INV_PI V1_INV_PI 1 2 0 200 7331\n"),
                       ("negative_iter", "1 0 0 V1_INV_PI V1_INV_PI 1 2 0 -1 7331\n"),
                       ("large_iter", "1 0 0 V1_INV_PI V1_INV_PI 1 2 0 5000 7331\n"),
                       ("unknown_driver", "1 0 0 V1_INV_PI UNKNOWN 1 2 0 200 7331\n"),
                       ("unknown_model", "1 0 0 UNKNOWN V1_INV_PI 1 2 0 200 7331\n"),
                       ("truncated", "1 0 0 V1_INV_PI\n")]
        for name, text in batch_cases:
            record, stdout, stderr = self.command("invalid_batch_" + name, [KERNEL, "--batch"], text, timeout=2)
            records.append({"name": "batch_"+name, "command_number": record["number"], "returncode": record.get("returncode"),
                            "timed_out": record.get("timed_out"), "stdout": stdout, "stderr": stderr})
        record, _, _ = self.command("unknown_command", [KERNEL, "--unknown"], timeout=2)
        self.e["invalid_cli"] = {"cases": records, "unknown_command": record, "timeout_policy": "Each suspect process limited to 2 seconds; timed-out child killed and reaped."}
        self.e["edge_iterations"] = self.batch("edge_iterations", [self.candidate("V1_INV_PI", cr=0, ci=0, max_iter=mi) for mi in (1, 2, 10)])

    def prime_trace(self):
        record, stdout, _ = self.command("prime_trace_1000", [KERNEL, "--trace", "--cr", f"{self.best['cr']:.6f}", "--ci", f"{self.best['ci']:.6f}", "--driver", "V1_INV_PI", "--max-iter", "1000"], timeout=15)
        trace = list(csv.DictReader(io.StringIO(stdout), delimiter="\t"))
        checks, count = [], 0
        for i, row in enumerate(trace, 1):
            prime = i >= 2 and all(i % k for k in range(2, math.isqrt(i)+1))
            count += prime
            checks.append({"k": i, "trace_iter": int(row["iter"]), "expected_pi": count,
                           "driver": float(row["driver"]), "expected_inv_pi": 1/max(1, count),
                           "driver_matches_print_precision": abs(float(row["driver"])-1/max(1, count)) <= 0.00000051,
                           "prime_event_matches": int(row["prime"]) == int(prime)})
        self.e["prime_trace"] = {"command_number": record["number"], "rows": len(trace), "first_100": checks[:100],
                                 "requested_pi_checks": [r for r in checks if r["k"] in (1, 2, 3, 5, 10, 100, 1000)],
                                 "driver_mismatches": [r for r in checks if not r["driver_matches_print_precision"]],
                                 "event_mismatches": [r for r in checks if not r["prime_event_matches"]],
                                 "note": "Trace iter is zero-based while prime/driver refer to k=iter+1. pi(0) is not exposed by CLI; existing selftest checks only pi(10), pi(100), pi(1000)."}

    def maps(self):
        result = {}
        for p in sorted((BASE / "best").glob("*.txt")):
            data = p.read_bytes()
            lines = data.decode("utf-8").splitlines()
            result[p.name] = {"bytes": len(data), "sha256": sha(data), "rows": len(lines), "row_widths": [len(s) for s in lines],
                              "nonspace_characters": sum(ch != " " for s in lines for ch in s),
                              "hex_if_small": data.hex() if len(data) <= 100 else None,
                              "dimension_60x30": len(lines) == 30 and all(len(s) == 60 for s in lines)}
        palette = " .:-=+*#%@"
        target_chars = [palette[max(0, min(9, int(v*10)))] for v in target_field("TARGET_A")]
        old_chars = list("".join((BASE / "best/target_map.txt").read_text().splitlines()))
        report_chars = [palette[min(9, int(abs(math.sin(math.pi*(-1.8+3.6*x/59))*math.cos(math.pi*(-1+2*y/29)))*10))] for y in range(30) for x in range(60)]
        result["target_coordinate_comparison"] = {"cells": len(old_chars), "different_from_kernel_TARGET_A": sum(a != b for a, b in zip(old_chars, target_chars)),
                                                  "different_from_report_coordinate_formula": sum(a != b for a, b in zip(old_chars, report_chars))}
        # Reproduce artifact extraction in memory, with no original artifact writes.
        rec, stdout, _ = self.command("artifact_render_raw", [KERNEL, "--render", "--cr", f"{self.best['cr']:.6f}", "--ci", f"{self.best['ci']:.6f}", "--driver", self.best["driver"], "--max-iter", str(self.best["max_iter"])])
        extracted = stdout.strip().split("\n")
        if extracted and "Score:" in extracted[-1]:
            extracted = extracted[:-1]
        if extracted and not extracted[-1].strip():
            extracted = extracted[:-1]
        artifact_bytes = ("\n".join(extracted) + "\n").replace("\n", "\r\n").encode()
        result["in_memory_original_extraction"] = {"command_number": rec["number"], "rows_after_strip": len(extracted),
                                                   "windows_output_hex": artifact_bytes.hex(),
                                                   "exact_match_stored_best_map": artifact_bytes == (BASE / "best/best_map.txt").read_bytes()}
        self.e["maps"] = result

    def benchmark(self):
        record, stdout, _ = self.command("benchmark_readonly_replay", [sys.executable, "-B", str(Path(__file__).resolve()), "--benchmark-worker"], timeout=120)
        if record.get("returncode") == 0:
            self.e["benchmark"] = json.loads(stdout)
            self.e["benchmark"]["command_number"] = record["number"]
        else:
            self.e["benchmark"] = {"unavailable": True, "command_number": record["number"]}

    def finish(self):
        after = self.capture_files()
        self.e["preservation_after"] = {"files_checked": len(after), "changed": [k for k in self.before if after.get(k) != self.before[k]],
                                         "removed": sorted(set(self.before)-set(after)), "new_original_tree_files": sorted(set(after)-set(self.before))}
        self.e["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.e["status"] = "completed_with_unavailable_diagnostics" if self.e["stage_errors"] else "completed"
        self.save()
        print(json.dumps({"evidence": str(self.path), "logs": str(self.logs), "status": self.e["status"],
                          "errors": self.e["stage_errors"], "preservation": self.e["preservation_after"]}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-worker", action="store_true")
    parser.add_argument("--stages", default="inventory,database,csv_trace,reproductions,replay,null_audit,invalid_cli,prime_trace,maps,benchmark")
    args = parser.parse_args()
    if args.benchmark_worker:
        benchmark_worker()
        return
    audit = Audit(args.stages.split(","))
    try:
        for stage in args.stages.split(","):
            print("Measuring " + stage, flush=True)
            started = time.perf_counter()
            try:
                getattr(audit, stage)()
            except Exception:
                detail = traceback.format_exc()
                audit.e["stage_errors"][stage] = detail
                (audit.logs / (stage + ".exception.log")).write_text(detail, encoding="utf-8")
                print(detail, file=sys.stderr, flush=True)
            audit.e.setdefault("stage_seconds", {})[stage] = time.perf_counter()-started
            audit.save()
    finally:
        audit.finish()


if __name__ == "__main__":
    main()
