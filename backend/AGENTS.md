# Backend working rules

- Primary owner: backend engineer; agent/rule areas are owned by the development and data lead.
- Routes validate and delegate. Business rules do not belong in route handlers.
- Application services own use cases, transactions, and idempotency.
- Domain code must not depend on FastAPI, SQLAlchemy models, Firebase SDK, or LLM SDK.
- Repositories own database access; integrations own external providers.
- Public API changes require `docs/API_CONTRACT.md`, examples, frontend review, and compatibility tests.
- Schema changes require `docs/DATA_MODEL.md`, Alembic migration, and rollback or forward-fix strategy.
- Required agent/rule/persistence failure must not return a successful workout plan.
- Never log identifiers, tokens, emails, full names, raw check-ins, or raw wearable data.
