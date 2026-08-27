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

## Staging one-shot live evidence

The stored/fake command above remains the default development and CI path. It never constructs a
provider. A live staging run uses the separate `backend.scripts.run_v3_staging_shadow` entry point;
it is not imported by FastAPI startup or connected to a public request path.

The operator must provide these environment variable names through the staging process environment
or deployment secret store. Do not place their values in this document, shell history, fixtures, or
committed files:

- `APP_ENV`
- `LLM_AGENTS_ENABLED`
- `LLM_AGENTS_PROVIDER_CODE`
- `LLM_AGENTS_MODEL_CODE`
- `LLM_AGENTS_APPROVED_MODEL_CODES`
- `LLM_AGENTS_MAX_ATTEMPTS`
- `LLM_AGENTS_TIMEOUT_SECONDS`
- `LLM_AGENTS_MAX_OUTPUT_TOKENS`
- `V3_LANGGRAPH_ENABLED`
- `V3_SHADOW_EVALUATION_ENABLED`
- `OPENAI_API_KEY`

Before live shadow execution, verify that the request catalog version, the PostgreSQL active catalog
and the active vector-index registry all identify `exercise-catalog-v2.0.1-final`. The registry's
embedding model, dimension, input schema and distance metric must exactly match the process settings,
and its Qdrant alias must resolve to the verified immutable collection. A missing registry or a
v2.0.0 registry is a deterministic fallback case, not successful v2.0.1 vector evidence.

The staging CLI deliberately disables dotenv loading. It consumes only the current process
environment, so it does not read `backend/.env`. Before running, confirm the selected model is in the
deployment-approved allowlist and verify the current provider pricing in the separately approved
pricing source. Do not estimate or write a cost when that reference is absent.

Calculate the conservative call upper bound before opt-in:

```text
fixture case count × repeat count × 8 bounded graph invocation slots × maximum attempts
```

The eight slots are three initial specialists, up to three reviews, one Coordinator call, and one
repair. Safety-terminal cases still make zero provider calls, but the declared budget intentionally
uses the larger worst case. The CLI rejects a smaller budget before constructing the provider.

Use a unique structured run ID and replace the placeholders only in the local command invocation:

```powershell
.venv\Scripts\python.exe -m backend.scripts.run_v3_staging_shadow `
  --run-id <unique-run-id> `
  --repeat-count <bounded-repeat-count> `
  --maximum-provider-calls <calculated-upper-bound> `
  --run-timeout-seconds <bounded-timeout> `
  --allow-provider-calls
```

Omitting `--allow-provider-calls`, using a non-staging environment, missing any gate, selecting a
model outside the allowlist, omitting the credential, or declaring insufficient budget fails before
provider construction. Timeout, interruption, provider exception, partial results, and report-write
failure return a non-zero exit. Evidence stores only canonical failure codes; raw responses,
exceptions, prompts, messages, credentials, identifiers, raw health/wearable values, vectors, and
embeddings are not manifest fields.

Successful output is written only beneath `outputs/v3-shadow/<run-id>/` and includes the five C1
reports plus `staging_run_manifest.json`. The staging manifest records the request/budget hash,
provider/model and graph/policy/catalog/prompt versions, expected and actual counts, timestamps, file
hashes, status, and its own canonical hash. This directory is gitignored local evidence and must not
be committed.

After a run, verify every hash and record count, inspect the hard safety gates, and send the expert
review template through the separately approved review process. A successful staging run does not
approve thresholds, complete expert review, enable the production graph, or authorize use of real
user data. Production promotion remains a separate development-lead decision.

Provider schemas must exclude reproducibility hashes such as `proposal_hash` and `plan_hash`.
The server computes these fields after JSON-mode validation; a model-supplied hash is discarded and
must never become canonical state.
