"""
MCP Server for SWE-bench tasks (Section V.4 + V.5).

必须放在仓库根目录（PDF明确要求）。9个工具会被评审单独测试（不只是在
agent 里跑一遍，而是单独调用检查输出格式），所以每个工具实现完之后要
对照 PDF Section V.5 核对一下输出格式。

架构（Plan B）：sandbox / agent loop 留在宿主机上跑，这个 MCP server
也是宿主机上的进程，它自己不直接读写代码 —— 每个工具内部都是通过
`docker exec` 钻进 agent_swebench/__main__.py 已经启动好的任务容器里，
代为执行文件读写/搜索/测试，再把结果传回来。

容器名字 + 任务信息怎么传进来：agent_swebench/__main__.py 在 spawn 这个
进程之前，会设置两个环境变量：
- SWEBENCH_CONTAINER_NAME: docker exec 要进哪个容器
- SWEBENCH_TASK_FILE:      task JSON 路径 (里面有 eval_script / repo /
                            instance_id 等字段，run_tests 会用到)
跟 mcp_tools_mbpp.py 靠 MBPP_TASK_FILE 知道当前任务是同一个套路。

容器桥接的框架代码（docker_exec / get_container / get_task / to_abs /
truncate）现在挪到同目录下的 docker_bridge.py 里了，这个文件只 import
用，具体实现和怎么单独测试看那边的说明。

=== 分工（TODO） ===
框架已经搭好了，下面 9 个工具的函数体还是 NotImplementedError，需要分头
填：
- 文件系统类: read_file / edit_file / list_files
- 代码搜索类: search_code / search_function_or_class_definition_in_code /
              find_references
- 执行类:     run_tests / get_patch / run_command

每个工具基本都是拼一条命令交给 docker_bridge.py 里的 docker_exec()，具体
命令思路写在每个函数自己的 docstring 里。
"""
import shlex

from mcp.server.fastmcp import FastMCP

from docker_bridge import docker_exec, get_container, get_task, to_abs, truncate

mcp = FastMCP("swebench-tools")


# ---------------------------------------------------------------------------
# 文件系统类
# ---------------------------------------------------------------------------


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read file content with line numbers, like `cat -n`.

    实现思路:
        docker_exec(f"cat -n {shlex.quote(to_abs(filepath))} | sed -n '{start_line},{end_line}p'")
    filepath 不管传相对路径还是绝对路径都行，交给 to_abs() 统一处理成容器
    里的绝对路径。
    """
    raise NotImplementedError("TODO: read_file")


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string.

    实现思路: filepath 先过一遍 to_abs()。old_str 必须在文件里唯一匹配，
    不唯一/找不到都要报错提示 LLM（不能瞎替换，不然容易改错地方）。用
    一段 python 脚本(通过 docker_exec 现场跑一个 python -c "...") 比用
    sed/grep 更好控制"必须唯一匹配"这条规则，也不用担心 old_str/new_str
    里有特殊字符转义的问题。
    """
    raise NotImplementedError("TODO: edit_file")


@mcp.tool()
def list_files(directory: str, pattern: str) -> str:
    """List files in a directory matching a pattern.

    实现思路: docker_exec(f"find {shlex.quote(to_abs(directory))} -name {shlex.quote(pattern)}")
    输出可能很长（大目录 + 宽泛的 pattern），记得用 truncate() 包一下。
    """
    raise NotImplementedError("TODO: list_files")


# ---------------------------------------------------------------------------
# 代码搜索类
# ---------------------------------------------------------------------------


@mcp.tool()
def search_code(pattern: str, file_pattern: str) -> str:
    """Grep-like search. Output format:
    /absolute/path/to/file.py:<line_number> <line_content>

    实现思路: docker_exec(f"grep -rn --include={shlex.quote(file_pattern)} {shlex.quote(pattern)} .")
    然后把每一行重新拼成上面要求的确切格式再返回，输出记得过一遍
    truncate()（宽泛的 pattern 很容易搜出几百行）。
    """
    raise NotImplementedError("TODO: search_code")


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Find the definition of a function or class.

    实现思路: 简单版可以 grep `^def {name}` / `^class {name}` 这种模式；
    更准确的话可以考虑在容器里现跑一个用 python ast 模块解析的小脚本。
    """
    raise NotImplementedError("TODO: search_function_or_class_definition_in_code")


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> str:
    """Find all usages of a symbol.

    实现思路: 最简单版本可以先做成全局 grep -rn 搜 name 出现的地方
    (filepath/line 这两个参数可以先用来排除定义本身那一行)。
    """
    raise NotImplementedError("TODO: find_references")


# ---------------------------------------------------------------------------
# 执行类
# ---------------------------------------------------------------------------


@mcp.tool()
def run_tests() -> str:
    """Execute the evaluation script (eval_script from SWEBenchTaskInput).

    实现思路:
        task = get_task()
        eval_script = task["eval_script"]
        把这段 script 通过 docker_exec 跑起来。eval_script 自己会
        checkout/revert 测试文件、装官方 gold test patch，直接整段跑就
        行，不用自己再拼测试命令。测试日志可能很长，返回前过一遍
        truncate()。
    """
    raise NotImplementedError("TODO: run_tests")


@mcp.tool()
def get_patch() -> str:
    """Return `git -c core.fileMode=false diff` from the repo.

    实现思路: docker_exec("git -c core.fileMode=false diff")，把
    stdout 原样返回就行，这是 agent 最后交卷 final_answer() 用的那份
    diff。
    """
    raise NotImplementedError("TODO: get_patch")


@mcp.tool()
def run_command(command: str, workdir: str) -> str:
    """Run a shell command, return stdout/stderr/exit code.

    实现思路: workdir 先过一遍 to_abs()，然后直接转发给
    docker_exec(command, workdir=to_abs(workdir))，把
    returncode/stdout/stderr 拼成字符串返回 (具体格式按 PDF 里的要求来，
    输出记得过一遍 truncate())。
    """
    raise NotImplementedError("TODO: run_command")


if __name__ == "__main__":
    mcp.run()
