"""
MBPP Agent CLI（Section V.3 第1点）。

用法（对照 PDF）：
    uv run python -m agent_mbpp --task-file ../cache/mbpp_task.json \\
        --output ../cache/mbpp_solution.json \\
        --model-name "model/name" --provider-url "https://provider.api/v1"

=== 你们需要实现的部分（TODO） ===
"""
from __future__ import annotations

import argparse
import json
import sys

from common.models import MBPPTaskInput, SandboxConfig, SolutionOutput
from common.llm_provider import LLMProvider
from common.agent_loop import AgentLoop, build_system_prompt
from sandbox.executor import Sandbox
from sandbox.mcp_client import MCPClient
from sandbox.manual import generate_sandbox_manual

# Hard limits — Section VI.1.1
MAX_ITERATIONS = 10
MAX_INPUT_TOKENS = 6_000
MAX_OUTPUT_TOKENS = 1_500
TIMEOUT_SECONDS = 120


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_mbpp")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    """
    TODO(学生实现):
    1. 解析参数，读取 task-file，解析成 MBPPTaskInput
    2. 用 --provider-url --model-name --api-key-env 构造 LLMProvider
    3. 启动 MCPClient，连接 mcp_tools_mbpp.py（stdio: "python mcp_tools_mbpp.py"）
    4. discover_tools() + wrap_as_python_functions()，塞进 Sandbox
    5. generate_sandbox_manual() 生成手册，build_system_prompt() 拼装完整提示词
    6. 构造 AgentLoop(...)，传入 MAX_ITERATIONS 等 hard limits
    7. 调用 agent_loop.run(task_id=..., benchmark="mbpp", user_task=...)
    8. 把返回的 SolutionOutput 写入 --output 指定的 json 文件
       （记得处理异常——任何崩溃都要被 try/except 兜住，
       写出 success=False + error 字段，而不是让程序直接崩溃）
    """
    args = parse_args(argv)

    with open(args.task_file) as f:
        task = MBPPTaskInput(**json.load(f))

    raise NotImplementedError("TODO: 按上面的步骤实现 main()")


if __name__ == "__main__":
    main(sys.argv[1:])
