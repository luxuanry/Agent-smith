# Agent Smith: How the MCP Connection Works

This note is organized around **"which process and which thread each piece of code runs in, and how they talk to each other."**
Instead of going file by file, it follows **the order in which the program actually runs.**

- Section 0: The whole picture on one page
- Section 1: Five concepts to know first
- Sections 2–3: The processes and threads involved, and why it is split up this way
- Sections 4–9: Following the execution order (connect → tool list → build functions → tool call → agent loop → cleanup)
- Section 10: stdio vs. HTTP
- Section 11: Common misconceptions
- Section 12: Where errors go
- Section 13: Live-modification practice

---

## 0. One-page summary

This is everything that is running while one MBPP task is being solved (`uv run python -m agent_mbpp ...`).

```
┌──────────────────────────── ① Agent main process ─────────────────────────────┐
│  agent_mbpp/__main__.py, common/agent_loop.py, sandbox/executor.py (Sandbox)  │
│                                                                               │
│   [main thread]                          [background thread]                  │
│    AgentLoop: talks to the LLM            asyncio event loop                  │
│    Sandbox: sends code to the worker      └ keeps the MCP session open        │
│    calls MCPClient.wrapper ──_run_coro──▶  session.call_tool(...)             │
└───────┬───────────────────────────────────────────────┬───────────────────────┘
        │ fork (created by Sandbox)                     │ launched by the MCP library (stdio)
        │ talks via Queue / Pipe                        │ talks via stdin/stdout
        ▼                                               ▼
┌──── ② Sandbox worker process ─────┐     ┌──── ③ MCP server process ───────┐
│ sandbox/executor.py _worker_main  │     │ mcp_tools_mbpp.py               │
│ runs LLM-written code via exec()  │     │ the real run_tests() lives here │
│ run_tests = proxy (forwards only) │     └────────────────┬────────────────┘
│ final_answer = built into worker  │                      │ subprocess.run
└───────────────────────────────────┘                      ▼
                                          ┌──── ④ Test process ─────────────┐
                                          │ python -c "<candidate+asserts>" │
                                          │ spawned fresh per run_tests     │
                                          └─────────────────────────────────┘
```

In one sentence each:

- **①** is the conductor. It talks to the LLM, hands code to the worker, and holds the connection (session) to the MCP server.
- **②** is where LLM-written code runs **locked up**. MCP tools do **not** run here. It only forwards requests to ①.
- **③** is where MCP tools **actually** run.
- **④** is where the code being graded runs, **locked up once more**.

`uv run sandbox --mcp-stdio ...` (the REPL a human uses directly) has exactly the same structure. The only difference is that in ①, `run_repl()` takes human input instead of AgentLoop.

---

## 1. Five concepts to know first

### 1-1. Processes and threads

| | Process | Thread |
|---|---|---|
| What it is | **One independent program** | **One worker inside a program** |
| Memory | Each has its own. They can't see each other's variables | Shares variables, since they're in the same program |
| How they talk | Needs a **channel** such as a pipe, queue, stdin/stdout, or HTTP | Shared variables or signals (Event) |
| When it dies | Only that process dies | Can affect the whole program |

In the Section 0 diagram, each box is a process, and [main thread] and [background thread] inside ① are threads.

### 1-2. Sync functions vs. async functions

```python
def f():            # regular (sync) function
    return 1
f()                 # runs as soon as it's called, returns 1

async def g():      # async function
    return 1
g()                 # ❗ does NOT run. You only get an "order ticket" (coroutine object)
```

- **Calling an async function doesn't run it.** It only creates an order ticket.
- What actually runs the ticket is the **event loop**.
- `await` means "I'll wait for the result here. Meanwhile, the loop is free to do other work."
- **`await` can only be used inside `async def`.** Using it in a regular function or at the top level of the code raises `SyntaxError`.

### 1-3. asyncio and the event loop

- `async` / `await` are **syntax**. They only **mark** something as asynchronous.
- `asyncio` is part of Python's **standard library**. It provides the **engine (event loop) that actually runs** the marked functions.
- The name means async + I/O (input/output). It keeps the program from sitting idle while it waits on network or pipe I/O.

Analogy: `async def` = **order form**, event loop = **kitchen**.

