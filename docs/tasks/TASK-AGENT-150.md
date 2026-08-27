# TASK-AGENT-150: Qdrant index 및 V3 staging evidence 수집

- 현재 상태: `BLOCKED` (v2.0.1 staging 자격증명·Qdrant 보안 토폴로지·Aurora read-only 증적 대기)
- 우선순위: `P1`
- GitHub issue: `#150`
- Primary owner: 백엔드·데이터 개발팀장
- Reviewers: 백엔드 owner, AI/data lead, PM, 외부 도메인 검수자
- 관련 요구사항: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-005`, `NFR-006`
- 관련 ADR: `ADR-0013`, `ADR-0014`
- 목표 브랜치: 이슈 전용 branch/worktree 또는 비식별 evidence PR
- 승인자 역할: 백엔드·데이터 개발팀장
- 승인일: 2026-08-26

## 배경과 사용자 가치

V3 staging DEMO composition과 Qdrant adapter는 구현됐지만 실제 Qdrant index build, OpenAI staging
호출, latency/cost/fallback/safety evidence와 인간 승인은 수집되지 않았다. production flag를
변경하지 않고 승인 가능한 staging evidence를 만들어 구현 완료와 운영 승격을 명확히 분리한다.

이 승인은 staging evidence 수집만 허용하며 production promotion을 승인하지 않는다.

## 포함 범위

- LLM provider/model allowlist 승인 기록
- embedding provider/model/version/dimension/metric 승인 기록
- ACTIVE V2 catalog UUID 기반 immutable Qdrant collection build
- point count, build hash, version 검증과 atomic alias 전환
- PostgreSQL canonical re-read 확인
- Qdrant timeout, unavailable, stale version, missing point의 deterministic fallback 확인
- staging-only one-shot OpenAI shadow 실행
- provider call count, latency, token, cost, timeout, fallback과 safety hard gate 증적
- privacy allowlist 검사
- promotion evaluator 실행과 human approval 대기 상태 기록

## 제외 범위

- production V3 활성화
- 실제 사용자 데이터 shadow
- production DB와 production Qdrant
- prompt, chain-of-thought, provider 원문 응답과 원문 오류 저장
- 직접 식별자, raw check-in, health 또는 wearable 데이터 저장
- Qdrant를 PostgreSQL source of truth 대신 사용하는 변경

## 인수 조건

1. provider/model/embedding 계약은 현재 공식 provider 문서와 승인 기록에 근거한다.
2. model code와 allowlist는 exact match로 검증한다.
3. Qdrant build 입력은 PostgreSQL ACTIVE V2 catalog의 승인 UUID로 제한한다.
4. collection은 immutable하고 검증 완료 전 alias를 전환하지 않는다.
5. point count, build hash와 catalog/embedding/index version이 일치한다.
6. 검색 결과는 PostgreSQL canonical re-read를 통과해야 한다.
7. Qdrant 실패 시 deterministic fallback을 사용하고 PostgreSQL 실패를 Qdrant로 우회하지 않는다.
8. Safety veto 입력은 Qdrant와 LLM 호출 전에 종료된다.
9. evidence에 금지된 개인정보·건강정보·provider 원문이 없다.
10. 실제 call count, latency, token, cost, fallback과 safety 결과를 기록한다.
11. human approval 전에는 `READY_FOR_HUMAN_APPROVAL`을 production 승인으로 해석하지 않는다.
12. `V3_PRODUCTION_PROMOTION_APPROVED=false`를 유지한다.

## 변경 예상 파일

- 승인된 provider/embedding 계약 task 또는 ADR 증적
- `outputs/v3-shadow/<run_id>`의 ignored local evidence
- 필요 시 비식별 summary/manifest 또는 runbook 보완
- 이 task 문서의 실제 검증 결과

실제 credential, raw provider output과 staging secret은 커밋하지 않는다.

## API 영향

공개 API 변경 없음. staging DEMO와 shadow 경계만 사용하며 LEGACY production 응답을 변경하지 않는다.

## DB·마이그레이션 영향

새 migration 없음. PostgreSQL은 canonical exercise와 V3 persistence source of truth로 유지한다.
staging 전용 DB만 사용한다.

## 안전·개인정보·보안 영향

- Agent input은 normalized identifier-free 값으로 제한한다.
- prompt, chain-of-thought, raw provider payload와 exception text를 저장하지 않는다.
- token, API key와 endpoint credential은 process secret으로만 주입한다.
- Safety veto는 Coordinator, LLM, Qdrant 또는 fallback이 변경할 수 없다.
- callbacks/tracing을 통해 건강정보가 외부로 전송되지 않게 한다.

## 선행 관계와 차단 요소

- `#148`에서 ACTIVE V2 catalog의 실제 PostgreSQL 검증이 완료돼야 한다.
- `#149` 또는 동등한 staging 실행 환경이 준비돼야 한다.
- provider/model, embedding 계약과 가격 근거가 승인돼야 한다.
- PM, backend owner와 외부 도메인 검수자의 production 승인은 이 task와 별도다.

