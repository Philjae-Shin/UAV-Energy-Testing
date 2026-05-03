"""
UAV Energy Analysis Runner
A script to batch analyze multiple .ulg files and save the results

Usage:
    # Analyze a single file
    python3 run_energy_analysis.py results/mission1.ulg

    # Analyze multiple files
    python3 run_energy_analysis.py results/*.ulg

    # Analyze an entire directory
    python3 run_energy_analysis.py --dir results/

    # Output results only (do not save files)
    python3 run_energy_analysis.py results/mission1.ulg --no-save

Author: Henry Shin
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from typing import List, Dict

# Add energy module path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from energy import EnergyMonitor, EnergyAnalyzer, EnergyVisualizer


def analyze_single_file(ulg_path: str, save_results: bool = True,
                        save_plot: bool = True) -> Dict:
    """
    Analyze a single .ulg file

    Args:
        ulg_path: Path to the .ulg file
        save_results: Whether to save JSON results
        save_plot: Whether to save plot images

    Returns:
        Analysis result dictionary
    """
    print(f"\n{'='*60}")
    print(f"Analyzing: {ulg_path}")
    print('='*60)

    try:
        # 1. Monitoring - Data Extraction
        monitor = EnergyMonitor(ulg_path)
        summary = monitor.get_flight_summary()

        print(f"\n[Flight Summary]")
        print(f"  Duration: {summary.flight_duration_sec:.1f} sec")
        print(f"  Battery consumed: {summary.battery_consumed_pct:.1f}%")
        print(f"  Voltage drop: {summary.voltage_drop_v:.2f}V")
        print(f"  Avg motor output: {summary.avg_motor_output:.0f} PWM")
        print(f"  Energy efficiency: {summary.energy_efficiency:.2f}%/min")

        # 2. Analysis - Bug Detection
        analyzer = EnergyAnalyzer(monitor)
        bugs = analyzer.detect_all()

        print(f"\n[Energy Bugs Detected: {len(bugs)}]")
        for bug in bugs:
            severity_color = {
                'low': ' ', # not adding and signal atm
                'medium': '',
                'high': ' ',
                'critical': ' '
            }
            print(f"  {severity_color.get(bug.severity, '')}{bug.bug_type.value} ({bug.severity})")
            print(f"    Time: {bug.time_start:.1f}s - {bug.time_end:.1f}s")
            print(f"    {bug.description}")

        # 3. Save results (convert numpy types to Python types)
        def convert_numpy(obj):
            """Convert numpy types to Python native types for JSON serialization"""
            import numpy as np
            if isinstance(obj, dict):
                return {k: convert_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(v) for v in obj]
            elif isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        result = {
            'file': os.path.basename(ulg_path),
            'path': ulg_path,
            'analyzed_at': datetime.now().isoformat(),
            'summary': convert_numpy(summary.to_dict()),
            'bugs': convert_numpy([b.to_dict() for b in bugs]),
            'bug_count': len(bugs),
            'bug_summary': convert_numpy(analyzer.get_bug_summary())
        }

        if save_results:
            json_path = ulg_path.replace('.ulg', '_energy_report.json')
            with open(json_path, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n[Saved] Report: {json_path}")

        # 4. Save plots
        if save_plot:
            visualizer = EnergyVisualizer(monitor, analyzer)

            # Energy profile plot
            plot_path = ulg_path.replace('.ulg', '_energy_plot.png')
            visualizer.plot_energy_profile(plot_path)
            print(f"[Saved] Plot: {plot_path}")

            # Save timeline plot if bugs are detected
            if bugs:
                timeline_path = ulg_path.replace('.ulg', '_bug_timeline.png')
                visualizer.plot_bug_timeline(timeline_path)
                print(f"[Saved] Timeline: {timeline_path}")

        return result

    except Exception as e:
        print(f"[ERROR] Failed to analyze {ulg_path}: {e}")
        return {
            'file': os.path.basename(ulg_path),
            'error': str(e)
        }


def analyze_multiple_files(ulg_paths: List[str], output_dir: str = None,
                           save_results: bool = True) -> List[Dict]:
    """
    Batch analyse multiple .ulg files

    Args:
        ulg_paths: List of .ulg file paths
        output_dir: Directory to save results (default: same directory as each file)
        save_results: Whether to save results

    Returns:
        List of all analysis results
    """
    all_results = []

    print(f"# UAV Energy Analysis - {len(ulg_paths)} files")

    for ulg_path in ulg_paths:
        result = analyze_single_file(ulg_path, save_results=save_results)
        all_results.append(result)

    # Print overall summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)

    total_bugs = sum(r.get('bug_count', 0) for r in all_results if 'error' not in r)
    successful = sum(1 for r in all_results if 'error' not in r)
    failed = len(all_results) - successful

    print(f"Files analyzed: {successful}/{len(all_results)}")
    print(f"Total bugs found: {total_bugs}")

    if failed > 0:
        print(f"Failed: {failed}")

    # Summary table by file
    print(f"\n{'File':<30} {'Duration':<12} {'Battery':<10} {'Bugs':<6}")
    print('-'*60)
    for r in all_results:
        if 'error' in r:
            print(f"{r['file']:<30} {'ERROR':<12}")
        else:
            duration = r['summary']['flight_duration_sec']
            battery = r['summary']['battery_consumed_pct']
            bugs = r['bug_count']
            print(f"{r['file']:<30} {duration:>8.1f}s   {battery:>6.1f}%    {bugs:>3}")

    # Save overall results CSV
    if save_results and output_dir:
        save_summary_csv(all_results, os.path.join(output_dir, 'energy_summary.csv'))

    return all_results


def save_summary_csv(results: List[Dict], csv_path: str):
    """Save results to CSV (for Evaluation chapter)"""
    import csv

    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'file', 'duration_sec', 'battery_consumed_pct', 'voltage_drop_v',
            'avg_motor_output', 'energy_efficiency', 'total_bugs',
            'energy_vampire', 'voltage_anomaly', 'motor_inefficiency', 'drain_rate_spike'
        ])

        # Data
        for r in results:
            if 'error' in r:
                continue

            s = r['summary']
            bugs_by_type = r['bug_summary']['by_type']

            writer.writerow([
                r['file'],
                s['flight_duration_sec'],
                s['battery_consumed_pct'],
                s['voltage_drop_v'],
                s['avg_motor_output'],
                s['energy_efficiency'],
                r['bug_count'],
                bugs_by_type.get('energy_vampire', 0),
                bugs_by_type.get('voltage_anomaly', 0),
                bugs_by_type.get('motor_inefficiency', 0),
                bugs_by_type.get('drain_rate_spike', 0)
            ])

    print(f"\n[Saved] Summary CSV: {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description='UAV Energy Analysis - Detect energy bugs in PX4 flight logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_energy_analysis.py results/mission1.ulg
  python3 run_energy_analysis.py results/*.ulg
  python3 run_energy_analysis.py --dir results/
  python3 run_energy_analysis.py results/mission1.ulg --no-save --no-plot
        """
    )

    parser.add_argument('files', nargs='*', help='.ulg files to analyze')
    parser.add_argument('--dir', '-d', help='Directory containing .ulg files')
    parser.add_argument('--output', '-o', help='Output directory for results')
    parser.add_argument('--no-save', action='store_true', help='Do not save JSON results')
    parser.add_argument('--no-plot', action='store_true', help='Do not save plots')

    args = parser.parse_args()

    # Collect list of files
    ulg_files = []

    if args.dir:
        ulg_files.extend(glob.glob(os.path.join(args.dir, '*.ulg')))

    if args.files:
        for pattern in args.files:
            if '*' in pattern:
                ulg_files.extend(glob.glob(pattern))
            else:
                ulg_files.append(pattern)

    # Remove duplicates and check existence
    ulg_files = list(set(ulg_files))
    ulg_files = [f for f in ulg_files if os.path.exists(f)]

    if not ulg_files:
        print("No .ulg files found!")
        print("Usage: python3 run_energy_analysis.py <file.ulg> [file2.ulg ...]")
        print("       python3 run_energy_analysis.py --dir results/")
        sys.exit(1)

    # Run analysis
    save_results = not args.no_save

    if len(ulg_files) == 1:
        analyze_single_file(ulg_files[0], save_results=save_results,
                           save_plot=not args.no_plot)
    else:
        analyze_multiple_files(ulg_files, output_dir=args.output or os.path.dirname(ulg_files[0]),
                              save_results=save_results)


if __name__ == "__main__":
    main()
