"""
LLM Provider 抽象层。

目标：Agent Loop 不应该关心「我用的是 OpenRouter 还是 Groq 还是 Gemini」，
它只应该调用 `provider.generate(messages, stop_sequences=[...])`，
拿到统一格式的返回值。

=== 你们需要实现的部分（TODO） ===
1. `LLMProvider.generate()`：真正发 HTTP 请求给 provider（大部分免费 provider
   都兼容 OpenAI 的 /chat/completions 格式，可以复用同一套请求逻辑）。
2. 多 API key 轮换：如果一个 key 被限流（HTTP 429），自动换下一个 key 重试。
3. 记录 usage：每次请求后，把 input_tokens / output_tokens / 耗时 记下来，
   这些数据最后要填进 StepMetrics。
4. stop_sequences：见 PDF Section V.6 —— 一定要传 stop 参数，防止模型
   在你还没执行代码之前就自己"编造"执行结果。

不要在代码里硬编码 API key！一定从环境变量读（评审会检查，见 Section VI.3）。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests


@dataclass
class LLMResponse:
    """一次 LLM 调用的标准化返回结果。"""

    text: str
    input_tokens: int
    output_tokens: int
    request_time_ms: float
    retries: int = 0


class LLMProvider:
    """对接一个 OpenAI-兼容的 LLM API（OpenRouter / Groq / 等）。

    多个 API key 用逗号分隔存在同一个环境变量里，比如：
        OPENROUTER_API_KEY=key1,key2,key3
    """

    def __init__(self, model_name: str, base_url: str, api_key_env: str):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        raw_keys = os.environ.get(api_key_env, "")
        self.api_keys: List[str] = [k.strip() for k in raw_keys.split(",") if k.strip()]
        if not self.api_keys:
            raise ValueError(
                f"没有在环境变量 {api_key_env} 里找到任何 API key。"
                f" 请检查 .env 文件或环境变量是否设置。"
            )
        self._key_index = 0

    def _current_key(self) -> str:
        return self.api_keys[self._key_index]

    def _rotate_key(self) -> None:
        self._key_index = (self._key_index + 1) % len(self.api_keys)

    def generate(
        self,
        messages: List[dict],
        stop_sequences: Optional[List[str]] = None,
        max_tokens: int = 1024,
        max_retries: int = 3,
    ) -> LLMResponse:
        """
        TODO(学生实现):
        - 用 requests.post 调用 f"{self.base_url}/chat/completions"
        - headers 里带 Authorization: Bearer {self._current_key()}
        - 遇到 429 / 5xx：调用 self._rotate_key()，sleep 一下，重试
        - 从 response.json() 里解析出:
            text = response["choices"][0]["message"]["content"]
            input_tokens = response["usage"]["prompt_tokens"]
            output_tokens = response["usage"]["completion_tokens"]
        - 记录 request_time_ms（用 time.perf_counter() 前后差）
        - 记录 retries 次数
        """
        raise NotImplementedError("TODO: 在这里实现真正的 API 调用逻辑")
