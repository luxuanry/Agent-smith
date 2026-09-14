"""
MCP Server for SWE-bench tasks (Section V.4 + V.5).

这个文件必须放在仓库**根目录**（PDF明确要求）。
必须实现 Section V.5 里全部9个工具，评审会**独立测试**这些工具
（不只是在agent里跑一遍，而是单独调用检查输出格式）。

=== 你们需要实现的部分（TODO） ===

用官方 `mcp` Python SDK，大致结构：

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("swebench-tools")

    # ---- 文件系统类 ----
    @mcp.tool()
    def read_file(filepath: str, start_line: int, end_line: int) -> str:
        '''Read file content with line numbers, like `cat -n`.'''
        raise NotImplementedError

    @mcp.tool()
    def edit_file(filepath: str, old_str: str, new_str: str) -> str:
        '''Replace an exact string in a file with a new string.'''
        raise NotImplementedError

    @mcp.tool()
    def list_files(directory: str, pattern: str) -> str:
        '''List files in a directory matching a pattern.'''
        raise NotImplementedError

    # ---- 代码搜索类 ----
    @mcp.tool()
    def search_code(pattern: str, file_pattern: str) -> str:
        '''Grep-like search. Output format:
        /absolute/path/to/file.py:<line_number> <line_content>
        '''
        raise NotImplementedError

    @mcp.tool()
    def search_function_or_class_definition_in_code(name: str) -> str:
        '''Find the definition of a function or class.'''
        raise NotImplementedError

    @mcp.tool()
    def find_references(name: str, filepath: str, line: int) -> str:
        '''Find all usages of a symbol.'''
        raise NotImplementedError

    # ---- 执行类 ----
    @mcp.tool()
    def run_tests() -> str:
        '''Execute the evaluation script (eval_script from SWEBenchTaskInput).'''
        raise NotImplementedError

    @mcp.tool()
    def get_patch() -> str:
        '''Return `git -c core.fileMode=false diff` from the repo.'''
        raise NotImplementedError

    @mcp.tool()
    def run_command(command: str, workdir: str) -> str:
        '''Run a shell command, return stdout/stderr/exit code.'''
        raise NotImplementedError

    if __name__ == "__main__":
        mcp.run()

提醒：
- 输出格式必须严格按 PDF Section V.5 的规定（评审会检查格式）
- 这些工具运行在 Docker 容器里 or 桥接进容器 —— 见 Section V.4，
  自己决定架构（两种都可以，但要想清楚 testbed 路径怎么挂载）
"""

# TODO: 在这里用 mcp SDK 实现全部9个工具
raise NotImplementedError("TODO: 实现 mcp_tools_swebench.py")