### 1-4. Session

Think of it as a **phone call**.

| Phone | MCP |
|---|---|
| Dialing | Opening the channel (`stdio_client` / `streamable_http_client`) |
| "Hello?" "Hi, go ahead." | `session.initialize()` |
| **The call being connected** | **The `ClientSession` object** |
| "What's on the menu?" | `session.list_tools()` |
| "One kimchi stew, please." | `session.call_tool("run_tests", {...})` |
| Hanging up | `close()` |

A session is an object that holds **the state of being connected to and talking with the server.** So that you don't redial for every question, it is **opened once and kept in use until the end.**

### 1-5. Who wrote which code

| Name | Whose code | Location |
|---|---|---|
| `connect_stdio`, `_start`, `_session_lifecycle`, `_run_coro`, `discover_tools`, `wrap_as_python_functions` | **This project** | `sandbox/mcp_client.py` |
| `stdio_client`, `streamable_http_client`, `ClientSession`, `initialize`, `list_tools`, `call_tool` | **The `mcp` library** (official MCP Python SDK) | `.venv/Lib/site-packages/mcp/...` |
| `asyncio.*`, `threading.*`, `subprocess`, `multiprocessing` | **Python standard library** | Built into Python |

For example, `initialize()` lives at `.venv/Lib/site-packages/mcp/client/session.py:160`. If you press **F12** (Go to Definition) in VS Code and the path contains `site-packages`, it's library code.

---

## 2. The cast: 4 processes + 2 threads

| | Who creates it | What code runs | When it's born and when it dies |
|---|---|---|---|
| **① Main process** | A human (`uv run ...`) | `agent_mbpp/__main__.py` or `sandbox/cli.py` | Start to finish |
| ├ Main thread | Python | AgentLoop / REPL, Sandbox, wrapper calls | Start to finish |
| └ Background thread | `mcp_client.py:99` `threading.Thread` | asyncio loop + MCP session | `connect_*` to `close()` |
| **② Sandbox worker** | `executor.py:307` `ctx.Process` (fork) | `_worker_main`: `exec()` of LLM code | `Sandbox()` to `shutdown()`. Recreated after a timeout or crash |
| **③ MCP server** | stdio: **the mcp library** (`mcp/client/stdio/__init__.py:251` `anyio.open_process`)<br>HTTP: **started separately by a human beforehand** | `mcp_tools_mbpp.py` | stdio: born and dies together with the session<br>HTTP: keeps running independently of us |
| **④ Test process** | `mcp_tools_mbpp.py:69` `subprocess.run` | `python -c "<imports + candidate code + tests>"` | Born on each `run_tests` call and dies right after |

**Who creates ③?** Even with stdio, **this project's code does not launch the process itself.** `connect_stdio` only builds a **recipe** that says "run it like this" (`StdioServerParameters`). The actual launch is done by the mcp library's `stdio_client`.

---

## 3. Why it's split this way

### 3-1. Why separate processes: containment

The walls are there so that **dangerous code can't break the important parts.**

| Wall | What it prevents |
|---|---|
| ① ↔ ② | Even if LLM code loops forever, blows up memory, or crashes, **the agent survives.** ① just kills the worker and makes a new one (`executor.py:386-395`) |
| ③ ↔ ④ | Even if the code being graded misbehaves, **the MCP server doesn't die** (comment at `mcp_tools_mbpp.py:23-24`) |
| ① ↔ ③ | The server is a swappable part. During evaluation, an **unknown MCP server** may be plugged in |

### 3-2. Why a background thread: a bridge between sync and async

Two things collide.

```
mcp library:  all async  (initialize, list_tools, call_tool are all async def)
our code:     all sync   (AgentLoop, REPL, executor.py:341, and the LLM-written code)
```

LLM code calls tools like this:

```python
result = run_tests(code=solution)    # called plainly, no await
print(result)
```

If `run_tests` were an async function:

```python
result = run_tests(code=solution)    # you get an order ticket, not a result. No request even reaches the server
print(result[:10])                   # 💥 TypeError: 'coroutine' object is not subscriptable
```

If you told the LLM to write `await run_tests(...)`, it would be top-level code run by `exec()`, so you'd get `SyntaxError: 'await' outside function`.

So here's how it's solved:

