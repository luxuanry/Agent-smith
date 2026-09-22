"""
MBPP MCP tools server (Section V.3, point 2).

Exposes one tool, run_tests(code), which checks a candidate solution
against the current task's tests.

The task file path comes from the MBPP_TASK_FILE environment variable
(set by agent_mbpp/__main__.py before this server is launched).
"""
import json
import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mbpp-tools")

TASK_FILE_ENV = "MBPP_TASK_FILE"
TEST_TIMEOUT_SECONDS = 10

# Small script that runs each test separately and prints PASS/FAIL per test.
# It is executed in a separate Python process, never inside this server,
# so broken or malicious code cannot crash or take over the MCP server.
_HARNESS = '''
import json as _json
_tests = _json.loads({tests_json!r})
_passed = 0
for _i, _t in enumerate(_tests, start=1):
    try:
        exec(_t, globals())
        print(f"  test {{_i}}: PASS  ({{_t}})")
        _passed += 1
    except AssertionError:
        print(f"  test {{_i}}: FAIL  ({{_t}})")
    except Exception as _e:
        print(f"  test {{_i}}: ERROR ({{_t}}) -> {{type(_e).__name__}}: {{_e}}")
print(f"[run_tests] {{_passed}}/{{len(_tests)}} tests passed")
'''


def _load_current_task() -> dict:
    task_file = os.environ.get(TASK_FILE_ENV)
    if not task_file or not os.path.exists(task_file):
        raise RuntimeError(
            f"Could not find the task file (env var {TASK_FILE_ENV}={task_file!r})."
        )
    with open(task_file, encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def run_tests(code: str) -> str:
    """Run the task's tests against the given solution code.

    Pass the full source code of your solution as `code`, for example:
        print(run_tests(code=solution))
    Returns a pass/fail line per test and a summary.
    """
    task = _load_current_task()
    test_imports = task.get("test_imports", [])
    test_list = task.get("test_list", [])

    script = "\n".join(test_imports) + "\n" + code + "\n" + _HARNESS.format(
        tests_json=json.dumps(test_list)
    )

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"[run_tests] Timed out after {TEST_TIMEOUT_SECONDS}s (infinite loop?)"

    if "[run_tests]" not in proc.stdout:
        # The solution itself failed before any test could run (e.g. SyntaxError).
        return "[run_tests] Failed to load the solution:\n" + proc.stderr.strip()
    return proc.stdout.strip()


if __name__ == "__main__":
    mcp.run()