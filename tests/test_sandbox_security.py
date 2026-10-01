"""
沙盒安全测试骨架（对应 Section VI Table VI.1 的 exam_sandbox.sh 检查项）：
  - import block
  - builtin block
  - network block
  - path restrict
  - timeout
  - memory limit
  - MCP protocol

评审会跑类似这些测试，建议自己先写、先跑通，别等评审才第一次面对。
"""
import os
import time

import pytest

from common.models import SandboxConfig
from sandbox.executor import Sandbox


@pytest.fixture
def sandbox():
    config = SandboxConfig(
        authorized_imports=["math"],
        allowed_directories=["/tmp/agent"],
        max_execution_time_seconds=2,
        max_memory_mb=128,
    )
    sb = Sandbox(config=config)
    yield sb
    # STAGE 4: each Sandbox now owns a live worker process (see
    # sandbox/executor.py). Shut it down explicitly after each test so a
    # full test run doesn't accumulate orphaned processes while it's going
    # -- Sandbox.__del__ would eventually catch it, but GC timing isn't
    # something to rely on across dozens of tests.
    sb.shutdown()


def test_allowed_import_works(sandbox):
    output = sandbox.execute("import math\nprint(math.sqrt(4))")
    assert "2.0" in output


def test_forbidden_import_is_blocked(sandbox):
    output = sandbox.execute("import os\nprint(os.listdir('.'))")
    assert "ImportError" in output or "not authorized" in output.lower()


def test_path_outside_allowlist_is_blocked(sandbox):
    output = sandbox.execute("open('/etc/passwd').read()")
    assert "error" in output.lower() or "denied" in output.lower()


def test_timeout_is_enforced(sandbox):
    output = sandbox.execute("while True:\n    pass")
    assert "timeout" in output.lower()


def test_final_answer_sets_flag(sandbox):
    sandbox.execute('final_answer("done")')
    assert sandbox.final_answer_called is True
    assert sandbox.final_answer_value == "done"


def test_network_import_is_blocked(sandbox):
    # socket/urllib/http.client are simply never on the authorized_imports
    # allowlist, so the same ImportGuard that blocks `os` blocks these too.
    for module in ("socket", "urllib.request", "http.client"):
        output = sandbox.execute(f"import {module}\nprint('reached')")
        assert "ImportError" in output or "not authorized" in output.lower()
        assert "reached" not in output


def test_memory_limit_is_enforced(sandbox):
    # sandbox fixture caps max_memory_mb at 128; try to grab ~400MB in one shot.
    output = sandbox.execute("x = bytearray(400 * 1024 * 1024)\nprint('reached')")
    assert "memory" in output.lower()
    assert "reached" not in output


# def test_agent_path_only_shows_what_was_printed(sandbox):
#     # execute() defaults to echo_last_expr=False, so an expression statement's
#     # value is discarded no matter how the code happens to be shaped. The loop
#     # is the case that matters: it's ONE top-level statement, so the old
#     # "try single first" compile echoed every iteration's value into the
#     # observation -- burning context for output the LLM never asked for.
#     assert sandbox.execute("sorted([3, 1, 2])") == ""
#     assert sandbox.execute("x = [3, 1, 2]\nsorted(x)") == ""
#     assert sandbox.execute("for q in [1, 2, 3]:\n    str(q)") == ""
#     # ...and print() still works, which is the only channel the LLM is told about.
#     assert "2.0" in sandbox.execute("import math\nprint(math.sqrt(4))")


# def test_repl_path_echoes_expression_values(sandbox):
#     # run_repl() opts in to the interactive behavior, matching CPython's own
#     # REPL: a bare expression shows its repr, nested statements included.
#     assert sandbox.execute("sorted([3, 1, 2])", echo_last_expr=True) == "[1, 2, 3]\n"
#     assert sandbox.execute("if True:\n    2 + 2", echo_last_expr=True) == "4\n"
#     # Several statements at once (a paste) still runs -- it just can't echo,
#     # since "single" rejects it and the "exec" fallback takes over.
#     assert sandbox.execute("y = 5\nprint(y)", echo_last_expr=True) == "5\n"


# TODO: MCP 协议相关的测试，等 mcp_client.py / mcp_tools_mbpp.py 写完之后再补


