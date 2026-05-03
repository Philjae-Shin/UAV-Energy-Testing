# Energy Visualizer Module
"""
EnergyVisualizer: Creates plots for energy data and detected bugs.

Usage:
    from energy.visualizer import EnergyVisualizer
    from energy.monitor import EnergyMonitor
    from energy.analyzer import EnergyAnalyzer

    monitor = EnergyMonitor("flight.ulg")
    analyzer = EnergyAnalyzer(monitor)
    visualizer = EnergyVisualizer(monitor, analyzer)
    visualizer.plot_energy_profile("output.png")
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from typing import Optional, List, Tuple
from pathlib import Path

from .monitor import EnergyMonitor
from .analyzer import EnergyAnalyzer, EnergyBug, EnergyBugType


class EnergyVisualizer:
    """Creates visualizations for energy analysis."""

    # Color scheme for different bug types
    BUG_COLORS = {
        EnergyBugType.ENERGY_VAMPIRE: '#FF6B6B',      # Red
        EnergyBugType.VOLTAGE_ANOMALY: '#4ECDC4',     # Teal
        EnergyBugType.MOTOR_INEFFICIENCY: '#FFE66D',  # Yellow
        EnergyBugType.DRAIN_RATE_SPIKE: '#95E1D3',    # Mint green
        EnergyBugType.BATTERY_STRESS: '#F38181',      # Coral
    }

    SEVERITY_ALPHA = {
        'low': 0.2,
        'medium': 0.4,
        'high': 0.6,
        'critical': 0.8
    }

    def __init__(self, monitor: EnergyMonitor, analyzer: Optional[EnergyAnalyzer] = None):
        """
        Initialize visualizer.

        Args:
            monitor: EnergyMonitor instance
            analyzer: Optional EnergyAnalyzer instance for bug highlighting
        """
        self.monitor = monitor
        self.analyzer = analyzer
        self._bugs: List[EnergyBug] = []
        if analyzer:
            self._bugs = analyzer.detect_all()

    def plot_energy_profile(self, output_path: str, figsize: Tuple[int, int] = (14, 10),
                           show_bugs: bool = True) -> str:
        """
        Create comprehensive energy profile plot.

        Args:
            output_path: Path to save the figure
            figsize: Figure size (width, height)
            show_bugs: Whether to highlight detected bugs

        Returns:
            Path to saved figure
        """
        fig, axes = plt.subplots(4, 1, figsize=figsize, sharex=True)
        fig.suptitle('UAV Energy Analysis Profile', fontsize=14, fontweight='bold')

        profile = self.monitor.get_energy_profile()
        time = profile['time_sec']

        # 1. Altitude plot
        ax1 = axes[0]
        if 'altitude' in profile.columns:
            ax1.plot(time, profile['altitude'], 'b-', linewidth=1.5, label='Altitude')
            ax1.fill_between(time, 0, profile['altitude'], alpha=0.3)
        ax1.set_ylabel('Altitude (m)')
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)
        ax1.set_title('Flight Profile')

        # 2. Battery percentage
        ax2 = axes[1]
        if 'remaining_pct' in profile.columns:
            ax2.plot(time, profile['remaining_pct'], 'g-', linewidth=1.5, label='Battery %')
            ax2.fill_between(time, 0, profile['remaining_pct'], alpha=0.3, color='green')
        ax2.set_ylabel('Battery (%)')
        ax2.set_ylim(0, 105)
        ax2.legend(loc='upper right')
        ax2.grid(True, alpha=0.3)
        ax2.set_title('Battery Level')

        # 3. Voltage
        ax3 = axes[2]
        if 'voltage_v' in profile.columns:
            ax3.plot(time, profile['voltage_v'], 'orange', linewidth=1.5, label='Voltage')
            ax3.axhline(y=14.8, color='r', linestyle='--', alpha=0.5, label='Low voltage threshold')
        ax3.set_ylabel('Voltage (V)')
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        ax3.set_title('Battery Voltage')

        # 4. Motor output
        ax4 = axes[3]
        if 'motor_avg' in profile.columns:
            ax4.plot(time, profile['motor_avg'], 'purple', linewidth=1.5, label='Avg Motor PWM')
            ax4.fill_between(time, 900, profile['motor_avg'], alpha=0.3, color='purple')
        ax4.set_ylabel('Motor PWM')
        ax4.set_xlabel('Time (seconds)')
        ax4.legend(loc='upper right')
        ax4.grid(True, alpha=0.3)
        ax4.set_title('Motor Output')

        # Highlight detected bugs
        if show_bugs and self._bugs:
            self._highlight_bugs(axes)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        return output_path

    def _highlight_bugs(self, axes: List) -> None:
        """Add bug highlighting to all axes."""
        for bug in self._bugs:
            color = self.BUG_COLORS.get(bug.bug_type, 'gray')
            alpha = self.SEVERITY_ALPHA.get(bug.severity, 0.3)

            for ax in axes:
                ax.axvspan(bug.time_start, bug.time_end, alpha=alpha, color=color)

        # Add legend for bug types
        legend_patches = []
        bug_types_present = set(bug.bug_type for bug in self._bugs)
        for bug_type in bug_types_present:
            patch = mpatches.Patch(
                color=self.BUG_COLORS[bug_type],
                alpha=0.5,
                label=bug_type.value.replace('_', ' ').title()
            )
            legend_patches.append(patch)

        if legend_patches:
            axes[0].legend(handles=legend_patches, loc='upper left', fontsize=8)

    def plot_bug_timeline(self, output_path: str, figsize: Tuple[int, int] = (12, 4)) -> str:
        """
        Create bug timeline visualization.

        Args:
            output_path: Path to save the figure
            figsize: Figure size

        Returns:
            Path to saved figure
        """
        if not self._bugs:
            print("No bugs to visualize")
            return ""

        fig, ax = plt.subplots(figsize=figsize)
        fig.suptitle('Energy Bug Timeline', fontsize=12, fontweight='bold')

        # Group bugs by type
        bug_types = list(set(bug.bug_type for bug in self._bugs))
        y_positions = {bt: i for i, bt in enumerate(bug_types)}

        for bug in self._bugs:
            y = y_positions[bug.bug_type]
            width = bug.time_end - bug.time_start
            color = self.BUG_COLORS.get(bug.bug_type, 'gray')
            alpha = min(self.SEVERITY_ALPHA.get(bug.severity, 0.3) + 0.3, 1.0)

            ax.barh(y, width, left=bug.time_start, height=0.6,
                   color=color, alpha=alpha, edgecolor='black', linewidth=0.5)

            # Add severity label
            ax.text(bug.time_start + width/2, y, bug.severity[0].upper(),
                   ha='center', va='center', fontsize=8, fontweight='bold')

        ax.set_yticks(range(len(bug_types)))
        ax.set_yticklabels([bt.value.replace('_', ' ').title() for bt in bug_types])
        ax.set_xlabel('Time (seconds)')
        ax.set_ylabel('Bug Type')
        ax.grid(True, alpha=0.3, axis='x')

        # Add severity legend
        severity_patches = [
            mpatches.Patch(color='gray', alpha=min(a+0.3, 1.0), label=s.title())
            for s, a in self.SEVERITY_ALPHA.items()
        ]
        ax.legend(handles=severity_patches, loc='upper right', title='Severity')

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        return output_path

    def plot_comparison(self, other_monitors: List[EnergyMonitor],
                       labels: List[str], output_path: str,
                       figsize: Tuple[int, int] = (12, 8)) -> str:
        """
        Compare energy profiles across multiple flights.

        Args:
            other_monitors: List of EnergyMonitor instances to compare
            labels: Labels for each flight
            output_path: Path to save the figure
            figsize: Figure size

        Returns:
            Path to saved figure
        """
        fig, axes = plt.subplots(2, 2, figsize=figsize)
        fig.suptitle('Multi-Flight Energy Comparison', fontsize=14, fontweight='bold')

        all_monitors = [self.monitor] + other_monitors
        all_labels = ['Current'] + labels
        colors = plt.cm.tab10(np.linspace(0, 1, len(all_monitors)))

        for i, (monitor, label, color) in enumerate(zip(all_monitors, all_labels, colors)):
            profile = monitor.get_energy_profile()
            time = profile['time_sec']

            # Battery percentage
            if 'remaining_pct' in profile.columns:
                axes[0, 0].plot(time, profile['remaining_pct'], color=color, label=label)

            # Voltage
            if 'voltage_v' in profile.columns:
                axes[0, 1].plot(time, profile['voltage_v'], color=color, label=label)

            # Motor output
            if 'motor_avg' in profile.columns:
                axes[1, 0].plot(time, profile['motor_avg'], color=color, label=label)

            # Altitude
            if 'altitude' in profile.columns:
                axes[1, 1].plot(time, profile['altitude'], color=color, label=label)

        axes[0, 0].set_ylabel('Battery (%)')
        axes[0, 0].set_title('Battery Drain')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        axes[0, 1].set_ylabel('Voltage (V)')
        axes[0, 1].set_title('Voltage')
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)

        axes[1, 0].set_ylabel('Motor PWM')
        axes[1, 0].set_xlabel('Time (s)')
        axes[1, 0].set_title('Motor Output')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)

        axes[1, 1].set_ylabel('Altitude (m)')
        axes[1, 1].set_xlabel('Time (s)')
        axes[1, 1].set_title('Flight Profile')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        return output_path


if __name__ == "__main__":
    import os

    log_path = "../UAV-Testing-Competition/snippets/case_studies/mission1.ulg"

    if os.path.exists(log_path):
        print("Creating energy visualizations...")

        monitor = EnergyMonitor(log_path)
        analyzer = EnergyAnalyzer(monitor)
        visualizer = EnergyVisualizer(monitor, analyzer)

        # Generate plots
        profile_path = "../../Project_Planning/energy_profile_with_bugs.png"
        visualizer.plot_energy_profile(profile_path)
        print(f"Saved: {profile_path}")

        timeline_path = "../../Project_Planning/bug_timeline.png"
        visualizer.plot_bug_timeline(timeline_path)
        print(f"Saved: {timeline_path}")
    else:
        print(f"Log file not found: {log_path}")
