"""
沙盒安全机制（Section V.2 第3、4点）。

这是整个项目里"安全 review"会重点检查的部分。四个维度：
  1. import 限制 —— 只有白名单里的模块能被 import
  2. 文件路径限制 —— 只能访问 allowed_directories 里的路径
  3. 执行超时 —— 用 signal.alarm 或者子进程 + timeout
  4. 内存限制 —— 用 resource.setrlimit(RLIMIT_AS, ...)（仅 Unix）

只能用标准库实现（PDF 明确禁止 RestrictedPython 等第三方库）。

=== 你们需要实现的部分（TODO） ===
"""
from __future__ import annotations

import builtins
from typing import Iterable, Set


class ImportGuard:
    """拦截 __import__，只放行白名单里的模块。"""

    def __init__(self, authorized_imports: Iterable[str]):
        self.authorized: Set[str] = set(authorized_imports)
        self._real_import = builtins.__import__

    def _is_authorized(self, module_name: str) -> bool:
        """
        TODO(学生实现): 判断 module_name 是否在白名单里。
        注意 authorized_imports 里可能有 "math.*" 这种通配符写法，
        代表 math 的所有子模块都允许，需要自己处理这个匹配逻辑。
        """
        raise NotImplementedError

    def guarded_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        """
        TODO(学生实现):
        - 如果 self._is_authorized(name) 为 False，抛出 ImportError，
          并给出清晰的错误信息（例如 "模块 'os' 不在白名单内"）
        - 否则调用 self._real_import(...) 正常导入
        """
        raise NotImplementedError

    def install(self) -> None:
        builtins.__import__ = self.guarded_import

    def uninstall(self) -> None:
        builtins.__import__ = self._real_import


def build_restricted_builtins() -> dict:
    """
    TODO(学生实现): 返回一份"安全"的 builtins 字典，
    去掉或者重写危险的内置函数，例如：
      - eval / exec 本身要不要放开？（沙盒本身要用 exec 执行代码，
        但不代表要把 exec 暴露给"沙盒里的代码"再去嵌套调用）
      - open() 需要包一层，检查路径是否在 allowed_directories 内
      - __import__ 由上面的 ImportGuard 接管
      - os / sys / subprocess 等模块本身不在白名单里，自然就 import 不了，
        但要想清楚：如果某个已经 import 好的模块间接暴露了这些能力，
        要不要也拦截？

    思路提示（Section V.2 的"Think about it"框）：
    考虑清楚未受信任的代码到底应该跑在你的主进程里，还是单独的子进程/线程里，
    这会决定你在这里要做多少防御，以及超时怎么真正"杀死"一段跑飞的代码。
    """
    raise NotImplementedError


def check_path_allowed(path: str, allowed_directories: Iterable[str]) -> bool:
    """
    TODO(学生实现): 判断 path 是否落在 allowed_directories 中的某一个目录内。
    注意处理 ../ 这种路径穿越攻击 —— 用 os.path.realpath() 规范化之后再比较。
    """
    raise NotImplementedError
