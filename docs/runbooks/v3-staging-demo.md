# V3 staging demo application composition

## Scope

This runbook enables the complete V3 application path for a controlled staging demo. It is
independent from production promotion. `READY_FOR_DEMO` means only that the staging demo checklist
was completed; it is not production approval, clinical validation, medical-device validation, or
permission to bypass the V3 production promotion gate.

An external exercise-rehabilitation instructor review may be recorded only as a non-clinical visual
review of exercise presentation and routine plausibility. It is not a diagnosis, prescription,
clinical efficacy assessment, or substitute for the required product, engineering, safety and
privacy approvals.

## Required process environment

Provide values through the staging deployment environment or secret store. Do not put credentials
in `.env`, fixtures, logs, screenshots, traces, or this document.

```text
APP_ENV=staging
V3_EXECUTION_PROFILE=DEMO
V3_LANGGRAPH_ENABLED=true
V3_REGENERATION_ENABLED=true
LLM_AGENTS_ENABLED=true
LLM_AGENTS_PROVIDER_CODE=<approved-provider-code>
LLM_AGENTS_MODEL_CODE=<approved-model-code>
LLM_AGENTS_APPROVED_MODEL_CODES=<sorted-approved-model-codes>
```

The provider credential is supplied only by the deployment secret store. When the provider is
missing, times out, fails, or returns invalid structured output, the application must use the
defined deterministic fallback and must not expose the provider exception as a 5xx response body.

## Profile behavior

| Profile | Creation behavior |
|---|---|
| `LEGACY` | Existing deterministic decision path and response contract |
| `SHADOW` | Existing response remains authoritative; V3 runs only for sanitized shadow evidence |
| `DEMO` | V3 creation, persistence and regeneration are authoritative; staging only |
| `PRODUCTION` | V3 only when the separately reviewed production promotion gate allows it; otherwise legacy |

`APP_ENV=production` with `V3_EXECUTION_PROFILE=DEMO` is rejected during settings validation before
the application starts. Existing V3 feature flags remain supported during migration, but the default
profile is `LEGACY` and no flag may silently promote V3 production traffic.

## Manual verification

1. Start the backend with staging configuration and no local `.env` credential loading.
2. Create a decision and verify the response still validates as the documented `DecisionResponse`.
3. Verify the stored run contains three specialist proposals separately from Coordinator attempts
   and the final decision.
4. Repeat the same request with the same `Idempotency-Key`; verify the stored response is replayed.
5. Regenerate without resubmitting check-in input and verify a meaningful difference code.
6. Simulate provider timeout and invalid structured output; verify a deterministic fallback result.
7. Submit a safety-veto fixture; verify zero provider calls and that no Coordinator output overrides it.
8. Inspect sanitized logs/traces for direct identifiers, raw health data, raw wearable samples,
   calendar text, credentials, prompts, provider raw responses, and hidden reasoning.
9. Confirm no generated staging output or run artifact is added to Git.