1. Start an asyncio loop (kitchen) on a background thread, then **open the session there and keep holding on to it.**
2. When sync code needs to ask the server something, it **drops an order ticket into that loop via `_run_coro` and waits for the result.**
3. From the outside, it just looks like **a regular function that returns a result.**

> We didn't choose async. **The mcp SDK is async**, so we have no choice. This project sends one request at a time, in order, so it isn't about speed either.

### 3-3. "Why not just call `asyncio.run()` every time?"

That works. But you'd have to open and close the connection **every time** you call a tool.

- stdio: the server process gets **started and stopped every time.** It's slow, and any state the server was holding is lost.
- HTTP: you'd have to connect and initialize every time. It works, but it's wasteful.

To **keep the session open**, you have to stay inside the `async with` block. Meanwhile, the main thread needs to talk to the LLM. **Doing "hold on to the session" and "do everything else" at the same time takes two workers.** That second worker is the background thread.

### 3-4. Why the worker (②) doesn't call MCP directly

fork copies **only the one thread that called fork.** So ② has **no** background thread (no MCP loop). If ② called `_run_coro`, it would **hang forever** waiting on a loop that doesn't exist.

So ② gets a **proxy** with the same name, and ① makes the real call on its behalf (Section 7).

---

## 4. Execution order ①: Connecting

It starts at `agent_mbpp/__main__.py:75` or `sandbox/cli.py:63`.

```python
mcp_client = MCPClient()                                  # cli.py:58 / __main__.py:62
mcp_client.connect_stdio("python mcp_tools_mbpp.py")      # cli.py:63 / __main__.py:75
```

### 4-0. `MCPClient()`: just empty slots (`mcp_client.py:53-60`)

```python
self.tools = {}                  # slot for the tool description sheets
self._loop = None                # slot for the event loop (kitchen)
self._thread = None              # slot for the background thread
self._session = None             # slot for the session
self._stop_event = None          # "time to stop" signal
self._ready = threading.Event()  # "connection ready" signal (off for now)
self._connect_error = None       # slot for the error if connecting fails
```

**Nothing is connected yet.**

### 4-1. `connect_stdio`: building the recipe (`mcp_client.py:65-78`)

```python
parts = shlex.split(command)
# "python mcp_tools_mbpp.py" → ["python", "mcp_tools_mbpp.py"]

server_params = StdioServerParameters(
    command=parts[0], args=parts[1:], env=dict(os.environ)
)
self._start(lambda: stdio_client(server_params))
```

- **`shlex.split`**: splits the string the way a shell would. A quoted path like `'python "/my dir/s.py"'` doesn't get broken apart at the space.
- **`env=dict(os.environ)`**: without this, the SDK only passes a few variables such as `PATH` and `HOME` to the server. Then `MBPP_TASK_FILE` (set at `__main__.py:72`) never reaches the server, and `run_tests` can't find the task file.
- **`server_params` is only a recipe.** Nothing has run yet.
- **`lambda: stdio_client(server_params)`**: instead of calling `stdio_client` **now**, this **wraps it in an envelope**: a function that means "run this when you're called later."
  - Why the envelope? `connect_http` uses the same `_start` (`:87`). **Only "how to open the channel" differs, and everything else is identical**, so only the part that differs is passed in as a lambda.
  - Why not call it now? The channel has to be opened with `async with`, and that must happen **inside the background thread's loop.**

### 4-2. `_start`: making one more worker (`mcp_client.py:89-106`)

```python
def run_loop():
    self._loop = asyncio.new_event_loop()                                # build a new kitchen
    asyncio.set_event_loop(self._loop)
    self._loop.run_until_complete(self._session_lifecycle(open_transport))

self._thread = threading.Thread(target=run_loop, daemon=True)
self._thread.start()             # the new thread starts running run_loop

self._ready.wait()               # the main thread blocks until the "ready" signal
if self._connect_error is not None:
    raise self._connect_error    # if it failed in the background, re-raise here
```

- `_start` itself runs on the **main thread**. Its job is "start the thread, then wait."
- `run_loop` runs on the **new thread**.
- `daemon=True`: when the main program exits, this thread dies with it. This keeps the thread from preventing the program from exiting.
- Exceptions raised in the background **don't automatically reach** the main thread. So they're stored in `_connect_error` and re-raised here.

