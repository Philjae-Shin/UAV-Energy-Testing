"""
Post-hoc mode: Analyze .ulg files from previous test runs

Usage:

    # Post-hoc: analyze latest results
    python3 aerialist_energy_runner.py --analyze-latest

    # Post-hoc: analyze specific log directory
    python3 aerialist_energy_runner.py --analyze-dir results/logs/16-02-10-30-00/

"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Add energy module path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from energy import EnergyMonitor, EnergyAnalyzer, EnergyVisualizer


# Default paths
RESULTS_DIR = "results/logs"
ENERGY_RESULTS_DIR = "results/energy"


def run_aerialist_test(test_yaml: str, agent_path: str = None) -> Optional[str]:
    """
    Stage 1: Run Aerialist test and capture .ulg output path.

    Args:
        test_yaml: Path to test YAML configuration
        agent_path: Optional custom output path for logs

    Returns:
        Path to generated .ulg file, or None if failed
    """
    print(f"\n{'#'*60}")
    print(f"STAGE 1: Executing Aerialist Test")
    print(f"  Config: {test_yaml}")
    print(f"{'#'*60}\n")

    cmd = ["aerialist", "exec", "--test", test_yaml]
    if agent_path:
        cmd.extend(["--path", agent_path])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        # Parse stdout for LOG: line
        log_file = None
        for line in result.stdout.split('\n'):
            if line.startswith("LOG:"):
                log_file = line[4:].strip()
                break

        # Also search stderr (some versions output there)
        if not log_file:
            for line in result.stderr.split('\n'):
                if line.startswith("LOG:"):
                    log_file = line[4:].strip()
                    break

        # Fallback: find newest .ulg in results dir
        if not log_file:
            log_file = find_latest_ulg(RESULTS_DIR)

        if log_file and os.path.exists(log_file):
            print(f"\n[OK] Test completed. Log file: {log_file}")
            return log_file
        else:
            print(f"\n[WARN] Test completed but .ulg not found.")
            print(f"  stdout: {result.stdout[-500:] if result.stdout else 'empty'}")
            print(f"  stderr: {result.stderr[-500:] if result.stderr else 'empty'}")

            # Try to find any new .ulg
            log_file = find_latest_ulg(RESULTS_DIR)
            if log_file:
                print(f"  Found recent .ulg: {log_file}")
                return log_file

            return None

    except subprocess.TimeoutExpired:
        print("[ERROR] Aerialist test timed out (10 min)")
        return None
    except FileNotFoundError:
        print("[ERROR] 'aerialist' command not found. Is Aerialist installed?")
        print("  Install: cd Aerialist && pip install -e .")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to run test: {e}")
        return None


def find_latest_ulg(search_dir: str) -> Optional[str]:
    """
    Find the most recently modified .ulg file in a directory tree.

    Args:
        search_dir: Root directory to search

    Returns:
        Path to newest .ulg file, or None
    """
    ulg_files = glob.glob(os.path.join(search_dir, "**/*.ulg"), recursive=True)

    if not ulg_files:
        return None

    # Sort by modification time, newest first
    ulg_files.sort(key=os.path.getmtime, reverse=True)
    return ulg_files[0]


def find_all_ulg(search_dir: str) -> List[str]:
    """Find all .ulg files in a directory tree, sorted by modification time."""
    ulg_files = glob.glob(os.path.join(search_dir, "**/*.ulg"), recursive=True)
    ulg_files.sort(key=os.path.getmtime, reverse=True)
    return ulg_files


def run_energy_analysis(ulg_path: str, output_dir: str = None) -> Dict:
    """
    Stage 2: Run energy bug detection on a .ulg file.

    Args:
        ulg_path: Path to the .ulg file
        output_dir: Directory to save results (default: results/energy/)

    Returns:
        Analysis result dictionary
    """
    print(f"STAGE 2: Energy Analysis")
    print(f"  File: {ulg_path}")

    if output_dir is None:
        output_dir = ENERGY_RESULTS_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Generate output filename from input
    base_name = Path(ulg_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # 1. Extract energy data
        print("[1/3] Extracting energy telemetry...")
        monitor = EnergyMonitor(ulg_path)
        summary = monitor.get_flight_summary()

        print(f"  Duration: {summary.flight_duration_sec:.1f}s")
        print(f"  Battery consumed: {summary.battery_consumed_pct:.1f}%")
        print(f"  Voltage drop: {summary.voltage_drop_v:.2f}V")
        print(f"  Efficiency: {summary.energy_efficiency:.2f}%/min")

        # 2. Detect bugs
        print("\n[2/3] Running bug detection algorithms...")
        analyzer = EnergyAnalyzer(monitor)
        bugs = analyzer.detect_all()

        print(f"  Total bugs detected: {len(bugs)}")
        for bug in bugs:
            icon = {'low': 'o', 'medium': '!', 'high': '!!', 'critical': '!!!'}
            print(f"    [{icon.get(bug.severity, '?')}] {bug.bug_type.value} "
                  f"({bug.severity}) @ {bug.time_start:.1f}s-{bug.time_end:.1f}s")

        # 3. Generate visualizations
        print("\n[3/3] Generating visualizations...")
        visualizer = EnergyVisualizer(monitor, analyzer)

        plot_path = os.path.join(output_dir, f"{base_name}_energy_profile.png")
        visualizer.plot_energy_profile(plot_path)
        print(f"  Saved: {plot_path}")

        if bugs:
            timeline_path = os.path.join(output_dir, f"{base_name}_bug_timeline.png")
            visualizer.plot_bug_timeline(timeline_path)
            print(f"  Saved: {timeline_path}")

        # 4. Save JSON report
        def convert_numpy(obj):
            """Convert numpy types to Python native types."""
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
            'source_file': os.path.basename(ulg_path),
            'source_path': os.path.abspath(ulg_path),
            'analyzed_at': datetime.now().isoformat(),
            'pipeline': 'aerialist_energy_runner',
            'summary': convert_numpy(summary.to_dict()),
            'bugs': convert_numpy([b.to_dict() for b in bugs]),
            'bug_count': len(bugs),
            'bug_summary': convert_numpy(analyzer.get_bug_summary()),
            'outputs': {
                'energy_profile_plot': plot_path,
                'bug_timeline_plot': timeline_path if bugs else None,
            }
        }

        report_path = os.path.join(output_dir, f"{base_name}_report.json")
        with open(report_path, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n  Report saved: {report_path}")

        # Print verdict
        if len(bugs) == 0:
            print("VERDICT: No energy bugs detected")
        else:
            high_count = sum(1 for b in bugs if b.severity in ('high', 'critical'))
            if high_count > 0:
                print(f"VERDICT: {len(bugs)} bugs detected ({high_count} HIGH/CRITICAL)")
            else:
                print(f"VERDICT: {len(bugs)} bugs detected (low/medium severity)")

        return result

    except Exception as e:
        print(f"\n[ERROR] Energy analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'source_file': os.path.basename(ulg_path)}


def run_full_pipeline(test_yaml: str, output_dir: str = None) -> Dict:
    """
    Run complete two-stage pipeline:
    Stage 1: aerialist exec → .ulg
    Stage 2: energy analysis → bugs + plots + report

    Args:
        test_yaml: Path to test YAML
        output_dir: Output directory for energy results

    Returns:
        Combined result dictionary
    """
    print(f"# Energy-Aware UAV Test Pipeline")
    print(f"# Test: {test_yaml}")
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = time.time()

    # Stage 1: Execute test
    ulg_path = run_aerialist_test(test_yaml)

    if not ulg_path:
        print("\n[FAILED] Stage 1 failed - no .ulg file generated")
        return {'error': 'No .ulg file generated', 'test_yaml': test_yaml}

    # Stage 2: Energy analysis
    result = run_energy_analysis(ulg_path, output_dir)

    elapsed = time.time() - start_time
    print(f"\nTotal pipeline time: {elapsed:.1f}s")

    result['pipeline_duration_sec'] = round(elapsed, 2)
    result['test_yaml'] = test_yaml
    return result


def analyze_directory(log_dir: str, output_dir: str = None) -> List[Dict]:
    """
    Analyze all .ulg files in a directory.

    Args:
        log_dir: Directory containing .ulg files
        output_dir: Output directory for results
    """
    ulg_files = find_all_ulg(log_dir)

    if not ulg_files:
        print(f"No .ulg files found in {log_dir}")
        return []

    print(f"# Batch Energy Analysis - {len(ulg_files)} files")
    print(f"# Source: {log_dir}")

    results = []
    for ulg_path in ulg_files:
        result = run_energy_analysis(ulg_path, output_dir)
        results.append(result)

    # Print summary table
    print(f"\n{'='*60}")
    print("BATCH SUMMARY")
    print(f"{'='*60}")
    print(f"{'File':<35} {'Duration':<10} {'Battery':<10} {'Bugs':<6}")
    print('-' * 60)

    total_bugs = 0
    for r in results:
        if 'error' in r:
            print(f"{r.get('source_file', '?'):<35} {'ERROR':<10}")
        else:
            s = r['summary']
            print(f"{r['source_file']:<35} {s['flight_duration_sec']:>7.1f}s "
                  f"{s['battery_consumed_pct']:>7.1f}% {r['bug_count']:>4}")
            total_bugs += r['bug_count']

    print(f"\nTotal bugs across all flights: {total_bugs}")
    return results


def watch_mode(watch_dir: str = None, output_dir: str = None, interval: int = 5):
    """
    Watch for new .ulg files and analyze them automatically.
    Useful when running multiple aerialist tests in sequence.

    Args:
        watch_dir: Directory to watch (default: results/logs/)
        output_dir: Output directory for results
        interval: Check interval in seconds
    """
    watch_dir = watch_dir or RESULTS_DIR
    print(f"# Watch Mode - Monitoring for new .ulg files")
    print(f"# Directory: {watch_dir}")
    print(f"# Press Ctrl+C to stop")

    analyzed_files = set()

    # Mark existing files as already analyzed
    for f in find_all_ulg(watch_dir):
        analyzed_files.add(f)
    print(f"Found {len(analyzed_files)} existing .ulg files (skipping)")

    try:
        while True:
            current_files = set(find_all_ulg(watch_dir))
            new_files = current_files - analyzed_files

            for ulg_path in new_files:
                print(f"\n[NEW] Detected: {ulg_path}")

                # Wait a moment for file to finish writing
                time.sleep(2)

                run_energy_analysis(ulg_path, output_dir)
                analyzed_files.add(ulg_path)

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\nWatch mode stopped. Analyzed {len(analyzed_files)} files total.")


def main():
    parser = argparse.ArgumentParser(
        description='Energy-Aware UAV Test Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Two-Stage Pipeline:
  Stage 1: aerialist exec → generates .ulg flight log
  Stage 2: energy analysis → detects bugs, generates plots + reports

Examples:
  # Full pipeline: run test + analyze
  python3 aerialist_energy_runner.py --test mission.yaml

  # Analyze latest .ulg in results/
  python3 aerialist_energy_runner.py --analyze-latest

  # Analyze all .ulg in a directory
  python3 aerialist_energy_runner.py --analyze-dir results/logs/

  # Analyze a specific .ulg file
  python3 aerialist_energy_runner.py --analyze path/to/flight.ulg

  # Watch for new .ulg files (useful during batch testing)
  python3 aerialist_energy_runner.py --watch
        """
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--test', '-t',
                      help='Run full pipeline: execute test YAML + energy analysis')
    mode.add_argument('--analyze', '-a',
                      help='Post-hoc: analyze a specific .ulg file')
    mode.add_argument('--analyze-latest', action='store_true',
                      help='Post-hoc: analyze the most recent .ulg file')
    mode.add_argument('--analyze-dir', '-d',
                      help='Post-hoc: analyze all .ulg files in directory')
    mode.add_argument('--watch', '-w', action='store_true',
                      help='Watch mode: monitor for new .ulg files')

    parser.add_argument('--output', '-o', default=ENERGY_RESULTS_DIR,
                        help=f'Output directory for results (default: {ENERGY_RESULTS_DIR})')
    parser.add_argument('--results-dir', default=RESULTS_DIR,
                        help=f'Aerialist results directory (default: {RESULTS_DIR})')

    args = parser.parse_args()

    # Override defaults
    results_dir = args.results_dir
    energy_results_dir = args.output

    if args.test:
        run_full_pipeline(args.test, energy_results_dir)

    elif args.analyze:
        if not os.path.exists(args.analyze):
            print(f"File not found: {args.analyze}")
            sys.exit(1)
        run_energy_analysis(args.analyze, energy_results_dir)

    elif args.analyze_latest:
        latest = find_latest_ulg(results_dir)
        if latest:
            print(f"Latest .ulg: {latest}")
            run_energy_analysis(latest, energy_results_dir)
        else:
            # Also check case_studies
            case_dir = "UAV-Testing-Competition/snippets/case_studies"
            latest = find_latest_ulg(case_dir)
            if latest:
                print(f"Latest .ulg (case_studies): {latest}")
                run_energy_analysis(latest, energy_results_dir)
            else:
                print(f"No .ulg files found in {results_dir} or {case_dir}")
                sys.exit(1)

    elif args.analyze_dir:
        if not os.path.isdir(args.analyze_dir):
            print(f"Directory not found: {args.analyze_dir}")
            sys.exit(1)
        analyze_directory(args.analyze_dir, energy_results_dir)

    elif args.watch:
        watch_mode(results_dir, energy_results_dir)


if __name__ == "__main__":
    main()
