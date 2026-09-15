# Candidate-review paid pilot

Date: 2026-09-15  
Model: `OPENAI:gpt-5.6-terra:reasoning-low`  
Dataset: `heldout_cases_v2`  
Cases: `SQ-HELD-001`, `SQ-HELD-013`, `SQ-HELD-022`

## Runs

- `summary.json` is the first attempt. B completed three paid calls, while D stopped
  locally during native structured-schema binding. Its D results are invalid for comparison.
- `summary-v2.json` is the schema-compatible rerun before candidate pre-validation.
- `summary-v3-pregate.json` is the candidate-pre-gate rerun and is the latest
  decision-bearing artifact.

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

The pre-gate rerun improved D to one direct plan out of three. On `SQ-HELD-001`, both
candidates passed independently, the reviewers disagreed, and the Coordinator changed the
selection to `RECOVERY_FOCUSED`; the final plan passed with no evaluator findings. On the
complex and conflict cases, Training exhausted its two attempts before review because at
least one candidate failed the common domain gate. B again produced 3/3 direct plans.

The principal design finding is that validating candidates only after selection is too late.
Each generated candidate must pass the same compile-and-integrity gate before specialists
spend calls reviewing it. A failed review also needs its exact sanitized audit retained in the
pilot report. The runner now retains those audits for subsequent runs; the stored v2 artifact
predates that reporting addition.

## Usage and cost

Across the first two attempts, recorded provider usage was 100,586 input tokens and 21,917
output tokens, costing **$0.464176** using the approved Round 3 pricing reference ($2.00/M
input, $12.00/M output). V3 records another 54,145 input and 14,427 output tokens, a
**$0.281414 recorded-usage lower bound**, and made 11 provider attempts.

The lower-bound qualifier matters: the shared invoker retains the final attempt's usage when
a domain-invalid answer is retried, not the sum of both attempts. The complex and conflict D
runs each used two Training attempts, so their first-attempt tokens are not present in the
artifact. Across all three pilot files the recorded lower bound is **$0.745590**; this is not
an invoice-equivalent total.

No judge calls were made. Results contain normalized evaluation inputs and metrics only;
the AWS secret was held in process memory and was not written to these artifacts.