### 4-3. `_session_lifecycle`: where the session actually opens (`mcp_client.py:108-136`, background thread)

```python
self._stop_event = asyncio.Event()
try:
    async with open_transport() as streams:                  # ①
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:    # ②
            await session.initialize()                       # ③
            self._session = session                          # ④
            self._ready.set()                                # ⑤
            await self._stop_event.wait()                    # ⑥
except BaseException as e:
    while len(getattr(e, "exceptions", ())) == 1:
        e = e.exceptions[0]
    self._connect_error = e
    self._ready.set()
finally:
    self._session = None
```

| # | What it does |
|---|---|
| ① | **Finally opens** the envelope (lambda). With stdio, **this is where the ③ MCP server process gets launched.** That process's stdout/stdin become the `read`/`write` streams |
| | Why pull out `streams[0], streams[1]`: stdio gives 2 values, HTTP gives 3 (the third is a session-id function). Writing `read, write = streams` raises `ValueError` on HTTP |
| ② | Puts an **object that talks by MCP rules** on top of the line that carries raw bytes |
| ③ | Handshake. "I speak MCP version X" ↔ "Me too, X, and I have the tools capability." If the versions don't match, it fails here (library `session.py:160`) |
| ④ | Stores the session. `discover_tools` and tool calls use it from here on |
| ⑤ | **Turns on the "ready" signal.** The main thread sleeping in `_ready.wait()` (4-2) wakes up, and `connect_stdio` returns |
| ⑥ | **Holds on here.** Without this line, `async with` would end immediately, closing the session and shutting down the server |

**⑥ does not put the whole thread to sleep.** It means: "This task will step aside until the stop signal arrives. **Loop, handle any other orders in the meantime.**" That's why the loop can later accept orders that come in through `_run_coro`.

**The except side:**
- Why catch even `BaseException`: no matter how it fails, `_ready.set()` must be called. Otherwise the main thread **hangs forever.**
- `while ... exceptions[0]`: anyio wraps errors in an `ExceptionGroup` with an unhelpful message like `"unhandled errors in a TaskGroup"`. If there's only one exception inside, this peels off the wrapper to get at the real cause (`ConnectError`, `FileNotFoundError`, etc.).

**Why do opening and closing both happen in one function?** anyio (the library the mcp SDK is built on) has a rule: **whatever is opened with `async with` must be closed in the same Task.** If opening and closing were sent through `_run_coro` separately, they would be different Tasks, and you'd get `"Attempted to exit cancel scope in a different task"`. So a single coroutine handles all of it: open → hold → close. (See the module docstring at the top of the file, lines 22-37.)

### 4-4. Connection timeline

```
[main thread]                           [background thread]                [③ MCP server]
MCPClient()        (empty slots)
connect_stdio()
  recipe + lambda
  _start()
    thread.start() ───────────────▶  run_loop(): create loop
    _ready.wait() 💤                  _session_lifecycle()
                                       ① open stdio_client ──────────▶ process launched
                                       ② ClientSession
                                       ③ initialize() ◀──────────────▶ handshake
                                       ④ self._session = session
    wakes up ◀──────────────────────── ⑤ _ready.set()
  return                               ⑥ _stop_event.wait() (holds session)   waiting for requests
```

**What we still don't know at this point:** **which tools** the server has. initialize only exchanges the version and "tools capability: yes." The list is requested separately in the next section.

---

## 5. Execution order ②: Getting the tool list (`discover_tools`)

Called from `cli.py:66` / `__main__.py:76`.

```python
def _run_coro(self, coro):                                        # mcp_client.py:141
    future = asyncio.run_coroutine_threadsafe(coro, self._loop)
    return future.result()

def discover_tools(self):                                         # mcp_client.py:150
    async def _list():
        result = await self._session.list_tools()
        return result.tools

    tools = self._run_coro(_list())
    self.tools = {t.name: t for t in tools}
    return self.tools
```

### Why is `_list` defined inside?

- `discover_tools` is a **regular function**, so it can't use `await`.
- `list_tools()` is async, so it needs `await`.
- So we make a **small async function, `_list`**, that can use `await`. Calling `_list()` creates an **order ticket** (not run yet), which is handed to `_run_coro`.

