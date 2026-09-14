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
    return Sandbox(config=config)


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


# TODO: 加更多测试 —— network block / memory limit / MCP协议相关
