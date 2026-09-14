"""
Agent Loop 核心（Section V.1）：Thought -> Code -> Observation 循环。

这是整个项目的心脏。跑起来大概是这样：

    messages = [system_prompt, user_task]
    for step in range(max_iterations):
        llm_response = llm_provider.generate(messages, stop_sequences=[...])
        extraction = extract_python_code_block(llm_response.text)

        if extraction.code is None:
            observation = "❌ 没有找到代码块，请用 ```python ... ``` 包裹你的代码"
        else:
            observation = sandbox.execute(extraction.code)   # 见 sandbox/executor.py
            if sandbox.final_answer_called:
                return build_solution_output(success=True, ...)

        messages.append({"role": "assistant", "content": llm_response.text})
        messages.append({"role": "user", "content": f"Observation:\n{observation}"})

        # 记得检查 token / 时间限制有没有超（Section VI.1）

=== 你们需要实现的部分（TODO） ===
1. `build_system_prompt()`：这是全项目最重要的手写内容之一。
   系统提示词要包含：
     - 沙盒手册（工具列表，从 MCP server 动态生成，见 sandbox/manual.py）
     - Thought/Code/Observation 的格式示例
     - 至少一个完整的"正确推理"示例（few-shot example）
2. `AgentLoop.run()`：真正的循环逻辑（伪代码已经写在上面的 docstring 里）
3. 累计 token 计数、判断是否超过 hard limits（Section VI.1），
   超限时要优雅地终止并返回 error 字段，而不是让程序崩溃
4. 处理 KeyboardInterrupt / SystemExit（沙盒那边必须让它们正常向上抛，
   这里的循环也不能吞掉它们）
"""
from __future__ import annotations

import time
from typing import List, Optional

from common.llm_provider import LLMProvider
from common.code_extraction import extract_python_code_block
from common.models import SolutionOutput, StepMetrics


class AgentLoop:
    """MBPP 和 SWE-bench 的 agent 都应该复用（或继承）这个类，
    区别只在于：system prompt 的内容、task 的输入格式、
    以及 sandbox 连接的是哪个 MCP server（mcp_tools_mbpp.py 还是
    mcp_tools_swebench.py）。
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        sandbox,  # sandbox.executor.Sandbox 实例，见 sandbox/executor.py
        system_prompt: str,
        max_iterations: int,
        max_input_tokens: int,
        max_output_tokens: int,
        timeout_seconds: int,
    ):
        self.llm_provider = llm_provider
        self.sandbox = sandbox
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds

    def run(self, task_id: str, benchmark: str, user_task: str) -> SolutionOutput:
        """
        TODO(学生实现): 按上面 docstring 里的伪代码实现完整循环。

        提示：
        - steps: List[StepMetrics] = [] 用来累积每一步的记录
        - total_input_tokens / total_output_tokens 累加后要和 hard limit 比较
        - 循环正常结束（LLM 调用了 final_answer）或者达到 max_iterations /
          超过 token 限制 / 超时，都要返回一个 SolutionOutput，
          而不是抛异常让整个程序崩掉
        """
        raise NotImplementedError("TODO: 实现 Thought -> Code -> Observation 循环")


def build_system_prompt(sandbox_manual: str, benchmark: str) -> str:
    """
    TODO(学生实现): 拼装完整的 system prompt。

    必须包含（Section V.1 明确要求）：
    1. 清晰的工具文档（直接嵌入 sandbox_manual，见 sandbox/manual.py）
    2. Thought / Code / Observation 的输出格式示例
    3. 至少一个完整的、有效的推理循环示例（few-shot）

    小技巧：先假装自己是 LLM，手动把这个任务做一遍，
    你手动做的那个过程，就应该是这份 prompt 里的示例。
    """
    raise NotImplementedError("TODO: 编写你的 system prompt 模板")
