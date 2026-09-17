"""
Agent loop core (Section V.1): Thought -> Code -> Observation.

    messages = [system_prompt, user_task]
    for step in 1..max_iterations:
        response    = llm.generate(messages, stop=["<end_code>"])
        code        = extract_python_code_block(response.text)
        observation = sandbox.execute(code)       (or a "no code found" message)
        if final_answer() was called -> return SolutionOutput
        messages += [assistant: response, user: "Observation: ..."]

STAGE 1 (current): max_iterations, max_input_tokens, max_output_tokens and
  timeout_seconds are all enforced. Token limits are cumulative across all
  iterations of the task (Section VI.1); timeout is checked before starting
  each new LLM call, not mid-request.
"""
from __future__ import annotations

import time
from typing import List

from common.code_extraction import extract_python_code_block
from common.llm_provider import LLMProvider
from common.models import SolutionOutput, StepMetrics

STOP_SEQUENCES = ["<end_code>"]


class AgentLoop:
    """Shared by the MBPP and SWE-bench agents; only the system prompt,
    the task text and the sandbox's MCP tools differ.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        sandbox,  # sandbox.executor.Sandbox
        system_prompt: str,
        max_iterations: int,
        max_input_tokens: int,
        max_output_tokens: int,
        timeout_seconds: int,
    ):
        self.llm_provider = llm_provider
        self.sandbox = sandbox
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds

    def run(self, task_id: str, benchmark: str, user_task: str) -> SolutionOutput:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_task},
        ]
        steps: List[StepMetrics] = []

        def finish(success: bool, solution: str, error=None) -> SolutionOutput:
            return SolutionOutput(
                task_id=task_id,
                benchmark=benchmark,
                success=success,
                solution=solution,
                iterations=len(steps),
                total_requests=sum(1 + s.retries for s in steps),
                total_input_tokens=sum(s.input_tokens for s in steps),
                total_output_tokens=sum(s.output_tokens for s in steps),
                total_time_seconds=time.perf_counter() - start,
                steps=steps,
                system_prompt=self.system_prompt,
                error=error,
            )

        total_input_tokens = 0
        total_output_tokens = 0

        for step in range(1, self.max_iterations + 1):
            elapsed = time.perf_counter() - start
            if elapsed >= self.timeout_seconds:
                return finish(False, "", f"Reached timeout ({self.timeout_seconds}s) before completing")

            try:
                response = self.llm_provider.generate(messages, stop_sequences=STOP_SEQUENCES)
            except Exception as e:
                return finish(False, "", f"LLM request failed at step {step}: {e}")

            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            extraction = extract_python_code_block(response.text)
            if extraction.code is None:
                observation = (
                    "No code block found. Reply with 'Thought: ...' followed by a "
                    "```python ... ``` block, then <end_code>."
                )
            else:
                observation = self.sandbox.execute(extraction.code) or "(no output — use print())"

            steps.append(
                StepMetrics(
                    step=step,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    request_time_ms=response.request_time_ms,
                    api_url=self.llm_provider.base_url,
                    model_name=self.llm_provider.model_name,
                    llm_output=response.text,
                    sandbox_input=extraction.code or "",
                    sandbox_output=observation,
                    retries=response.retries,
                )
            )

            if self.sandbox.final_answer_called:
                # A successful final_answer on this very step counts as success even
                # if this step's tokens happen to push the running total over budget --
                # the totals were only knowable after the response that solved the task.
                return finish(True, self.sandbox.final_answer_value)

            if total_input_tokens > self.max_input_tokens:
                return finish(False, "", f"Exceeded max input tokens ({self.max_input_tokens})")
            if total_output_tokens > self.max_output_tokens:
                return finish(False, "", f"Exceeded max output tokens ({self.max_output_tokens})")

            messages.append({"role": "assistant", "content": response.text})
            messages.append({"role": "user", "content": f"Observation:\n{observation}"})

        return finish(False, "", f"Reached max iterations ({self.max_iterations}) without final_answer")


def build_system_prompt(sandbox_manual: str, benchmark: str) -> str:
    """STAGE 0: minimal prompt with format rules and one worked example."""
    tools = sandbox_manual.strip() or "(no extra tools connected)"
    return f"""You are a coding agent that solves tasks by writing and running Python code.

At each turn, write:
Thought: your reasoning about what to do next
```python
# code to run
```
<end_code>

Rules:
- Your code is executed and its printed output is sent back to you as "Observation:".
  Only what you print() is visible, so print the results you need.
- Variables and functions you define persist between turns.
- Never write the Observation yourself; stop after <end_code>.
- When you are done, call final_answer(answer) inside a code block.

Always available:
- final_answer(answer: str) -> None : submit your final answer and end the task.

Other tools:
{tools}

For {benchmark} tasks: write the requested function as a source-code string, exec() it,
check it against the given tests, then submit the source string with final_answer.

Example
-------
Task: Write a function to find the square of a number.
Function signature: def square(n):
Tests:
assert square(3) == 9

Thought: I will define the function as a string, run it and check the test.
```python
solution = '''def square(n):
    return n * n
'''
exec(solution)
assert square(3) == 9
print("all tests passed")
```
<end_code>
Observation:
all tests passed

Thought: The tests pass, I submit the solution.
```python
final_answer(solution)
```
<end_code>
"""
