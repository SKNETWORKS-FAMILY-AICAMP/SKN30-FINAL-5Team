# Local Docker

Issue #149에서 승인된 FastAPI, PostgreSQL 16, Qdrant 로컬 검증 구성입니다. production 배포 선언이
아니며 실제 build, container 실행, DB/Qdrant 연결과 최종 검증은 개발팀장이 수행합니다.

## Services and defaults

| Service | Container port | Default host port | Readiness | Persistent volume |
|---|---:|---:|---|---|
| `api` | 8000 | `API_PORT=8000` | `/api/v1/health/ready` | 없음 |
| `postgres` | 5432 | `POSTGRES_PORT=55432` | `pg_isready` | `postgres_data` |
| `qdrant` | 6333/6334 | `QDRANT_HTTP_PORT=6333`, `QDRANT_GRPC_PORT=6334` | `/readyz` | `qdrant_data` |

모든 host port는 loopback에만 bind됩니다. 기본 API profile은 `LEGACY`이며 V3, Qdrant retrieval,
LLM Agent, narration과 production promotion은 비활성입니다. Qdrant container가 실행되는 사실만으로
API 결정 경로가 활성화되지 않습니다.

`exercise_app_demo`는 local/demo 전용이고 `POSTGRES_TEST_DB=exercise_app_test`는 test 전용입니다.
두 이름을 같게 설정하지 않습니다. Compose는 test DB를 자동 생성하지 않습니다.

## Prepare and start

```powershell
Copy-Item infra/docker/.env.example infra/docker/.env
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml config
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml build api
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml up -d
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml ps
```

예상 startup 순서는 PostgreSQL health 통과 후 API 시작입니다. Qdrant는 독립적으로 readiness를
보고하며 기본 API startup dependency가 아닙니다. API live/ready 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

## Explicit one-shot release commands

다음 명령은 API startup에 숨겨져 있지 않습니다. 비어 있거나 폐기 가능한 demo DB에서 순서대로
명시적으로 실행합니다.

```powershell
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml run --rm --no-deps api uv run --no-sync alembic -c backend/alembic.ini upgrade head
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml run --rm --no-deps api uv run --no-sync python -m backend.scripts.catalog_promote_v2
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml run --rm --no-deps api uv run --no-sync python -m backend.scripts.catalog_activate activate exercise-catalog-v2.0.0-final
```

Test DB가 필요할 때만 별도로 생성하고 demo DB URL과 혼용하지 않습니다.

```powershell
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml exec postgres sh -c 'createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_TEST_DB"'
```

## Failure and fallback verification

Qdrant 장애 fallback은 Qdrant를 명시적으로 연동하는 별도 승인 설정에서만 검증합니다. 기본
`QDRANT_ENABLED=false`에서는 API가 Qdrant에 연결하지 않습니다. 개발팀장은 승인된 embedding 설정을
외부 환경에서 주입한 뒤 Qdrant를 중지하고, 결정 결과가 PostgreSQL canonical 재검증과 기존
deterministic fallback을 유지하는지 확인해야 합니다. 실제 key나 provider credential은 `.env`나
명령 기록에 넣지 않습니다.

상태와 로그 확인 시 request body, bearer token, check-in 또는 건강 데이터를 복사하지 않습니다.

```powershell
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml ps
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml logs api --tail 100
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml stop qdrant
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml start qdrant
```

## Stop, restart, and rollback

```powershell
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml down
docker compose --env-file infra/docker/.env -f infra/docker/compose.yaml up -d
```

`down`은 named volume을 보존합니다. 데이터를 삭제해야 할 때는 개발팀장이 대상 project와 volume을
확인한 뒤 별도로 수행합니다. 코드 rollback은 이 PR을 revert합니다. 새 migration이나 schema 변경은
없으므로 DB downgrade는 필요하지 않습니다.

## Development lead evidence

PR에는 실행 SHA, Docker/Compose version, 실제 port mapping, image digest, 세 readiness 결과,
migration head, V2 exact count와 ACTIVE catalog 수, 재시작 후 volume 보존, Qdrant 중단 fallback 결과를
기록합니다. 이 증적 전에는 task를 `COMPLETE`로 변경하지 않습니다.
