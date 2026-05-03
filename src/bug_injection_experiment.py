"""
Bug Injection Experiment for UAV Energy Testing Framework

This script creates synthetic energy bugs in real ULog flight data and measures
the precision and recall of the energy detection framework.

Injected Bugs:
1. Energy Vampire: increased drain, t=60--70s, multiplier=2.5
2. Voltage Drop: Sudden 0.8V drop over 3 seconds (0.8 V drop, t=80--83s)
3. Motor Imbalance: High motor variance (imbalance factor=0.6, t=50--55s)
4. Drain Spike: 4x median drain rate (drain multiplier=4.0, t=70--75s)
5. Clean Section: No injection control (t=40-80s)

Author: Henry
Date: 2026-03-02
"""

# 55555

import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from energy.monitor import EnergyMonitor
from energy.analyzer import EnergyAnalyzer, EnergyBugType


@dataclass
class InjectedBug:
    """Represents an injected synthetic bug."""
    bug_type: str
    time_start: float
    time_end: float
    description: str


class ModifiedEnergyMonitor(EnergyMonitor):
    """
    Extended EnergyMonitor that allows modification of energy profile data.
    Used to inject synthetic bugs into real flight data.
    """

    def __init__(self, log_file: str):
        """Initialize with a ULog file and prepare for modifications."""
        super().__init__(log_file)
        self._modified_profile: Optional[pd.DataFrame] = None
        self._injections: List[InjectedBug] = []

    def get_energy_profile(self, resample_sec: float = 1.0) -> pd.DataFrame:
        """Get energy profile, using modified version if injections exist."""
        if self._modified_profile is not None:
            return self._modified_profile.copy()
        return super().get_energy_profile(resample_sec)

    def inject_vampire_bug(self, time_start: float, time_end: float,
                          drain_multiplier: float = 2.5) -> None:
        """
        Inject energy vampire: high drain during low motor activity.

        Args:
            time_start: Start time in seconds
            time_end: End time in seconds
            drain_multiplier: Multiplier for drain rate during the period
        """
        if self._modified_profile is None:
            self._modified_profile = super().get_energy_profile()

        profile = self._modified_profile
        mask = (profile['time_sec'] >= time_start) & (profile['time_sec'] <= time_end)

        # Calculate baseline drain (median from entire flight)
        baseline_drain = profile['remaining_pct'].diff().abs().mean()

        # Artificially increase drain rate by modifying remaining_pct
        drain_per_sec = baseline_drain * drain_multiplier

        indices = np.where(mask)[0]
        for i, idx in enumerate(indices):
            profile.loc[idx, 'remaining_pct'] -= drain_per_sec * (i + 1)

        # Ensure remaining never goes below 0
        profile.loc[profile['remaining_pct'] < 0, 'remaining_pct'] = 0

        self._injections.append(InjectedBug(
            bug_type="energy_vampire",
            time_start=time_start,
            time_end=time_end,
            description=f"Energy vampire: {drain_multiplier}x drain during low motor activity"
        ))

    def inject_voltage_drop(self, time_start: float, duration: float,
                           drop_magnitude: float = 0.8) -> None:
        """
        Inject voltage anomaly: sudden voltage drop.

        Args:
            time_start: Start time in seconds
            duration: Duration of voltage drop in seconds
            drop_magnitude: Voltage drop magnitude in volts
        """
        if self._modified_profile is None:
            self._modified_profile = super().get_energy_profile()

        profile = self._modified_profile
        time_end = time_start + duration
        mask = (profile['time_sec'] >= time_start) & (profile['time_sec'] <= time_end)

        # Create smooth voltage drop
        time_in_window = profile.loc[mask, 'time_sec'] - time_start
        drop_curve = drop_magnitude * (time_in_window / duration)  # Linear drop

        profile.loc[mask, 'voltage_v'] -= drop_curve.values

        self._injections.append(InjectedBug(
            bug_type="voltage_anomaly",
            time_start=time_start,
            time_end=time_end,
            description=f"Voltage drop: {drop_magnitude}V over {duration}s"
        ))

    def inject_motor_imbalance(self, time_start: float, time_end: float,
                               imbalance_factor: float = 0.6) -> None:
        """
        Inject motor inefficiency: high variance across motor outputs.

        Args:
            time_start: Start time in seconds
            time_end: End time in seconds
            imbalance_factor: How much to skew motors (0-1, where 1 = max skew)
        """
        if self._modified_profile is None:
            self._modified_profile = super().get_energy_profile()

        profile = self._modified_profile
        motor_df = self.get_motor_data()

        mask = (motor_df['time_sec'] >= time_start) & (motor_df['time_sec'] <= time_end)
        motor_cols = [c for c in motor_df.columns if c.startswith('output[')]

        if len(motor_cols) < 4:
            return

        # Pandas 2.x rejects assigning float64 arrays into float32 ULog columns.
        # Convert once so injected motor values can be assigned consistently.
        motor_df[motor_cols] = motor_df[motor_cols].astype('float64')

        # Get original values
        original_avg = motor_df.loc[mask, motor_cols].mean(axis=1).values

        # Create imbalanced outputs with pattern [-1, -0.3, 0.3, 1]
        base_deviation = original_avg * imbalance_factor
        deviation_pattern = np.array([-1, -0.3, 0.3, 1])

        for i, col in enumerate(motor_cols):
            new_values = original_avg + (deviation_pattern[i] * base_deviation)
            motor_df.loc[mask, col] = np.maximum(new_values, 900)

        # Recalculate average motor output
        motor_df['avg_output'] = motor_df[motor_cols].mean(axis=1)

        # Update profile's motor_avg
        profile_motor_avg = np.interp(
            profile['time_sec'],
            motor_df['time_sec'],
            motor_df['avg_output']
        )
        profile['motor_avg'] = profile_motor_avg

        self._injections.append(InjectedBug(
            bug_type="motor_inefficiency",
            time_start=time_start,
            time_end=time_end,
            description=f"Motor imbalance: {imbalance_factor} skew factor"
        ))

    def inject_drain_spike(self, time_start: float, time_end: float,
                          spike_multiplier: float = 4.0) -> None:
        """
        Inject drain rate spike: sudden increase in energy consumption.

        Args:
            time_start: Start time in seconds
            time_end: End time in seconds
            spike_multiplier: Multiplier for baseline drain rate
        """
        if self._modified_profile is None:
            self._modified_profile = super().get_energy_profile()

        profile = self._modified_profile
        mask = (profile['time_sec'] >= time_start) & (profile['time_sec'] <= time_end)

        # Calculate baseline drain (median from entire flight)
        baseline_drain = profile['remaining_pct'].diff().abs().median()

        # Spike drain
        spike_drain = baseline_drain * spike_multiplier

        indices = np.where(mask)[0]
        for i, idx in enumerate(indices):
            profile.loc[idx, 'remaining_pct'] -= spike_drain * (i + 1)

        # Ensure remaining never goes below 0
        profile.loc[profile['remaining_pct'] < 0, 'remaining_pct'] = 0

        self._injections.append(InjectedBug(
            bug_type="drain_rate_spike",
            time_start=time_start,
            time_end=time_end,
            description=f"Drain spike: {spike_multiplier}x baseline"
        ))

    def get_injections(self) -> List[InjectedBug]:
        """Return list of injected bugs."""
        return self._injections


