# TASK-BACKEND-008: V3 ExercisePool Qdrant 기술 검증과 catalog mapping 영향 분석

- 상태: `READY_FOR_REVIEW`
- Primary owner: 백엔드 담당
- Contract owner: 개발리드
- Reviewers: 개발리드, AI/data lead, PM, 외부 도메인 검수자, 프론트엔드 owner
- 관련 ADR: ADR-0013(`ACCEPTED`), ADR-0014(`PROPOSED`)
- 기준 branch: `origin/develop@52a71f1`
- 검증일: 2026-08-24

## Summary

PostgreSQL을 canonical source of truth로 유지하고 Qdrant를 승인 운동의 순위·다양성 계산에만 사용하는
ADR-0014의 derived-index 경계는 Qdrant 1.18.2 REST PoC에서 기술적으로 가능함을 확인했다.

고정 경계는 다음과 같다.

```text
SafetyPolicyEngine
-> PostgreSQL deterministic eligible/mandatory ID filter
-> Qdrant ranking/diversity inside eligible IDs
-> PostgreSQL canonical re-read and validation
-> mandatory/safe-alternative preservation
-> ExercisePoolSnapshot
```

Qdrant payload는 최종 운동 데이터가 아니며 Agent와 Coordinator는 Qdrant에 직접 접근하지 않는다.
Qdrant 장애·stale data·missing point는 PostgreSQL 결정적 후보로 fallback한다. PostgreSQL 장애는 Qdrant
payload로 대체하지 않는다.

이번 작업은 기술 검증과 영향 분석만 수행했다. public API, DB migration, production adapter,
dependency, ADR, 공통 domain contract는 변경하지 않았다.

## Files inspected

문서:

- `AGENTS.md`, `backend/AGENTS.md`, 관련 nested `AGENTS.md`
- `docs/README.md`, `docs/ARCHITECTURE.md`, `docs/DOMAIN_RULES.md`
- `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`, `docs/TECHNICAL_PLAN.md`
- `docs/TEST_STRATEGY.md`, `docs/TRACEABILITY.md`, `docs/COLLABORATION_GUIDE.md`
- `docs/adr/0013-safety-first-llm-multi-agent.md`
- `docs/adr/0014-qdrant-exercise-pool-vector-retrieval.md`
- `docs/tasks/TASK-AGENT-003.md`

Catalog와 decision 경계:

- `backend/app/db/models/catalog.py`
- `backend/app/db/repositories/catalog.py`
- `backend/app/modules/catalog/**`
- `backend/scripts/catalog_data_load.py`, `backend/scripts/catalog_activate.py`
- catalog importer/activation/approval tests
- exercise alternatives와 safety rules model, repository, service, unit/integration/golden tests
- `data/generated/exercise-catalog-seed-merged-mvp-v0.4.0/**`
- `data/generated/exercise-safety-rules-merged-mvp-v0.5.0/**`
- `data/generated/exercise-alternatives-merged-mvp-v0.4.0/**`

Onboarding, feedback, weekly report:

- `frontend/src/features/onboarding/OnboardingScreen.tsx`
- `frontend/src/api/types.ts`
- `backend/app/db/models/profile.py`, `backend/app/db/repositories/profile.py`
- `backend/app/modules/profiles/**`
- `backend/app/db/models/workout.py`
- `backend/app/modules/workouts/**`, `backend/app/db/repositories/workout.py`
- `backend/app/modules/weekly_reports/**`, `backend/app/db/repositories/weekly_report.py`
- 관련 backend API/unit/integration tests와 frontend component tests

## Current catalog model analysis

`CatalogVersion`이 운영 승인 단위다. production 후보는 최소한 ACTIVE catalog,
`DOMAIN_APPROVED`, `DOMAIN_REVIEWER`, `PRODUCTION_APPROVED`, `production_eligible=true`, 유효한 activation
상태를 모두 만족해야 한다. Exercise도 자체 review 상태와 beginner suitability를 가진다.

Exercise UUID는 importer가 PostgreSQL row 생성 시 부여한다. 따라서 Qdrant Point ID는 artifact의
stable code에서 추론하지 않고 실제 `exercises.id`를 읽어야 한다. 한 catalog version 안의 identity는
`(catalog_version_id, stable_code)` unique 경계가 담당한다.

승인 catalog 관계는 다음과 같이 분리돼 있다.

