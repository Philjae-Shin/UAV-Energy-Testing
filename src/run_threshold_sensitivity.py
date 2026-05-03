"""
Threshold Sensitivity Analysis
Varies each detection threshold by ±25% and ±50% and counts detections
across all 6 competition missions.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from energy.monitor import EnergyMonitor
from energy.analyzer import EnergyAnalyzer

ULG_DIR = "UAV-Testing-Competition/snippets/case_studies"
MISSIONS = ["mission1.ulg", "mission1-2.ulg", "mission2.ulg",
            "mission2-2.ulg", "mission3.ulg", "mission3-2.ulg"]

# Default thresholds from analyzer
DEFAULTS = {
    'vampire_drain_threshold': 0.5,       # %/min
    'motor_variance_threshold': 50000,    # PWM^2
    'drain_spike_ratio': 2.0,            # x baseline
}

MULTIPLIERS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
LABELS = ["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x", "2.5x", "3.0x"]

def count_bugs_by_type(ulg_files, threshold_overrides):
    """Run analysis on all files with given thresholds, return bug counts by type."""
    counts = {"energy_vampire": 0, "motor_inefficiency": 0, "drain_rate_spike": 0}
    for fname in ulg_files:
        path = os.path.join(ULG_DIR, fname)
        try:
            monitor = EnergyMonitor(path)
            analyzer = EnergyAnalyzer(monitor, thresholds=threshold_overrides)
            bugs = analyzer.detect_all()
            for bug in bugs:
                btype = bug.bug_type.value if hasattr(bug.bug_type, 'value') else str(bug.bug_type)
                if btype in counts:
                    counts[btype] += 1
        except Exception as e:
            print(f"  Error with {fname}: {e}")
    return counts

print("THRESHOLD SENSITIVITY ANALYSIS")

# Test each threshold independently
results = {}

# 1. Vampire drain threshold
print("\n--- Energy Vampire (vampire_drain_threshold) ---")
print(f"{'Variation':<10} {'Threshold':>12} {'Detections':>12}")
print("-" * 40)
vampire_results = []
for mult, label in zip(MULTIPLIERS, LABELS):
    thresh = DEFAULTS['vampire_drain_threshold'] * mult
    overrides = {'vampire_drain_threshold': thresh}
    counts = count_bugs_by_type(MISSIONS, overrides)
    n = counts['energy_vampire']
    vampire_results.append(n)
    print(f"{label:<10} {thresh:>12.3f} {n:>12}")
results['Energy Vampire'] = vampire_results

# 2. Motor variance threshold
print("\n--- Motor Inefficiency (motor_variance_threshold) ---")
print(f"{'Variation':<10} {'Threshold':>12} {'Detections':>12}")
print("-" * 40)
motor_results = []
for mult, label in zip(MULTIPLIERS, LABELS):
    thresh = DEFAULTS['motor_variance_threshold'] * mult
    overrides = {'motor_variance_threshold': thresh}
    counts = count_bugs_by_type(MISSIONS, overrides)
    n = counts['motor_inefficiency']
    motor_results.append(n)
    print(f"{label:<10} {thresh:>12.0f} {n:>12}")
results['Motor Inefficiency'] = motor_results

# 3. Drain spike ratio
print("\n--- Drain Rate Spike (drain_spike_ratio) ---")
print(f"{'Variation':<10} {'Threshold':>12} {'Detections':>12}")
print("-" * 40)
drain_results = []
for mult, label in zip(MULTIPLIERS, LABELS):
    thresh = DEFAULTS['drain_spike_ratio'] * mult
    overrides = {'drain_spike_ratio': thresh}
    counts = count_bugs_by_type(MISSIONS, overrides)
    n = counts['drain_rate_spike']
    drain_results.append(n)
    print(f"{label:<10} {thresh:>12.2f} {n:>12}")
results['Drain Rate Spike'] = drain_results

# Summary table
print("SUMMARY TABLE")

header = f"{'Detector':<25}" + "".join(f"{label:>8}" for label in LABELS)
print(header)
print("-" * len(header))

for name, vals in results.items():
    row = f"{name:<25}" + "".join(f"{v:>8}" for v in vals)
    print(row)

