"""V6 database layer (deliverable: history_v6.sqlite3).

Two roles:
* CHECKPOINT / CACHE  -- `worlds` stores every (generator, mechanism, seed)
  instance's cached response-operator and baseline feature vectors as JSON so a
  rerun (or the determinism re-run) does not recompute the intervention battery.
* RESULTS  -- long-format `benchmark_results` for every metric the pipeline
  produces, plus a `meta` table for protocol identity.

Idempotent: tables are cleared and repopulated. stdlib-only.
"""
import os
import json
import sqlite3
from datetime import datetime

DB_PATH = "history_v6.sqlite3"


def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS worlds (
        gen TEXT, mech TEXT, seed INTEGER, grp TEXT,
        response_json TEXT, baseline_json TEXT,
        PRIMARY KEY (gen, mech, seed));
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_name TEXT, metric_name TEXT, metric_value REAL,
        meaning TEXT, run_at TEXT);
    """)
    conn.commit()
    return conn


# ---- feature cache -------------------------------------------------------
def load_worlds(conn):
    """Return {(gen, mech, seed): (response_dict, baseline_dict)} from cache."""
    out = {}
    for gen, mech, seed, rj, bj in conn.execute(
            "SELECT gen, mech, seed, response_json, baseline_json FROM worlds"):
        out[(gen, mech, seed)] = (json.loads(rj), json.loads(bj))
    return out


def upsert_world(conn, gen, mech, seed, grp, response, baseline):
    conn.execute(
        "INSERT OR REPLACE INTO worlds (gen, mech, seed, grp,"
        " response_json, baseline_json) VALUES (?,?,?,?,?,?)",
        (gen, mech, seed, grp, json.dumps(response), json.dumps(baseline)))


# ---- results -------------------------------------------------------------
def _walk(conn, test_name, obj, meaning=None):
    c = conn.cursor()
    now = datetime.now().isoformat()
    if isinstance(obj, dict):
        m = obj.get("meaning", meaning)
        for k, v in obj.items():
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                c.execute("INSERT INTO benchmark_results"
                          " (test_name,metric_name,metric_value,meaning,run_at)"
                          " VALUES (?,?,?,?,?)", (test_name, k, float(v), m, now))
            elif isinstance(v, dict):
                _walk(conn, f"{test_name}.{k}", v, m)
            elif isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
                for i, x in enumerate(v):
                    c.execute("INSERT INTO benchmark_results"
                              " (test_name,metric_name,metric_value,meaning,run_at)"
                              " VALUES (?,?,?,?,?)",
                              (test_name, f"{k}[{i}]", float(x), m, now))


def populate_db(pipe, db_path=DB_PATH):
    conn = init_db(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM meta")
    c.execute("DELETE FROM benchmark_results")
    c.execute("DELETE FROM sqlite_sequence WHERE name='benchmark_results'")
    r = pipe.results
    for k in ("branch", "protocol_hash", "final_status", "never_emits", "base_seed"):
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(r.get(k))))
    # per-instance feature checkpoint (generator x mechanism x seed)
    c.execute("DELETE FROM worlds")
    train_gens = set((r.get("generators") or {}).get("train", []))
    for key, resp in getattr(pipe, "feat", {}).items():
        gen, mech, seed = key
        grp = "train" if gen in train_gens else "holdout"
        base = pipe.base.get(key, {})
        c.execute(
            "INSERT OR REPLACE INTO worlds (gen, mech, seed, grp,"
            " response_json, baseline_json) VALUES (?,?,?,?,?,?)",
            (gen, mech, seed, grp, json.dumps(resp), json.dumps(base)))
    for test_name, block in r.items():
        if isinstance(block, dict):
            _walk(conn, test_name, block)
    conn.commit()
    conn.close()
    print(f"[V6 DB] Saved to {db_path}")


if __name__ == "__main__":
    print("Run v6_pipeline.py to produce results; this module is imported by it.")
