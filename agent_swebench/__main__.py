"""
SWE-bench Agent CLI (Section V.4 point 1).

Usage:
    uv run python -m agent_swebench --task-file ../cache/swebench_task.json \
        --output ../cache/swebench_solution.json \
        --model-name "model/name" --provider-url "https://provider.api/v1"

Mirrors agent_mbpp/__main__.py: same AgentLoop / build_system_prompt /
SolutionOutput plumbing (see that file for the parts that are identical).
What's different here is the Docker container lifecycle -- Plan B: the
sandbox/agent loop stay on the host, mcp_tools_swebench.py bridges into the
task's container via `docker exec` instead of running inside it. So this
file additionally has to:
  1. pull the task's docker_image and start it detached
  2. tell mcp_tools_swebench.py which container to exec into, and where the
     task file (eval_script etc.) is, via environment variables -- same
     pattern as MBPP_TASK_FILE in agent_mbpp/__main__.py
  3. always clean the container up afterwards (stop + rm), success or not --
     exam_swebench.sh grades "container cleanup" as its own step
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from common.agent_loop import AgentLoop, build_system_prompt
from common.env import load_env_file
from common.llm_provider import LLMProvider
from common.models import SandboxConfig, SolutionOutput, SWEBenchTaskInput
from sandbox.executor import Sandbox
from sandbox.manual import generate_sandbox_manual
from sandbox.mcp_client import MCPClient

# Hard limits -- Section VI.1.2
MAX_ITERATIONS = 30
MAX_INPUT_TOKENS = 300_000
MAX_OUTPUT_TOKENS = 10_000
TIMEOUT_SECONDS = 900

# Env vars mcp_tools_swebench.py reads to know which task/container it is
# serving -- must match the constants of the same name over there.
TASK_FILE_ENV = "SWEBENCH_TASK_FILE"
CONTAINER_NAME_ENV = "SWEBENCH_CONTAINER_NAME"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_swebench")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    return parser.parse_args(argv)


def build_user_task(task: SWEBenchTaskInput) -> str:
    parts = []
    if task.repo:
        parts.append(f"Repository: {task.repo}")
    parts.append(f"Instance: {task.instance_id}")
    parts.append(f"Issue:\n{task.problem_statement}")
    if task.hints_text:
        parts.append(f"Hints:\n{task.hints_text}")
    return "\n\n".join(parts)


def _container_name(instance_id: str) -> str:
    """Docker container names must match [a-zA-Z0-9][a-zA-Z0-9_.-]*.
    SWE-bench instance_ids (e.g. 'sympy__sympy-14711') already satisfy that;
    we just namespace them so they don't collide with unrelated containers
    on the host."""
    return f"agent-smith-{instance_id}"


def _docker_pull(image: str) -> None:
    subprocess.run(["docker", "pull", image], check=True)


def _docker_start_container(image: str, name: str) -> None:
    # Best-effort: remove any stale container left over from a previous
    # crashed run before starting a fresh one under the same name.
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        ["docker", "run", "-dit", "--name", name, image, "/bin/bash"],
        check=True,
    )


def _docker_cleanup(name: str) -> None:
    """Stop + remove the task container. Best-effort and must never raise --
    this runs after we've already written the solution to disk, and a
    cleanup failure should never cost us a result we already have."""
    subprocess.run(["docker", "stop", name], capture_output=True)
    subprocess.run(["docker", "rm", name], capture_output=True)


def main(argv=None) -> None:
    args = parse_args(argv)
    load_env_file(".env")
    start = time.perf_counter()
    task_id = "unknown"
    mcp_client = MCPClient()
    container_name: str | None = None

    try:
        with open(args.task_file, encoding="utf-8") as f:
            task = SWEBenchTaskInput(**json.load(f))
        task_id = task.instance_id

        container_name = _container_name(task.instance_id)
        _docker_pull(task.docker_image)
        _docker_start_container(task.docker_image, container_name)

        # mcp_tools_swebench.py needs to know which container to `docker
        # exec` into, and where the task file (eval_script, repo, ...) is --
        # same idea as MBPP_TASK_FILE in agent_mbpp/__main__.py.
        os.environ[TASK_FILE_ENV] = args.task_file
        os.environ[CONTAINER_NAME_ENV] = container_name

        mcp_client.connect_stdio("python mcp_tools_swebench.py")
        mcp_client.discover_tools()
        wrapped_tools = mcp_client.wrap_as_python_functions()

        sandbox_manual = generate_sandbox_manual(mcp_client.tools)

        provider = LLMProvider(args.model_name, args.provider_url, args.api_key_env)
        sandbox = Sandbox(config=SandboxConfig(), mcp_tools=wrapped_tools)
        system_prompt = build_system_prompt(sandbox_manual=sandbox_manual, benchmark="swebench")

        agent = AgentLoop(
            llm_provider=provider,
            sandbox=sandbox,
            system_prompt=system_prompt,
            max_iterations=MAX_ITERATIONS,
            max_input_tokens=MAX_INPUT_TOKENS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        result = agent.run(task_id=task_id, benchmark="swebench", user_task=build_user_task(task))
    except Exception as e:
        result = SolutionOutput(
            task_id=task_id,
            benchmark="swebench",
            success=False,
            solution="",
            iterations=0,
            total_requests=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_time_seconds=time.perf_counter() - start,
            error=f"{type(e).__name__}: {e}",
        )

    # Write the result BEFORE attempting any cleanup, so a cleanup failure
    # (MCP subprocess or Docker) can never cause us to lose a task result we
    # already have.
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"success={result.success} iterations={result.iterations} error={result.error}")

    try:
        # Shuts down the MCP session, the mcp_tools_swebench.py subprocess,
        # and the background event-loop thread.
        mcp_client.close()
    except Exception as e:
        print(f"[warning] MCP client cleanup failed: {type(e).__name__}: {e}", file=sys.stderr)

    if container_name is not None:
        _docker_cleanup(container_name)


if __name__ == "__main__":
    main(sys.argv[1:])
