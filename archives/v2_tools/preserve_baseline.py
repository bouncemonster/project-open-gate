"""Preserve V1 evidence once, without importing or modifying V1 application code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_new_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def git_result(root, *args):
    try:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=15)
        return {"returncode": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def verify(snapshot):
    manifest = json.loads((snapshot / "snapshot_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        copied = snapshot / item["path"]
        if not copied.is_file() or digest(copied) != item["sha256"]:
            raise RuntimeError(f"Snapshot verification failed: {copied}")
    print(f"Verified {len(manifest['files'])} baseline files; no V1 files modified.")
    return manifest


def preserve(root, spec=None):
    root = root.resolve()
    snapshot = root / "archives" / "v1_baseline"
    if snapshot.exists():
        verify(snapshot)
        return
    files = sorted((p for p in root.iterdir() if p.is_file()), key=lambda p: p.name)
    for name in ("best", "validation", "benchmark", "tests"):
        directory = root / name
        if directory.exists():
            files.extend(sorted(p for p in directory.rglob("*") if p.is_file()))
    for path in files:
        if path.is_symlink():
            raise RuntimeError(f"Refusing unverified symlink: {path}")
    snapshot.mkdir(parents=True, exist_ok=False)
    for name in ("best", "validation", "benchmark"):
        (snapshot / name).mkdir()
    entries = []
    for src in files:
        rel = src.relative_to(root)
        before = digest(src)
        dst = snapshot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if digest(dst) != before or digest(src) != before:
            raise RuntimeError(f"Concurrent modification during snapshot: {rel}")
        entries.append({"path": rel.as_posix(), "bytes": src.stat().st_size,
                        "sha256": before})
    database = snapshot / "history.sqlite3"
    wal = snapshot / "history.sqlite3-wal"
    db_details = {}
    if database.exists():
        # The raw database and sidecars remain byte-exact. For a live WAL,
        # consolidate a separate copy, never checkpoint the V1 database.
        query_database = database
        if wal.exists() and wal.stat().st_size:
            staging = snapshot / "database_working_copy"
            staging.mkdir()
            for src in snapshot.glob("history.sqlite3*"):
                if src.is_file():
                    shutil.copy2(src, staging / src.name)
            source = sqlite3.connect(str(staging / "history.sqlite3"))
            query_database = snapshot / "consistent_history.sqlite3"
            destination = sqlite3.connect(str(query_database))
            source.backup(destination)
            destination.close()
            source.close()
        uri = query_database.as_uri() + "?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        db_details = {"query_database": query_database.name,
                      "integrity_check": [row[0] for row in conn.execute("PRAGMA integrity_check")],
                      "foreign_key_check": conn.execute("PRAGMA foreign_key_check").fetchall(),
                      "tables": [row[0] for row in conn.execute(
                          "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]}
        conn.close()
        if db_details["integrity_check"] != ["ok"]:
            raise RuntimeError("Preserved database failed integrity check; do not modify V1")
    manifest = {"identity": "V1_BASELINE", "created_at": datetime.now(timezone.utc).isoformat(),
                "source_directory": str(root), "preservation": "byte-exact; original data untouched",
                "files": entries, "database": db_details,
                "git_status": git_result(root, "status", "--short"),
                "git_head": git_result(root, "rev-parse", "HEAD")}
    write_new_json(snapshot / "snapshot_manifest.json", manifest)
    verify(snapshot)
    if spec:
        audit = root / "archives" / "v2_audit"
        audit.mkdir(exist_ok=True)
        target = audit / "input_specification.txt"
        if target.exists():
            raise RuntimeError("Refusing to overwrite a preserved specification")
        shutil.copy2(spec, target)
        write_new_json(audit / "specification_receipt.json",
                       {"source": str(spec), "sha256": digest(target)})
    print(f"Baseline: {snapshot}")
    print(json.dumps(db_details, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(args.root / "archives" / "v1_baseline")
    else:
        preserve(args.root, args.spec)
