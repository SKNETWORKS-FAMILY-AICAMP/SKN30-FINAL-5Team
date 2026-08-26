# Deployment

The approved AWS staging baseline is one EC2 Docker Compose host for FastAPI and Qdrant, with the
separate Aurora PostgreSQL cluster as the source of truth. This is a staging/demo topology, not a
high-availability production architecture.

## AWS staging baseline

`compose.staging.yaml` runs only FastAPI and Qdrant. The API binds to EC2 loopback until a reviewed
domain and TLS reverse proxy are configured; Qdrant is reachable only on the Compose network.

The baseline is intentionally fail-closed: V3, LLM calls, Qdrant retrieval and production promotion
remain disabled. `infra/deployment/.env.staging` is generated on the host from AWS Secrets Manager
and must contain only `DATABASE_URL` and non-secret operational settings. Never copy a developer
`.env` file to EC2.

```bash
docker compose -f infra/deployment/compose.staging.yaml config --quiet
docker compose -f infra/deployment/compose.staging.yaml build api
docker compose -f infra/deployment/compose.staging.yaml run --rm --no-deps api \
  uv run --no-sync alembic -c backend/alembic.ini upgrade head
docker compose -f infra/deployment/compose.staging.yaml up -d
docker compose -f infra/deployment/compose.staging.yaml ps
for attempt in $(seq 1 24); do
  curl --fail http://127.0.0.1:8000/api/v1/health/ready && break
  sleep 5
done
```

Do not expose ports 8000, 6333, 6334 or 5432 in the EC2 security group. Public traffic is enabled
only after a domain is attached and the TLS reverse proxy exposes 80/443. OpenAI credentials are
not part of this baseline and require a separately rotated staging credential and provider approval.

DRAFT catalog import still permits only `local` or `test`, and that gate stays closed in staging; do
not reopen it by changing the container environment. The reviewed release path is separate: because
`import_v2_bundle` reaches the importer only after all four manifests match an exact approval-registry
entry, that one path is allowed to run under `APP_ENV=staging`. Production is still excluded and needs
its own release decision.

Load the approved catalog into Aurora with:

```bash
uv run --no-sync alembic -c backend/alembic.ini upgrade head
uv run --no-sync python -m backend.scripts.catalog_promote_v2
uv run --no-sync python -m backend.scripts.catalog_activate activate exercise-catalog-v2.0.0-final
```

`catalog_activate` is run without `--demo-unreviewed`: the registry already carries the
`DOMAIN_REVIEWER` sign-off (`V2-PROMOTION-APPROVAL-2026-08-25-R01`), so the repository writes
`PRODUCTION_APPROVED` on its own. Reaching for that flag here would record a review that did not
happen. The four unreviewed KSPO/wger catalogs stay `DRAFT`/`AGENT_ONLY` and are never activated.
