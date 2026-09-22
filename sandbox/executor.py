"""
Sandbox executor (Section V.2 points 1, 2).

Responsibilities:
  1. Keep one namespace dict that lives across steps, pre-filled with
     - MCP tool wrappers (discovered from mcp_client.py)
     - final_answer()  (built into the sandbox, NOT an MCP tool)
  2. execute(code) -> str : run code, capture stdout (the LLM only sees what it print()s)
  3. run_repl() : interactive mode for `uv run sandbox`

STAGE 4 (current): code now runs in a persistent CHILD PROCESS instead of
being exec()'d directly inside the agent's own process. Why this changed:

  - Real timeout. The previous approach used `signal.alarm`, which only
    interrupts Python BETWEEN bytecode instructions. Code stuck in a tight
    C-extension loop (some numpy/requests internals, a C-level infinite
    loop) never yields back to the Python interpreter, so alarm never
    fires and the "timeout" never actually stops it. A subprocess can be
    SIGKILLed unconditionally from outside -- no cooperation from the
    stuck code required, so this is a real guarantee instead of a
    best-effort one.
  - Real isolation. A segfault, a C-level crash, or the OS OOM-killing the
    process now only takes down the *worker*, not the whole agent_mbpp /
    agent_swebench run. Before, a crash inside exec() could kill the
    entire agent process (or worse, corrupt its state without killing it).
  - Memory limit is now TWO layers instead of one:
      1. security.apply_memory_limit()/reset_memory_limit() (RLIMIT_AS),
         applied ONLY around the exec(code, namespace) call inside the
         worker's loop -- not for the worker's whole lifetime. Reliable on
         Linux, loosely enforced by the macOS kernel. IMPORTANT: this used
         to be applied once at worker startup and left on permanently,
         which caused a real bug on Linux (never showed up on macOS, since
         macOS doesn't enforce RLIMIT_AS anyway): a forked, fully-loaded
         CPython worker can already be using a good chunk of a tight limit
         (e.g. 128MB in tests) just from its own imports, so when
         result_queue.put() lazily starts its internal feeder thread after
         exec() finishes, the mmap for that thread's stack could fail with
         "RuntimeError: can't start new thread" -- nothing was actually
         leaking, the cap meant for the user's code was just still active
         for the worker's own plumbing. Now the cap is applied right before
         exec() and lifted right after, so it never constrains anything
         except the code it's meant to constrain.
      2. An RSS watchdog in the PARENT: execute()'s polling loop (already
         running every _POLL_INTERVAL_SECONDS to check for a result/crash)
         also shells out to `ps -o rss= -p <pid>` to read the worker's
         actual resident memory and kills it if it crosses
         config.max_memory_mb. `ps` works the same way on Linux and macOS,
         so this layer is the one that makes the limit actually hold on
         both platforms, independent of how the kernel treats RLIMIT_AS.

Design:
  - One worker process per Sandbox instance, started in __init__ and kept
    alive across calls (`multiprocessing`, fork start method).
  - Two queues: code goes parent -> child (`_code_queue`), results come
    child -> parent (`_result_queue`).
  - The worker keeps its OWN `namespace` dict alive across calls (it lives
    in the child's memory, not the parent's), so a variable/function
    defined in step N is still there in step N+1 -- same externally
    visible behavior as the old in-process version.
  - If a call times out, or the worker dies (crash/OOM-kill), that worker
    is replaced with a fresh one. The namespace from that in-flight call
    is lost -- but the step failed anyway, so from the LLM's point of view
    this is no different from any other failed step: it sees an error
    observation and tries again.

MCP tools and the worker process:
  MCP tools must NOT be called directly inside the worker. The MCP
  connection lives in a background thread of the PARENT process, and fork
  only copies the calling thread -- so in the child, a tool call would wait
  forever for a thread that doesn't exist (the call hangs until timeout).

  Instead, the worker gets small proxy functions with the same names. A
  proxy sends (tool_name, kwargs) to the parent over a Pipe and waits for
  the reply; the parent, while polling for the result in execute(), runs
  the real MCP call and sends the result back. So the connection is only
  ever used by the process that owns it, and MCP tools run outside the
  sandbox, as Section V.2 describes.

  A Pipe (not a Queue) is used on purpose: Connection.send() writes
  synchronously and never starts a background feeder thread, so a tool
  call made while the memory cap is active can't fail with
  "can't start new thread" (the Queue problem described above).

Import restriction:
  The ImportGuard is installed only in the sandbox namespace's own
  __builtins__ (see _worker_main), NOT globally with install(). A global
  install would also apply to trusted code running in the worker, such as
  the tool proxies.
"""
from __future__ import annotations

