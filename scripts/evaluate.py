"""
evaluate.py - Run the full test suite and report real metrics.
This script calls pytest programmatically and parses the results.
It does NOT hard-code any percentages — all numbers come from actual test runs.

Usage:
  python scripts/evaluate.py (from proofloop/ directory)
  python ..\\scripts\\evaluate.py (from proofloop/backend/ directory)
"""
import sys
import os
import json
import subprocess
from datetime import datetime, timezone

# Ensure stdout handles UTF-8 on Windows
if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
BACKEND_DIR = os.path.join(PROJECT_DIR, "backend")

# Always run pytest from the backend directory where pytest.ini and tests/ live
TARGET_CWD = BACKEND_DIR if os.path.exists(BACKEND_DIR) else PROJECT_DIR
REPORT_PATH = os.path.join(TARGET_CWD, "test_results.json")


def run_tests() -> dict:
    """Run pytest with JSON output and parse real results."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/",
            "-v",
            "--tb=short",
            "--json-report",
            f"--json-report-file={REPORT_PATH}",
        ],
        capture_output=True,
        text=True,
        cwd=TARGET_CWD,
    )
    return {
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def parse_results() -> dict:
    """Parse the pytest JSON report if available."""
    if not os.path.exists(REPORT_PATH):
        return {"error": "test_results.json not found"}

    try:
        with open(REPORT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"Failed to load test report: {e}"}

    summary = data.get("summary", {})
    tests = data.get("tests", [])

    categories = {
        "finance_api": [],
        "tools": [],
        "agent": [],
    }
    for t in tests:
        name = t["nodeid"]
        if "finance_api" in name:
            categories["finance_api"].append(t)
        elif "tools" in name:
            categories["tools"].append(t)
        elif "agent" in name:
            categories["agent"].append(t)

    def summarize(tests_list):
        passed = sum(1 for t in tests_list if t.get("outcome") == "passed")
        failed = sum(1 for t in tests_list if t.get("outcome") == "failed")
        return {"passed": passed, "failed": failed, "total": len(tests_list)}

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": summary,
        "by_module": {k: summarize(v) for k, v in categories.items()},
        "failed_tests": [
            {"name": t["nodeid"], "message": str(t.get("call", {}).get("longrepr", ""))[:200]}
            for t in tests if t.get("outcome") == "failed"
        ],
    }


def print_report(output: dict, parsed: dict):
    print("\n" + "=" * 60)
    print("  ProofLoop Evaluation Report")
    print(f"  Generated: {parsed.get('timestamp', 'unknown')}")
    print("=" * 60)

    overall = parsed.get("overall", {})
    total = overall.get("total", 0)
    passed = overall.get("passed", 0)
    failed = overall.get("failed", 0)

    print(f"\nOverall Results: {passed}/{total} tests passed")
    if total > 0:
        pct = 100 * passed / total
        print(f"   Pass rate: {pct:.1f}%")

    print("\nResults by Module:")
    for module, stats in parsed.get("by_module", {}).items():
        tag = "[PASS]" if stats["failed"] == 0 else "[FAIL]"
        print(f"   {tag} {module}: {stats['passed']}/{stats['total']} passed")

    if parsed.get("failed_tests"):
        print("\nFailed Tests:")
        for ft in parsed["failed_tests"]:
            print(f"   - {ft['name']}")
            if ft["message"]:
                print(f"     {ft['message'][:100]}")

    print("\n" + "=" * 60)

    exit_code = 0 if (failed == 0 and total > 0) else 1
    print(f"\n{'[SUCCESS] All tests passed successfully!' if exit_code == 0 else '[FAILURE] Some tests failed'}")
    
    # Clean up test_results.json so no stray files linger
    if os.path.exists(REPORT_PATH):
        try:
            os.remove(REPORT_PATH)
        except Exception:
            pass

    return exit_code


if __name__ == "__main__":
    print("Running ProofLoop test suite...")
    output = run_tests()
    parsed = parse_results()
    exit_code = print_report(output, parsed)
    sys.exit(exit_code)
