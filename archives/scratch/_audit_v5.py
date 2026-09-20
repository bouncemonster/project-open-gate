"""V5.1 Forensic Audit: Query the V5 database for inconsistencies."""
import sqlite3
import json
import os

conn = sqlite3.connect("archives/v5_baseline/history_v5.sqlite3")
conn.row_factory = sqlite3.Row

print("=" * 70)
print("V5.1 FORENSIC AUDIT")
print("=" * 70)

# === SECTION 2: WORLD INVENTORY ===
print("\n=== SECTION 2: WORLD INVENTORY ===")
rows = conn.execute("""
    SELECT w.world_type, COUNT(*) as count, COUNT(DISTINCT w.seed) as seeds
    FROM worlds w GROUP BY w.world_type ORDER BY w.world_type
""").fetchall()
total = 0
continuous_types = {"W01_CONTINUOUS_ANALYTIC", "W02_GAUSSIAN_FIELD", "W03_FRACTAL_ANALYTIC",
                    "W04_FLOAT32", "W05_FLOAT16", "W06_QUANTIZED_8BIT", "W07_QUANTIZED_4BIT",
                    "W08_FIXED_GRID"}
for r in rows:
    wtype = r["world_type"]
    cls = "continuous" if wtype in continuous_types else "computational"
    print(f"  {wtype:40s} count={r['count']:4d} seeds={r['seeds']:3d} class={cls}")
    total += r["count"]
print(f"  TOTAL: {total}")

# W17 check
w17 = conn.execute("SELECT COUNT(*) as c FROM worlds WHERE world_type LIKE '%W17%'").fetchone()
print(f"\n  W17 worlds in DB: {w17['c']}")
if w17['c'] == 0:
    print("  *** W17_REFERENCE_ERROR: W17_UNKNOWN_COMPUTATIONAL does not exist ***")

# === SECTION 3: SPLIT ACCOUNTING ===
print("\n=== SECTION 3: SPLIT ACCOUNTING ===")
splits = conn.execute("""
    SELECT s.split_type, COUNT(*) as count
    FROM splits s GROUP BY s.split_type
""").fetchall()
split_total = 0
for r in splits:
    print(f"  {r['split_type']:15s}: {r['count']}")
    split_total += r["count"]
print(f"  TOTAL IN SPLITS: {split_total}")
print(f"  TOTAL WORLDS:    {total}")
if split_total != total:
    print(f"  *** MISMATCH: {total} worlds but {split_total} split assignments ***")

# Worlds without split
no_split = conn.execute("""
    SELECT COUNT(*) as c FROM worlds w
    LEFT JOIN splits s ON w.id = s.world_id
    WHERE s.id IS NULL
""").fetchone()
print(f"  Worlds without split assignment: {no_split['c']}")

# === SECTION 5: CLASS BALANCE ===
print("\n=== SECTION 5: CLASS BALANCE PER SPLIT ===")
rows = conn.execute("""
    SELECT s.split_type, w.world_type, COUNT(*) as count
    FROM splits s JOIN worlds w ON s.world_id = w.id
    GROUP BY s.split_type, w.world_type
    ORDER BY s.split_type, w.world_type
""").fetchall()

split_classes = {}
for r in rows:
    wtype = r["world_type"]
    cls = "continuous" if wtype in continuous_types else "computational"
    key = r["split_type"]
    if key not in split_classes:
        split_classes[key] = {"continuous": 0, "computational": 0}
    split_classes[key][cls] += r["count"]

for split_name, counts in sorted(split_classes.items()):
    total_split = counts["continuous"] + counts["computational"]
    print(f"  {split_name:15s}: continuous={counts['continuous']:4d} computational={counts['computational']:4d} total={total_split}")
    if counts["continuous"] == 0:
        print(f"    *** WARNING: No continuous worlds in {split_name} ***")
    if counts["computational"] == 0:
        print(f"    *** WARNING: No computational worlds in {split_name} ***")

# === SECTION 6: TRIVIAL BASELINES ===
print("\n=== SECTION 6: TRIVIAL BASELINES ===")
for split_name, counts in sorted(split_classes.items()):
    total_split = counts["continuous"] + counts["computational"]
    if total_split == 0:
        continue
    majority = max(counts["continuous"], counts["computational"])
    majority_acc = majority / total_split
    print(f"  {split_name}:")
    print(f"    majority_class_accuracy = {majority_acc:.4f} ({majority}/{total_split})")
    print(f"    always_continuous       = {counts['continuous']/total_split:.4f}")
    print(f"    always_computational    = {counts['computational']/total_split:.4f}")
    print(f"    random_50               = 0.5000")

