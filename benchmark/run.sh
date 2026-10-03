#!/usr/bin/env bash
# Run one model on the 3 benchmark tasks and keep everything the report needs.
# Run from the repository root:
#
#   bash benchmark/run.sh <run_name> <model_name> <provider_url> <api_key_env>
#
# Example:
#   bash benchmark/run.sh gemini-flash gemini-2.5-flash \
#       https://generativelanguage.googleapis.com/v1beta/openai GEMINI_API_KEY
#
# Results: benchmark/runs/<run_name>/<instance_id>/{solution.json,validate.txt,agent.log}
# The task files are copied to benchmark/tasks/ because cache/ is git-ignored
# and the report's backing files must be committed (PDF V.7).
set -u
if [ $# -ne 4 ]; then
    echo "usage: bash benchmark/run.sh <run_name> <model_name> <provider_url> <api_key_env>" >&2
    exit 1
fi
RUN="$1" MODEL="$2" URL="$3" KEYENV="$4"

# The same 3 tasks for every model.
TASK_FILES="${TASK_FILES:-cache/swebench_task.json cache/swebench_task2.json cache/swebench_task3.json}"

mkdir -p benchmark/tasks
for src in $TASK_FILES; do
    if [ ! -f "$src" ]; then
        echo "!! $src not found, skipping" >&2
        continue
    fi
    T=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["instance_id"])' "$src")
    task="benchmark/tasks/$T.json"
    out="benchmark/runs/$RUN/$T"
    [ -f "$task" ] || cp "$src" "$task"
    mkdir -p "$out"

    if [ -f "$out/solution.json" ]; then
        echo "== $RUN / $T: already done, skipping (delete $out to rerun)"
        continue
    fi

    echo "== $RUN / $T"
    uv run python -m agent_swebench --task-file "$task" --output "$out/solution.json" \
        --model-name "$MODEL" --provider-url "$URL" --api-key-env "$KEYENV" \
        2>&1 | tee "$out/agent.log"

    (cd moulinette && uv run moulinette_eval validate swebench "../$task" "../$out/solution.json") \
        2>&1 | tee "$out/validate.txt" | grep -a "Overall:" | tail -n 1

    if [ -n "$(docker ps -aq)" ]; then
        echo "!! containers left over: $(docker ps -a --format '{{.Names}}')"
    fi
done

