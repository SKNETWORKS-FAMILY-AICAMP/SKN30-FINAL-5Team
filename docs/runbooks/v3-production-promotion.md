# V3 production promotion review gate

## Scope

The V3-C2 evaluator determines whether a completed V3-C1 shadow evidence bundle is internally
consistent and meets an approved threshold reference. Its strongest positive result is
`READY_FOR_HUMAN_APPROVAL`: the evidence may proceed to human approval review. It never means
production is approved, never changes a feature flag, and never connects V3 to the production
decision service.

The committed 20-case synthetic harness proves the evaluation machinery and safety fixtures work.
It is not completed staging evidence, a live-provider run, an expert review, or production approval.

## Required inputs

- `summary.json` from one immutable shadow run
- `manifest.json` from the same run
- the corresponding `results.jsonl` beside the manifest
- completed expert-review JSONL
- an approved `v3-promotion-threshold-v1` JSON reference
- an approved `v3-approved-pricing-v1` JSON reference when cost is evaluated

Threshold values are governance inputs. The evaluator has no numeric threshold defaults. The
versioned threshold reference identifies its fixture, harness, graph, policy, catalog, prompt,
provider, model, pricing, currency, approval record, and timezone-aware effective time.

## Run

From the repository root:

```powershell
backend\.venv\Scripts\python.exe -m backend.scripts.evaluate_v3_promotion `
  --summary outputs\v3-shadow\staging-run\summary.json `
  --manifest outputs\v3-shadow\staging-run\manifest.json `
  --expert-reviews outputs\v3-shadow\staging-run\completed_expert_reviews.jsonl `
  --threshold-reference approved\v3-promotion-threshold.json `
  --pricing-reference approved\v3-pricing-reference.json `
  --output-directory outputs\v3-shadow\staging-run\promotion
```

The CLI performs no provider, database, FastAPI, or network operation. Output is restricted to the
repository's `outputs/v3-shadow` subtree:

- `promotion_decision.json`: canonical, schema-versioned decision with stable SHA-256 hash
- `promotion_decision.md`: human-readable status, machine reason codes, and the approval warning

`BLOCKED` and `NOT_EVALUATED` are valid evaluation outcomes and return a successful CLI exit.
Malformed JSON, schema violations, NaN/Infinity, privacy/extra fields, missing input files, and path
escape attempts are contract errors and return a non-zero exit without writing a decision.

## Fail-closed interpretation

`READY_FOR_HUMAN_APPROVAL` requires all artifact hashes, record counts, internal summary/result
hashes, and fixture/harness/runtime versions to agree. It also requires:

- 100% safety-invariant pass rate, zero veto overrides, and zero constraint violations
- approved minimum case and repeat counts
- approved structured-output, latency, fallback, and expert-agreement thresholds
- complete expert review records with role, public reason codes, and timezone-aware timestamps
- verifiable token and cost data with an exactly matching provider/model/currency pricing reference
- schema allowlisted, identifier-free evidence

Unavailable nullable metrics remain unavailable; they are never treated as zero. Every blocker is a
canonical `V3PromotionReasonCode`, and identical inputs produce byte-stable JSON and the same
decision hash.

## Human approval and production change

After `READY_FOR_HUMAN_APPROVAL`, all of the following remain manual and outside this evaluator:

1. PM confirms product scope and user-impact readiness.
2. Development lead approves the threshold reference and production composition change.
3. Backend owner approves deployment, rollback, observability, and capacity readiness.
4. External exercise-domain expert approves completed review evidence.
5. Owners record approval references and review the exact evidence/threshold hashes.
6. A separate production-change PR connects the approved composition and changes server-owned
   flags under rollout and rollback controls.

Until that separate approval and change are complete, `V3_LANGGRAPH_ENABLED` and
`V3_REGENERATION_ENABLED` production activation remains false. No evaluator output may be used to
edit these values automatically.
