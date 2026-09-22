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
