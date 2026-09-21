# Agent Smith — What Happens After the Response

Study notes for `common/agent_loop.py:80-108`.
Scope: one step of the loop, from raw model text to the termination check.

---

## 0. The four stages

```
response.text  (just a long string)
      |  (1) extract     extract_python_code_block()
   code  (runnable Python string)
      |  (2) execute     sandbox.execute()
observation  (result string)
      |  (3) record      steps.append(StepMetrics(...))
      |  (4) check       if sandbox.final_answer_called
      |  (not done) append to messages, next turn
```

Why the pipeline exists: an LLM can only emit text. It cannot run code, read
files, or verify a test. It can *claim* it checked something without having
checked anything. So we run the code for it and feed back the real result.

---

## 1. Extract

```python
extraction = extract_python_code_block(response.text)
```

`response.text` contains prose and code mixed together:

```
Thought: I will define the function as a string and check the test.
```python
solution = '''def square(n):
    return n * n
'''
exec(solution)
print("all tests passed")
```
```

Passing that whole string to `exec()` raises `SyntaxError` on the first line.
Only the fenced part is valid Python, so it has to be cut out.

### The regex

```python
_PY_BLOCK_RE = re.compile(r"```python\s*(.*?)```", re.DOTALL)
```

| Element | Purpose |
|---|---|
| `` ```python `` | literal opening fence |
| `\s*` | skip whitespace/newline after the fence |
| `(.*?)` | capture group — the code itself |
| `re.DOTALL` | makes `.` match newlines, so multi-line code is captured |
| `?` in `.*?` | non-greedy; without it, `.*` swallows through to the **last** fence, pulling prose into the code |
| `.search()` (not `findall`) | only the **first** block — one execution per turn |

`match.group(1).strip()` is the captured code, ready for `exec()`.

#### `re.compile` — what it is and why it is a module constant

`re.compile(pattern)` parses the pattern string **once** and returns a reusable
pattern object. `_PY_BLOCK_RE.search(text)` then just runs it.

The alternative, `re.search(r"...", text)` inside the function, re-looks-up the
pattern on every call. Behaviour is identical; compiling once at module level
buys a little speed and, more importantly, puts the contract — *this is the
shape of a reply we accept* — in one named place.

#### The `.` is in the **pattern**, not in the model's text

This trips people up: `.` is not a character we are looking for in the response.
It is the regex metacharacter inside `(.*?)`, and it means *any one character*.

By default `.` means *any one character **except** a newline*. `re.DOTALL` drops
that exception, so `.` matches `\n` too. The table row above is loose wording:
DOTALL does not make `.` *be* a newline, it makes `.` *also accept* newlines.

It matters because every real reply is multi-line. Without DOTALL, `(.*?)` stops
at the first `\n` and never reaches the closing fence:

~~~python
text = "Thought: ok\n```python\na = 1\nprint(a)\n```"

re.search(r"```python\s*(.*?)```", text)               # -> None
re.search(r"```python\s*(.*?)```", text, re.DOTALL)    # -> 'a = 1\nprint(a)\n'
~~~

So without the flag every block longer than one line falls into the
"No code block found" branch below.

### When no block is found

```python
if extraction.code is None:
    observation = (
        "No code block found. Reply with 'Thought: ...' followed by a "
        "```python ... ``` block, then <end_code>."
    )
```

Not a crash and not a termination. The error message *becomes* the observation,
so the model receives it as feedback and can fix its format on the next turn.
One step is wasted; the task survives.

---

## 2. Execute

```python
observation = self.sandbox.execute(extraction.code) or "(no output — use print())"
```

`sandbox/executor.py`:

```python
def execute(self, code: str) -> str:
    stdout_buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buffer):
            exec(code, self.namespace)
    except Exception:
        return stdout_buffer.getvalue() + traceback.format_exc(limit=-1)
    return stdout_buffer.getvalue()
