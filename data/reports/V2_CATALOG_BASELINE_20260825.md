# V2 카탈로그 baseline (2026-08-25)

이 문서는 V2 생성기 변경 전의 읽기 전용 baseline이다. V1은 병합 원천이 아니라 회귀 비교
근거로만 사용한다. 현재 worktree의 사용자 변경·untracked 산출물은 정리하지 않았다.

## 산출물 요약

| 산출물 | records | bytes | SHA-256 | baseline 판정 |
|---|---:|---:|---|---|
| `generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv` | 102 | 121,579 | `1383d0407107fb270ef0b0f8f3090a4f159ec4c6ada78706baaecd4ae7291fbc` | stable code 102 unique |
| `generated/exercise-catalog-v2.0.0-final/representative_exercise_taxonomy_v2_final.csv` | 102 | 152,210 | `64fc1723eba63bf1f7be899b9dd4e8532ddc871070918bdc8c362c6593782155` | representative coverage complete |
| `generated/exercise-catalog-v2.0.0-final/exercise_alternatives_v2_final.csv` | 116 | 48,493 | `2a2d58220b1e98aa173861de631c3e2d4e4ccaa1c822b06895985d85e11eeba3` | production-ineligible |
| `generated/exercise-catalog-v2.0.0-final/representative_exercise_safety_mapping_v2_final.csv` | 406 | 99,911 | `067603185a1169485d7baed5596ff0a1e98156ecd3cb7c5249f3344cf08d9bde` | inactive/pending approval |
| `generated/exercise-catalog-v2.0.0-final/safety_rules_v2_final.jsonl` | 384 | 323,512 | `b9c4d1e2ef6730105c32a9066751e5b1a8d7de7097712f6ed9986b6711cc5f9d` | reference/bridge only |
| `generated/exercise-catalog-v2.0.0-final/stable_code_registry_v2.json` | 102 records | 13,424 | `e50ae1258664aa96fd94ab62f151660236d06dc8a50fa60725ef62e0893e6308` | materialization-pending |

## V2 release profile 위반

| 검사 | 결과 |
|---|---:|
| `OUTDOOR` location | 0 |
| `BENCH` equipment | 5 |
| `CHAIR` equipment | 3 |
| `source_track=merged`인 운동 행 | 0 |
| `source_track` 허용값(`wger/kspo/gymvisual`) 밖의 운동 행 | 0 |
| `REX-000049` equipment | `MACHINE` |
| `REX-000094` equipment | `STRETCH_STRAP` |

`BENCH`와 `CHAIR`는 V2 equipment code에서 제거하고, 필요한 지지물 조건만 수행 안내·설치
조건으로 보존해야 한다. `OUTDOOR`는 현재 V2 release에서 계속 0이어야 한다.

## V1 회귀 비교

| 비교 대상 | V1 | V2 | 해석 |
|---|---:|---:|---|
| 카탈로그 원천 NEX | 208 | 208 | V2 representative 102개가 `nex_exercise_ids`로 208개 모두 보존 |
| 대표운동 | - | 102 | V2 family 대표화 결과 |
| 대체관계 | 189 | 116 | REX 양끝점 변환·중복 제거·V2 관계 필터 후 73건 감소 |
| 대체관계 source NEX unique | 102 | 52 REX | V2 관계가 실제로 연결되는 대표운동 수 |

V1 대체관계의 189개 NEX edge 중 V2 최종 CSV에 동일 NEX 양끝점으로 남아 있는 edge는 116개다.
나머지 73개는 V2에서 직접 복사하지 않고 관계 유형·난이도·목표 보존·장비/장소 조건을
재검증해야 하는 대상으로 기록한다. V1의 값은 최신 원천값을 대체하지 않는다.

## 안전·운영 게이트

- 모든 현재 V2 대표운동·대체·안전 산출물은 운영 승격 전제 없이 `production_eligible=false`로 유지한다.
- manifest version/hash/count가 승인 registry와 일치하기 전에는 DB 적재·서비스 노출을 금지한다.
- 어깨·허리(`LOWER_BACK`)·팔꿈치의 `DISCOMFORT` 매핑은 baseline에 승인된 행이 없으므로 자동 생성하지 않는다.

## 5번까지의 checkpoint

생성기·정책 입력을 수정한 뒤 관련 generated 산출물을 재생성했다.

