# v2.0.2 HOME/GYM Context Default 및 Coverage 보고서

- 생성 시각: `2026-08-28T00:00:00+09:00`
- 상태: `DRAFT_CONTEXT_DEFAULTS_REVIEW_REQUIRED`
- 운영 적격: `false`

## 결론

Context fallback 우선순위는 `대표운동 → PRIMARY_VARIANT → SECONDARY_VARIANT`로 확정했다. 단, 장소·장비 hard filter를 먼저 적용하고, HOME은 서비스 허용 장비만 통과시킨다. Variant가 default가 된 7개 HOME 항목은 관계·안전·FITT 검수 전까지 운영 default가 아니다.

HOME 허용 장비: `BODYWEIGHT`, `HOUSEHOLD_WEIGHT`, `MAT`, `DUMBBELL`, `RESISTANCE_BAND`, `FOAM_ROLLER`, `JUMP_ROPE`.

장비는 사용자 입력으로 받지 않으므로 GYM은 `location_codes=GYM`만으로 산출하고, `equipment_codes`는 운동 분류와 수행 안내에만 사용한다.

HOME 수행 가능 row는 GYM에서도 수행 가능하도록 `HOME ⊆ GYM` location 일관성을 검수한다. 검수 결과 현재 HOME-only row는 `0`건이다.

Alternative는 통증/불편에 의한 교체 관계로만 남기며, 장비·장소 fallback에는 사용하지 않는다. `SEPARATE_EXERCISE`도 family fallback에 사용하지 않는다.

## Context 결과

| Context | family | covered draft | representative default | Variant default | review | unavailable |
|---|---:|---:|---:|---:|---:|---:|
| HOME | 86 | 58 | 59 | 7 | 9 | 19 |
| GYM | 86 | 84 | 85 | 0 | 2 | 0 |

`representative/Variant default`는 선호 default 후보 유형 집계이고, `review/unavailable`은 상태 집계라 서로 겹칠 수 있다.


## 선택 우선순위

1. Context location과 HOME 허용 장비를 hard filter한다.
2. 해당 family의 context-eligible 대표운동을 1순위로 둔다.
3. 대표운동이 없을 때 PRIMARY_VARIANT, 그 다음 SECONDARY_VARIANT를 둔다.
4. 같은 단계에서는 BEGINNER, exercise_id 순으로 tie-break한다. 장비 코드는 우선순위 계산에 사용하지 않는다.

## Coverage 축

### HOME

- `goal`: 선택 가능 `GENERAL_FITNESS`; reference 대비 미확정 `없음`
- `training_type`: 선택 가능 `MOBILITY, STRENGTH`; reference 대비 미확정 `CARDIO`
- `movement_pattern`: 선택 가능 `BALANCE, CORE_BRACE, HIP_DOMINANT, HORIZONTAL_PULL, HORIZONTAL_PUSH, ISOLATION, KNEE_DOMINANT, MOBILITY_STRETCH, VERTICAL_PUSH`; reference 대비 미확정 `JUMP_PLYOMETRIC, KNEE_FLEXION`
- `primary_body_area`: 선택 가능 `ABDOMEN, ANKLE_FOOT, CHEST, ELBOW, HIP, KNEE, LOWER_BACK, NECK, SHOULDER, UPPER_BACK, WRIST_HAND`; reference 대비 미확정 `없음`
- `difficulty`: 선택 가능 `BEGINNER, INTERMEDIATE`; reference 대비 미확정 `없음`
- `phase`: 선택 가능 `COOLDOWN, MAIN, WARMUP`; reference 대비 미확정 `없음`

### GYM

- `goal`: 선택 가능 `GENERAL_FITNESS`; reference 대비 미확정 `없음`
- `training_type`: 선택 가능 `MOBILITY, STRENGTH`; reference 대비 미확정 `CARDIO`
- `movement_pattern`: 선택 가능 `BALANCE, CORE_BRACE, HIP_DOMINANT, HORIZONTAL_PULL, HORIZONTAL_PUSH, ISOLATION, KNEE_DOMINANT, KNEE_FLEXION, MOBILITY_STRETCH, VERTICAL_PULL, VERTICAL_PUSH`; reference 대비 미확정 `CYCLING, ELLIPTICAL, JUMP_PLYOMETRIC`
- `primary_body_area`: 선택 가능 `ABDOMEN, ANKLE_FOOT, CHEST, ELBOW, HIP, KNEE, LOWER_BACK, NECK, SHOULDER, UPPER_BACK, WRIST_HAND`; reference 대비 미확정 `없음`
- `difficulty`: 선택 가능 `BEGINNER, INTERMEDIATE`; reference 대비 미확정 `없음`
- `phase`: 선택 가능 `COOLDOWN, MAIN, WARMUP`; reference 대비 미확정 `없음`

