"""
MBPP Agent CLI (Section V.3 point 1).

Usage:
    uv run python -m agent_mbpp --task-file ../cache/mbpp_task.json \\
        --output ../cache/mbpp_solution.json \\
        --model-name "model/name" --provider-url "https://provider.api/v1"

STAGE 0 (current): no MCP server — the sandbox only has final_answer(),
and the tests are given to the LLM in the task text.
  TODO(stage 1): connect mcp_tools_mbpp.py, generate the sandbox manual, enforce limits.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from common.agent_loop import AgentLoop, build_system_prompt
from common.env import load_env_file
from common.llm_provider import LLMProvider
from common.models import MBPPTaskInput, SandboxConfig, SolutionOutput
from sandbox.executor import Sandbox

# Hard limits — Section VI.1.1 (only MAX_ITERATIONS is enforced in stage 0)
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


def build_user_task(task: MBPPTaskInput) -> str:
    parts = [
        f"Task: {task.task_definition}",
        f"Function signature: {task.function_definition}",
    ]
    if task.test_imports:
        parts.append("Test imports:\n" + "\n".join(task.test_imports))
    parts.append("Tests:\n" + "\n".join(task.test_list))
    return "\n".join(parts)


def main(argv=None) -> None:
    args = parse_args(argv)
    load_env_file(".env")
    start = time.perf_counter()
    task_id = "unknown"

    try:
        with open(args.task_file, encoding="utf-8") as f:
            task = MBPPTaskInput(**json.load(f))
        task_id = str(task.task_id)

        provider = LLMProvider(args.model_name, args.provider_url, args.api_key_env)
        sandbox = Sandbox(config=SandboxConfig())
        system_prompt = build_system_prompt(sandbox_manual="", benchmark="mbpp")

        agent = AgentLoop(
            llm_provider=provider,
            sandbox=sandbox,
            system_prompt=system_prompt,
            max_iterations=MAX_ITERATIONS,
            max_input_tokens=MAX_INPUT_TOKENS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        result = agent.run(task_id=task_id, benchmark="mbpp", user_task=build_user_task(task))
    except Exception as e:
        result = SolutionOutput(
            task_id=task_id,
            benchmark="mbpp",
            success=False,
            solution="",
            iterations=0,
            total_requests=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_time_seconds=time.perf_counter() - start,
            error=f"{type(e).__name__}: {e}",
        )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"success={result.success} iterations={result.iterations} error={result.error}")


if __name__ == "__main__":
    main(sys.argv[1:])