| 검사 | checkpoint |
|---|---:|
| 대표운동 | 102 |
| stable code unique | 102 / 102 |
| V2 `BENCH` equipment | 0 |
| V2 `CHAIR` equipment | 0 |
| V2 `OUTDOOR` location | 0 |
| 대체관계 | 64 |
| 안전규칙 | 126 (`MOVEMENT_PATTERN` legacy 24 + V2 bridge 102) |
| 모든 generated V2 relation/rule `production_eligible` | `false` 정책 유지 |

대체관계 64건은 V2 REX endpoint와 실제 장비·장소·난이도를 재검증한 관계다. legacy `SAFETY`
관계와 승인 매핑표가 없는 어깨·허리·팔꿈치 `DISCOMFORT` 관계는 생성하지 않았다.

## 근거

- [V2 스키마 정합성 검토](V2_SCHEMA_ALIGNMENT_REVIEW.md)
- [대표운동 V2 산출물](../generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv)
- [대체관계 V2 산출물](../generated/exercise-catalog-v2.0.0-final/exercise_alternatives_v2_final.csv)
- [V1 대체관계 회귀 원천](../generated/exercise-alternatives-v0.3.0/alternative_relationships.csv)

## 2026-08-25 명시적 장비 대체 관계 재생성 보충

사용자 승인 정책에 따라 `REX-000094 (STRETCH_STRAP)`에서 `REX-000034 (BODYWEIGHT)`로
동일 목표의 맨몸 햄스트링 스트레칭 관계를 추가했다. 관계 사유는 `EQUIPMENT`, 난이도 변화는
`0`이며, 운영 승격 전까지 `production_eligible=false`를 유지한다.

- 현재 대체관계 수: `65`
- 현재 대체관계 산출물 SHA-256: `d324943c62277a2e37b2249df43e351a28a78dee29c70fa84894405d681e27f8`
- 생성 원본: `data/normalized/v2_representative_decisions.json`
- [V2 대표운동 결정 정책](../normalized/v2_representative_decisions.json)

## 2026-08-25 도메인 승인 타겟 근육·불편 대체 최종 보충

102개 대표운동의 `body_focus_code`를 `DOMAIN_APPROVED`로 확정했다. 저강도 후보는
`difficulty_code=BEGINNER`와 `fitt_intensity_level=LIGHT`를 동시에 만족해야 한다.

- MILD: 통증 부위가 대체운동의 primary에 있으면 제외하고, secondary-only 또는 미사용 부위만 허용
- MODERATE: 통증 부위가 primary·secondary 어느 쪽에도 없는 후보만 허용
- 런타임 조치: `INTENSITY_REDUCED`; REST는 MILD/MODERATE 매핑에 사용하지 않음
- 불편 대체 매핑 입력: `160`행
- 최종 대체관계 수: `225`
- 최종 대체관계 산출물 SHA-256: `a6bfe775e8ea1a82a74116a83ef77c305b1086f4d22c5fb12cc957c08518a641`
- 대표운동 타겟 근육 승인 수: `102/102`

## 2026-08-25 NRS 서비스 안전액션 정책 v2 보충

기존 MILD/MODERATE 스트레칭 중심 매핑을 폐기하고 `pain-intensity-action-v2` 정책으로
재생성했다. NRS 1–3은 같은 목표의 부하·ROM 다운시프트와 쉬운 변형을 우선하고, NRS 4–6은
통증 부위를 primary·secondary 모두 제외한 `ACTIVE_RECOVERY` 후보를 사용한다. NRS 7–10은
대체운동 없이 `STOP_EXERCISE`이며, red flag는 점수와 무관하게 `STOP_AND_SEEK_HELP`다.

- 불편 대체 매핑: `520`행 (`NRS_1_3=259`, `NRS_4_6=261`)
- NRS 7–10 대체 매핑: `0`행
- 최종 대체관계 수: `585`
- 최종 대체관계 SHA-256: `7706a4c5f08d66495bbcdc696391e35afb715dd3a5671f57cfbabd21fec0f05c`
- 최종 안전규칙 SHA-256: `368a0d238b91fc6b317d2cc91d68ea8ce0cf7c899532ac1667b7229915100ce0`
- 정책 입력: [v2_pain_action_policy.json](../normalized/v2_pain_action_policy.json)