## 테스트 계획

- Qdrant local/server integration test
- index build count/hash/version 검증
- timeout/unavailable/stale/missing-point fallback test
- PostgreSQL canonical re-read test
- V3 golden/safety/privacy/fallback test
- staging one-shot shadow execution
- promotion evaluator
- formatter, linter, mypy와 관련 전체 backend test

## 수동 확인

개발팀장은 기준 SHA, provider/model/embedding versions, call budget, collection/alias, point count,
build hash, report hash, record count, latency/cost/fallback/safety 결과를 기록한다. 실제 secret과 raw
provider payload는 기록하지 않는다.

## 알려진 제한과 후속 작업

- staging 성공은 임상 검증 또는 production 승인이 아니다.
- 실제 사용자 shadow는 승인 범위가 아니다.
- threshold 승인, PM·개발팀장·backend owner·외부 전문가 서명과 production composition/flag 변경은
  별도 수동 승인과 후속 PR이 필요하다.

## 2026-08-27 v2.0.1 staging preflight

### 현재 목표 계약

- target catalog: `exercise-catalog-v2.0.1-final`
- catalog identity: staging PostgreSQL에서 읽은 ACTIVE catalog UUID로 고정, 아직 미확인
- vector index version: `v201-openai-text-embedding-3-large-d3072-inputv1-cosine-r1`
- provider/model/dimension: `OPENAI` / `text-embedding-3-large` / `3072`
- distance metric: `COSINE`
- input schema: `exercise-embedding-input-v1`
- provider timeout/retry: 30초 / 자동 retry 0회
- pricing reference: 2026-08-27 OpenAI 공식 model page, USD 0.13 / 1M input tokens
- index provider-cost ceiling: aggregate input 300,000-token 상한 기준 USD 0.04
- 승인: 백엔드·데이터 개발팀장, 2026-08-27; AI/data lead review 필요
- production promotion: `V3_PRODUCTION_PROMOTION_APPROVED=false` 유지

OpenAI 공식 문서는 `text-embedding-3-large`를 영어·비영어 텍스트 모두를 위한 가장 성능이 높은
embedding model로 설명하고 기본 dimension을 3072로 명시한다. 102개 검수 운동의 한국어 이름과 설명
검색 품질을 우선하고 저장량이 제한적이므로 축소 dimension 없이 사용한다. model page가 날짜가 붙은
별도 snapshot code를 제공하지 않는 제한은 vector index version과 build hash로 보완한다.

- model/pricing: <https://developers.openai.com/api/docs/models/text-embedding-3-large>
- dimension/input limit: <https://developers.openai.com/api/docs/guides/embeddings>
- dimensions parameter: <https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create>

### 수행한 사전 점검

- 기준 branch는 #149 병합 commit `ae8441f28c26385ca4f1f26736d307c01c667ae8`을 포함한 최신
  `origin/develop` 위로 rebase했다.
- 현재 작업 process에는 `APP_ENV`, `DATABASE_URL`, `OPENAI_API_KEY`, Qdrant endpoint/API key와
  embedding 계약 환경변수가 설정돼 있지 않다. 값은 조회하거나 기록하지 않고 설정 여부만 확인했다.
- `infra/deployment/.env.staging`은 이 worktree에 없고 AWS identity 확인도 실패했다. secret 값을
  로컬 `.env`, 문서, 로그 또는 명령 인자에 복사하지 않는다.
