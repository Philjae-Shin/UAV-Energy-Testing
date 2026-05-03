# Energy-Aware Testing for UAV Software

Detecting energy bugs through simulation-based analysis of PX4 ULog telemetry.

This repository accompanies the BSc Computer Science (COMS30045) dissertation
*"Energy-Aware Testing for UAV Software: Detecting Energy Bugs through
Simulation-Based Analysis"* by **Philjae (Henry) Shin**, supervised by
Dr Kerstin Eder (University of Bristol).

The framework adds a host-side energy-analysis layer to the existing PX4
SITL / Aerialist test pipeline. It does not modify PX4 or Aerialist, it
consumes the `.ulg` files they produce and detects four classes of
energy anomaly (Energy Vampire, Voltage Anomaly, Motor Inefficiency,
Drain Rate Spike), then applies a phase-aware filter to separate
startup artefacts from in-flight anomalies. Across 9 SITL missions the
framework reports 27 raw candidates, of which 18 are removed as
arming/take-off artefacts, leaving 9 operational candidates — all Drain
Rate Spikes that extend into early cruise.

> *Section, table, and figure numbers in this README refer to the
> as-submitted version of the dissertation.*

---

## 1. Dependencies and installation

Tested on **Python 3.10**. Stage 1 (running new SITL flights yourself)
additionally requires Docker and the Aerialist image.

```bash
git clone <THIS-REPO-URL>
cd COMS30045_Individual_Project_Submisssion

python3 -m venv .venv && source .venv/bin/activate    # optional
pip install -r src/requirements.txt
```

`src/requirements.txt` pins `pandas`, `numpy`, `pyulog`, and
`matplotlib`. For Stage 1 follow `src/Aerialist/README.md`.

---

## 2. Reproduction

Pre-generated `.ulg` files, JSON reports, and figures are bundled, so
the dissertation results can be verified without re-running the SITL
simulator. Each command below states its expected working directory
explicitly because the scripts use a mix of `src/`-relative and
repo-root-relative paths.

### 2.1 Per-mission energy analysis (Stage 2a + 2b, §3.1–§3.3)

From `src/`:

```bash
# All six SBFT case-study missions
python3 run_energy_analysis.py --dir UAV-Testing-Competition/snippets/case_studies/

# A single .ulg
python3 run_energy_analysis.py UAV-Testing-Competition/snippets/case_studies/mission1.ulg
```

Writes `*_energy_report.json`, `*_energy_plot.png`, and
`*_bug_timeline.png` next to each input. Reproduces Table 4.1 (six
missions, three detections each).

### 2.2 Threshold sensitivity sweep (§4.3, Table 4.2)

From `src/`:

```bash
python3 run_threshold_sensitivity.py
```

Sweeps each detector threshold over `[0.25×, 0.5×, 0.75×, 1.0×, 1.25×,
1.5×, 2.0×, 2.5×, 3.0×]` of the default value across all six
competition missions.

### 2.3 Phase-aware filtering (Stage 2c, §4.5, Table 4.4)

From `src/`:

```bash
python3 phase_aware_analysis.py
```

> **Reproducibility caveat.** This script contains absolute paths
> hard-coded for the development machine (the `MISSIONS` dictionary at
> lines 267–277 and the `output_dir` / `dissertation_dir` literals at
> lines 444–447). The bundled outputs in `src/results/phase_aware/`
> already correspond to the reported 27 → 9 result; to rerun on a
> different machine those paths must be edited to match the local
> repository location.

### 2.4 Synthetic bug injection (§4.6, Table 4.5)

From `src/`:

```bash
python3 bug_injection_experiment.py
```

Reads `UAV-Testing-Competition/snippets/case_studies/mission1.ulg`,
runs the four injection scenarios (Vampire, Voltage Drop, Motor
Imbalance, Drain Spike) plus a clean control, and reports aggregate
precision = 0.20, recall = 0.75, F1 = 0.32 across the four injections.

### 2.5 Custom stress missions (§4.4, Table 4.3) (Takes long time!)

The three `.plan` mission descriptions live in
`src/experiments/stress_missions/`. Static Aerialist test wrappers
(`stress_hover.yaml`, `stress_zigzag.yaml`, `stress_altitude.yaml`) are
included for convenience and are byte-equivalent to what
`run_stress_missions.sh` generates from `mission1.yaml` at runtime.

To re-run inside an Aerialist Docker container, from the repository
root:

```bash
mkdir -p data/stress_results
docker pull skhatiri/aerialist     # or: docker build -t skhatiri/aerialist src/Aerialist

docker run -it --rm \
  -v "$(pwd)/src/experiments/stress_missions:/src/aerialist/stress_plans:ro" \
  -v "$(pwd)/src/experiments/run_stress_missions.sh:/src/aerialist/run_stress_missions.sh:ro" \
  -v "$(pwd)/data/stress_results:/src/aerialist/results" \
  skhatiri/aerialist \
  bash -c "cd /src/aerialist && bash run_stress_missions.sh"
```

The pre-generated logs and reports are already in
`data/stress_results/` and `src/results/stress_missions/`.

---

## 3. Directory layout

