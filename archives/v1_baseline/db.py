"""
PROOF OF SIMULATION — SQLite Access Layer
Canonical storage for all experiment data.
"""
import sqlite3
import json
import os
import time

DB_PATH = "history.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    phase TEXT,
    status TEXT,
    protocol_hash TEXT,
    source_hash TEXT,
    seed INTEGER,
    python_version TEXT,
    compiler TEXT,
    compiler_version TEXT,
    os TEXT,
    cpu TEXT,
    command_line TEXT
);

CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    family TEXT,
    degree INTEGER,
    driver TEXT,
    channel INTEGER,
    alpha REAL,
    description TEXT,
    protocol_version TEXT
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    step INTEGER,
    candidate_id INTEGER,
    cr REAL,
    ci REAL,
    model_id TEXT,
    driver TEXT,
    degree INTEGER,
    channel INTEGER,
    alpha REAL,
    max_iter INTEGER,
    score REAL,
    pearson01 REAL,
    spearman01 REAL,
    mae01 REAL,
    gradient01 REAL,
    spectral01 REAL,
    autocorrelation01 REAL,
    entropy REAL,
    anisotropy REAL,
    quantization_index REAL,
    compression_ratio REAL,
    escaped_fraction REAL,
    runtime_ms REAL,
    accepted INTEGER DEFAULT 0,
    is_best INTEGER DEFAULT 0,
    seed INTEGER,
    timestamp TEXT,
    metrics_json TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS best_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    step INTEGER,
    evaluation_id INTEGER,
    cr REAL,
    ci REAL,
    score REAL,
    model_id TEXT,
    driver TEXT,
    max_iter INTEGER,
    map_path TEXT,
    metrics_path TEXT,
    timestamp TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS validations (
    validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    best_snapshot_id INTEGER,
    validation_type TEXT,
    target_id TEXT,
    resolution TEXT,
    max_iter INTEGER,
    score REAL,
    metrics_json TEXT,
    status TEXT,
    timestamp TEXT,
    FOREIGN KEY (best_snapshot_id) REFERENCES best_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS null_runs (
    null_id INTEGER PRIMARY KEY AUTOINCREMENT,
    null_type TEXT,
    seed INTEGER,
    search_budget INTEGER,
    target_id TEXT,
    best_score REAL,
    best_cr REAL,
    best_ci REAL,
    model_id TEXT,
    result_json TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    benchmark_id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_type TEXT,
    seed INTEGER,
    split TEXT,
    feature_json TEXT,
    label TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    data_json TEXT,
    timestamp TEXT
);

CREATE INDEX IF NOT EXISTS idx_eval_run ON evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_score ON evaluations(score DESC);
CREATE INDEX IF NOT EXISTS idx_eval_best ON evaluations(is_best);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
"""


def get_connection(db_path=None):
    """Open a connection with proper PRAGMAs."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn):
    """Create all tables and indexes."""
    conn.executescript(SCHEMA)
    conn.commit()


def insert_run(conn, run_id, **kwargs):
    """Insert a new run record."""
    cols = ["run_id", "started_at"]
    vals = [run_id, kwargs.get("started_at", _now())]
    for k in ["finished_at", "phase", "status", "protocol_hash", "source_hash",
              "seed", "python_version", "compiler", "compiler_version",
              "os", "cpu", "command_line"]:
        if k in kwargs:
            cols.append(k)
            vals.append(kwargs[k])
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(f"INSERT INTO runs ({', '.join(cols)}) VALUES ({placeholders})", vals)
    conn.commit()


def update_run(conn, run_id, **kwargs):
    """Update run fields."""
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(run_id)
    conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?", vals)
    conn.commit()


def insert_evaluation(conn, run_id, step, candidate_id, cr, ci, model_id,
                      driver, degree, channel, alpha, max_iter,
                      score, pearson01, spearman01, mae01, gradient01,
                      spectral01, autocorrelation01,
                      entropy, anisotropy, quantization_index,
                      compression_ratio, escaped_fraction, runtime_ms,
                      seed=None, metrics_json=None):
    """Insert an evaluation result."""
    conn.execute("""
        INSERT INTO evaluations (
            run_id, step, candidate_id, cr, ci, model_id, driver,
            degree, channel, alpha, max_iter,
            score, pearson01, spearman01, mae01, gradient01,
            spectral01, autocorrelation01,
            entropy, anisotropy, quantization_index,
            compression_ratio, escaped_fraction, runtime_ms,
            accepted, is_best, seed, timestamp, metrics_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [run_id, step, candidate_id, cr, ci, model_id, driver,
          degree, channel, alpha, max_iter,
          score, pearson01, spearman01, mae01, gradient01,
          spectral01, autocorrelation01,
          entropy, anisotropy, quantization_index,
          compression_ratio, escaped_fraction, runtime_ms,
          0, 0, seed, _now(), metrics_json])
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def mark_best(conn, evaluation_id):
    """Mark an evaluation as the current best."""
    conn.execute("UPDATE evaluations SET is_best = 1 WHERE evaluation_id = ?",
                 [evaluation_id])
    conn.commit()


def insert_best_snapshot(conn, run_id, step, evaluation_id, cr, ci, score,
                         model_id, driver, max_iter, map_path=None, metrics_path=None):
    """Insert a best snapshot record."""
    conn.execute("""
        INSERT INTO best_snapshots (
            run_id, step, evaluation_id, cr, ci, score,
            model_id, driver, max_iter, map_path, metrics_path, timestamp
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, [run_id, step, evaluation_id, cr, ci, score,
          model_id, driver, max_iter, map_path, metrics_path, _now()])
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def insert_validation(conn, best_snapshot_id, validation_type, target_id,
                      resolution, max_iter, score, metrics_json=None, status="OK"):
    """Insert a validation result."""
    conn.execute("""
        INSERT INTO validations (
            best_snapshot_id, validation_type, target_id, resolution,
            max_iter, score, metrics_json, status, timestamp
        ) VALUES (?,?,?,?,?,?,?,?,?)
    """, [best_snapshot_id, validation_type, target_id, resolution,
          max_iter, score, metrics_json, status, _now()])
    conn.commit()


def insert_null_run(conn, null_type, seed, search_budget, target_id,
                    best_score, best_cr, best_ci, model_id, result_json=None):
    """Insert a null run result."""
    conn.execute("""
        INSERT INTO null_runs (
            null_type, seed, search_budget, target_id,
            best_score, best_cr, best_ci, model_id, result_json, timestamp
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
    """, [null_type, seed, search_budget, target_id,
          best_score, best_cr, best_ci, model_id, result_json, _now()])
    conn.commit()


def insert_benchmark(conn, world_type, seed, split, feature_json, label):
    """Insert a benchmark run result."""
    conn.execute("""
        INSERT INTO benchmark_runs (
            world_type, seed, split, feature_json, label, timestamp
        ) VALUES (?,?,?,?,?,?)
    """, [world_type, seed, split, feature_json, label, _now()])
    conn.commit()


def insert_event(conn, event_type, data=None):
    """Append an event to the events table."""
    conn.execute("""
        INSERT INTO events (event_type, data_json, timestamp) VALUES (?,?,?)
    """, [event_type, json.dumps(data) if data else None, _now()])
    conn.commit()


def get_best(conn, run_id=None):
    """Get the current best evaluation."""
    if run_id:
        row = conn.execute("""
            SELECT * FROM evaluations WHERE run_id = ? AND is_best = 1
            ORDER BY score DESC LIMIT 1
        """, [run_id]).fetchone()
    else:
        row = conn.execute("""
            SELECT * FROM evaluations WHERE is_best = 1
            ORDER BY score DESC LIMIT 1
        """).fetchone()
    return dict(row) if row else None


def get_all_evaluations(conn, run_id=None):
    """Get all evaluations, optionally filtered by run."""
    if run_id:
        rows = conn.execute("""
            SELECT * FROM evaluations WHERE run_id = ? ORDER BY evaluation_id
        """, [run_id]).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM evaluations ORDER BY evaluation_id
        """).fetchall()
    return [dict(r) for r in rows]


def get_null_runs(conn, null_type=None):
    """Get null run results."""
    if null_type:
        rows = conn.execute("""
            SELECT * FROM null_runs WHERE null_type = ? ORDER BY null_id
        """, [null_type]).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM null_runs ORDER BY null_id
        """).fetchall()
    return [dict(r) for r in rows]


def get_validations(conn, best_snapshot_id=None):
    """Get validation results."""
    if best_snapshot_id:
        rows = conn.execute("""
            SELECT * FROM validations WHERE best_snapshot_id = ? ORDER BY validation_id
        """, [best_snapshot_id]).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM validations ORDER BY validation_id
        """).fetchall()
    return [dict(r) for r in rows]


def get_benchmarks(conn, world_type=None):
    """Get benchmark results."""
    if world_type:
        rows = conn.execute("""
            SELECT * FROM benchmark_runs WHERE world_type = ? ORDER BY benchmark_id
        """, [world_type]).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM benchmark_runs ORDER BY benchmark_id
        """).fetchall()
    return [dict(r) for r in rows]


