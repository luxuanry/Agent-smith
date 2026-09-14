"""
MCP Server for MBPP tasks (Section V.3).

这个文件必须放在仓库**根目录**（PDF明确要求）。
运行方式（被 sandbox 通过 stdio 启动）：
    python mcp_tools_mbpp.py

=== 你们需要实现的部分（TODO） ===
MBPP 相对简单，最起码要有一个 run_tests 工具。
用官方 `mcp` Python SDK 搭 server，大致长这样（伪代码，具体API请查
https://modelcontextprotocol.io/ 的Python SDK文档）：

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("mbpp-tools")

    @mcp.tool()
    def run_tests() -> str:
        '''Execute the MBPP test suite against the current solution.'''
        # TODO: 实际执行测试逻辑，返回通过/失败信息
        raise NotImplementedError

    if __name__ == "__main__":
        mcp.run()  # 默认 stdio transport；如果要HTTP，参考SDK文档换transport
"""

# TODO: 在这里用 mcp SDK 实现你的 MBPP 工具（至少要有 run_tests）
raise NotImplementedError("TODO: 实现 mcp_tools_mbpp.py")