## 루틴 구성 coverage

현재 service의 WARMUP/MAIN/COOLDOWN, MAIN CORE, ±300초 규칙을 draft profile로 재현했다. 서비스 지원 검사 시간 10·20·30·40·50·60분은 네 조합 모두 draft pool에서 구성 가능으로 확인되지만, 카탈로그·처방이 production gate를 통과하지 않아 운영 가능을 의미하지 않는다.

| Context | Experience | draft pool | operational | 10/20/30/40/50/60분 |
|---|---|---|---|---|
| HOME | BEGINNER | DRAFT_COMPOSABLE | BLOCKED_PRODUCTION_GATE | Y/Y/Y/Y/Y/Y |
| HOME | INTERMEDIATE | DRAFT_COMPOSABLE | BLOCKED_PRODUCTION_GATE | Y/Y/Y/Y/Y/Y |
| GYM | BEGINNER | DRAFT_COMPOSABLE | BLOCKED_PRODUCTION_GATE | Y/Y/Y/Y/Y/Y |
| GYM | INTERMEDIATE | DRAFT_COMPOSABLE | BLOCKED_PRODUCTION_GATE | Y/Y/Y/Y/Y/Y |

## 미확정·Blocker

- `CATALOG_NOT_PRODUCTION_ELIGIBLE`: 1건 — v2.0.2 통합 카탈로그 production_eligible=false라 Context Default는 운영 추천으로 사용할 수 없다.
- `VARIANT_SAFETY_FITT_REVIEW_REQUIRED`: 70건 — Variant의 관계·안전·FITT가 REVIEW_REQUIRED다.
- `INVALID_TIMING_PROFILE`: 15건 — REPS 처방인데 catalog timing_mode가 DURATION이거나 seconds_per_rep가 없어 시간 계산이 불가능한 처방이 있다.
- `INVALID_FAMILY_CODE`: 12건 — 대표운동 12건의 family_code가 REVIEW_REQUIRED placeholder다.
- `AMBIGUOUS_FAMILY_REPRESENTATIVE`: 1건 — CARDIO family처럼 하나의 family_code에 대표운동이 여러 개라 단일 default를 확정할 수 없다.
- `CONTEXT_DEFAULT_UNAVAILABLE`: 19건 — 동일 family 내부에 해당 Context에서 사용할 대표/Variant 후보가 없어 실제 루틴 선택에서 제외된다.
- `GOAL_LINK_NOT_FOUND`: 2건 — 대표운동 stable_code와 승인 goal link가 정확히 일치하지 않아 목표 필터에 연결할 수 없다.
- `PRESCRIPTION_LINK_NOT_FOUND`: 2건 — 대표운동 stable_code와 service prescription이 정확히 일치하지 않아 처방을 계산할 수 없다.
- `LOCATION_NOT_DECLARED`: 19건 — 해당 Context가 location_codes에 선언되지 않아 Context 후보에서 제외한다.
- `MANIFEST_CANONICAL_COUNT_MISMATCH`: 1건 — manifest active_canonical_exercises=None와 catalog canonical rows=131가 다르다.

Context review queue는 총 `114`건이며, 상세 row는 `context_default_review_queue_v2_0_2.jsonl/csv`에 보존했다.

## 산출물

- `context_defaults_v2_0_2.jsonl/csv`: family/context별 default와 fallback
- `context_default_candidates_v2_0_2.jsonl/csv`: 우선순위별 후보
- `family_context_coverage_v2_0_2.jsonl/csv`: family별 Context coverage
- `routine_coverage_v2_0_2.jsonl/csv`: 시간별 draft 루틴 구성 검사
- `context_default_review_queue_v2_0_2.jsonl/csv`: 미확정·review·blocker
- `context_coverage_report_v2_0_2.json`: 재현 가능한 종합 report

## 근거

- `AGENTS.md` 7절·8절: HOME/GYM 실행 가능성, 안전·검수·운영 승격 원칙
- `docs/DOMAIN_RULES.md` 4절·5절·6절: 장소·장비 우선순위, 시간 보존, 검수된 후보 사용
- `docs/DATA_MODEL.md` 5.8: Alternative는 방향성 별도 관계이며 production 승인 row만 사용
- `docs/tasks/TASK-ROUTINE-EQUIPMENT-AND-DURATION.md` 2.3·3절: Variant/Alternative 경계와 LOCATION 처리
- `data/generated/exercise-catalog-v2.0.2-final/variant_integrity_report_v2_0_2.json`: Variant integrity 및 review gate
