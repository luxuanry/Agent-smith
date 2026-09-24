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
from sandbox.manual import generate_sandbox_manual
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
    args = parse_args(argv)
    if args.mcp_stdio and args.mcp_server:
        sys.exit("error: --mcp-stdio and mcp-server cant be run together")
    try:
        config = load_config(args.config_file)
    except FileNotFoundError:
        sys.exit(f"error: cant find the file: {args.config_file}")
    except json.JSONDecodeError as e:
        sys.exit(f"error: JSON error: {e}")
    except Exception as e:
        sys.exit(f"error: config error: {e}")
    
    # stdio: we launch the server ourselves. HTTP: it must already be running.
    mcp_client = MCPClient()
    mcp_tools = {}
    if args.mcp_stdio or args.mcp_server:
        try:
            if args.mcp_stdio:
                mcp_client.connect_stdio(args.mcp_stdio)
            else:
                mcp_client.connect_http(args.mcp_server)
            mcp_client.discover_tools()
        except Exception as e:
            mcp_client.close()
            sys.exit(f"error: cant connect to MCP server: {type(e).__name__}: {e}")
        mcp_tools = mcp_client.wrap_as_python_functions()
        print(generate_sandbox_manual(mcp_client.tools))

    try:
        sandbox = Sandbox(config=config, mcp_tools=mcp_tools)
        try:
            sandbox.run_repl()
        finally:
            sandbox.shutdown()
    finally:
        mcp_client.close()


if __name__ == "__main__":
    main(sys.argv[1:])
