"""
Proof of Simulation V4 — dedicated evidence store (history_v4.sqlite3).

V4 is isolated from V1/V2/V3: its own file name, SQLite application_id and
schema version.  Every reported number is persisted here so report generation
can verify it against the database.
"""
import json
import sqlite3
import time

V4_MODEL = "V4_INTERIOR_CONTRAST"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


V4_SCHEMA = """
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
    model_id TEXT NOT NULL,
    driver TEXT NOT NULL, cr REAL NOT NULL, ci REAL NOT NULL,
    alpha REAL NOT NULL, degree INTEGER NOT NULL, channel INTEGER NOT NULL,
    max_iter INTEGER NOT NULL CHECK(max_iter BETWEEN 1 AND 20000),
    seed INTEGER NOT NULL, driver_hash TEXT NOT NULL,
    score REAL, status TEXT NOT NULL,
    params_json TEXT NOT NULL, result_json TEXT NOT NULL,
    UNIQUE(run_id, step, candidate_id),
    FOREIGN KEY(run_id, step) REFERENCES checkpoints(run_id, step)
);
CREATE INDEX evaluations_run_score ON evaluations(run_id, score DESC);
CREATE TABLE results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL, key TEXT NOT NULL, score REAL,
    value_json TEXT NOT NULL, timestamp TEXT NOT NULL,
    UNIQUE(phase, key)
);
CREATE TABLE counters (
    name TEXT PRIMARY KEY NOT NULL, value INTEGER NOT NULL
);
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL, event_type TEXT NOT NULL,
    data_json TEXT NOT NULL, timestamp TEXT NOT NULL
);
"""