- goal tag와 prescription은 Exercise 관계 테이블
- prescription phase는 `WARMUP`, `MAIN`, `COOLDOWN`
- 한 Exercise가 여러 prescription/phase에 속할 수 있음
- equipment 관계는 현재 REQUIRED 항목을 사용
- alternatives는 방향성 관계이며 goal-preservation과 review/version/hash를 가짐
- safety rule은 exercise 또는 movement-pattern target을 결정적으로 평가

저장소 artifact 정적 분석 결과는 다음과 같다. 이는 실행 중인 PostgreSQL 조회 결과가 아니다.

| 항목 | 결과 |
|---|---:|
| merged catalog exercises | 56 |
| goal links | 32 |
| prescriptions | 36 |
| goal link/prescription이 없는 exercises | 24 |
| 둘 이상의 prescription을 가진 exercises | 4 |
| `name_en` 누락 | 26 |
| instruction summary 누락 | 0 |

## Embedding source document proposal

Embedding 원문은 승인 catalog projection만 사용하며 label 순서와 배열 정렬이 고정된 canonical
document로 만든다.

포함 후보:

- `name_ko`, 존재하는 `name_en`
- 승인된 `instruction_summary_ko`와 검수된 form cue
- `goal_codes`
- `training_type_code`
- `primary_movement_pattern_code`
- `body_focus_code`
- `difficulty_code`
- `equipment_codes`, `location_codes`
- `phase_codes`
- `beginner_suitable`, `recovery_eligible`

제외 항목:

- Safety rule, 금기 판단, safety severity/reason
- `pain_present`, 사용자 `body_area_code`, `pain_intensity_score`, normalized severity
- user ID, 이메일, 이름, authentication subject
- raw check-in, 통증, wearable, calendar, GPS 데이터
- 미승인 운동 설명
- 내부 prompt, provider 원문, hidden reasoning

운동 목표 부위와 사용자 통증 부위의 혼동을 막기 위해 v1에는
`exercise_body_parts.body_area_code`를 넣지 않는다. 향후 검색 품질상 필요하면 검수된
`target_area_codes`라는 별도 비사용자 catalog 계약을 승인받는다.

Point별 `source_hash`는 현재 모델에 없으므로 다음을 구분한다.

- `catalog_manifest_hash`: 전체 source artifact
- `source_document_hash`: canonical embedding document의 SHA-256

## Proposed Qdrant schema

Collection과 alias:

```text
exercise_catalog__{catalog_version}__{embedding_version}
exercise_catalog_active
```

Vector:

```yaml
name: semantic
dimension: embedding model 승인 후 고정
distance: model 권장 metric
```

Point:

```yaml
id: PostgreSQL exercises.id UUID
vector:
  semantic: float[]
payload:
  payload_schema_version: 1
  catalog_version_id: UUID
  catalog_version_code: string
  catalog_manifest_hash: sha256
  embedding_version: string
  embedding_model_version: string
  review_status_code: DOMAIN_APPROVED
  review_method_code: DOMAIN_REVIEWER
  status_interpretation_code: PRODUCTION_APPROVED
  production_eligible: true
  goal_codes: string[]
  equipment_codes: string[]
  location_codes: string[]
  phase_codes: string[]
  training_type_code: string
  body_focus_code: string
  difficulty_code: string
  primary_movement_pattern_code: string
  beginner_suitable: boolean
  recovery_eligible: boolean
  instruction_content_version: string
  source_document_hash: sha256
```

초안의 단일 `phase_code`는 실제 다중 prescription을 보존하도록 `phase_codes`로 사용한다. 현재 모델이
단일 primary movement pattern을 가지므로 `movement_pattern_codes` 대신
`primary_movement_pattern_code`를 사용한다. 실제 DB code와 다른 `difficulty_tier`를 새로 만들지 않는다.

Runtime query는 `with_payload=false`, `with_vector=false`를 기본으로 하고 Qdrant에서 UUID, score,
selection order만 받는다. Payload는 server-side filter와 build QA에만 사용한다.

## PoC performed and actual results

환경:

- Docker Desktop 29.6.2
- Qdrant `1.18.2`
- image `qdrant/qdrant:v1.18.2`
- image digest `sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c`
- localhost `6333`, `6334`만 bind
- Qdrant REST API와 synthetic UUID/3차원 vector 사용
- Python client와 embedding dependency는 설치하지 않음