### `_run_coro`: the kitchen counter and the buzzer

```
[main thread]                                    [background loop]
_run_coro(_list())
  run_coroutine_threadsafe ── hand over ticket ──▶ run _list()
  future.result() 💤 (waiting for the buzzer)      await list_tools() ──▶ ③ "what tools do you have?"
                                                                   ◀── [run_tests, ...]
                   ◀── buzzer goes off ────────    return result.tools
self.tools = {"run_tests": Tool(...)}
```

- `run_coroutine_threadsafe`: safely places an order into that loop **from a different thread**. Normally you can only add work to a loop from the loop's own thread, which is why the `threadsafe` version is needed.
- `future.result()`: waits until the result is ready. **This is the point where an async call turns into a sync call.**
- Why not `asyncio.run(_list())`? That would create a **new loop (a new kitchen)** on the main thread. The session and pipes are **bound to the original loop**, so they can't be used from a new one.

### Result

```python
self.tools = {
    "run_tests": Tool(name="run_tests", description="Run the task's tests ...", inputSchema={...}),
}
```

A `Tool` is a **description sheet** holding the name, description, and argument schema. It is not a function you can call. The server (FastMCP) builds it from the docstring and type hints of each function decorated with `@mcp.tool()`.

The important point is that **no tool names are hardcoded in the code.** Everything works as-is even when an unknown MCP server is plugged in during evaluation.

These description sheets are used in two places:
- `generate_sandbox_manual(mcp_client.tools)` → a human-readable manual → goes into the **system prompt**. That's how the LLM knows `run_tests` exists and how to use it (`__main__.py:81, 85`)
- `wrap_as_python_functions()` → next section

---

## 6. Execution order ③: Turning description sheets into callable functions (`wrap_as_python_functions`)

Called from `cli.py:70` / `__main__.py:77`.

```python
def wrap_as_python_functions(self):                           # mcp_client.py:159
    return {name: self._make_wrapper(name) for name in self.tools}

def _make_wrapper(self, tool_name):                           # mcp_client.py:170
    def wrapper(**kwargs):
        async def _call():
            return await self._session.call_tool(tool_name, arguments=kwargs)

        result = self._run_coro(_call())
        texts = [block.text for block in result.content if hasattr(block, "text")]
        return "\n".join(texts)

    wrapper.__name__ = tool_name
    return wrapper
```

This builds one **remote-control button** per description sheet.

```python
{"run_tests": Tool description}   →   {"run_tests": <function that asks the server to run run_tests>}
```

### Line by line

- **dict comprehension**: calls `_make_wrapper(name)` for each tool name, building one function per tool.
- **`_make_wrapper` is a function that builds and returns a function.** The resulting `wrapper` **remembers** the outer `tool_name` (a closure).
- **`**kwargs`**: collects keyword arguments into a dict. `run_tests(code="...")` → `kwargs = {"code": "..."}`. MCP takes arguments as a dict of named values, so it's passed straight through. The downside is that **positional arguments are not accepted.** That's why the system prompt says "always call tools with keyword arguments" (`agent_loop.py:195`).
- **`_call` + `_run_coro`**: **exactly the same pattern** as `_list`. The only difference is the request sent to the server (`call_tool`).
- **`result.content`**: the server's reply is a **list** of blocks (text, images, etc.). Only blocks that have `text` are collected and joined into **a single string**.
- **`wrapper.__name__`**: a name tag so it shows up as `run_tests` instead of `wrapper` when debugging.

### Why `_make_wrapper` is split out (a Python trap)

If you build the wrapper directly inside the loop:

```python
for name in self.tools:
    def wrapper(**kwargs):
        return call_tool(name, kwargs)     # name is looked up "when called"
    result[name] = wrapper
```

The inner function looks up `name` **when it is called, not when it is created.** Once the loop is over, `name` only holds the last value, so **every button calls the last tool.** Calling a separate function, `_make_wrapper(name)`, creates a fresh `tool_name` variable on every call, so the problem goes away.

### ⚠️ Known limitation

`result.isError` is not checked. Even if the server replies "tool execution failed," that message is returned **as if it were a normal result.**

---

