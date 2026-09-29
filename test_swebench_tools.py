"""
Standalone check of the SWE-bench MCP tools (Section V.5).

The graders call these tools one by one and look at their output format,
so this script does the same, without the agent or the LLM: it starts the
task's container itself, runs each tool, and cleans up afterwards.

    cd moulinette
    uv run moulinette_eval dump swebench --output ../cache/swebench_task.json
    cd ..
    uv run python test_swebench_tools.py

Pass --keep to leave the container running for manual poking around.
"""
import json
import os
import subprocess
import sys

TASK_FILE = "cache/swebench_task.json"
CONTAINER_NAME = "agent_smith_tool_test"


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kwargs)


def qualified(image: str) -> str:
    """Podman (which stands in for docker on the 42 machines) searches its
    own registry list when the image name has no registry in it, and fails
    on "swebench/...". Docker Hub has to be named explicitly.
    """
    first = image.split("/")[0]
    if "." in first or ":" in first or first == "localhost":
        return image  # already qualified
    return f"docker.io/{image}"


def start_container(image: str) -> None:
    image = qualified(image)
    print(f"[setup] removing any leftover container named {CONTAINER_NAME}")
    docker("rm", "-f", CONTAINER_NAME)

    print(f"[setup] pulling {image} (this can take a few minutes the first time)")
    pull = subprocess.run(["docker", "pull", image])
    if pull.returncode != 0:
        sys.exit("[setup] docker pull failed")

    print("[setup] starting the container")
    # `sleep infinity` keeps it alive so every tool call can docker exec into it.
    run = docker("run", "-d", "--name", CONTAINER_NAME, image, "sleep", "infinity")
    if run.returncode != 0:
        sys.exit(f"[setup] docker run failed:\n{run.stderr}")


def show(title: str, result: str, limit: int = 1500) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    text = result if len(result) <= limit else result[:limit] + f"\n... [{len(result) - limit} more characters]"
    print(text)


def main() -> None:
    if not os.path.exists(TASK_FILE):
        sys.exit(f"{TASK_FILE} not found -- dump a task first (see this file's docstring)")

    task = json.load(open(TASK_FILE, encoding="utf-8"))
    print(f"[setup] instance: {task['instance_id']}  repo: {task.get('repo', '?')}")

    start_container(task["docker_image"])

    # The tools read these two environment variables, exactly as they would
    # when agent_swebench/__main__.py launches the MCP server.
    os.environ["SWEBENCH_TASK_FILE"] = os.path.abspath(TASK_FILE)
    os.environ["SWEBENCH_CONTAINER_NAME"] = CONTAINER_NAME

    import mcp_tools_swebench as tools

    try:
        show("run_command('ls', '/testbed')", tools.run_command("ls", "/testbed"))
        show("run_command('cat nope.txt', '/testbed') -- expected to fail cleanly",
             tools.run_command("cat nope.txt", "/testbed"))

        show("search_code('def __init__', '*.py') -- expect /abs/path:NN content",
             tools.search_code("def __init__", "*.py"))

        name = input("\nName of a function or class to look up (Enter for 'Symbol'): ").strip() or "Symbol"
        definitions = tools.search_function_or_class_definition_in_code(name)
        show(f"search_function_or_class_definition_in_code({name!r})", definitions)

        first = definitions.splitlines()[0] if ":" in definitions else ""
        if first:
            path, rest = first.split(":", 1)
            line = int(rest.split()[0])
            show(f"find_references({name!r}, {path!r}, {line}) -- the definition line must be absent",
                 tools.find_references(name, path, line))

        show("get_patch() before any edit -- expect no changes", tools.get_patch())

        print("\n[check] making a small edit so get_patch() has something to show")
        subprocess.run(["docker", "exec", "-w", "/testbed", CONTAINER_NAME,
                        "bash", "-lc", "echo '# agent smith test' >> setup.py"])
        show("get_patch() after the edit", tools.get_patch())

        print("\n[check] running the evaluation script (up to 300s)")
        show("run_tests()", tools.run_tests(), limit=3000)
    finally:
        if "--keep" in sys.argv:
            print(f"\n[cleanup] left {CONTAINER_NAME} running; remove it with:")
            print(f"    docker rm -f {CONTAINER_NAME}")
        else:
            print(f"\n[cleanup] removing {CONTAINER_NAME}")
            docker("rm", "-f", CONTAINER_NAME)


if __name__ == "__main__":
    main()