| 검증 | 실제 결과 |
|---|---|
| UUID point upsert, `wait=true` | PASS |
| payload approval filter | PASS |
| eligible UUID `has_id` allowlist | PASS |
| cosine similarity 순위 | PASS |
| 동일 vector score | `1.0` |
| previous-plan `must_not has_id` 제외 | PASS |
| MMR query | PASS |
| 없는 UUID retrieve | PASS, 존재하는 point만 반환 |
| exact count | PASS, 3 points |
| alias 생성 | PASS |
| 단일 alias delete/create 요청 전환 | PASS |
| alias 전환 후 신규 collection 검색 | PASS |
| client timeout 감지 | PASS, 1,127ms 후 `System.Net.WebException` |

Alias API의 실제 경로는 `/collections/aliases`다. 탐색 중 `/aliases`를 호출한 첫 시도는 404였으며,
정확한 경로로 수정한 뒤 생성과 전환이 통과했다.

Timeout은 컨테이너를 일시 정지하고 PowerShell client `TimeoutSec=1`로 검증했다. 이는 client timeout
감지를 확인한 것이며 부하 상태의 Qdrant query-level timeout 검증은 아니다.

PoC 후 `--rm` 임시 container를 제거하고 Docker Desktop을 종료했다. 다운로드된 image만 local cache에
남아 있다.

## PostgreSQL integration boundary

일반 생성:

1. PostgreSQL과 SafetyPolicyEngine이 eligible/mandatory UUID를 확정한다.
2. allowlist machine code로 transient query vector를 생성한다.
3. Qdrant `has_id`와 catalog/index/approval payload filter를 함께 적용한다.
4. top-K UUID, score, MMR selection order만 받는다.
5. 동일 catalog version의 PostgreSQL row를 다시 조회한다.
6. existence, review, production eligibility, content version, constraint를 재검증한다.
7. mandatory와 승인 safe alternative를 병합한다.
8. retrieval metadata를 포함한 `ExercisePoolSnapshot`을 생성한다.

재생성:

- mandatory ID는 제외하지 않는다.
- 이전 non-mandatory ID는 `must_not has_id`로 우선 제외한다.
- MMR로 신규 후보 집합의 다양성을 높인다.
- 결과 부족 시 PostgreSQL 결정적 후보로 보충한다.
- 이전 후보를 다시 허용해도 Safety와 목표 적합도는 완화하지 않는다.
- Qdrant empty/timeout만으로 `NO_ALTERNATIVE_AVAILABLE`을 반환하지 않는다.
- PostgreSQL 전체 안전 후보에서도 의미 있는 변경이 불가능할 때만 해당 결과를 사용한다.
- 사용자별 embedding은 저장하지 않고 query vector로만 사용한다.

현재 56개 규모에서 explicit ID allowlist는 가능했다. 실제 catalog 확장 후에는 ID 수에 따른 request
크기와 filter latency를 benchmark한다. Chunk 검색은 전역 top-K를 보장하지 않으므로 사용 시 결과
병합 계약과 검증이 필요하다.

## Catalog/index synchronization and alias strategy

1. catalog/source와 embedding contract를 고정한다.
2. immutable 신규 collection을 만든다.
3. 승인된 PostgreSQL projection을 `wait=true`로 upsert한다.
4. exact count, UUID set, vector dimension, version, source document hash를 비교한다.
5. allowlist, missing ID, approval filter, MMR smoke test를 실행한다.
6. PostgreSQL catalog를 활성화한다.
7. alias delete/create를 한 요청으로 전환한다.
8. PostgreSQL registry에 active build를 기록한다.
9. rollback 기간 동안 이전 collection을 보존한다.

PostgreSQL과 Qdrant 사이에 분산 transaction이 없으므로 activation과 alias switch 사이의 짧은 구간은
version mismatch로 판단하고 deterministic fallback한다. In-place mixed-vector update는 사용하지 않는다.

향후 `vector_index_registry`는 catalog/source hash, collection, immutable build version, embedding model,
input schema, dimension, metric, expected count, status와 timestamp를 저장한다. Qdrant alias만으로 active
version을 판단하지 않는다.

## Failure and fallback behavior

다음은 모두 Vector 결과 폐기 또는 deterministic 보충 조건이다.