```

### Capturing output

`io.StringIO()` is an in-memory file. `contextlib.redirect_stdout` swaps
`sys.stdout` for it inside the `with` block, so `print()` writes into the buffer
instead of the terminal, and `.getvalue()` retrieves it. Output sent to the real
terminal could not be put back into the next request — this is how we keep it.

This is why the system prompt says *"Only what you print() is visible"*.
Expression values are not returned; `exec` is not a REPL.

#### What "not a REPL" means

In the interactive interpreter, a bare expression is echoed automatically:

```
>>> 1 + 1
2                 <- nothing was printed; the REPL echoed the value
```

`exec()` does not do that. It evaluates the expression, throws the value away,
and writes nothing to stdout:

```python
exec("1 + 1", ns)        # buffer stays ""        -> observation = "(no output ...)"
exec("print(1 + 1)", ns) # buffer = "2\n"        -> observation = "2\n"
```

So the chain is: the model's code calls `print()` -> `sys.stdout` (currently the
`StringIO`) receives the text -> `getvalue()` turns the buffer back into a plain
`str` -> that `str` becomes `observation` and is pasted into the next request.
Anything the code computes but does not print is invisible to the model.

### The namespace

`exec(code, self.namespace)` — the second argument is the dict the code sees as
its globals. It is pre-filled in `Sandbox.__init__`:

```python
self.namespace["final_answer"] = self._final_answer
self.namespace.update(self.mcp_tools)
```

So `final_answer(...)` and every MCP tool look like ordinary global functions to
the model.

The **same dict** is reused every step, which is what makes state persist:

```
step 1:  exec("solution = '...'", ns)        ->  ns["solution"] set
step 2:  exec("final_answer(solution)", ns)  ->  ns["solution"] still there
```

A fresh dict per step would raise `NameError` on step 2. This one dict is the
entire implementation of *"Variables and functions you define persist between
turns"*.

### Errors are feedback

On exception, the return value is **partial output + traceback**. The model then
sees:

```
Observation:
Traceback (most recent call last):
  File "<string>", line 4, in <module>
AssertionError
```

and corrects its code next turn. A failing assert is a normal path through the
loop, not a loop failure.

### The `or` fallback

If nothing was printed, `execute` returns `""`, and `or "(no output — use
print())"` substitutes a hint. An empty observation would just confuse the model.

---

## 3. Record

```python
steps.append(StepMetrics(
    step=step,
    input_tokens=response.input_tokens,
    output_tokens=response.output_tokens,
    request_time_ms=response.request_time_ms,
    api_url=self.llm_provider.base_url,
    model_name=self.llm_provider.model_name,
    llm_output=response.text,
    sandbox_input=extraction.code or "",
    sandbox_output=observation,
    retries=response.retries,
))
```

Three fields form the reproducible trace of a turn:

| Field | Holds |
|---|---|
| `llm_output` | what the model said (raw) |
| `sandbox_input` | what was actually executed |
| `sandbox_output` | what came back |

`sandbox_input == ""` marks a step where extraction failed, so format errors are
visible in the log alone.

### Why it sits before the termination check

If the order were reversed, the successful final step would never be appended —
the most important turn of the task would be missing, `iterations = len(steps)`
would be short by one, and its tokens would drop out of the totals.

Rule: record unconditionally, judge afterwards.

---

## 4. Check for termination

```python
if self.sandbox.final_answer_called:
    return finish(True, self.sandbox.final_answer_value)
```

The loop never parses the text for "I'm done". The signal arrives as a **side
effect of executing the model's code**:

```
1. system prompt:  "call final_answer(answer) inside a code block"
2. model emits:    ```python
                   final_answer(solution)
                   ```
3. stage 1 extracts it, stage 2 exec()s it
4. ns["final_answer"] is Sandbox._final_answer:

       def _final_answer(self, answer):
           self.final_answer_value = str(answer)
           self.final_answer_called = True

5. after exec returns, the loop reads the flag -> return
```

Because it is a real function call and not string matching, conditional
termination works for free:

```python
if all_tests_pass:
    final_answer(solution)
else:
    print("still failing")
```

### `finish()`

A closure over `task_id`, `steps` and `start`, so all three exit points are one
line. It aggregates:

```python
iterations          = len(steps)
total_requests      = sum(1 + s.retries for s in steps)   # first call + retries
total_input_tokens  = sum(s.input_tokens for s in steps)
total_output_tokens = sum(s.output_tokens for s in steps)
total_time_seconds  = time.perf_counter() - start
```

### The three exits

| Exit | Line | Result |
|---|---|---|
| `final_answer` was called | `agent_loop.py:104` | `success=True`, solution returned |
| LLM request raised | `agent_loop.py:77` | `success=False`, step **not** recorded |
| `for` loop ran out | `agent_loop.py:110` | `success=False`, "Reached max iterations" |

All three return a `SolutionOutput`, so the caller only reads `success`.

---

## 5. Append and continue

```python
messages.append({"role": "assistant", "content": response.text})
messages.append({"role": "user", "content": f"Observation:\n{observation}"})
```

Two messages per turn: what the model said, and what came back. The observation
is sent as `role: "user"` because it must read as information arriving from
outside; as `assistant` the model would treat it as its own words.

