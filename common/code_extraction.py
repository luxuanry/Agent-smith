"""
Code extraction layer (Section V.1, "Extract LLM-generated Python code").

The LLM's response is a block of text, for example:

    Let me check the definition of this function first.
```python
    result = search_code("is_valid_email")
    print(result)
```
    <end_code>

We need to pull out the executable code from this text, across
different formats the LLM might produce, and turn it into a single
Python code string that can be handed to the sandbox for execution.

Supported formats:
1. Python code blocks (primary) -- ```python ... ``` <end_code>
2. XML tool calls (Anthropic-style) -- <invoke name="..."><parameter>...</parameter></invoke>
3. JSON/Hermes tool calls -- <tool_call>{"name": "...", "arguments": {...}}</tool_call>
4. ReAct format -- Action: tool_name / Action Input: {...}

Non-Python formats are converted into equivalent Python function call
strings, e.g. an XML/JSON/ReAct call to read_file becomes:
    read_file(filepath="/testbed/file.py")

If a single response mixes multiple formats (e.g. explanatory text
followed by a tool call), the extracted snippets are concatenated in
the order they appear in the original text.

If no valid code/call is found, this does not crash -- it returns a
clear warning that can be fed back to the LLM so it can retry with a
correct format (explicitly required by the subject PDF).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExtractionResult:
    code: Optional[str]          # extracted executable Python code; None if nothing found
    raw_llm_output: str          # raw LLM output (stored in StepMetrics.llm_output)
    warning: Optional[str] = None  # e.g. "malformed code block, attempted parsing anyway"


# ---------------------------------------------------------------------------
# Regex patterns for each format
# ---------------------------------------------------------------------------

_PY_BLOCK_RE = re.compile(r"```python\s*(.*?)```\s*(?:<end_code>)?", re.DOTALL)

_XML_INVOKE_RE = re.compile(r'<invoke name="([^"]+)">(.*?)</invoke>', re.DOTALL)
_XML_PARAM_RE = re.compile(r'<parameter name="([^"]+)">(.*?)</parameter>', re.DOTALL)

_JSON_TOOLCALL_RE = re.compile(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', re.DOTALL)

# The lookahead accepts either a newline followed by another
# Action/Observation block, OR the end of the string directly
# (no trailing newline required in the latter case).
_REACT_RE = re.compile(
    r'Action:\s*(\S+)\s*\nAction Input:\s*(\{.*?\})(?=\n(?:Action:|Observation:)|$)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

def _coerce(val: str) -> Any:
    """Try to recover the real type of an XML parameter value
    (number / bool / list / dict, etc). Falls back to the raw string
    if that fails.
    """
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return val


def _call_to_python(name: str, arguments: dict) -> str:
    """Convert a (function name, arguments dict) pair into a single
    line of equivalent Python function-call code. Uses repr() instead
    of manual string building to avoid quoting/escaping bugs.
    """
    args_str = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    return f"{name}({args_str})"


def _extract_xml_calls(text: str) -> list[tuple[int, str]]:
    """Extract Anthropic-style XML tool calls."""
    results = []
    for m in _XML_INVOKE_RE.finditer(text):
        name, body = m.group(1), m.group(2)
        args = {
            p.group(1): _coerce(p.group(2).strip())
            for p in _XML_PARAM_RE.finditer(body)
        }
        results.append((m.start(), _call_to_python(name, args)))
    return results


def _extract_json_calls(text: str) -> list[tuple[int, str]]:
    """Extract JSON/Hermes-style <tool_call>{...}</tool_call> calls."""
    results = []
    for m in _JSON_TOOLCALL_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
            results.append(
                (m.start(), _call_to_python(data["name"], data.get("arguments", {})))
            )
        except (json.JSONDecodeError, KeyError):
            # Malformed entry -- skip it rather than failing the whole extraction
            continue
    return results


def _extract_react_calls(text: str) -> list[tuple[int, str]]:
    """Extract ReAct-format calls: Action: xxx / Action Input: {...}"""
    results = []
    for m in _REACT_RE.finditer(text):
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            args = {}
        results.append((m.start(), _call_to_python(m.group(1).strip(), args)))
    return results


# ---------------------------------------------------------------------------
# Single public entry point
# ---------------------------------------------------------------------------

def extract_python_code_block(llm_text: str) -> ExtractionResult:
    """Extract executable Python code from a raw LLM response.

    Detects all four formats, sorts the matches by their position in
    the original text, and concatenates them into one code string.
    The agent loop only needs to call this one function.
    """
    events: list[tuple[int, str]] = []

    for m in _PY_BLOCK_RE.finditer(llm_text):
        events.append((m.start(), m.group(1).strip()))

    events.extend(_extract_xml_calls(llm_text))
    events.extend(_extract_json_calls(llm_text))
    events.extend(_extract_react_calls(llm_text))

    if not events:
        return ExtractionResult(
            code=None,
            raw_llm_output=llm_text,
            warning="No valid code block found in the model output (Python/XML/JSON/ReAct all failed to match)",
        )

    events.sort(key=lambda e: e[0])
    code = "\n".join(snippet for _, snippet in events)
    return ExtractionResult(code=code, raw_llm_output=llm_text)