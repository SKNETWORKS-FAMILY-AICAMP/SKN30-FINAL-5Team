# Catalog module

검수된 운동, FITT 속성, 대체 관계, 안전 규칙, 출처·라이선스를 조회하는 모듈 경계입니다.

현재 구현은 DRAFT catalog와 파생 안전 규칙·대체 관계 bundle importer를 포함합니다.

- catalog schema 1.1은 `difficulty_code`를 운동 자체 난이도로 사용하고
  `beginner_suitable` 입력을 거부합니다. schema 1.0은 기존 승인 bundle 재현을 위해 해당 필드를
  검증 후 폐기하는 읽기 호환만 유지합니다.
- 처방의 `experience_level_code`는 `BEGINNER`와 `INTERMEDIATE`를 허용합니다. schema 1.1 bundle은
  운동 난이도 이하의 처방을 fail-closed 처리하므로 `BEGINNER` 운동에는 두 처방 레벨을,
  `INTERMEDIATE` 운동에는 `INTERMEDIATE` 처방만 허용합니다.

- local/test에서만 `seed_manifest.json`과 exercise JSONL을 검증·적재합니다.
- Pydantic `StrEnum`의 기존 `mvp-v1`과 additive `catalog-v2` code set을 사용합니다. V2 import는
  14개 body-focus만 허용하고 legacy `UPPER_BODY`·`LOWER_BODY`, `BENCH`·`CHAIR`, `OUTDOOR`
  대체관계를 fail-closed로 거부합니다.
- version/hash 멱등성, artifact 경계, hash/byte/record count와 transaction 원자성을
  fail-closed로 검증합니다.
- 원본 DRAFT 매니페스트의 `DOMAIN_APPROVED`는 파이프라인 호환 상태이며 그 자체로 production
  승격을 뜻하지 않습니다.
- V2 안전 규칙·대체관계의 version, source hash/metadata, timezone audit timestamp를 검증하며
  입력의 `production_eligible`은 반드시 false여야 합니다. repository는 검증된 manifest에서
  canonical DB metadata를 만들고 record metadata를 그대로 신뢰해 승격하지 않습니다.
- `python -m backend.scripts.catalog_data_load load`는 네 카탈로그와 안전 규칙 354개,
  대체 관계 238개를 한 transaction으로 적재하며 재실행은 멱등합니다.
- Issue 53에서 별도 승인된 안전 규칙 `mvp-v0.3.0` 354건과 대체 관계 `mvp-v0.2.0`
  238건은 승인 registry의 version/hash/count가 모두 일치할 때 `production_eligible=true`로
  적재됩니다. 그 밖의 파생 데이터는 계속 false로 fail-closed 처리합니다.
- 현재 매니페스트에 없는 URL·license code는 추정하지 않습니다. source 매니페스트 전체를
  보존하므로 후속 schema가 해당 필드를 제공하면 손실 없이 저장할 수 있습니다.
- `python -m backend.scripts.catalog_promote_v2`는 V1 경로와 분리된 V2 전용 명령입니다. 승인된
  bundle·taxonomy hash와 네 artifact의 version/hash/count를 exact-match로 검증하고 한 transaction에
  적재합니다. 기본 동작은 DRAFT 유지이며 `--activate`를 명시해야 activation gate까지 실행합니다.
- media artifact는 선택적입니다. 포함된 경우 canonical S3 key, 실제 exercise FK, rights evidence와
  media approval registry를 검증·보존하고, 승인 조건을 모두 만족한 media만 조회합니다.

## V2 release verification runbook

아래 절차는 실제 PostgreSQL을 사용할 권한이 있는 개발팀장이 빈 전용 `_test` 데이터베이스에서
수행합니다. 코딩 에이전트는 DB 연결이나 migration 적용을 실행하지 않습니다.

```powershell
$env:APP_ENV = "test"
$env:TEST_DATABASE_URL = "postgresql+psycopg://exercise_app:<test-password>@localhost:5432/exercise_app_v2_release_test"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini downgrade base
uv run alembic -c backend/alembic.ini upgrade head
uv run python -m backend.scripts.catalog_promote_v2
uv run python -m backend.scripts.catalog_promote_v2
uv run python -m backend.scripts.catalog_promote_v2 --activate
uv run python -m backend.scripts.catalog_promote_v2 --activate
uv run pytest backend/tests/unit/test_catalog_data_bundle_importer.py backend/tests/unit/test_backend_workflow.py -vv --maxfail=1
uv run pytest backend/tests/integration/test_catalog_v2_release_flow.py -vv --maxfail=1
```

예상 결과는 current Alembic head, import 직후 DRAFT, catalog/safety/alternative/goal-tag/prescription
각각 `102/394/285/102/137`, activation 후 ACTIVE 1건, 재실행 후 동일 count다. hash/count/version
변조와 synthetic 중간 실패는 오류를 반환하고 catalog·derived table에 부분 행을 남기지 않아야 한다.
현재 승인 bundle에는 media artifact가 없으므로 공개 repository 결과의 `media_asset_key`는 모두
`null`이어야 하며, registry 승인 metadata가 없는 AVAILABLE media는 비노출되고 activation을
차단해야 한다.

실행 SHA, DB 이름, Alembic head, 각 count, ACTIVE count, media 결과와 rollback assertion을 PR에
기록합니다. rollback은 이 PR을 revert해 V2 job과 테스트·runbook만 제거하는 방식이며 migration,
V1 importer, DB schema와 적재 데이터에는 변경이 없습니다.
