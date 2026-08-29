# v2.0.2 통증 Alternative 재검토 결과

생성일: 2026-08-28  
정책: `exercise-alternative-policy-v2.0.2-v1.0.0`  
상태: `DRAFT_REVIEW_REQUIRED`  
운영 적격: `false`

## 결론

v2.0.2-final catalog와 확정된 Variant·HOME/GYM Context Default를 기준으로 기존 Alternative 279건을 재검토했다. Alternative에는 `DISCOMFORT` 조건만 남겼고, target이 보고된 불편 부위를 계속 포함하는 관계는 `NRS_1_3`라도 삭제했다. `REVIEW_REQUIRED`로 남긴 기존 52건은 없다.

| 구분 | 건수 |
|---|---:|
| 기존 Alternative | 279 |
| 유지 | 157 |
| 제거·재분류 | 122 |
| `REVIEW_REQUIRED` | 0 |
| normalized discomfort Alternative | 157 |

normalized 157건은 stable code 통합으로 합쳐진 legacy 관계 155건과 neck 보강 candidate 2건으로 구성된다. 통합된 원본 identity는 `legacy_relation_identities`에 보존한다.

### 기존 Alternative reason별 집계

| 기존 reason | 유지 | 제거·재분류 | 추가 검토 |
|---|---:|---:|---:|
| `DISCOMFORT` | 157 | 53 | 0 |
| `EQUIPMENT` | 0 | 19 | 0 |
| `LOCATION` | 0 | 34 | 0 |
| `DIFFICULTY` | 0 | 6 | 0 |
| 합계 | **157** | **122** | **0** |

제거·재분류 122건은 다음과 같다.

- 동일 불편 부위 target 52건: `REMOVE_TARGET_RETAINS_DISCOMFORT_AREA`
- neck 불편에서 안전성이 확인되지 않은 core/bracing target 1건: `REMOVE_NECK_TARGET_SAFETY_UNCONFIRMED`
- Variant 또는 동일 exercise identity 중복 10건: `RECLASSIFY_VARIANT_OR_EXERCISE_IDENTITY`
- 장비 19건: `RECLASSIFY_VARIANT`
- 장소 34건: `RECLASSIFY_CONTEXT_DEFAULT`
- 난이도 6건: `RECLASSIFY_DIFFICULTY_VARIANT`

## 판정 기준

- source가 보고된 불편 부위를 포함하고 target은 해당 부위를 포함하지 않아야 한다.
- target 난이도는 source보다 높지 않아야 한다.
- 동일 부위 target은 통증 정도가 낮아도 부담 회피를 충족하지 못하므로 Alternative에서 제거한다.
- 장비 차이는 Variant, HOME/GYM 차이는 Context Default, 단순 난이도 차이는 Variant 체계로 재분류한다.
- `PRIMARY_VARIANT`, `SECONDARY_VARIANT`는 Alternative 사유가 아니다. 단, 통증 조건과 안전 target 근거가 독립적으로 있으면 exercise row를 target으로 참조할 수 있다.
- `NRS_1_3`도 Alternative 관계를 적용한다. 원 운동이 보고된 불편 부위를 사용하면 해당 부위를
  피하는 `NRS_1_3` target을 우선 사용하고 `LOAD_REDUCED`를 적용한다. `NRS_4_6`은
  `SKIP_AFFECTED_AREA`, `NRS_7_10`은 `STOP_EXERCISE`이며 Alternative를 만들지 않는다.
- 유지 관계도 외부 도메인 승인 전까지 `review_status_code=REVIEW_REQUIRED`, `production_eligible=false`다.

## 영역별 보강·안전성 검토

### 전 부위 Alternative target map

기존 legacy 관계 검토 결과와 별도로, map 생성 당시의 201개 후보 catalog snapshot을 이용해 11개 사용자 입력 통증 부위 전체를 덮는 target map을 생성했다. 현재 통합 v2.0.2-final catalog는 170개 운동이므로, backend 적재 전 map의 source·target stable code를 현재 catalog와 다시 대조해야 한다. source가 해당 부위를 primary 또는 secondary target으로 포함할 때만 map을 만들고, target은 선택된 통증 부위를 primary·secondary 어디에도 포함하지 않는다. source별·강도별 최대 12개 후보를 제공한다.

- `NRS_1_3`: 해당 부위를 피하는 cross-training target을 사용하고 volume·load·난이도를 낮추거나 유지한다.
- `NRS_4_6`: `recovery_eligible` 저부하 target만 사용하며 affected area를 건너뛴다.
- `NRS_7_10`: target map을 사용하지 않고 운동 중단 정책으로 보낸다.
- 복수 통증 부위는 각 부위 target set의 교집합을 사용하고, 교집합이 없으면 generalized REST/STOP 정책으로 전환한다.

