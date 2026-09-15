"""
Sandbox executor (Section V.2 points 1, 2).

Responsibilities:
  1. Keep one namespace dict that lives across steps, pre-filled with
     - MCP tool wrappers (discovered from mcp_client.py)
     - final_answer()  (built into the sandbox, NOT an MCP tool)
  2. execute(code) -> str : run code, capture stdout (the LLM only sees what it print()s)
  3. run_repl() : interactive mode for `uv run sandbox`

STAGE 0 (current): plain exec() in-process, NO security at all.
  TODO(stage 2): import allowlist, restricted builtins, path allowlist,
                 timeout, memory limit, no network (see sandbox/security.py).
"""
from __future__ import annotations

import contextlib
import io
import traceback
from typing import Any, Callable, Dict, Optional

from common.models import SandboxConfig


class Sandbox:
    def __init__(self, config: SandboxConfig, mcp_tools: Optional[Dict[str, Callable]] = None):
        self.config = config
        self.mcp_tools = mcp_tools or {}
        self.final_answer_value: Optional[str] = None
        self.final_answer_called: bool = False
        self.namespace: Dict[str, Any] = {}
        self._setup_namespace()

    def _final_answer(self, answer: str) -> None:
        """Built into the sandbox, not an MCP tool (Section V.2)."""
        self.final_answer_value = str(answer)
        self.final_answer_called = True

    def _setup_namespace(self) -> None:
        self.namespace["final_answer"] = self._final_answer
        self.namespace.update(self.mcp_tools)

    def execute(self, code: str) -> str:
        """Run `code` in the shared namespace and return what it printed (or the error)."""
        stdout_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                exec(code, self.namespace)
        except (KeyboardInterrupt, SystemExit):
            raise  # must reach the agent loop, never swallow these
        except Exception:
            # Keep the partial output, then show the error so the LLM can fix its code.
            return stdout_buffer.getvalue() + traceback.format_exc(limit=-1)
        return stdout_buffer.getvalue()

    def run_repl(self) -> None:
        """Read code, execute it, print result. `exit` or EOF quits."""
        print("Agent Smith sandbox. Type 'exit' to quit.")
        while True:
            try:
                line = input(">>> ")
            except EOFError:
                print()
                break
            if line.strip() == "exit":
                break
            if not line.strip():
                continue
            output = self.execute(line)
            if output:
                print(output, end="" if output.endswith("\n") else "\n")
            if self.final_answer_called:
                print(f"[final_answer] {self.final_answer_value!r}")
                self.final_answer_called = False
