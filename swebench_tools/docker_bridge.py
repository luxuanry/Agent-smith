"""
Shared infrastructure for the SWE-bench MCP tools (swebench_tools/*).

Every tool in fs_tools.py / search_tools.py / exec_tools.py needs two
things: which container to `docker exec` into, and which task it's serving
(eval_script, repo, instance_id, ...). This module resolves both and
provides docker_exec(), the single primitive every tool is built on top of,
plus the shared conventions the whole swebench_tools package follows:

  - Tools never raise. mcp_tools_swebench.py wraps every registered tool in
    never_raise() below, so any exception (a bug, a misconfigured
    container/task from get_container()/get_task(), ...) comes back to the
    LLM as "[error] <reason>" instead of crashing the MCP server.
  - Paths: a relative path is resolved against /testbed (see to_abs());
    whatever a tool outputs should use absolute paths.
  - Long output goes through truncate() before being returned -- except
    get_patch(), which must return the complete, unmodified diff (a
    truncated patch is a broken patch).

Settings (which container, which task) are resolved in this priority order:
  1. --container / --task-file command-line flags, if mcp_tools_swebench.py
     was launched with them directly. Only useful for manual testing.
  2. SWEBENCH_CONTAINER_NAME / SWEBENCH_TASK_FILE environment variables.
     This is the real path: agent_swebench/__main__.py sets these before
     spawning mcp_tools_swebench.py, and the sandbox CLI's own
     `--mcp-stdio "python mcp_tools_swebench.py"` invocation never passes
     any command-line flags at all.
  3. DEFAULT_CACHE_TASK_FILE (cache/swebench_task.json, moulinette's default
     dump path) plus a container name derived from that task's instance_id
     via common.docker_env.container_name() -- lets you test the tools in
     this package standalone against a container you started by hand,
     without running the full agent_swebench pipeline first.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import posixpath
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from common.docker_env import container_name as _derive_container_name

TASK_FILE_ENV = "SWEBENCH_TASK_FILE"
CONTAINER_NAME_ENV = "SWEBENCH_CONTAINER_NAME"

REPO_DIR = "/testbed"  # SWE-bench images always check the repo out here
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_CACHE_TASK_FILE = "cache/swebench_task.json"  # moulinette's default dump path

# truncate() thresholds, in characters (not lines -- a single line, e.g. a
# stack trace, can be huge on its own). Keep a chunk from the start (what
# command produced this) and a chunk from the end (errors are usually near
# the bottom); only cut the middle out.
TRUNCATE_MAX_CHARS = 20_000
TRUNCATE_HEAD_CHARS = 10_000
TRUNCATE_TAIL_CHARS = 5_000


@dataclass
class ExecResult:
    """Result of a docker_exec() call. Deliberately never raised as an
    exception on failure: a nonzero exit code or a timeout is a normal
    outcome the LLM needs to see, not a bug in our own code."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def never_raise(fn: Callable[..., str]) -> Callable[..., str]:
    """Tool-registration wrapper: catches anything fn raises and turns it
    into a "[error] <type>: <message>" string instead of letting the
    exception reach the MCP protocol layer. Every tool registered in
    mcp_tools_swebench.py goes through this, so no individual tool
    implementation has to remember to add its own top-level try/except for
    infrastructure failures (e.g. get_container()/get_task() raising on a
    missing task file). A tool can still return its own more specific
    "[error] ..." string for a domain-specific failure (edit_file's old_str
    not found, say) -- this wrapper is only the last-resort safety net."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return f"[error] {type(e).__name__}: {e}"

    return wrapper


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--container", default=None)
    parser.add_argument("--task-file", default=None)
    # parse_known_args, not parse_args: mcp_tools_swebench.py is normally
    # launched with no flags at all (see module docstring, tier 2), so any
    # unrecognized argv should be ignored rather than causing a crash.
    args, _unknown = parser.parse_known_args()
    return args


_CLI_ARGS = _parse_cli_args()


def get_task() -> dict:
    """Resolve the current task's JSON (docker_image / eval_script / repo /
    instance_id / ...)."""
    task_file = _CLI_ARGS.task_file or os.environ.get(TASK_FILE_ENV) or DEFAULT_CACHE_TASK_FILE
    if not os.path.exists(task_file):
        raise RuntimeError(
            f"Task file not found: {task_file!r}. mcp_tools_swebench.py is "
            f"normally started by agent_swebench/__main__.py, which sets "
            f"{TASK_FILE_ENV} before spawning it. For standalone testing, "
            f"either set that env var yourself, pass --task-file, or dump "
            f"a task to {DEFAULT_CACHE_TASK_FILE!r} (moulinette's default)."
        )
    with open(task_file, encoding="utf-8") as f:
        return json.load(f)


def get_container() -> str:
    """Resolve which container this process should `docker exec` into."""
    if _CLI_ARGS.container:
        return _CLI_ARGS.container
    container = os.environ.get(CONTAINER_NAME_ENV)
    if container:
        return container
    # Fallback: derive the name the same way agent_swebench/__main__.py
    # does, from whatever task get_task()'s own fallback resolves to. Only
    # works if you already started a container by hand under that exact
    # name (see common.docker_env.container_name / start_container).
    task = get_task()
    return _derive_container_name(task["instance_id"])


def to_abs(path: str) -> str:
    """Resolve a filepath the LLM gave us to an absolute path inside the
    container. A relative path is assumed to be relative to the repo
    checkout (REPO_DIR); an already-absolute path is returned unchanged.
    Uses posixpath explicitly (not pathlib) because the target path is
    always a Linux container path, regardless of what OS this bridge runs
    on."""
    if posixpath.isabs(path):
        return path
    return posixpath.join(REPO_DIR, path)


def truncate(text: str) -> str:
    """Cut long tool output down to a manageable size before it goes back
    to the LLM (V.1 feedback (4)). Keeps a head and a tail instead of just
    hard-cutting from the start -- the command that produced the output is
    usually at the top, the error is usually at the bottom -- and always
    says explicitly how much was cut. Do NOT call this on get_patch()'s
    output: a truncated diff is a broken patch, not a shortened one."""
    if len(text) <= TRUNCATE_MAX_CHARS:
        return text
    omitted = len(text) - TRUNCATE_HEAD_CHARS - TRUNCATE_TAIL_CHARS
    head = text[:TRUNCATE_HEAD_CHARS]
    tail = text[-TRUNCATE_TAIL_CHARS:] if TRUNCATE_TAIL_CHARS else ""
    return f"{head}\n[... {omitted} characters omitted ...]\n{tail}"


def docker_exec(
    command: str,
    workdir: str = REPO_DIR,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    input: Optional[str] = None,
) -> ExecResult:
    """Run `command` inside the current task's container via `docker exec`,
    optionally feeding it `input` on stdin. Never raises for a command
    failure: a timeout, a nonzero exit code, or anything docker itself
    prints to stderr all come back as a normal ExecResult for the caller to
    inspect -- only a genuine setup problem (no container configured at
    all, see get_container()) is still allowed to raise, and that gets
    caught by never_raise() at the tool-registration layer instead.

    Runs through `bash -lc` because each `docker exec` call is a brand new
    process -- it does NOT remember a previous call's
    `conda activate testbed`. If a tool needs that environment (running
    tests almost certainly does), prepend the activation to `command`
    yourself, e.g.:

        docker_exec(
            "source /opt/miniconda3/etc/profile.d/conda.sh && "
            "conda activate testbed && bin/test -C sympy/some/test.py"
        )

    `workdir` is passed straight to `docker exec -w`, a single argv item
    that never goes through a shell, so it needs no escaping here. Escaping
    only matters where a *tool* builds a piece of `command` itself out of
    LLM-supplied values (a filepath, a pattern, ...) -- use shlex.quote()
    there, e.g. `docker_exec(f"cat -n {shlex.quote(to_abs(filepath))}")` in
    read_file. `command` as a whole is never escaped or sanitized, on
    purpose: run_command's entire job is to let the LLM execute arbitrary
    shell.
    """
    container = get_container()
    full_cmd = ["docker", "exec", "-w", workdir, container, "bash", "-lc", command]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input,
        )
        return ExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as e:
        return ExecResult(
            returncode=-1,
            stdout=e.stdout or "",
            stderr=(e.stderr or "") + f"\n[docker_exec] timed out after {timeout}s",
            timed_out=True,
        )