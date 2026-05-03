# Energy Analyzer Module
"""
EnergyAnalyzer: Detects energy bugs and anomalies in UAV flight data.

Energy Bug Categories (based on literature):
1. Energy Vampires - Unexpected high consumption during idle/hover
2. Voltage Anomalies - Sudden voltage drops indicating battery stress
3. Motor Inefficiency - Abnormal motor output patterns
4. Drain Rate Spikes - Sudden increases in energy consumption

Usage:
    from energy.analyzer import EnergyAnalyzer
    from energy.monitor import EnergyMonitor

    monitor = EnergyMonitor("flight.ulg")
    analyzer = EnergyAnalyzer(monitor)
    bugs = analyzer.detect_all()
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .monitor import EnergyMonitor, FlightSummary


class EnergyBugType(Enum):
    """Types of energy bugs that can be detected."""
    ENERGY_VAMPIRE = "energy_vampire"           # High consumption during low activity
    VOLTAGE_ANOMALY = "voltage_anomaly"         # Sudden voltage drops
    MOTOR_INEFFICIENCY = "motor_inefficiency"   # Abnormal motor patterns
    DRAIN_RATE_SPIKE = "drain_rate_spike"       # Sudden consumption increase
    BATTERY_STRESS = "battery_stress"           # Signs of battery degradation


@dataclass
class EnergyBug:
    """Represents a detected energy bug."""
    bug_type: EnergyBugType
    severity: str           # 'low', 'medium', 'high', 'critical'
    time_start: float       # Start time in seconds
    time_end: float         # End time in seconds
    description: str        # Human-readable description
    metrics: Dict           # Relevant metrics

    def to_dict(self) -> Dict:
        return {
            'type': self.bug_type.value,
            'severity': self.severity,
            'time_start': self.time_start,
            'time_end': self.time_end,
            'description': self.description,
            'metrics': self.metrics
        }


class EnergyAnalyzer:
    """
    Analyzes energy data to detect anomalies and bugs.

    Thresholds can be customized for different UAV types and missions.
    """

    # Default thresholds (can be adjusted)
    THRESHOLDS = {
        # Energy vampire: high consumption when motors < this value
        'vampire_motor_threshold': 1200,      # PWM
        'vampire_drain_threshold': 0.5,       # % per minute

        # Voltage anomaly: drop greater than this in short time
        'voltage_drop_threshold': 0.5,        # Volts
        'voltage_drop_window': 5.0,           # seconds

        # Motor inefficiency: variance threshold
        'motor_variance_threshold': 50000,    # PWM^2

        # Drain rate spike: sudden increase ratio
        'drain_spike_ratio': 2.0,             # x times normal

        # Battery stress: voltage oscillation
        'voltage_oscillation_threshold': 0.3  # Volts
    }

    def __init__(self, monitor: EnergyMonitor, thresholds: Optional[Dict] = None):
        """
        Initialize analyzer with an EnergyMonitor instance.

        Args:
            monitor: EnergyMonitor instance with loaded flight data
            thresholds: Optional custom thresholds dictionary
        """
        self.monitor = monitor
        self.thresholds = {**self.THRESHOLDS, **(thresholds or {})}
        self._profile: Optional[pd.DataFrame] = None
        self._bugs: List[EnergyBug] = []

    def get_profile(self, resample_sec: float = 0.5) -> pd.DataFrame:
        """Get or compute the energy profile."""
        if self._profile is None:
            self._profile = self.monitor.get_energy_profile(resample_sec)
            self._compute_derivatives()
        return self._profile

    def _compute_derivatives(self) -> None:
        """Compute rate of change metrics for analysis."""
        profile = self._profile

        # Battery drain rate (% per second)
        if 'remaining_pct' in profile.columns:
            profile['drain_rate'] = -profile['remaining_pct'].diff() / profile['time_sec'].diff()
            profile['drain_rate'] = profile['drain_rate'].fillna(0)

        # Voltage rate of change
        if 'voltage_v' in profile.columns:
            profile['voltage_rate'] = profile['voltage_v'].diff() / profile['time_sec'].diff()
            profile['voltage_rate'] = profile['voltage_rate'].fillna(0)

        # Motor output rate of change
        if 'motor_avg' in profile.columns:
            profile['motor_rate'] = profile['motor_avg'].diff() / profile['time_sec'].diff()
            profile['motor_rate'] = profile['motor_rate'].fillna(0)

    def detect_energy_vampires(self) -> List[EnergyBug]:
        """
        Detect energy vampire patterns.

        Energy vampires occur when battery drains faster than expected
        during low-activity periods (hovering, idle).
        """
        bugs = []
        profile = self.get_profile()

        if 'motor_avg' not in profile.columns or 'drain_rate' not in profile.columns:
            return bugs

        motor_thresh = self.thresholds['vampire_motor_threshold']
        drain_thresh = self.thresholds['vampire_drain_threshold'] / 60  # Convert to per-second

        # Find periods of low motor activity with high drain
        low_activity = profile['motor_avg'] < motor_thresh
        high_drain = profile['drain_rate'] > drain_thresh

        vampire_periods = low_activity & high_drain

        # Group consecutive vampire periods
        if vampire_periods.any():
            groups = (vampire_periods != vampire_periods.shift()).cumsum()
            for group_id, group_data in profile[vampire_periods].groupby(groups[vampire_periods]):
                if len(group_data) >= 3:  # At least 1.5 seconds
                    avg_drain = group_data['drain_rate'].mean() * 60  # % per minute
                    avg_motor = group_data['motor_avg'].mean()

                    severity = 'low'
                    if avg_drain > drain_thresh * 60 * 1.5:
                        severity = 'medium'
                    if avg_drain > drain_thresh * 60 * 2:
                        severity = 'high'

                    bugs.append(EnergyBug(
                        bug_type=EnergyBugType.ENERGY_VAMPIRE,
                        severity=severity,
                        time_start=group_data['time_sec'].iloc[0],
                        time_end=group_data['time_sec'].iloc[-1],
                        description=f"High battery drain ({avg_drain:.2f}%/min) during low motor activity ({avg_motor:.0f} PWM)",
                        metrics={
                            'avg_drain_rate_per_min': round(avg_drain, 2),
                            'avg_motor_output': round(avg_motor, 2),
                            'duration_sec': round(group_data['time_sec'].iloc[-1] - group_data['time_sec'].iloc[0], 2)
                        }
                    ))

        return bugs

    def detect_voltage_anomalies(self) -> List[EnergyBug]:
        """
        Detect sudden voltage drops indicating battery stress.
        """
        bugs = []
        profile = self.get_profile()

        if 'voltage_v' not in profile.columns:
            return bugs

        drop_thresh = self.thresholds['voltage_drop_threshold']
        window = int(self.thresholds['voltage_drop_window'] / 0.5)  # Convert to samples

        # Calculate rolling voltage drop
        voltage = profile['voltage_v']
        rolling_max = voltage.rolling(window=window, min_periods=1).max()
        rolling_min = voltage.rolling(window=window, min_periods=1).min()
        voltage_drop = rolling_max - rolling_min

        anomaly_idx = voltage_drop > drop_thresh

        if anomaly_idx.any():
            groups = (anomaly_idx != anomaly_idx.shift()).cumsum()
            for group_id, group_data in profile[anomaly_idx].groupby(groups[anomaly_idx]):
                if len(group_data) >= 2:
                    max_drop = voltage_drop[group_data.index].max()

                    severity = 'low'
                    if max_drop > drop_thresh * 1.5:
                        severity = 'medium'
                    if max_drop > drop_thresh * 2:
                        severity = 'high'
                    if max_drop > drop_thresh * 3:
                        severity = 'critical'

                    bugs.append(EnergyBug(
                        bug_type=EnergyBugType.VOLTAGE_ANOMALY,
                        severity=severity,
                        time_start=group_data['time_sec'].iloc[0],
                        time_end=group_data['time_sec'].iloc[-1],
                        description=f"Sudden voltage drop of {max_drop:.2f}V detected",
                        metrics={
                            'max_voltage_drop': round(max_drop, 2),
                            'voltage_at_start': round(voltage[group_data.index[0]], 2),
                            'voltage_at_end': round(voltage[group_data.index[-1]], 2)
                        }
                    ))

        return bugs

    def detect_motor_inefficiency(self) -> List[EnergyBug]:
        """
        Detect abnormal motor output patterns indicating inefficiency.
        """
        bugs = []
        profile = self.get_profile()
        motor_df = self.monitor.get_motor_data()

        if motor_df is None:
            return bugs

        variance_thresh = self.thresholds['motor_variance_threshold']

        # Calculate variance across all 4 motors at each timestamp
        motor_cols = [c for c in motor_df.columns if c.startswith('output[')]
        if len(motor_cols) >= 4:
            motor_df['motor_variance'] = motor_df[motor_cols].var(axis=1)

            # Convert to time_sec for consistency
            motor_df['time_sec'] = (motor_df['timestamp'] - motor_df['timestamp'].iloc[0]) / 1e6

            # Find high variance periods
            high_variance_idx = motor_df['motor_variance'] > variance_thresh

            if high_variance_idx.any():
                groups = (high_variance_idx != high_variance_idx.shift()).cumsum()
                for group_id, group_data in motor_df[high_variance_idx].groupby(groups[high_variance_idx]):
                    if len(group_data) >= 5:
                        avg_variance = group_data['motor_variance'].mean()

                        severity = 'low'
                        if avg_variance > variance_thresh * 1.5:
                            severity = 'medium'
                        if avg_variance > variance_thresh * 2:
                            severity = 'high'

                        bugs.append(EnergyBug(
                            bug_type=EnergyBugType.MOTOR_INEFFICIENCY,
                            severity=severity,
                            time_start=group_data['time_sec'].iloc[0],
                            time_end=group_data['time_sec'].iloc[-1],
                            description=f"High motor output variance ({avg_variance:.0f}) indicating unbalanced load",
                            metrics={
                                'avg_variance': round(avg_variance, 2),
                                'duration_sec': round(group_data['time_sec'].iloc[-1] - group_data['time_sec'].iloc[0], 2)
                            }
                        ))

        return bugs

    def detect_drain_rate_spikes(self) -> List[EnergyBug]:
        """
        Detect sudden spikes in battery drain rate.
        """
        bugs = []
        profile = self.get_profile()

        if 'drain_rate' not in profile.columns:
            return bugs

        # Calculate baseline drain rate (median)
        baseline_drain = profile['drain_rate'].median()
        if baseline_drain <= 0:
            baseline_drain = profile['drain_rate'].mean()

        if baseline_drain <= 0:
            return bugs

        spike_ratio = self.thresholds['drain_spike_ratio']
        spike_threshold = baseline_drain * spike_ratio

        # Find spike periods
        spike_idx = profile['drain_rate'] > spike_threshold

        if spike_idx.any():
            groups = (spike_idx != spike_idx.shift()).cumsum()
            for group_id, group_data in profile[spike_idx].groupby(groups[spike_idx]):
                if len(group_data) >= 2:
                    max_drain = group_data['drain_rate'].max() * 60  # % per minute
                    avg_drain = group_data['drain_rate'].mean() * 60

                    severity = 'low'
                    ratio = group_data['drain_rate'].max() / baseline_drain
                    if ratio > spike_ratio * 1.5:
                        severity = 'medium'
                    if ratio > spike_ratio * 2:
                        severity = 'high'

                    bugs.append(EnergyBug(
                        bug_type=EnergyBugType.DRAIN_RATE_SPIKE,
                        severity=severity,
                        time_start=group_data['time_sec'].iloc[0],
                        time_end=group_data['time_sec'].iloc[-1],
                        description=f"Battery drain rate spike: {max_drain:.2f}%/min (baseline: {baseline_drain*60:.2f}%/min)",
                        metrics={
                            'max_drain_rate_per_min': round(max_drain, 2),
                            'avg_drain_rate_per_min': round(avg_drain, 2),
                            'baseline_drain_per_min': round(baseline_drain * 60, 2),
                            'spike_ratio': round(ratio, 2)
                        }
                    ))

        return bugs

    def detect_all(self) -> List[EnergyBug]:
        """
        Run all detection algorithms and return combined results.

        Returns:
            List of all detected EnergyBug instances, sorted by time
        """
        self._bugs = []

        # Run all detectors
        self._bugs.extend(self.detect_energy_vampires())
        self._bugs.extend(self.detect_voltage_anomalies())
        self._bugs.extend(self.detect_motor_inefficiency())
        self._bugs.extend(self.detect_drain_rate_spikes())

        # Sort by start time
        self._bugs.sort(key=lambda b: b.time_start)

        return self._bugs

    def get_bug_summary(self) -> Dict:
        """
        Get summary of detected bugs.

        Returns:
            Dictionary with bug counts by type and severity
        """
        if not self._bugs:
            self.detect_all()

        summary = {
            'total_bugs': len(self._bugs),
            'by_type': {},
            'by_severity': {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        }

        for bug in self._bugs:
            bug_type = bug.bug_type.value
            if bug_type not in summary['by_type']:
                summary['by_type'][bug_type] = 0
            summary['by_type'][bug_type] += 1
            summary['by_severity'][bug.severity] += 1

        return summary

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert detected bugs to a DataFrame for analysis.

        Returns:
            DataFrame with bug information
        """
        if not self._bugs:
            self.detect_all()

        records = [bug.to_dict() for bug in self._bugs]
        return pd.DataFrame(records)


if __name__ == "__main__":
    # Test with mission1.ulg
    import os

    log_path = "../UAV-Testing-Competition/snippets/case_studies/mission1.ulg"

    if os.path.exists(log_path):
        print("Loading flight data...")
        monitor = EnergyMonitor(log_path)

        print("Running energy analysis...")
        analyzer = EnergyAnalyzer(monitor)
        bugs = analyzer.detect_all()

        print(f"\n Detected {len(bugs)} Energy Bugs ")
        for bug in bugs:
            print(f"\n[{bug.severity.upper()}] {bug.bug_type.value}")
            print(f"  Time: {bug.time_start:.1f}s - {bug.time_end:.1f}s")
            print(f"  {bug.description}")

        print("\n Bug Summary ")
        summary = analyzer.get_bug_summary()
        print(f"Total bugs: {summary['total_bugs']}")
        print(f"By type: {summary['by_type']}")
        print(f"By severity: {summary['by_severity']}")
    else:
        print(f"Log file not found: {log_path}")
