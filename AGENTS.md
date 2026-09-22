# proof_of_simulation — project instructions

## Overview
Autonomous scientific-computing research on whether hidden computational
constraints are detectable. V1–V5.5 (passive substrate-fingerprint line) are all
CLOSED as statistical/control artifacts. V6 (active black-box response-operator
benchmark) is the current branch: synthetic-only, never emits SIMULATION_DETECTED.

## Commands
- `python v6_pipeline.py` — run the active V6 benchmark; regenerates
  `v6_results.json`, `v6_protocol.json`, `history_v6.sqlite3`, `v6_artifacts/`.
- `python verify.py [--quick|--skip-db]` — read-only repo self-check
  (source, imports, report lineage, V6 hash reproducibility, DB integrity). Exit 0 = ready.
- `python v5_5_pipeline.py` — V5.5 audit (depends on `v5_3_*`, `v5_detector.py`).
- `python v7_lattice.py` — V7 lattice-signature test: control gate + ingestion
  self-test on synthetic skies. `python v7_lattice.py <catalogue.csv> [cut_eV]`
  scores a real UHECR event list (columns `ra,dec[,energy]` deg/eV or `x,y,z`).
- `make` / `make test` — build & self-test the V1/V2 C kernel only (Makefile does
  not cover V3–V6; those pipelines are standalone scripts).

## Boundaries
- **Hash-frozen deliverables:** `v6_core.py`, `v6_pipeline.py`, `v6_db.py`,
  `v5_detector.py` are SHA-hashed into `v6_protocol.json` (`protocol_hash`). Editing
  any of them changes the hash — after edits re-run `python v6_pipeline.py` and sync
  the recorded hash in `report_v6.md`, or `verify.py` will FAIL.
- **Do not reformat / rename** frozen sources or the `vN_*` module convention
  (breaks imports + hashes).
- **Heavy evidence stays on disk, out of git:** `*.sqlite3`, `*.pkl`, `*.exe`,
  `v3..v5_5_artifacts/` are gitignored (see `.gitignore`). They are the sole copies
  of closed-branch results — never delete.
- `archives/` is read-only historical lineage; V2/V3/V4 stores reject `archives` paths at runtime.
- Docs: `README.md` is the index/lineage; each version's truth is its `report_vN.md` +
  `*_results.json`. Keep them consistent with code (doc-maintenance rule).

## Notes
- Machine-specific facts go to AGENTS.local.md (gitignored).
- Detailed guidance goes to .qoder/rules/*.md with model_decision/glob triggers.
- Working principle: understand architecture/context before flagging issues; resolve
  weak points (fix or document) rather than merely listing them; close tasks at ~90%.
## Git / path
- Git root: `J:\project\project_open_gate\proof_of_simulation`
- Alias: `J:\project\project-open-gate` (junction)
- Remote: `git@github.com:bouncemonster/project-open-gate.git`
- Branch: `main` — no force-push; keep heavy `*.sqlite3` / data dirs gitignored