# TASK-AGENT-150: Qdrant index 및 V3 staging evidence 수집

- 현재 상태: `READY_FOR_SHADOW_RERUN` (v2.0.1 schema-v2 index 완료·활성, 첫 live shadow의 provider schema 실패 수정·재실행 승인 대기)
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
- catalog identity: `04d726d5-ad3d-45f0-b400-bf4205113863` (staging PostgreSQL ACTIVE catalog)
- vector index version: `v201-openai-text-embedding-3-large-d3072-inputv1-cosine-r2-helkki-staging`
- provider/model/dimension: `OPENAI` / `text-embedding-3-large` / `3072`
- distance metric: `COSINE`
- input schema: `exercise-embedding-input-v1`
- provider timeout/retry: 30초 / 자동 retry 0회
- pricing reference: 2026-08-27 OpenAI 공식 model page, USD 0.13 / 1M input tokens
- index provider-cost ceiling: aggregate input 300,000-token 상한 기준 USD 0.04
- 승인: 개발팀장 겸 AI/data lead 권한 보유자, 2026-08-27; staging evidence 범위
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
  확정됐다. #149 자체 상태는 `ACCEPTED`다: staging Qdrant topology는 외부 인증·TLS endpoint로
  승인됐고 Aurora read-only evidence는 아래 schema-v2 build 절에 기록했다.
- `infra/deployment/compose.staging.yaml`은 Qdrant를 내부 HTTP로 선언하고 API의 safe default를
  `QDRANT_ENABLED=false`, `QDRANT_TLS_ENABLED=false`로 유지한다. 반면 application settings는 staging에서
  Qdrant를 활성화할 때 HTTPS와 API key를 요구한다. 승인된 외부 Qdrant 또는 승인된 TLS/auth 구성이
  전달되기 전까지 실제 build를 실행하지 않는다.
- Docker Engine `29.6.2`와 Compose CLI 접근은 확인했다. 다만 staging secret/env가 주입되지 않은
  상태의 `docker compose -f infra/deployment/compose.staging.yaml config --quiet`는 필수
  `API_DOMAIN`이 없어 fail-closed로 종료됐으며 staging Qdrant health는 실행하지 않았다.

### 2026-08-27 AWS staging live preflight

- 실행 identity: AWS account `343953861875`의 승인된 CLI session. credential과 secret 값은 기록하지
  않았다.
