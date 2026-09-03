# ADR-0014: Qdrant 기반 ExercisePool Vector Retrieval

- 상태: ACCEPTED
- 날짜: 2026-08-24
- 소유자: AI/data lead
- 필수 승인자: 개발팀장 + 백엔드 owner + PM + 외부 도메인 검수자
- 개인정보 검토: 출시 전 법률/개인정보 검토
- 관계: ACCEPTED ADR-0013의 `ExercisePoolSnapshot` 생성 단계를 구체화하며 Safety-first 순서와
  Agent/Coordinator DB 접근 금지를 변경하지 않음
- 관련 요구사항/이슈: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`, `TASK-AGENT-003`

## 배경

ADR-0013은 결정적 `SafetyPolicyEngine`과 `ConstraintEnvelope` 뒤에서 승인 운동 pool을 고정하도록
정했다. 카탈로그가 커지면 목표·이전 계획과 유사한 운동을 우선하고 결과의 다양성을 확보할 검색
계층이 필요하지만, Vector 검색이 안전 또는 운영 카탈로그의 진실 공급원이 되어서는 안 된다.

이 ADR은 구현 승인이 아니라 문서 수준의 V3 검색 계약 초안이다. Qdrant client, production adapter,
collection, embedding job, LangGraph/LangChain runtime, dependency와 물리 DB migration은 후속 작업이다.

## 결정

### 1. 책임과 진실 공급원

- PostgreSQL은 운동, 검수 상태, 목표·처방, 안전 규칙, 대체 관계와 모든 decision audit의 canonical
  source of truth다.
- Qdrant는 PostgreSQL 승인 카탈로그에서 재구축할 수 있는 derived search index다. Qdrant 단독
  데이터는 운동의 존재, 승인, 안전 또는 처방 근거가 아니다.
- `SafetyPolicyEngine`은 모든 LLM과 Vector 검색보다 먼저 결정적으로 실행된다.
- `ConstraintEnvelope`는 Safety, 요청 시간, 목표, 장비, 장소와 Recovery/return 상한을 고정한다.
- PostgreSQL deterministic filter가 먼저 `eligible_exercise_ids`, `mandatory_exercise_ids`와 승인된
  안전 대체 운동을 계산한다.
- Qdrant는 `eligible_exercise_ids` 범위 안의 순위와 다양성만 결정한다.
- Qdrant 반환 ID는 PostgreSQL에서 같은 `catalog_version`으로 다시 조회해 존재, 검수·운영 승인,
  constraint 적합성과 content version을 재검증한 뒤에만 `ExercisePoolSnapshot`에 포함한다.
- 필수 목표 운동과 승인된 안전 대체 운동은 Vector 순위·누락과 무관하게 보존한다.
- Agent와 Coordinator는 PostgreSQL, repository, ORM, raw SQL, Qdrant 또는 Vector tool을 직접 호출하지
  않는다. application loader/retrieval adapter가 만든 동일한 envelope와 snapshot만 받는다.

### 2. 고정 실행 순서

```text
minimum input snapshot
-> deterministic SafetyPolicyEngine
-> immutable ConstraintEnvelope
-> PostgreSQL deterministic eligible/mandatory ID filter
-> ExerciseRetriever(Qdrant ranking within eligible IDs)
-> PostgreSQL canonical re-read and validation
-> mandatory/safe-alternative preservation
-> immutable ExercisePoolSnapshot
-> three parallel LLM Agents
```

Safety가 plan generation을 금지하면 PostgreSQL 후보 계산과 Qdrant 호출을 모두 생략한다. Qdrant
오류는 Safety 결과를 바꾸지 않으며, 안전하게 계획 가능한 deterministic pool을 만들 수 있으면 그
pool로 계속한다.

### 3. `ExerciseRetriever` 도메인 포트

도메인 포트는 provider SDK 타입을 노출하지 않는 pure Python/Pydantic 계약이다. production adapter는
후속 단계에서 integrations 경계에 둔다.

#### `ExerciseRetrievalRequest` (`exercise-retrieval-request-v1`)

| 필드 | 계약 |
|---|---|
| `catalog_version` | PostgreSQL ACTIVE/production-approved catalog version |
| `constraint_envelope_hash` | 요청을 만든 immutable envelope의 canonical SHA-256 |
| `eligible_exercise_ids` | PostgreSQL에서 결정적으로 허용된 UUID의 중복 없는 canonical 정렬 목록 |
| `mandatory_exercise_ids` | eligible의 부분집합. 목표/승인 안전 대체 보존 대상 |
| `previous_plan_exercise_ids` | 같은 사용자 lineage의 이전 plan 순서. 없으면 빈 목록 |
| `normalized_query_codes` | allowlist machine code의 정렬·중복 제거 목록. 자유 문구 금지 |
| `retrieval_mode` | `VECTOR_RANKED` 또는 `DETERMINISTIC_ONLY` |
| `requested_limit` | 양의 정수. 정책 버전의 최대치 이하 |

`eligible_exercise_ids`와 `mandatory_exercise_ids`가 비어야 하는 Safety 차단 상태에서는 이 요청을
만들지 않는다. `requested_limit`은 mandatory 보존을 위한 최종 snapshot 크기 상한으로 해석하지
않으며, Vector가 반환할 비필수 순위 수의 상한이다.

#### `ExerciseRetrievalResult` (`exercise-retrieval-result-v1`)

| 필드 | 계약 |
|---|---|
| `ranked_exercise_ids` | 중복 없는 유효 순위 목록. Vector 성공 시 eligible의 부분집합이어야 함 |
| `similarity_scores` | ranked ID와 index가 1:1로 대응. Vector 항목은 finite decimal, deterministic fallback 항목은 null |
| `collection_name` | 사용한 allowlisted collection. Vector 미호출/미도달 시 null |
| `vector_index_version` | collection의 불변 index build version. 미도달 시 null |
| `embedding_model_version` | index를 만든 embedding model/version. 미도달 시 null |
| `query_hash` | 식별자·통증 없이 canonical query code와 request version으로 만든 SHA-256 |
| `retrieval_status_code` | 성공 또는 단일 canonical 원인 code |
| `fallback_used` | deterministic pool을 사용했으면 true |

`similarity_scores`는 사용자에게 공개하지 않고 안전 임계값으로 사용하지 않는다. invalid ID, 중복,
NaN/Infinity, 길이 불일치 또는 version 불일치는 성공 결과가 아니다.

### 4. `ExercisePoolSnapshot` V3

`exercise-pool-snapshot-v3`의 최소 필드는 다음과 같다.

| 필드 | 계약 |
|---|---|
| `schema_version` | `exercise-pool-snapshot-v3` |
| `catalog_version` | PostgreSQL canonical catalog version |
| `constraint_envelope_hash` | 요청 envelope hash |
| `exercises` | PostgreSQL 재검증을 통과한 selected exercise record의 canonical 배열 |
| `mandatory_exercise_ids` | snapshot에 반드시 존재하는 목표/안전 대체 ID |
| `vector_ranked_exercise_ids` | 재검증을 통과한 Qdrant 순위 ID. fallback-only면 빈 목록 |
| `pool_hash` | retrieval metadata를 포함한 canonical snapshot SHA-256 |
| `retrieval_metadata` | request/result schema, collection/index/embedding/query version·hash, status와 fallback |
| `created_at` | timezone-aware timestamp. hash 입력에는 포함하지 않음 |

selected exercise record는 ID, catalog/content version, goal/location/equipment/movement tag, 검수된
처방 범위와 source/review reference만 가진다. 사용자 ID, 통증 부위·점수, 원문 건강정보와 raw
wearable 값은 포함하지 않는다. `mandatory_exercise_ids`가 `exercises`의 부분집합이 아니면 snapshot
생성은 실패한다.

### 5. Graph State의 Vector Retrieval 필드

`v3-graph-state-v1`은 다음 immutable field를 추가한다.

- `eligible_exercise_ids`
- `mandatory_exercise_ids`
- `exercise_retrieval_request`
- `exercise_retrieval_result`
- `exercise_pool_snapshot`
- `exercise_pool_hash`
- `retrieval_failure_codes`
- `deterministic_pool_fallback_used`

loader/retrieval node만 위 필드를 생성한다. Agent fan-out은 동일한 `ConstraintEnvelope`와
`ExercisePoolSnapshot` projection만 받고 retrieval request/result 원문이나 DB/Qdrant handle을 받지
않는다. Coordinator도 snapshot 밖의 후보를 선택할 수 없다.

### 6. canonical retrieval code

저장소 검색 결과 기존 code와 중복되지 않아 다음 이름을 채택한다.

| code | 의미와 처리 |
|---|---|
| `VECTOR_RETRIEVAL_SUCCEEDED` | Qdrant 결과가 PostgreSQL 재검증을 통과함 |
| `VECTOR_INDEX_UNAVAILABLE` | Qdrant/collection 접근 불가. fallback |
| `VECTOR_INDEX_NOT_READY` | collection build/activation 미완료. fallback |
| `VECTOR_INDEX_VERSION_MISMATCH` | 요청 catalog/index/embedding version 불일치. fallback |
| `VECTOR_SEARCH_TIMEOUT` | 정책 timeout 초과. fallback |
| `VECTOR_RESULT_STALE` | 반환 payload/catalog freshness 불일치. 결과 폐기 후 fallback |
| `VECTOR_RESULT_NOT_CANONICAL` | eligible 밖 ID 또는 PostgreSQL 재검증 실패. invalid 결과 폐기 |
| `VECTOR_RESULT_INSUFFICIENT` | 재검증 후 비필수 결과가 정책 최소 수 미달. deterministic 보충/fallback |
| `DETERMINISTIC_POOL_FALLBACK_USED` | 위 원인 뒤 결정적 후보 생성이 실제 사용된 audit event |

`retrieval_status_code`는 성공 또는 가장 앞선 단일 원인을 저장하고, `retrieval_failure_codes`는 발생한
원인을 위 표 순서의 canonical 배열로 저장한다. fallback event는 원인 code를 대체하지 않는다.
fallback도 mandatory 보존과 PostgreSQL 재검증을 통과해야 하며 안전한 pool을 만들 수 없으면 기존
계획 없는 `REST`/`NEEDS_INPUT`/`FAILED` 경계를 따른다.

### 7. collection과 embedding version

- collection name은 환경·catalog family·embedding contract를 나타내는 allowlisted logical name이며
  사용자 입력으로 만들지 않는다.
- collection alias의 mutable 현재값과 별도로 불변 `vector_index_version`을 저장한다.
- index build는 `catalog_version`, source manifest hash, embedding model/version, embedding input
  schema version, distance metric, vector dimension, build hash와 activation status를 가진다.
- query는 동일한 `embedding_model_version`과 normalized code schema를 사용해야 한다.
- version mismatch를 암묵적으로 허용하거나 다른 collection으로 재시도하지 않는다.

### 8. PostgreSQL 논리 저장과 replay

후속 persistence 단계는 additive하게 다음을 저장한다.

- `vector_index_registry`: collection, 불변 index/build version, catalog/source hash, embedding
  model/input schema, metric/dimension, status, build/activation timestamp
- `decision_exercise_retrievals`: envelope/pool FK, request/result schema와 hash, eligible/mandatory ID
  hash, normalized query code hash, collection/index/embedding version, query hash, status/failure code,
  returned/revalidated ID와 score, fallback version/사용 여부, latency와 created timestamp

replay는 Qdrant나 embedding provider를 다시 호출하지 않는다. 저장된 envelope, request/result,
PostgreSQL 재검증 결과, final snapshot과 hash, catalog/collection/index/embedding/graph/prompt/model
version으로 동일한 Agent 입력을 복원할 수 있어야 한다. score와 latency는 감사 정보일 뿐 Safety와
최종 action을 재판정하지 않는다.

### 9. 개인정보와 건강정보 제한

- 직접 사용자 식별정보, 날짜, 자유 체크인, 통증 부위, `pain_intensity_score`, severity, 원문 건강정보,
  raw wearable data를 vector, payload, embedding input/query에 포함하지 않는다.
- Qdrant payload는 exercise ID와 비사용자 catalog/index/version metadata로 제한한다.
- `normalized_query_codes`는 목표·운동 유형·장비·장소처럼 승인된 비민감 code allowlist만 사용한다.
- 로그·metric label에는 query 원문, eligible ID 전체 목록, 사용자/decision ID와 provider 예외 원문을
  넣지 않는다.

## 결정 이유

> 사후 정리(2026-08-27). 이 절은 원래 결정 시점에 기록되지 않았고, `docs/adr/README.md`가 요구하는
> 필수 항목을 뒤늦게 채운 것이다. 아래는 구현된 계약과 staging 증적에서 역으로 정리한 근거이며,
> 당시 실제 판단 근거와 다를 수 있다. **ADR 승인자 확인이 필요하다.**

### Qdrant

- **derived index 경계를 물리적으로 강제한다.** 이 ADR의 핵심은 PostgreSQL이 진실 공급원이고 Qdrant는
  언제든 재구축 가능한 파생 index라는 것이다. 별도 서비스로 두면 "Qdrant 단독 데이터는 운동의 존재·
  승인 근거가 아니다"라는 규칙이 코드 리뷰가 아니라 배포 구조로 지켜진다.
- **불변 collection과 alias 교체를 기본 제공한다.** 이 ADR은 불변 `vector_index_version`과 mutable
  alias를 분리하도록 요구한다. Qdrant의 alias는 이 교체를 원자적으로 수행하고 롤백도 alias를 되돌리는
  것으로 끝난다.
- **payload filter로 eligible ID 범위를 강제할 수 있다.** Qdrant는 PostgreSQL이 계산한
  `eligible_exercise_ids` 안에서만 순위를 매겨야 하는데, payload index 기반 필터가 이를 검색 단계에서
  직접 표현한다.
- **개인정보 경계를 감사하기 쉽다.** payload를 exercise ID와 비사용자 catalog/version metadata로
  제한하므로, 별도 저장소에 무엇이 들어 있는지 점검하는 범위가 좁다.

### `text-embedding-3-large` / dimension 3072

`docs/tasks/TASK-AGENT-150.md`의 2026-08-27 승인 기록이 근거다. 요약하면 provider 문서가 이 모델을
영어·비영어 텍스트 모두에서 가장 성능이 높은 embedding model로 설명하고, 검수 운동 102건의 한국어
이름·설명 검색 품질을 우선했다. 카탈로그 규모가 작아 3072 dimension의 저장·비용 부담이 제한적이므로
`dimensions` 축소 없이 기본값을 쓴다.

### COSINE

- 이 provider의 embedding은 정규화되어 반환되므로 cosine과 내적의 순위 결과가 사실상 같고, cosine이
  provider 문서와 생태계의 관례다.
- cosine은 벡터 크기에 영향을 받지 않으므로, 이후 정규화를 보장하지 않는 모델로 바뀌어도 순위 의미가
  유지된다. metric 변경은 collection 재구축을 요구하므로 보수적인 쪽을 택한다.
- metric은 index build identity의 일부이며 query 시 재선택할 수 없다. 즉 이 선택은 `COSINE`으로
  고정된 index를 만들고, 바꾸려면 새 `vector_index_version`으로 재구축해야 한다.

## 검토한 대안

기록이 남아 있지 않다. 아래는 이 결정 구조에서 실제로 비교 대상이 되는 선택지이며, 당시 검토
여부는 확인되지 않았다.

| 대안 | 성격 |
|---|---|
| PostgreSQL `pgvector` | 별도 서비스 없이 기존 DB에 vector column 추가 |
| managed vector SaaS | 운영 부담을 외부에 위임 |
| in-process ANN 라이브러리 | 프로세스 메모리에 index 상주 |
| vector 검색 없이 결정적 정렬만 사용 | 현재 fallback 경로를 유일 경로로 사용 |

## 선택하지 않은 대안과 이유

> 아래도 사후 정리다. 당시 배제 사유가 기록되지 않았다.

- **`pgvector`**: 가장 유력한 대안이었을 것이다. 운영 구성 요소가 늘지 않는다는 장점이 크다. 다만 이
  ADR이 요구하는 "canonical source와 derived index의 분리"가 같은 데이터베이스 안에서는 규칙으로만
  유지된다. 카탈로그 102건 규모에서는 성능 차이가 결정적이지 않으므로, 이 선택은 성능이 아니라 경계
  강제 방식의 문제로 보는 것이 맞다.
- **managed vector SaaS**: 이 서비스는 건강 관련 도메인이고 ADR-0014가 신규 외부 서비스에 보안·
  개인정보 검토를 요구한다. 자체 운영 가능한 엔진 쪽이 검토 범위를 좁힌다.
- **in-process ANN 라이브러리**: alias 기반 무중단 교체, 불변 index version, 재시작 간 영속성을
  직접 구현해야 한다. 이 ADR의 replay·lineage 요구사항 대비 구현 부담이 크다.
- **vector 검색 미도입**: 결정적 정렬만으로도 안전한 pool은 만들 수 있다. 실제로 fallback 경로가
  그렇게 동작한다. 다만 이 ADR의 목적인 목표·이전 계획 유사도 기반 우선순위와 다양성 확보를
  달성하지 못한다.

## 장애 fallback

Vector 검색은 품질 향상 계층이므로 장애가 안전 실패를 만들지 않는다. timeout은 bounded하고 provider
retry는 같은 request에 최대 한 번만 허용한다. 이후 PostgreSQL 승인 후보를 stable code/goal
preservation/이전 계획/정책 version의 결정적 정렬로 생성한다. mandatory와 승인 안전 대체를 먼저
포함하고 남은 자리를 deterministic 후보로 채운다. fallback 결과도 snapshot hash와 audit metadata를
저장한다.

## 다음 구현 단계 인수 조건

1. Safety 차단이면 Qdrant가 호출되지 않는다.
2. eligible ID는 PostgreSQL에서 먼저 결정되고 Qdrant filter에도 적용된다.
3. Qdrant 밖 ID와 stale/version-mismatch 결과는 PostgreSQL 재검증에서 제거된다.
4. mandatory 목표 운동과 승인 안전 대체는 Vector 결과에 없어도 snapshot에 남는다.
5. Qdrant timeout/unavailable/not-ready에서 같은 envelope의 deterministic pool로 성공하거나 계획 없이
   fail-closed한다.
6. Agent/Coordinator에 DB, repository, Qdrant client/tool이 주입되지 않는다.
7. 통증 부위·점수, 직접 식별자와 raw 건강·웨어러블 값이 embedding/query/payload/log에 없다.
8. 같은 stored retrieval record와 version으로 Qdrant 재호출 없이 pool과 downstream result를 replay한다.
9. catalog/index/embedding/collection/graph/prompt/model version lineage가 끊기지 않는다.
10. migration과 API는 별도 owner 승인 및 하위 호환 전략을 갖는다.

## 다음 구현 단계 테스트 시나리오

- Safety veto/REST/STOP_AND_SEEK_HELP에서 Qdrant adapter zero-call
- eligible allowlist 밖 Qdrant ID 주입과 `VECTOR_RESULT_NOT_CANONICAL`
- mandatory ID가 Vector top-k 밖이어도 pool 보존
- stale catalog payload와 index/embedding version mismatch fallback
- timeout, unavailable, not-ready와 deterministic ordering/hash 재현
- 일부 invalid/중복/NaN score 결과의 폐기와 insufficient 보충
- PostgreSQL 재조회 중 review status 변경 시 fail-closed
- Agent/Coordinator dependency graph에 DB/Qdrant port가 없는지 architecture test
- embedding/query/payload/log privacy allowlist test
- stored-output replay와 graph/prompt/model/index version linkage test

## 영향과 승인 경계

- 이 ADR은 accepted ADR-0013의 의미를 폐기하지 않고 pool 생성 단계만 확장한다.
- Qdrant는 신규 외부 서비스이므로 개발팀장과 운영 담당 승인, 보안·개인정보 검토가 필요하다.
- Vector 결과가 안전 대체 우선순위나 통증 정책을 바꾸는 변경은 이 ADR 범위가 아니며 별도 PM·외부
  도메인 승인이 필요하다.
- 물리 schema, dependency와 production adapter는 이 ADR이 ACCEPTED되기 전 구현하지 않는다.

## 알려진 제한

- collection naming의 실제 값, embedding provider/model, dimension, distance metric과 retrieval limit은
  정하지 않았다.
- 성능·품질 승격 기준과 Qdrant 운영 topology는 후속 구현/운영 ADR에서 정한다.
