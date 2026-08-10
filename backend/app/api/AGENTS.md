# API boundary rules

- All public product paths use `/api/v1`.
- Use Pydantic schemas, UUIDs, timezone-aware timestamps, stable machine codes, and the common error envelope.
- Mutation endpoints define idempotency behavior.
- Routes may call application services only; they do not call repositories, rule engines, or LLM providers directly.
- Do not expose internal prompts, hidden reasoning, rule internals, provider tokens, or raw health data.