import multiprocessing as mp
import queue as queue_module
import time
import traceback
from multiprocessing.connection import Connection
from typing import Any, Callable, Dict, List, Optional

from common.models import SandboxConfig
from sandbox.security import ImportGuard, apply_memory_limit, build_restricted_builtins, reset_memory_limit

# How often the parent polls for a result while waiting on a call. Small
# enough that a dead worker (crash/OOM) is noticed well before the full
# timeout elapses, instead of always waiting out the whole budget.
_POLL_INTERVAL_SECONDS = 0.1

# The RSS check (layer 2 of the memory limit, see module docstring) shells
# out to `ps` -- cheap, but no need to do it on every single 0.1s poll tick.
# Checking every 2nd tick still catches a runaway allocation within ~0.2s.
_RSS_CHECK_EVERY_N_TICKS = 2


def _get_worker_rss_mb(pid: int) -> Optional[float]:
    """Resident memory of the worker process, in MB, via `ps` (works the
    same way on Linux and macOS, unlike RLIMIT_AS -- see module docstring).
    Returns None if the process is already gone or `ps` itself fails.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = proc.stdout.strip()
    if not output:
        return None  # pid not found -- process already exited
    try:
        return int(output) / 1024  # ps reports RSS in KB
    except ValueError:
        return None


def _worker_main(
    code_queue: "mp.Queue",
    result_queue: "mp.Queue",
    config: SandboxConfig,
    tool_names: List[str],
    tool_conn: "Connection",
) -> None:
    """Entry point of the child process. Runs until it receives `None`
    (shutdown sentinel) or is killed by the parent. Everything in here
    happens in the child's own memory -- it never touches parent state.
    """
    import contextlib
    import io

    # NOTE: the memory cap is intentionally NOT applied here. It's scoped
    # to just the exec() call below instead -- see the module docstring's
    # "Memory limit" section for why applying it for the worker's whole
    # lifetime caused a real bug on Linux.
    namespace: Dict[str, Any] = {}
    final_answer_state: Dict[str, Any] = {"called": False, "value": None}

    def _final_answer(answer: str) -> None:
        """Built into the sandbox, not an MCP tool (Section V.2)."""
        final_answer_state["value"] = str(answer)
        final_answer_state["called"] = True

    def _make_tool_proxy(tool_name: str) -> Callable:
        """A stand-in for an MCP tool: forwards the call to the parent
        process (which owns the MCP connection) and returns its reply."""

        def proxy(**kwargs):
            tool_conn.send((tool_name, kwargs))
            status, value = tool_conn.recv()
            if status == "error":
                raise RuntimeError(value)
            return value

        proxy.__name__ = tool_name
        return proxy

    namespace["final_answer"] = _final_answer
    for tool_name in tool_names:
        namespace[tool_name] = _make_tool_proxy(tool_name)

    import_guard = ImportGuard(config.authorized_imports)
    restricted_builtins = build_restricted_builtins(config.allowed_directories)
    restricted_builtins["__import__"] = import_guard.guarded_import
    namespace["__builtins__"] = restricted_builtins

    while True:
        try:
            code = code_queue.get()
        except (KeyboardInterrupt, EOFError):
            break
        if code is None:  # shutdown sentinel
            break

        stdout_buffer = io.StringIO()
        error: Optional[str] = None
        apply_memory_limit(config.max_memory_mb)
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                exec(code, namespace)
        except (KeyboardInterrupt, SystemExit):
            raise
        except MemoryError:
            error = f"[MEMORY LIMIT] Execution exceeded {config.max_memory_mb}MB and was stopped"
        except Exception:
            # Keep the partial output, then show the error so the LLM can fix its code.
            error = traceback.format_exc(limit=-1)
        finally:
            # Lift the memory cap before touching result_queue.put() below,
            # which may need to start its own background thread the first
            # time it's called -- that shouldn't be squeezed by a limit
            # meant only for the code that just ran.
            reset_memory_limit()

        result_queue.put(
            {
                "output": stdout_buffer.getvalue(),
                "error": error,
                "final_answer_called": final_answer_state["called"],
                "final_answer_value": final_answer_state["value"],
            }
        )
        final_answer_state["called"] = False  # reported; reset for the next call


class Sandbox:
    def __init__(self, config: SandboxConfig, mcp_tools: Optional[Dict[str, Callable]] = None):
        self.config = config
        self.mcp_tools = mcp_tools or {}
        self.final_answer_value: Optional[str] = None
        self.final_answer_called: bool = False
        # fork (not spawn): the child inherits everything already imported
        # in the parent for free and doesn't need `mcp_tools` to be
        # picklable. See the fork caveat in the module docstring re: what
        # mcp_tools is (and isn't) safe to close over.
        self._ctx = mp.get_context("fork")
        self._code_queue: "mp.Queue" = self._ctx.Queue()
        self._result_queue: "mp.Queue" = self._ctx.Queue()
        # Pipe for MCP tool calls: the worker sends requests, we answer them.
        self._tool_conn, self._worker_tool_conn = self._ctx.Pipe()
        self._worker: mp.process.BaseProcess = self._spawn_worker()

    def _spawn_worker(self) -> mp.process.BaseProcess:
        worker = self._ctx.Process(
            target=_worker_main,
            args=(
                self._code_queue,
                self._result_queue,
                self.config,
                list(self.mcp_tools),
                self._worker_tool_conn,
            ),
            daemon=True,
        )
        worker.start()
        return worker

    def _restart_worker(self) -> None:
        if self._worker.is_alive():
            self._worker.kill()  # SIGKILL -- no cooperation from the child needed
            self._worker.join()
        # Old queues may hold a stale/half-written result from the dead
        # worker; start clean so the next call can't accidentally read it.
        self._code_queue = self._ctx.Queue()
        self._result_queue = self._ctx.Queue()
        self._tool_conn, self._worker_tool_conn = self._ctx.Pipe()
        self._worker = self._spawn_worker()

    def _serve_tool_requests(self) -> None:
        """Answer any MCP tool calls the worker is waiting on, using the
        real tool functions (and MCP connection) owned by this process."""
        while self._tool_conn.poll():
            try:
                tool_name, kwargs = self._tool_conn.recv()
            except (EOFError, OSError):
                return  # worker died mid-request; execute() will notice
            try:
                reply = ("ok", self.mcp_tools[tool_name](**kwargs))
            except Exception as e:
                reply = ("error", f"Tool '{tool_name}' failed: {type(e).__name__}: {e}")
            try:
                self._tool_conn.send(reply)
            except (BrokenPipeError, OSError):
                return

    def execute(self, code: str) -> str:
        """Run `code` in the persistent worker and return what it printed
        (or the error/timeout/crash message)."""
        self._code_queue.put(code)

        deadline = time.monotonic() + self.config.max_execution_time_seconds
        result: Optional[dict] = None
        over_memory_limit = False
        tick = 0
        while True:
            self._serve_tool_requests()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                result = self._result_queue.get(timeout=min(remaining, _POLL_INTERVAL_SECONDS))
                break
            except queue_module.Empty:
                if not self._worker.is_alive():
                    break  # crashed mid-call -- don't wait out the full timeout
                tick += 1
                if tick % _RSS_CHECK_EVERY_N_TICKS == 0:
                    rss_mb = _get_worker_rss_mb(self._worker.pid)
                    if rss_mb is not None and rss_mb > self.config.max_memory_mb:
                        over_memory_limit = True
                        break  # don't wait for the timeout -- kill it now

        if over_memory_limit:
            self._restart_worker()
            return f"[MEMORY LIMIT] Execution exceeded {self.config.max_memory_mb}MB and was stopped"

        if result is None:
            if self._worker.is_alive():
                self._restart_worker()
                return f"[TIMEOUT] Execution exceeded {self.config.max_execution_time_seconds}s and was terminated"
            else:
                self._restart_worker()
                return "[CRASHED] Worker process died while running this code (likely OOM or a segfault)"

        if result["final_answer_called"]:
            self.final_answer_value = result["final_answer_value"]
            self.final_answer_called = True

        if result["error"]:
            return result["output"] + result["error"]
        return result["output"]

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

    def shutdown(self) -> None:
        """Call when done with this Sandbox so the worker process doesn't
        leak. `daemon=True` means it would get cleaned up at interpreter
        exit either way, but don't rely on that for a long-running agent
        loop that creates many Sandboxes (one per task)."""
        if self._worker.is_alive():
            try:
                self._code_queue.put(None)
                self._worker.join(timeout=2)
            except Exception:
                pass
            if self._worker.is_alive():
                self._worker.kill()
                self._worker.join()

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
