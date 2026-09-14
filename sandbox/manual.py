"""
沙盒手册（Sandbox Manual）—— Section V.2 第6点。

这份"手册"就是塞进 system prompt 里、让 LLM 知道"有哪些工具可以用、
怎么用"的那部分文字。要求是**动态生成**：连不同的 MCP server，
手册内容要自动变化，不能写死。

=== 你们需要实现的部分（TODO） ===
"""
from __future__ import annotations

from typing import Dict


def generate_sandbox_manual(tool_schemas: Dict[str, dict]) -> str:
    """
    TODO(学生实现):
    输入: MCP server discover_tools() 返回的 {tool_name: schema} 字典
    输出: 一段人类/LLM可读的文档字符串，例如：

        Available tools:

        - read_file(filepath: str, start_line: int, end_line: int) -> str
          Read the content of a file with line numbers.

        - search_code(pattern: str, file_pattern: str) -> str
          Perform a grep-like search in the codebase.

        ...

    提示：MCP 的 tool schema 通常是 JSON Schema 格式，
    里面有 name / description / inputSchema（参数名+类型）。
    """
    raise NotImplementedError("TODO: 从 tool_schemas 生成人类可读的手册文本")
