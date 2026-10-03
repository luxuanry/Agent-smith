"""
Turn benchmark runs into the tables BENCHMARK_REPORT.md needs (PDF V.7).

Expected layout (commit it: the PDF requires the backing solution.json files):
    benchmark/runs/<run_name>/<instance_id>/solution.json
    benchmark/runs/<run_name>/<instance_id>/validate.txt   # moulinette validate output

Usage:
    python benchmark/aggregate.py benchmark/runs > benchmark/tables.md
"""
import json
import re
import statistics
import sys
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
# "Tests pass" across runners: unittest/Django "OK", pytest/sympy "N passed" (N > 0) ...
PASS_RE = re.compile(r"^OK\b|\b[1-9]\d* passed\b", re.M)
# ... and no sign of a failure in the same output.
FAIL_RE = re.compile(r"\b[1-9]\d* (?:failed|errors?)\b|^FAILED \(|^FAIL:|\[FAIL\]", re.M)


def verdict(run_dir: Path) -> str:
    """PASS/FAIL from moulinette's own "Overall:" line -- not from
    solution.json's `success`, which only means final_answer() was called."""
    f = run_dir / "validate.txt"
    if not f.exists():
        return "?"
    text = ANSI.sub("", f.read_text(errors="replace"))
    m = re.search(r"^Overall:\s*(PASSED|FAILED)", text, re.M)
    return "?" if not m else ("PASS" if m.group(1) == "PASSED" else "FAIL")


def patch_files(patch: str) -> list:
    return re.findall(r"^diff --git a/(\S+) b/", patch or "", re.M)


def first_touch_step(steps: list, files: list):
    """Exploration efficiency: first step whose code names a file that ends up in the final patch."""
    for s in steps:
        if any(f in s.get("sandbox_input", "") for f in files):
            return s["step"]
    return None


def tests_pass_step(steps: list):
    """First step where run_tests() reported passing tests and no failures."""
    for s in steps:
        if "run_tests(" in s.get("sandbox_input", ""):
            out = s.get("sandbox_output", "")
            if PASS_RE.search(out) and not FAIL_RE.search(out):
                return s["step"]
    return None


def fmt(value):
    return "-" if value is None else value


def main(root: str) -> None:
    rows, per_run = [], {}
    for sol_file in sorted(Path(root).glob("*/*/solution.json")):
        run_dir = sol_file.parent
        run_name = run_dir.parent.name
        sol = json.loads(sol_file.read_text())
        steps = sol.get("steps", [])
        files = patch_files(sol.get("solution", ""))
        passed_at = tests_pass_step(steps)
        last = steps[-1]["step"] if steps else None
        rows.append({
            "run": run_name,
            "model": steps[0]["model_name"] if steps else "?",
            "task": sol["task_id"],
            "verdict": verdict(run_dir),
            "iterations": sol["iterations"],
            "in": sol["total_input_tokens"],
            "out": sol["total_output_tokens"],
            "time": round(sol["total_time_seconds"], 1),
            "first_touch": first_touch_step(steps, files) if files else None,
            "tests_pass": passed_at,
            # Steps spent after tests first passed, before submitting (0 is ideal).
            "extra": max(0, last - passed_at - 1) if sol.get("success") and passed_at else None,
            "error": sol.get("error") or "",
        })
        r = per_run.setdefault(run_name, {"times": [], "retries": 0, "requests": 0,
                                          "runs": 0, "provider_fail": 0, "url": ""})
        r["runs"] += 1
        r["times"] += [s["request_time_ms"] for s in steps]
        r["retries"] += sum(s.get("retries", 0) for s in steps)
        r["requests"] += sol.get("total_requests", 0)
        r["url"] = r["url"] or (steps[0].get("api_url", "") if steps else "")
        if "LLM request failed" in (sol.get("error") or ""):
            r["provider_fail"] += 1

    print("## Results\n")
    print("| Run | Model | Task | Pass/Fail | Iterations | Input tokens | Output tokens | Wall-clock (s) |")
    print("|---|---|---|---|---|---|---|---|")
    for x in rows:
        print(f"| {x['run']} | {x['model']} | {x['task']} | {x['verdict']} | {x['iterations']} "
              f"| {x['in']} | {x['out']} | {x['time']} |")

    print("\n## Provider reliability\n")
    print("| Run | API | Avg response (ms) | Requests | Retries | Runs without provider failure |")
    print("|---|---|---|---|---|---|")
    for name, r in per_run.items():
        avg = round(statistics.mean(r["times"])) if r["times"] else "-"
        print(f"| {name} | {r['url']} | {avg} | {r['requests']} | {r['retries']} "
              f"| {r['runs'] - r['provider_fail']}/{r['runs']} |")

    print("\n## Intermediary metrics\n")
    print("| Run | Task | First step touching a patched file | First step tests pass | Extra steps before final_answer |")
    print("|---|---|---|---|---|")
    for x in rows:
        print(f"| {x['run']} | {x['task']} | {fmt(x['first_touch'])} | {fmt(x['tests_pass'])} | {fmt(x['extra'])} |")

    errors = [x for x in rows if x["error"]]
    if errors:
        print("\n## Errors\n")
        for x in errors:
            print(f"- {x['run']} / {x['task']}: {x['error'][:150]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "benchmark/runs")
