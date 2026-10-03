from types import SimpleNamespace

from common.agent_loop import AgentLoop


class _FakeLLM:
    base_url = "http://fake"
    model_name = "fake"

    def __init__(self, text):
        self._text = text

    def generate(self, messages, stop_sequences=None, deadline=None, **kw):
        return SimpleNamespace(
            text=self._text, input_tokens=1, output_tokens=1, request_time_ms=1.0, retries=0
        )


class _FakeSandbox:
    final_answer_called = False
    final_answer_value = ""

    def execute(self, code, *a, **k):
        return "ran"


def _first_observation(llm_text):
    agent = AgentLoop(_FakeLLM(llm_text), _FakeSandbox(), "sys", 1, 10**9, 10**9, timeout_seconds=60)
    result = agent.run("t", "mbpp", "go")
    return result.steps[0].sandbox_output if result.steps else None


def test_llm_is_told_when_its_reply_was_interpreted():
    obs = _first_observation("Thought: x\n```python\nprint(1)\n")  # no closing fence
    assert obs.startswith("[Note]")
    assert "closing" in obs.lower()
    assert obs.endswith("ran")


def test_clean_reply_gets_no_note():
    obs = _first_observation("Thought: x\n```python\nprint(1)\n```\n<end_code>")
    assert obs == "ran"
