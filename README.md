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
uv run moulinette_eval dump swebench --task-id sympy__sympy-14711 --output ../cache/swebench_task.json
cd ..
uv run python -m agent_swebench --task-file cache/swebench_task.json \
    --output cache/swebench_solution.json \
    --model-name "TODO" --provider-url "TODO"
cd moulinette
uv run moulinette_eval validate swebench ../cache/swebench_task.json ../cache/swebench_solution.json
```

Leave off `--task-id` to dump a random instance instead of a fixed one.

> **Status:** the `dump` step above already works. `agent_swebench/__main__.py`
> and `mcp_tools_swebench.py` are not implemented yet (both currently
> `raise NotImplementedError`), so the `agent_swebench` and `validate` steps
> don't run yet -- see below for exploring a task by hand in the meantime.

### Exploring a SWE-bench container by hand

Before the 9 MCP tools are wired up, it's worth pulling one task's image and
poking around inside it manually -- this is the same thing
`mcp_tools_swebench.py`'s tools will eventually do via `docker exec`, just
typed by hand instead of called by the agent.

Requires Docker Desktop running. The image name comes from the
`docker_image` field of the dumped task JSON and is different per
`instance_id` -- using `sympy__sympy-14711` as the running example below.

```bash
# 1. pull the instance's image (first pull can take a few minutes)
docker pull swebench/sweb.eval.x86_64.sympy_1776_sympy-14711:latest

# 2. start it detached -- the trailing /bin/bash is what keeps it alive
docker run -dit --name sympy-14711 \
    swebench/sweb.eval.x86_64.sympy_1776_sympy-14711:latest \
    /bin/bash

# 3. confirm it's up (should show sympy-14711, status Up)
docker ps

# 4. step inside -- prompt changes to something like root@<id>:/# once you're in
docker exec -it sympy-14711 /bin/bash

# --- now inside the container ---
cd /testbed
ls
git log -1        # one synthetic "SWE-bench" commit, not the real project history
git status
source /opt/miniconda3/bin/activate
conda activate testbed
# poke around, try reproducing the bug from problem_statement, etc.
exit
# --- back on the host ---

# 5. clean up -- don't skip this, an unremoved container just sits there
docker stop sympy-14711
docker rm sympy-14711
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