The next iteration sends this longer list. The model's "memory" is nothing but
this growing list.

Note the `return` in stage 4 sits **above** these lines, so the successful final
turn is never appended to `messages`. It is already in `steps`, and no further
request is sent.

---

## 6. Full trace

```
messages = [system, "Write a function to find the square of a number..."]

-- step 1 --
  -> LLM
  <- "Thought: define it as a string and test it.
      ```python
      solution = '''def square(n):
          return n * n
      '''
      exec(solution)
      assert square(3) == 9
      print("all tests passed")
      ```"

  (1) code = "solution = '''...'''\nexec(solution)\nassert...\nprint(...)"
  (2) ns["solution"], ns["square"] set; assert passes
      observation = "all tests passed\n"
  (3) steps = [Step1]
  (4) final_answer_called? False
  (5) messages = [system, task, assistant(...), user("Observation:\nall tests passed")]

-- step 2 --
  -> LLM  (now sees 4 messages)
  <- "Thought: tests pass, submit.
      ```python
      final_answer(solution)
      ```"

  (1) code = "final_answer(solution)"
  (2) _final_answer runs: value = "def square(n):\n    return n * n\n", flag = True
      nothing printed -> observation = "(no output — use print())"
  (3) steps = [Step1, Step2]
  (4) final_answer_called? True
      return finish(True, "def square(n):\n    return n * n\n")
      iterations=2, total_requests=2
```

---

## 7. Who actually writes the observation

Look again at step 1 of the trace:

```
observation = "all tests passed\n"
```

Nothing in the loop decided that the tests passed. That string is a **literal the
model typed inside its own code block**:

```python
assert square(3) == 9
print("all tests passed")     # <- the observation, verbatim
```

`Sandbox.execute` does not inspect, judge or verify anything. It returns
`stdout_buffer.getvalue()`. Only two kinds of text can ever reach `observation`:

1. whatever `print()` wrote during `exec`
2. the traceback, if an exception escaped

Prose outside the fence never gets there — it was dropped back in stage 1.

### Where the asserts come from

They are not hallucinated. The moulinette dumps them into the task file, and
`agent_mbpp/__main__.py` pastes them into the user message:

```python
parts.append("Tests:\n" + "\n".join(task.test_list))
```

`MBPPTaskInput.test_list` (Section V.3 of the subject) is exactly that list, so
the model starts the task already holding the real tests. In
`cache/mbpp_solution.json` you can see the model copying both given asserts
verbatim.

### But the report is still self-issued

The model is free to skip the asserts and print the verdict anyway:

```python
solution = '''def ascii_value(k):
    return 82
'''
exec(solution)
print("all tests passed")     # sandbox has no opinion about this
```

The observation would read `all tests passed`. The only victim is the model
itself: the score is decided outside this loop, by

```
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json ../cache/mbpp_solution.json
```

which re-runs the *original* `test_list` against the submitted `solution`
string. A false observation cannot buy a pass; it just wastes the run.

### The fix: `run_tests` (stage 1)

Section V.3.2 of the subject requires an MBPP MCP tool named `run_tests`. Its
purpose is precisely this gap — it moves authorship of the verdict out of the
model and into our code:

| | who produces the verdict string | trustworthy |
|---|---|---|
| stage 0 (now) | the model's own `print("all tests passed")` | no |
| stage 1 (`run_tests`) | our MCP server, running the real `test_list` | yes |

The shape that matters is printing the **tool's return value**, not a sentence
of the model's own:

```python
print(run_tests(solution))    # observation = "2/2 passed"  (our words)
```

`run_tests(...)` followed by a separate `print("all tests passed")` would change
nothing — and the return value would be discarded anyway, since `exec` is not a
REPL (§2).

Three places have to move together:

| file | change |
|---|---|
| `mcp_tools_mbpp.py` | implement `run_tests` (currently `raise NotImplementedError`) |
| `common/agent_loop.py` — few-shot example | the example still teaches `assert ... / print("all tests passed")`; the model imitates the example, so it must show `print(run_tests(...))` |
| `common/agent_loop.py` — the `For {benchmark} tasks:` line | "check it against the given tests" -> validate with `run_tests` and print its output |

Two design decisions the tool forces, because the MCP server is a **separate
process** and cannot see the sandbox namespace:

- how the candidate source reaches it — an argument (`run_tests(code: str)`) or
  a shared file
- how it learns `test_list` — the task-file path via argv or env at startup

The stub's pseudo-code shows a no-argument `run_tests()`; the subject does not
fix the signature, so either is allowed, but a no-argument version needs an
answer to "how does the server know the current solution".
