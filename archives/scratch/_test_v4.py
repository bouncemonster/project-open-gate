#!/usr/bin/env python
"""Test V4 pipeline with error capture."""
import traceback
import sys

try:
    from v4_pipeline import V4Pipeline
    p = V4Pipeline(time_budget=14400)
    ok = p.run()
    print(f"\n{'='*60}")
    print(f"RESULT: {'SUCCESS' if ok else 'FAILED'}")
    print(f"{'='*60}")
    sys.exit(0 if ok else 1)
except Exception as e:
    print(f"\n{'='*60}")
    print(f"ERROR: {e}")
    print(f"{'='*60}")
    traceback.print_exc()
    sys.exit(1)
