# Candidate-review paid pilot

Date: 2026-09-15  
Model: `OPENAI:gpt-5.6-terra:reasoning-low`  
Dataset: `heldout_cases_v2`  
Cases: `SQ-HELD-001`, `SQ-HELD-013`, `SQ-HELD-022`

## Runs

- `summary.json` is the first attempt. B completed three paid calls, while D stopped
  locally during native structured-schema binding. Its D results are invalid for comparison.
- `summary-v2.json` is the schema-compatible rerun and is the decision-bearing artifact.

## Result

| Case | B direct plan | D direct plan | D intervention | D terminal reason |
|---|---:|---:|---|---|
| SQ-HELD-001 (simple) | yes | no | none observed | domain-invalid candidate path |
| SQ-HELD-013 (complex) | yes | no | selected recovery candidate; reviewer disagreement; 2 adjustments | `PLAN_EXERCISE_VARIETY_EXCEEDED` |
| SQ-HELD-022 (conflict) | yes | no | review pipeline stopped before selection | provider-stage failure |

B produced a direct plan in 3/3 rerun cases. D reached a meaningful multi-agent
intervention in one case, but its selected plan failed the downstream deterministic gate;
all three D results therefore used deterministic fallback. This pilot does not establish D
superiority.

The principal design finding is that validating candidates only after selection is too late.
Each generated candidate must pass the same compile-and-integrity gate before specialists
spend calls reviewing it. A failed review also needs its exact sanitized audit retained in the
pilot report. The runner now retains those audits for subsequent runs; the stored v2 artifact
predates that reporting addition.

## Usage and cost

Across both attempts, recorded provider usage was 100,586 input tokens and 21,917 output
tokens. Using the approved pricing reference in the Round 3 artifacts ($2.00/M input,
$12.00/M output), the calculated cost is **$0.464176**. The rerun recorded 14 role calls;
the first attempt recorded six role invocations, of which the three D schema failures had no
provider token usage.

No judge calls were made. Results contain normalized evaluation inputs and metrics only;
the AWS secret was held in process memory and was not written to these artifacts.