- 실행 환경: EC2 `helkki-staging-compose`, SSM `Online`, Docker `25.0.14`, Compose `v2.40.3`.
- 기준 commit: `50616aff070dce719ae07fe364248144dbf0a4c0` (`origin/develop`, #149와 #150 병합 포함).
- 기존 EC2 release는 `0599c1adb17c7a7a9eb5581c8c96882d72749e3c`였으므로 실행 중인 stack을
  교체하지 않고 `/opt/helkki/releases/50616af` detached worktree와
  `helkki_issue150_api:50616af` one-shot image를 별도로 만들었다.
- 기존 migration을 staging Aurora에 적용한 뒤 승인된 V2 bundle을 적재하고
  `exercise-catalog-v2.0.1-final`을 활성화했다. 결과는 exercises `102`, safety rules `394`였다.
- Aurora reader endpoint와 `SET TRANSACTION READ ONLY` transaction으로 재확인한 ACTIVE catalog는
  UUID `04d726d5-ad3d-45f0-b400-bf4205113863`, `DOMAIN_APPROVED`, `DOMAIN_REVIEWER`,
  `PRODUCTION_APPROVED`, `production_eligible=true`, exercise record/indexable count `102`였다.
- `vector_index_registry`는 전체 `0`행이고 상태별 행과 v2.0.0/v2.0.1 registry도 없었다.
- AWS Secrets Manager의 staging Qdrant secret은 endpoint와 Database API key를 포함한다. 값을
  출력하지 않고 HTTPS scheme, key 존재와 인증된 `/readyz` HTTP `200`을 확인했다.
- staging OpenAI secret도 값 또는 prefix를 출력하지 않고 비어 있지 않음만 확인했다.
- PR #166은 `50616af`로 병합됐고 GitHub review는 `0`건이었다. 이후 개발팀장 겸 AI/data lead 권한
  보유자가 2026-08-27에 위 embedding 계약과 staging evidence 범위를 명시적으로 승인했다.
- 승인에 따라 EC2 instance role에 OpenAI/Qdrant secret 두 개만 대상으로 하는 exact-ARN
  `GetSecretValue` inline policy를 추가했다. IAM 평가와 EC2 role session의 실제 secret 조회가 모두
  성공했으며 secret 값은 출력하지 않았다.
- build 전 Qdrant inventory는 collection `0`, alias `0`이었다.
- 실제 catalog embedding input을 OpenAI provider에 전송하는 별도 외부 데이터 전송 승인이 당시
  확인되지 않아 provider 호출 직전 안전 게이트에서 중단됐다. collection, registry와 alias는 변경되지
  않았다.
- 이후 개발팀장 겸 AI/data lead 권한 보유자가 승인된 운동 102개의 비사용자 catalog embedding input을
  OpenAI Embeddings API에 전송하는 것을 비용 상한 USD 0.04와 staging-only 범위로 명시 승인했다.
- 첫 build 시도는 provider 호출 전 `QDRANT_TIMEOUT_SECONDS=15`가 코드 상한 10초를 초과해
  `SETTINGS_INVALID`로 종료됐다. Qdrant timeout을 10초로 수정한 두 번째 시도는 fail-closed
  `QDRANT_INDEX_BUILD_FAILED`로 종료됐다.
- 비사용자 connectivity probe 1건으로 원인을 분리한 결과 OpenAI가 HTTP `401`, error code
  `invalid_api_key`를 반환했다. exception message, key와 provider 원문 응답은 기록하지 않았다.
- 실패 후 Qdrant collection/alias는 각각 `0/0`, PostgreSQL `vector_index_registry`도 reader endpoint
  재확인 기준 `0`행이었다. 실제 102개 embedding build, registry write와 alias 전환은 발생하지 않았다.
- `V3_PRODUCTION_PROMOTION_APPROVED=false`를 변경하지 않았다.

### Historical evidence — 2026-08-27 v2.0.1 live index before database cutover

This section records the first successful provider build against the former staging catalog UUID.
The collection remains immutable for rollback/audit purposes, but its registry row was intentionally
replaced during the canonical `helkki_staging` database cutover below. It is not the active staging
index after that cutover.

- 교체된 staging OpenAI key는 값 비노출 probe에서 `text-embedding-3-large`, dimension `3072`,
  prompt/total token `8/8`로 계약 일치를 확인했다.
- build 기준 commit은 `50616aff070dce719ae07fe364248144dbf0a4c0`이고 catalog UUID는
  `04d726d5-ad3d-45f0-b400-bf4205113863`이다.
- vector index version은
  `v201-openai-text-embedding-3-large-d3072-inputv1-cosine-r1`이다.
- immutable collection은
  `exercise_catalog__staging__exercise_catalog_v2_0_1_final__text_embedding_3_large__v201_openai_text_embedding_3_large_d3072_inputv1_cosine_r1`이다.
- build hash는 `da87ebd2683cafb9346c3ee1abe8951216e4bc246c7ae0e81965a3d9e86d4bc6`이고
  PostgreSQL indexable count/Qdrant point count는 `102/102`다.
- registry는 위 catalog UUID에 연결된 `ACTIVE` 1행이며 model `text-embedding-3-large`, dimension
  `3072`, input schema `exercise-embedding-input-v1`, metric `COSINE`과 정확히 일치한다.
- alias `exercise_catalog_active`는 위 immutable collection만 가리킨다.
- payload에는 승인된 catalog metadata와 hash/version 필드만 있고 사용자 식별자, 건강정보, raw
  embedding input, vector 또는 provider response는 없다.
- 동일 immutable version 재실행은 같은 build hash와 point count를 반환했고
  `alias_changed=false`였다.
- 첫 live query에서 Qdrant Cloud strict-mode payload filter에 필요한 payload index가 없고 140자
  collection name이 retrieval contract의 일반 128자 제한을 초과하는 구현 누락을 발견했다.
- `1f3bb10d8421bff769e958e3593976bb34b0049d`에서 keyword index 3개와 bool index 1개를 build 검증
  경로에 추가하고 collection reference만 255자까지 허용했다. version reference의 128자 제한은
  유지했다.
- 수정 image의 live query는 `VECTOR_RETRIEVAL_SUCCEEDED`, fallback `false`, ranked `12`, eligible
  subset `true`였고 PostgreSQL canonical re-read도 `12/12`였다.
- OpenAI adapter가 provider usage를 build result에 노출하지 않으므로 실제 index token/cost는 기록하지
  못했다. 사전 승인된 300,000-token/USD 0.04 상한을 초과했다는 증거는 없지만 이를 실제 비용 측정으로
  해석하지 않는다.
- 실행 중인 staging API stack과 production flag는 변경하지 않았다.

### 남은 차단 검증

- staging live shadow의 token/cost/latency/fallback/safety evidence 수집

live shadow는 합성 fixture를 별도의 OpenAI chat model로 전송하므로 embedding 전송 승인만으로 실행하지
않는다. exact LLM model allowlist, 최대 provider call budget과 합성 fixture 외부 전송 승인을 받은 뒤
수행한다. 현재 상태는 `STAGING_EVIDENCE_COMPLETE` 또는 production promotion 승인이 아니다.
live shadow 전에는 전체 완료 evidence로 해석하지 않는다.

### 2026-08-27 canonical `helkki_staging` database cutover

The development/data lead selected `helkki_staging` as the canonical staging database after a
preflight found that the application data was in `exercise_app` while the original vector registry
was in `helkki_staging`. Copying only the registry was rejected: both catalogs had the same version,
manifest hash and 102 reviewed documents, but their catalog and exercise UUIDs differed.

| Item | Actual result |
|---|---|
| Aurora recovery point | manual cluster snapshot `database-1-pre-helkki-staging-migration-20260827-01`, `available`, 100% |
| schema gate | both databases at Alembic `0027_catalog_media_assets`; schema signatures equal |
| source / target | `exercise_app` / `helkki_staging` |
| migration isolation | source `REPEATABLE READ, READ ONLY`; target `SERIALIZABLE` plus transaction advisory lock |
| copied data | 72 application tables, 4,800 rows, source UUIDs and stored reproducibility hashes preserved |
| post-copy verification | 71 replicated non-registry tables have identical counts and canonical content hashes |
| canonical catalog | UUID `419eaab4-0b93-4a9f-8705-132d46cc681f`, `exercise-catalog-v2.0.1-final`, 102 exercises |
| vector migration | existing approved vectors reused by stable-code mapping; no OpenAI provider call |
| vector index version | `v201-openai-text-embedding-3-large-d3072-inputv1-cosine-r2-helkki-staging` |
| collection | `exercise_catalog__staging__exercise_catalog_v2_0_1_final__text_embedding_3_large__v201_openai_text_embedding_3_large_d3072_inputv1_cosine_r2_helkki_staging` |
| point count / build hash | `102` / `7df34c1c844b1d8abce9d02a3ccbee03e238ab8644afc58dd6d977fb7c3dcb59` |
| registry / alias | one `ACTIVE` registry row; `exercise_catalog_active` atomically switched to the new collection |
| idempotency | second validation returned the same count/hash and `alias_changed=false` |
| service state | `helkki_staging-api-1` restarted and Docker reported `healthy` |
| production promotion | not performed; `V3_PRODUCTION_PROMOTION_APPROVED=false` remains required |

The staging API was stopped only for the cutover window. The target replacement occurred in one
transaction and was committed only after every table count and canonical content hash matched. A
failure before commit would have rolled back the target; a failure after DB commit but before vector
activation would have left the registry empty and forced deterministic fallback. The former database
and Qdrant collection were not deleted or overwritten. Secrets, user rows, raw health data, embedding
inputs, vectors and provider responses were not printed or written to this evidence.

### 2026-08-27 first v2.0.1 live Shadow attempt

This attempt is retained as non-completion evidence. It must not be represented as successful V3
quality evidence or production-promotion approval.

| Item | Actual result |
|---|---|
| execution commit | `edd7d82f66e2c19fd64b7234b9926218dd37bc2f` |
| run ID | `issue150-v201-live-20260827-edd7d82` |
| fixture / catalog | `v3-shadow-golden-v2` / `exercise-catalog-v2.0.1-final` |
| provider / exact model | `OPENAI` / `gpt-4o-mini-2024-07-18` |
| started / finished UTC | `2026-08-27T06:23:33.697799Z` / `2026-08-27T06:26:57.993402Z` |
| cases / repeat | `20 / 1` |
| provider calls | actual `102`, approved maximum `320` |
| terminal outcomes | `FAILED=17`, `STOP_AND_SEEK_HELP=3` |
| structured outputs | `FAILED=17`, `SUCCEEDED=3` (the three successes were zero-call safety terminals) |
| canonical failure | `LLM_AGENT_SCHEMA_INVALID=17`; specialist invocation failures `51` |
| safety | invariant pass `100%`, veto override `0`, hard-gate violation `0` |
| latency | decision p50 `11,383 ms`, p95 `14,496 ms` |
| usage / cost | `UNAVAILABLE` for 17 provider cases; token and cost fields remain `null` and are not estimated |
| staging manifest hash | `c3e912caf0ed294b6c60d77da062cd07765c12b758e2aacc14d46e74c7bc54c9` |
| results SHA-256 | `06965b138bb20d5c5d04f9e395bb9f5ddc334b297d99fdcf4a351d1653433880` |
| summary SHA-256 | `47312cdb86e2890e08280722283389318a40775ab23f1fdb7054862b9c21295d` |

The harness process completed and wrote internally consistent reports, but all provider-backed cases
failed before coordination. The provider schema incorrectly required the model to calculate
`proposal_hash` (and would later have required `plan_hash`). These SHA-256 reproducibility fields are
server-owned and cannot be delegated to an LLM. Commit
`569298d6b38f0b1843aa987353f63bd8406b699c` removes those fields from provider schemas, parses the
remaining JSON in strict JSON mode, and computes canonical hashes on the server. Its focused adapter
and staging CLI suite passed `43` tests.

The first evidence directory remains only on the staging host under the ignored evidence path. No
prompt, raw provider response, credential, user data, or health record was written to the reports.
A second provider run requires a new explicit call-budget approval. Until that rerun succeeds this
task is not `STAGING_EVIDENCE_COMPLETE`.

### 2026-08-27 v2.0.1 schema-v2 staging index build

#168이 embedding input에서 `beginner_suitable` 투영을 제거하면서 기본 input schema가
`exercise-embedding-input-v2`가 됐다. 직전 ACTIVE index는 `exercise-embedding-input-v1`이어서 계약이
불일치했고, 그 상태의 retrieval은 오류 없이 deterministic fallback만 반환한다. 이 build가 그 간극을
해소한다.

- topology는 #149에서 승인한 외부 인증·TLS staging Qdrant endpoint다. 값 비노출 확인에서 scheme
  `https`, `TLSv1.3`, Let's Encrypt 인증서(만료 `2026-11-11`), hostname 검증 통과, API key 인증
  `/collections` HTTP `200`이었다.
- provider 호출 전 read-only preflight: ACTIVE catalog `1`행, UUID
  `419eaab4-0b93-4a9f-8705-132d46cc681f`, `exercise-catalog-v2.0.1-final`,
  `DOMAIN_APPROVED`/`DOMAIN_REVIEWER`/`PRODUCTION_APPROVED`, production eligible, activated,
  indexable exercise count `102`.
- vector index version은
  `v201-openai-text-embedding-3-large-d3072-inputv2-cosine-r1-helkki-staging`이다.
- immutable collection은
  `exercise_catalog__staging__exercise_catalog_v2_0_1_final__text_embedding_3_large__v201_openai_text_embedding_3_large_d3072_inputv2_cosine_r1_helkki_staging`이다.
- build hash는 `2805d2e10ea9d71540e0f8fa3c8d100cb3e717340d5e5924462aa2a2b6aa92de`이고
  PostgreSQL indexable count/Qdrant point count는 `102/102`다.
- registry는 catalog UUID `419eaab4-0b93-4a9f-8705-132d46cc681f`에 연결된 `ACTIVE` 1행이며 model
  `text-embedding-3-large`, dimension `3072`, input schema `exercise-embedding-input-v2`, metric
  `COSINE`과 일치한다. 직전 inputv1 r2 row는 `STALE`로 강등됐다.
- alias `exercise_catalog_active`는 위 immutable collection만 가리키고 해석된 point count는 `102`다.
- 기존 inputv1 collection 2개는 삭제하지 않았다. 롤백은 alias를
  `..._inputv1_cosine_r2_helkki_staging`으로 되돌린다. inputv1 r1 collection은 런북대로 재활성화하지
  않는다.
- `V3_PRODUCTION_PROMOTION_APPROVED=false`를 유지했고 실행 중인 staging API stack의 flag는 바꾸지
  않았다. secret은 실행 process 메모리에만 존재했고 파일, 명령 인자, 로그에 기록하지 않았다.
- OpenAI adapter가 provider usage를 build result에 노출하지 않으므로 실제 token/cost는 기록하지
  못했다. 사전 승인된 300,000-token/USD 0.04 상한을 초과했다는 증거는 없지만 이를 실제 비용 측정으로
  해석하지 않는다.
- 동일 version 재실행은 같은 build hash `2805d2e10ea9d71540e0f8fa3c8d100cb3e717340d5e5924462aa2a2b6aa92de`,
  point count `102`, `alias_changed=false`를 반환해 멱등성을 확인했다.
- 이 build만으로 live retrieval evidence를 대체하지 않는다. staging API stack에서의 실제 retrieval
  확인은 아래 demo profile 적용 후 별도로 수집한다.

### 2026-08-27 승인된 V3 demo agent model

- agent model code는 `gpt-5.6-terra`로 통일했고 `LLM_AGENTS_APPROVED_MODEL_CODES`도 같은 값 1건이다.
- `.env.example:51`이 요구하는 provider 모델 목록 대조를 수행했다. staging key로 조회한 provider
  model list `124`건에 `gpt-5.6-terra`가 존재한다.
- narration(ADR-0011)의 `LLM_MODEL_CODE` 기본값도 같은 코드로 정렬했으나 `LLM_ENABLED=false`를
  유지해 narration provider 호출은 켜지 않았다.
- `openai_demo_gates_ready`와 V3 demo runtime 구성이 이 설정에서 통과함을 provider 호출 없이
  확인했다. `V3_PRODUCTION_PROMOTION_APPROVED=false`를 유지한다.

### 2026-08-27 schema-v2 live retrieval 확인

아래는 세 compose 파일을 병합했을 때 생성되는 것과 동일한 설정을 사용해, 실제 staging PostgreSQL과
staging Qdrant를 대상으로 수행했다. 읽기 전용이며 decision을 생성하거나 두 저장소에 쓰지 않았다.

| 항목 | 결과 |
|---|---|
| `openai_demo_gates_ready` | `True` |
| PostgreSQL 승인 eligible pool | `102` |
| `retrieval_status_code` | `VECTOR_RETRIEVAL_SUCCEEDED` |
| `fallback_used` | `False` |
| ranked count | `12` (requested limit `12`) |
| vector index version | `v201-openai-text-embedding-3-large-d3072-inputv2-cosine-r1-helkki-staging` |
| embedding model | `text-embedding-3-large` |
| ranked ⊆ PostgreSQL eligible | `True` |
| similarity score 범위·정렬 | `0.4531`–`0.4931`, 내림차순 |
| app boot `v3_authoritative_enabled` | `True` |
| app boot V3 demo runtime | 구성됨 |
| `/api/v1/health/live` · `/ready` | `200 OK` · `200 READY` |

Qdrant는 PostgreSQL이 승인한 ID만 순위화했고 자체적으로 eligibility를 만들지 않았다.

한계: 이 확인은 개발자 workstation에서 staging backend를 대상으로 수행했고 EC2 staging host의
task process에서 실행하지 않았다. 따라서 compose stack 배포 자체의 증적은 아니며 host 배포·TLS
종단·`.env.staging` 생성 절차는 별도로 확인해야 한다. `STAGING_EVIDENCE_COMPLETE`도 아니다.

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
| 지정 Qdrant/staging evidence tests | 94 passed, opt-in server test 1 skipped |
| 실제 v2.0.1 PostgreSQL/Qdrant server integration | 1 passed |
| `uv run pytest -q` | 1362 passed, DB/Qdrant opt-in tests 81 skipped, QdrantLocal warning 1 |

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