```
COMS30045_Individual_Project_Submisssion/
├── README.md                                   
│
├── data/
│   └── stress_results/                         # (mine) bundled outputs for the 3 stress missions
│       ├── stress_{hover,zigzag,altitude}.ulg
│       ├── stress_{hover,zigzag,altitude}_energy_report.json
│       ├── stress_{hover,zigzag,altitude}_energy_plot.png
│       ├── stress_{hover,zigzag,altitude}_bug_timeline.png
│       └── energy_summary.csv
│
└── src/
    ├── requirements.txt                        # (mine) Python dependencies
    │
    ├── energy/                                 # (mine) framework — Stages 2a / 2b
    │   ├── monitor.py                          #   EnergyMonitor
    │   ├── analyzer.py                         #   EnergyAnalyzer
    │   ├── visualizer.py                       #   EnergyVisualizer
    │   └── __init__.py
    │
    ├── phase_aware_analysis.py                 # (mine) Stage 2c — PhaseClassifier, PhaseAwareAnalyzer
    ├── bug_injection_experiment.py             # (mine) ModifiedEnergyMonitor + BugInjectionExperiment
    ├── run_energy_analysis.py                  # (mine) batch CLI for Stages 2a + 2b
    ├── run_threshold_sensitivity.py            # (mine) threshold sweep over §4.3 multipliers
    ├── aerialist_energy_runner.py              # (mine) Post-hoc mode
    │
    ├── experiments/                            # (mine) stress-mission assets
    │   ├── run_stress_missions.sh              #   in-container driver
    │   └── stress_missions/
    │       ├── stress_{hover,zigzag,altitude}.plan   # QGroundControl mission descriptions
    │       └── stress_{hover,zigzag,altitude}.yaml   # static Aerialist test wrappers
    │
    ├── results/                                # (mine) bundled outputs of the scripts above
    │   ├── bug_injection/                      #   Table 4.5 — injection metrics
    │   │   ├── bug_injection_report.json
    │   │   ├── bug_injection_results.png
    │   │   ├── metrics.csv
    │   │   └── metrics_table.tex
    │   ├── energy/                             #   per-mission energy reports + plots (Stages 2a/2b)
    │   ├── phase_aware/                        #   Table 4.4 — phase-aware filtering
    │   │   ├── comparison_table.csv
    │   │   └── phase_aware_analysis_report.json
    │   ├── stress_missions/                    #   stress mission JSON reports + energy_summary.csv
    │   └── demo/                               #   illustrative plots used during development
    │
    ├── Aerialist/                              # UPSTREAM — skhatiri/Aerialist (PX4 SITL test bench)
    │
    └── UAV-Testing-Competition/                # UPSTREAM — skhatiri/UAV-Testing-Competition, EXCEPT:
        └── snippets/
            ├── energy_testcase.py              # (mine) EnergyTestCase
            └── testcase.py                     # (mine) EnergyTestCase(TestCase)
```

`src/Aerialist/` and `src/UAV-Testing-Competition/` are the upstream
projects on which the framework depends; their original READMEs and
licences remain inside their respective folders. The two files in
`src/UAV-Testing-Competition/snippets/` listed above are mine — they
live there because they need to subclass the SBFT `TestCase` class.

---

## 4. Mapping to the dissertation

### 4.1 Modules (dissertation Table 3.1)

| File | Class | Responsibility |
|---|---|---|
| `src/energy/monitor.py` | `EnergyMonitor` | ULog parsing, data extraction, resampling |
| `src/energy/analyzer.py` | `EnergyAnalyzer` | Bug-detection algorithms, threshold management |
| `src/energy/visualizer.py` | `EnergyVisualizer` | Plot generation, bug highlighting |

### 4.2 Detectors (dissertation §3.3)

| Detector | Default threshold | Tuned in `EnergyAnalyzer.THRESHOLDS` |
|---|---|---|
| Energy Vampire | motor < 1200 PWM **and** drain > 0.5 %/min, ≥ 1.5 s | `vampire_motor_threshold`, `vampire_drain_threshold` |
| Voltage Anomaly | rolling 5-second voltage range > 0.5 V | `voltage_drop_threshold`, `voltage_drop_window` |
| Motor Inefficiency | variance of 4 PWM outputs > 50 000 PWM² | `motor_variance_threshold` |
| Drain Rate Spike | drain rate > 2.0 × flight-median | `drain_spike_ratio` |

### 4.3 Headline numbers

| Result | Where | Reproduction |
|---|---|---|
| 6 missions × 3 detections = 18 raw candidates | Table 4.1 | §2.1 above |
| Threshold sensitivity stable for Vampire, sharp drop for Motor at ≥ 2.5×, gradual for Spike | Table 4.2 | §2.2 above |
| 9 missions × 3 = 27 raw → 18 startup-only removed (67%) → 9 retained | Table 4.4 | §2.3 above |
| Synthetic injection: 3/4 detected; aggregate P = 0.20, R = 0.75, F1 = 0.32 | Table 4.5 | §2.4 above |
| No Voltage Anomalies on unmodified SITL logs | Discussion / Limitations of Chapter 4 | (PX4 SITL battery-model artefact) |

### 4.4 External dependencies (dissertation *Supporting Technologies*)

* **PX4-Autopilot** — SITL flight-controller firmware producing the
  `.ulg` files. <https://github.com/PX4/PX4-Autopilot>
* **Aerialist** — Docker-based PX4/Gazebo test bench used in Stage 1.
  <https://github.com/skhatiri/Aerialist>
* **SBFT UAV Testing Competition** — source of the six baseline mission
  scenarios and case-study `.ulg` files.
  <https://github.com/skhatiri/UAV-Testing-Competition>
* **pyulog** — Python library used (read-only) to parse PX4 binary
  logs. <https://github.com/PX4/pyulog>

---

## 5. Author and licence

Author: **Philjae (Henry) Shin** — University of Bristol, BSc Computer
Science (COMS30045), 2026.

The code authored for this project is submitted for assessment as part
of the COMS30045 dissertation. Upstream components (`src/Aerialist/`,
`src/UAV-Testing-Competition/`, `pyulog`, PX4) retain their original
licences inside their respective folders.