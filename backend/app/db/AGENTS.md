# Database boundary rules

- Primary owner: backend engineer.
- PostgreSQL is the source of truth.
- Keep relationships, queryable fields, FK, unique, and CHECK constraints explicit.
- JSONB is limited to versioned snapshots, proposals, and metadata.
- Schema changes require `docs/DATA_MODEL.md` and an Alembic migration.
- Preserve agent, policy, catalog, safety, duration, coordinator, and prompt versions.
- Account deletion must cover all user-linked tables without retaining re-identifiable decision logs by default.
