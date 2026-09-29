"""Execution tools: run_tests / get_patch / run_command (Section V.5.3)."""
import base64
import re

from swebench_tools.docker_bridge import clean_stderr, docker_exec, get_task, to_abs, truncate

# The eval script reinstalls the package and runs a whole test suite, so it
# needs far more than docker_exec's default timeout.
RUN_TESTS_TIMEOUT_SECONDS = 300

# Written inside the container, deliberately outside the repo: a file under
# /testbed would show up in get_patch()'s diff and corrupt the answer.
EVAL_SCRIPT_PATH = "/tmp/agent_eval_script.sh"


def _summarize_test_output(stdout: str, stderr: str) -> str:
    """Turn a full eval-script log into something an LLM can read.

    The raw log runs to thousands of lines, most of it installation noise.
    The SWE-bench eval script brackets the part that matters with
    ">>>>> Start Test Output" / ">>>>> End Test Output", so that section is
    what gets summarized: how many tests passed and failed, and the names
    of the failing ones.

    stdout and stderr are kept apart on purpose. The scripts run under
    `set -x`, so the shell echoes the marker lines themselves to stderr;
    looking for the markers in a merged log finds those echoes and returns
    the trace instead of the test results, which are on stdout.
    """
    section = stdout
    start = stdout.find("Start Test Output")
    if start != -1:
        end = stdout.find("End Test Output", start)
        section = stdout[start:end if end != -1 else len(stdout)]

    # Counting depends on the test runner: pytest prints "PASSED test_x",
    # while sympy's own bin/test prints "45 passed, 1 failed" at the end.
    passed = len(re.findall(r"\bPASSED\b", section))
    failed = len(re.findall(r"\bFAILED\b", section))
    errors = len(re.findall(r"\bERROR\b", section))

    summary_lines = [
        line.strip()
        for line in section.splitlines()
        if re.search(r"\b\d+\s+(passed|failed|error)", line)
        or re.match(r"^=+.*\b(passed|failed|error)\b.*=+$", line.strip())
        or "tests finished" in line
    ]
    for line in summary_lines:
        for count, word in re.findall(r"\b(\d+)\s+(passed|failed|error)", line):
            if word == "passed":
                passed = max(passed, int(count))
            elif word == "failed":
                failed = max(failed, int(count))
            else:
                errors = max(errors, int(count))

    # pytest: "FAILED path::test_name"; sympy underlines the name instead.
    failing = re.findall(r"^(?:FAILED|ERROR)\s+(\S+)", section, flags=re.MULTILINE)
    failing += re.findall(
        r"^_{3,}\s+(\S*[A-Za-z0-9]\S*)\s+_{3,}$", section, flags=re.MULTILINE
    )

    lines = [f"[run_tests] {passed} passed, {failed} failed, {errors} errors"]
    lines.extend(dict.fromkeys(summary_lines))  # de-duplicated, order kept

    if failing:
        lines.append("Failing tests:")
        lines.extend(f"  {name}" for name in dict.fromkeys(failing[:20]))
        if len(failing) > 20:
            lines.append(f"  ... and {len(failing) - 20} more")

    # Keep the tail of the log, so a failure that happened before any test
    # ran (an import error, a patch that would not apply) is still visible.
    # In that case fall back to stderr, where the traceback usually is.
    if passed or failed or errors:
        tail_source = section
    else:
        tail_source = (stdout + "\n" + clean_stderr(stderr)).strip()
    lines.append("--- end of test output ---")
    lines.append("\n".join(tail_source.strip().splitlines()[-25:]))
    return truncate("\n".join(lines))


def run_tests() -> str:
    """Execute the evaluation script (eval_script from SWEBenchTaskInput).

    The script is base64-encoded here and decoded inside the container
    instead of being interpolated into the command line: it is a whole
    multi-line bash script containing quotes, heredocs and patch text, none
    of which survives being pasted into another shell command intact.

    It is written to /tmp, never into the repository, because any file
    under /testbed would appear in get_patch()'s diff.

    Returns a summary (pass/fail counts, failing test names, the tail of
    the log), not the full log, which is thousands of lines long.
    """
    task = get_task()
    eval_script = task.get("eval_script", "")
    if not eval_script.strip():
        return "[run_tests] the task file has no eval_script"

    encoded = base64.b64encode(eval_script.encode()).decode()
    result = docker_exec(
        f"echo {encoded} | base64 -d > {EVAL_SCRIPT_PATH} && bash {EVAL_SCRIPT_PATH}",
        timeout=RUN_TESTS_TIMEOUT_SECONDS,
    )
    if result.timed_out:
        return f"[run_tests] timed out after {RUN_TESTS_TIMEOUT_SECONDS}s"
    return _summarize_test_output(result.stdout, result.stderr)


def get_patch() -> str:
    """Return `git -c core.fileMode=false diff` from the repo.

    This is the agent's actual answer (final_answer() submits it), so the
    output is returned exactly as git produced it and is never truncated:
    a cut-off diff cannot be applied.

    `core.fileMode=false` keeps permission-only changes out of the diff,
    as the project requires.
    """
    result = docker_exec("git -c core.fileMode=false diff")
    if result.timed_out:
        return "[get_patch] timed out"
    if result.returncode != 0:
        return f"[get_patch] failed: {truncate(clean_stderr(result.stderr))}"
    return result.stdout if result.stdout.strip() else "(no changes in the repository yet)"


def run_command(command: str, workdir: str) -> str:
    """Run a shell command in the container and report what happened.

    Both streams are reported separately, along with the exit code, since
    a command can fail while still printing something useful.
    """
    result = docker_exec(command, workdir=to_abs(workdir or "."))
    if result.timed_out:
        return f"exit_code: -1\n[run_command] timed out\n{truncate(result.stderr)}"

    return "\n".join(
        [
            f"exit_code: {result.returncode}",
            "stdout:\n" + (truncate(result.stdout.rstrip()) or "(empty)"),
            "stderr:\n" + (truncate(clean_stderr(result.stderr)) or "(empty)"),
        ]
    )