## 7. Execution order ④: The path of one tool call through four processes

When `Sandbox(mcp_tools=wrapped_tools)` is created (`__main__.py:84` / `cli.py:74`):

- ① forks ② (`executor.py:299` `mp.get_context("fork")`, `:307`).
- **Only the list of tool names** is passed to ② (`:313` `list(self.mcp_tools)`).
- ② builds a **proxy** for each name and puts it into the namespace used by `exec()` (`:240-241`).
- **The real wrappers stay in ①** (`self.mcp_tools`).
- There is one **Pipe** between ① and ② dedicated to tool calls (`:303`).

Now, when the LLM code runs `print(run_tests(code=solution))`:

```
② worker                      ① main (main thread)            ① main (background)     ③ MCP server         ④ test
────────                      ────────────────────            ───────────────────     ────────────         ──────
exec(LLM code)
 run_tests(code=s)
 = proxy (executor.py:229)
 tool_conn.send(
   ("run_tests",{"code":s})) ──Pipe──▶
 tool_conn.recv() 💤                 execute()'s polling loop
                                     (executor.py:367-368)
                                     _serve_tool_requests (:332)
                                     self.mcp_tools["run_tests"](code=s)   (:341)
                                     = wrapper (mcp_client.py:171)
                                     _run_coro(_call()) ─────────────▶ call_tool ──stdio──▶ run_tests()
                                                                                             (mcp_tools_mbpp.py:53)
                                                                                             subprocess.run ─────▶ candidate code
                                                                                                                  + asserts run
                                                                                              ◀──── stdout ─────  "PASS/FAIL"
                                                                          ◀──stdio── "[run_tests] 3/3 passed"
                                     ◀───────────────────────────── result
                                     extract text into one string
                   ◀──Pipe── send(("ok", "[run_tests] 3/3 passed"))
 return "...3/3 passed"
 print(...)  → buffered in stdout
```

- **While ① waits for the LLM code to finish, its main thread keeps checking the Pipe** (the while loop in `execute()`). That's how it can handle the worker's request right away.
- `executor.py:341` also calls `self.mcp_tools[tool_name](**kwargs)` **without await**. So the wrapper must be **a regular function that returns the result directly** (3-2).
- Why ④ gets `stdin=subprocess.DEVNULL` (`mcp_tools_mbpp.py:73`): in stdio mode, ③'s stdin is the **MCP message channel**. If ④ inherited it, the test code could intercept and read MCP messages, or get stuck reading from it.

---

## 8. Execution order ⑤: The whole agent loop (MBPP)

This is `AgentLoop.run()` in `common/agent_loop.py`. One turn (step) goes like this:

````
① AgentLoop                              LLM API                 ② worker (+ ③, ④)
───────────                              ───────                 ─────────────────
messages = [system, user_task]
llm.generate(messages)   (:86) ─────────▶
                         ◀─────────────── "Thought: ...
                                           ```python
                                           solution = '''def f(...): ...'''
                                           print(run_tests(code=solution))
                                           ```"
extract only the code block (:93)
sandbox.execute(code)    (:100) ───────────────────────────────▶ exec
                                                                  run_tests → the Section 7 path
                         ◀──────────────────────────────────── printed output = observation
final_answer called? (:117)   if not ↓
messages += [assistant: response, user: "Observation:\n..."]   (:131-132)
next turn ...
````

Once the LLM confirms that the tests pass, on the next turn it returns code like this:

```python
final_answer(solution)
```

→ Inside ②, `_final_answer` (`executor.py:220`) records the value → `execute()` copies it to ①'s `sandbox.final_answer_called` (`:397-399`) → AgentLoop sees it and stops (`agent_loop.py:117-121`).

Things to remember:

- **The LLM doesn't execute anything.** It only returns **text** that contains code. All execution happens in our own processes.
- **The observation is only what was `print()`ed.** If the code doesn't print it, the LLM can't see the result.
- **`final_answer` is not an MCP tool.** It's a function built into the worker and never goes through MCP.
- **`success=True` means "final_answer was called," not "the answer is correct."** Real grading is done by moulinette, which also runs **hidden tests**. That's why the prompt says "don't hardcode the expected test values" (`agent_loop.py:149-150`).
- The limits (10 iterations, 6000 input tokens, 1500 output tokens, 120 seconds) are in `__main__.py:30-33`, and `agent_loop.py` checks them every turn.

