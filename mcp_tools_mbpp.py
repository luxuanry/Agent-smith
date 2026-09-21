"""
MCP Server for MBPP tasks (Section V.3).

Design for run_tests():
  The MCP server is a separate process that doesn't share memory with the
  sandbox (where the LLM's code is actually exec()'d), so it can't directly
  "see" the function the LLM defined inside the sandbox. We bridge the two
  through a file:

    1. The LLM writes its candidate solution to a fixed path
       (e.g. /tmp/agent/solution.py) — this path is inside the sandbox's
       allowed_directories allowlist, so writing there is permitted.
    2. The LLM calls run_tests().
    3. run_tests() reads that file, exec()s it to get the function
       definition, then runs the task's REAL, official test_list against
       it (not whatever ad-hoc checks the LLM wrote itself), and returns
       a clear pass/fail report.

  The MCP server needs to know which task is currently being solved. Here
  that's done via an environment variable pointing to the task's JSON file
  (set by whoever launches this server), so the same mcp_tools_mbpp.py file
  works for any task without needing per-task code changes.
"""
import json
import os
import traceback

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mbpp-tools")

SOLUTION_FILE = "/tmp/agent/solution.py"
TASK_FILE_ENV = "MBPP_TASK_FILE"  # set by whoever launches this server


def _load_current_task() -> dict:
    """Read the current task's JSON (to get test_imports/test_list)."""
    task_file = os.environ.get(TASK_FILE_ENV)
    if not task_file or not os.path.exists(task_file):
        raise RuntimeError(
            f"Could not find the task file (checked env var "
            f"{TASK_FILE_ENV}={task_file!r} — make sure it's set correctly)."
        )
    with open(task_file) as f:
        return json.load(f)


@mcp.tool()
def run_tests() -> str:
    """Run the official test suite against the solution currently written
    to /tmp/agent/solution.py, and report pass/fail per test.
    """
    if not os.path.exists(SOLUTION_FILE):
        return (
            f"[run_tests] No solution file found at {SOLUTION_FILE}. "
            f"Write your solution there first, e.g.:\n"
            f'  with open("{SOLUTION_FILE}", "w") as f:\n'
            f'      f.write(your_solution_code)'
        )

    task = _load_current_task()
    test_imports = task.get("test_imports", [])
    test_list = task.get("test_list", [])

    with open(SOLUTION_FILE) as f:
        solution_code = f.read()

    # Fresh namespace on every run, so state from a previous run can't leak in
    namespace: dict = {}

    try:
        for imp in test_imports:
            exec(imp, namespace)
        exec(solution_code, namespace)
    except Exception:
        return "[run_tests] Failed to load the solution:\n" + traceback.format_exc(limit=-1)

    results = []
    passed = 0
    for i, test_line in enumerate(test_list, start=1):
        try:
            exec(test_line, namespace)
            results.append(f"  test {i}: PASS  ({test_line})")
            passed += 1
        except AssertionError:
            results.append(f"  test {i}: FAIL  ({test_line})")
        except Exception as e:
            results.append(f"  test {i}: ERROR ({test_line}) -> {type(e).__name__}: {e}")

    summary = f"[run_tests] {passed}/{len(test_list)} tests passed"
    return summary + "\n" + "\n".join(results)


if __name__ == "__main__":
    mcp.run()