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


# V2 is deliberately isolated from the legacy connection helpers and schema.
V2_MODEL = "V2_EXPANDED_DOMAIN"
V2_DRIVERS = (
    "V0_NONE", "V1_INV_PI", "V2_SMOOTH", "V3_CENTERED_INV_PI",
    "V4_PRIME_RESIDUAL", "V5_SHUFFLED", "V6_REVERSED", "V7_IMAGINARY",
    "V8_PHASE_RANDOMIZED", "V9_PRIME_EVENT", "V10_PRIME_RESIDUAL",
    "V11_MATCHED_EVENT", "V12_SHIFTED_EVENT", "V13_GAP_MATCHED",
    "S1_ANALYTIC", "S2_DATA_SMOOTHED",
)
V2_ALIASES = dict(zip(
    ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9",
     "V10", "V11", "V12", "V13", "S1", "S2"), V2_DRIVERS))
V2_ALIASES["NONE"] = "V0_NONE"


def v2_driver(driver):
    driver = V2_ALIASES.get(driver, driver)
    if driver not in V2_DRIVERS:
        raise ValueError(f"Unknown V2 driver: {driver!r}")
    return driver


def _v2_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _v2_int(value, name, lo=0, hi=2**63 - 1):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer in [{lo}, {hi}]")
    return value


def _v2_number(value, name):
    import math
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _v2_text(value, name):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{name} must be a nonempty string without NUL")
    return value


