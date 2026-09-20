"""V5.3 Database layer (spec §15: reuse SQLite infrastructure).

Reuses the V5.2 schema shape (generators/substrates/worlds/features/
benchmark_results) but stores the NATIVE substrate taxonomy and pairwise
results. Idempotent: derived tables cleared before repopulation.
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "history_v5_3.sqlite3"


def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS generators (
        id TEXT PRIMARY KEY, name TEXT, type TEXT, split TEXT);
    CREATE TABLE IF NOT EXISTS substrates (
        id TEXT PRIMARY KEY, name TEXT, class TEXT, split TEXT, impl TEXT);
    CREATE TABLE IF NOT EXISTS worlds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        generator_id TEXT, substrate_id TEXT, seed INTEGER,
        width INTEGER, height INTEGER, label TEXT, split TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS features (
        world_id INTEGER, feature_name TEXT, feature_value REAL,
        feature_family TEXT,
        PRIMARY KEY (world_id, feature_name));
    CREATE TABLE IF NOT EXISTS pairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        generator_id TEXT, seed INTEGER,
        cont_world_id INTEGER, comp_world_id INTEGER, pair_type TEXT);
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_name TEXT, metric_name TEXT, metric_value REAL,
        track TEXT, run_at TEXT);
    """)
    conn.commit()
    return conn


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k != "field"}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def populate_db(pipeline, db_path=DB_PATH):
    from v5_3_features import family_of
    from v5_3_core import (SUBSTRATES_COMPUTATIONAL, TRAIN_SUBSTRATES,
                           HOLDOUT_SUBSTRATES, substrate_label)
    conn = init_db(db_path)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.executescript("""
        DELETE FROM worlds; DELETE FROM features; DELETE FROM benchmark_results;
        DELETE FROM generators; DELETE FROM substrates;
        DELETE FROM sqlite_sequence WHERE name IN ('worlds','benchmark_results','pairs');
    """)

    gens = sorted({w["generator"] for w in pipeline.worlds})
    for gen in gens:
        split = next((w["split"] for w in pipeline.worlds if w["generator"] == gen), "train")
        c.execute("INSERT OR REPLACE INTO generators VALUES (?,?,?,?)", (gen, gen, "recurrence", split))
    from v5_3_core import SNAPSHOTS, TRAIN_GENERATORS
    impl = {
        "S64": "float64 reference", "S32": "IEEE single per-step",
        "S16": "IEEE half per-step", "S_Q15": "fixed-point Q15 recurrence",
        "S_FSM": "13-state lattice snap", "S_MOD": "Z_100003 residue recurrence",
        "S_HASH_NATIVE": "SplitMix64 in-recurrence term", "S_UNKNOWN": "mantissa truncation (novel)",
    }
    for sub in SNAPSHOTS:
        cls = substrate_label(sub)
        ssplit = "train" if sub in TRAIN_SUBSTRATES else ("holdout" if sub in HOLDOUT_SUBSTRATES else "reference")
        c.execute("INSERT OR REPLACE INTO substrates VALUES (?,?,?,?,?)", (sub, sub, cls, ssplit, impl.get(sub, "")))

    for w in pipeline.worlds:
        c.execute("INSERT INTO worlds (generator_id,substrate_id,seed,width,height,label,split,created_at)"
                  " VALUES (?,?,?,?,?,?,?,?)",
                  (w["generator"], w["substrate"], w["seed"], w.get("width", 60),
                   w.get("height", 30), w["label"], w["split"], now))
        wid = c.lastrowid
        for fname, fval in w["featsB"].items():
            if isinstance(fval, (int, float)):
                c.execute("INSERT OR REPLACE INTO features VALUES (?,?,?,?)",
                          (wid, fname, float(fval), family_of(fname)))

    def _walk(test_name, obj, track=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    c.execute("INSERT INTO benchmark_results (test_name,metric_name,metric_value,track,run_at)"
                              " VALUES (?,?,?,?,?)", (test_name, k, float(v), track, now))
                elif isinstance(v, dict):
                    _walk(f"{test_name}.{k}", v, track or (k if k.startswith("track_") else track))
                elif isinstance(v, list):
                    pass

    for test_name, metrics in pipeline.results.items():
        _walk(test_name, metrics)

    conn.commit()
    conn.close()
    print(f"[V5.3 DB] Saved to {db_path}")


if __name__ == "__main__":
    import pickle
    if os.path.exists("v5_3_pipeline_cache.pkl"):
        with open("v5_3_pipeline_cache.pkl", "rb") as f:
            data = pickle.load(f)
        from v5_3_pipeline import V53Pipeline
        p = V53Pipeline()
        p.worlds = data["worlds"]
        results_json = "v5_3_results.json"
        if os.path.exists(results_json):
            with open(results_json, encoding="utf-8") as f:
                p.results = json.load(f)
        else:
            p.results = data["results"]
        populate_db(p)
    else:
        print("Run v5_3_pipeline first to create the cache.")