class BugInjectionExperiment:
    """
    Orchestrates the bug injection experiment:
    1. Load real ULog data
    2. Create modified versions with injected bugs
    3. Run detectors on each version
    4. Calculate precision, recall, F1
    5. Generate reports and visualizations
    """

    def __init__(self, log_file: str, output_dir: str = "results/bug_injection"):
        """
        Initialize experiment.

        Args:
            log_file: Path to ULog file
            output_dir: Directory for output files
        """
        self.log_file = log_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.scenarios: Dict[str, Tuple[ModifiedEnergyMonitor, List[InjectedBug]]] = {}
        self.detection_results: Dict[str, List] = {}
        self.metrics: Dict[str, Dict] = {}

    def create_scenarios(self) -> None:
        """Create all bug injection scenarios."""
        print("Creating bug injection scenarios...")

        # Scenario 1: Energy Vampire (t=60-70s)
        monitor_vampire = ModifiedEnergyMonitor(self.log_file)
        monitor_vampire.inject_vampire_bug(time_start=60, time_end=70, drain_multiplier=2.5)
        self.scenarios['vampire'] = (monitor_vampire, monitor_vampire.get_injections())

        # Scenario 2: Voltage Drop (t=80s, 3 second duration)
        monitor_voltage = ModifiedEnergyMonitor(self.log_file)
        monitor_voltage.inject_voltage_drop(time_start=80, duration=3, drop_magnitude=0.8)
        self.scenarios['voltage'] = (monitor_voltage, monitor_voltage.get_injections())

        # Scenario 3: Motor Imbalance (t=50-55s)
        monitor_motor = ModifiedEnergyMonitor(self.log_file)
        monitor_motor.inject_motor_imbalance(time_start=50, time_end=55, imbalance_factor=0.6)
        self.scenarios['motor'] = (monitor_motor, monitor_motor.get_injections())

        # Scenario 4: Drain Spike (t=70-75s)
        monitor_spike = ModifiedEnergyMonitor(self.log_file)
        monitor_spike.inject_drain_spike(time_start=70, time_end=75, spike_multiplier=4.0)
        self.scenarios['spike'] = (monitor_spike, monitor_spike.get_injections())

        # Scenario 5: Clean Control (no injections, t=40-80s)
        monitor_clean = ModifiedEnergyMonitor(self.log_file)
        # No injections
        self.scenarios['clean'] = (monitor_clean, [])

        print(f"  Created {len(self.scenarios)} scenarios")

    def run_detectors(self) -> None:
        """Run all detectors on each scenario."""
        print("\nRunning detectors on all scenarios...")

        for scenario_name, (monitor, injections) in self.scenarios.items():
            print(f"  Processing scenario: {scenario_name}")

            analyzer = EnergyAnalyzer(monitor)
            detected_bugs = analyzer.detect_all()

            self.detection_results[scenario_name] = {
                'injected': injections,
                'detected': detected_bugs,
                'profile': monitor.get_energy_profile()
            }

    def calculate_metrics(self) -> None:
        """Calculate precision, recall, F1 for each scenario."""
        print("\nCalculating detection metrics...")

        for scenario_name, results in self.detection_results.items():
            injected = results['injected']
            detected = results['detected']

            # For each injection, check if it was detected
            tp = 0  # True positives
            fn = 0  # False negatives

            for injection in injected:
                found = False
                for detection in detected:
                    # Check if detection overlaps with injection
                    if self._overlaps(injection, detection):
                        tp += 1
                        found = True
                        break

                if not found:
                    fn += 1

            # False positives: detections without corresponding injection
            fp = 0
            for detection in detected:
                found = False
                for injection in injected:
                    if self._overlaps(injection, detection):
                        found = True
                        break

                if not found:
                    fp += 1

            # Calculate metrics
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

            self.metrics[scenario_name] = {
                'tp': int(tp),
                'fp': int(fp),
                'fn': int(fn),
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1': round(f1, 4),
                'injected_count': len(injected),
                'detected_count': len(detected)
            }

    def _overlaps(self, injection: InjectedBug, detection) -> bool:
        """Check if detection overlaps with injection time window."""
        # Allow 2-second tolerance for detection
        tolerance = 2.0
        return not (detection.time_end < injection.time_start - tolerance or
                   detection.time_start > injection.time_end + tolerance)

    def generate_json_report(self) -> str:
        """Generate JSON report with all results."""
        print("\nGenerating JSON report...")

        report = {
            'experiment': 'Bug Injection for UAV Energy Testing',
            'log_file': str(self.log_file),
            'date': pd.Timestamp.now().isoformat(),
            'scenarios': {}
        }

        for scenario_name in self.scenarios.keys():
            results = self.detection_results[scenario_name]
            metrics = self.metrics[scenario_name]

            injected_bugs = [
                {
                    'type': inj.bug_type,
                    'time_start': float(inj.time_start),
                    'time_end': float(inj.time_end),
                    'description': inj.description
                }
                for inj in results['injected']
            ]

            detected_bugs = [
                {
                    'type': bug.bug_type.value,
                    'severity': bug.severity,
                    'time_start': float(bug.time_start),
                    'time_end': float(bug.time_end),
                    'description': bug.description,
                    'metrics': {k: float(v) if isinstance(v, (np.floating, np.integer)) else v
                               for k, v in bug.metrics.items()}
                }
                for bug in results['detected']
            ]

            report['scenarios'][scenario_name] = {
                'metrics': metrics,
                'injected_bugs': injected_bugs,
                'detected_bugs': detected_bugs
            }

        # Add summary statistics
        all_metrics = list(self.metrics.values())
        if all_metrics:
            report['summary'] = {
                'avg_precision': float(round(np.mean([m['precision'] for m in all_metrics]), 4)),
                'avg_recall': float(round(np.mean([m['recall'] for m in all_metrics]), 4)),
                'avg_f1': float(round(np.mean([m['f1'] for m in all_metrics]), 4))
            }

        report_file = self.output_dir / "bug_injection_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"  Saved: {report_file}")
        return str(report_file)

    def generate_latex_table(self) -> str:
        """Generate LaTeX table of results."""
        print("Generating LaTeX table...")

        latex = r"""
\begin{table}[h]
\centering
\caption{Bug Injection Experiment Results: Detection Metrics}
\label{tab:bug_injection_metrics}
\begin{tabular}{lrrrrrr}
\toprule
\textbf{Scenario} & \textbf{TP} & \textbf{FP} & \textbf{FN} & \textbf{Precision} & \textbf{Recall} & \textbf{F1} \\
\midrule
"""

        for scenario_name in sorted(self.metrics.keys()):
            m = self.metrics[scenario_name]
            latex += (f"{scenario_name:20} & {m['tp']} & {m['fp']} & {m['fn']} & "
                     f"{m['precision']:.4f} & {m['recall']:.4f} & {m['f1']:.4f} \\\\\n")

        # Add average row
        all_metrics = list(self.metrics.values())
        if all_metrics:
            avg_tp = np.mean([m['tp'] for m in all_metrics])
            avg_fp = np.mean([m['fp'] for m in all_metrics])
            avg_fn = np.mean([m['fn'] for m in all_metrics])
            avg_prec = np.mean([m['precision'] for m in all_metrics])
            avg_rec = np.mean([m['recall'] for m in all_metrics])
            avg_f1 = np.mean([m['f1'] for m in all_metrics])

            latex += (r"\midrule" + "\n")
            latex += (f"{'Average':20} & {avg_tp:.1f} & {avg_fp:.1f} & {avg_fn:.1f} & "
                     f"{avg_prec:.4f} & {avg_rec:.4f} & {avg_f1:.4f} \\\\\n")

        latex += r"""
\bottomrule
\end{tabular}
\end{table}
"""

        latex_file = self.output_dir / "metrics_table.tex"
        with open(latex_file, 'w') as f:
            f.write(latex)

        print(f"  Saved: {latex_file}")
        return str(latex_file)

    def generate_visualization(self) -> str:
        """Generate matplotlib visualization of results."""
        print("Generating visualization...")

        # Create figure with subplots
        fig = plt.figure(figsize=(16, 12))

        # Plot 1: Detection metrics comparison
        ax1 = plt.subplot(2, 3, 1)
        scenarios = list(self.metrics.keys())
        precision_vals = [self.metrics[s]['precision'] for s in scenarios]
        recall_vals = [self.metrics[s]['recall'] for s in scenarios]
        f1_vals = [self.metrics[s]['f1'] for s in scenarios]

        x = np.arange(len(scenarios))
        width = 0.25

        ax1.bar(x - width, precision_vals, width, label='Precision', alpha=0.8)
        ax1.bar(x, recall_vals, width, label='Recall', alpha=0.8)
        ax1.bar(x + width, f1_vals, width, label='F1', alpha=0.8)

        ax1.set_ylabel('Score', fontsize=11)
        ax1.set_title('Detection Metrics by Scenario', fontsize=12, fontweight='bold')
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios, rotation=45)
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        ax1.set_ylim([0, 1.1])

        # Plot 2: TP/FP/FN comparison
        ax2 = plt.subplot(2, 3, 2)
        tp_vals = [self.metrics[s]['tp'] for s in scenarios]
        fp_vals = [self.metrics[s]['fp'] for s in scenarios]
        fn_vals = [self.metrics[s]['fn'] for s in scenarios]

        ax2.bar(x - width, tp_vals, width, label='TP', alpha=0.8, color='green')
        ax2.bar(x, fp_vals, width, label='FP', alpha=0.8, color='red')
        ax2.bar(x + width, fn_vals, width, label='FN', alpha=0.8, color='orange')

        ax2.set_ylabel('Count', fontsize=11)
        ax2.set_title('Detection Error Analysis', fontsize=12, fontweight='bold')
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios, rotation=45)
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)

        # Plot 3: Injected vs Detected counts
        ax3 = plt.subplot(2, 3, 3)
        injected_counts = [self.metrics[s]['injected_count'] for s in scenarios]
        detected_counts = [self.metrics[s]['detected_count'] for s in scenarios]

        ax3.bar(x - width/2, injected_counts, width, label='Injected', alpha=0.8)
        ax3.bar(x + width/2, detected_counts, width, label='Detected', alpha=0.8)

        ax3.set_ylabel('Count', fontsize=11)
        ax3.set_title('Injected vs Detected Bugs', fontsize=12, fontweight='bold')
        ax3.set_xticks(x)
        ax3.set_xticklabels(scenarios, rotation=45)
        ax3.legend()
        ax3.grid(axis='y', alpha=0.3)

        # Plot 4-6: Energy profiles for each scenario
        profile_scenarios = ['vampire', 'voltage', 'motor', 'spike', 'clean']

        for idx, scenario_name in enumerate(profile_scenarios[:3]):
            ax = plt.subplot(2, 3, 4 + idx)

            profile = self.detection_results[scenario_name]['profile']
            injections = self.detection_results[scenario_name]['injected']
            detections = self.detection_results[scenario_name]['detected']

            # Plot relevant metric
            if scenario_name == 'vampire':
                ax.plot(profile['time_sec'], profile['remaining_pct'], 'b-', linewidth=1.5, label='Battery %')
                ax.set_ylabel('Battery Remaining (%)', fontsize=10)
            elif scenario_name == 'voltage':
                ax.plot(profile['time_sec'], profile['voltage_v'], 'r-', linewidth=1.5, label='Voltage')
                ax.set_ylabel('Voltage (V)', fontsize=10)
            else:  # motor
                ax.plot(profile['time_sec'], profile['motor_avg'], 'g-', linewidth=1.5, label='Avg Motor')
                ax.set_ylabel('Motor Output (PWM)', fontsize=10)

            # Mark injected and detected regions
            for inj in injections:
                ax.axvspan(inj.time_start, inj.time_end, alpha=0.2, color='green', label='Injected')

            for det in detections:
                ax.axvspan(det.time_start, det.time_end, alpha=0.15, color='red', label='Detected')

            ax.set_xlabel('Time (s)', fontsize=10)
            ax.set_title(f'{scenario_name.capitalize()} Scenario', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=9)

        plt.tight_layout()
        viz_file = self.output_dir / "bug_injection_results.png"
        plt.savefig(viz_file, dpi=150, bbox_inches='tight')
        print(f"  Saved: {viz_file}")

        return str(viz_file)

    def run(self) -> Dict:
        """Run complete experiment."""
        print("=" * 70)
        print("BUG INJECTION EXPERIMENT FOR UAV ENERGY TESTING")
        print("=" * 70)

        self.create_scenarios()
        self.run_detectors()
        self.calculate_metrics()

        self.generate_json_report()
        self.generate_latex_table()
        self.generate_visualization()

        return self.metrics


def main():
    """Main entry point."""
    log_file = "UAV-Testing-Competition/snippets/case_studies/mission1.ulg"

    # Run experiment
    experiment = BugInjectionExperiment(log_file)
    metrics = experiment.run()

    # Print summary
    print("\n" + "=" * 70)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 70)

    for scenario_name, m in sorted(metrics.items()):
        print(f"\n[{scenario_name.upper()}]")
        print(f"  Injected bugs: {m['injected_count']}")
        print(f"  Detected bugs: {m['detected_count']}")
        print(f"  True Positives: {m['tp']}")
        print(f"  False Positives: {m['fp']}")
        print(f"  False Negatives: {m['fn']}")
        print(f"  Precision: {m['precision']:.4f}")
        print(f"  Recall: {m['recall']:.4f}")
        print(f"  F1-Score: {m['f1']:.4f}")

    print(f"\nOutput files saved to: {experiment.output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