V2_SCHEMA = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    protocol_hash TEXT NOT NULL, source_hash TEXT NOT NULL,
    binary_hash TEXT NOT NULL, config_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE checkpoints (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    step INTEGER NOT NULL CHECK(step >= 0), state_json TEXT NOT NULL,
    PRIMARY KEY(run_id, step)
);
CREATE TABLE evaluations (
    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    step INTEGER NOT NULL CHECK(step >= 0),
    candidate_id INTEGER NOT NULL CHECK(candidate_id >= 0),
    role TEXT NOT NULL, target TEXT NOT NULL,
    width INTEGER NOT NULL CHECK(width BETWEEN 2 AND 512),
    height INTEGER NOT NULL CHECK(height BETWEEN 2 AND 512),
    model_id TEXT NOT NULL CHECK(model_id = 'V2_EXPANDED_DOMAIN'),
    driver TEXT NOT NULL, cr REAL NOT NULL, ci REAL NOT NULL,
    alpha REAL NOT NULL, degree INTEGER NOT NULL CHECK(degree IN (2,3)),
    channel INTEGER NOT NULL CHECK(channel IN (0,1)),
    max_iter INTEGER NOT NULL CHECK(max_iter BETWEEN 1 AND 20000),
    seed TEXT NOT NULL, score REAL, status TEXT NOT NULL,
    params_json TEXT NOT NULL, result_json TEXT NOT NULL,
    UNIQUE(run_id, step, candidate_id),
    FOREIGN KEY(run_id, step) REFERENCES checkpoints(run_id, step)
);
CREATE INDEX evaluations_run_score ON evaluations(run_id, score DESC);
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    event_type TEXT NOT NULL, data_json TEXT NOT NULL, timestamp TEXT NOT NULL
);
"""


class V2Store:
    """Dedicated V2 evidence with append-only steps and atomic checkpoints.

    A directory path selects history_v2.sqlite3. An explicit file path must
    have that name. Existing non-V2 databases are inspected read-only first.
    """

    APPLICATION_ID = 0x50535632
    SCHEMA_VERSION = 2

    def __init__(self, path, protocol_hash, source_hash, binary_hash):
        from pathlib import Path
        path = Path(path).absolute()
        if path.is_dir():
            path /= "history_v2.sqlite3"
        resolved = path.resolve()
        if (path.name.lower() != "history_v2.sqlite3"
                or resolved.name.lower() != "history_v2.sqlite3"
                or "archives" in (p.lower() for p in resolved.parts)):
            raise ValueError("V2 requires dedicated history_v2.sqlite3 outside archives")
        self.path = str(path)
        self.protocol_hash = _v2_text(protocol_hash, "protocol_hash")
        self.source_hash = _v2_text(source_hash, "source_hash")
        self.binary_hash = _v2_text(binary_hash, "binary_hash")
        if path.exists() and path.stat().st_size:
            probe = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                self._check_identity(probe)
            finally:
                probe.close()
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA foreign_keys = ON")
            if self.conn.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
                raise RuntimeError("V2 requires SQLite WAL mode")
            self.conn.execute("PRAGMA synchronous = FULL")
            # The write lock also serializes two first-time openers.
            self.conn.execute("BEGIN IMMEDIATE")
            identity = self.conn.execute("PRAGMA application_id").fetchone()[0]
            tables = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not identity and not tables:
                for statement in V2_SCHEMA.split(";"):
                    if statement.strip():
                        self.conn.execute(statement)
                self.conn.execute(f"PRAGMA application_id = {self.APPLICATION_ID}")
                self.conn.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            else:
                self._check_identity(self.conn)
            self.conn.commit()
            self.integrity()
        except BaseException:
            self.conn.rollback()
            self.conn.close()
            raise

    def _check_identity(self, conn):
        identity = conn.execute("PRAGMA application_id").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if (identity, version) != (self.APPLICATION_ID, self.SCHEMA_VERSION):
            raise ValueError("Refusing legacy or incompatible database; no migration is allowed")

    def _run(self, run_id):
        row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise sqlite3.IntegrityError(f"Unknown V2 run: {run_id}")
        for key in ("protocol_hash", "source_hash", "binary_hash"):
            if row[key] != getattr(self, key):
                raise ValueError(f"Incompatible V2 resume: {key} differs for {run_id}")
        return row

    def create_run(self, run_id, config):
        _v2_text(run_id, "run_id")
        if not isinstance(config, dict):
            raise ValueError("Run config must be a dict")
        serialized = _v2_json(config)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            exists = self.conn.execute(
                "SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if exists:
                if self._run(run_id)["config_json"] != serialized:
                    raise ValueError(f"Incompatible V2 resume: config differs for {run_id}")
            else:
                self.conn.execute(
                    "INSERT INTO runs(run_id,protocol_hash,source_hash,binary_hash,"
                    "config_json,started_at) VALUES(?,?,?,?,?,?)",
                    (run_id, self.protocol_hash, self.source_hash, self.binary_hash,
                     serialized, _now()))

    def get_state(self, run_id):
        self._run(run_id)
        row = self.conn.execute(
            "SELECT state_json FROM checkpoints WHERE run_id=? ORDER BY step DESC LIMIT 1",
            (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def _evaluation(self, candidate, config, run_id, step):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("result"), dict):
            raise ValueError("Each evaluation requires a candidate dict and result dict")
        for key, value in (("run_id", run_id), ("step", step)):
            if key in candidate and candidate[key] != value:
                raise ValueError(f"Contradictory evaluation {key}")
        params = {k: v for k, v in candidate.items()
                  if k not in ("result", "status", "run_id", "step")}
        if "evaluation_id" in params:
            raise ValueError("evaluation_id is assigned by SQLite")
        _v2_int(params.get("candidate_id"), "candidate_id")
        for key in ("cr", "ci", "alpha"):
            _v2_number(params.get(key), key)
        params["driver"] = v2_driver(params.get("driver"))
        _v2_int(params.get("degree"), "degree", 2, 3)
        _v2_int(params.get("channel"), "channel", 0, 1)
        _v2_int(params.get("max_iter"), "max_iter", 1, 20000)
        _v2_int(params.get("seed"), "seed", 0, 2**64 - 1)
        if params["driver"] == "V7_IMAGINARY":
            params["channel"] = 1
        for key, default in (("role", "PRIMARY"), ("target", "TARGET_A"),
                             ("width", 60), ("height", 30), ("model_id", V2_MODEL)):
            params.setdefault(key, config.get(key, default))
        if params["model_id"] != V2_MODEL:
            raise ValueError("All V2 evaluations require V2_EXPANDED_DOMAIN")
        for key in ("width", "height"):
            _v2_int(params[key], key, 2, 512)
        for key in ("role", "target"):
            _v2_text(params[key], key)
        result = candidate["result"]
        if "candidate_id" in result and result["candidate_id"] != params["candidate_id"]:
            raise ValueError("Result candidate_id does not match its parameters")
        status = candidate.get("status", "OK")
        if status not in ("OK", "FAILED", "ERROR", "TIMEOUT"):
            raise ValueError(f"Unknown evaluation status: {status}")
        metrics = result.get("metrics", result)
        if not isinstance(metrics, dict):
            raise ValueError("Result metrics must be a dict")
        score = metrics.get("score")
        if score is not None:
            _v2_number(score, "score")
            if not 0 <= score <= 1:
                raise ValueError("score must be in [0,1]")
        if status == "OK" and (score is None or result.get("error_code", 0) != 0):
            raise ValueError("Successful evaluations require a score and no kernel error")
        return params, result, status, score

    def commit_step(self, run_id, step, evaluations, state):
        _v2_int(step, "step")
        if not isinstance(state, dict) or not isinstance(evaluations, list):
            raise ValueError("commit_step requires a list of evaluations and a state dict")
        state_json = _v2_json(state)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            run = self._run(run_id)
            if run["status"] != "RUNNING":
                raise ValueError("Cannot append evaluations to a finished run")
            last = self.conn.execute(
                "SELECT MAX(step) FROM checkpoints WHERE run_id=?", (run_id,)).fetchone()[0]
            if last is not None and step <= last:
                raise sqlite3.IntegrityError("Duplicate or out-of-order V2 step commit")
            self.conn.execute("INSERT INTO checkpoints VALUES(?,?,?)",
                              (run_id, step, state_json))
            config = json.loads(run["config_json"])
            for candidate in evaluations:
                params, result, status, score = self._evaluation(candidate, config, run_id, step)
                keys = ("candidate_id", "role", "target", "width", "height", "model_id",
                        "driver", "cr", "ci", "alpha", "degree", "channel", "max_iter")
                self.conn.execute(
                    "INSERT INTO evaluations(run_id,step,candidate_id,role,target,width,"
                    "height,model_id,driver,cr,ci,alpha,degree,channel,max_iter,seed,score,"
                    "status,params_json,result_json) VALUES(" + ",".join(["?"] * 20) + ")",
                    (run_id, step, *(params[k] for k in keys), str(params["seed"]),
                     score, status, _v2_json(params), _v2_json(result)))
            rows = self.conn.execute(
                "SELECT e.*,r.protocol_hash,r.source_hash,r.binary_hash FROM evaluations e "
                "JOIN runs r USING(run_id) WHERE e.run_id=? AND step=? ORDER BY evaluation_id",
                (run_id, step)).fetchall()
        return [self._flat(row) for row in rows]

    @staticmethod
    def _flat(row):
        data = dict(row)
        params = json.loads(data["params_json"])
        result = json.loads(data["result_json"])
        flat = dict(result)
        flat.update(result.get("metrics", {}))
        flat.update(params)
        flat.update(data)
        flat["seed"] = params["seed"]
        flat["params"] = params
        flat["result"] = result
        return flat

    def run_rows(self, run_id):
        self._run(run_id)
        rows = self.conn.execute(
            "SELECT e.*,r.protocol_hash,r.source_hash,r.binary_hash FROM evaluations e "
            "JOIN runs r USING(run_id) WHERE e.run_id=? ORDER BY step,evaluation_id",
            (run_id,)).fetchall()
        return [self._flat(row) for row in rows]

    def runs(self):
        result = []
        for row in self.conn.execute("SELECT * FROM runs ORDER BY run_id"):
            data = dict(row)
            config = json.loads(data["config_json"])
            result.append({**config, **data, "config": config})
        return result

    def finish_run(self, run_id, status="FINISHED"):
        if status not in ("FINISHED", "FAILED", "CANCELLED"):
            raise ValueError("Invalid terminal run status")
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self._run(run_id)
            if row["status"] == status:
                return
            if row["status"] != "RUNNING":
                raise ValueError("Cannot change an existing terminal status")
            self.conn.execute("UPDATE runs SET status=?,finished_at=? WHERE run_id=?",
                              (status, _now(), run_id))

    def integrity(self):
        checks = [row[0] for row in self.conn.execute("PRAGMA integrity_check")]
        foreign_keys = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        if checks != ["ok"] or foreign_keys:
            raise sqlite3.DatabaseError(f"V2 integrity failure: {checks}; FK={foreign_keys}")

    def event(self, run_id, type, data):
        _v2_text(type, "event type")
        with self.conn:
            self._run(run_id)
            self.conn.execute(
                "INSERT INTO events(run_id,event_type,data_json,timestamp) VALUES(?,?,?,?)",
                (run_id, type, _v2_json(data), _now()))

    def close(self):
        self.conn.close()
