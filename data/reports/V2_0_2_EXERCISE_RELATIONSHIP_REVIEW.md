# v2.0.2 운동 관계 후보 Queue 분리 보고서

생성일: 2026-08-27  
상태: `DRAFT_REVIEW_QUEUE`  
운영 적격: `false`

## 결론

603건을 관계 유형과 HOME 서비스 정책으로 먼저 분리했다. 원본 review batch의
603행은 삭제하지 않고, 모든 행에 `queue_code`, `decision_code`, `decision_source`,
`decision_reason_code`, `decision_note`, `human_review_required`를 추가했다.
Human Review 행에는 `human_review_reason_ko`로 보류 사유를 한국어로 기록했다.

1차 라우팅 기준 최종 사람이 직접 확인할 `HUMAN_REVIEW_QUEUE`는 342건이었고,
후속 중복 확인에서 동일 방법·타겟인 10개 pair행을 제거하여 현재는 332건이다.

## 라우팅 결과

| Queue | 기준 | 건수 |
|---|---|---:|
| `VARIANT_CANDIDATE_QUEUE` | `PRIMARY_VARIANT` 74 + `SECONDARY_VARIANT` 5 | 79 |
| `SEPARATE_EXERCISE_QUEUE` | 기존 `SEPARATE_EXERCISE` 58 + 명백한 비관계 116 | 174 |
| `HOME_POLICY_EXCLUDED_QUEUE` | HOME 양쪽 후보 중 허용 장비 외 `STEP_BOX` 관계 | 8 |
| `HUMAN_REVIEW_QUEUE` | 위 규칙으로 결정할 수 없는 `REVIEW_REQUIRED` 중 중복 제거 후 | 332 |
| **합계** |  | **593** |

기존 집계의 `PRIMARY_VARIANT` 75건 중 동일 정규화명 중복으로 삭제된 pair행 1건이
반영되어, 현재 원본 batch에서는 74건이다.

Human Review Queue에서는 동일 stable code·운동 방법·primary/secondary target을
가지며 이름만 번역·설명 차이인 10개 pair행을 추가 제거했다. 우측 `EXERCISE`
record를 유지하고 좌측 `V1_ALIAS` 관계행을 삭제했다.

Variant 후보도 실제 수행 형태 확인이 필요하므로 `human_review_required=true`로
남겼다. 반면 별도 운동·HOME 정책 제외·명백한 비관계 자동 처리는
`decision_source=AUTO_RULE`과 세부 근거 코드로 기록했다.

## 적용 규칙

- Variant 후보: `candidate_relation_code`가 `PRIMARY_VARIANT` 또는
  `SECONDARY_VARIANT`이면 `VARIANT_CANDIDATE_QUEUE`로 보낸다.
- 기존 별도 운동: `SEPARATE_EXERCISE`이면 `SEPARATE_EXERCISE_QUEUE`로 보낸다.
- 명백한 비관계: `REVIEW_REQUIRED`이면서 `movement_pattern_match=false`이고
  `primary_body_area_overlap=0.000`이면 별도 운동으로 처리한다.
- HOME 제외: 양쪽 `location_codes`에 `HOME`이 있고 장비를 비교하는 관계에서
  `STEP_BOX`가 포함된 8건은 `HOME_POLICY_EXCLUDED_QUEUE`로 보낸다. HOME 허용
  장비 코드는 `BODYWEIGHT`, `DUMBBELL`, `MAT`, `FOAM_ROLLER`, `JUMP_ROPE`,
  `RESISTANCE_BAND`로 고정했다.
- 위 조건에 해당하지 않는 항목만 `HUMAN_REVIEW_QUEUE`로 보낸다.

생활용품 대체는 장비 자동 추가가 아니라 운동 설명에 안내하는 정책이므로,
이번 HOME 제외 규칙의 허용 장비로 취급하지 않았다.

HOME 자동 제외는 장비 원인과 관계가 명확한 `STEP_BOX` 8건으로 보수적으로
한정했다. 다른 비허용 장비가 포함되더라도 관계 원인이 불명확한 항목은
`HUMAN_REVIEW_QUEUE`에 남겼다.

## 입력과 산출물

- 입력 catalog: [`exercises_v1_v2.csv`](../generated/exercise-catalog-v2.0.2-draft/catalog/exercises_v1_v2.csv)
  - `EXERCISE` 102건, `V1_ALIAS` 114건
  - 이전 동일 정규화명 중복 제거 후 총 216 records
- 원본 batch: [`review_batch.jsonl`](../validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0/review_batch.jsonl)
- CSV batch: [`review_batch.csv`](../validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0/review_batch.csv)
- Queue manifest: [`queue_manifest.json`](../validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0/queue_manifest.json)
- 사람 검토 Queue: [`human_review_queue.jsonl`](../validation/review_batches/exercise-catalog-v2.0.2-relationship-review-v0.1.0/human_review_queue.jsonl)
- 재현용 생성기: [`build_v2_0_2_exercise_relationship_review.py`](../scripts/build_v2_0_2_exercise_relationship_review.py)
- Queue 라우터: [`route_v2_0_2_relationship_queues.py`](../scripts/route_v2_0_2_relationship_queues.py)

JSONL과 CSV의 candidate pair ID 집합은 일치한다. Queue 파일은 원본 batch의 비중복
partition이며, 자동 분류된 261건은 원본 batch에도 그대로 남아 있다. 중복 제거 후
원본 review batch는 593건, Human Review Queue는 332건이다.

## 샘플 검증

다음 유형을 각 1건씩 확인했다.

- Variant: `RELATION_TYPE_VARIANT` → Variant Queue
- 기존 별도 운동: `RELATION_TYPE_SEPARATE_EXERCISE` → Separate Queue
- 규칙 기반 비관계: `NO_MOVEMENT_OR_PRIMARY_AREA_OVERLAP` → Separate Queue
- HOME 제외: `HOME_UNSUPPORTED_STEP_BOX` → HOME Excluded Queue
- 미결정: `NO_DETERMINISTIC_QUEUE_RULE` → Human Review Queue

자동 분류는 최종 운동 병합이나 stable code 변경이 아니라 검토 Queue 라우팅이다.
원본 관계 코드와 원본 후보 데이터는 보존하며, 운영 반영 전 사람 검토가 필요하다.