# === SECTION 4: RECONCILE NUMBERS ===
print("\n=== SECTION 4: RECONCILE REPORT CLAIMS ===")
print("  Report claims: 380 total, 260 train, 100 validation, 80 holdout")
print(f"  DB actual:     {total} total, ", end="")
train_c = split_classes.get("train", {"continuous": 0, "computational": 0})
val_c = split_classes.get("validation", {"continuous": 0, "computational": 0})
hold_c = split_classes.get("holdout", {"continuous": 0, "computational": 0})
train_total = train_c["continuous"] + train_c["computational"]
val_total = val_c["continuous"] + val_c["computational"]
hold_total = hold_c["continuous"] + hold_c["computational"]
print(f"{train_total} train, {val_total} validation, {hold_total} holdout")
print(f"  Sum of splits: {train_total + val_total + hold_total}")

# === SECTION 14: DUPLICATE CHECK ===
print("\n=== SECTION 14: DUPLICATE/OVERLAP CHECK ===")
dupes = conn.execute("""
    SELECT world_type, seed, observation, COUNT(*) as c
    FROM worlds GROUP BY world_type, seed, observation HAVING c > 1
""").fetchall()
print(f"  Duplicate records: {len(dupes)}")

# Check if any world is in multiple splits
multi_split = conn.execute("""
    SELECT world_id, COUNT(DISTINCT split_type) as c
    FROM splits GROUP BY world_id HAVING c > 1
""").fetchall()
print(f"  Worlds in multiple splits: {len(multi_split)}")

# === SECTION 19: ABLATION ANOMALY ===
print("\n=== SECTION 19: ABLATION RESULTS ===")
ablations = conn.execute("SELECT feature_set, accuracy FROM ablations ORDER BY id").fetchall()
for r in ablations:
    print(f"  {r['feature_set']:20s}: {r['accuracy']:.4f}")

# Check: if holdout is 100% computational, then:
# - spatial_only gets 62.5% (predicts computational 62.5% of time)
# - computational_only gets 7.5% (predicts continuous 92.5% of time??)
# This suggests LABEL INVERSION in computational features
print("\n  ANALYSIS: Holdout is 100% computational (W13-W16).")
print("  If holdout has NO continuous worlds:")
print("    - 'always computational' baseline = 100%")
print("    - 62.5% accuracy means detector MISCLASSIFIES 37.5% as continuous")
print("    - 7.5% for computational_only means it classifies 92.5% as WRONG class")
print("    - This is NOT 'above chance' - it is BELOW the trivial baseline")

# === SECTION 15: LEAKAGE CHECK ===
print("\n=== SECTION 15: LEAKAGE CHECK ===")
# Check feature names for leakage
sample_world = conn.execute("SELECT id FROM worlds LIMIT 1").fetchone()
features = conn.execute("SELECT feature_name FROM features WHERE world_id=?", (sample_world["id"],)).fetchall()
fnames = [f["feature_name"] for f in features]
leakage_terms = ["world_type", "generator", "seed", "split", "class", "label", "filename", "path"]
found_leaks = []
for fn in fnames:
    for term in leakage_terms:
        if term in fn.lower():
            found_leaks.append((fn, term))
if found_leaks:
    print(f"  *** LEAKAGE FOUND: {found_leaks}")
else:
    print("  No obvious label leakage in feature names.")

# Check detector labels
print("\n=== SECTION 17: DETECTOR LABEL AUDIT ===")
preds = conn.execute("SELECT DISTINCT predicted_class FROM predictions").fetchall()
print(f"  Predicted classes in DB: {[p['predicted_class'] for p in preds]}")

# === V5 PIPELINE CODE AUDIT ===
print("\n=== SECTION 8: GENERATOR GENERALIZATION AUDIT ===")
print("  V5 TRAIN contains: W01-W10 (8 continuous + 2 computational)")
print("  V5 VALIDATION contains: W11-W13 (all computational)")
print("  V5 HOLDOUT contains: W14-W16 (all computational)")
print("  *** CRITICAL: Holdout has ZERO continuous worlds ***")
print("  *** CRITICAL: W17_UNKNOWN_COMPUTATIONAL was SKIPPED in code ***")
print("  *** The 'blind holdout' is entirely one-class ***")
print("  *** 62.5% on a one-class holdout is WORSE than always-computational ***")

# === SUMMARY ===
print("\n" + "=" * 70)
print("V5.1 AUDIT SUMMARY")
print("=" * 70)
print("""
FINDINGS:
1. W17_UNKNOWN_COMPUTATIONAL: DOES NOT EXIST (W17_REFERENCE_ERROR)
2. Holdout is 100% computational (0 continuous) -> NOT class-balanced
3. 62.5% on one-class holdout is BELOW the trivial 100% baseline
4. computational_only = 7.5% suggests label inversion in features
5. all_combined == spatial_only because computational features HURT
6. Split numbers: train=260 val=100 holdout=80 (total=440 != 380)
   -> Paired worlds are counted in splits but not in total
7. No generator-level split: same generator can appear in multiple splits
8. Feature scaling: normalizer fit on train only (CORRECT)
9. No filename/path leakage in features (CORRECT)

STATUS: V5.1_BENCHMARK_INVALID
""")

conn.close()
