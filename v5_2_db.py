"""V5.2 Database layer (per spec section 60)."""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "history_v5_2.sqlite3"


def init_db(path=DB_PATH):
    """Create V5.2 database with required tables."""
    conn = sqlite3.connect(path)
    c = conn.cursor()
    
    c.executescript("""
    CREATE TABLE IF NOT EXISTS generators (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        split TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS substrates (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        class TEXT NOT NULL,
        split TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS worlds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        generator_id TEXT REFERENCES generators(id),
        substrate_id TEXT REFERENCES substrates(id),
        seed INTEGER,
        width INTEGER,
        height INTEGER,
        label TEXT,
        split TEXT,
        sub_split TEXT,
        created_at TEXT
    );
    
    CREATE TABLE IF NOT EXISTS features (
        world_id INTEGER REFERENCES worlds(id),
        feature_name TEXT,
        feature_value REAL,
        PRIMARY KEY (world_id, feature_name)
    );
    
    CREATE TABLE IF NOT EXISTS pairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        generator_id TEXT,
        seed INTEGER,
        continuous_world_id INTEGER REFERENCES worlds(id),
        computational_world_id INTEGER REFERENCES worlds(id),
        pair_type TEXT
    );
    
    CREATE TABLE IF NOT EXISTS detectors (
        id TEXT PRIMARY KEY,
        name TEXT,
        config_json TEXT,
        trained_at TEXT
    );
    
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detector_id TEXT REFERENCES detectors(id),
        world_id INTEGER REFERENCES worlds(id),
        predicted_label TEXT,
        true_label TEXT,
        score REAL,
        correct BOOLEAN
    );
    
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_name TEXT,
        metric_name TEXT,
        metric_value REAL,
        details_json TEXT,
        run_at TEXT
    );
    
    CREATE TABLE IF NOT EXISTS adversarial_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_type TEXT,
        generator_id TEXT,
        substrate_id TEXT,
        result_json TEXT,
        passed BOOLEAN,
        run_at TEXT
    );
    
    CREATE TABLE IF NOT EXISTS ablation_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        feature_set TEXT,
        balanced_accuracy REAL,
        accuracy REAL,
        details_json TEXT,
        run_at TEXT
    );
    
    CREATE TABLE IF NOT EXISTS splits (
        world_id INTEGER REFERENCES worlds(id),
        split_type TEXT,
        split_name TEXT,
        PRIMARY KEY (world_id, split_type)
    );
    """)
    conn.commit()
    return conn


def populate_db(pipeline, db_path=DB_PATH):
    """Populate database from pipeline results. Idempotent: derived tables are
    cleared first so re-population never duplicates or mixes stale runs."""
    conn = init_db(db_path)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.executescript("""
        DELETE FROM worlds; DELETE FROM features; DELETE FROM benchmark_results;
        DELETE FROM generators; DELETE FROM substrates; DELETE FROM splits;
        DELETE FROM sqlite_sequence
        WHERE name IN ('worlds','benchmark_results');
    """)
    
    # Insert generators
    for gen_id in pipeline.train_generators + pipeline.val_generators + pipeline.holdout_generators:
        split = "train" if gen_id in pipeline.train_generators else \
                "validation" if gen_id in pipeline.val_generators else "holdout"
        c.execute("INSERT OR REPLACE INTO generators VALUES (?, ?, ?, ?)",
                  (gen_id, gen_id, "mathematical", split))
    
    # Insert substrates
    for sub in ["S_CONTINUOUS", "S_UNKNOWN_CONTINUOUS"]:
        c.execute("INSERT OR REPLACE INTO substrates VALUES (?, ?, ?, ?)",
                  (sub, sub, "continuous", "train"))
    for sub in ["S_FLOAT32", "S_FLOAT16", "S_QUANT_8", "S_LATTICE"]:
        c.execute("INSERT OR REPLACE INTO substrates VALUES (?, ?, ?, ?)",
                  (sub, sub, "computational", "train"))
    for sub in ["S_QUANT_4", "S_LOOKUP", "S_HASH", "S_FINITE_STATE", "S_UNKNOWN_COMPUTATIONAL"]:
        c.execute("INSERT OR REPLACE INTO substrates VALUES (?, ?, ?, ?)",
                  (sub, sub, "computational", "holdout"))
    
    # Insert worlds
    for w in pipeline.worlds:
        c.execute(
            "INSERT INTO worlds (generator_id, substrate_id, seed, width, height, label, split, sub_split, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (w["generator"], w["substrate"], w["seed"], w["width"], w["height"],
             w["label"], w["split"], w.get("sub_split", "train"), now))
        world_id = c.lastrowid
        
        # Insert features
        for fname, fval in w["features"].items():
            c.execute("INSERT OR REPLACE INTO features VALUES (?, ?, ?)",
                      (world_id, fname, fval))
    
    # Insert benchmark results
    for test_name, metrics in pipeline.results.items():
        if isinstance(metrics, dict):
            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)):
                    c.execute("INSERT INTO benchmark_results (test_name, metric_name, metric_value, run_at) VALUES (?, ?, ?, ?)",
                              (test_name, metric_name, value, now))
    
    conn.commit()
    conn.close()
    print(f"[V5.2 DB] Saved to {db_path}")


if __name__ == "__main__":
    # Load cached worlds; take results from the AUTHORITATIVE results JSON
    # (audit fix: the pkl cache may hold stale pre-audit results).
    import pickle
    if os.path.exists("v5_2_pipeline_cache.pkl"):
        with open("v5_2_pipeline_cache.pkl", "rb") as f:
            data = pickle.load(f)
        from v5_2_pipeline import V52Pipeline
        p = V52Pipeline.__new__(V52Pipeline)
        p.worlds = data["worlds"]
        results_json = os.path.join("v5_2_artifacts", "benchmark", "v5_2_results.json")
        if os.path.exists(results_json):
            with open(results_json, encoding="utf-8") as f:
                p.results = json.load(f)
        else:
            p.results = data["results"]
        p.train_generators = ["G01_analytic_smooth", "G02_gaussian_correlated",
                              "G03_analytic_fractal", "G04_wave_eigenmode", "G05_chaotic_map"]
        p.val_generators = ["G06_nonlinear_dyn", "G07_reaction_diffusion"]
        p.holdout_generators = ["G08_procedural_noise", "G09_coupled_oscillator",
                                "G10_cosmological_like"]
        populate_db(p)
    else:
        print("Run pipeline first (v5_2_extended.py) to create cache.")
