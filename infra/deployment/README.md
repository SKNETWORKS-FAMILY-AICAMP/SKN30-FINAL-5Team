# Deployment

The approved AWS staging baseline is one EC2 Docker Compose host for FastAPI and Qdrant, with the
separate Aurora PostgreSQL cluster as the source of truth. This is a staging/demo topology, not a
high-availability production architecture.

## AWS staging baseline

`compose.staging.yaml` runs only FastAPI and Qdrant. The API binds to EC2 loopback until a reviewed
domain and TLS reverse proxy are configured; Qdrant is reachable only on the Compose network.

The public service runs the approved V3 route. Its canonical deployment always combines the base,
authenticated-Qdrant and V3-production overlays. `infra/deployment/.env.staging` is generated on
the host from AWS Secrets Manager and is never committed, printed or copied from a developer `.env`
file.

```bash
docker compose --env-file infra/deployment/.env.staging \
  -f infra/deployment/compose.staging.yaml \
  -f infra/deployment/compose.staging.qdrant.yaml \
  -f infra/deployment/compose.staging.v3production.yaml config --quiet
docker compose --env-file infra/deployment/.env.staging -f infra/deployment/compose.staging.yaml -f infra/deployment/compose.staging.qdrant.yaml -f infra/deployment/compose.staging.v3production.yaml build api
docker compose --env-file infra/deployment/.env.staging -f infra/deployment/compose.staging.yaml -f infra/deployment/compose.staging.qdrant.yaml -f infra/deployment/compose.staging.v3production.yaml run --rm --no-deps api \
  uv run --no-sync alembic -c backend/alembic.ini upgrade head
docker compose --env-file infra/deployment/.env.staging -f infra/deployment/compose.staging.yaml -f infra/deployment/compose.staging.qdrant.yaml -f infra/deployment/compose.staging.v3production.yaml up -d
docker compose --env-file infra/deployment/.env.staging -f infra/deployment/compose.staging.yaml -f infra/deployment/compose.staging.qdrant.yaml -f infra/deployment/compose.staging.v3production.yaml ps
for attempt in $(seq 1 24); do
  curl --fail http://127.0.0.1:8000/api/v1/health/ready && break
  sleep 5
done
```

Do not expose ports 8000, 6333, 6334 or 5432 in the EC2 security group. Only 80 and 443 are public,
and they terminate at Caddy; the API keeps its own port on loopback so `curl 127.0.0.1:8000` still
works over SSH for operators. OpenAI credentials are not part of this baseline and require a
separately rotated staging credential and provider approval.

## Birthdate encryption with AWS KMS

Staging and production never use `BIRTHDATE_ENCRYPTION_KEY_BASE64`; that setting remains restricted
to local and test environments. Configure a symmetric customer-managed KMS key with the alias
`alias/helkki-staging-birthdate`, then set these non-secret values in `.env.staging`:

```dotenv
AWS_REGION=ap-northeast-2
BIRTHDATE_KMS_KEY_ID=alias/helkki-staging-birthdate
```

The API obtains AWS credentials from the EC2 instance role. Do not create or inject static
`AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` values. Attach
`infra/aws/ec2-staging-secrets-policy.json` to that role; its KMS statement permits only `Encrypt`
and `Decrypt` on a key carrying the expected alias. The KMS key policy must also allow IAM policies
in this account to delegate access.

The database stores a versioned KMS ciphertext blob. KMS encryption context binds it to a one-way
hash of the internal user ID; neither the birthdate nor the raw user ID is placed in CloudTrail's
logged encryption context. Verify the role and key before restarting the API:

```bash
aws kms describe-key \
  --region ap-northeast-2 \
  --key-id alias/helkki-staging-birthdate \
  --query 'KeyMetadata.[KeyState,KeyUsage,KeySpec]' \
  --output text
```

The expected result is `Enabled`, `ENCRYPT_DECRYPT`, and `SYMMETRIC_DEFAULT`. A missing key setting
keeps onboarding fail-closed with `503 PROFILE_CONFIGURATION_UNAVAILABLE`; a denied KMS call is
translated to the same safe response without logging the birthdate or provider exception.

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

Point the app at the new origin with `EXPO_PUBLIC_API_BASE_URL=https://api.<your-domain>`.
Pass the origin only, without the `/api/v1` suffix: the client appends that prefix itself
(`frontend/src/api/client.ts`), so including it here produces `/api/v1/api/v1/...` and every
request 404s.

### Landing page and Expo web app on separate hosts

Use `compose.staging.web.yaml` when the public entry page and the Expo web app
share one Caddy instance. The overlay serves the landing page on `WEB_DOMAIN`,
preserves `WEB_DOMAIN/api/*` for backward compatibility, serves the existing
Expo export on `APP_DOMAIN`, and redirects `APEX_DOMAIN` to `WEB_DOMAIN`.

