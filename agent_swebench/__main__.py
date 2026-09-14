"""
SWE-bench Agent CLI（Section V.4 第1点）。

用法（对照 PDF）：
    uv run python -m agent_swebench --task-file ../cache/swebench_task.json \\
        --output ../cache/swebench_solution.json \\
        --model-name "model/name" --provider-url "https://provider.api/v1"

=== 你们需要实现的部分（TODO） ===
和 agent_mbpp/__main__.py 结构几乎一样，区别是：
- 读取的是 SWEBenchTaskInput（多了 docker_image / eval_script / repo 等字段）
- 连接的是 mcp_tools_swebench.py（9个工具全部要能用）
- 在跑 agent 之前，要先把 docker_image pull 下来、启动容器
  （挂载 testbed 路径，具体挂载方式取决于你们选的架构——
  沙盒在容器内 vs 沙盒在宿主机桥接进容器，见 Section V.4）
- 跑完之后要记得清理容器（PDF明确要求"you are responsible to clean it"）
"""
from __future__ import annotations

import argparse
import json
import sys

from common.models import SWEBenchTaskInput

# Hard limits — Section VI.1.2
MAX_ITERATIONS = 30
MAX_INPUT_TOKENS = 300_000
MAX_OUTPUT_TOKENS = 10_000
TIMEOUT_SECONDS = 900


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_swebench")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    """
    TODO(学生实现): 参照 agent_mbpp/__main__.py 的步骤，
    加上 Docker 容器的启动/挂载/清理逻辑。

    建议先跑通 sympy__sympy-14711 这种简单任务，
    不要一开始就上最难的 instance。
    """
    args = parse_args(argv)

    with open(args.task_file) as f:
        task = SWEBenchTaskInput(**json.load(f))

    raise NotImplementedError("TODO: 按上面的步骤实现 main()（含 Docker 生命周期管理）")


if __name__ == "__main__":
    main(sys.argv[1:])
