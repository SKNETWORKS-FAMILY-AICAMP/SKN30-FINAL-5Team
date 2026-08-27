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
docker compose --env-file infra/deployment/.env.staging \
  -f infra/deployment/compose.staging.yaml config --quiet
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

Do not expose ports 8000, 6333, 6334 or 5432 in the EC2 security group. Only 80 and 443 are public,
and they terminate at Caddy; the API keeps its own port on loopback so `curl 127.0.0.1:8000` still
works over SSH for operators. OpenAI credentials are not part of this baseline and require a
separately rotated staging credential and provider approval.

## TLS and domain

The mobile client is the reason this step is mandatory rather than cosmetic: iOS App Transport
Security and the Android cleartext policy both refuse a plain `http://` origin, so the Expo app
cannot reach staging until it is served under a real certificate.

Order matters. Caddy requests a certificate as soon as it starts and the ACME HTTP-01 challenge
fails if the record does not resolve yet.

1. Point an A record at the EC2 public IP and wait for it to resolve:
   `dig +short api.<your-domain>` must return that IP.
2. Open inbound `80` and `443` (TCP, plus `443/udp` for HTTP/3) in the security group. Port 80 is
   required for the challenge and cannot be skipped. Leave 8000, 6333, 6334 and 5432 closed.
3. Set `API_DOMAIN` and `ACME_EMAIL` in `infra/deployment/.env.staging`. Both are required; Compose
   refuses to start without them rather than serving an unencrypted default.
4. Add the Expo web origin to `CORS_ALLOWED_ORIGINS` if the browser demo is used. Native builds send
   no `Origin` header and need nothing. A wildcard is rejected at startup.
5. Bring the stack up and confirm the certificate:

```bash
docker compose -f infra/deployment/compose.staging.yaml up -d
docker compose -f infra/deployment/compose.staging.yaml logs caddy | grep -i "certificate obtained"
curl --fail https://api.<your-domain>/api/v1/health/ready
```

Point the app at the new origin with `EXPO_PUBLIC_API_BASE_URL=https://api.<your-domain>/api/v1`.

The `caddy_data` volume holds the certificate and the ACME account key. Do not prune it between
deploys: re-requesting on every restart reaches the Let's Encrypt rate limit within a day. If a
certificate must be reissued, use the staging ACME endpoint first.

DRAFT catalog import still permits only `local` or `test`, and that gate stays closed in staging; do
not reopen it by changing the container environment. The reviewed release path is separate: because
`import_v2_bundle` reaches the importer only after all four manifests match an exact approval-registry
entry, that one path is allowed to run under `APP_ENV=staging`. Production is still excluded and needs
its own release decision.

Load the approved catalog into Aurora with:

```bash
uv run --no-sync alembic -c backend/alembic.ini upgrade head
uv run --no-sync python -m backend.scripts.catalog_promote_v2
uv run --no-sync python -m backend.scripts.catalog_activate activate exercise-catalog-v2.0.1-final
```

`catalog_activate` is run without `--demo-unreviewed`: the registry already carries the
`DOMAIN_REVIEWER` sign-off (`V2-PROMOTION-APPROVAL-2026-08-25-R01`), so the repository writes
`PRODUCTION_APPROVED` on its own. Reaching for that flag here would record a review that did not
happen. The four unreviewed KSPO/wger catalogs stay `DRAFT`/`AGENT_ONLY` and are never activated.

## Qdrant staging readiness and #150 handoff

The checked-in baseline is safe but is **not currently executable for a real staging index build**.
It declares `QDRANT_URL=http://qdrant:6333` and `QDRANT_TLS_ENABLED=false`, while application
`Settings` requires both HTTPS and `QDRANT_API_KEY` whenever `APP_ENV=staging` and
`QDRANT_ENABLED=true`. Keep `QDRANT_ENABLED=false` and
`V3_PRODUCTION_PROMOTION_APPROVED=false`; do not weaken that application validation in an
infrastructure-only change.

Issue #150 remains `BLOCKED` until the backend development lead and security/infrastructure owner
approve exactly one topology:

1. an external staging Qdrant endpoint with authentication and TLS;
2. an explicit, reviewed security exception or design change for the internal Compose endpoint; or
3. authentication and TLS configured on the Compose Qdrant service itself.

After approval, pass the endpoint and secret through the deployment secret path appropriate to the
selected topology. Do not put a credential in Compose, this README, `.env.staging.example`, command
history, logs or evidence. The present endpoint is Compose-network-only; ports 6333 and 6334 are not
published to the host.

Before #150 runs any index builder, an operator with read-only Aurora access must execute the
following queries and transfer only the returned non-secret catalog/registry fields. Do not print
the connection URL or any user data.

```sql
SELECT id, version_code, status_code, review_status_code, review_method_code,
       status_interpretation_code, production_eligible, activated_at,
       exercise_record_count
FROM catalog_versions
WHERE status_code = 'ACTIVE';

SELECT id, version_code, status_code, review_status_code, review_method_code,
       status_interpretation_code, production_eligible, activated_at,
       exercise_record_count
FROM catalog_versions
WHERE version_code = 'exercise-catalog-v2.0.1-final';

SELECT count(*) AS indexable_exercise_count
FROM exercises AS e
JOIN catalog_versions AS c ON c.id = e.catalog_version_id
WHERE c.version_code = 'exercise-catalog-v2.0.1-final'
  AND c.status_code = 'ACTIVE'
  AND c.review_status_code = 'DOMAIN_APPROVED'
  AND c.review_method_code = 'DOMAIN_REVIEWER'
  AND c.status_interpretation_code = 'PRODUCTION_APPROVED'
  AND c.production_eligible IS TRUE
  AND c.activated_at IS NOT NULL
  AND e.review_status_code = 'DOMAIN_APPROVED';

SELECT count(*) AS total_count
FROM vector_index_registry;

SELECT status_code, count(*) AS status_count
FROM vector_index_registry
GROUP BY status_code
ORDER BY status_code;

SELECT vir.id, vir.vector_index_version, vir.collection_name, vir.status_code,
       vir.built_at, vir.activated_at, cv.id AS catalog_id, cv.version_code
FROM vector_index_registry AS vir
JOIN catalog_versions AS cv ON cv.id = vir.catalog_version_id
WHERE cv.version_code IN (
  'exercise-catalog-v2.0.0-final',
  'exercise-catalog-v2.0.1-final'
)
ORDER BY cv.version_code, vir.created_at;
```

If any active catalog field differs from the required UUID/version/approval tuple, or the observed
indexable count differs from the builder's preflight count, stop without creating a collection or
changing an alias. Registry reads in this readiness step are observational only.