초기 후보 map은 2,455건이며 11개 부위 모두 mild·moderate source coverage와 target coverage를 확보했다. 대표적인 우회 경로로 어깨 불편 시 `스탠딩 카프 레이즈`, 무릎 불편 시 `랫풀다운`을 포함한다.

### map의 보수적 자동 검수

위 원본 map을 다음 순서로 재검수했다. 각 후보는 `KEEP` 또는 `REMOVE`로만 판정했고, 애매한 후보는 사람 검수 큐로 보내지 않고 제거했다.

`catalog reference eligibility → primary/secondary pain-area overlap 제거 → movement/load/impact 위험 제거 → NRS·recovery 조건 적용 → HOME/GYM·장비·난이도 필터 → 남은 후보 유지`

| 구분 | 건수 |
|---|---:|
| 검수 입력 map | 2,455 |
| 검수 후 유지 | 1,517 |
| 제거 | 938 |
| 사람 검수 이관 | 0 |
| `NRS_7_10` Alternative | 0 |

제거 938건은 catalog 참조·movement/load/impact 조건을 통과하지 못한 후보이며, 유지 map에서 통증 부위 overlap은 0건이다. 현재 통합 catalog의 Variant·SEPARATE_EXERCISE 후보는 별도 독립 바인딩·승인 후에만 backend 관계 target으로 편입한다. 이 결과는 `SECONDARY_VARIANT`를 Alternative로 취급한 것이 아니라, 애매한 참조를 fail-closed로 제거한 것이다.

검수 후 map은 pain area별 mild(`NRS_1_3`)·moderate(`NRS_4_6`) target set을 유지한다. 이후 concern resolution에서 1,104건을 resolved map으로 확정하고, 384건을 제거했으며, 난이도 정책 변경 29건은 별도 pending 재검수로 분리했다. mild는 해당 부위를 피하면서 부담을 낮추거나 유지하고, moderate는 `recovery_eligible` target만 남긴다. severe(`NRS_7_10`)는 Alternative 대신 별도 운동중단 정책을 사용한다. 관계의 도메인 승인과 별개로 새 safe-variant 운동 레코드는 `REVIEW_REQUIRED`, `production_eligible=false`로 유지한다.

### Neck

- 기존 `목 옆면 스트레칭 → 발목 돌리기`(`NRS_1_3`)는 목·어깨 overlap이 없는 distal low-load target으로 유지했다.
- 기존 `목 옆면 스트레칭 → 크런치`(`NRS_4_6`)는 core/bracing 수행 중 목 부담 감소가 확인되지 않아 제거했다.
- `목 옆면 스트레칭 → 스탠딩 카프 레이즈`(`NRS_4_6`)를 보강 candidate로 추가했다. 목·어깨 영역 비중복, beginner, bodyweight, HOME/GYM 공통 조건을 갖추며, 중립 머리·목과 불편 증가 시 중단 guard가 필요하다.
- neck 별도 review는 4건(유지 3, 제거 1)이다.

### Lower-back

기존 lower-back discomfort Alternative 12건은 target이 lower-back을 포함하지 않아 유지하되 `CONDITIONALLY_RETAINED`로 별도 검토했다. 모든 관계에 다음 guard를 붙인다.

- 중립 척추 유지
- core 또는 hip-dominant target으로 runtime 대체 금지
- volume·load 감축
- lower-back 불편 증가 시 즉시 중단

세부 결과는 [lower-back safety review](../generated/exercise-catalog-v2.0.2-final/alternatives/lower_back_alternative_safety_review_v2_0_2.jsonl)와 [lower-back policy](../normalized/lower_back_alternative_safety_policy_v2_0_2.json)에 보존했다.

### Generalized / 전신 회복·운동 중단

generalized 또는 3개 이상 부위 불편은 exercise-specific Alternative를 임의 생성하지 않고 별도 정책을 적용한다.

- 급성 신호 또는 `NRS_7_10`: 운동·Alternative·회복운동을 생성하지 않고 `STOP_EXERCISE_NO_ALTERNATIVE`
- generalized/다부위 `NRS_4_6`: 모든 보고 부위와 겹치지 않는 low-load recovery pool만 허용하고, 후보가 없으면 `REST_NO_PLAN`
- generalized/다부위 `NRS_1_3`: 전신 부담을 낮춘 recovery pool만 검토하고, 후보가 없으면 `REST_NO_PLAN`

정책 원문은 [generalized recovery/stop policy](../normalized/generalized_recovery_stop_policy_v2_0_2.json)에 별도로 정의했다. 이 정책은 진단·치료·의학적 처방이 아니다.

## 산출물

