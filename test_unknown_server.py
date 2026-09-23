"""Check that the sandbox works with an MCP server it has never seen."""
import sys

from sandbox.executor import Sandbox
from sandbox.manual import generate_sandbox_manual
from sandbox.mcp_client import MCPClient
from common.models import SandboxConfig

client = MCPClient()
client.connect_stdio(f"{sys.executable} fake_mcp_server.py")
client.discover_tools()

print("1. DISCOVERED TOOLS:", sorted(client.tools))
print()
print("2. GENERATED MANUAL (this text goes into the system prompt):")
print(generate_sandbox_manual(client.tools))
print()

sandbox = Sandbox(config=SandboxConfig(), mcp_tools=client.wrap_as_python_functions())
print("3. CALLING THE TOOLS FROM INSIDE THE SANDBOX:")
for code in [
    'print(shout(text="hello from the sandbox"))',
    'print(add_numbers(a=2, b=40))',
    'print(favourite_colour())',
    'print(run_tests(code="whatever"))',  # must NOT exist here
]:
    print(f"   >>> {code}")
    print(f"   {sandbox.execute(code).strip()}")

sandbox.shutdown()
client.close()
