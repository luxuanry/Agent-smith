"""
MCP server entry point for SWE-bench tasks (Section V.4 + V.5).

Must live at the repository root (the PDF requires this). This file's only
job is to register the 9 mandatory tools and start the server -- the actual
implementations live in swebench_tools/{fs_tools,search_tools,exec_tools}.py,
and the shared plumbing (docker_exec, get_container, get_task, to_abs,
truncate, never_raise) lives in swebench_tools/docker_bridge.py. See that
module's docstring for the full set of shared conventions (never raise,
absolute-path output, truncate everything except get_patch) and for how
this process learns which container/task to serve.

Each tool is wrapped in never_raise() before being registered, so a bug or
an infrastructure failure (e.g. a misconfigured container) comes back to
the LLM as a "[error] ..." string instead of crashing this server.
"""
from mcp.server.fastmcp import FastMCP

from swebench_tools.docker_bridge import never_raise
from swebench_tools.exec_tools import get_patch, run_command, run_tests
from swebench_tools.fs_tools import edit_file, list_files, read_file
from swebench_tools.search_tools import (
    find_references,
    search_code,
    search_function_or_class_definition_in_code,
)

mcp = FastMCP("swebench-tools")

_TOOLS = (
    read_file,
    edit_file,
    list_files,
    search_code,
    search_function_or_class_definition_in_code,
    find_references,
    run_tests,
    get_patch,
    run_command,
)

for _fn in _TOOLS:
    mcp.tool()(never_raise(_fn))


if __name__ == "__main__":
    mcp.run()