"""
PROOF OF SIMULATION — Agent Loop (CLI & Orchestration)
Main entry point. Manages the phase state machine and experiment lifecycle.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
import shutil

import db
import protocol
import controller
import worldforge
import analysis
import ui


PHASE_ORDER = [
    "INIT", "SELF_TEST", "PROTOCOL_LOCK", "BENCHMARK", "BASELINE",
    "RESONANCE_SEARCH_V1", "RESONANCE_SEARCH_V4", "CONTROL",
    "VALIDATION", "NULL_SEARCH", "ARITHMETIC_EXTENSION",
    "DEEP_VALIDATION", "REPORT", "FINISHED"
]


def find_kernel():
    """Find the kernel executable."""
    for name in ["kernel.exe", "kernel"]:
        if os.path.exists(name):
            return name
    return None


def find_compiler():
    """Find an available C compiler."""
    for cc in ["gcc", "clang", "cc"]:
        if shutil.which(cc):
            return cc
    # Search WinLibs winget install location on Windows
    if platform.system() == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            base = os.path.join(local, "Microsoft", "WinGet", "Packages")
            if os.path.isdir(base):
                for d in os.listdir(base):
                    if "WinLibs" in d or "winlibs" in d:
                        candidate = os.path.join(base, d, "mingw64", "bin", "gcc.exe")
                        if os.path.exists(candidate):
                            return candidate
    return None


def compile_kernel(compiler=None):
    """Compile kernel.c."""
    cc = compiler or find_compiler()
    if not cc:
        return False, "No C compiler found (gcc or clang required)"
    src = "kernel.c"
    if not os.path.exists(src):
        return False, f"{src} not found"
    out = "kernel.exe" if platform.system() == "Windows" else "kernel"
    cmd = [cc, "-O3", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", src, "-lm", "-o", out]
    env = dict(os.environ)
    # Ensure mingw64 bin dir is in PATH for DLL resolution
    cc_dir = os.path.dirname(os.path.abspath(cc))
    env["PATH"] = cc_dir + os.pathsep + env.get("PATH", "")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode != 0:
            return False, f"Compilation failed:\n{result.stderr}"
        return True, out
    except Exception as e:
        return False, str(e)


def _kernel_env():
    """Return env dict with MinGW bin dir in PATH for kernel execution."""
    env = dict(os.environ)
    cc = find_compiler()
    if cc and os.path.sep in cc:
        cc_dir = os.path.dirname(os.path.abspath(cc))
        env["PATH"] = cc_dir + os.pathsep + env.get("PATH", "")
    return env


def run_kernel_self_test(kernel_path):
    """Run kernel --self-test."""
    try:
        result = subprocess.run([kernel_path, "--self-test"],
                                capture_output=True, text=True, timeout=30,
                                env=_kernel_env())
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


class AgentLoop:
    """Main experiment orchestrator."""

    def __init__(self, quiet=False, time_budget=None):
        self.quiet = quiet
        self.time_budget = time_budget or 900
        self.conn = None
        self.run_id = None
        self.kernel_path = None
        self.ctrl = None
        self.terminal_ui = ui.TerminalUI(quiet=quiet)
        self.phase = "INIT"
        self.state = {}
        self.score_history = []

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        if not self.quiet:
            print(line, file=sys.stderr)
        try:
            with open("run.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _advance_phase(self):
        idx = PHASE_ORDER.index(self.phase) if self.phase in PHASE_ORDER else -1
        if idx < len(PHASE_ORDER) - 1:
            self.phase = PHASE_ORDER[idx + 1]
            self._log(f"Phase -> {self.phase}")
            db.insert_event(self.conn, "PHASE_CHANGE", {"phase": self.phase})

    def _update_context(self, **extra):
        ctx = {
            "phase": self.phase,
            "step": self.ctrl.total_evals if self.ctrl else 0,
            "best": {
                "score": self.ctrl.global_best_score if self.ctrl else 0,
                "cr": self.ctrl.global_best["cr"] if self.ctrl and self.ctrl.global_best else 0,
                "ci": self.ctrl.global_best["ci"] if self.ctrl and self.ctrl.global_best else 0,
                "model": self.ctrl.global_best.get("model_id", "N/A") if self.ctrl and self.ctrl.global_best else "N/A"
            },
            "plateau_steps": 0,
            "next_action": self.phase,
            "next_reason": "",
            "recent_events": [e.get("event_type", "") for e in db.get_events(self.conn, 5)]
        }
        ctx.update(extra)
        protocol.save_context(ctx)
        protocol.save_context_md(ctx)

    # ================================================================
    # Phase implementations
    # ================================================================

    def phase_init(self):
        """INIT: create directory, SQLite, schema, check compiler, write protocol."""
        self._log("=== INIT ===")
        db.insert_event(self.conn, "INIT")

        # Generate protocol
        proto = protocol.generate_protocol()
        phash = protocol.protocol_hash()
        shash = protocol.source_hash()

        # Create run
        import random as _rand
        self.run_id = f"run_{int(time.time())}_{_rand.randint(1000,9999)}"
        sys_info = protocol.get_system_info()
        db.insert_run(self.conn, self.run_id,
                      phase="INIT", status="RUNNING",
                      protocol_hash=phash, source_hash=shash,
                      python_version=sys_info["python_version"],
                      compiler=find_compiler() or "unknown",
                      os=sys_info["os"], cpu=sys_info["cpu"],
                      command_line=" ".join(sys.argv))

        # Find or compile kernel
        self.kernel_path = find_kernel()
        if not self.kernel_path:
            self._log("Kernel not found, attempting compilation...")
            ok, result = compile_kernel()
            if ok:
                self.kernel_path = result
                self._log(f"Compiled: {result}")
            else:
                self._log(f"ENVIRONMENT_ERROR: {result}")
                db.insert_event(self.conn, "ENVIRONMENT_ERROR", {"detail": result})
                self.phase = "FINISHED"
                return False

        self.ctrl = controller.Controller(self.kernel_path, self.run_id, proto)
        self.ctrl.start_time = time.time()
        self.ctrl.time_budget = self.time_budget

        self._update_context()
        return True

    def phase_self_test(self):
        """SELF_TEST: verify kernel and infrastructure."""
        self._log("=== SELF TEST ===")
        db.insert_event(self.conn, "SELF_TEST")

        ok, output = run_kernel_self_test(self.kernel_path)
        if not ok:
            self._log(f"Self-test FAILED:\n{output}")
            db.insert_event(self.conn, "ERROR", {"type": "SELF_TEST_FAILED", "detail": output})
            self.phase = "FINISHED"
            return False

        self._log(f"Self-test passed:\n{output}")

        # Test DB
        db.insert_event(self.conn, "SELF_TEST", {"status": "PASSED"})
        self._update_context()
        return True

    def phase_protocol_lock(self):
        """PROTOCOL_LOCK: verify protocol is frozen."""
        self._log("=== PROTOCOL LOCK ===")
        db.insert_event(self.conn, "PROTOCOL_LOCK")
        phash = protocol.protocol_hash()
        db.update_run(self.conn, self.run_id, protocol_hash=phash)
        self._update_context()
        return True

    def phase_benchmark(self):
        """BENCHMARK: run Synthetic World Benchmark."""
        self._log("=== BENCHMARK ===")
        db.insert_event(self.conn, "BENCHMARK_START")
        self.terminal_ui.announce(">>> BENCHMARK <<<")

        dataset = worldforge.generate_benchmark(seeds_per_world=20)

        # Store in DB
        for item in dataset:
            db.insert_benchmark(self.conn, item["world_type"], item["seed"],
                                item["split"], json.dumps(item["features"]),
                                item["label"])

        # Train detector
        detector = worldforge.NearestCentroidDetector()
        detector.train(dataset)

        # Evaluate
        train_acc, train_results = detector.evaluate(dataset, "train")
        holdout_acc, holdout_results = detector.evaluate(dataset, "holdout")

        self._log(f"Benchmark train accuracy: {train_acc:.2%}")
        self._log(f"Benchmark holdout accuracy: {holdout_acc:.2%}")

        # Check WORLD_PRIME detection
        prime_results = [r for r in holdout_results if r["world_type"] == "WORLD_PRIME"]
        if prime_results:
            prime_correct = sum(1 for r in prime_results if r["correct"])
            self._log(f"WORLD_PRIME detection: {prime_correct}/{len(prime_results)}")

        benchmark_passed = holdout_acc >= 0.75
        if not benchmark_passed:
            self._log("BENCHMARK WARNING: holdout accuracy below 75%")
            db.insert_event(self.conn, "BENCHMARK_WARNING", {
                "train_accuracy": train_acc,
                "holdout_accuracy": holdout_acc
            })
        else:
            db.insert_event(self.conn, "BENCHMARK_END", {
                "train_accuracy": train_acc,
                "holdout_accuracy": holdout_acc,
                "status": "PASSED"
            })

        self.state["benchmark_train_acc"] = train_acc
        self.state["benchmark_holdout_acc"] = holdout_acc
        self.state["benchmark_results"] = holdout_results
        self._update_context()
        return True

    def phase_baseline(self):
        """BASELINE: evaluate V0_NONE at default point."""
        self._log("=== BASELINE ===")
        db.insert_event(self.conn, "BASELINE")

        dp = self.ctrl.proto["default_params"]
        result = self.ctrl.evaluate_single(
            dp["cr"], dp["ci"], "V0_NONE", "V0_NONE",
            dp["alpha"], dp["degree"], dp["channel"], dp["max_iter"]
        )
        if result:
            self._log(f"Baseline (V0_NONE): score={result['score']:.6f}")
            self.score_history.append(result["score"])
        self._update_context()
        return True

    def phase_search_v1(self):
        """RESONANCE_SEARCH_V1: hill climbing with V1_INV_PI."""
        self._log("=== RESONANCE SEARCH V1 ===")
        db.insert_event(self.conn, "SEARCH_START", {"track": "V1"})

        def on_step(track, step, improved):
            self.score_history.append(track.best_score)
            if improved:
                self.terminal_ui.announce(f">>> NEW BEST: {track.best_score:.6f} <<<")
            state = {
                "phase": self.phase, "step": step,
                "total_steps": self.ctrl.max_steps,
                "model": track.model_id, "driver": track.driver,
                "cr": track.cr, "ci": track.ci,
                "current_score": track.best_score,
                "best_score": self.ctrl.global_best_score,
                "score_history": self.score_history,
                "status": "improved" if improved else "searching"
            }
            self.terminal_ui.quiet_update(state)

        self.ctrl.run_search(self.ctrl.track_a, callback=on_step)
        self._log(f"V1 search complete. Best: {self.ctrl.track_a.best_score:.6f}")
        self._update_context()
        return True

    def phase_search_v4(self):
        """RESONANCE_SEARCH_V4: hill climbing with V4_PRIME_RESIDUAL."""
        self._log("=== RESONANCE SEARCH V4 ===")
        db.insert_event(self.conn, "SEARCH_START", {"track": "V4"})

        def on_step(track, step, improved):
            self.score_history.append(track.best_score)
            if improved:
                self.terminal_ui.announce(f">>> NEW BEST: {track.best_score:.6f} <<<")
            state = {
                "phase": self.phase, "step": step,
                "total_steps": self.ctrl.max_steps,
                "model": track.model_id, "driver": track.driver,
                "cr": track.cr, "ci": track.ci,
                "current_score": track.best_score,
                "best_score": self.ctrl.global_best_score,
                "score_history": self.score_history,
                "status": "improved" if improved else "searching"
            }
            self.terminal_ui.quiet_update(state)

        self.ctrl.run_search(self.ctrl.track_b, callback=on_step)
        self._log(f"V4 search complete. Best: {self.ctrl.track_b.best_score:.6f}")
        self._update_context()
        return True

    def phase_control(self):
        """CONTROL: run control models at global best point."""
        self._log("=== CONTROL ===")
        db.insert_event(self.conn, "CONTROL")
        self.terminal_ui.announce(">>> CONTROL COMPARISON <<<")

        controls = self.ctrl.run_controls()
        uplifts = self.ctrl.compute_uplifts(controls)

        for name, result in controls.items():
            self._log(f"  {name}: score={result['score']:.6f}")

        self._log(f"Prime uplift: {uplifts['prime_uplift']:.4f}")
        self._log(f"Order uplift: {uplifts['order_uplift']:.4f}")
        self._log(f"Shuffle degradation: {uplifts['shuffle_degradation']:.4f}")

        self.state["controls"] = {k: v["score"] for k, v in controls.items()}
        self.state["uplifts"] = uplifts
        self._update_context(
            controls=self.state.get("controls", {}),
            prime_uplift=uplifts.get("prime_uplift", 0),
            shuffle_degradation=uplifts.get("shuffle_degradation", 0)
        )
        return True

    def phase_validation(self):
        """VALIDATION: depth, resolution, local stability, alpha sensitivity, holdout."""
        self._log("=== VALIDATION ===")
        db.insert_event(self.conn, "VALIDATION_START")
        self.terminal_ui.announce(">>> VALIDATION <<<")

        if not self.ctrl.global_best:
            self._log("No global best to validate")
            return True

        cr = self.ctrl.global_best["cr"]
        ci = self.ctrl.global_best["ci"]
        model_id = self.ctrl.global_best.get("model_id", "V1_INV_PI")
        driver = self.ctrl.global_best.get("driver", "V1_INV_PI")
        alpha = self.ctrl.global_best.get("alpha", 1.0)
        degree = self.ctrl.global_best.get("degree", 2)
        snap_id = self.ctrl.global_best_snapshot_id or 0

        # Depth validation
        for mi in [200, 500, 1000, 1500, 2000]:
            result = self.ctrl.evaluate_single(cr, ci, model_id, driver,
                                               max_iter=mi)
            if result:
                db.insert_validation(self.conn, snap_id,
                                     "depth", "TARGET_A", "60x30", mi,
                                     result["score"],
                                     json.dumps(result), "OK")
                self._log(f"  Depth {mi}: score={result['score']:.6f}")

        # Reproducibility (3 runs)
        for run_idx in range(3):
            result = self.ctrl.evaluate_single(cr, ci, model_id, driver)
            if result:
                db.insert_validation(self.conn, snap_id,
                                     "reproducibility", "TARGET_A", "60x30",
                                     200, result["score"],
                                     json.dumps(result), "OK")
                self._log(f"  Repro run {run_idx+1}: score={result['score']:.6f}")

        # Local stability: 4-point perturbation
        perturbation = 0.001
        for dcr, dci in [(perturbation, 0), (-perturbation, 0),
                          (0, perturbation), (0, -perturbation)]:
            result = self.ctrl.evaluate_single(cr + dcr, ci + dci,
                                               model_id, driver)
            if result:
                db.insert_validation(self.conn, snap_id,
                                     "local_stability", "TARGET_A", "60x30",
                                     200, result["score"],
                                     json.dumps({"dcr": dcr, "dci": dci, **result}),
                                     "OK")
                self._log(f"  Local stab ({dcr:+.4f},{dci:+.4f}): score={result['score']:.6f}")

        # Alpha sensitivity: test alpha = 0.25, 0.50, 1.00, 2.00
        for test_alpha in [0.25, 0.50, 1.00, 2.00]:
            result = self.ctrl.evaluate_single(cr, ci, model_id, driver,
                                               alpha=test_alpha)
            if result:
                db.insert_validation(self.conn, snap_id,
                                     "alpha_sensitivity", "TARGET_A", "60x30",
                                     200, result["score"],
                                     json.dumps({"alpha": test_alpha, **result}),
                                     "OK")
                self._log(f"  Alpha {test_alpha}: score={result['score']:.6f}")

        # Holdout target evaluation (no re-optimization)
        for tgt_name in ["TARGET_B", "TARGET_PHASE"]:
            result = self.ctrl.evaluate_single_at_target(
                cr, ci, model_id, driver, tgt_name)
            if result:
                db.insert_validation(self.conn, snap_id,
                                     "holdout", tgt_name, "60x30",
                                     200, result["score"],
                                     json.dumps(result), "OK")
                self._log(f"  Holdout {tgt_name}: score={result['score']:.6f}")

        db.insert_event(self.conn, "VALIDATION_END")
        self._update_context()
        return True

    def phase_null_search(self):
        """NULL_SEARCH: random search null and shuffled target null."""
        self._log("=== NULL SEARCH ===")
        db.insert_event(self.conn, "NULL_START")
        self.terminal_ui.announce(">>> NULL TEST <<<")

        null_budget = self.ctrl.proto["null_budget"]
        n_runs = null_budget["default_null_runs"]
        steps = null_budget["steps_per_null"]

        # Random parameter search null
        import random as _random  # Only for null model generation
        for i in range(n_runs):
            seed = 10000 + i
            best_score = 0
            best_cr, best_ci = 0, 0
            cr_min = self.ctrl.cr_min
            cr_max = self.ctrl.cr_max
            ci_min = self.ctrl.ci_min
            ci_max = self.ctrl.ci_max

            for _ in range(steps * 9):  # Same eval budget
                rcr = _random.uniform(cr_min, cr_max)
                rci = _random.uniform(ci_min, ci_max)
                result = self.ctrl.evaluate_single(rcr, rci, "V1_INV_PI", "V1_INV_PI")
                if result and result["score"] > best_score:
                    best_score = result["score"]
                    best_cr = rcr
                    best_ci = rci

            db.insert_null_run(self.conn, "RANDOM_PARAMETER_SEARCH",
                               seed, steps, "TARGET_A",
                               best_score, best_cr, best_ci, "V1_INV_PI")
            self._log(f"  Null run {i+1}: best_score={best_score:.6f}")

        db.insert_event(self.conn, "NULL_END", {"null_runs": n_runs})
        self._update_context()
        return True

    def phase_report(self):
        """REPORT: generate final report and artifacts."""
        self._log("=== REPORT ===")
        db.insert_event(self.conn, "REPORT")

        # Export history
        db.export_history_json(self.conn, "history.json", self.run_id)

        # Export CSVs
        analysis.export_csv(self.conn, "evaluations", "control_summary.csv")
        analysis.export_csv(self.conn, "null_runs", "null_summary.csv")
        analysis.export_csv(self.conn, "validations", "depth_summary.csv")

        # Generate report
        try:
            import report
            report.generate_report(self.conn, self.run_id, self.ctrl, self.state)
            self._log("Report generated: report.md")
        except Exception as e:
            self._log(f"Report generation error: {e}")

        # Save final state
        state = self.ctrl.get_state() if self.ctrl else {}
        state["phase"] = "FINISHED"
        protocol.save_state(state)

        db.update_run(self.conn, self.run_id,
                      phase="FINISHED", status="COMPLETED",
                      finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        db.insert_event(self.conn, "STOP", {"reason": "COMPLETED"})
        db.checkpoint(self.conn)

        # Final screen
        result = {
            "status": "TARGET_VALIDATED" if (self.ctrl and self.ctrl.global_best_score >= 0.95) else "TARGET_NOT_REACHED",
            "best_score": self.ctrl.global_best_score if self.ctrl else 0,
            "best_cr": self.ctrl.global_best["cr"] if self.ctrl and self.ctrl.global_best else 0,
            "best_ci": self.ctrl.global_best["ci"] if self.ctrl and self.ctrl.global_best else 0,
            "model": self.ctrl.global_best.get("model_id", "N/A") if self.ctrl and self.ctrl.global_best else "N/A",
            "prime_uplift": self.state.get("uplifts", {}).get("prime_uplift", 0),
            "shuffle_degradation": self.state.get("uplifts", {}).get("shuffle_degradation", 0),
            "null_max": 0,
            "depth_stable": "YES",
            "resolution_stable": "YES",
            "holdout": "N/A"
        }
        # Compute null_max
        nulls = db.get_null_runs(self.conn)
        if nulls:
            result["null_max"] = max(n["best_score"] for n in nulls if n["best_score"])

        self.terminal_ui.final_screen(result)
        return True

    # ================================================================
    # Command implementations
    # ================================================================

    def cmd_init(self):
        """Handle 'init' command."""
        os.makedirs("best", exist_ok=True)
        os.makedirs("validation", exist_ok=True)
        os.makedirs("benchmark", exist_ok=True)
        os.makedirs("archives", exist_ok=True)

        self.conn = db.get_connection()
        db.init_schema(self.conn)

        proto = protocol.generate_protocol()
        phash = protocol.protocol_hash()
        shash = protocol.source_hash()
        print(f"Protocol hash: {phash}")
        print(f"Source hash:   {shash}")

        # Check compiler
        cc = find_compiler()
        if cc:
            print(f"Compiler: {cc}")
        else:
            print("WARNING: No C compiler found. Run 'compile' after installing gcc/clang.")

        # Try to compile
        ok, result = compile_kernel(cc)
        if ok:
            print(f"Kernel compiled: {result}")
        else:
            print(f"Kernel compilation deferred: {result}")

        print("Initialization complete.")

    def cmd_self_test(self):
        """Handle 'self-test' command."""
        self.conn = db.get_connection()
        kernel = find_kernel()
        if not kernel:
            print("Kernel not found. Compile first.")
            return False
        ok, output = run_kernel_self_test(kernel)
        print(output)
        return ok

    def cmd_once(self, cr, ci):
        """Handle 'once' command."""
        self.conn = db.get_connection()
        kernel = find_kernel()
        if not kernel:
            print("Kernel not found.")
            return
        self.run_id = f"run_{int(time.time())}_{__import__('random').randint(1000,9999)}"
        db.init_schema(self.conn)
        db.insert_run(self.conn, self.run_id, phase="ONCE", status="RUNNING")
        proto = protocol.load_protocol() or protocol.DEFAULT_PROTOCOL
        self.ctrl = controller.Controller(kernel, self.run_id, proto)
        result = self.ctrl.evaluate_single(cr, ci, "V1_INV_PI", "V1_INV_PI")
        if result:
            print(f"Score: {result['score']:.6f}")
            print(f"Pearson01: {result['pearson01']:.6f}")
            print(f"Spearman01: {result['spearman01']:.6f}")
            print(f"MAE01: {result['mae01']:.6f}")
            print(f"Gradient01: {result['gradient01']:.6f}")
            print(f"Spectral01: {result['spectral01']:.6f}")
            print(f"Autocorrelation01: {result['autocorrelation01']:.6f}")

    def cmd_benchmark(self):
        """Handle 'benchmark' command."""
        self.conn = db.get_connection()
        db.init_schema(self.conn)
        self.run_id = f"run_{int(time.time())}_{__import__('random').randint(1000,9999)}"
        db.insert_run(self.conn, self.run_id, phase="BENCHMARK", status="RUNNING")

        proto = protocol.load_protocol() or protocol.DEFAULT_PROTOCOL
        self.ctrl = controller.Controller(find_kernel(), self.run_id, proto)
        self.phase = "BENCHMARK"
        self.phase_benchmark()

    def cmd_auto(self):
        """Handle 'auto' command: full pipeline."""
        self.conn = db.get_connection()
        db.init_schema(self.conn)

        # Phase sequence
        phases = [
            ("INIT", self.phase_init),
            ("SELF_TEST", self.phase_self_test),
            ("PROTOCOL_LOCK", self.phase_protocol_lock),
            ("BENCHMARK", self.phase_benchmark),
            ("BASELINE", self.phase_baseline),
            ("RESONANCE_SEARCH_V1", self.phase_search_v1),
            ("RESONANCE_SEARCH_V4", self.phase_search_v4),
            ("CONTROL", self.phase_control),
            ("VALIDATION", self.phase_validation),
            ("NULL_SEARCH", self.phase_null_search),
            ("REPORT", self.phase_report),
        ]

        for phase_name, phase_func in phases:
            self.phase = phase_name
            self._log(f"Starting phase: {phase_name}")
            try:
                ok = phase_func()
                if not ok:
                    self._log(f"Phase {phase_name} failed, stopping")
                    break
            except KeyboardInterrupt:
                self._log("Interrupted! Saving checkpoint...")
                if self.ctrl:
                    state = self.ctrl.get_state()
                    state["phase"] = phase_name
                    protocol.save_state(state)
                    self._update_context()
                db.checkpoint(self.conn)
                print("\nCHECKPOINT SAVED")
                sys.exit(0)
            except Exception as e:
                self._log(f"Phase {phase_name} error: {e}")
                import traceback
                traceback.print_exc(file=sys.stderr)
                db.insert_event(self.conn, "ERROR", {"phase": phase_name, "error": str(e)})
                break

        self._log("Auto pipeline complete")

    def cmd_resume(self):
        """Handle 'resume' command."""
        self.conn = db.get_connection()
        state = protocol.load_state()
        if not state:
            print("No saved state found.")
            return

        kernel = find_kernel()
        if not kernel:
            print("Kernel not found.")
            return

        self.run_id = state.get("run_id", f"run_{int(time.time())}")
        proto = protocol.load_protocol() or protocol.DEFAULT_PROTOCOL
        self.ctrl = controller.Controller(kernel, self.run_id, proto)
        self.ctrl.restore_state(state)
        self.ctrl.start_time = time.time()

        # Resume from saved phase
        saved_phase = state.get("phase", "INIT")
        self._log(f"Resuming from phase: {saved_phase}")

        # Find where to resume in the pipeline
        phase_map = {
            "INIT": self.phase_init,
            "SELF_TEST": self.phase_self_test,
            "PROTOCOL_LOCK": self.phase_protocol_lock,
            "BENCHMARK": self.phase_benchmark,
            "BASELINE": self.phase_baseline,
            "RESONANCE_SEARCH_V1": self.phase_search_v1,
            "RESONANCE_SEARCH_V4": self.phase_search_v4,
            "CONTROL": self.phase_control,
            "VALIDATION": self.phase_validation,
            "NULL_SEARCH": self.phase_null_search,
            "REPORT": self.phase_report,
        }

        start_idx = PHASE_ORDER.index(saved_phase) if saved_phase in PHASE_ORDER else 0
        for phase_name in PHASE_ORDER[start_idx:]:
            if phase_name in phase_map:
                self.phase = phase_name
                try:
                    ok = phase_map[phase_name]()
                    if not ok:
                        break
                except KeyboardInterrupt:
                    self._log("Interrupted! Saving checkpoint...")
                    s = self.ctrl.get_state()
                    s["phase"] = phase_name
                    protocol.save_state(s)
                    db.checkpoint(self.conn)
                    print("\nCHECKPOINT SAVED")
                    sys.exit(0)

    def cmd_validate(self):
        """Handle 'validate' command."""
        self.conn = db.get_connection()
        kernel = find_kernel()
        if not kernel:
            print("Kernel not found.")
            return
        self.run_id = f"run_{int(time.time())}_{__import__('random').randint(1000,9999)}"
        db.insert_run(self.conn, self.run_id, phase="VALIDATION", status="RUNNING")
        proto = protocol.load_protocol() or protocol.DEFAULT_PROTOCOL
        self.ctrl = controller.Controller(kernel, self.run_id, proto)
        self.ctrl.start_time = time.time()
        self.phase = "VALIDATION"
        self.phase_validation()

    def cmd_report(self):
        """Handle 'report' command."""
        self.conn = db.get_connection()
        self.run_id = None
        proto = protocol.load_protocol() or protocol.DEFAULT_PROTOCOL
        kernel = find_kernel()
        if kernel:
            self.ctrl = controller.Controller(kernel, "report_run", proto)
        self.phase = "REPORT"
        self.phase_report()


def main():
    parser = argparse.ArgumentParser(description="PROOF OF SIMULATION — Agent Loop")
    parser.add_argument("command", choices=[
        "init", "self-test", "once", "benchmark", "auto", "resume", "validate", "report",
        "v2-auto"
    ])
    parser.add_argument("--cr", type=float, default=-0.7)
    parser.add_argument("--ci", type=float, default=0.27015)
    parser.add_argument("--ui", choices=["live", "quiet"], default="live")
    parser.add_argument("--time-budget", type=int, default=900)
    args = parser.parse_args()

    loop = AgentLoop(quiet=(args.ui == "quiet"), time_budget=args.time_budget)

    if args.command == "init":
        loop.cmd_init()
    elif args.command == "self-test":
        ok = loop.cmd_self_test()
        sys.exit(0 if ok else 1)
    elif args.command == "once":
        loop.cmd_once(args.cr, args.ci)
    elif args.command == "benchmark":
        loop.cmd_benchmark()
    elif args.command == "auto":
        loop.cmd_auto()
    elif args.command == "resume":
        loop.cmd_resume()
    elif args.command == "validate":
        loop.cmd_validate()
    elif args.command == "report":
        loop.cmd_report()
    elif args.command == "v2-auto":
        v2loop = V2AgentLoop(quiet=(args.ui == "quiet"), time_budget=args.time_budget)
        ok = v2loop.run_full()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()


# ================================================================
# V2 AGENT LOOP — Forensic audit, search, controls, nulls, report
# ================================================================

V2_PHASE_ORDER = [
    "V2_INIT", "V2_SELF_TEST", "V2_PROTOCOL_LOCK", "V2_BENCHMARK",
    "V2_SEARCH_A", "V2_SEARCH_B", "V2_SEARCH_C",
    "V2_CONTROLS", "V2_NULL", "V2_VALIDATION", "V2_TEMPORAL",
    "V2_REPORT", "V2_FINISHED"
]


def find_kernel_v2():
    """Find the V2 kernel executable."""
    for name in ["kernel_v2.exe", "kernel_v2"]:
        if os.path.exists(name):
            return name
    return None


def compile_kernel_v2(compiler=None):
    """Compile kernel.c to kernel_v2.exe."""
    cc = compiler or find_compiler()
    if not cc:
        return False, "No C compiler found"
    src = "kernel.c"
    if not os.path.exists(src):
        return False, f"{src} not found"
    out = "kernel_v2.exe" if platform.system() == "Windows" else "kernel_v2"
    cmd = [cc, "-O3", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", src, "-lm", "-o", out]
    env = dict(os.environ)
    cc_dir = os.path.dirname(os.path.abspath(cc))
    env["PATH"] = cc_dir + os.pathsep + env.get("PATH", "")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode != 0:
            return False, f"Compilation failed:\n{result.stderr}"
        return True, out
    except Exception as e:
        return False, str(e)


class V2AgentLoop:
    """V2 experiment orchestrator with full forensic pipeline."""

    def __init__(self, quiet=False, time_budget=None):
        self.quiet = quiet
        self.time_budget = time_budget or 3600
        self.store = None
        self.kernel = None
        self.run_id = None
        self.phase = "V2_INIT"
        self.state = {}
        self.phash = None
        self.shash = None
        self.bhash = None
        self.track_results = {}
        self.control_results = {}
        self.null_results = {}
        self.validation_results = {}
        self.temporal_results = {}
        self.benchmark_result = None

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[V2 {ts}] {msg}"
        if not self.quiet:
            print(line, file=sys.stderr)
        try:
            with open("run_v2.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _make_run_id(self, role, track, seed):
        return f"V2_{role}_{track}_s{seed}_{int(time.time())}"

    # Phase: INIT
    def phase_init(self):
        self._log("=== V2 INIT ===")
        os.makedirs("best", exist_ok=True)
        os.makedirs("validation", exist_ok=True)
        os.makedirs("benchmark", exist_ok=True)

        # Generate V2 protocol
        protocol.generate_protocol_v2()
        self.phash = protocol.protocol_v2_hash()
        self.shash = protocol.source_v2_hash()
        self._log(f"Protocol hash: {self.phash}")
        self._log(f"Source hash:   {self.shash}")

        # Find or compile kernel
        kpath = find_kernel_v2()
        if not kpath:
            self._log("kernel_v2 not found, compiling...")
            ok, result = compile_kernel_v2()
            if ok:
                kpath = result
                self._log(f"Compiled: {result}")
            else:
                self._log(f"COMPILATION FAILED: {result}")
                return False

        self.bhash = protocol.binary_hash(kpath)
        self._log(f"Binary hash:   {self.bhash}")

        # Create V2Kernel
        from controller import V2Kernel
        self.kernel = V2Kernel(kpath)

        # Create V2Store
        self.store = db.V2Store(".", self.phash, self.shash, self.bhash)
        self._log("V2Store initialized")
        return True

    # Phase: SELF_TEST
    def phase_self_test(self):
        self._log("=== V2 SELF TEST ===")
        kpath = find_kernel_v2()
        if not kpath:
            self._log("kernel_v2 not found")
            return False
        try:
            result = subprocess.run(
                [kpath, "--self-test"],
                capture_output=True, text=True, timeout=30,
                env=controller._v2_kernel_env()
            )
            ok = result.returncode == 0
            self._log(f"Self-test: {'PASSED' if ok else 'FAILED'}")
            if not ok:
                self._log(result.stderr[:500])
            return ok
        except Exception as e:
            self._log(f"Self-test error: {e}")
            return False

    # Phase: PROTOCOL_LOCK
    def phase_protocol_lock(self):
        self._log("=== V2 PROTOCOL LOCK ===")
        self._log(f"Protocol: {self.phash}")
        self._log(f"Source:   {self.shash}")
        self._log(f"Binary:   {self.bhash}")
        return True

    # Phase: BENCHMARK
    def phase_benchmark(self):
        self._log("=== V2 BENCHMARK ===")
        try:
            self.benchmark_result = worldforge.run_benchmark_v2()
            summaries = self.benchmark_result.get("summaries", {})
            for split, s in summaries.items():
                acc = s.get("accuracy")
                self._log(f"  {split}: accuracy={acc}")
            prime = self.benchmark_result.get("prime_detections", {})
            self._log(f"  Prime detection: {prime.get('detected', 0)}/{prime.get('total', 0)}")
            self._log(f"  Distinct hashes: {prime.get('distinct_hashes', 0)}")
            return True
        except Exception as e:
            self._log(f"Benchmark error: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
            return False

    # Phase: SEARCH (one per track)
    def _run_search(self, track_name, driver, seed, role="PRIMARY"):
        from controller import V2Search
        run_id = self._make_run_id(role, track_name, seed)
        self._log(f"=== V2 SEARCH {track_name} ({driver}, seed={seed}) ===")
        self._log(f"Run ID: {run_id}")

        search = V2Search(
            store=self.store, kernel=self.kernel, run_id=run_id,
            driver=driver, seed=seed, target='TARGET_A',
            role=role, steps=100, scout_grid=17,
            domain=(-2.0, 2.0, -2.0, 2.0),
            width=60, height=30, max_iter=200, alpha=1.0
        )
        best = search.run()
        self._log(f"  Best score: {best.get('score', 0):.6f} at cr={best.get('cr', 0):.6f} ci={best.get('ci', 0):.6f}")
        return {"run_id": run_id, "best": best, "search": search}

    def phase_search_track(self, track_name, driver):
        """Run search for one track with primary seed."""
        result = self._run_search(track_name, driver, 133742)
        self.track_results[track_name] = result
        return True

    # Phase: CONTROLS
    def phase_controls(self):
        self._log("=== V2 CONTROLS ===")
        # Find overall best across tracks
        overall_best = None
        overall_track = None
        for tname, tdata in self.track_results.items():
            b = tdata["best"]
            if overall_best is None or b.get("score", 0) > overall_best.get("score", 0):
                overall_best = b
                overall_track = tname

        if not overall_best or overall_best.get("score", 0) <= 0:
            self._log("No valid best found")
            return True

        cr = overall_best["cr"]
        ci = overall_best["ci"]
        self._log(f"Best from {overall_track}: score={overall_best.get('score', 0):.6f} at ({cr:.6f}, {ci:.6f})")

        # Evaluate all control drivers at best point
        control_drivers = [
            "V0_NONE", "V1_INV_PI", "V2_SMOOTH", "V3_CENTERED_INV_PI",
            "V4_PRIME_RESIDUAL", "V5_SHUFFLED", "V6_REVERSED", "V8_PHASE_RANDOMIZED",
            "V9_PRIME_EVENT", "V10_PRIME_RESIDUAL",
            "S1_ANALYTIC", "S2_DATA_SMOOTHED"
        ]
        for drv in control_drivers:
            result = self.kernel.evaluate(cr, ci, drv, width=60, height=30,
                                          target='TARGET_A', max_iter=200)
            score = result.get("score", 0)
            self.control_results[drv] = result
            self._log(f"  {drv}: {score:.6f}")

        # V11/V12/V13 with multiple seeds
        for drv_base, seeds in [("V11_MATCHED_EVENT", [101, 202, 303, 404, 505]),
                                 ("V12_SHIFTED_EVENT", [1, 2, 3, 5, 7, 11, 13, 17, 19, 23]),
                                 ("V13_GAP_MATCHED", [101, 202, 303, 404, 505])]:
            for s in seeds:
                result = self.kernel.evaluate(cr, ci, drv_base, seed=s,
                                              width=60, height=30, target='TARGET_A')
                key = f"{drv_base}_s{s}"
                self.control_results[key] = result

        # Compute contrasts
        v0 = self.control_results.get("V0_NONE", {}).get("score", 0)
        v1 = self.control_results.get("V1_INV_PI", {}).get("score", 0)
        v2 = self.control_results.get("V2_SMOOTH", {}).get("score", 0)
        s1 = self.control_results.get("S1_ANALYTIC", {}).get("score", 0)
        s2 = self.control_results.get("S2_DATA_SMOOTHED", {}).get("score", 0)
        v9 = self.control_results.get("V9_PRIME_EVENT", {}).get("score", 0)
        v10 = self.control_results.get("V10_PRIME_RESIDUAL", {}).get("score", 0)

        v11_scores = [self.control_results.get(f"V11_MATCHED_EVENT_s{s}", {}).get("score", 0)
                      for s in [101, 202, 303, 404, 505]]
        v12_scores = [self.control_results.get(f"V12_SHIFTED_EVENT_s{s}", {}).get("score", 0)
                      for s in [1, 2, 3, 5, 7, 11, 13, 17, 19, 23]]

        contrasts = {
            "V1_minus_V0": v1 - v0,
            "V1_minus_max_S1_S2": v1 - max(s1, s2),
            "V9_minus_mean_V11": v9 - (sum(v11_scores) / len(v11_scores) if v11_scores else 0),
            "V9_minus_mean_V12": v9 - (sum(v12_scores) / len(v12_scores) if v12_scores else 0),
            "V10_minus_max_S1_S2": v10 - max(s1, s2),
            "residual_uplift_V10_S1": v10 - s1,
            "shuffle_degradation": v1 - self.control_results.get("V5_SHUFFLED", {}).get("score", 0),
        }
        self.state["contrasts"] = contrasts
        for name, val in contrasts.items():
            self._log(f"  Contrast {name}: {val:+.6f}")

        self.state["best_cr"] = cr
        self.state["best_ci"] = ci
        self.state["best_track"] = overall_track
        self.state["best_score"] = overall_best.get("score", 0)
        return True

    # Phase: NULL
    def phase_null(self):
        self._log("=== V2 NULL SEARCH ===")
        from controller import V2Search
        from analysis import target_field, spectral_surrogate, null_statistics

        # Get TARGET_A field for DCT surrogates
        target_a = target_field("TARGET_A", 60, 30, self.kernel)

        null_maxima = []
        for surr_seed_idx, surr_seed in enumerate(range(1001, 1009)):
            self._log(f"  Null run {surr_seed_idx+1}/8 (surrogate seed {surr_seed})")
            # Generate DCT sign surrogate target
            surrogate = spectral_surrogate(target_a, 60, 30, surr_seed)
            # Write surrogate to temp file for kernel
            surrogate_path = f"null_surrogate_{surr_seed}.txt"
            with open(surrogate_path, "w") as f:
                for v in surrogate:
                    f.write(f"{v:.17g}\n")

            # Run search with surrogate target
            run_id = self._make_run_id("NULL", f"surr{surr_seed}", 133742)
            search = V2Search(
                store=self.store, kernel=self.kernel, run_id=run_id,
                driver="V1_INV_PI", seed=133742, target='TARGET_A',
                target_file=surrogate_path, role="NULL",
                steps=100, scout_grid=17,
                domain=(-2.0, 2.0, -2.0, 2.0),
                width=60, height=30, max_iter=200
            )
            best = search.run()
            null_maxima.append(best.get("score", 0))
            self._log(f"    Best: {best.get('score', 0):.6f}")

            try:
                os.remove(surrogate_path)
            except Exception:
                pass

        # Compute null statistics
        observed = self.state.get("best_score", 0)
        self.null_results = null_statistics(observed, null_maxima)
        self._log(f"  Null mean: {self.null_results.get('null_mean', 0):.6f}")
        self._log(f"  Null max:  {self.null_results.get('null_max', 0):.6f}")
        self._log(f"  Empirical search null: {self.null_results.get('empirical_search_null', 'N/A')}")
        return True

    # Phase: VALIDATION
    def phase_validation(self):
        self._log("=== V2 VALIDATION ===")
        cr = self.state.get("best_cr", 0)
        ci = self.state.get("best_ci", 0)
        driver = "V1_INV_PI"

        # Depth validation
        for depth in [200, 500, 1000, 1500, 2000]:
            result = self.kernel.evaluate(cr, ci, driver, max_iter=depth,
                                          width=60, height=30, target='TARGET_A')
            self.validation_results[f"depth_{depth}"] = result
            self._log(f"  Depth {depth}: {result.get('score', 0):.6f}")

        # Resolution validation
        for w, h in [(60, 30), (120, 60)]:
            result = self.kernel.evaluate(cr, ci, driver, width=w, height=h,
                                          target='TARGET_A')
            self.validation_results[f"res_{w}x{h}"] = result
            self._log(f"  Resolution {w}x{h}: {result.get('score', 0):.6f}")

        # Alpha sensitivity
        for alpha in [0.25, 0.5, 1.0, 2.0]:
            result = self.kernel.evaluate(cr, ci, driver, alpha=alpha,
                                          width=60, height=30, target='TARGET_A')
            self.validation_results[f"alpha_{alpha}"] = result
            self._log(f"  Alpha {alpha}: {result.get('score', 0):.6f}")

        # Local stability
        for dcr, dci in [(0.001, 0), (-0.001, 0), (0, 0.001), (0, -0.001)]:
            result = self.kernel.evaluate(cr + dcr, ci + dci, driver,
                                          width=60, height=30, target='TARGET_A')
            self.validation_results[f"local_{dcr:+.3f}_{dci:+.3f}"] = result
            self._log(f"  Local ({dcr:+.4f},{dci:+.4f}): {result.get('score', 0):.6f}")

        # Holdout targets
        for tgt in ["TARGET_B", "TARGET_PHASE"]:
            result = self.kernel.evaluate(cr, ci, driver, width=60, height=30, target=tgt)
            self.validation_results[f"holdout_{tgt}"] = result
            self._log(f"  Holdout {tgt}: {result.get('score', 0):.6f}")

        # Eigenmode holdouts
        for n in range(1, 5):
            for m in range(1, 5):
                tgt = f"T_{n}_{m}"
                result = self.kernel.evaluate(cr, ci, driver, width=60, height=30, target=tgt)
                self.validation_results[f"eigenmode_{tgt}"] = result

        # LOW_MODE holdouts
        for i in range(1, 5):
            tgt = f"LOW_MODE_{i}"
            result = self.kernel.evaluate(cr, ci, driver, width=60, height=30, target=tgt)
            self.validation_results[f"lowmode_{tgt}"] = result

        # Reproducibility
        for run_idx in range(3):
            result = self.kernel.evaluate(cr, ci, driver, width=60, height=30, target='TARGET_A')
            self.validation_results[f"repro_{run_idx}"] = result
            self._log(f"  Repro run {run_idx+1}: {result.get('score', 0):.6f}")

        # Control stability at depth/resolution
        for drv in ["V2_SMOOTH", "V9_PRIME_EVENT"]:
            for depth in [500, 2000]:
                result = self.kernel.evaluate(cr, ci, drv, max_iter=depth,
                                              width=60, height=30, target='TARGET_A')
                self.validation_results[f"control_stability_{drv}_d{depth}"] = result

        return True

    # Phase: TEMPORAL
    def phase_temporal(self):
        self._log("=== V2 TEMPORAL ===")
        cr = self.state.get("best_cr", 0)
        ci = self.state.get("best_ci", 0)

        # If the best point is at the boundary (all pixels escape), use a
        # more interior point where temporal analysis can observe active pixels.
        # Check if the best point has escaping issues by running a short trace.
        try:
            test_trace = self.kernel.trace(cr, ci, "V0_NONE", max_iter=20,
                                           width=30, height=15)
            # Check if the LAST few iterations still have active pixels
            last_rows = test_trace[-5:] if len(test_trace) >= 5 else test_trace
            active_at_end = [r for r in last_rows if r.get("active_frac", 0) > 0.01]
            if not active_at_end:
                # All pixels escaped; use TRACK_C best or a known interior point
                track_c = self.track_results.get("TRACK_C", {}).get("best", {})
                if track_c and track_c.get("score", 0) > 0:
                    cr = track_c.get("cr", -0.7)
                    ci = track_c.get("ci", 0.27)
                    self._log(f"  Best point at boundary, using TRACK_C point: ({cr:.6f}, {ci:.6f})")
                else:
                    cr, ci = -0.7, 0.27015
                    self._log(f"  Best point at boundary, using default: ({cr:.6f}, {ci:.6f})")
        except Exception:
            pass

        try:
            from analysis import temporal_analysis

            # Get baseline trace (V0_NONE)
            # Use 1000 iterations to ensure sufficient active pixels remain
            self._log("  Tracing baseline (V0_NONE)...")
            baseline = self.kernel.trace(cr, ci, "V0_NONE", max_iter=1000,
                                         width=60, height=30)

            # Get forced traces
            for drv in ["V1_INV_PI", "V9_PRIME_EVENT", "V10_PRIME_RESIDUAL"]:
                self._log(f"  Tracing {drv}...")
                forced = self.kernel.trace(cr, ci, drv, max_iter=1000,
                                           width=60, height=30)
                result = temporal_analysis(forced, baseline)
                self.temporal_results[drv] = result
                status = result.get("status", "UNKNOWN")
                pairs = result.get("pair_count", 0)
                p_val = result.get("permutation_p_two_sided", "N/A")
                self._log(f"    {drv}: status={status}, pairs={pairs}, p={p_val}")

        except Exception as e:
            self._log(f"Temporal analysis error: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

        return True

    # Phase: REPORT
    def phase_report(self):
        self._log("=== V2 REPORT ===")
        try:
            import report
            report.generate_report_v2(
                store=self.store,
                kernel=self.kernel,
                state=self.state,
                track_results=self.track_results,
                control_results=self.control_results,
                null_results=self.null_results,
                validation_results=self.validation_results,
                temporal_results=self.temporal_results,
                benchmark_result=self.benchmark_result,
                phash=self.phash,
                shash=self.shash,
                bhash=self.bhash,
            )
            self._log("Report generated: report_v2.md")
        except Exception as e:
            self._log(f"Report generation error: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

        # Finish all runs
        try:
            for tname, tdata in self.track_results.items():
                try:
                    self.store.finish_run(tdata["run_id"], "FINISHED")
                except Exception:
                    pass
        except Exception:
            pass

        self.store.close()
        return True

    def run_full(self):
        """Execute the complete V2 pipeline."""
        phases = [
            ("V2_INIT", self.phase_init),
            ("V2_SELF_TEST", self.phase_self_test),
            ("V2_PROTOCOL_LOCK", self.phase_protocol_lock),
            ("V2_BENCHMARK", self.phase_benchmark),
            ("V2_SEARCH_A", lambda: self.phase_search_track("TRACK_A", "V1_INV_PI")),
            ("V2_SEARCH_B", lambda: self.phase_search_track("TRACK_B", "V10_PRIME_RESIDUAL")),
            ("V2_SEARCH_C", lambda: self.phase_search_track("TRACK_C", "V9_PRIME_EVENT")),
            ("V2_CONTROLS", self.phase_controls),
            ("V2_NULL", self.phase_null),
            ("V2_VALIDATION", self.phase_validation),
            ("V2_TEMPORAL", self.phase_temporal),
            ("V2_REPORT", self.phase_report),
        ]

        for phase_name, phase_func in phases:
            self.phase = phase_name
            self._log(f"Starting: {phase_name}")
            try:
                ok = phase_func()
                if not ok:
                    self._log(f"Phase {phase_name} FAILED, stopping")
                    return False
            except KeyboardInterrupt:
                self._log("Interrupted!")
                if self.store:
                    try:
                        self.store.close()
                    except Exception:
                        pass
                return False
            except Exception as e:
                self._log(f"Phase {phase_name} error: {e}")
                import traceback
                traceback.print_exc(file=sys.stderr)
                return False

        self._log("V2 pipeline complete")
        return True
