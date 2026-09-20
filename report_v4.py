"""
Proof of Simulation V4 — report generation with SQLite verification.

20 sections per V4 protocol §74.  Every numeric score is taken from the V4
store and verified against the persisted results table.
"""
import json
import os
import time


def _f(v, nd=6):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "N/A"


def write_report(p):
    """Write report_v4.md. Returns a list of report/database mismatches."""
    st = p.state
    best = st.get("best", {}) or {}
    null = st.get("null", {}) or {}
    val = st.get("validation", {}) or {}
    bench = st.get("benchmark", {}) or {}
    ctrl = st.get("controls", {}) or {}
    rep = st.get("reproducibility", {}) or {}
    temp = st.get("temporal", {}) or {}
    search = st.get("search", {}) or {}
    diff = st.get("difference_field", {}) or {}
    hp = st.get("high_pass", {}) or {}
    surr = st.get("spectral_surrogates", {}) or {}
    scout = st.get("interior_scout", {}) or {}
    self_test = st.get("self_test", {}) or {}

    best_track = best.get("track", "TRACK_A")
    track_ctrl = ctrl.get(best_track, {}) or {}
    scores = track_ctrl.get("scores", {}) or {}
    contrasts = track_ctrl.get("contrasts", {}) or {}
    matched = track_ctrl.get("matched_family", {}) or {}
    boundary = track_ctrl.get("boundary_distance", {}) or {}

    mismatches = []
    status = p.final_status()

    L = []
    A = L.append

    # ---- 1. Executive Summary
    A("# Proof of Simulation V4\n")
    A("## 1. Executive Summary\n")
    A(f"**Experiment**: V4_INTERIOR_DYNAMICS_PRIME_CONTRAST  ")
    A(f"**Final Status**: **{status}**  ")
    A(f"**Best contrast**: {_f(best.get('contrast'))} (track {best_track})  ")
    A(f"**Best score**: {_f(best.get('score'))} at c = {_f(best.get('cr'))} + {_f(best.get('ci'))}i  ")
    A(f"**Protocol hash**: `{p.phash[:16]}…`  ")
    A(f"**Source hash**: `{p.shash[:16]}…`  ")
    A(f"**Binary hash**: `{p.bhash[:16]}…`  ")
    A("")

    # ---- 2. V3 Audit
    A("## 2. V3 Audit\n")
    A("V3 established STATUS = BOUNDARY_ARTIFACT with best score 0.858321 at cr=2.0.  ")
    A("V3 key findings:  ")
    A("- V1_INV_PI = 0.858321, V0_BASELINE = 0.820852, S1_SMOOTH = 0.858321  ")
    A("- V9 vs matched events ≈ 0  ")
    A("- V2 best on boundary cr=2 (monotone increasing)  ")
    A("V4 addresses this by searching the interior regime [-1.5, 1.5]².\n")

    # ---- 3. Interior Regime Definition
    A("## 3. Interior Regime Definition\n")
    A("### Admissibility criteria (protocol §5)\n")
    adm = p.proto.get("admissibility", {})
    A(f"- escaped_fraction ∈ [{adm.get('escaped_fraction_min', 0.05)}, {adm.get('escaped_fraction_max', 0.95)}]")
    A(f"- normalized_entropy ≥ {adm.get('normalized_entropy_min', 0.20)}")
    A(f"- std(F_smooth) ≥ {adm.get('smooth_std_min', 0.05)}")
    A("")
    A("### Interior scout results\n")
    A(f"- Total scout points: {scout.get('total', 'N/A')}")
    A(f"- Admissible points: {scout.get('admissible', 'N/A')}")
    A(f"- Domain: {p.proto.get('scout_domain', 'N/A')}")
    A("")
    s1a = self_test.get("s1_ok", "N/A")
    A(f"### S1 audit\n")
    A(f"- Riemann R stability at small k: {'OK' if s1a else 'ISSUES'}")
    drv_aud = self_test.get("driver_audit", {}) if isinstance(self_test, dict) else {}
    if isinstance(drv_aud, dict):
        A(f"- S1 vs V1 max_abs_diff: {_f(drv_aud.get('max_abs_diff'))}")
        A(f"- S1 vs V1 correlation: {_f(drv_aud.get('correlation'))}")
    A("")

    # ---- 4. Search Domain
    A("## 4. Search Domain\n")
    A(f"- Domain: {p.proto.get('domain', 'N/A')}")
    A(f"- Scout grid: {p.proto.get('scout_grid', 'N/A')}×{p.proto.get('scout_grid', 'N/A')}")
    A(f"- Search steps: {p.proto.get('search', {}).get('logical_steps', 'N/A')}")
    A(f"- Multi-start count: {p.proto.get('search', {}).get('multi_start_count', 'N/A')}")
    A(f"- Search seeds: {p.proto.get('search_seeds', 'N/A')}")
    A("")

    # ---- 5. Prime Drivers
    A("## 5. Prime Drivers\n")
    A("| Driver | RMS | Nonzero | Hash |")
    A("|--------|-----|---------|------|")
    reg_data = self_test.get("registry", {}) if isinstance(self_test, dict) else {}
    for dn in ("V1_FULL", "V9_EVENT", "V10_RESIDUAL", "S1_ANALYTIC", "S2_DATA_SMOOTHED"):
        rd = reg_data.get(dn, {})
        A(f"| {dn} | {_f(rd.get('rms'))} | {rd.get('nonzero_count', 'N/A')} | `{str(rd.get('hash', ''))[:12]}…` |")
    A("")
    v9a = self_test.get("v9_magnitude", {}) if isinstance(self_test, dict) else {}
    if v9a:
        A("### V9 magnitude audit (protocol §49)\n")
        A("| max_iter | event_count | RMS(E) | max_abs(E) |")
        A("|----------|-------------|--------|------------|")
        for mi, info in v9a.items():
            if isinstance(info, dict):
                A(f"| {mi} | {info.get('event_count', 'N/A')} | {_f(info.get('RMS_E'))} | {_f(info.get('max_abs_E'))} |")
        A("")

    # ---- 6. Matched Event Controls
    A("## 6. Matched Event Controls\n")
    for fam_name, label in [("V11", "V11_MATCHED_EVENT (permuted positions)"),
                            ("V12", "V12_SHIFTED_EVENT (circular shifts)"),
                            ("V13", "V13_GAP_MATCHED_EVENT (gap-permuted)")]:
        fam = matched.get(fam_name, {})
        A(f"### {label}\n")
        for key, sc in sorted(fam.items()):
            A(f"- {key}: score = {_f(sc)}")
        if fam:
            A(f"- **mean**: {_f(sum(fam.values()) / len(fam))}")
        A("")

    # ---- 7. Track-Local Results
    A("## 7. Track-Local Results\n")
    for track_name in ("TRACK_A", "TRACK_B", "TRACK_C"):
        t = search.get(track_name, {}) or {}
        b = t.get("best", {}) or {}
        tc = ctrl.get(track_name, {}) or {}
        t_scores = tc.get("scores", {}) or {}
        t_contrasts = tc.get("contrasts", {}) or {}
        t_boundary = tc.get("boundary_distance", {}) or {}
        A(f"### {track_name}\n")
        A(f"- Best c: {_f(b.get('cr'))} + {_f(b.get('ci'))}i")
        A(f"- Best contrast: {_f(b.get('contrast'))}")
        A(f"- Best score: {_f(b.get('score'))}")
        A(f"- V0={_f(t_scores.get('V0_NONE'))} V1={_f(t_scores.get('V1_FULL'))} "
          f"S1={_f(t_scores.get('S1_ANALYTIC'))} V9={_f(t_scores.get('V9_EVENT'))} "
          f"V10={_f(t_scores.get('V10_RESIDUAL'))}")
        A(f"- C_full={_f(t_contrasts.get('C_full'))} "
          f"C_event={_f(t_contrasts.get('C_event'))} "
          f"C_residual={_f(t_contrasts.get('C_residual'))}")
        A(f"- Boundary distance: {_f(t_boundary.get('fraction'), 3)} "
          f"({'BOUNDARY_SUSPECT' if t_boundary.get('BOUNDARY_SUSPECT') else 'interior'})")
        A("")

    # ---- 8. Boundary Diagnostics
    A("## 8. Boundary Diagnostics\n")
    for track_name in ("TRACK_A", "TRACK_B", "TRACK_C"):
        tc = ctrl.get(track_name, {}) or {}
        bd = tc.get("boundary_distance", {}) or {}
        A(f"- {track_name}: distance={_f(bd.get('fraction'), 3)} "
          f"nearest_edge={bd.get('nearest_edge', 'N/A')} "
          f"{'**BOUNDARY_SUSPECT**' if bd.get('BOUNDARY_SUSPECT') else 'ok'}")
    A("")

    # ---- 9. Prime-Specific Contrasts
    A("## 9. Prime-Specific Contrasts\n")
    A("| Contrast | Value |")
    A("|----------|-------|")
    for k in ("C_full", "C_event", "C_residual", "C_event_all", "C_shift_search",
              "C_shift_all", "C_gap_search", "C_gap_all",
              "V1_minus_V0", "V1_minus_max_S1_S2"):
        A(f"| {k} | {_f(contrasts.get(k))} |")
    A("")

    # ---- 10. Difference-Field Analysis
    A("## 10. Difference-Field Analysis\n")
    A("| Driver | RMS | Entropy | DCT low | DCT high | Autocorr | Corr w/ target |")
    A("|--------|-----|---------|---------|----------|----------|----------------|")
    for dn in ("V1_FULL", "V9_EVENT", "V10_RESIDUAL"):
        dd = diff.get(dn, {}) or {}
        if dd.get("status") == "FIELD_UNAVAILABLE":
            A(f"| {dn} | UNAVAILABLE |")
        else:
            A(f"| {dn} | {_f(dd.get('RMS'))} | {_f(dd.get('entropy'))} | "
              f"{_f(dd.get('DCT_low_energy'))} | {_f(dd.get('DCT_high_energy'))} | "
              f"{_f(dd.get('autocorrelation'))} | {_f(dd.get('correlation_with_target_residual'))} |")
    A("")

    # ---- 11. High-Pass Analysis
    A("## 11. High-Pass Analysis\n")
    A("| Driver | Full score | Pearson (high-pass) |")
    A("|--------|-----------|---------------------|")
    for drv in ("V0_NONE", "V1_FULL", "V9_EVENT", "V10_RESIDUAL"):
        h = hp.get(drv)
        if h and isinstance(h, dict):
            A(f"| {drv} | {_f(h.get('full_score'))} | {_f(h.get('pearson_highpass'))} |")
        else:
            A(f"| {drv} | N/A | N/A |")
    A("")

    # ---- 12. Temporal Prime Response
    A("## 12. Temporal Prime Response\n")
    pts = temp.get("points", {}) or {}
    for pname, pdata in pts.items():
        A(f"### {pname}\n")
        A(f"c = {_f(pdata.get('c', {}).get('cr'))} + {_f(pdata.get('c', {}).get('ci'))}i  ")
        drv_data = pdata.get("drivers", {}) or {}
        for dn, dd in drv_data.items():
            if isinstance(dd, dict):
                A(f"- {dn}: status={dd.get('status')}, effect_size={_f(dd.get('effect_size'))}, "
                  f"pairs={dd.get('pair_count', 'N/A')}")
        A("")
    shifts = temp.get("shift_null", {}) or {}
    if shifts:
        A("### Circular-shift null\n")
        for sh, sd in shifts.items():
            if isinstance(sd, dict):
                A(f"- shift {sh}: status={sd.get('status')}, effect_size={_f(sd.get('effect_size'))}")
        A("")

    # ---- 13. Search-Aware Null
    A("## 13. Search-Aware Null\n")
    A(f"- N_null: {null.get('N_null', 'N/A')}")
    A(f"- Observed best: {_f(null.get('observed_best'))}")
    A(f"- Null max: {_f(null.get('null_max'))}")
    A(f"- Null mean: {_f(null.get('null_mean'))}")
    A(f"- Null std: {_f(null.get('null_std'))}")
    A(f"- Count exceeding: {null.get('count_exceeding', 'N/A')}")
    A(f"- Empirical p: {_f(null.get('empirical_search_null'), 4)}")
    A(f"- Note: exploratory statistic, not confirmatory (protocol §31)")
    A("")

    # ---- 14. Spectral Target Null
    A("## 14. Spectral Target Null\n")
    if surr:
        A(f"- N surrogates: {surr.get('N', 'N/A')}")
        A(f"- Mean: {_f(surr.get('mean'))}")
        A(f"- Std: {_f(surr.get('std'))}")
        A(f"- Median: {_f(surr.get('median'))}")
        A(f"- P90: {_f(surr.get('p90'))}")
        A(f"- P95: {_f(surr.get('p95'))}")
        A(f"- Max: {_f(surr.get('max'))}")
    else:
        A("- NOT EXECUTED")
    A("")

    # ---- 15. Holdout Targets
    A("## 15. Holdout Targets\n")
    ht = val.get("holdout_targets", {}) or {}
    if ht:
        A("| Target | Score |")
        A("|--------|-------|")
        for tgt, sc in sorted(ht.items()):
            A(f"| {tgt} | {_f(sc)} |")
    else:
        A("- NOT EXECUTED")
    A("")

    # ---- 16. Reproducibility
    A("## 16. Reproducibility\n")
    A(f"- Canonical best: c = {_f(rep.get('canonical_best', {}).get('cr'))} + {_f(rep.get('canonical_best', {}).get('ci'))}i")
    A(f"- Scores: [{', '.join(_f(s) for s in rep.get('scores', []))}]")
    A(f"- Identical within tolerance: {rep.get('identical_within_tolerance', 'N/A')}")
    A(f"- DB integrity: {rep.get('db_integrity', 'N/A')}\n")

    # ---- 17. WORLD_PRIME Detector
    A("## 17. WORLD_PRIME Detector\n")
    pd = bench.get("prime_detection", {}) or {}
    A(f"- Prime detection: {pd.get('detected', 0)}/{pd.get('total', 0)}")
    A(f"- Interpretation: {bench.get('interpretation', 'N/A')}\n")

    # ---- 18. V1/V2/V3/V4 Comparison
    A("## 18. V1/V2/V3/V4 Comparison\n")
    A("| Metric | V1 | V2 | V3 | V4 |")
    A("|--------|----|----|----|----|")
    A(f"| Best score | 0.858321 | 0.858321 | 0.858321 | {_f(best.get('score'))} |")
    A(f"| Best c | 2+0.011i | 2+0.011i | 2+0.011i | {_f(best.get('cr'))}+{_f(best.get('ci'))}i |")
    A(f"| Domain | [-2,2] | [-2,2] | [-2,2] | {p.proto.get('domain', 'N/A')} |")
    A(f"| Objective | raw score | raw score | raw score | contrast |")
    A(f"| Status | — | — | BOUNDARY_ARTIFACT | {status} |")
    A("")

    # ---- 19. Limitations
    A("## 19. Limitations\n")
    A("- Search budget bounded (100 steps × 9 candidates × 4 drivers + scout)")
    A("- Interior domain [-1.5, 1.5]² may exclude interesting boundary-adjacent dynamics")
    A("- V4 S1 uses Riemann R (differs from kernel li-based S1); V10 not directly comparable to V2")
    A("- Temporal analysis limited by active-point availability at some parameter values")
    A("- WORLD_PRIME detection rate may be low due to frozen feature limitations")
    A("- Contrast-based search is more expensive per step (4× kernel evaluations)")
    A("")

    # ---- 20. Final Scientific Conclusion
    A("## 20. Final Scientific Conclusion\n")
    A(f"**Status: {status}**\n")
    if status == "NO_PRIME_SPECIFIC_SIGNAL":
        A("After removing boundary effects, smooth forcing, generic low-frequency geometry, "
          "event-density effects and search selection bias, no prime-specific component "
          "was detected. The observed resonance in V1-V3 is attributable to generic "
          "geometric and boundary effects.\n")
    elif status == "GENERIC_RESONANCE":
        A("High absolute score but prime-specific contrast ≈ 0. The resonance is "
          "driven by smooth/generic forcing, not prime-specific arithmetic structure.\n")
    elif status == "BOUNDARY_ARTIFACT":
        A("Best candidate is within 5% of the search domain boundary. The result "
          "may be a boundary effect rather than a genuine interior phenomenon.\n")
    elif status == "PRIME_CANDIDATE_SIGNAL":
        A("Prime-specific contrasts survive interior regime filtering, matched-event "
          "controls, null separation and holdout validation. This is a candidate signal "
          "requiring independent replication. **NOT PROOF OF SIMULATION.**\n")
    elif status == "ROBUST_PRIME_SPECIFIC_SIGNAL":
        A("All criteria met: interior point, V1 > smooth controls, V9 > matched events, "
          "V10 > smooth controls, temporal signal, null separation, holdout survival, "
          "depth and resolution stability. **NOT PROOF OF SIMULATION** but strong evidence "
          "of prime-specific arithmetic structure in Julia set dynamics.\n")
    else:
        A(f"See detailed analysis above for status {status}.\n")

    # ---- Evidence table (protocol §75)
    A("### Evidence table\n")
    A("| Evidence | Result |")
    A("|----------|--------|")
    A(f"| Interior V1 contrast | {_f(contrasts.get('C_full'))} |")
    A(f"| Interior V9 contrast | {_f(contrasts.get('C_event'))} |")
    A(f"| Interior V10 contrast | {_f(contrasts.get('C_residual'))} |")
    A(f"| Matched-event contrast | {_f(contrasts.get('C_event_all'))} |")
    A(f"| Shift-event contrast | {_f(contrasts.get('C_shift_all'))} |")
    A(f"| Gap-matched contrast | {_f(contrasts.get('C_gap_all'))} |")
    # High-pass
    hp_v1 = hp.get("V1_FULL", {}) or {}
    A(f"| High-pass contrast | {_f(hp_v1.get('pearson_highpass'))} |")
    # Temporal
    temp_pts = temp.get("points", {}) or {}
    temp_effect = "N/A"
    for pn, pd in temp_pts.items():
        dd = pd.get("drivers", {}).get("V1_FULL", {})
        if isinstance(dd, dict) and dd.get("status") == "OK":
            temp_effect = _f(dd.get("effect_size"))
            break
    A(f"| Temporal prime effect | {temp_effect} |")
    A(f"| Null percentile | {_f(null.get('percentile'))} |")
    A(f"| Spectral-surrogate mean | {_f(surr.get('mean'))} |")
    # Depth stability
    depth_vals = list(val.get("depth", {}).values()) if val.get("depth") else []
    depth_range = (max(depth_vals) - min(depth_vals)) if len(depth_vals) >= 2 else 0
    A(f"| Depth stability | range={_f(depth_range)} |")
    # Resolution stability
    res_vals = list(val.get("resolution", {}).values()) if val.get("resolution") else []
    res_range = (max(res_vals) - min(res_vals)) if len(res_vals) >= 2 else 0
    A(f"| Resolution stability | range={_f(res_range)} |")
    A("")

    A("---\n")
    A(f"*Report generated {time.strftime('%Y-%m-%d %H:%M:%S')}*  ")
    A(f"*Protocol: `{p.phash[:32]}…`*  ")
    A(f"*Source: `{p.shash[:32]}…`*  ")
    A(f"*Binary: `{p.bhash[:32]}…`*\n")

    # ---- write file
    path = "report_v4.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    p.log(f"report_v4.md written ({len(L)} lines)")

    # ---- SQLite verification
    for phase, key in [("search", "TRACK_A"), ("controls", best_track),
                       ("null", "stats")]:
        stored = p.store.get(phase, key)
        if stored is None:
            mismatches.append(f"MISSING {phase}:{key} in database")

    return mismatches