# ---------------------------------------------------------------------------
# Extra security tests (builtins, indirect access, paths, recovery, tools)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_sandbox():
    """Build sandboxes with a custom config; every one is shut down afterwards."""
    created = []

    def _make(**overrides):
        mcp_tools = overrides.pop("mcp_tools", None)
        params = dict(
            authorized_imports=["math"],
            allowed_directories=["/tmp/agent"],
            max_execution_time_seconds=2,
            max_memory_mb=128,
        )
        params.update(overrides)
        sb = Sandbox(config=SandboxConfig(**params), mcp_tools=mcp_tools)
        created.append(sb)
        return sb

    yield _make
    for sb in created:
        sb.shutdown()


@pytest.fixture
def files():
    """Create files on the host for the path tests; remove them afterwards."""
    made_files, made_dirs = [], []

    def _make(path, content):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
            made_dirs.append(parent)
        with open(path, "w") as f:
            f.write(content)
        made_files.append(path)
        return path

    yield _make
    for p in made_files:
        try:
            os.remove(p)
        except OSError:
            pass
    for d in made_dirs:
        try:
            os.rmdir(d)
        except OSError:
            pass


# ---- builtin block ---------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "exec(\"print('reached')\")",
        "print(eval('1 + 1'), 'reached')",
        "compile('1', 'x', 'eval')\nprint('reached')",
        "m = __import__('os')\nprint('reached')",
    ],
)
def test_dangerous_builtins_are_blocked(sandbox, code):
    output = sandbox.execute(code)
    assert "reached" not in output
    assert output.strip() != ""  # an error message, not silence


# ---- import block (more forms) --------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "os", "sys", "subprocess", "importlib", "builtins", "ctypes",
        "pathlib", "shutil", "pickle", "multiprocessing", "threading",
        "signal", "socket", "urllib.request", "http.client",
    ],
)
def test_forbidden_modules_are_blocked(sandbox, module):
    output = sandbox.execute(f"import {module}\nprint('reached')")
    assert "reached" not in output


@pytest.mark.parametrize(
    "code",
    [
        "from os import path\nprint('reached')",
        "import math, os\nprint('reached')",
        "import os.path\nprint('reached')",
    ],
)
def test_forbidden_import_forms_are_blocked(sandbox, code):
    assert "reached" not in sandbox.execute(code)


# ---- allowed modules must not leak the blocked ones ------------------------


@pytest.mark.parametrize(
    "code",
    [
        "import random\nrandom._os.getcwd()\nprint('reached')",
        "import collections\ncollections._sys.modules['os'].getcwd()\nprint('reached')",
        "import collections\n"
        "collections.namedtuple.__globals__['_sys'].modules['os'].getcwd()\n"
        "print('reached')",
    ],
)
def test_allowed_modules_do_not_leak_blocked_ones(make_sandbox, code):
    # If the attribute simply does not exist in this Python version, the test
    # passes too: it only proves this particular route is closed.
    sb = make_sandbox(authorized_imports=["math", "random", "collections"])
    assert "reached" not in sb.execute(code)


def test_subclasses_introspection_escape(sandbox):
    code = (
        "subs = ().__class__.__base__.__subclasses__()\n"
        "wrap = [c for c in subs if c.__name__ == '_wrap_close'][0]\n"
        "print('reached', wrap.__init__.__globals__['system'])"
    )
    assert "reached" not in sandbox.execute(code)


# ---- path restrict ----------------------------------------------------------


def test_file_inside_allowlist_is_readable(sandbox, files):
    files("/tmp/agent/_sbx_test_inside.txt", "INSIDE-OK")
    output = sandbox.execute("print(open('/tmp/agent/_sbx_test_inside.txt').read())")
    assert "INSIDE-OK" in output


def test_path_traversal_is_blocked(sandbox, files):
    files("/tmp/_sbx_test_secret.txt", "SECRET-TRAVERSAL")
    output = sandbox.execute(
        "print(open('/tmp/agent/../_sbx_test_secret.txt').read())"
    )
    assert "SECRET-TRAVERSAL" not in output


def test_sibling_directory_with_same_prefix_is_blocked(sandbox, files):
    # "/tmp/agent_evil" starts with "/tmp/agent" but is a different directory.
    files("/tmp/agent_evil/_sbx_test_secret.txt", "SECRET-PREFIX")
    output = sandbox.execute(
        "print(open('/tmp/agent_evil/_sbx_test_secret.txt').read())"
    )
    assert "SECRET-PREFIX" not in output