- unavailable, timeout, 5xx, alias/collection missing
- embedding provider failure
- catalog/index/embedding version mismatch
- eligible 밖 UUID, invalid/duplicate UUID, non-finite score
- stale approval/payload/content version
- PostgreSQL 재조회 누락
- zero/insufficient result

없는 ID는 Qdrant retrieve 응답에서 생략되므로 요청 UUID 집합과 응답 UUID 집합의 차이를 반드시
검사한다. Eligible 밖 ID나 version mismatch는 부분 채택하지 않고 해당 Vector retrieval을
non-canonical로 처리한다. PostgreSQL 장애는 Qdrant payload로 대체하지 않고 fail-closed한다.

## Onboarding pain impact

현재 frontend는 부위별 3단계 severity를 선택하지만 onboarding API에는 `attention_area_codes`만 보낸다.
Backend request와 `user_attention_areas`에도 severity/intensity가 없다.

확정 제안은 입력과 저장에 원본 1..10 값을 유지하고 service 내부에서 다음과 같이 정규화하는 것이다.

| `pain_intensity_score` | 내부 severity |
|---:|---|
| 1..3 | `MILD` |
| 4..7 | `MODERATE` |
| 8..10 | `SEVERE` |

- DB에는 원본 score를 저장하고 중복 severity column은 만들지 않는다.
- pure normalizer와 mapping version을 사용한다.
- decision snapshot에는 정규화 결과와 mapping version을 기록해 replay한다.
- 기존 row의 점수를 추정하거나 backfill하지 않는다.
- `NULL`은 `MILD`가 아니라 `UNSPECIFIED`다.
- 신규 request는 `pain_present`와 `pain_areas[{body_area_code, pain_intensity_score}]`를 사용한다.
- legacy `attention_area_codes`는 호환 기간 동안 유지한다.
- 두 필드가 함께 오면 body-area set이 같아야 하며 불일치는 validation error다.

주의: 최신 develop의 `pain-intensity-map-v1` 초안은 `1..3`, `4..6`, `7..10`이다. 이번 사용자 결정은
`1..3`, `4..7`, `8..10`이므로 현재 ADR/공통 문서와 충돌한다. 안전·통증 수치 계약은 개발리드, PM,
외부 도메인 검수 승인 후 별도 owner PR에서 정합화해야 하며 이번 보고서 PR은 해당 파일을 수정하지
않는다.

Migration 초안은 별도 `user_onboarding_pain_areas` 모델을 우선 검토한다. 기존
`user_attention_areas`에 nullable `SMALLINT`를 추가하는 방식은 변경량은 작지만 attention과 pain 의미를
결합한다. 어느 방식을 사용하든 1..10 CHECK, duplicate body-area unique, user cascade delete, nullable
legacy 호환과 no-backfill 원칙이 필요하다.

## Difficulty-only workout feedback impact

신규 완료 feedback은 `difficulty_code` 하나만 받는다. 운동 종료 후 신규 통증·이상 반응 입력은 만들지
않고 운동 중 `/api/v1/workout-sessions/{id}/safety-events`를 유지한다.

기존 feedback의 fatigue, satisfaction, `pain_occurred`, discomfort와 adverse reaction은 model, schema,
service, repository, history response, notification suppression과 weekly report에 연결돼 있다. 즉시 field와
column을 삭제하지 않고 다음 순서로 전환한다.

1. 신규 client write는 difficulty-only로 전환한다.
2. Legacy client field는 호환 기간 동안 명시적으로 처리한다.
3. 운동 중 safety-event가 health/safety 입력의 canonical 경로가 된다.
4. 기존 closed report와 historical feedback row는 보존한다.
5. 신규 weekly aggregate의 `pain_report_count`는 그 주의
   `workout_safety_event_discomforts`가 존재하는 distinct session 수로 versioned 전환한다.
6. Daily pain과 legacy post-workout pain을 새 aggregate에 중복 집계하지 않는다.
7. 소비자 전환 뒤 별도 migration에서 legacy column 제거를 검토한다.

누락된 post-workout pain을 `false`로 저장하면 미수집과 통증 없음이 섞이므로 허용하지 않는다.

## Security and privacy impact

