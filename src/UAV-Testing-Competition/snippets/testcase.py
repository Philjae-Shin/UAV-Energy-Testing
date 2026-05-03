"""
EnergyTestCase - TestCase

Usage:
    from energy_testcase import EnergyTestCase

    tc = EnergyTestCase(casestudy, obstacles)
    trajectory = tc.execute()  # Test execution + energy analysis

    # Access energy results
    print(tc.energy_summary)
    print(tc.energy_bugs)
"""

import sys
import os
import logging
from typing import List, Optional

# Add energy module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from testcase import TestCase
from aerialist.px4.aerialist_test import AerialistTest
from aerialist.px4.obstacle import Obstacle
from aerialist.px4.trajectory import Trajectory

# Import energy module
try:
    from energy import EnergyMonitor, EnergyAnalyzer, EnergyVisualizer
    ENERGY_AVAILABLE = True
except ImportError:
    ENERGY_AVAILABLE = False
    print("Warning: energy module not available. Install pyulog, pandas, matplotlib.")

logger = logging.getLogger(__name__)


class EnergyTestCase(TestCase):
    """
    TestCase extension - adds energy analysis features

    All features of the original TestCase + energy bug detection
    """

    def __init__(self, casestudy: AerialistTest, obstacles: List[Obstacle],
                 auto_analyze: bool = True):
        """
        Args:
            casestudy: Aerialist test configuration
            obstacles: List of obstacles
            auto_analyze: Whether to automatically perform energy analysis after execute()
        """
        super().__init__(casestudy, obstacles)
        self.auto_analyze = auto_analyze

        # Energy analysis results
        self.energy_monitor: Optional[EnergyMonitor] = None
        self.energy_analyzer: Optional[EnergyAnalyzer] = None
        self.energy_summary = None
        self.energy_bugs = []
        self.energy_profile = None

    def execute(self) -> Trajectory:
        """
        Automatically performs energy analysis after test execution
        """
        # Run original test execution
        trajectory = super().execute()

        # Automatic energy analysis
        if self.auto_analyze and ENERGY_AVAILABLE and self.log_file:
            logger.info("running energy analysis...")
            self.analyze_energy()
            logger.info(f"energy analysis complete. found {len(self.energy_bugs)} bugs")

        return trajectory

    def analyze_energy(self, log_file: str = None) -> List:
        """
        Perform energy analysis

        Args:
            log_file: Path to .ulg file (default: self.log_file)

        Returns:
            List of detected energy bugs
        """
        if not ENERGY_AVAILABLE:
            logger.warning("energy module not available")
            return []

        ulg_path = log_file or self.log_file
        if not ulg_path or not os.path.exists(ulg_path):
            logger.warning(f"log file not found: {ulg_path}")
            return []

        try:
            # Monitoring
            self.energy_monitor = EnergyMonitor(ulg_path)
            self.energy_summary = self.energy_monitor.get_flight_summary()
            self.energy_profile = self.energy_monitor.get_energy_profile()

            # Bug detection
            self.energy_analyzer = EnergyAnalyzer(self.energy_monitor)
            self.energy_bugs = self.energy_analyzer.detect_all()

            return self.energy_bugs

        except Exception as e:
            logger.error(f"energy analysis failed: {e}")
            return []

    def plot_energy(self, output_path: str = None) -> str:
        """
        Visualize energy profile

        Args:
            output_path: Path to save the plot (default: same directory as log_file)

        Returns:
            Path to the saved file
        """
        if not ENERGY_AVAILABLE or not self.energy_monitor:
            logger.warning("run analyze_energy() first")
            return ""

        if output_path is None:
            base_dir = os.path.dirname(self.log_file) or "."
            output_path = os.path.join(base_dir, "energy_profile.png")

        visualizer = EnergyVisualizer(self.energy_monitor, self.energy_analyzer)
        visualizer.plot_energy_profile(output_path)

        self.energy_plot_file = output_path
        return output_path

    def get_energy_report(self) -> dict:
        """
        Energy analysis summary report

        Returns:
            dict with summary, bugs, and recommendations
        """
        report = {
            'summary': None,
            'bugs': [],
            'bug_count': 0,
            'severity_counts': {'low': 0, 'medium': 0, 'high': 0, 'critical': 0},
            'recommendations': []
        }

        if self.energy_summary:
            report['summary'] = self.energy_summary.to_dict()

        if self.energy_bugs:
            report['bugs'] = [bug.to_dict() for bug in self.energy_bugs]
            report['bug_count'] = len(self.energy_bugs)

            for bug in self.energy_bugs:
                report['severity_counts'][bug.severity] += 1

            # Generate recommendations
            if report['severity_counts']['high'] > 0 or report['severity_counts']['critical'] > 0:
                report['recommendations'].append(
                    "High/Critical severity bugs detected. Investigate immediately."
                )

            bug_types = set(bug.bug_type.value for bug in self.energy_bugs)
            if 'energy_vampire' in bug_types:
                report['recommendations'].append(
                    "Energy vampire detected: Check for unnecessary processing during idle/hover."
                )
            if 'voltage_anomaly' in bug_types:
                report['recommendations'].append(
                    "Voltage anomaly detected: Check battery health or high-current draws."
                )
            if 'motor_inefficiency' in bug_types:
                report['recommendations'].append(
                    "Motor inefficiency detected: Check propeller balance or motor calibration."
                )

        return report

    def has_energy_bugs(self, min_severity: str = 'low') -> bool:
        """
        Check if energy bugs exist at or above a certain severity

        Args:
            min_severity: Minimum severity ('low', 'medium', 'high', 'critical')

        Returns:
            True if bugs exist at or above min_severity
        """
        severity_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
        min_level = severity_order.get(min_severity, 0)

        for bug in self.energy_bugs:
            if severity_order.get(bug.severity, 0) >= min_level:
                return True
        return False


# Usage example
if __name__ == "__main__":
    print("EnergyTestCase - TestCase with integrated energy analysis")
    print()
    print("Usage:")
    print("  from energy_testcase import EnergyTestCase")
    print("  tc = EnergyTestCase(casestudy, obstacles)")
    print("  tc.execute()  # runs test + energy analysis")
    print("  print(tc.energy_bugs)")
    print("  tc.plot_energy('output.png')")
