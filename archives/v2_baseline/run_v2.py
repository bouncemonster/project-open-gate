#!/usr/bin/env python3
"""Run the V2 experiment pipeline."""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=== V2 PIPELINE START ===", flush=True)
    try:
        from agent_loop import V2AgentLoop
        print("Import OK", flush=True)
        loop = V2AgentLoop(quiet=False, time_budget=3600)
        print("Loop created", flush=True)
        
        # Phase 1: INIT
        print("\n=== PHASE: V2_INIT ===", flush=True)
        ok = loop.phase_init()
        print(f"INIT result: {ok}", flush=True)
        if not ok:
            print("INIT FAILED", flush=True)
            return False
        
        # Phase 2: SELF_TEST
        print("\n=== PHASE: V2_SELF_TEST ===", flush=True)
        ok = loop.phase_self_test()
        print(f"SELF_TEST result: {ok}", flush=True)
        if not ok:
            print("SELF_TEST FAILED", flush=True)
            return False
        
        # Phase 3: PROTOCOL_LOCK
        print("\n=== PHASE: V2_PROTOCOL_LOCK ===", flush=True)
        ok = loop.phase_protocol_lock()
        print(f"PROTOCOL_LOCK result: {ok}", flush=True)
        
        # Phase 4: BENCHMARK
        print("\n=== PHASE: V2_BENCHMARK ===", flush=True)
        ok = loop.phase_benchmark()
        print(f"BENCHMARK result: {ok}", flush=True)
        
        # Phase 5-7: SEARCH
        for track_name, driver in [("TRACK_A", "V1_INV_PI"),
                                    ("TRACK_B", "V10_PRIME_RESIDUAL"),
                                    ("TRACK_C", "V9_PRIME_EVENT")]:
            print(f"\n=== PHASE: V2_SEARCH {track_name} ({driver}) ===", flush=True)
            ok = loop.phase_search_track(track_name, driver)
            print(f"SEARCH {track_name} result: {ok}", flush=True)
        
        # Phase 8: CONTROLS
        print("\n=== PHASE: V2_CONTROLS ===", flush=True)
        ok = loop.phase_controls()
        print(f"CONTROLS result: {ok}", flush=True)
        
        # Phase 9: NULL
        print("\n=== PHASE: V2_NULL ===", flush=True)
        ok = loop.phase_null()
        print(f"NULL result: {ok}", flush=True)
        
        # Phase 10: VALIDATION
        print("\n=== PHASE: V2_VALIDATION ===", flush=True)
        ok = loop.phase_validation()
        print(f"VALIDATION result: {ok}", flush=True)
        
        # Phase 11: TEMPORAL
        print("\n=== PHASE: V2_TEMPORAL ===", flush=True)
        ok = loop.phase_temporal()
        print(f"TEMPORAL result: {ok}", flush=True)
        
        # Phase 12: REPORT
        print("\n=== PHASE: V2_REPORT ===", flush=True)
        ok = loop.phase_report()
        print(f"REPORT result: {ok}", flush=True)
        
        print("\n=== V2 PIPELINE COMPLETE ===", flush=True)
        return True
        
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        return False

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
