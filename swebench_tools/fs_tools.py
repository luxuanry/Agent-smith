"""File system tools: read_file / edit_file / list_files (Section V.5.1)."""
import shlex

from swebench_tools.docker_bridge import docker_exec, to_abs, truncate


def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read file content with line numbers, like `cat -n`.

    Implementation approach:
        docker_exec(f"cat -n {shlex.quote(to_abs(filepath))} | sed -n '{start_line},{end_line}p'")
    filepath can be relative or absolute -- to_abs() normalizes it to an
    absolute path inside the container either way.
    """
    raise NotImplementedError("TODO: read_file")


def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string.

    Implementation approach: run filepath through to_abs() first. old_str
    must match exactly once in the file -- report an error to the LLM
    whether it's not found or matches more than once (never guess which
    occurrence to replace, that's how you edit the wrong spot). Doing the
    replacement via a small Python script (run in the container through
    docker_exec's python -c "...") gives better control over the
    "must match exactly once" rule than sed/grep, and sidesteps escaping
    old_str/new_str's special characters.
    """
    raise NotImplementedError("TODO: edit_file")


def list_files(directory: str, pattern: str) -> str:
    """List files in a directory matching a pattern.

    Implementation approach: docker_exec(f"find {shlex.quote(to_abs(directory))} -name {shlex.quote(pattern)}")
    Output can get long (a big directory + a broad pattern) -- remember to
    wrap it with truncate().
    """
    raise NotImplementedError("TODO: list_files")