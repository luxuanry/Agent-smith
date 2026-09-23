"""
A throwaway MCP server used only for testing (not part of the project).

Its tools have nothing to do with MBPP or SWE-bench: if the sandbox can
discover them, describe them in the manual and call them, then nothing in
our code is hardcoded to our own tool names -- which is what the evaluation
checks by plugging in an MCP server we have never seen.

Run it like our real servers:
    uv run sandbox --mcp-stdio "python fake_mcp_server.py"
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fake-tools")


@mcp.tool()
def shout(text: str) -> str:
    """Return the given text in upper case with an exclamation mark."""
    return text.upper() + "!"


@mcp.tool()
def add_numbers(a: int, b: int) -> str:
    """Add two integers and return the result."""
    return f"{a} + {b} = {a + b}"


@mcp.tool()
def favourite_colour() -> str:
    """Return this server's favourite colour. Takes no arguments."""
    return "teal"


if __name__ == "__main__":
    mcp.run()
