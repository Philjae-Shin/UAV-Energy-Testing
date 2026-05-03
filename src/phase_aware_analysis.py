"""
Phase-Aware Energy Bug Detection for UAV Testing Framework

Classifies flight phases (PREFLIGHT, ARMING_TAKEOFF, CRUISE, LANDING) and
re-runs detection excluding the startup phase to demonstrate that most detected
bugs are artifacts of the takeoff process.
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from energy.monitor import EnergyMonitor
from energy.analyzer import EnergyAnalyzer, EnergyBug


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        return super().default(obj)


class FlightPhase(Enum):
    """Flight phase classifications."""
    PREFLIGHT = "PREFLIGHT"
    ARMING_TAKEOFF = "ARMING_TAKEOFF"
    CRUISE = "CRUISE"
    LANDING = "LANDING"


@dataclass
class PhaseInfo:
    """Information about a flight phase."""
    phase: FlightPhase
    start_time: float
    end_time: float

    def contains_time(self, time_sec: float) -> bool:
        """Check if a time falls within this phase."""
        return self.start_time <= time_sec <= self.end_time


class PhaseClassifier:
    """Classifies flight timestamps into flight phases."""

    # Heuristic parameters
    MOTOR_IDLE_THRESHOLD = 950  # PWM - below this = motors not spinning
    ALTITUDE_CRUISE_THRESHOLD = 3.0  # meters - minimum altitude for cruise
    ALTITUDE_TAKEOFF_TARGET = 5.0  # meters - altitude that defines end of takeoff
    DESCENT_RATE_THRESHOLD = -0.5  # m/s - negative velocity indicates descent

    def __init__(self, energy_profile: pd.DataFrame):
        """
        Initialize phase classifier with energy profile.

        Args:
            energy_profile: DataFrame from monitor.get_energy_profile()
                           with columns: time_sec, motor_avg, altitude
        """
        self.profile = energy_profile.copy()
        self.phases: List[PhaseInfo] = []
        self._classify_phases()

    def _classify_phases(self) -> None:
        """Classify all timestamps into flight phases."""
        if 'motor_avg' not in self.profile.columns or 'altitude' not in self.profile.columns:
            raise ValueError("Profile must contain 'motor_avg' and 'altitude' columns")

        profile = self.profile.copy()
        profile['phase'] = FlightPhase.PREFLIGHT

        # Find takeoff: when altitude first consistently exceeds threshold
        altitude = profile['altitude'].fillna(0)
        motor_avg = profile['motor_avg'].fillna(0)

        # Find when altitude first exceeds takeoff target consistently
        # Use a smoothed check: altitude > threshold for sustained period
        altitude_high = altitude > self.ALTITUDE_TAKEOFF_TARGET

        # Find transitions
        if altitude_high.any():
            # Get indices where altitude is high
            high_indices = np.where(altitude_high)[0]
            if len(high_indices) > 0:
                # Takeoff ends at first high altitude
                takeoff_end_idx = high_indices[0]
                takeoff_end_time = profile.loc[takeoff_end_idx, 'time_sec']
            else:
                takeoff_end_time = profile['time_sec'].max()
        else:
            takeoff_end_time = profile['time_sec'].max()

        # Find landing: when altitude starts final descent
        # Landing starts when altitude begins decreasing toward zero at the end
        # Use: find last time altitude is high, then landing starts when it drops
        if altitude_high.any():
            high_indices = np.where(altitude_high)[0]
            if len(high_indices) > 0:
                last_high_idx = high_indices[-1]
                # Check if altitude decreases after this point
                remaining_altitude = altitude[last_high_idx:]

                # Landing starts when altitude drops significantly from the end of cruise
                # Use a simple heuristic: when altitude < cruise threshold at the end
                landing_indices = np.where(altitude[last_high_idx:] < self.ALTITUDE_CRUISE_THRESHOLD)[0]
                if len(landing_indices) > 0:
                    landing_start_idx = last_high_idx + landing_indices[0]
                    landing_start_time = profile.loc[landing_start_idx, 'time_sec']
                else:
                    landing_start_time = profile['time_sec'].max()
            else:
                landing_start_time = profile['time_sec'].max()
        else:
            landing_start_time = profile['time_sec'].max()

        # Ensure landing starts after takeoff ends
        if landing_start_time < takeoff_end_time:
            landing_start_time = profile['time_sec'].max()

        # Classify phases
        for idx, row in profile.iterrows():
            time = row['time_sec']

            if time < takeoff_end_time:
                profile.loc[idx, 'phase'] = FlightPhase.ARMING_TAKEOFF
            elif time >= landing_start_time:
                profile.loc[idx, 'phase'] = FlightPhase.LANDING
            else:
                profile.loc[idx, 'phase'] = FlightPhase.CRUISE

        # Store phase transitions
        self.profile = profile
        self._compute_phase_ranges()

    def _compute_phase_ranges(self) -> None:
        """Compute the time ranges for each phase."""
        self.phases = []

        for phase in FlightPhase:
            phase_mask = self.profile['phase'] == phase
            if phase_mask.any():
                phase_times = self.profile[phase_mask]['time_sec']
                start_time = phase_times.min()
                end_time = phase_times.max()
                self.phases.append(PhaseInfo(phase, start_time, end_time))

        # Sort by start time
        self.phases.sort(key=lambda p: p.start_time)

    def get_phase_at_time(self, time_sec: float) -> FlightPhase:
        """Get the flight phase at a specific time."""
        row = self.profile[self.profile['time_sec'] == time_sec]
        if not row.empty:
            return row.iloc[0]['phase']

        # Linear search for closest time
        idx = (self.profile['time_sec'] - time_sec).abs().argmin()
        return self.profile.iloc[idx]['phase']

    def get_phase_ranges(self) -> List[PhaseInfo]:
        """Get all phase transitions as time ranges."""
        return self.phases

    def classify_bug(self, bug: EnergyBug) -> List[FlightPhase]:
        """
        Determine which phases a bug overlaps with.

        Returns:
            List of phases that the bug intersects
        """
        bug_start = bug.time_start
        bug_end = bug.time_end

        bug_phases = []
        for phase_info in self.phases:
            # Check if bug overlaps with this phase
            if bug_end >= phase_info.start_time and bug_start <= phase_info.end_time:
                bug_phases.append(phase_info.phase)

        return bug_phases


class PhaseAwareAnalyzer:
    """Runs energy analysis with phase-aware filtering."""

    def __init__(self, log_file: str):
        """Initialize with a ULog file."""
        self.log_file = log_file
        self.monitor = EnergyMonitor(log_file)
        self.analyzer = EnergyAnalyzer(self.monitor)
        self.profile = self.monitor.get_energy_profile()
        self.classifier = PhaseClassifier(self.profile)

    def get_all_bugs(self) -> List[EnergyBug]:
        """Get all detected bugs (no filtering)."""
        return self.analyzer.detect_all()

    def get_phase_filtered_bugs(self, exclude_phases: List[FlightPhase] = None) -> List[EnergyBug]:
        """
        Get bugs filtered by phase.

        Args:
            exclude_phases: List of phases to exclude (default: [ARMING_TAKEOFF])

        Returns:
            List of bugs that occur outside excluded phases
        """
        if exclude_phases is None:
            exclude_phases = [FlightPhase.ARMING_TAKEOFF]

        all_bugs = self.get_all_bugs()
        filtered_bugs = []

        for bug in all_bugs:
            bug_phases = self.classifier.classify_bug(bug)
            # Keep bug if it has phases outside the excluded set
            if not all(phase in exclude_phases for phase in bug_phases):
                filtered_bugs.append(bug)

        return filtered_bugs

    def get_bug_phase_mapping(self) -> Dict[int, Dict]:
        """
        Get mapping of bugs to their phases.

        Returns:
            Dict mapping bug index to phase information
        """
        all_bugs = self.get_all_bugs()
        mapping = {}

        for i, bug in enumerate(all_bugs):
            bug_phases = self.classifier.classify_bug(bug)
            mapping[i] = {
                'bug': bug.to_dict(),
                'phases': [p.value for p in bug_phases],
                'time_range': (bug.time_start, bug.time_end)
            }

        return mapping

    def get_phase_ranges(self) -> Dict[str, Tuple[float, float]]:
        """Get time ranges for each phase."""
        ranges = {}
        for phase_info in self.classifier.get_phase_ranges():
            ranges[phase_info.phase.value] = (phase_info.start_time, phase_info.end_time)
        return ranges


def analyze_all_missions() -> Dict:
    """Analyze all available ULog files."""

    # Define mission locations
    mission_paths = {
        # Competition missions
        'competition/mission1': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/UAV-Testing-Competition/snippets/case_studies/mission1.ulg',
        'competition/mission1-2': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/UAV-Testing-Competition/snippets/case_studies/mission1-2.ulg',
        'competition/mission2': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/UAV-Testing-Competition/snippets/case_studies/mission2.ulg',
        'competition/mission2-2': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/UAV-Testing-Competition/snippets/case_studies/mission2-2.ulg',
        'competition/mission3': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/UAV-Testing-Competition/snippets/case_studies/mission3.ulg',
        'competition/mission3-2': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/UAV-Testing-Competition/snippets/case_studies/mission3-2.ulg',

        # Stress missions
        'stress/hover': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/data/stress_results/stress_hover.ulg',
        'stress/zigzag': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/data/stress_results/stress_zigzag.ulg',
        'stress/altitude': '/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/data/stress_results/stress_altitude.ulg',
    }

    results = {}

    for mission_name, log_path in mission_paths.items():
        if not os.path.exists(log_path):
            print(f"Skipping {mission_name}: file not found at {log_path}")
            continue

        try:
            print(f"Analyzing {mission_name}...")
            analyzer = PhaseAwareAnalyzer(log_path)

            all_bugs = analyzer.get_all_bugs()
            filtered_bugs = analyzer.get_phase_filtered_bugs()
            phase_ranges = analyzer.get_phase_ranges()
            bug_phase_mapping = analyzer.get_bug_phase_mapping()

            results[mission_name] = {
                'log_path': log_path,
                'original_bug_count': len(all_bugs),
                'phase_filtered_bug_count': len(filtered_bugs),
                'phase_ranges': phase_ranges,
                'bug_details': bug_phase_mapping,
                'all_bugs': [b.to_dict() for b in all_bugs],
                'filtered_bugs': [b.to_dict() for b in filtered_bugs],
                'analyzer': analyzer
            }

            print(f"  Original bugs: {len(all_bugs)}")
            print(f"  Phase-filtered bugs: {len(filtered_bugs)}")
            print(f"  Phases: {', '.join(phase_ranges.keys())}")

        except Exception as e:
            print(f"Error analyzing {mission_name}: {e}")
            results[mission_name] = {'error': str(e)}

    return results


def generate_comparison_table(results: Dict) -> pd.DataFrame:
    """Generate a comparison table of original vs phase-filtered bugs."""
    rows = []

    for mission_name, data in results.items():
        if 'error' in data:
            continue

        rows.append({
            'Mission': mission_name,
            'Original Bugs': data['original_bug_count'],
            'Phase-Filtered Bugs': data['phase_filtered_bug_count'],
            'Bugs Removed': data['original_bug_count'] - data['phase_filtered_bug_count'],
            'Phases': ', '.join(sorted(data['phase_ranges'].keys()))
        })

    return pd.DataFrame(rows)


def generate_phase_visualization(analyzer: PhaseAwareAnalyzer, mission_name: str,
                                 output_path: str) -> None:
    """
    Generate a visualization showing flight phases and detected bugs.

    Creates a figure with:
    - Flight phases as colored bands
    - Detected bugs as horizontal bars
    - Energy metrics as line plots
    """
    profile = analyzer.profile
    all_bugs = analyzer.get_all_bugs()
    phase_ranges = analyzer.get_phase_ranges()

    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f'Phase-Aware Bug Detection: {mission_name}', fontsize=16, fontweight='bold')

    # Define colors for phases
    phase_colors = {
        FlightPhase.PREFLIGHT.value: '#cccccc',
        FlightPhase.ARMING_TAKEOFF.value: '#ff6b6b',
        FlightPhase.CRUISE.value: '#4ecdc4',
        FlightPhase.LANDING.value: '#ffe66d'
    }

    # Axis 0: Altitude and Motor Output
    ax = axes[0]
    ax.plot(profile['time_sec'], profile['altitude'], label='Altitude (m)', linewidth=2, color='blue')
    if 'motor_avg' in profile.columns:
        # Normalize motor to same scale as altitude for visualization
        motor_norm = profile['motor_avg'] / 200 - 4
        ax.plot(profile['time_sec'], motor_norm, label='Motor Avg (PWM/200 - 4)', linewidth=1.5, color='orange', alpha=0.7)

    ax.set_ylabel('Altitude (m)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)

    # Axis 1: Battery Level
    ax = axes[1]
    if 'remaining_pct' in profile.columns:
        ax.plot(profile['time_sec'], profile['remaining_pct'], label='Battery Level (%)',
                linewidth=1.5, color='red')
        ax.set_ylim(0, 105)
    ax.set_ylabel('Battery (%)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)

    # Axis 2: Voltage
    if 'voltage_v' in profile.columns:
        ax = axes[2]
        ax.plot(profile['time_sec'], profile['voltage_v'], label='Voltage (V)',
                linewidth=1.5, color='green')
        ax.set_ylabel('Voltage (V)')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)

    # Axis 3: Phases and Bugs
    ax = axes[3]

    # Draw phase backgrounds
    max_time = profile['time_sec'].max()
    phase_labels_added = set()
    for phase_info in analyzer.classifier.get_phase_ranges():
        label = phase_info.phase.value if phase_info.phase.value not in phase_labels_added else None
        phase_labels_added.add(phase_info.phase.value)
        ax.axvspan(phase_info.start_time, phase_info.end_time,
                  alpha=0.3, color=phase_colors[phase_info.phase.value],
                  label=label)

    # Draw bug bars
    for bug_idx, bug in enumerate(all_bugs):
        bug_phases = analyzer.classifier.classify_bug(bug)
        is_takeoff_only = all(p == FlightPhase.ARMING_TAKEOFF for p in bug_phases)

        color = 'red' if is_takeoff_only else 'darkgreen'
        alpha = 0.5 if is_takeoff_only else 0.8
        label_suffix = ' (Arming/Takeoff)' if is_takeoff_only else ''

        ax.barh(bug_idx + 1, bug.time_end - bug.time_start,
               left=bug.time_start, height=0.6,
               color=color, alpha=alpha)

    ax.set_ylabel('Bug Index')
    ax.set_xlabel('Time (seconds)')
    ax.set_ylim(0, len(all_bugs) + 1)
    ax.set_xlim(0, max_time)
    ax.grid(True, alpha=0.3, axis='x')

    # Add legend for bugs
    red_patch = mpatches.Patch(color='red', alpha=0.5, label='Startup-only bugs')
    green_patch = mpatches.Patch(color='darkgreen', alpha=0.8, label='Cruise/Landing bugs')
    ax.legend(handles=[red_patch, green_patch], loc='upper right')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved figure to {output_path}")
    plt.close()


def main():
    """Main analysis pipeline."""

    print("="*70)
    print("Phase-Aware Energy Bug Detection Analysis")
    print("="*70)

    # Ensure output directories exist
    output_dir = Path('/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/src/results/phase_aware')
    output_dir.mkdir(parents=True, exist_ok=True)

    dissertation_dir = Path('/sessions/peaceful-stoic-einstein/mnt/UAV-Energy-Testing/Dissertation')
    dissertation_dir.mkdir(parents=True, exist_ok=True)

    # Run analysis on all missions
    print("\nAnalyzing all missions...")
    results = analyze_all_missions()

    # Generate comparison table
    print("\nGenerating comparison table...")
    comparison_df = generate_comparison_table(results)
    print("\n" + "="*70)
    print("PHASE-AWARE BUG DETECTION RESULTS")
    print("="*70)
    print(comparison_df.to_string(index=False))

    # Save comparison table
    csv_path = output_dir / 'comparison_table.csv'
    comparison_df.to_csv(csv_path, index=False)
    print(f"\nSaved comparison table to {csv_path}")

    # Generate detailed report
    print("\n" + "="*70)
    print("DETAILED BUG ANALYSIS")
    print("="*70)

    detailed_report = {}
    for mission_name, data in results.items():
        if 'error' in data:
            print(f"\n{mission_name}: ERROR - {data['error']}")
            detailed_report[mission_name] = {'error': data['error']}
            continue

        print(f"\n{mission_name}:")
        print(f"  Original bugs: {data['original_bug_count']}")
        print(f"  Phase-filtered bugs: {data['phase_filtered_bug_count']}")
        print(f"  Reduction: {data['original_bug_count'] - data['phase_filtered_bug_count']} bugs removed")
        print(f"  Phase ranges:")
        for phase_name, (start, end) in sorted(data['phase_ranges'].items()):
            print(f"    - {phase_name}: {start:.1f}s to {end:.1f}s ({end-start:.1f}s duration)")

        print(f"\n  All bugs by phase:")
        for bug_idx, bug_info in data['bug_details'].items():
            bug = bug_info['bug']
            phases = ', '.join(bug_info['phases'])
            print(f"    Bug {bug_idx}: {bug['type']} [{bug['severity']}] at {bug['time_start']:.1f}-{bug['time_end']:.1f}s (phases: {phases})")

        # Build report entry with JSON-serializable data
        phase_ranges_serializable = {k: (float(v[0]), float(v[1])) for k, v in data['phase_ranges'].items()}
        detailed_report[mission_name] = {
            'original_bugs': int(data['original_bug_count']),
            'phase_filtered_bugs': int(data['phase_filtered_bug_count']),
            'phase_ranges': phase_ranges_serializable,
            'bugs': data['bug_details']
        }

    # Save detailed report as JSON
    json_path = output_dir / 'phase_aware_analysis_report.json'
    with open(json_path, 'w') as f:
        json.dump(detailed_report, f, indent=2, cls=NumpyEncoder)
    print(f"\nSaved detailed report to {json_path}")

    # Generate visualizations for key missions
    print("\n" + "="*70)
    print("GENERATING VISUALIZATIONS")
    print("="*70)

    key_missions = [
        ('competition/mission1', 'mission1'),
        ('stress/zigzag', 'stress_zigzag'),
    ]

    for mission_key, output_name in key_missions:
        if mission_key in results and 'error' not in results[mission_key]:
            analyzer = results[mission_key]['analyzer']
            output_path = dissertation_dir / f'phase_aware_{output_name}.png'
            print(f"\nGenerating visualization for {mission_key}...")
            try:
                generate_phase_visualization(analyzer, mission_key, str(output_path))
            except Exception as e:
                import traceback
                print(f"  Error generating visualization: {e}")
                traceback.print_exc()
        else:
            print(f"Skipping visualization for {mission_key}: not available")

    # Summary statistics
    print("SUMMARY STATISTICS")

    total_original = 0
    total_filtered = 0
    missions_analyzed = 0

    for mission_name, data in results.items():
        if 'error' not in data:
            total_original += data['original_bug_count']
            total_filtered += data['phase_filtered_bug_count']
            missions_analyzed += 1

    if missions_analyzed > 0:
        print(f"Missions analyzed: {missions_analyzed}")
        print(f"Total original bugs: {total_original}")
        print(f"Total phase-filtered bugs: {total_filtered}")
        print(f"Total bugs removed: {total_original - total_filtered}")
        print(f"Average removal rate: {((total_original - total_filtered) / total_original * 100):.1f}%"
              if total_original > 0 else "N/A")

    print("Analysis complete!")


if __name__ == '__main__':
    main()
