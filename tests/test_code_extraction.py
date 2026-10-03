from common.code_extraction import extract_python_code_block


def test_closed_block_has_no_warning():
    r = extract_python_code_block("Thought: x\n```python\nprint(1)\n```\n<end_code>")
    assert r.code == "print(1)"
    assert r.warning is None


def test_unclosed_block_is_recovered_with_warning():
    r = extract_python_code_block("Thought: x\n```python\nprint(1)\n")
    assert r.code == "print(1)"
    assert r.warning and "closing" in r.warning.lower()


def test_unclosed_block_followed_by_end_code_is_recovered():
    r = extract_python_code_block("```python\nprint(1)\n<end_code>")
    assert r.code == "print(1)"
    assert r.warning


def test_xml_call_is_converted_and_the_llm_is_told():
    text = '<invoke name="read_file"><parameter name="filepath">a.py</parameter></invoke>'
    r = extract_python_code_block(text)
    assert r.code == "read_file(filepath='a.py')"
    assert r.warning and "XML" in r.warning and "read_file(filepath='a.py')" in r.warning


def test_json_call_is_converted_and_the_llm_is_told():
    text = '<tool_call>{"name": "read_file", "arguments": {"filepath": "a.py"}}</tool_call>'
    r = extract_python_code_block(text)
    assert r.code == "read_file(filepath='a.py')"
    assert r.warning and "JSON" in r.warning


def test_invalid_json_call_is_reported_not_silently_dropped():
    r = extract_python_code_block('<tool_call>{"name": "x",}</tool_call>')
    assert r.code is None
    assert "could not be parsed" in r.warning


def test_react_with_invalid_arguments_says_so():
    r = extract_python_code_block("Action: read_file\nAction Input: {bad}")
    assert r.code == "read_file()"
    assert "no arguments" in r.warning


def test_nothing_found_explains_how_to_reply():
    r = extract_python_code_block("I think the answer is 42.")
    assert r.code is None
    assert "```python" in r.warning