Build a new Expo web release when needed with:

```bash
cd frontend
npm run build:web
```

Set `LANDING_SITE_ROOT` and `WEB_APP_ROOT` to absolute host paths. Set
`CORS_ALLOWED_ORIGINS` to the exact `https://APP_DOMAIN` origin because an Expo
bundle built with `WEB_DOMAIN` as its API base makes a cross-origin API request
after the app moves to `APP_DOMAIN`.

```bash
docker compose --env-file infra/deployment/.env.staging \
  -f infra/deployment/compose.staging.yaml \
  -f infra/deployment/compose.staging.web.yaml config --quiet
docker compose --env-file infra/deployment/.env.staging \
  -f infra/deployment/compose.staging.yaml \
  -f infra/deployment/compose.staging.web.yaml up -d api caddy
```

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

`compose.staging.yaml` stays fail-closed on its own and is **not executable for a real staging index
build**. It declares `QDRANT_URL=http://qdrant:6333` and `QDRANT_TLS_ENABLED=false`, while
application `Settings` requires both HTTPS and `QDRANT_API_KEY` whenever `APP_ENV=staging` and
`QDRANT_ENABLED=true`. That is deliberate: keep the base file's `QDRANT_ENABLED=false` and
`V3_PRODUCTION_PROMOTION_APPROVED=false`, and do not weaken the application validation in an
infrastructure-only change. Enabling Qdrant is the overlay's job, not the baseline's.

The topology choice was between:

1. an external staging Qdrant endpoint with authentication and TLS;
2. an explicit, reviewed security exception or design change for the internal Compose endpoint; or
3. authentication and TLS configured on the Compose Qdrant service itself.

**Topology 1 is the approved and deployed choice** (`docs/tasks/TASK-AGENT-150.md`). The staging
endpoint terminates TLS with a publicly trusted certificate and requires an API key; both the
endpoint and the key are injected from AWS Secrets Manager. The schema-v2 index is built and active
against catalog UUID `419eaab4-0b93-4a9f-8705-132d46cc681f`; that record, including the rollback
target, lives in the task document rather than here.

After approval, pass the endpoint and secret through the deployment secret path appropriate to the
selected topology. Do not put a credential in Compose, this README, `.env.staging.example`, command
history, logs or evidence. The present endpoint is Compose-network-only; ports 6333 and 6334 are not
published to the host.

### Applying topology 1

`compose.staging.qdrant.yaml` is the overlay for topology 1. It is checked in but must not be used
until that approval is recorded, because it is what actually turns Qdrant retrieval on.

```bash
docker compose --env-file infra/deployment/.env.staging   -f infra/deployment/compose.staging.yaml   -f infra/deployment/compose.staging.qdrant.yaml up -d
```

Both `-f` flags are required, in that order. The overlay re-declares `QDRANT_ENABLED`, `QDRANT_URL`
and `QDRANT_TLS_ENABLED` because `compose.staging.yaml` pins them in its `environment:` block, which
outranks `env_file:`: setting them in `.env.staging` alone is read but silently ignored, leaving the
API pointed at the in-Compose plaintext endpoint. The overlay also resets the API's `depends_on` and
parks the in-Compose `qdrant` service under an unused profile, so only `api` and `caddy` start.

Enabling Qdrant is necessary but not sufficient for vector retrieval: the retriever is only
constructed on the V3 path, so the production profile below is what actually puts it in use.

### Applying the public V3 production profile

`compose.staging.v3production.yaml` makes V3 authoritative and is the required overlay that puts
Qdrant retrieval and the LLM multi-agent path on every public routine-creation request. Apply it on
top of the Qdrant overlay, which supplies `OPENAI_API_KEY`
and the index this profile ranks against:

```bash
docker compose --env-file infra/deployment/.env.staging   -f infra/deployment/compose.staging.yaml   -f infra/deployment/compose.staging.qdrant.yaml   -f infra/deployment/compose.staging.v3production.yaml up -d
```

The approved agent model code is `gpt-5.6-terra`, and `LLM_AGENTS_APPROVED_MODEL_CODES` must contain
it. `backend/app/integrations/llm_agents/openai.py` ANDs every provider gate: if any one fails, the
chat model is `None`, the V3 runtime is never built, and the retriever is never constructed. The
runtime is not composed and routine creation must not silently use the legacy service. Confirm
retrieval positively rather
than reading a healthy `/health/ready` as proof.

`V3_PRODUCTION_PROMOTION_APPROVED=true` is part of this overlay. It records the approved production
composition and must never be set by a client request or the shadow evaluator.

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
