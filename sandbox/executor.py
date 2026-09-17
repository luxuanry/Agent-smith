"""
Sandbox executor (Section V.2 points 1, 2).

Responsibilities:
  1. Keep one namespace dict that lives across steps, pre-filled with
     - MCP tool wrappers (discovered from mcp_client.py)
     - final_answer()  (built into the sandbox, NOT an MCP tool)
  2. execute(code) -> str : run code, capture stdout (the LLM only sees what it print()s)
  3. run_repl() : interactive mode for `uv run sandbox`

STAGE 2 (current): security.py is wired in.
  - import allowlist (ImportGuard)
  - restricted builtins, `open` checked against allowed_directories
  - timeout via signal.alarm
  TODO(stage 3): memory limit (resource.setrlimit), no network.
"""
from __future__ import annotations

import contextlib
import io
import signal
import traceback
from typing import Any, Callable, Dict, Optional

from common.models import SandboxConfig
from sandbox.security import ImportGuard, build_restricted_builtins


class Sandbox:
    def __init__(self, config: SandboxConfig, mcp_tools: Optional[Dict[str, Callable]] = None):
        self.config = config
        self.mcp_tools = mcp_tools or {}
        self.final_answer_value: Optional[str] = None
        self.final_answer_called: bool = False
        self.namespace: Dict[str, Any] = {}
        self._import_guard = ImportGuard(config.authorized_imports)
        self._setup_namespace()

    def _final_answer(self, answer: str) -> None:
        """Built into the sandbox, not an MCP tool (Section V.2)."""
        self.final_answer_value = str(answer)
        self.final_answer_called = True

    def _setup_namespace(self) -> None:
        self.namespace["final_answer"] = self._final_answer
        self.namespace.update(self.mcp_tools)
        restricted_builtins = build_restricted_builtins(self.config.allowed_directories)
        restricted_builtins["__import__"] = self._import_guard.guarded_import
        self.namespace["__builtins__"] = restricted_builtins

    def _timeout_handler(self, signum, frame) -> None:
        raise TimeoutError(
            f"Execution exceeded {self.config.max_execution_time_seconds}s and was terminated"
        )

    def execute(self, code: str) -> str:
        """Run `code` in the shared namespace and return what it printed (or the error)."""
        stdout_buffer = io.StringIO()
        self._import_guard.install()
        previous_handler = signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.config.max_execution_time_seconds)
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                exec(code, self.namespace)
        except (KeyboardInterrupt, SystemExit):
            raise  # must reach the agent loop, never swallow these
        except TimeoutError as e:
            return stdout_buffer.getvalue() + f"[TIMEOUT] {e}"
        except Exception:
            # Keep the partial output, then show the error so the LLM can fix its code.
            return stdout_buffer.getvalue() + traceback.format_exc(limit=-1)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)
            self._import_guard.uninstall()
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