class V4Store:
    APPLICATION_ID = 0x50535634  # 'PSV4'
    SCHEMA_VERSION = 4

    def __init__(self, path, protocol_hash, source_hash, binary_hash):
        from pathlib import Path
        path = Path(path).absolute()
        if path.is_dir():
            path /= "history_v4.sqlite3"
        resolved = path.resolve()
        if (path.name.lower() != "history_v4.sqlite3"
                or resolved.name.lower() != "history_v4.sqlite3"
                or "archives" in (p.lower() for p in resolved.parts)):
            raise ValueError(
                "V4 requires dedicated history_v4.sqlite3 outside archives")
        self.path = str(path)
        self.protocol_hash = protocol_hash
        self.source_hash = source_hash
        self.binary_hash = binary_hash
        if path.exists() and path.stat().st_size:
            probe = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                self._check_identity(probe)
            finally:
                probe.close()
        self.conn = sqlite3.connect(self.path, timeout=30,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = FULL")
            identity = self.conn.execute(
                "PRAGMA application_id").fetchone()[0]
            tables = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if not identity and not tables:
                for statement in V4_SCHEMA.split(";"):
                    if statement.strip():
                        self.conn.execute(statement)
                self.conn.execute(
                    f"PRAGMA application_id = {self.APPLICATION_ID}")
                self.conn.execute(
                    f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            else:
                self._check_identity(self.conn)
            self.integrity()
        except BaseException:
            self.conn.rollback()
            self.conn.close()
            raise

    def _check_identity(self, conn):
        identity = conn.execute(
            "PRAGMA application_id").fetchone()[0]
        version = conn.execute(
            "PRAGMA user_version").fetchone()[0]
        if (identity, version) != (self.APPLICATION_ID, self.SCHEMA_VERSION):
            raise ValueError(
                "Refusing legacy or incompatible database; no migration")

    def integrity(self):
        status = self.conn.execute(
            "PRAGMA integrity_check").fetchone()[0]
        fk = self.conn.execute(
            "PRAGMA foreign_key_check").fetchall()
        if status != "ok" or fk:
            raise RuntimeError(
                f"V4 database integrity failure: {status} {fk}")
        return status

    def create_run(self, run_id, config):
        serialized = _json(config)
        with self.conn:
            exists = self.conn.execute(
                "SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if exists:
                row = self.conn.execute(
                    "SELECT config_json FROM runs WHERE run_id=?",
                    (run_id,)).fetchone()
                if row[0] != serialized:
                    raise ValueError(
                        f"Incompatible V4 resume: config differs for {run_id}")
            else:
                self.conn.execute(
                    "INSERT INTO runs(run_id,protocol_hash,source_hash,"
                    "binary_hash,config_json,started_at) VALUES(?,?,?,?,?,?)",
                    (run_id, self.protocol_hash, self.source_hash,
                     self.binary_hash, serialized, _now()))

    def get_state(self, run_id):
        with self.conn:
            row = self.conn.execute(
                "SELECT state_json FROM checkpoints WHERE run_id=? "
                "ORDER BY step DESC LIMIT 1", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def commit_step(self, run_id, step, evaluations, state):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO checkpoints(run_id,step,state_json) "
                "VALUES(?,?,?)", (run_id, step, _json(state)))
            for cand in evaluations:
                result = cand.get("result", {})
                metrics = result.get("metrics", result)
                self.conn.execute(
                    "INSERT OR REPLACE INTO evaluations(run_id,step,"
                    "candidate_id,role,target,width,height,model_id,driver,"
                    "cr,ci,alpha,degree,channel,max_iter,seed,driver_hash,"
                    "score,status,params_json,result_json) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, step, int(cand["candidate_id"]),
                     cand.get("role", "PRIMARY"),
                     cand.get("target", "TARGET_A"),
                     int(cand.get("width", 60)),
                     int(cand.get("height", 30)),
                     cand.get("model_id", V4_MODEL), cand["driver"],
                     float(cand["cr"]), float(cand["ci"]),
                     float(cand.get("alpha", 1.0)),
                     int(cand.get("degree", 2)),
                     int(cand.get("channel", 0)),
                     int(cand.get("max_iter", 200)),
                     int(cand.get("seed", 7331)),
                     cand.get("driver_hash", ""),
                     metrics.get("score"),
                     cand.get("status", "OK"),
                     _json({k: v for k, v in cand.items()
                            if k not in ("result", "status")}),
                     _json(result)))

    def finish_run(self, run_id, status="FINISHED"):
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET status=?, finished_at=? WHERE run_id=?",
                (status, _now(), run_id))

    def run_rows(self, run_id):
        with self.conn:
            rows = self.conn.execute(
                "SELECT * FROM evaluations WHERE run_id=? "
                "ORDER BY step, candidate_id", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def best_of(self, run_id):
        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM evaluations WHERE run_id=? AND status='OK' "
                "AND score IS NOT NULL ORDER BY score DESC LIMIT 1",
                (run_id,)).fetchone()
        return dict(row) if row else None

    def count_by_role(self):
        with self.conn:
            rows = self.conn.execute(
                "SELECT role, COUNT(*) c FROM evaluations GROUP BY role"
            ).fetchall()
        return {r["role"]: r["c"] for r in rows}

    def total_evaluations(self):
        with self.conn:
            return self.conn.execute(
                "SELECT COUNT(*) FROM evaluations").fetchone()[0]

    def record(self, phase, key, value, score=None):
        self.integrity()
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO results(phase,key,score,value_json,"
                "timestamp) VALUES(?,?,?,?,?)",
                (phase, key, score, _json(value), _now()))

    def get(self, phase, key):
        with self.conn:
            row = self.conn.execute(
                "SELECT value_json FROM results WHERE phase=? AND key=?",
                (phase, key)).fetchone()
        return json.loads(row[0]) if row else None

    def all_results(self, phase=None):
        with self.conn:
            sql = "SELECT phase,key,score,value_json FROM results"
            args = ()
            if phase:
                sql += " WHERE phase=?"
                args = (phase,)
            out = {}
            for r in self.conn.execute(sql, args).fetchall():
                out[f"{r['phase']}:{r['key']}"] = {
                    "phase": r["phase"], "key": r["key"],
                    "score": r["score"],
                    "value": json.loads(r["value_json"])}
        return out

    def set_counter(self, name, value):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO counters(name,value) VALUES(?,?)",
                (name, value))

    def inc_counter(self, name, delta):
        with self.conn:
            self.conn.execute(
                "INSERT INTO counters(name,value) VALUES(?,?) "
                "ON CONFLICT(name) DO UPDATE SET value = value + ?",
                (name, delta, delta))

    def counters(self):
        with self.conn:
            return {r["name"]: r["value"]
                    for r in self.conn.execute(
                        "SELECT name,value FROM counters").fetchall()}

    def event(self, run_id, event_type, data=None):
        with self.conn:
            self.conn.execute(
                "INSERT INTO events(run_id,event_type,data_json,timestamp) "
                "VALUES(?,?,?,?)",
                (run_id, event_type, _json(data or {}), _now()))