def test_write_outside_allowlist_is_blocked(sandbox):
    target = "/tmp/_sbx_test_write.txt"
    if os.path.exists(target):
        os.remove(target)
    try:
        sandbox.execute(f"open('{target}', 'w').write('x')")
        assert not os.path.exists(target)
    finally:
        if os.path.exists(target):
            os.remove(target)


def test_symlink_inside_allowlist_cannot_escape(sandbox, files):
    files("/tmp/_sbx_test_target.txt", "SECRET-SYMLINK")
    os.makedirs("/tmp/agent", exist_ok=True)
    link = "/tmp/agent/_sbx_test_link"
    if os.path.lexists(link):
        os.remove(link)
    os.symlink("/tmp/_sbx_test_target.txt", link)
    try:
        output = sandbox.execute(f"print(open('{link}').read())")
    finally:
        os.remove(link)
    assert "SECRET-SYMLINK" not in output


# ---- recovery and state -----------------------------------------------------


def test_sandbox_still_works_after_timeout(sandbox):
    assert "timeout" in sandbox.execute("while True:\n    pass").lower()
    assert "2" in sandbox.execute("print(1 + 1)")


def test_sandbox_still_works_after_memory_limit(sandbox):
    assert "memory" in sandbox.execute("x = bytearray(400 * 1024 * 1024)").lower()
    assert "2" in sandbox.execute("print(1 + 1)")


def test_variables_persist_between_executions(sandbox):
    sandbox.execute("x = 41")
    assert "42" in sandbox.execute("print(x + 1)")


# ---- tool time vs sandbox timeout ------------------------------------------


def _slow_tool():
    time.sleep(3)
    return "tool-done"


def test_tool_time_does_not_count_against_sandbox_timeout(make_sandbox):
    sb = make_sandbox(max_execution_time_seconds=2, mcp_tools={"slow_tool": _slow_tool})
    output = sb.execute("print(slow_tool())")
    assert "tool-done" in output
    assert "timeout" not in output.lower()


def test_sandbox_code_after_a_tool_call_is_still_limited(make_sandbox):
    sb = make_sandbox(max_execution_time_seconds=2, mcp_tools={"slow_tool": _slow_tool})
    output = sb.execute("slow_tool()\nwhile True:\n    pass")
    assert "timeout" in output.lower()

# ---- hardening: private attributes, getattr, frames, environment -----------


@pytest.mark.parametrize(
    "code",
    [
        "import random\ngetattr(random, '_os')\nprint('reached')",
        "from random import _os\nprint('reached')",
        "import random\nprint(vars(random)['_os'], 'reached')",
        "g = (i for i in range(1))\nnext(g)\nprint(g.gi_frame.f_globals, 'reached')",
        "def f():\n    yield 1\ng = f()\nnext(g)\nprint(g.gi_frame.f_back, 'reached')",
        "try:\n    1 / 0\nexcept Exception as e:\n"
        "    print(e.__traceback__.tb_frame.f_globals, 'reached')",
        "print((1).__class__.__bases__, 'reached')",
    ],
)
def test_private_and_frame_access_is_blocked(make_sandbox, code):
    sb = make_sandbox(authorized_imports=["math", "random"])
    assert "reached" not in sb.execute(code)


def test_worker_does_not_inherit_parent_environment(make_sandbox, monkeypatch):
    # Even if some route to the real `os` stays open, no secret should be in it.
    monkeypatch.setenv("SBX_TEST_SECRET", "TOPSECRET-VALUE")
    sb = make_sandbox(authorized_imports=["math", "random"])
    output = sb.execute("import random\nprint('{0._os.environ}'.format(random))")
    assert "TOPSECRET-VALUE" not in output


def test_normal_attribute_and_getattr_use_still_works(sandbox):
    code = (
        "d = {'a': 1}\n"
        "print(getattr(d, 'get')('a'), getattr(d, 'missing', 'dflt'))\n"
        "print(sorted([3, 1, 2], key=lambda x: -x))"
    )
    output = sandbox.execute(code)
    assert "1 dflt" in output
    assert "[3, 2, 1]" in output


def test_attrgetter_route_is_closed(make_sandbox):
    sb = make_sandbox(authorized_imports=["math", "random", "operator"])
    code = (
        "import operator, random\n"
        "operator.attrgetter('_os')(random).getcwd()\n"
        "print('reached')"
    )
    assert "reached" not in sb.execute(code)
