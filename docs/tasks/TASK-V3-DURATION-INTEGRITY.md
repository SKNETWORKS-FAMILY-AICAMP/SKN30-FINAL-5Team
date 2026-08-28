# TASK-V3-DURATION-INTEGRITY

- 이슈: #172
- 승인자: 채동현
- 상태: 구현 완료, 리뷰 대기
- 날짜: 2026-08-28

## 1. 문제

사용자 보고: "루틴이 생성은 되는데 운동 구성이 시간에 맞지 않게 너무 적게 나온다."

staging 실측(60분 요청)에서 pool 12개, `recovery_ceiling` 2세트/8회/60초로 도달 가능한 최대
작업시간이 24분이었다. 60분 요청이 구조적으로 충족 불가능한 상태였다.

## 2. 정책 변경 여부

**정책 변경 없음.** `docs/DOMAIN_RULES.md` 5절은 이미 다음을 규정하고 있었다.

- `estimated_duration_seconds`는 `requested_duration_minutes * 60`을 목표로 하고 ±300초 허용
- 허용 범위를 넘으면 계획을 반환하지 않고 실패
- 서버가 실제 동작 시간만 합산하고 휴식·전환을 누락하는 것은 금지

V3 경로가 이 계약을 구현하지 않고 있었다. 이 작업은 V3를 기존 계약에 맞추는 것이다.

## 3. 원인

### 3.1 소요시간 검증이 항등식이었다

`v3_compiler.compile_plan`이 duration을 계산하지 않고 PlanSpec의 선언값을 그대로 옮겼다.
검사는 `estimated_duration_seconds == requested_duration_minutes * 60` 하나뿐이었고,
서버가 `estimated_duration_seconds`를 `requested * 60`으로 파생하게 되면서 항상 참인 식이 됐다.

`backend/app/domain/rules/duration.py`에 검토 완료된 결정론적 duration 엔진이 있고
V1/V2 경로는 이를 사용한다. V3만 사용하지 않았다.

### 3.2 에이전트가 시간을 계산할 수단이 없었다

카탈로그 `exercises`에 승인된 타이밍 기준이 CHECK 제약과 함께 존재하지만
`ExercisePoolExerciseRecord`와 agent payload 어디에도 실리지 않았다.

### 3.3 pool 크기가 요청 시간과 무관했다

`requested_limit=min(12, len(selected))` 하드코딩. 20분 요청과 60분 요청이 같은 12개를 받았다.

### 3.4 반복 기반 운동의 작업시간이 0으로 집계됐다

응답 투영에서 `work = sets * work_seconds_per_set if work_seconds_per_set is not None else 0`.
REPS 모드 운동은 `work_seconds_per_set`이 `None`이므로 항상 0이 됐다.

### 3.5 fallback이 1세트 1회를 처방하고 전체 시간을 선언했다

`sets = min(1, ...)`, `repetitions = min(1, ...)`은 항상 1을 반환한다.
운동 3개 상한과 합쳐져 약 1분짜리 계획이 30분으로 기록됐다.

## 4. 변경

| 영역 | 변경 |
|---|---|
| `domain/rules/duration.py` | `DURATION_TOLERANCE_SECONDS`를 도메인 규칙으로 이동. V1/V2/V3 공유 |
| `domain/agents/v3_duration.py` | 신규. 처방을 카탈로그 기준으로 시간 산출, pool 크기 도출 |
| `domain/agents/retrieval.py` | pool 레코드에 타이밍 4개 필드. schema v3 → v4 |
| `domain/agents/v3_compiler.py` | duration을 계산값으로 대체. 정확일치 → ±300초 창 |
| `domain/agents/v3_validation.py` | 실측 duration과 요청을 비교 |
| `modules/decisions/v3_shadow.py` | 동일 창 적용 |
| `modules/decisions/v3_application.py` | pool 크기 도출, 응답 투영 0초 버그 수정 |
| `integrations/langgraph/fallback.py` | 요청 시간을 실제로 채우고, 못 채우면 거절 |
| `integrations/llm_agents/payload.py` | 타이밍 기준을 에이전트에게 전달 |
| `db/repositories/vector_index.py` | 카탈로그 타이밍을 레코드로 전달 |

## 5. 계산식

```
work      = sets x (repetitions x default_seconds_per_rep)   # REPS
          = sets x work_seconds_per_set                       # DURATION
rest      = max(sets - 1, 0) x rest_seconds_between_sets
transition= default_transition_seconds                        # 카탈로그 값
```

세트·반복·휴식은 계획의 선택이므로 처방에서, 초당 환산과 전환 시간은 검수 대상이므로
카탈로그에서 가져온다. V1/V2가 쓰는 식과 동일하다.

## 6. 테스트

- `backend/tests/unit/test_v3_duration.py` 신규 15건
- `backend/tests/unit/test_v3_deterministic_graph_fallback.py` 2건 추가
- 단위 전체 1021건 통과 (기존 1004 + 신규 17)
- ruff format/check, mypy 통과
- 통합 테스트는 `TEST_DATABASE_URL` 미설정으로 skip

회귀 감지 확인: 컴파일러 계산과 검증기 허용창을 각각 되돌린 상태에서 신규 테스트가 실패하는 것을
확인했다.

## 7. 알려진 한계

1. **setup/warmup/cooldown 미구현.** `DOMAIN_RULES` 5절 산식은 준비·마무리를 포함하지만
   V3는 `v3_application.py`가 모든 항목을 `MAIN`으로 고정하므로 이 세 구간이 0이다.
   초보자 대상 서비스에서 준비운동 부재는 별도 검토가 필요하다. 후속 이슈로 분리한다.
2. **fallback이 반복 기반 운동에서 ceiling에 의존한다.** `maximum_repetitions_per_set`이
   없으면 임의 값을 만들지 않고 해당 운동을 건너뛴다. 승인된 처방 프로필
   (`exercise_prescription_profiles`)을 pool로 전달하면 해소되나 이 작업 범위 밖이다.
3. **저장된 v3 snapshot은 replay 불가.** 레코드 형태가 바뀌었고 schema를 v4로 올렸다.
   V3는 DEMO 프로파일이며 production 승인 전이므로 운영 영향은 없다.
4. **`recovery_ceiling` 산출 자체는 변경하지 않았다.** 승인된 기본 루틴의 운동별 최댓값을
   그대로 쓴다. pool이 커지면서 요청 시간 도달은 가능해졌으나, 기본 루틴이 짧은 사용자는
   여전히 낮은 상한을 받는다.

## 8. 수동 확인 절차

1. staging에서 60분 요청으로 루틴 생성
2. 응답 `plan.items`의 `estimated_item_seconds` 합이 3600 ±300 안인지 확인
3. 반복 기반 운동의 `work_seconds`가 0이 아닌지 확인
4. 20분 요청으로 반복해 pool 크기와 운동 수가 줄어드는지 확인
