# Benchmark Report

## 1. Setup

TODO:
- Which models/providers were compared (at least 5)
- Which SWE-bench tasks were used (at least 3), and why those were chosen

## 2. Results Table

| Model | Task | Pass/Fail | Iterations | Input tokens | Output tokens | Wall-clock time |
|-------|------|-----------|------------|---------------|-----------------|------------------|
| TODO  | TODO | TODO      | TODO       | TODO          | TODO            | TODO             |

## 3. Provider Reliability

| Model/Provider | Avg response time | Retries needed | Availability |
|-----------------|--------------------|------------------|----------------|
| TODO            | TODO               | TODO             | TODO           |

## 4. Intermediary Metrics

TODO (at least 2 of):
- Step at which the agent first reads/edits the file that appears in the final patch
- Step at which test failures first decrease vs baseline
- Iterations between "tests first pass" and `final_answer` (zero is ideal)

## 5. Ablation Study

TODO: at least one before/after comparison of a change to the agent
(prompt, tools, parameters) on the same tasks with the same model.

## 6. Conclusions

TODO: which model(s) were selected for the final pipeline and why;
which models can be disregarded and why — based on the data above.