- #149 PR #165가 병합돼 Qdrant image/digest, healthcheck, safe defaults와 read-only handoff SQL은
  확정됐다. 다만 #149 자체 상태는 staging Qdrant topology 승인과 Aurora read-only evidence 대기로
  `BLOCKED`다.
- `infra/deployment/compose.staging.yaml`은 Qdrant를 내부 HTTP로 선언하고 API의 safe default를
  `QDRANT_ENABLED=false`, `QDRANT_TLS_ENABLED=false`로 유지한다. 반면 application settings는 staging에서
  Qdrant를 활성화할 때 HTTPS와 API key를 요구한다. 승인된 외부 Qdrant 또는 승인된 TLS/auth 구성이
  전달되기 전까지 실제 build를 실행하지 않는다.
- Docker Engine `29.6.2`와 Compose CLI 접근은 확인했다. 다만 staging secret/env가 주입되지 않은
  상태의 `docker compose -f infra/deployment/compose.staging.yaml config --quiet`는 필수
  `API_DOMAIN`이 없어 fail-closed로 종료됐으며 staging Qdrant health는 실행하지 않았다.

### 차단된 검증

- staging PostgreSQL ACTIVE catalog UUID, 승인 상태, indexable exercise count 확인
- 실제 `vector_index_registry` 전체/상태별 행 수와 v2.0.0 registry 존재 여부 확인
- `exercise-catalog-v2.0.1-final` OpenAI embedding index build와 alias 전환
- 동일 immutable version 재실행 idempotency 확인
- staging live shadow의 token/cost/latency/fallback/safety evidence 수집

위 항목은 credential 또는 실제 staging 실행 결과가 아니며, 완료 evidence로 해석하지 않는다.
staging DB/Qdrant handoff와 embedding 계약 승인을 받은 뒤 read-only preflight부터 다시 수행한다.

### 2026-08-27 v2.0.1 local PostgreSQL/Qdrant integration

이 검증은 #149의 로컬 Compose를 `issue150v201` project로 격리해 수행했다. test-only deterministic
embedding을 사용했으며 staging, OpenAI embedding 품질 또는 provider 승인을 의미하지 않는다.

| 항목 | 실제 결과 |
|---|---|
| Docker / Compose | `29.6.2` / `v5.3.1` |
| PostgreSQL / Qdrant | `16.14` / `1.18.2` 고정 digest |
| 전용 host ports | PostgreSQL `55450`, Qdrant HTTP `6350`, gRPC `6351` |
| migration head | `0027_catalog_media_assets` |
| ACTIVE catalog | UUID `41074957-8de0-4e22-92e5-404d65e87b0a`, `exercise-catalog-v2.0.1-final` |
| catalog approval | `DOMAIN_APPROVED`, `DOMAIN_REVIEWER`, `PRODUCTION_APPROVED`, production eligible |
| indexable exercise / Qdrant points | `102 / 102` |
| registry before / after | `0 / 1`, 최종 `ACTIVE` |
| embedding contract | `DETERMINISTIC_TEST_ONLY`, dimension `16`, input schema v1, `COSINE` |
| vector index version | `qdrant-integration-test-v1` |
| build hash | `592404eca2aa720a5d886cacc0e851a732cf919e1a4545f7c1bfcefc98412c60` |
| alias | `exercise_catalog_active` → 검증된 v2.0.1 immutable collection |
| 동일 version 재실행 | point/hash 일치, `alias_changed=false` |
| server integration test | `1 passed` |

다른 작업의 container나 volume은 수정하지 않았다. 이 로컬 catalog UUID, registry ID, collection과
build hash는 격리된 test evidence이며 실제 staging 값으로 복사하거나 재사용하지 않는다.

### 로컬 회귀 검증

| 검증 | 실제 결과 |
|---|---|
| `uv run ruff check backend data/scripts` | 통과 |
| `uv run ruff format --check backend data/scripts` | 488 files, 변경 필요 없음 |
| `uv run mypy` | 280 source files, 문제 없음 |
| 지정 Qdrant/staging evidence tests | 70 passed |
| 실제 v2.0.1 PostgreSQL/Qdrant server integration | 1 passed |
| `uv run pytest -q` | 1358 passed, DB/Qdrant opt-in tests 81 skipped |