def get_events(conn, limit=20):
    """Get recent events."""
    rows = conn.execute("""
        SELECT * FROM events ORDER BY event_id DESC LIMIT ?
    """, [limit]).fetchall()
    return [dict(r) for r in reversed(rows)]


def count_evaluations(conn, run_id=None):
    """Count total evaluations."""
    if run_id:
        return conn.execute(
            "SELECT COUNT(*) FROM evaluations WHERE run_id = ?", [run_id]
        ).fetchone()[0]
    return conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]


def checkpoint(conn):
    """WAL checkpoint after major phases."""
    try:
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    except Exception:
        pass


def export_history_json(conn, path="history.json", run_id=None):
    """Export evaluations to history.json."""
    evals = get_all_evaluations(conn, run_id)
    export = []
    for e in evals:
        export.append({
            "evaluation_id": e["evaluation_id"],
            "step": e["step"],
            "cr": e["cr"],
            "ci": e["ci"],
            "model": e["model_id"],
            "driver": e["driver"],
            "score": e["score"],
            "max_iter": e["max_iter"],
            "is_best": bool(e["is_best"]),
            "pearson01": e["pearson01"],
            "spearman01": e["spearman01"],
            "mae01": e["mae01"],
        })
    _atomic_write_json(path, export)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _atomic_write_json(path, data):
    """Atomic write: write to .tmp then rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)
