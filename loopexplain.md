# Agent Smith — How the LLM Request Works

Study notes for `common/llm_provider.py`.
Scope: how the agent asks the model for code, and how the answer comes back.

---

## 1. What a payload is

**Payload = the data placed in the *body* of the HTTP request.** The word means
"cargo" — it is not attached to the envelope (the headers), it is the content
*inside* the envelope.

In `LLMProvider.generate()` we build a Python `dict`, but that dict is only the
raw material. What actually travels over the network is JSON text:

```http
POST /v1beta/openai/chat/completions HTTP/1.1
Host: generativelanguage.googleapis.com
Authorization: Bearer AIzaSy...          <- header (ID card)
Content-Type: application/json           <- header (says the body is JSON)

{                                        <- the payload starts here (body)
  "model": "gemini-3.6-flash",
  "messages": [
    {"role": "system", "content": "You are a coding agent..."},
    {"role": "user",   "content": "Write a function to find the square..."}
  ],
  "max_tokens": 1024,
  "temperature": 0,
  "stop": ["<end_code>"]
}
```

`requests.post(url, json=payload)` does two things for us:

1. serializes the dict to a JSON string (`json.dumps`)
2. automatically sets the `Content-Type: application/json` header

The server receives that JSON text and parses it back into objects in whatever
language it is written in.

---

## 2. The payload is not itself "the format" — it follows one

The spec the payload must obey is the **OpenAI Chat Completions API**.

OpenAI defined it, and it became the de-facto industry standard. That is why the
same payload can be sent to Google, OpenRouter, Groq, or a local Ollama instance
by changing nothing but `base_url`. Our `.env` holds a `GOOGLE_API_KEY` and the
URL contains `/openai/` — that is Google's OpenAI-compatible endpoint, built so
that clients written for OpenAI keep working.

### Payload keys

| Key | Required | Meaning |
|---|---|---|
| `model` | yes | Which model to use. The server routes on this. |
| `messages` | yes | The whole conversation. `role` is one of `system` / `user` / `assistant`. |
| `max_tokens` | no | Upper bound on how many tokens the model may **generate** (output limit). |
| `temperature` | no | Randomness of the sampling (see below). Provider default is usually `1.0`. |
| `stop` | no | List of strings; generation halts as soon as one is produced. |
| `n` | no | **How many independent candidate answers to generate. Default is `1`.** We never set it, so we always get exactly one. |

Only the first two are mandatory. Anything omitted falls back to the server's
default — which is why `generate()` only inserts the `stop` key when stop
sequences were actually passed:

```python
if stop_sequences:
    payload["stop"] = stop_sequences
```

Omitting a key is safer than sending `"stop": null`; some providers reject an
explicit null.

### Note on `n`

`n` is why the response contains a **list** called `choices`. With `"n": 3` the
server would return three separately sampled answers to the same prompt:

```json
"choices": [
  {"index": 0, "message": {}},
  {"index": 1, "message": {}},
  {"index": 2, "message": {}}
]
```

The intended use is "generate several candidates, then pick the best one."
We do not use it, for two reasons:

- with `temperature: 0` all `n` candidates would come out **identical**, so it
  buys nothing (candidate diversity requires a non-zero temperature);
- it multiplies the output token cost by `n`.

Since `n` defaults to `1`, our `choices` list always has exactly one element.
`data["choices"][0]` is therefore not "pick the first of several" — it is
"unwrap the only element from a list the spec forces to be a list."

---

## 3. `temperature` — the randomness dial

How the model picks each token:

1. the model emits a score (**logit**) for every token in its vocabulary
2. those scores are turned into a probability distribution (**softmax**)
3. one token is **sampled** from that distribution

`temperature` is the value the logits are **divided by** at step 2:
`softmax(logits / T)`.

```
raw logits:   "the"=5.0   "a"=4.0   "banana"=1.0

T = 1.0  ->  5.0, 4.0, 1.0  ->  probs:  70%, 26%,  4%   (unchanged)
T = 2.0  ->  2.5, 2.0, 0.5  ->  probs:  48%, 39%, 13%   (flatter = diverse, creative, more nonsense)
T = 0.5  -> 10.0, 8.0, 2.0  ->  probs:  88%, 12%,  0%   (sharper = conservative)
T -> 0   ->  fully sharpened ->  probs: 100%,  0%,  0%  (always rank 1 = greedy)
```

Lower `T` = "only ever pick what it is confident about."
Higher `T` = "sometimes pick the 2nd or 3rd best token."

`T = 0` cannot literally be used as a divisor, so implementations special-case it
as **greedy decoding**: always take the highest-probability token.

### Why this project uses `temperature = 0`

- **Reproducibility.** Running the same task twice should give the same result,
  otherwise benchmark scores drift between runs and you cannot tell whether a
  prompt change actually helped.
- **Code does not need creativity.** For poetry `T = 0.9` may be better; for
  `def square(n): return n * n` diversity is pure downside. Writing `n ** 2`
  instead of `n * n` would be fine — a typo 40% of the time would not.
- **Format compliance.** The agent only works if the model reliably emits a
  ` ```python ` block and calls `final_answer()`. Higher temperature raises the
  chance of drifting out of that format, which wastes a whole step on
  "No code block found."

> Caveat: even at `T = 0`, reproduction is not guaranteed. GPU floating-point
> results can vary slightly with batching and kernel scheduling, and when the
> top two logits are nearly tied that tiny difference can flip the chosen token.
> "T=0 but I get different answers" is a common real-world complaint. It is
> still far more stable than `T = 0.7`.

### Note on `max_tokens`

`1024` caps the **response**. If the model writes past that limit it is cut off
mid-sentence, the closing fence of the code block never arrives, the extraction
regex fails to match, and the step falls through to "No code block found."
Fine for short MBPP answers; a likely bottleneck once long SWE-bench patches are
being generated.

---

## 4. The headers, and what `Bearer` means

```python
response = requests.post(
    f"{self.base_url}/chat/completions",                          # where
    headers={"Authorization": f"Bearer {self._current_key()}"},   # who (auth)
    json=payload,                                                 # what (body)
    timeout=120,                                                  # give up after 120s
)
```

This is the **only** line that touches the network. Execution blocks here for the
seconds (or tens of seconds) the model spends thinking.

- **`Bearer <key>`** is the standard HTTP authorization scheme: "grant access to
  whoever *bears* this token." There is no challenge/response — possession of
  the string is the entire proof, which is exactly why the key is read from
  `os.environ` and never hardcoded.
- **`timeout=120`** is not optional in spirit. Without it, a server that never
  replies leaves the program hanging forever.

---

## 5. What comes back

`response` is a `requests.Response`: status code + headers + raw bytes. Not JSON
yet. `response.json()` parses it into a dict:

```json
{
  "id": "chatcmpl-...",
  "choices": [
    { "index": 0,
      "message": { "role": "assistant", "content": "Thought: ..." },
      "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 412, "completion_tokens": 87, "total_tokens": 499 }
}
```
