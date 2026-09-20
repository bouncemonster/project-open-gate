"""V5 Database: SQLite storage for worlds, features, predictions, and benchmarks."""
import sqlite3
import json
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime


class V5Database:
    """V5 SQLite database manager."""
    
    def __init__(self, db_path: str = "history_v5.sqlite3"):
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database with V5 schema."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        
        # Create tables
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_type TEXT NOT NULL,
                seed INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                observation TEXT DEFAULT 'O1_FULL_PRECISION',
                field_hash TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(world_type, seed, observation)
            );
            
            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id INTEGER NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value REAL NOT NULL,
                FOREIGN KEY (world_id) REFERENCES worlds(id),
                UNIQUE(world_id, feature_name)
            );
            
            CREATE TABLE IF NOT EXISTS splits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id INTEGER NOT NULL,
                split_type TEXT NOT NULL,
                FOREIGN KEY (world_id) REFERENCES worlds(id),
                UNIQUE(world_id, split_type)
            );
            
            CREATE TABLE IF NOT EXISTS detectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detector_type TEXT NOT NULL,
                config_json TEXT,
                trained_at TEXT DEFAULT CURRENT_TIMESTAMP,
                frozen INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id INTEGER NOT NULL,
                detector_id INTEGER NOT NULL,
                predicted_class TEXT NOT NULL,
                confidence REAL,
                proba_json TEXT,
                FOREIGN KEY (world_id) REFERENCES worlds(id),
                FOREIGN KEY (detector_id) REFERENCES detectors(id)
            );
            
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detector_id INTEGER NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                ci_lower REAL,
                ci_upper REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (detector_id) REFERENCES detectors(id)
            );
            
            CREATE TABLE IF NOT EXISTS ablations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detector_id INTEGER NOT NULL,
                feature_set TEXT NOT NULL,
                accuracy REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (detector_id) REFERENCES detectors(id)
            );
            
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_type TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS paired_worlds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_world_id INTEGER NOT NULL,
                paired_world_id INTEGER NOT NULL,
                pair_type TEXT NOT NULL,
                FOREIGN KEY (base_world_id) REFERENCES worlds(id),
                FOREIGN KEY (paired_world_id) REFERENCES worlds(id)
            );
        """)
        self.conn.commit()
    
    def insert_world(self, world_type: str, seed: int, width: int, height: int,
                     observation: str = "O1_FULL_PRECISION",
                     field_hash: str = "") -> int:
        """Insert a world record."""
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO worlds (world_type, seed, width, height, observation, field_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (world_type, seed, width, height, observation, field_hash)
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            # Already exists, get ID
            row = self.conn.execute(
                "SELECT id FROM worlds WHERE world_type=? AND seed=? AND observation=?",
                (world_type, seed, observation)
            ).fetchone()
            return row["id"]
        return cursor.lastrowid
    
    def insert_features(self, world_id: int, features: Dict[str, float]):
        """Insert feature vector for a world."""
        for fname, fvalue in features.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO features (world_id, feature_name, feature_value) "
                "VALUES (?, ?, ?)",
                (world_id, fname, fvalue)
            )
        self.conn.commit()
    
    def get_features(self, world_id: int) -> Dict[str, float]:
        """Get feature vector for a world."""
        rows = self.conn.execute(
            "SELECT feature_name, feature_value FROM features WHERE world_id=?",
            (world_id,)
        ).fetchall()
        return {row["feature_name"]: row["feature_value"] for row in rows}
    
    def get_worlds_by_split(self, split_type: str) -> List[int]:
        """Get world IDs for a split."""
        rows = self.conn.execute(
            "SELECT world_id FROM splits WHERE split_type=?",
            (split_type,)
        ).fetchall()
        return [row["world_id"] for row in rows]
    
    def assign_split(self, world_id: int, split_type: str):
        """Assign a world to a split."""
        self.conn.execute(
            "INSERT OR REPLACE INTO splits (world_id, split_type) VALUES (?, ?)",
            (world_id, split_type)
        )
        self.conn.commit()
    
    def insert_prediction(self, world_id: int, detector_id: int,
                         predicted_class: str, confidence: float,
                         proba: Dict[str, float]):
        """Insert a prediction."""
        self.conn.execute(
            "INSERT INTO predictions (world_id, detector_id, predicted_class, confidence, proba_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (world_id, detector_id, predicted_class, confidence, json.dumps(proba))
        )
        self.conn.commit()
    
    def insert_detector(self, detector_type: str, config: Dict) -> int:
        """Insert a detector record."""
        cursor = self.conn.execute(
            "INSERT INTO detectors (detector_type, config_json) VALUES (?, ?)",
            (detector_type, json.dumps(config))
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def insert_benchmark_result(self, detector_id: int, metric_name: str,
                                metric_value: float, ci_lower: float = None,
                                ci_upper: float = None):
        """Insert a benchmark metric."""
        self.conn.execute(
            "INSERT INTO benchmark_results (detector_id, metric_name, metric_value, ci_lower, ci_upper) "
            "VALUES (?, ?, ?, ?, ?)",
            (detector_id, metric_name, metric_value, ci_lower, ci_upper)
        )
        self.conn.commit()
    
    def insert_ablation(self, detector_id: int, feature_set: str, accuracy: float):
        """Insert an ablation result."""
        self.conn.execute(
            "INSERT INTO ablations (detector_id, feature_set, accuracy) VALUES (?, ?, ?)",
            (detector_id, feature_set, accuracy)
        )
        self.conn.commit()
    
    def insert_artifact(self, artifact_type: str, artifact_path: str,
                       metadata: Dict = None):
        """Insert an artifact record."""
        self.conn.execute(
            "INSERT INTO artifacts (artifact_type, artifact_path, metadata_json) VALUES (?, ?, ?)",
            (artifact_type, artifact_path, json.dumps(metadata) if metadata else None)
        )
        self.conn.commit()
    
    def insert_paired_world(self, base_world_id: int, paired_world_id: int,
                           pair_type: str):
        """Insert a paired world relationship."""
        self.conn.execute(
            "INSERT INTO paired_worlds (base_world_id, paired_world_id, pair_type) "
            "VALUES (?, ?, ?)",
            (base_world_id, paired_world_id, pair_type)
        )
        self.conn.commit()
    
    def get_all_worlds(self) -> List[Dict]:
        """Get all worlds."""
        rows = self.conn.execute("SELECT * FROM worlds").fetchall()
        return [dict(row) for row in rows]
    
    def get_world(self, world_id: int) -> Optional[Dict]:
        """Get a single world."""
        row = self.conn.execute("SELECT * FROM worlds WHERE id=?", (world_id,)).fetchone()
        return dict(row) if row else None
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
