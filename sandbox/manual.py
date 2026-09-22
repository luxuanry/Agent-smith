"""
Sandbox manual (Section V.2 point 6).

This turns the tool schemas discovered from an MCP server into a
human-readable block of text that gets embedded in the system prompt, so
the LLM actually knows which tools exist and how to call them. It must be
generated DYNAMICALLY from whatever MCP server we're connected to — if we
swap in a different server, this text should automatically reflect the new
set of tools, never be hardcoded.

Input: the `tools` dict returned by MCPClient.discover_tools(), i.e.
{tool_name: Tool} where Tool is the MCP SDK's Tool object with
.name, .description and .inputSchema (a JSON Schema dict).
"""
from __future__ import annotations

from typing import Dict

_JSON_TYPE_TO_PY = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def generate_sandbox_manual(tools: Dict[str, object]) -> str:
    if not tools:
        return "(no extra tools connected)"

    lines = ["Available tools:", ""]

    for name, tool in tools.items():
        schema = getattr(tool, "inputSchema", None) or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        params = []
        for prop_name, prop_schema in properties.items():
            py_type = _JSON_TYPE_TO_PY.get(prop_schema.get("type"), "Any")
            if prop_name in required:
                params.append(f"{prop_name}: {py_type}")
            else:
                params.append(f"{prop_name}: {py_type} = None")

        signature = f"{name}({', '.join(params)})"
        description = (getattr(tool, "description", "") or "").strip()

        lines.append(f"- {signature}")
        for desc_line in description.splitlines():
            desc_line = desc_line.strip()
            if desc_line:
                lines.append(f"  {desc_line}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
