"""
代码提取层（Section V.1，"Extract LLM-generated Python code"）。

LLM 的回复是一整段文字，比如：

    我先看一下这个函数的定义。
    ```python
    result = search_code("is_valid_email")
    print(result)
    ```
    <end_code>

我们需要从这段文字里，把 ```python ... ``` 之间的代码抠出来，
变成一段真正可以喂给 exec() 的 Python 代码字符串。

=== 你们需要实现的部分（TODO） ===
1. `extract_python_code_block()`：处理最主要的格式——```python ... ```
2. 至少处理 PDF 里提到的另外几种非 Python 格式之一
   （XML tool call / JSON tool call / ReAct 格式），把它们转换成
   等价的 Python 函数调用字符串。
   例：ReAct 格式 "Action: read_file / Action Input: {...}"
       转换成 -> 'read_file(filepath="...")'
3. 处理"没找到任何代码块"的情况——不要让程序崩溃，
   而是返回一个清晰的错误信息，反馈给 LLM（这是 PDF 里明确要求的）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractionResult:
    code: Optional[str]          # 抽取出的可执行 Python 代码；None 表示没找到
    raw_llm_output: str          # LLM 的原始输出（要存进 StepMetrics.llm_output）
    warning: Optional[str] = None  # 例如"代码块格式不规范，但仍尝试解析"


_PY_BLOCK_RE = re.compile(r"```python\s*(.*?)```", re.DOTALL)


def extract_python_code_block(llm_text: str) -> ExtractionResult:
    """处理最基本情况：```python ... ``` 代码块。"""
    match = _PY_BLOCK_RE.search(llm_text)
    if match:
        return ExtractionResult(code=match.group(1).strip(), raw_llm_output=llm_text)

    # TODO: 在这里依次尝试其他格式：
    #   - XML: <invoke name="...">...</invoke>
    #   - JSON/Hermes: <tool_call>{"name": ..., "arguments": {...}}</tool_call>
    #   - ReAct: Action: xxx / Action Input: {...}
    # 每种格式都应该转换成等价的 Python 函数调用字符串。

    return ExtractionResult(
        code=None,
        raw_llm_output=llm_text,
        warning="未能在模型输出中找到任何合法的代码块（Python/XML/JSON/ReAct 均未匹配）",
    )
