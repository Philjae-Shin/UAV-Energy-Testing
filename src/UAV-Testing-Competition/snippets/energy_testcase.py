"""
EnergyTestCase

Post-hoc mode: Analyze .ulg from a previous test run

Usage (Post-hoc mode - standalone):
    from energy_testcase import EnergyTestCase

    tc = EnergyTestCase.from_log("path/to/flight.ulg")
    tc.analyze_energy()
    print(tc.energy_bugs)
    tc.plot_energy("output.png")
    report = tc.get_energy_report()

Author: Henry Shin
"""
# 44444

import sys
import os
import logging
from typing import List, Optional

# energy module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# energy module import
try:
    from energy import EnergyMonitor, EnergyAnalyzer, EnergyVisualizer
    ENERGY_AVAILABLE = True
except ImportError:
    ENERGY_AVAILABLE = False
    print("Warning: energy module not available. Install pyulog, pandas, matplotlib.")

# Aerialist imports (optional for post-hoc mode)
try:
    from testcase import TestCase
    from aerialist.px4.aerialist_test import AerialistTest
    from aerialist.px4.obstacle import Obstacle
    from aerialist.px4.trajectory import Trajectory
    AERIALIST_AVAILABLE = True
except ImportError:
    AERIALIST_AVAILABLE = False

logger = logging.getLogger(__name__)


