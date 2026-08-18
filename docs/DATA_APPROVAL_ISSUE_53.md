# Issue 53 derived safety data approval

## Decision

On 2026-08-18, the development lead recorded completion of PM and domain review and approved
the complete reviewed derived-data sets below for runtime use.

| Data set | Version | Manifest SHA-256 | Records | Decision |
|---|---|---|---:|---|
| Exercise safety rules | `mvp-v0.3.0` | `d3281fb7bcf85d614ace027b1a50587430a6578733aab765f0d0b805dd85f51b` | 354 | Production eligible |
| Exercise alternatives | `mvp-v0.2.0` | `9875cecc075ff1e3f827243f1ebe4db475dfe9a86985a122febaf2558b81ec7f` | 238 | Production eligible |

Approval record code: `ISSUE-53-PM-DOMAIN-APPROVAL`

Required approval roles recorded: `DEVELOPMENT_LEAD`, `PM`, `DOMAIN_REVIEWER`.

## Guardrails

- Approval applies only to the exact versions, manifest hashes, and record counts above.
- A changed hash, version, or count remains production-ineligible and requires a new approval.
- Runtime safety evaluation remains deterministic and rechecks alternatives against current
  discomfort, chronic attention areas, location, and equipment.
- This approval does not permit diagnosis, treatment, or medical prescription language.

## Rollback

Downgrading migration `0016_approve_safety_data` marks these exact sets production-ineligible,
removes their stored approval metadata, and restores the original fail-closed constraints.
