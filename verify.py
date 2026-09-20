#!/usr/bin/env python
"""Proof of Simulation — consolidated repository self-check.

One command that answers: "is the whole project internally consistent and
operationally ready right now?" Replaces the ad-hoc diagnostics used during
development. stdlib-only, read-only (never mutates a deliverable or database).

    python verify.py            # full check (slow on large closed-branch DBs)
    python verify.py --quick     # quick_check instead of full integrity_check
    python verify.py --skip-db   # skip sqlite checks entirely (fastest)

Exit code 0 = all gates pass, 1 = at least one FAIL.
"""
import argparse
import ast
import glob
import hashlib
import os
import py_compile
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

results = []  # (ok: bool, label: str, detail: str)


def check(ok, label, detail=""):
    results.append((bool(ok), label, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------- source health
def check_syntax(modules):
    bad = []
    for m in modules:
        try:
            py_compile.compile(m + ".py", doraise=True)
        except Exception as e:
            bad.append(f"{m}.py: {e}")
    check(not bad, "syntax: all top-level modules compile",
          "; ".join(bad[:3]) if bad else f"{len(modules)} modules")


def check_local_imports(modules):
    local = set(modules)
    std = set(getattr(sys, "stdlib_module_names", set()))
    missing = []
    for m in modules:
        try:
            tree = ast.parse(open(m + ".py", encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for d in mods:
                if d in local or d in std:
                    continue
                if re.match(r"(v\d|kernel_)", d) and not (
                        os.path.exists(d + ".py") or os.path.exists(d)):
                    missing.append(f"{m}.py->{d}")
    check(not missing, "imports: all local dependencies resolve",
          ", ".join(sorted(set(missing))) if missing else "0 unresolved")


# --------------------------------------------------------------- deliverables
def check_reports_exist():
    expected = ["report.md", "report_v2.md", "report_v3.md", "report_v4.md",
                "report_v5.md", "report_v5_1.md", "report_v5_2.md",
                "report_v5_3.md", "report_v5_5.md", "report_v6.md", "README.md"]
    miss = [f for f in expected if not os.path.exists(f)]
    check(not miss, "reports: full V1-V6 lineage present",
          ", ".join(miss) if miss else f"{len(expected)} reports")


def check_v6_deliverables():
    need = ["v6_results.json", "v6_protocol.json", "report_v6.md",
            "history_v6.sqlite3", "v6_artifacts"]
    miss = [f for f in need if not os.path.exists(f)]
    check(not miss, "V6: §11 deliverables present", ", ".join(miss) if miss else "5/5")


def check_v6_reproducibility():
    """Recompute the frozen V6 protocol hash from source and confirm the stored
    deliverable and the report agree — without re-running the pipeline."""
    src = ["v6_core.py", "v6_pipeline.py", "v6_db.py", "v5_detector.py"]
    blob = ""
    for f in src:
        if os.path.exists(f):
            blob += open(f, "rb").read().decode("utf-8", errors="ignore")
    h = hashlib.sha256(blob.encode()).hexdigest()[:16]

    stored = None
    try:
        import json
        stored = json.load(open("v6_protocol.json", encoding="utf-8")).get("protocol_hash")
    except Exception:
        pass
    check(stored == h, "V6: stored protocol_hash matches source",
          f"{h}" if stored == h else f"source {h} != stored {stored}")

    md = open("report_v6.md", encoding="utf-8").read() if os.path.exists("report_v6.md") else ""
    m = re.search(r"Protocol hash:\*\* `([0-9a-f]{16})`", md)
    report_hash = m.group(1) if m else None
    check(report_hash == h, "V6: report_v6.md hash matches source",
          f"{report_hash}" if report_hash == h else f"report {report_hash} != source {h}")

    # status consistency: report status line vs stored results final_status
    try:
        status = json.load(open("v6_results.json", encoding="utf-8")).get("final_status")
    except Exception:
        status = None
    check(status is not None and status in md,
          "V6: final_status appears in report", str(status))


# -------------------------------------------------------------------- database
def _open_ro(path):
    return sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)


def check_dbs(quick):
    pragma = "quick_check" if quick else "integrity_check"
    for db in sorted(glob.glob("history*.sqlite3")):
        try:
            con = _open_ro(db)
            try:
                verdict = con.execute(f"PRAGMA {pragma}").fetchone()[0]
                ntab = con.execute(
                    "select count(*) from sqlite_master where type='table'"
                ).fetchone()[0]
            finally:
                con.close()
            check(verdict == "ok", f"db: {db}", f"tables={ntab} {pragma}={verdict}")
        except Exception as e:
            check(False, f"db: {db}", str(e))


# -------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="repository self-check")
    ap.add_argument("--quick", action="store_true", help="PRAGMA quick_check")
    ap.add_argument("--skip-db", action="store_true", help="skip sqlite checks")
    args = ap.parse_args()

    modules = sorted(os.path.basename(p)[:-3]
                     for p in glob.glob("*.py") if not os.path.basename(p).startswith("_"))

    print("== source health ==")
    check_syntax(modules)
    check_local_imports(modules)

    print("== deliverables ==")
    check_reports_exist()
    check_v6_deliverables()
    check_v6_reproducibility()

    if not args.skip_db:
        print("== databases ==")
        check_dbs(args.quick)

    fails = [r for r in results if not r[0]]
    print(f"\n== SUMMARY: {len(results) - len(fails)}/{len(results)} passed ==")
    if fails:
        for _, label, detail in fails:
            print(f"  FAIL {label}: {detail}")
        return 1
    print("  ALL CHECKS PASS — repository is internally consistent and operationally ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