---

## 9. Execution order ⑥: Cleanup

`cli.py:77-80`:

```python
    try:
        sandbox.run_repl()
    finally:
        sandbox.shutdown()      # shut down the ② worker
finally:
    mcp_client.close()          # shut down the session, the background thread, and (for stdio) ③
```

`agent_mbpp/__main__.py` **writes the result file first** (`:114-115`) and only then calls `close()` (`:122`). This order means the results already obtained aren't lost even if cleanup fails.

`close()` (`mcp_client.py:186-196`):

```python
if not self._loop or not self._stop_event:
    return                                               # never connected: do nothing
self._loop.call_soon_threadsafe(self._stop_event.set)    # send "stop" to the background loop
if self._thread:
    self._thread.join(timeout=10)                        # wait up to 10 seconds for the thread to finish
```

Once the signal arrives, things unwind like this:

```
_stop_event.set()
 → ⑥ await _stop_event.wait() returns
 → async with ClientSession closes     (session ends)
 → async with stdio_client closes      (stdio: ③ server process exits / HTTP: just disconnects)
 → _session_lifecycle ends → run_until_complete ends → background thread ends
```

Why ask via `call_soon_threadsafe` instead of calling `_stop_event.set` directly: asyncio objects must only be touched **from their own loop's thread.**

---

## 10. stdio vs. HTTP

**Only the way the channel is opened differs. Once it's open, everything is identical.** In the code, the only place they diverge is one lambda line each (`mcp_client.py:78`, `:87`).

### stdio

```
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json

┌─ ① main ─────────────────┐
│ [BG thread] session      │──stdin──▶ ┌─ ③ MCP server (child of ①) ─┐
│                          │◀─stdout── │ mcp_tools_mbpp.py           │
└──────────────────────────┘           └─────────────────────────────┘
  ③ is launched by the mcp library and dies on close()
```

### HTTP

```
(terminal 1) python mcp_tools_mbpp.py --http --port 8000     ← a human starts the server first
(terminal 2) uv run sandbox --mcp-server http://127.0.0.1:8000/mcp sandbox_template.json

┌─ ① main ─────────────────┐   HTTP POST   ┌─ ③ MCP server (separate program) ─┐
│ [BG thread] session      │─────────────▶ │ mcp_tools_mbpp.py --http          │
│                          │◀── JSON/SSE ─ │                                   │
└──────────────────────────┘               └───────────────────────────────────┘
  Nobody starts ③ for you. It keeps running after close()
```

| | stdio | HTTP |
|---|---|---|
| Creates a new ③ server process? | ✅ the mcp library creates it | ❌ attaches to a server that's already running |
| Needs a background thread? | ✅ | ✅ (because our code is sync; it has nothing to do with where the server is) |
| Channel | ③'s stdin / stdout | HTTP requests / responses |
| If the server isn't running | (n/a, it gets started for you) | `ConnectError` at step ① |
| Server after `close()` | Dies | Stays alive |

### Server-side `--http` mode (`mcp_tools_mbpp.py:87-104`)

```python
if args.http:
    mcp.settings.host = args.host         # default 127.0.0.1 = reachable only from this machine
    mcp.settings.port = args.port
    mcp.run(transport="streamable-http")  # address: http://<host>:<port>/mcp
else:
    mcp.run()                             # stdio (this branch runs when connect_stdio launches it)
```

- The same `run_tests` code can be served both ways. **On the server side, too, only the channel changes.**
- To run the server inside a Docker container and connect from outside, you need `--host 0.0.0.0` (Stage 4, SWE-bench).
- In a stdio server, stdin/stdout are **reserved for the protocol.** Using `print()` in server code breaks the protocol. Send debug output to stderr instead.

---

## 11. Common misconceptions

