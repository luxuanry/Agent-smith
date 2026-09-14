"""
沙盒 CLI 入口（Section V.2 第1点）。

对应 pyproject.toml 里的:
    [project.scripts]
    sandbox = "sandbox.cli:main"

用法（PDF 里给的example）：
    uv run sandbox                                             # 交互式REPL
    uv run sandbox sandbox_template.json                       # 自定义配置
    uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
    uv run sandbox --mcp-server <URL>

=== 你们需要实现的部分（TODO） ===
"""
from __future__ import annotations

import argparse
import json
import sys

from common.models import SandboxConfig
from sandbox.executor import Sandbox
from sandbox.mcp_client import MCPClient


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sandbox")
    parser.add_argument("config_file", nargs="?", default=None, help="sandbox_template.json 路径")
    parser.add_argument("--mcp-stdio", dest="mcp_stdio", default=None, help='例如 "python mcp_tools_mbpp.py"')
    parser.add_argument("--mcp-server", dest="mcp_server", default=None, help="MCP HTTP server URL")
    return parser.parse_args(argv)


def load_config(config_file) -> SandboxConfig:
    if config_file is None:
        return SandboxConfig()
    with open(config_file) as f:
        data = json.load(f)
    return SandboxConfig(**data)


def main(argv=None) -> None:
    """
    TODO(学生实现):
    1. 解析参数（已经帮你搭好 parse_args）
    2. 加载 SandboxConfig（已经帮你搭好 load_config）
    3. 如果传了 --mcp-stdio 或 --mcp-server，用 MCPClient 连接并
       discover_tools() + wrap_as_python_functions()
    4. 用得到的 config + mcp_tools 构造 Sandbox 实例
    5. 调用 sandbox.run_repl() 进入交互模式

    别忘了：Ctrl+D (EOF) 或输入 "exit" 要能干净退出。
    """
    args = parse_args(argv)
    config = load_config(args.config_file)

    mcp_tools = {}
    # TODO: 根据 args.mcp_stdio / args.mcp_server 连接 MCP，填充 mcp_tools

    sandbox = Sandbox(config=config, mcp_tools=mcp_tools)
    sandbox.run_repl()


if __name__ == "__main__":
    main(sys.argv[1:])
