"""
MCP Client (Section III.1 diagram + Section V.2 point 5).

The sandbox itself acts as an MCP client, connecting to an MCP server
(could be our own mcp_tools_mbpp.py / mcp_tools_swebench.py, or, during
evaluation, an unknown MCP server — so this logic must stay generic and
never hardcode "I know there are exactly these tools").

Sync vs async — why the background thread exists
--------------------------------------------------
The official MCP Python SDK is async (built on asyncio): every call to the
server (listing tools, calling a tool) is an `await`-able coroutine. But the
sandbox's exec(code) runs plain synchronous code — when the LLM's code calls
read_file(...), it needs a normal blocking function call that returns a
value, not something it has to `await`.

To bridge this, we start a background thread that runs its own asyncio
event loop for the lifetime of the connection. Every time a sandbox
function needs to actually talk to the MCP server, it schedules that async
call onto the background loop and *blocks* until the result comes back
(via asyncio.run_coroutine_threadsafe(...).result()). From the sandbox's
point of view, this looks and behaves like an ordinary synchronous function
call — the async machinery is fully hidden behind it.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self):
        self.tools: Dict[str, object] = {}  # tool_name -> Tool schema object (from the server)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[ClientSession] = None
        self._session_cm = None  # async context manager for ClientSession
        self._stdio_cm = None  # async context manager for stdio_client

    # ------------------------------------------------------------------
    # Background event loop plumbing
    # ------------------------------------------------------------------
    def _start_background_loop(self) -> None:
        self._loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

    def _run_coro(self, coro):
        """Schedule `coro` on the background loop and block until it's done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    # ------------------------------------------------------------------
    # Connecting
    # ------------------------------------------------------------------
    def connect_stdio(self, command: str) -> None:
        """Launch the MCP server as a subprocess and connect over stdin/stdout.

        `command` example: "python mcp_tools_mbpp.py"
        """
        self._start_background_loop()

        parts = command.split()
        server_params = StdioServerParameters(command=parts[0], args=parts[1:])

        async def _connect():
            self._stdio_cm = stdio_client(server_params)
            read, write = await self._stdio_cm.__aenter__()
            self._session_cm = ClientSession(read, write)
            self._session = await self._session_cm.__aenter__()
            await self._session.initialize()

        self._run_coro(_connect())

    def connect_http(self, url: str) -> None:
        """TODO: implement when an HTTP-based MCP server is needed
        (Section V.2 requires supporting both stdio and HTTP transports).
        """
        raise NotImplementedError("TODO: HTTP transport")

    # ------------------------------------------------------------------
    # Discovering and wrapping tools
    # ------------------------------------------------------------------
    def discover_tools(self) -> Dict[str, object]:
        async def _list():
            result = await self._session.list_tools()
            return result.tools

        tools = self._run_coro(_list())
        self.tools = {t.name: t for t in tools}
        return self.tools

    def wrap_as_python_functions(self) -> Dict[str, Callable]:
        """Turn every discovered MCP tool into a plain Python function that
        can be dropped straight into the sandbox's exec() namespace.

        NOTE: wrapped functions only accept KEYWORD arguments (e.g.
        read_file(filepath="a.py", start_line=1, end_line=10)), never
        positional ones. This keeps the wrapper simple and unambiguous —
        the system prompt should tell the LLM to always call tools with
        keyword arguments.
        """
        return {name: self._make_wrapper(name) for name in self.tools}

    def _make_wrapper(self, tool_name: str) -> Callable:
        def wrapper(**kwargs):
            async def _call():
                return await self._session.call_tool(tool_name, arguments=kwargs)

            result = self._run_coro(_call())
            # MCP tool results are a list of content blocks; join the text ones.
            texts = [block.text for block in result.content if hasattr(block, "text")]
            return "\n".join(texts)

        wrapper.__name__ = tool_name
        return wrapper

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Shut down the MCP session, the subprocess, and the background
        thread. Call this once you're done with the client (e.g. in a
        try/finally around agent.run(...)) so the process doesn't hang.
        """
        if not self._loop:
            return

        async def _close():
            if self._session_cm:
                await self._session_cm.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)

        self._run_coro(_close())
        self._loop.call_soon_threadsafe(self._loop.stop)