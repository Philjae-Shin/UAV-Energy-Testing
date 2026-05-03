# Energy Monitor Module
"""
EnergyMonitor: Core class for extracting battery and motor data from .ulg flight logs.

Usage:
    from energy.monitor import EnergyMonitor

    monitor = EnergyMonitor("path/to/flight.ulg")
    battery_df = monitor.get_battery_data()
    motor_df = monitor.get_motor_data()
    summary = monitor.get_flight_summary()
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pyulog import ULog


@dataclass
class FlightSummary:
    """Summary statistics for a single flight."""
    flight_duration_sec: float
    battery_consumed_pct: float
    voltage_drop_v: float
    avg_motor_output: float
    max_motor_output: float
    energy_efficiency: float  # % battery per minute

    def to_dict(self) -> Dict:
        return {
            'flight_duration_sec': self.flight_duration_sec,
            'battery_consumed_pct': self.battery_consumed_pct,
            'voltage_drop_v': self.voltage_drop_v,
            'avg_motor_output': self.avg_motor_output,
            'max_motor_output': self.max_motor_output,
            'energy_efficiency': self.energy_efficiency
        }


class EnergyMonitor:
    """
    Extracts and processes energy-related data from PX4 ULog files.

    Supported PX4 topics:
    - battery_status: voltage, current, remaining capacity, discharge
    - actuator_outputs: motor PWM outputs (4 motors for quadcopter)
    - vehicle_local_position: altitude for correlation analysis
    """

    # PX4 topic names
    BATTERY_TOPIC = 'battery_status'
    ACTUATOR_TOPIC = 'actuator_outputs'
    POSITION_TOPIC = 'vehicle_local_position'

    # Key columns for each topic
    BATTERY_COLUMNS = ['timestamp', 'voltage_v', 'current_a', 'remaining', 'discharged_mah']
    MOTOR_COLUMNS = ['timestamp', 'output[0]', 'output[1]', 'output[2]', 'output[3]']
    POSITION_COLUMNS = ['timestamp', 'x', 'y', 'z']

    def __init__(self, log_file: str):
        """
        Initialize EnergyMonitor with a ULog file.

        Args:
            log_file: Path to the .ulg flight log file
        """
        self.log_file = log_file
        self._ulog: Optional[ULog] = None
        self._battery_df: Optional[pd.DataFrame] = None
        self._motor_df: Optional[pd.DataFrame] = None
        self._position_df: Optional[pd.DataFrame] = None
        self._load_log()

    def _load_log(self) -> None:
        """Load the ULog file."""
        try:
            self._ulog = ULog(self.log_file)
        except Exception as e:
            raise ValueError(f"Failed to load ULog file: {self.log_file}") from e

    def _extract_topic(self, topic_name: str, columns: List[str]) -> Optional[pd.DataFrame]:
        """
        Extract data from a specific PX4 topic.

        Args:
            topic_name: Name of the PX4 topic
            columns: List of column names to extract

        Returns:
            DataFrame with extracted data, or None if topic not found
        """
        for data in self._ulog.data_list:
            if data.name == topic_name:
                df = pd.DataFrame(data.data)
                # Filter to only requested columns that exist
                available_cols = [c for c in columns if c in df.columns]
                return df[available_cols]
        return None

    def get_battery_data(self) -> pd.DataFrame:
        """
        Get battery status data.

        Returns:
            DataFrame with columns: timestamp, voltage_v, current_a, remaining, discharged_mah
        """
        if self._battery_df is None:
            self._battery_df = self._extract_topic(self.BATTERY_TOPIC, self.BATTERY_COLUMNS)
            if self._battery_df is not None:
                # Convert timestamp to seconds from start
                self._battery_df['time_sec'] = (
                    self._battery_df['timestamp'] - self._battery_df['timestamp'].iloc[0]
                ) / 1e6
        return self._battery_df

    def get_motor_data(self) -> pd.DataFrame:
        """
        Get motor (actuator) output data.

        Returns:
            DataFrame with columns: timestamp, output[0-3] (PWM values)
        """
        if self._motor_df is None:
            self._motor_df = self._extract_topic(self.ACTUATOR_TOPIC, self.MOTOR_COLUMNS)
            if self._motor_df is not None:
                # Convert timestamp to seconds from start
                self._motor_df['time_sec'] = (
                    self._motor_df['timestamp'] - self._motor_df['timestamp'].iloc[0]
                ) / 1e6
                # Calculate average motor output
                motor_cols = [c for c in self._motor_df.columns if c.startswith('output[')]
                self._motor_df['avg_output'] = self._motor_df[motor_cols].mean(axis=1)
        return self._motor_df

    def get_position_data(self) -> pd.DataFrame:
        """
        Get vehicle position data (for altitude correlation).

        Returns:
            DataFrame with columns: timestamp, x, y, z
        """
        if self._position_df is None:
            self._position_df = self._extract_topic(self.POSITION_TOPIC, self.POSITION_COLUMNS)
            if self._position_df is not None:
                self._position_df['time_sec'] = (
                    self._position_df['timestamp'] - self._position_df['timestamp'].iloc[0]
                ) / 1e6
                # Convert z to positive altitude (PX4 uses NED, z is negative up)
                self._position_df['altitude'] = -self._position_df['z']
        return self._position_df

    def get_flight_summary(self) -> FlightSummary:
        """
        Calculate summary statistics for the flight.

        Returns:
            FlightSummary dataclass with key metrics
        """
        battery_df = self.get_battery_data()
        motor_df = self.get_motor_data()

        if battery_df is None or battery_df.empty:
            raise ValueError("No battery data available")

        # Flight duration
        flight_duration = battery_df['time_sec'].max()

        # Battery consumption
        battery_start = battery_df['remaining'].iloc[0] * 100
        battery_end = battery_df['remaining'].iloc[-1] * 100
        battery_consumed = battery_start - battery_end

        # Voltage drop
        voltage_start = battery_df['voltage_v'].iloc[0]
        voltage_end = battery_df['voltage_v'].iloc[-1]
        voltage_drop = voltage_start - voltage_end

        # Motor statistics
        if motor_df is not None and not motor_df.empty:
            avg_motor = motor_df['avg_output'].mean()
            max_motor = motor_df['avg_output'].max()
        else:
            avg_motor = 0.0
            max_motor = 0.0

        # Energy efficiency (% battery per minute)
        if flight_duration > 0:
            energy_efficiency = (battery_consumed / flight_duration) * 60
        else:
            energy_efficiency = 0.0

        return FlightSummary(
            flight_duration_sec=round(flight_duration, 2),
            battery_consumed_pct=round(battery_consumed, 2),
            voltage_drop_v=round(voltage_drop, 2),
            avg_motor_output=round(avg_motor, 2),
            max_motor_output=round(max_motor, 2),
            energy_efficiency=round(energy_efficiency, 2)
        )

    def get_available_topics(self) -> List[str]:
        """Get list of all available topics in the log file."""
        return [d.name for d in self._ulog.data_list]

    def get_energy_profile(self, resample_sec: float = 1.0) -> pd.DataFrame:
        """
        Get unified energy profile with battery, motor, and position data.
        Resampled to common time intervals for analysis.

        Args:
            resample_sec: Resample interval in seconds (default 1.0)

        Returns:
            DataFrame with time-aligned energy metrics
        """
        battery_df = self.get_battery_data()
        motor_df = self.get_motor_data()
        position_df = self.get_position_data()

        if battery_df is None:
            raise ValueError("No battery data available")

        # Create time index
        max_time = battery_df['time_sec'].max()
        time_index = np.arange(0, max_time, resample_sec)

        profile = pd.DataFrame({'time_sec': time_index})

        # Interpolate battery data
        profile['voltage_v'] = np.interp(time_index, battery_df['time_sec'], battery_df['voltage_v'])
        profile['remaining_pct'] = np.interp(time_index, battery_df['time_sec'], battery_df['remaining']) * 100

        if 'current_a' in battery_df.columns:
            profile['current_a'] = np.interp(time_index, battery_df['time_sec'], battery_df['current_a'])

        # Interpolate motor data
        if motor_df is not None and not motor_df.empty:
            profile['motor_avg'] = np.interp(time_index, motor_df['time_sec'], motor_df['avg_output'])

        # Interpolate position data
        if position_df is not None and not position_df.empty:
            profile['altitude'] = np.interp(time_index, position_df['time_sec'], position_df['altitude'])

        return profile


if __name__ == "__main__":
    # Test with mission1.ulg
    import os

    # Adjust path as needed
    log_path = "../UAV-Testing-Competition/snippets/case_studies/mission1.ulg"

    if os.path.exists(log_path):
        monitor = EnergyMonitor(log_path)

        print("=== Available Topics ===")
        for topic in monitor.get_available_topics()[:10]:
            print(f"  - {topic}")

        print("\n=== Flight Summary ===")
        summary = monitor.get_flight_summary()
        for key, value in summary.to_dict().items():
            print(f"  {key}: {value}")

        print("\n=== Energy Profile (first 5 rows) ===")
        profile = monitor.get_energy_profile()
        print(profile.head())
    else:
        print(f"Log file not found: {log_path}")
