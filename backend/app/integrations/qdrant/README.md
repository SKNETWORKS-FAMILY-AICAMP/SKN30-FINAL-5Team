# Qdrant exercise derived index

## Runtime boundary

```text
PostgreSQL eligible UUIDs
-> Qdrant query_points(has_id + version filters)
-> UUID/score only
-> PostgreSQL canonical revalidation in the later application-loader integration
```

Collection names are generated only from configured environment and catalog/embedding/index machine versions.
New builds use immutable collections. Exact UUID count and `build_hash` are checked before one atomic alias update.
Build retries upsert the same PostgreSQL exercise UUID, so they do not create duplicate points. This code never
deletes a collection.

## Local server verification

The official-client local integration test requires no Docker:

```powershell
uv run pytest backend/tests/integration/test_qdrant_local.py -m qdrant_integration
```

For a server-mode verification, start the PoC-verified image outside production data paths:

```powershell
docker run --rm -p 127.0.0.1:6333:6333 -p 127.0.0.1:6334:6334 `
  qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c
```

Do not enable a build with the deterministic fake embedding adapter. Deployment owners must first approve a
provider/model revision, license, dimension, metric, secret delivery, TLS/auth, monitoring and rollback runbook.