| Misconception | Reality |
|---|---|
| "MCP tools run in the sandbox" | ② only has a **proxy**. The real execution happens in the **③ MCP server**, and the code being graded runs in **④** |
| "Creating the thread creates another session" | There is **only one** session. What gets added is **a thread + an event loop**, and the session lives inside them |
| "asyncio creates the thread" | The thread is created by `threading` (`:99`). asyncio creates the loop **inside** that thread (`:95`) |
| "Once connect_stdio finishes, we know the tool list" | At that point the server has only started and said hello. The list is requested **separately** in `discover_tools` |
| "The server runs once and exits" | The server **stays up** waiting for requests |
| "`_list` and `_call` both ask what tools exist" | `_list` = **"Can I see the menu?"** (`tools/list`, once at startup). `_call` = **"I'll have this item"** (`tools/call`, every time a tool is called). Only the pattern is the same |
| "The background thread sleeps during `_stop_event.wait()`" | Only that **task** steps aside. The **loop stays awake** and handles other orders (`_list`, `_call`) |
| "Our code launches the stdio server process" | Our code only provides the recipe. The **mcp library** launches it |
| "HTTP doesn't launch a server, so no thread is needed" | The thread is needed **because our code is sync.** It's needed exactly as much as with stdio |
| "`initialize()` is our code" | It's an **mcp library** function (`session.py:160`) |
| "`success=True` means the answer is correct" | It only means final_answer was called. Grading is done by moulinette |

---

## 12. Where errors go

### Connection failure (e.g. the server isn't running, or the command has a typo)

```
[BG] exception at _session_lifecycle ①
 → except: peel off the ExceptionGroup → self._connect_error = e → _ready.set()
[main] _start: _ready.wait() is released → raise self._connect_error   (mcp_client.py:106)
[main] cli.py:67 except → mcp_client.close() → sys.exit("error: cant connect to MCP server: ConnectError: ...")
       (agent_mbpp: __main__.py:97 except → result file with success=False)
```

### Problems during a tool call

| Situation | Result |
|---|---|
| The wrapper raises (lost connection, etc.) | `executor.py:342-343` → `("error", "Tool 'run_tests' failed: ...")` → the proxy in ② re-raises it as a `RuntimeError` → the LLM sees the traceback as its observation |
| The graded code loops forever | ④ times out after 10 seconds (`mcp_tools_mbpp.py:79`) → the string `"[run_tests] Timed out ..."` comes back as if it were a normal result |
| The LLM code itself loops forever or blows up memory | ① kills ② and makes a new one → `[TIMEOUT]` / `[MEMORY LIMIT]` / `[CRASHED]` (`executor.py:385-395`) |

---

## 13. Live-modification practice (eval prep)

First say out loud "which file and which line you'd change," then check the answer.

| Question | Answer |
|---|---|
| Print "connected: N tools" when the connection succeeds | Around `cli.py:71`. `len(mcp_client.tools)` |
| Which tools exist when you run without any MCP options? | Only `final_answer`. `mcp_tools = {}` (`cli.py:59`) is passed through unchanged |
| How do you run the HTTP server on a different port? | No code change: `python mcp_tools_mbpp.py --http --port 9000`, then connect with `--mcp-server http://127.0.0.1:9000/mcp` |
| Prefix the output with `[TOOL ERROR]` when a tool returns an error | Around `mcp_client.py:177`. Check `result.isError` |
| What if the HTTP connection needs an auth header? | `mcp_client.py:87`. Pass `http_client=httpx.AsyncClient(headers=...)` to `streamable_http_client` |
| Where does the program exit when connecting fails? | The Section 12 path: `_session_lifecycle` except → `_start` raise (106) → `cli.py` except (67) → `sys.exit` (69) |
| What happens if `_ready.set()` is left out of the except block? | On connection failure, `_ready.wait()` (104) is never released and **the program hangs** |
| What happens if you change it to `read, write = streams`? | stdio still works, but HTTP returns 3 values, so you get `ValueError` |
| What happens if you delete ⑥ `await self._stop_event.wait()`? | `async with` ends immediately and the session closes. Then `discover_tools` fails because `self._session` is `None` |
| What happens if the worker (②) calls the wrapper directly? | fork copies only one thread, so ② has no MCP loop → it waits forever |
| Does adding a new tool require changing client code? | No. Just add an `@mcp.tool()` function to the server (`mcp_tools_*.py`), and `discover_tools` → wrapper → manual all pick it up automatically |
| What happens if you build the wrappers inside a for loop without `_make_wrapper`? | The closure trap. Every button calls the last tool |
