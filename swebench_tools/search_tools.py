"""Code search tools: search_code / search_function_or_class_definition_in_code /
find_references (Section V.5.2)."""
import shlex

from swebench_tools.docker_bridge import docker_exec, truncate


def search_code(pattern: str, file_pattern: str) -> str:
    """Grep-like search. Output format:
    /absolute/path/to/file.py:<line_number> <line_content>

    Implementation approach: docker_exec(f"grep -rn --include={shlex.quote(file_pattern)} {shlex.quote(pattern)} .")
    then reformat each line into the exact format required above. Remember
    to run the output through truncate() -- a broad pattern can easily
    match hundreds of lines.
    """
    raise NotImplementedError("TODO: search_code")


def search_function_or_class_definition_in_code(name: str) -> str:
    """Find the definition of a function or class.

    Implementation approach: a simple version can grep for patterns like
    `^def {name}` / `^class {name}`; for more accuracy, consider running a
    small script in the container that parses with Python's ast module.
    """
    raise NotImplementedError("TODO: search_function_or_class_definition_in_code")


def find_references(name: str, filepath: str, line: int) -> str:
    """Find all usages of a symbol.

    Implementation approach: the simplest version can just do a global
    grep -rn for every place `name` appears (use the filepath/line
    arguments to exclude the definition itself).
    """
    raise NotImplementedError("TODO: find_references")