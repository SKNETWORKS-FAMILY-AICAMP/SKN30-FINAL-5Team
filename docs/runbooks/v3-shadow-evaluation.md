# V3 synthetic shadow evaluation runbook

## Scope

This harness evaluates saved synthetic `V3ShadowExecutionResult` values without enabling the V3
production path. The default command has no provider factory, network client, database write, public
API, or frontend dependency. Its 20 versioned cases cover the required healthy, downshift, safety,
fallback, review, repair, retrieval, regeneration, provider-failure, terminal, and privacy paths.

The generated report is test evidence only. It is not an expert approval, a live-user shadow result,
or permission to promote V3 to production.

## Run

From the repository root:

```powershell
backend\.venv\Scripts\python.exe -m backend.scripts.run_v3_shadow_evaluation `
  --repeat-count 1 `
  --output-directory outputs\v3-shadow
```

The stored-result mode is the default and makes zero provider calls. `--allow-provider-calls` is an
explicit application-level integration hook and still fails unless the caller injects a
`V3ShadowRunnerPort`; this repository CLI deliberately does not construct a live provider.

An approved, versioned pricing JSON may be supplied with `--pricing-reference`. It must match the
result provider and model. Current vendor prices are not hard-coded. Without complete usage and an
approved matching reference, cost fields remain `null`/`NOT_AVAILABLE`.

## Output contract

| File | Content |
|---|---|
| `results.jsonl` | Canonical terminal shadow results, one per case and repeat |
| `summary.json` | Aggregate metrics, hard-gate result, nullable expert/cost fields, summary hash |
| `summary.md` | Human-readable summary that labels non-safety thresholds report-only |
| `expert_review_template.jsonl` | V1/V3 plans, differences, safety evidence, and pending reviewer fields |
| `manifest.json` | Fixture/harness versions, repeat count, file hashes, and record counts |

Every structured report is checked against a schema-derived key allowlist before writing. Direct
identifiers, raw health/wearable records, prompts/messages, provider raw responses/errors, hidden
reasoning, and credentials are not valid report fields.

The expert template starts with `PENDING` decisions. A completed review requires a reviewer role,
timestamp, and public reason codes. Agreement counts `V3_PREFERRED` and `EQUIVALENT` among completed
reviews only; with no completed review its status is `NOT_REVIEWED` and its rate is `null`.

## Gates and interpretation

The evaluation fails only for explicit safety violation codes or constraint violation codes. These
include safety-veto override, provider activity after a terminal safety decision, forbidden plan
generation, pool/mandatory/duration/recovery violations, invalid partial coordination, exceeded
review/repair limits, or weakened fallback safety.

Latency p50/p95, token/cost data, structured-output success, agent/coordinator failure, review,
repair, deterministic fallback, no-plan terminal, and expert agreement are report-only until V3-C2
approves thresholds. A V1/V3 plan difference alone is not a hard failure.

## Verification

```powershell
backend\.venv\Scripts\ruff.exe format --check backend/app/modules/decisions/v3_evaluation.py backend/app/modules/decisions/v3_evaluation_fixtures.py backend/scripts/run_v3_shadow_evaluation.py backend/tests/unit/test_v3_evaluation.py backend/tests/unit/test_v3_evaluation_cli.py backend/tests/scenarios/test_v3_shadow_evaluation_golden.py
backend\.venv\Scripts\ruff.exe check backend/app/modules/decisions/v3_evaluation.py backend/app/modules/decisions/v3_evaluation_fixtures.py backend/scripts/run_v3_shadow_evaluation.py backend/tests/unit/test_v3_evaluation.py backend/tests/unit/test_v3_evaluation_cli.py backend/tests/scenarios/test_v3_shadow_evaluation_golden.py
backend\.venv\Scripts\mypy.exe backend/app/modules/decisions/v3_evaluation.py backend/app/modules/decisions/v3_evaluation_fixtures.py backend/scripts/run_v3_shadow_evaluation.py
backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_v3_evaluation.py backend/tests/unit/test_v3_evaluation_cli.py backend/tests/scenarios/test_v3_shadow_evaluation_golden.py -q
```

Review `manifest.json` hashes before transferring artifacts. Do not commit generated output, inject
production credentials, or interpret a synthetic pass as production readiness.
