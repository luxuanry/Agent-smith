"""
MCP Client（Section III.1 图示 + Section V.2 第5点）。

沙盒本身要作为一个 MCP client，去连接一个 MCP server
（可能是你们自己的 mcp_tools_mbpp.py / mcp_tools_swebench.py，
也可能是评审时连的"未知 MCP server"——所以这里的逻辑必须是通用的，
不能写死"我知道有哪几个工具"）。

两种连接方式都要支持：
  - stdio: 用子进程启动 `python mcp_tools_mbpp.py`，通过标准输入输出通信
  - HTTP (streamable): 连接一个 URL

=== 你们需要实现的部分（TODO） ===
1. `connect_stdio(command: str)`：启动子进程并建立 MCP session
2. `connect_http(url: str)`：连接远程 HTTP MCP server
3. `discover_tools()`：调用 MCP 协议里的 list_tools，拿到每个工具的
   name / description / 参数 schema
4. `wrap_as_python_functions()`：把每个 MCP 工具包装成一个普通的
   Python 函数，函数内部实际上是通过 MCP 协议调用远程工具、
   再把结果转成字符串返回——这样 sandbox/executor.py 才能直接把它们
   塞进 exec() 的命名空间里给 LLM 调用

推荐用官方 `mcp` Python SDK（pip install mcp），
文档：https://modelcontextprotocol.io/
"""
from __future__ import annotations

from typing import Callable, Dict


class MCPClient:
    def __init__(self):
        self.tools: Dict[str, dict] = {}   # tool_name -> schema (从 server 发现)

    def connect_stdio(self, command: str) -> None:
        """TODO(学生实现): 用 mcp SDK 的 stdio_client 启动子进程并连接。"""
        raise NotImplementedError

    def connect_http(self, url: str) -> None:
        """TODO(学生实现): 用 mcp SDK 的 streamable HTTP client 连接。"""
        raise NotImplementedError

    def discover_tools(self) -> Dict[str, dict]:
        """TODO(学生实现): 调用 MCP list_tools，缓存到 self.tools 并返回。"""
        raise NotImplementedError

    def wrap_as_python_functions(self) -> Dict[str, Callable]:
        """
        TODO(学生实现): 为 self.tools 里的每一个工具生成一个 Python 包装函数。

        例如工具 "read_file" 应该变成一个可以这样调用的函数：
            read_file(filepath="/testbed/src/mail.py", start_line=1, end_line=50)
        函数内部通过 MCP 协议真正调用远程工具，并把结果（通常是字符串）返回。
        """
        raise NotImplementedError
