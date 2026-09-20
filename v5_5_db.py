"""V5.5 Database layer (spec §7 deliverable: history_v5_5.sqlite3).

V5.5 Branch C reuses the cached V5.3 worlds/features and detector; it does NOT
generate a new world set, so this DB records the *audit* itself: the protocol
metadata and every test/metric produced, in a long-format table for querying.
Idempotent: cleared before repopulation.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = "history_v5_5.sqlite3"


def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_name TEXT, metric_name TEXT, metric_value REAL,
        meaning TEXT, run_at TEXT);
    """)
    conn.commit()
    return conn


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
            elif isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
                for i, x in enumerate(v):
                    c.execute("INSERT INTO benchmark_results"
                              " (test_name,metric_name,metric_value,meaning,run_at)"
                              " VALUES (?,?,?,?,?)",
                              (test_name, f"{k}[{i}]", float(x), m, now))


def populate_db(audit, db_path=DB_PATH):
    conn = init_db(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM meta")
    c.execute("DELETE FROM benchmark_results")
    c.execute("DELETE FROM sqlite_sequence WHERE name='benchmark_results'")
    r = audit.results
    for k in ("branch", "protocol_hash", "final_status", "never_emits"):
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(r.get(k))))
    c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
              ("base_seed", str(r.get("base_seed"))))
    c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
              ("reused_source", "V5.3 cached worlds/features/detector"))
    for test_name in ("positive_replication", "artifact_null",
                      "classfree_identical_null", "permutation_null",
                      "status_checks"):
        _walk(conn, test_name, r.get(test_name, {}))
    conn.commit()
    conn.close()
    print(f"[V5.5 DB] Saved to {db_path}")


if __name__ == "__main__":
    import json
    print("Run v5_5_pipeline.py to produce results; this module is imported by it.")