skip은 `TEST_DATABASE_URL` 또는 명시적 PostgreSQL/Qdrant integration 환경이 제공되지 않아 발생했다.
따라서 로컬 회귀 결과는 staging DB/Qdrant/OpenAI evidence를 대체하지 않는다.

## Historical evidence — 2026-08-26 v2.0.0 local integration

### 기준과 격리 환경

- 기준 commit: `3fa46b5015dcf8386b32228b719f15748bd55cae`
- branch: `codex/150-qdrant-v3-staging-evidence`
- Docker Engine: `29.6.2`
- PostgreSQL: `16.14`
- Qdrant: `1.18.2`, repository 고정 digest 사용
- 전용 DB: `exercise_app_v3_staging_20260826_test`
- 전용 host port: PostgreSQL `55435`, Qdrant HTTP `6343`, gRPC `6344`

기존 사용자 checkout의 미커밋 파일과 dump는 읽거나 복원하지 않았다. 전용 PostgreSQL/Qdrant
container, network와 named volume만 사용했다.

### 비밀값 없는 실제 PostgreSQL/Qdrant 통합

아래 결과는 ACTIVE `exercise-catalog-v2.0.0-final`의 production-approved exercise 102건을
PostgreSQL에서 읽고,
test-only deterministic embedding contract로 실제 Qdrant collection을 구축했다. 이 단계는 OpenAI
embedding 품질 또는 provider 승인이 아니라 DB/Qdrant integration과 privacy 경계 증적이다.
이 historical 결과와 collection은 v2.0.1 staging index 또는 live-provider evidence로 재사용하지 않는다.

| 항목 | 결과 |
|---|---|
| PostgreSQL ACTIVE catalog | 1개, production eligible, activated |
| index input/point count | 102 / 102 |
| vector dimension | 16, deterministic test-only |
| registry status | `ACTIVE` |
| build hash | `20f8c69f6bf47bbc9c89ad4e66292e677ca512247f76d3c7d5400a5ec4d95538` |
| alias | `exercise_catalog_active` → 검증된 immutable collection |
| 동일 version 재실행 | point/hash 일치, `alias_changed=false` |

### 실행한 검증

| 검증 | 결과 |
|---|---|
| V3 evaluation formatter | 6 files formatted |
| V3 evaluation Ruff | 통과 |
| V3 evaluation mypy | 3 source files, 문제 없음 |
| V3 evaluation/staging CLI tests | 83 passed |
| OpenAI embedding/index CLI/builder/config tests | 29 passed |
| Qdrant retrieval/fallback/canonical re-read/scenario tests | 206 passed |
| 실제 PostgreSQL/Qdrant index integration | 1 passed |
| stored synthetic shadow | 20 records, `PASSED`, safety pass `1.000000`, veto override 0 |
| 전체 Ruff format/check | 485 files, 통과 |
| 전체 mypy | 278 source files, 문제 없음 |
| 전체 backend pytest + PostgreSQL integration | 1417 passed, Qdrant opt-in 1 skipped |
| data pipeline unittest | 117 passed |
| promotion evaluator precheck | `NOT_EVALUATED`, `THRESHOLD_REFERENCE_MISSING` |

### 아직 완료되지 않은 staging gate

- 이전 로컬 OpenAI credential은 보안상 사용하지 않고 rotation이 필요하다.
- AWS CLI `2.36.29`는 설치했으나 현재 AWS credential/profile이 없어 Secrets Manager와 ECS에
  접근하지 못한다.
- OpenAI Agent model, embedding model/dimension과 versioned pricing reference의 최종 승인 기록이
  아직 없다.
- 따라서 실제 OpenAI embedding index, staging one-shot shadow, 실제 token/cost/latency evidence와
  최종 promotion 판정은 실행하지 않았고 task 상태는 완료로 변경하지 않는다. 합성 evidence에 대한
  evaluator precheck는 승인 threshold가 없음을 `NOT_EVALUATED`로 fail-closed 기록했다.
- `V3_PRODUCTION_PROMOTION_APPROVED=false`를 유지한다.
