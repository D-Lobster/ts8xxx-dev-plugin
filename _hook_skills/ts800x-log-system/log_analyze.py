"""Log analysis tool for TS800X firmware verification.

Usage:
    python log_analyze.py --log capture.log --output report.json
    python log_analyze.py --log capture.log --expect "init done,KEY pressed"
"""
import argparse
import json
import re
import sys
import os
from datetime import datetime


# Known log patterns for TS800X
PATTERNS = {
    "boot": {
        "regex": r"(?:Startup|init done|System Initialization)",
        "description": "Device boot sequence",
        "severity": "info"
    },
    "ble_init": {
        "regex": r"(?:Ble init|Ble initializing|Ble adv)",
        "description": "BLE initialization",
        "severity": "info"
    },
    "ble_connect": {
        "regex": r"(?:connected|disconnect)",
        "description": "BLE connection events",
        "severity": "info"
    },
    "key_event": {
        "regex": r"(?:KEY\d|press|long press|triple)",
        "description": "Key events",
        "severity": "info"
    },
    "filter_state": {
        "regex": r"(?:FILTERING|RED|GREEN|DONE|STANDBY|SCREEN_OFF)",
        "description": "Filter state transitions",
        "severity": "info"
    },
    "sleep": {
        "regex": r"(?:sleep|deep sleep|wakeup|wake)",
        "description": "Sleep/wake events",
        "severity": "info"
    },
    "error": {
        "regex": r"\b(?:ERROR|FAIL(?:ED)?|NG|exception|fault)\b",
        "description": "Error conditions",
        "severity": "error"
    },
    "warning": {
        "regex": r"\b(?:WARN(?:ING)?|warning)\b",
        "description": "Warnings",
        "severity": "warning"
    },
    "rtc_timer": {
        "regex": r"(?:Filter:|RTC:|timer)",
        "description": "RTC timer events",
        "severity": "info"
    }
}


def analyze_log(log_path, expect_patterns=None, allow_warnings=False):
    """Analyze log file and return structured results."""
    results = {
        "file": log_path,
        "timestamp": datetime.now().isoformat(),
        "total_lines": 0,
        "pattern_matches": {},
        "errors": [],
        "warnings": [],
        "expect_results": [],
        "summary": "",
        "success": False,
    }

    if not os.path.exists(log_path):
        results["summary"] = f"Log file not found: {log_path}"
        return results

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as exc:
        results["summary"] = f"FAILED: cannot read log: {exc}"
        return results

    results["total_lines"] = len(lines)

    # Count pattern matches
    for name, pattern in PATTERNS.items():
        regex = re.compile(pattern["regex"], re.IGNORECASE)
        matches = []
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append({"line": i, "text": line.strip()})
        results["pattern_matches"][name] = {
            "count": len(matches),
            "description": pattern["description"],
            "severity": pattern["severity"],
            "samples": matches[:5]  # Keep first 5 matches as samples
        }

    # Keep bounded samples while preserving full counts in pattern_matches.
    for match in results["pattern_matches"].get("error", {}).get("samples", []):
        results["errors"].append(match)
    for match in results["pattern_matches"].get("warning", {}).get("samples", []):
        results["warnings"].append(match)

    # Check expect patterns
    if expect_patterns:
        for pattern_str in expect_patterns:
            try:
                regex = re.compile(pattern_str, re.IGNORECASE)
                found = False
                for i, line in enumerate(lines, 1):
                    if regex.search(line):
                        results["expect_results"].append({
                            "pattern": pattern_str,
                            "found": True,
                            "line": i,
                            "text": line.strip()
                        })
                        found = True
                        break
                if not found:
                    results["expect_results"].append({
                        "pattern": pattern_str,
                        "found": False,
                        "line": None,
                        "text": None
                    })
            except re.error:
                results["expect_results"].append({
                    "pattern": pattern_str,
                    "found": False,
                    "error": "Invalid regex"
                })

    # Generate summary
    error_count = results["pattern_matches"].get("error", {}).get("count", 0)
    warning_count = results["pattern_matches"].get("warning", {}).get("count", 0)
    expect_passed = sum(1 for r in results["expect_results"] if r.get("found"))
    expect_total = len(results["expect_results"])

    if results["total_lines"] == 0:
        results["summary"] = "FAILED: log is empty"
    elif error_count > 0:
        results["summary"] = f"FAILED: {error_count} errors, {warning_count} warnings"
    elif warning_count > 0 and not allow_warnings:
        results["summary"] = f"FAILED: {warning_count} runtime warnings"
    elif expect_total > 0 and expect_passed < expect_total:
        results["summary"] = f"PARTIAL: {expect_passed}/{expect_total} expected patterns found"
    else:
        results["summary"] = f"PASSED: {results['total_lines']} lines, {error_count} errors"
        results["success"] = True

    return results


def main():
    parser = argparse.ArgumentParser(description="TS800X log analysis")
    parser.add_argument("--log", required=True, help="Log file path")
    parser.add_argument("--output", default=None, help="Output JSON report path")
    parser.add_argument("--expect", type=str, default=None,
                        help="Comma-separated regex patterns to verify")
    parser.add_argument("--allow-warnings", action="store_true",
                        help="Do not fail solely because WARN lines are present")
    args = parser.parse_args()

    expect_patterns = None
    if args.expect:
        expect_patterns = [p.strip() for p in args.expect.split(",") if p.strip()]

    results = analyze_log(args.log, expect_patterns, args.allow_warnings)

    # Print summary
    print(f"[INFO] Log: {args.log}")
    print(f"[INFO] Lines: {results['total_lines']}")
    print(f"[INFO] {results['summary']}")

    # Print pattern matches
    print("\n--- Pattern Matches ---")
    for name, data in results["pattern_matches"].items():
        if data["count"] > 0:
            print(f"  {name}: {data['count']} ({data['description']})")

    # Print expect results
    if results["expect_results"]:
        print("\n--- Expected Patterns ---")
        for r in results["expect_results"]:
            status = "FOUND" if r.get("found") else "MISSING"
            print(f"  [{status}] {r['pattern']}")
            if r.get("text"):
                print(f"         Line {r['line']}: {r['text'][:80]}")

    # Print errors/warnings
    if results["errors"]:
        print(f"\n--- Errors ({len(results['errors'])}) ---")
        for e in results["errors"][:5]:
            print(f"  Line {e['line']}: {e['text'][:100]}")

    if results["warnings"]:
        print(f"\n--- Warnings ({len(results['warnings'])}) ---")
        for w in results["warnings"][:5]:
            print(f"  Line {w['line']}: {w['text'][:100]}")

    # Save JSON report
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[INFO] Report saved: {args.output}")

    # Exit code
    if not results.get("success"):
        sys.exit(1)
    elif results["expect_results"] and not all(r.get("found") for r in results["expect_results"]):
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
