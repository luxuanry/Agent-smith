"""Execution tools: run_tests / get_patch / run_command (Section V.5.3)."""
from swebench_tools.docker_bridge import docker_exec, get_task, to_abs, truncate


def run_tests() -> str:
    """Execute the evaluation script (eval_script from SWEBenchTaskInput).

    Implementation approach:
        task = get_task()
        eval_script = task["eval_script"]
    Run this script via docker_exec. eval_script already handles
    checking out/reverting test files and installing the official gold
    test patch -- just run the whole thing as-is, no need to assemble your
    own test command. The test log can get long; run it through
    truncate() before returning.
    """
    raise NotImplementedError("TODO: run_tests")


def get_patch() -> str:
    """Return `git -c core.fileMode=false diff` from the repo.

    Implementation approach: docker_exec("git -c core.fileMode=false diff"),
    return stdout as-is -- this is the diff the agent submits via
    final_answer(). Note: do NOT call truncate() here, a truncated diff
    can't be applied as a patch.
    """
    raise NotImplementedError("TODO: get_patch")


def run_command(command: str, workdir: str) -> str:
    """Run a shell command, return stdout/stderr/exit code.

    Implementation approach: run workdir through to_abs() first, then
    forward directly to docker_exec(command, workdir=to_abs(workdir)), and
    format returncode/stdout/stderr into a string (follow the exact format
    the PDF requires; remember to run the output through truncate()).
    """
    raise NotImplementedError("TODO: run_command")