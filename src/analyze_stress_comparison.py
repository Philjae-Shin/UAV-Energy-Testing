"""
Stress Mission vs Competition Mission Comparison Analysis
Generates comparison figure for Chapter 4 of dissertation
"""
import json
import os
import matplotlib.pyplot as plt
import numpy as np

# Paths
STRESS_DIR = "data/stress_results"
COMP_DIR = "src/UAV-Testing-Competition/snippets/case_studies"
OUTPUT_DIR = "Dissertation"

def load_report(path):
    with open(path) as f:
        return json.load(f)

# Load stress mission reports
stress_files = {
    "Hover": os.path.join(STRESS_DIR, "stress_hover_energy_report.json"),
    "Zigzag": os.path.join(STRESS_DIR, "stress_zigzag_energy_report.json"),
    "Altitude": os.path.join(STRESS_DIR, "stress_altitude_energy_report.json"),
}

stress_data = {}
for name, path in stress_files.items():
    stress_data[name] = load_report(path)

# Load competition mission reports
comp_files = {}
for f in os.listdir(COMP_DIR):
    if f.endswith("_energy_report.json") and "wind" not in f:
        comp_files[f] = os.path.join(COMP_DIR, f)

comp_data = {}
for fname, path in sorted(comp_files.items()):
    label = fname.replace("_energy_report.json", "")
    comp_data[label] = load_report(path)

print("=== Stress Missions ===")
for name, d in stress_data.items():
    s = d["summary"]
    bugs = d["bugs"]
    bug_types = [b["type"] for b in bugs]
    print(f"  {name}: {s['flight_duration_sec']:.1f}s, "
          f"motor={s['avg_motor_output']:.0f} PWM, "
          f"efficiency={s['energy_efficiency']:.2f}%/min, "
          f"bugs={len(bugs)} ({', '.join(bug_types)})")

print("\n=== Competition Missions ===")
for name, d in comp_data.items():
    s = d["summary"]
    bugs = d["bugs"]
    bug_types = [b["type"] for b in bugs]
    print(f"  {name}: {s['flight_duration_sec']:.1f}s, "
          f"motor={s['avg_motor_output']:.0f} PWM, "
          f"efficiency={s['energy_efficiency']:.2f}%/min, "
          f"bugs={len(bugs)} ({', '.join(bug_types)})")

# Prepare comparison data
fig, axes = plt.subplots(2, 2, figsize=(12, 9))
fig.suptitle("Stress Missions vs Competition Missions: Energy Analysis Comparison",
             fontsize=14, fontweight='bold')

# Colors
stress_color = '#e74c3c'
comp_color = '#3498db'

# 1. Flight Duration
ax = axes[0, 0]
stress_durations = [stress_data[n]["summary"]["flight_duration_sec"] for n in ["Hover", "Zigzag", "Altitude"]]
comp_durations = [comp_data[n]["summary"]["flight_duration_sec"] for n in sorted(comp_data.keys())]
labels_s = ["Hover", "Zigzag", "Altitude"]
labels_c = [n.replace("mission", "M") for n in sorted(comp_data.keys())]
all_labels = labels_s + labels_c
all_durations = stress_durations + comp_durations
colors = [stress_color]*3 + [comp_color]*len(comp_durations)
bars = ax.bar(range(len(all_labels)), all_durations, color=colors, alpha=0.8)
ax.set_xticks(range(len(all_labels)))
ax.set_xticklabels(all_labels, rotation=45, ha='right')
ax.set_ylabel("Duration (s)")
ax.set_title("Flight Duration")
ax.axvline(x=2.5, color='gray', linestyle='--', alpha=0.5)

# 2. Avg Motor Output
ax = axes[0, 1]
stress_motors = [stress_data[n]["summary"]["avg_motor_output"] for n in ["Hover", "Zigzag", "Altitude"]]
comp_motors = [comp_data[n]["summary"]["avg_motor_output"] for n in sorted(comp_data.keys())]
all_motors = stress_motors + comp_motors
bars = ax.bar(range(len(all_labels)), all_motors, color=colors, alpha=0.8)
ax.set_xticks(range(len(all_labels)))
ax.set_xticklabels(all_labels, rotation=45, ha='right')
ax.set_ylabel("Avg Motor Output (PWM)")
ax.set_title("Average Motor Output")
ax.axvline(x=2.5, color='gray', linestyle='--', alpha=0.5)

# 3. Energy Efficiency
ax = axes[1, 0]
stress_eff = [stress_data[n]["summary"]["energy_efficiency"] for n in ["Hover", "Zigzag", "Altitude"]]
comp_eff = [comp_data[n]["summary"]["energy_efficiency"] for n in sorted(comp_data.keys())]
all_eff = stress_eff + comp_eff
bars = ax.bar(range(len(all_labels)), all_eff, color=colors, alpha=0.8)
ax.set_xticks(range(len(all_labels)))
ax.set_xticklabels(all_labels, rotation=45, ha='right')
ax.set_ylabel("Energy Efficiency (%/min)")
ax.set_title("Energy Consumption Rate")
ax.axvline(x=2.5, color='gray', linestyle='--', alpha=0.5)

# 4. Bug Count by Type
ax = axes[1, 1]
bug_types_list = ["energy_vampire", "motor_inefficiency", "drain_rate_spike"]
type_labels = ["Vampire", "Motor", "Drain Spike"]
type_colors = ['#e74c3c', '#f39c12', '#2ecc71']

stress_names = ["Hover", "Zigzag", "Altitude"]
comp_names = sorted(comp_data.keys())
all_names = stress_names + [n.replace("mission", "M") for n in comp_names]

x = np.arange(len(all_names))
width = 0.25

for i, (bt, tl, tc) in enumerate(zip(bug_types_list, type_labels, type_colors)):
    counts = []
    for n in stress_names:
        counts.append(sum(1 for b in stress_data[n]["bugs"] if b["type"] == bt))
    for n in comp_names:
        counts.append(sum(1 for b in comp_data[n]["bugs"] if b["type"] == bt))
    ax.bar(x + i*width - width, counts, width, label=tl, color=tc, alpha=0.8)

ax.set_xticks(x)
ax.set_xticklabels(all_names, rotation=45, ha='right')
ax.set_ylabel("Bug Count")
ax.set_title("Detected Bugs by Type")
ax.legend(fontsize=8)
ax.axvline(x=2.5, color='gray', linestyle='--', alpha=0.5)

# Add legend for stress vs competition
from matplotlib.patches import Patch
legend_elements = [Patch(facecolor=stress_color, alpha=0.8, label='Stress Missions'),
                   Patch(facecolor=comp_color, alpha=0.8, label='Competition Missions')]
fig.legend(handles=legend_elements, loc='upper right', fontsize=10,
           bbox_to_anchor=(0.98, 0.98))

plt.tight_layout(rect=[0, 0, 1, 0.93])
output_path = os.path.join(OUTPUT_DIR, "stress_comparison.png")
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"\nSaved: {output_path}")
plt.close()
