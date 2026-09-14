"""
沙盒执行器（Section V.2 第1、2点）：Sandbox 类。

职责：
  1. 维护一个执行命名空间（namespace dict），里面预先塞好：
     - 所有 MCP 工具的 Python 包装函数（从 mcp_client.py 动态发现）
     - final_answer() 函数（沙盒自带，不是 MCP 工具！）
  2. 提供 execute(code: str) -> str 方法：
     - 在受限的 builtins / import 环境下 exec(code, namespace)
     - 捕获 stdout（LLM 是靠 print() 看到结果的，不是 return）
     - 超时/内存超限时要能真正终止执行，并返回清晰的错误信息
     - KeyboardInterrupt / SystemExit 不能被这里的 try/except 吞掉
  3. 提供交互式 REPL 模式（`uv run sandbox` 不带任务参数时）

=== 你们需要实现的部分（TODO） ===
"""
from __future__ import annotations

import io
import contextlib
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
        """这是沙盒自带的构造，不是 MCP 工具（见 Section V.2）。"""
        self.final_answer_value = answer
        self.final_answer_called = True

    def _setup_namespace(self) -> None:
        """
        TODO(学生实现):
        - self.namespace["final_answer"] = self._final_answer
        - 把 self.mcp_tools 里的每个工具函数也塞进 self.namespace
        - 塞入 build_restricted_builtins() 得到的受限 builtins
        """
        raise NotImplementedError

    def execute(self, code: str) -> str:
        """
        TODO(学生实现): 核心执行逻辑。

        伪代码：
            self._import_guard.install()
            stdout_buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout_buffer):
                    # 用 signal.alarm / 子进程 实现超时，
                    # 用 resource.setrlimit 实现内存限制
                    exec(code, self.namespace)
            except (KeyboardInterrupt, SystemExit):
                raise  # 绝对不能吞掉这两个异常！
            except TimeoutError:
                return "[TIMEOUT] 代码执行超过 {}s，已被终止".format(
                    self.config.max_execution_time_seconds
                )
            except Exception as e:
                return f"[ERROR] {type(e).__name__}: {e}"
            finally:
                self._import_guard.uninstall()
            return stdout_buffer.getvalue()
        """
        raise NotImplementedError

    def run_repl(self) -> None:
        """
        交互式沙盒（`uv run sandbox`，不带任务文件时）。
        Section V.2 第1点要求：
          - 循环读取用户输入的一行/一段代码
          - 用 self.execute() 跑
          - 打印结果，回到提示符
          - 遇到 "exit" 命令或者 EOF (Ctrl+D) 时干净退出

        TODO(学生实现)
        """
        raise NotImplementedError
