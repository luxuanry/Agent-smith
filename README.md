*This project has been created as part of the 42 curriculum by <login1>, <login2>, <login3>.*

# Agent Smith

## Description

TODO: Explain what this project does — an agentic framework that autonomously
solves coding challenges (MBPP + SWE-bench) through a Thought -> Code ->
Observation loop, executed inside a secure sandbox connected to an MCP server.

## Instructions

### Requirements
- Python 3.10
- [uv](https://docs.astral.sh/uv/)
- Docker (for SWE-bench)

### Setup
```bash
cp .env.example .env
# fill in your real API key(s) in .env
uv sync
```

### Running the sandbox interactively
```bash
uv run sandbox
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
```

### Running the MBPP agent
```bash
cd moulinette
uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json
cd ..
uv run python -m agent_mbpp --task-file cache/mbpp_task.json \
    --output cache/mbpp_solution.json \
    --model-name "TODO" --provider-url "TODO"
```

### Running the SWE-bench agent
```bash
cd moulinette
uv run moulinette_eval dump swebench --output ../cache/swebench_task.json
cd ..
uv run python -m agent_swebench --task-file cache/swebench_task.json \
    --output cache/swebench_solution.json \
    --model-name "TODO" --provider-url "TODO"
```

## System Architecture

TODO: describe (with a diagram if you like)
- Orchestrator / agent loop
- Code extraction layer
- Sandbox (execution boundary)
- MCP client <-> MCP server(s)

## Agent Loop Explanation

TODO: describe the Thought -> Code -> Observation loop, how the system prompt
is built, and how limits (iterations/tokens/timeout) are enforced.

## Sandbox Design

TODO: describe the security model — import allowlist, filesystem allowlist,
timeout, memory limits, restricted builtins — and which isolation approach
you chose (in-process vs subprocess) and why.

## Tool Implementation Details

TODO: describe how the 9 mandatory MCP tools work, and how stdio/HTTP
transports are supported.

## Benchmark Results and Analysis

See [BENCHMARK_REPORT.md](./BENCHMARK_REPORT.md) for the full comparison.

## Resources

TODO: list documentation, articles, tutorials you used, e.g.:
- Model Context Protocol docs: https://modelcontextprotocol.io/
- SWE-bench: https://www.swebench.com/
- smolagents (CodeAgent concept, for inspiration only — not used as a dependency)

### How AI was used

TODO: be specific about which parts were AI-assisted vs. designed/written by
the team, per the project's AI Instructions (Chapter II). Example format:
- Scaffolding / boilerplate: AI-assisted, reviewed and modified by the team
- Sandbox security design: designed by the team, AI used to check edge cases
- Agent loop core logic: written by the team