class EnergyTestCase:
    """
    TestCase extension with integrated energy bug detection.

    Supports two modes:
    - Auto mode: wraps Aerialist TestCase, runs energy analysis after test
    - Post-hoc mode: analyzes .ulg files from previous test runs
    """

    def __init__(self, casestudy=None, obstacles=None,
                 auto_analyze: bool = True, log_file: str = None):
        """
        Args:
            casestudy: Aerialist test configuration (None for post-hoc mode)
            obstacles: Obstacle list for test (None for post-hoc mode)
            auto_analyze: Auto-run energy analysis after test execution
            log_file: Path to .ulg file (for post-hoc mode)
        """
        # Aerialist test case (if in auto mode)
        self._testcase = None
        if casestudy is not None and AERIALIST_AVAILABLE:
            self._testcase = TestCase(casestudy, obstacles or [])

        self.auto_analyze = auto_analyze
        self.log_file = log_file

        # Energy analysis results
        self.energy_monitor: Optional[EnergyMonitor] = None
        self.energy_analyzer: Optional[EnergyAnalyzer] = None
        self.energy_visualizer: Optional[EnergyVisualizer] = None
        self.energy_summary = None
        self.energy_bugs = []
        self.energy_profile = None

    @classmethod
    def from_log(cls, log_file: str, auto_analyze: bool = False) -> 'EnergyTestCase':
        """
        Create EnergyTestCase in post-hoc mode from a .ulg file.

        Args:
            log_file: Path to .ulg file
            auto_analyze: Whether to run analysis immediately

        Returns:
            EnergyTestCase instance ready for analysis
        """
        if not os.path.exists(log_file):
            raise FileNotFoundError(f"Log file not found: {log_file}")

        instance = cls(log_file=log_file, auto_analyze=False)

        if auto_analyze:
            instance.analyze_energy()

        return instance

    def execute(self):
        """
        Execute test via Aerialist, then optionally run energy analysis.

        Returns:
            Trajectory from test execution
        """
        if self._testcase is None:
            raise RuntimeError(
                "No Aerialist test case configured. "
                "Use from_log() for post-hoc analysis."
            )

        # Run Aerialist test
        trajectory = self._testcase.execute()

        # Get log file from test results
        if hasattr(self._testcase, 'log_file'):
            self.log_file = self._testcase.log_file
        elif hasattr(self._testcase, 'test_results') and self._testcase.test_results:
            self.log_file = self._testcase.test_results[0].log_file

        # Auto energy analysis
        if self.auto_analyze and ENERGY_AVAILABLE and self.log_file:
            logger.info("Running energy analysis...")
            self.analyze_energy()
            logger.info(f"Energy analysis complete. Found {len(self.energy_bugs)} bugs")

        return trajectory

    def analyze_energy(self, log_file: str = None,
                       thresholds: dict = None) -> List:
        """
        Run energy bug detection on the .ulg file.

        Args:
            log_file: Override .ulg file path
            thresholds: Custom detection thresholds

        Returns:
            List of detected EnergyBug objects
        """
        if not ENERGY_AVAILABLE:
            logger.warning("Energy module not available")
            return []

        ulg_path = log_file or self.log_file
        if not ulg_path or not os.path.exists(ulg_path):
            logger.warning(f"Log file not found: {ulg_path}")
            return []

        try:
            # Extract energy data
            self.energy_monitor = EnergyMonitor(ulg_path)
            self.energy_summary = self.energy_monitor.get_flight_summary()
            self.energy_profile = self.energy_monitor.get_energy_profile()

            # Detect bugs
            self.energy_analyzer = EnergyAnalyzer(
                self.energy_monitor,
                thresholds=thresholds
            )
            self.energy_bugs = self.energy_analyzer.detect_all()

            # Prepare visualizer
            self.energy_visualizer = EnergyVisualizer(
                self.energy_monitor, self.energy_analyzer
            )

            return self.energy_bugs

        except Exception as e:
            logger.error(f"Energy analysis failed: {e}")
            return []

    def plot_energy(self, output_path: str = None) -> str:
        """
        Generate energy profile visualization.

        Args:
            output_path: Save path (default: alongside .ulg file)

        Returns:
            Path to saved plot
        """
        if not ENERGY_AVAILABLE or not self.energy_monitor:
            logger.warning("Run analyze_energy() first")
            return ""

        if output_path is None:
            base_dir = os.path.dirname(self.log_file) or "."
            output_path = os.path.join(base_dir, "energy_profile.png")

        if self.energy_visualizer is None:
            self.energy_visualizer = EnergyVisualizer(
                self.energy_monitor, self.energy_analyzer
            )

        self.energy_visualizer.plot_energy_profile(output_path)
        return output_path

    def plot_bug_timeline(self, output_path: str = None) -> str:
        """
        Generate bug timeline visualization.

        Args:
            output_path: Save path

        Returns:
            Path to saved plot
        """
        if not self.energy_visualizer or not self.energy_bugs:
            logger.warning("No bugs to plot. Run analyze_energy() first.")
            return ""

        if output_path is None:
            base_dir = os.path.dirname(self.log_file) or "."
            output_path = os.path.join(base_dir, "bug_timeline.png")

        self.energy_visualizer.plot_bug_timeline(output_path)
        return output_path

    def get_energy_report(self) -> dict:
        """
        Get comprehensive energy analysis report.

        Returns:
            Dictionary with summary, bugs, severity counts, recommendations
        """
        report = {
            'log_file': self.log_file,
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
            if 'drain_rate_spike' in bug_types:
                report['recommendations'].append(
                    "Drain rate spike detected: Review flight controller software for sudden compute bursts."
                )

        return report

    def has_energy_bugs(self, min_severity: str = 'low') -> bool:
        """
        Check if energy bugs exist at or above a severity level.

        Args:
            min_severity: Minimum severity ('low', 'medium', 'high', 'critical')

        Returns:
            True if matching bugs exist
        """
        severity_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
        min_level = severity_order.get(min_severity, 0)

        for bug in self.energy_bugs:
            if severity_order.get(bug.severity, 0) >= min_level:
                return True
        return False

    def __repr__(self):
        status = "analyzed" if self.energy_bugs is not None and self.energy_monitor else "pending"
        bug_count = len(self.energy_bugs) if self.energy_bugs else 0
        return f"EnergyTestCase(log={self.log_file}, status={status}, bugs={bug_count})"


# CLI for quick post-hoc analysis
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='EnergyTestCase - Post-hoc Analysis')
    parser.add_argument('log_file', help='Path to .ulg file')
    parser.add_argument('--plot', '-p', action='store_true', help='Generate plots')
    parser.add_argument('--output', '-o', help='Output directory for plots')
    args = parser.parse_args()

    # Post-hoc analysis
    tc = EnergyTestCase.from_log(args.log_file, auto_analyze=True)

    print(f"\n{tc}")
    report = tc.get_energy_report()

    print(f"\n Flight Summary ")
    if report['summary']:
        for k, v in report['summary'].items():
            print(f"  {k}: {v}")

    print(f"\n Energy Bugs ({report['bug_count']}) ")
    for bug in report['bugs']:
        print(f"  [{bug['severity'].upper()}] {bug['type']}")
        print(f"    {bug['description']}")

    if report['recommendations']:
        print(f"\n Recommendations ")
        for rec in report['recommendations']:
            print(f"  - {rec}")

    if args.plot:
        out_dir = args.output or os.path.dirname(args.log_file) or "."
        tc.plot_energy(os.path.join(out_dir, "energy_profile.png"))
        tc.plot_bug_timeline(os.path.join(out_dir, "bug_timeline.png"))
        print(f"\nPlots saved to {out_dir}")