- [통증 Alternative review result JSONL](../generated/exercise-catalog-v2.0.2-final/alternatives/pain_alternative_review_result_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/pain_alternative_review_result_v2_0_2.csv): 기존 279건 전체와 source/target stable code·id, 조건, legacy identity, 판정·근거·reviewer
- [normalized discomfort alternatives JSONL](../generated/exercise-catalog-v2.0.2-final/alternatives/normalized_discomfort_alternatives_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/normalized_discomfort_alternatives_v2_0_2.csv): 유지 155건과 neck 보강 2건
- [제거·재분류 legacy Alternative 목록](../generated/exercise-catalog-v2.0.2-final/alternatives/legacy_alternative_dispositions_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/legacy_alternative_dispositions_v2_0_2.csv): 122건
- [unresolved Alternative review 목록](../generated/exercise-catalog-v2.0.2-final/alternatives/unresolved_alternatives_review_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/unresolved_alternatives_review_v2_0_2.csv): 0건
- [neck review result](../generated/exercise-catalog-v2.0.2-final/alternatives/neck_alternative_review_v2_0_2.jsonl) / [normalized neck alternatives](../generated/exercise-catalog-v2.0.2-final/alternatives/normalized_neck_discomfort_alternatives_v2_0_2.jsonl)
- [lower-back safety review](../generated/exercise-catalog-v2.0.2-final/alternatives/lower_back_alternative_safety_review_v2_0_2.jsonl)
- [Alternative integrity report](../generated/exercise-catalog-v2.0.2-final/alternatives/alternative_integrity_report_v2_0_2.json)
- [Alternative manifest](../generated/exercise-catalog-v2.0.2-final/alternatives/alternative_manifest_v2_0_2.json)
- [재현용 검토 생성기](../scripts/review_v2_0_2_discomfort_alternatives.py)
- [v2.0.2 Alternative policy](../normalized/exercise_alternative_policy_v2_0_2.json)
- [neck candidate input](../normalized/neck_discomfort_alternative_candidates_v2_0_2.json)
- [전 부위 discomfort alternative map JSONL](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_v2_0_2.csv)
- [전 부위 target sets](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_target_sets_v2_0_2.json)
- [전 부위 map integrity report](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_integrity_report_v2_0_2.json)
- [전 부위 map manifest](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_manifest_v2_0_2.json)
- [전 부위 map policy](../normalized/discomfort_alternative_target_map_policy_v2_0_2.json)
- [검수된 discomfort Alternative map JSONL](../generated/exercise-catalog-v2.0.2-final/alternatives/reviewed_discomfort_alternative_map_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/reviewed_discomfort_alternative_map_v2_0_2.csv)
- [제거된 map 후보 JSONL](../generated/exercise-catalog-v2.0.2-final/alternatives/removed_discomfort_alternative_map_v2_0_2.jsonl) / [CSV](../generated/exercise-catalog-v2.0.2-final/alternatives/removed_discomfort_alternative_map_v2_0_2.csv)
- [난이도 재검수 pending map](../generated/exercise-catalog-v2.0.2-final/alternatives/difficulty_policy_pending_map_v2_0_2.jsonl): 29건
- [resolved 통증 Alternative map](../generated/exercise-catalog-v2.0.2-final/alternatives/resolved_discomfort_alternative_map_v2_0_2.jsonl): 1,104건
- [검수된 target sets](../generated/exercise-catalog-v2.0.2-final/alternatives/reviewed_discomfort_alternative_target_sets_v2_0_2.json)
- [map 검수 integrity report](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_review_report_v2_0_2.json)
- [map 검수 manifest](../generated/exercise-catalog-v2.0.2-final/alternatives/discomfort_alternative_map_review_manifest_v2_0_2.json)
- [map 검수 policy](../normalized/discomfort_alternative_map_review_policy_v2_0_2.json)
- [map 검수 생성기](../scripts/review_v2_0_2_discomfort_alternative_map.py)

## 무결성 결과

모든 무결성 invariant가 통과했고, 아래 오류 건수는 모두 0이다.

| 검증 | 결과 |
|---|---:|
| 자기 참조 | 0 |
| 중복 natural key | 0 |
| cross-condition 동일 source→target 중복 | 0 |
| 존재하지 않는 exercise 참조 | 0 |
| 제외 exercise 참조 | 0 |
| 단순 Variant 관계 중복 | 0 |
| `SECONDARY_VARIANT` 관계 중복 | 0 |
| 통증 조건 없는 normalized Alternative | 0 |
| source → target 방향성 오류 | 0 |
| 역방향 동일 조건 관계 | 0 |
| normalized neck unsafe target | 0 |
| lower-back target 영역 overlap | 0 |

검증 natural key는 `(source stable code, alternative stable code, pain/discomfort area, condition code)`다. 관계 identity와 조건이 모두 보존되며, 현재 normalized 결과에는 cross-condition 동일 source→target 재사용도 없다.

## 검토 한계

이 산출물은 v2.0.2-final catalog의 taxonomy와 저장된 body-area/evidence metadata를 이용한 보수적 데이터 검토 결과다. 운동 수행 영상 또는 개인별 임상 안전성 판단을 대체하지 않으며, 운영 반영 전 외부 도메인 검수와 최종 승인이 필요하다.