- Qdrant에 직접 식별자와 health data를 저장하지 않는다.
- 통증 부위·점수·severity를 payload, vector, embedding source/query에 포함하지 않는다.
- Query vector는 transient이며 사용자별 point를 만들지 않는다.
- Runtime log는 version, count, latency와 canonical failure code만 기록한다.
- API key, vector, query document, eligible ID 전체, provider exception 원문은 log/metric label에 넣지 않는다.
- Pain score는 민감 건강정보이므로 동의, 보존, 계정 삭제와 출시 전 개인정보 검토가 필요하다.

## Dependencies and infrastructure requirements

후속 구현에는 다음이 필요하다.

- pinned Qdrant server image/digest. MMR을 사용하려면 1.15 이상
- 서버와 호환되는 pinned `qdrant-client`
- 승인된 embedding provider/model/revision/license/dimension/distance
- `QDRANT_ENABLED`, URL, SecretStr API key, timeout, alias, top-K, MMR 설정
- embedding model/version/document-schema/timeout 설정
- localhost Docker integration environment와 synthetic catalog fixture
- fake adapter unit test와 별도 Qdrant integration marker
- 운영 TLS/auth, backup, monitoring, retention과 rollback runbook

Production dependency와 `pyproject.toml`/`uv.lock` 변경은 ADR-0014 승인 후 별도 PR에서 수행한다.

## Expected implementation files

Qdrant 후속 구현 예상:

- `backend/app/core/config.py`, `backend/.env.example`
- `backend/app/integrations/`의 Qdrant adapter
- catalog projection/revalidation repository와 retrieval port/service
- index rebuild/validation script
- vector registry와 retrieval audit additive migration
- unit/integration/golden/privacy/fallback tests
- `pyproject.toml`, `uv.lock`, local infra/runbook
- 개발리드 contract가 허용한 ExercisePool loader/snapshot 연결부

Pain과 feedback 후속 구현 예상:

- profile/workout/weekly report model, schema, service, repository
- 신규 additive migration. 기존 migration 파일은 수정하지 않음
- onboarding/workout/weekly API·unit·integration tests
- frontend onboarding, result/history API type, UI와 component tests
- 공개 계약과 DATA_MODEL의 owner 승인 변경

## Tests run and results

- Qdrant REST PoC assertion: PASS
- `git diff --check`: PASS
- production backend/frontend test: 실행하지 않음. Production code 변경 없음
- formatter/linter/type checker: 실행하지 않음. Markdown 문서만 변경
- 실제 embedding 품질/latency benchmark: 실행하지 않음
- 실제 PostgreSQL-Qdrant integration: 실행하지 않음

## Known limitations

- Synthetic 3차원 vector 검증이므로 실제 한국어 embedding 품질을 증명하지 않는다.
- 실제 PostgreSQL UUID 56개를 사용한 index build는 수행하지 않았다.
- 대규모 eligible allowlist 성능과 MMR 품질 승격 기준은 미검증이다.
- Query-level server timeout, replica consistency와 운영 topology는 검증하지 않았다.
- ADR-0014는 `PROPOSED`이므로 production dependency/adapter/migration을 시작할 수 없다.
- 통증 threshold는 현재 develop 문서와 사용자 결정이 충돌해 필수 안전 승인이 필요하다.

## Questions requiring team-lead decision

1. ADR-0014 필수 reviewer 승인과 `ACCEPTED` 전환 여부
2. embedding model/revision/license/dimension/distance와 품질 승격 기준
3. collection allowlist naming, Qdrant topology와 운영 owner
4. `user_onboarding_pain_areas` 별도 테이블과 기존 테이블 nullable column 중 물리 모델
5. 사용자 결정 `1..3 / 4..7 / 8..10`을 `pain-intensity-map-v1`로 승인할지
6. difficulty-only cutover 일정과 legacy feedback 제거 release
7. 실제 task/issue ID가 발급되면 임시 `TASK-BACKEND-008` 식별자를 교체할지

## Manual verification steps

1. `rg -n "Qdrant|ExercisePoolSnapshot|eligible_exercise_ids" docs`
2. `rg -n "pain-intensity-map-v1|pain_intensity_score|difficulty_code|pain_report_count" docs`
3. `git diff --check`
4. ADR-0014가 `PROPOSED`이고 production dependency/migration이 추가되지 않았는지 확인
5. 보고서에 사용자 식별자, 건강 원문, token, secret 또는 실제 user UUID가 없는지 확인
6. 후속 승인 PoC에서는 pinned image로 UUID upsert, filter, MMR, missing ID, timeout과 alias switch를 재실행
