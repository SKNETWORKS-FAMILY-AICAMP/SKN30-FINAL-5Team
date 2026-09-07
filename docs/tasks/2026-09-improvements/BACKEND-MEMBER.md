# 백엔드 팀원 트랙 (BM-1 ~ BM-6)

- 기준 코드: `origin/develop` = `5a6fd26`
- 소유 모듈: `app/modules/catalog/**`, `app/modules/checkins/**`, `app/modules/workouts/**`,
  `app/modules/routines/**`, `app/domain/rules/duration.py`, `app/domain/rules/plan_shape.py`
- 공통 규칙과 병렬화 계획은 `README.md` 참조

이 트랙은 추가 필드, 읽기 경로, 결정적 규칙 중심이다. 팀장 트랙과 파일이 겹치지 않는다.
이 트랙에는 마이그레이션이 필요한 작업이 없다(BM-6 포함 — 칼로리 컬럼은 이미 존재한다).

---

## BM-1. 운동 시간 상한 90분 + MAIN 구간 반복 배치

- 선행: 없음 / 게이트: **G4 확정**
- 짝 작업: FE-6
- **이 트랙에서 가장 무거운 작업이다.** 먼저 착수하기를 권장한다.
- 위험: 높음. 이미 배포된 계획 구성 규칙(`plan_shape.py`)과 결정적 fallback을 바꾼다.

### 확정된 결정

> 운동 시간 최대 60분 제한 → **90분으로 상한을 올리고 1회 권장 시간을 권고한다.** (G4 이전)
>
> 운동 종류는 10개지만, **스트레칭을 제외하고 MAIN 본운동에서는 순서가 다르게 중복을 허용해서
> 시간을 채우도록.** 예: 푸시업 → 스쿼트 → 데드리프트 → 푸시업. (G4)

### 현재 상태 1: 상한이 두 곳에 이중으로 걸려 있다

- `backend/app/modules/checkins/schemas.py:96`
  `available_time_minutes: int | None = Field(default=None, ge=10, le=60)`
- 같은 파일 145행 (레거시 경로)
  `if not 10 <= self.requested_duration_minutes <= 60:`

프로필 기본값은 이미 더 넓다(`gt=0, le=240`). 당일 체크인만 60분에 막혀 있다.

### 현재 상태 2: 반복은 이미 규칙상 허용된다 — 막는 것은 생성기다

무결성 검증은 운동 **종류** 수를 센다.

```python
# app/domain/agents/v3_validation.py:263
if len(set(ids)) > MAX_PLAN_EXERCISE_TYPES:
    codes.add(IntegrityViolationCode.PLAN_EXERCISE_VARIETY_EXCEEDED)
```

`plan_shape.py`의 주석도 같은 의도를 적어 두었다 — "splitting one movement across two blocks is a
way to shape a session, not a licence to hand the user twelve different movements."
즉 푸시업 → 스쿼트 → 데드리프트 → 푸시업은 **검증을 이미 통과한다.**

반복을 만들지 않는 쪽은 결정적 fallback이다.

```python
# app/integrations/langgraph/fallback.py
placed: dict[UUID, PhaseCode]      # 운동당 자리 하나
for exercise_id in ordered_ids:
    if exercise_id in placed or len(placed) >= MAX_PLAN_EXERCISE_TYPES:
        continue
```

`placed`가 운동 ID를 키로 쓰는 dict라서 한 운동이 두 번 배치될 수 없다. LLM 훈련 에이전트 쪽도
프롬프트가 "10종목 상한"만 말하고 반복 허용을 말하지 않는다.

### 목표

1. 당일 요청 시간 상한을 90분으로 올린다.
2. MAIN 구간에서 같은 운동을 여러 블록에 배치해 남은 시간을 채운다.
3. 권장 시간을 계약에 노출한다.

### 설계

**(a) 반복 규칙을 `plan_shape.py`에 명시한다**

지금은 "종류를 센다"는 사실이 검증 코드와 주석에만 있다. 반복이 정식 수단이 됐으므로 규칙으로
올린다. 최소한 다음을 상수·함수로 표현한다.

| 규칙 | 값 |
|---|---|
| 서로 다른 운동 종류 상한 | 10 (변경 없음) |
| WARMUP·COOLDOWN 종류 상한 | 각 2 (변경 없음) |
| WARMUP·COOLDOWN 반복 | **금지.** 스트레칭은 한 번씩만 |
| MAIN 반복 | **허용** |
| 같은 운동의 연속 배치 | **금지.** "순서가 다르게"를 이 규칙으로 표현한다 |
| 한 운동의 MAIN 최대 반복 횟수 | 상한을 정한다. 무한 반복 방지 |

`PLAN_SHAPE_RULE_VERSION`을 올린다.

**(b) fallback의 자료구조를 바꾼다**

`placed: dict[UUID, PhaseCode]`를 **블록 시퀀스**로 바꾼다
(예: `tuple[tuple[UUID, PhaseCode], ...]`). 종류 상한은 `len({id for id, _ in blocks})`로 계산하고,
블록 수는 별도로 늘어난다. `_ordered_prescriptions`가 이미 phase 순으로 번호를 다시 매기므로,
MAIN 안에서의 반복 순서만 추가로 정하면 된다.

시간을 채우는 순서를 제안한다.

1. mandatory 배치
2. WARMUP·COOLDOWN 각 1개 이상 확보 (반복 없음)
3. MAIN을 서로 다른 운동으로 채운다 (종류 상한까지)
4. 남은 시간이 `DURATION_TOLERANCE_SECONDS`를 넘으면, MAIN 운동을 **연속되지 않게** 라운드 형태로
   다시 배치해 채운다
5. 그래도 창 밖이면 실패한다 (조용히 줄이지 않는다)

**(c) 무결성 검증에 연속 반복 금지를 추가한다**

`PLAN_PHASE_COVERAGE_INVALID`와 같은 층에 규칙을 추가한다. 새 위반 코드가 필요하면
`_CONDITIONALLY_REPAIRABLE`에 넣어 coordinator 수리 → fallback 경로가 살아 있게 한다.
**fail-closed로 만들지 않는다.**

**(d) 프롬프트를 갱신한다**

`app/integrations/llm_agents/prompts.py`의 훈련 에이전트 지시에 "MAIN에서 같은 운동을 연속되지 않게
반복해 시간을 채워도 된다"를 넣고 프롬프트 버전을 올린다(`v3-training-prompt-v6` → `v7`).

### 반드시 유지할 것

- AGENTS.md 7절 duration 불변식: 요청 시간을 보존하고, ±5분 창을 벗어나면 조용히 줄이지 말고
  실패시킨다.
- 안전 제외 운동은 반복 대상이 될 수 없다.
- 회복 상한(`RECOVERY_CEILING_EXCEEDED`)은 반복으로 초과되면 안 된다. **반복이 부하를 늘린다는
  점을 회복 규칙이 알고 있는지 확인한다.** 이 작업에서 가장 놓치기 쉬운 지점이다.

### 인수 조건

1. 90분 요청이 수용되고 계획이 ±5분 안에 생성된다.
2. 91분 이상, 9분 이하 요청은 거부된다.
3. 레거시 `requested_duration_minutes` 경로도 같은 상한을 따른다.
4. 60분을 넘는 요청이 조용히 60분으로 줄어들지 않는다.
5. 90분 계획에서 서로 다른 운동 종류가 10개를 넘지 않는다.
6. 같은 운동이 연속된 두 블록에 배치되지 않는다.
7. WARMUP·COOLDOWN에는 반복이 없다.
8. 반복이 회복 상한을 넘기지 않는다.
9. 30분 이하 요청의 계획이 이전과 동일하다 (반복이 불필요하게 끼어들지 않는다).
10. 권장 시간이 서버 응답으로 제공되고 결정적이며 버전이 붙어 있다.
11. LLM 실패 시 fallback이 90분 계획을 만들 수 있다.

### 변경 예상 파일

`app/domain/rules/plan_shape.py`, `app/domain/rules/duration.py`,
`app/modules/checkins/schemas.py`, `app/modules/checkins/service.py`,
`app/integrations/langgraph/fallback.py`, `app/domain/agents/v3_validation.py`,
`app/integrations/llm_agents/prompts.py`,
`docs/API_CONTRACT.md`, `docs/DOMAIN_RULES.md`

### 테스트

- 경계값: 10, 30, 60, 61, 90, 91분
- **90분 골든 시나리오**: 계획이 실제로 만들어지고 종류 10개 이하, 연속 반복 없음
- 30분 계획 회귀: 반복이 생기지 않는다
- 연속 반복 위반이 검증에 걸리고 수리 경로로 라우팅된다
- 회복 상한 상호작용
- fallback 단독으로 90분 계획 생성
- 기존 `test_v3_deterministic_graph_fallback.py`, `test_v3_integrity_validator.py`,
  `test_v3_duration.py` 회귀

### 제외 범위

프로필 기본 운동 시간 상한 변경(이미 240분). 세트·반복수 처방 규칙 재설계.
WARMUP·COOLDOWN 시간 상한 변경.

---

## BM-2. 운동 상세 계약: 주요 부위 · 단계별 자세 설명 · 주의사항

- 선행: 없음 / 게이트: **G5 확정** (2026-09-07, 아래 참조)
- 짝 작업: FE-1

### 보고된 문제

> 운동 자세 설명 보기 할 경우 "검수된 생활도구 안내를 사용할 수 없습니다"라는 문구로 자세 설명과
> 자세 이미지가 안 보임.

이 503 자체는 이미 고쳐져 배포됐다(PR #262, #264, #265). 남은 것은 **표시 계약**이다.

> 주요부위 / 자세 설명(번호별 줄바꿈 가독성 개선) / 주의사항 순서로 나타내도록

### 현재 데이터의 실제 모습 (v2.0.6, 237건 전수 확인)

`instruction_summary_ko`는 번호가 붙은 여러 단계가 **줄바꿈 없이 한 문자열**로 들어 있다.

```
"1. 발을 어깨 넓이로 벌리고 팔을 양쪽에 내려 펼칩니다 2. 등을 곧게 펴고 복근을 긴장시킨
상태에서 천천히 몸통을 한쪽으로 구부려 손을 무릎 쪽으로 내립니다 3. 맨 아래에서 잠깐
멈췄다가 천천히 시작 자세로 돌아옵니다"
```

- 237건 전부가 `N. ` 형태의 번호 마커를 가진다. 단계 수는 2단계 57건, 3단계 153건, 4단계 27건.
  마커가 없는 레코드는 0건이다.
- `form_cues_ko`는 237건 전부 정확히 2개이며, 내용이 실제로 **주의사항**이다.
  예: `["목과 허리를 과하게 꺾지 말고 편안한 자세를 유지합니다", "반동을 쓰지 말고 천천히 움직입니다"]`
- `form_cues_review_status`는 `DOMAIN_APPROVED`다.

### G5가 신규 검수 없이 해소된 이유

주의사항 콘텐츠를 새로 검수해야 하는 줄 알았으나, `form_cues_ko`가 이미 승인된 주의사항이다.
따라서 **신규 데이터 검수 없이** 주의사항을 노출할 수 있다. 2026-09-07에 이 표기를 확정했다.

운동 테이블에는 별도의 주의사항 컬럼이 없다(`app/db/models/catalog.py:247`). 컬럼을 새로 만들지 않는다.

### 목표

프론트가 한국어 콘텐츠 문자열을 파싱하지 않도록, 백엔드가 단계를 나눠서 준다.

### 설계

`ExerciseDetailResponse`(`app/modules/catalog/schemas.py:286`)에 optional 필드를 추가한다.
기존 필드는 그대로 두어 하위 호환을 유지한다.

| 필드 | 내용 |
|---|---|
| `instruction_steps: list[str] \| None` | `instruction_summary`를 번호 마커로 분리한 단계 목록. 번호 접두사는 제거하고 순서로만 표현한다 |
| `cautions: list[str] \| None` | `form_cues` + 생활도구 가이드의 `cautions_ko`(있는 경우) |

분리는 결정적이어야 하고, 마커가 없거나 하나뿐이면 **전체 문자열을 단일 단계로** 반환한다.
파싱 실패가 상세 조회를 실패시키면 안 된다.

`household_equipment_guides`는 이미 응답에 있으나 프론트가 렌더링하지 않는다(FE-1에서 처리).

### 인수 조건

1. 활성 카탈로그의 237건 전부에서 `instruction_steps`가 비어 있지 않다.
2. 단계 수가 원본의 번호 개수와 일치한다(2, 3, 4단계 분포가 위와 같아야 한다).
3. 단계 문자열에 `"1. "` 같은 번호 접두사가 남아 있지 않다.
4. `instruction_summary`가 기존과 동일한 값으로 계속 반환된다.
5. 번호 마커가 없는 가상의 레코드에서도 200이 반환되고 단일 단계가 나온다.
6. 생활도구 가이드가 있는 34건에서 `cautions`에 가이드의 `cautions_ko`가 포함된다.
7. 같은 입력에 항상 같은 결과가 나온다.

### 변경 예상 파일

`app/modules/catalog/schemas.py`, `app/modules/catalog/service.py`,
`app/db/repositories/catalog.py`, `docs/API_CONTRACT.md`

### 테스트

- 2·3·4단계 레코드 각각의 분리 결과
- 마커 없는 입력의 폴백
- 생활도구 가이드 유·무 두 경우의 `cautions` 구성
- 기존 `test_catalog_media.py`, 상세 조회 API 테스트

### 제외 범위

카탈로그 데이터 재생성. 새 주의사항 콘텐츠 작성. 화면 구성(FE-1).

---

## BM-3. 장비 대체 변형 운동을 집 운동으로 한정

- 선행: 없음 / 게이트: 없음
- 짝 작업: FE-2

### 개선 항목

> 장비가 없을 때 변형운동은 집에서 하는 운동에서만

### 현재 상태

`GET /exercises/{exercise_id}/variants`(`app/api/v1/exercises.py:126`)는 장소를 전혀 고려하지 않는다.
헬스장 세션에서도 생활도구 대체 변형이 그대로 제안된다. 헬스장에는 원래 장비가 있으므로 대체가
의미 없고, 사용자에게 혼란을 준다.

### 목표

장비 대체 변형은 집 운동 맥락에서만 제공한다.

### 설계 선택지

권장: 엔드포인트가 장소 맥락을 받고, `HOME`이 아니면 빈 목록을 반환한다. 404나 에러가 아니라
**빈 목록**이어야 한다. 변형이 없는 것과 조회 실패는 다른 상태다.

장소 맥락을 어디서 얻을지 두 가지가 있다.

1. 쿼리 파라미터로 받는다. 단순하지만 클라이언트가 속일 수 있다.
2. 당일 체크인의 `location_code`를 서버가 조회한다. 신뢰할 수 있으나 결합이 늘어난다.

체크인이 이미 존재하는 시점에만 변형이 필요하므로 2번을 권장한다. 1번을 선택하면 그 이유를
task 문서에 남긴다.

### 인수 조건

1. 당일 장소가 `HOME`일 때 기존과 동일한 변형 목록이 반환된다.
2. 당일 장소가 `GYM` 또는 `OUTDOOR`일 때 빈 목록이 반환되고 200이다.
3. 체크인이 없을 때의 동작이 정의돼 있고 문서화돼 있다.
4. 구버전 클라이언트가 깨지지 않는다.

### 변경 예상 파일

`app/api/v1/exercises.py`, `app/modules/catalog/service.py`,
`app/modules/catalog/schemas.py`, `docs/API_CONTRACT.md`

### 제외 범위

변형 운동 데이터 자체. 대체 규칙 변경. 화면 노출 제어(FE-2).

---

## BM-4. 체크인에서 운동 장소 선택

- 선행: 없음 / 게이트: **G7 확정**
- 짝 작업: FE-4 (체크인 UI), BL-7 (프로필 legacy 필드)

### 확정된 결정 (G7)

> 온보딩에서 집·헬스장 선택 자체를 제거, 운동 장소는 **체크인 화면에서 헬스장/집을 선택할 수 있게
> 표시돼야 함.** 온보딩 완료 오류 고려해서 수정.

이 결정은 이미 승인된 ADR-0017과 같다.

> 운동 장소와 1회 운동시간은 Daily Check-in의 `location_code`와 `available_time_minutes`로만 받는다.
> 프로필에 기본값을 두지 않는다.

### 좋은 소식: 백엔드는 이미 이 모델이다

- 온보딩 요청에서 장소는 이미 필수가 아니다(`preferred_location_code`에 기본값 `HOME`).
  스키마 주석이 "Location and duration are selected by Daily Check-in after onboarding"이라고
  명시한다.
- 체크인 `DailyContextUpsertRequest.location_code`는 유효한 `LocationCode`면 무엇이든 받는다.
  프로필과 대조하지 않는다. **이것이 G7이 원하는 동작이다.**
- 기본 루틴 생성은 ADR-0017에 따라 장소를 후보 게이트로 쓰지 않는다.

따라서 이 작업의 대부분은 **프론트(FE-4)**이고, 백엔드 몫은 계약을 확정하고 문서를 맞추는 일이다.

### 백엔드에서 확인·정리할 것

1. **선택 가능한 장소 목록의 출처를 정한다.** 지금 프론트는 프로필에서 목록을 만든다. 프로필이
   더 이상 권위가 아니므로, 체크인 기본값 응답이 선택 가능한 `location_code` 목록을 내려주는 것이
   낫다. 프론트가 코드 목록을 하드코딩하지 않게 한다.
2. **`OUTDOOR`는 노출하지 않는다** (2026-09-07 확정). `LocationCode`의 세 값 중 사용자가 고를 수
   있는 것은 `HOME`과 `GYM` 둘뿐이다. `OUTDOOR` 값 자체는 삭제하지 않는다 — 기존 행과 승인된
   운동 풀의 `location_codes`가 이 값을 쓰고 있고, 값 도메인을 좁히면 그것들이 깨진다.
   **선택지에서만 뺀다.**
3. 프로필 장소 값에 의존하는 백엔드 경로가 남아 있는지 확인한다. 있으면 제거하거나 BL-7로 넘긴다.

### 인수 조건

1. 체크인이 프로필 장소 값과 무관하게 `HOME`과 `GYM`을 모두 받는다.
2. 프로필에 장소가 저장돼 있지 않아도 체크인이 성공한다.
3. 선택 가능한 장소 목록이 서버 응답에서 오고, 프론트가 하드코딩하지 않는다.
4. 선택 가능한 장소 목록에 `OUTDOOR`가 들어 있지 않다.
5. `location_code = 'OUTDOOR'`인 기존 체크인 행을 읽어도 실패하지 않는다.
6. 장소에 따른 운동 풀 필터링은 기존대로 동작한다 (당일 안전 승인 풀이 적용).

### 변경 예상 파일

`app/modules/checkins/schemas.py`, `app/modules/checkins/service.py`,
`app/modules/checkins/ports.py`, `docs/API_CONTRACT.md`

### 제외 범위

프로필 legacy 필드 제거(BL-7). 체크인 화면(FE-4). 장소별 운동 풀 로직.

---

## BM-5. 루틴 이름 결정 규칙

- 선행: 없음 / 게이트: 없음
- 짝 작업: FE-10

### 개선 항목

> 루틴 생성 시 루틴 명이 대부분 "가동성 스트레칭 구성"이나 "유산소" 정도로 제한적으로 걸려있는데,
> 루틴에 맞게 이름이 유동적으로 변경되도록.

### 원인

백엔드에는 루틴 이름 개념이 없다. 프론트가 **계획 수준 코드 두 개만으로** 만든다.

```ts
// frontend/src/features/home/homeModel.ts:687
export function routineTitleFromPlan(plan: WorkoutPlan): string {
  const focus = plan.body_focus_code === null ? '' : bodyFocusLabel(plan.body_focus_code);
  return `${focus ? `${focus} ` : ''}${trainingTypeLabel(plan.training_type_code)} 루틴`;
}
```

`body_focus_code`와 `training_type_code`는 값 종류가 적으므로 이름도 몇 개로 수렴한다.
`MOBILITY`가 두 코드 모두에 존재해서 "가동성 가동성 루틴" 같은 결과도 나온다
(`app/modules/catalog/codes.py:231`과 `:249`가 둘 다 `가동성`으로 매핑된다).

### 목표

계획의 실제 구성에서 이름을 만든다. 이름은 백엔드가 결정적으로 정하고 버전을 붙인다.

### 왜 백엔드인가

이름은 홈 화면, 운동 기록, 주간 리포트, 알림에서 같아야 한다. 프론트마다 다시 계산하면
어긋난다. 다만 이름은 안전 판정이 아니므로 AGENTS.md 6절의 "프론트가 백엔드 결정 로직을 복제하지
말 것"과는 별개의 이유로 백엔드에 둔다.

### 설계

`app/domain/rules/plan_naming.py`를 새로 만든다. `plan_shape.py`가 좋은 선례다
(규칙 버전 상수, 순수 함수, 상수의 근거를 주석으로 남김).

입력은 컴파일된 계획이다. 이름의 근거로 쓸 만한 값:

- MAIN 구간 운동들의 `primary_body_area_codes` 분포 (어느 부위가 주가 되는지)
- `primary_movement_pattern_code` 분포
- `training_type_code` 구성 비율 (근력 위주인지, 유산소가 섞였는지)
- 하향 조정 여부 (회복 중심 세션인지)

규칙은 결정적이고 재현 가능해야 한다. 같은 계획은 항상 같은 이름을 낳는다. LLM을 쓰지 않는다.

한국어 라벨은 DB 키가 아니다(AGENTS.md 9절). 응답에는 이름 문자열과 함께, 이름을 만든 근거
코드를 같이 실어 프론트가 필요하면 다르게 표현할 수 있게 한다.

### 인수 조건

1. 같은 계획에 항상 같은 이름이 나온다.
2. 부위 구성이 다른 두 계획이 서로 다른 이름을 받는다.
3. "가동성 가동성 루틴" 같은 라벨 중복이 발생하지 않는다.
4. 계획 데이터가 부족해도 이름 생성이 실패하지 않고 정의된 기본 이름이 나온다.
5. 이름 규칙에 버전 상수가 있고 응답에서 확인할 수 있다.
6. 이름에 진단·의료 표현이 들어가지 않는다.

### 변경 예상 파일

`app/domain/rules/plan_naming.py` (신규), `app/modules/decisions/schemas.py`,
`app/modules/decisions/v3_application.py`, `app/modules/routines/schemas.py`,
`docs/API_CONTRACT.md`, `docs/DOMAIN_RULES.md`

### 테스트

- 부위·패턴 조합별 골든 이름 테스트
- 동일 입력 재현성
- 데이터 부족 시 폴백
- 라벨 중복 회귀 테스트 (`MOBILITY` 이중 매핑 사례)

### 제외 범위

사용자가 이름을 직접 바꾸는 기능. 이름 다국어. 프론트 표시(FE-10).

---

## BM-6. 세션 종료 시 소모 칼로리

- 선행: 없음 / 게이트: **G3 확정**
- 데이터 소비처: BL-4 (주간 총 소모 칼로리)

### 확정된 결정

> 칼로리 계산 → 운동 종료 시 총 소모한 칼로리 넣는걸로
>
> **체중과 수행한 운동 기준으로 반영되도록 승인.** (G3)

즉 산식의 근거는 **MET × 체중 × 실제 수행 시간**이다. 이는 ADR-0004가 정한
"운동 종류·시간·강도와 사용자 체중 기반 추정치" 경계 안에 있다.

### 착수 전 반드시 읽을 것

`docs/adr/0004-safety-calorie-privacy-retention.md`. 이 ADR이 이미 정한 제약은 그대로 유지한다.

- 예상 소모 칼로리는 **추정치로만** 제공한다.
- 칼로리 추정치를 진단이나 안전 판정의 단독 근거로 쓰지 않는다.
- 웨어러블 칼로리를 실제값으로 취급하지 않는다.

G3이 산식의 **근거**를 승인했으므로, 남은 것은 구현 세부다. 아래를 task 문서에 확정해 적고
`calorie_policy_version` 문자열로 고정한다.

- 단위: kcal
- 반올림 규칙과 자릿수
- MET 출처 버전 식별자 (`exercise-met-mapping-v0.1.0`)
- 정책 버전 문자열

ADR-0004의 "미확정" 절을 이 결정으로 갱신하거나, 후속 결정으로 추가 기록한다.

### 현재 상태 — 저장 구조는 이미 다 있다

`workout_sessions`에 다음 컬럼이 이미 있다(`app/db/models/workout.py:154-159`).

| 컬럼 | 용도 |
|---|---|
| `estimated_calories_burned` | 값. `>= 0` CHECK 제약 있음 |
| `calorie_source_code` | 출처. 웨어러블 측정과 MET 추정을 구분하기 위해 존재 |
| `calorie_policy_version` | 정책 버전 |
| `calorie_input_snapshot` | 입력 스냅샷 (재현성) |

즉 **마이그레이션이 필요 없다.** 값을 계산해 채우는 코드만 없다.
현재 `v3_application.py`가 `estimated_calories_burned=None`을 그대로 넣는다.

### 데이터도 이미 있다

`data/generated/exercise-met-mapping-v0.1.0/exercise_met_mapping_reviewed.csv`에 208건.
`review_status = DOMAIN_APPROVED`, `production_eligible = true`, 출처는 Adult Compendium 2024이며
승인 이력(`met_domain_approval_change_log.csv`, `met_final_approval_change_log.csv`)이 남아 있다.

### 목표

세션 종료 시 결정적으로 칼로리를 계산해 위 네 컬럼을 모두 채운다.

### 설계 요구

- `app/domain/rules/calories.py`를 새로 만든다. 순수 함수, 정책 버전 상수를 둔다.
- 계산 근거는 **공식 완료 판정 기준과 같은 값**을 쓴다. AGENTS.md 7절: 공식 완료 상태는 명시적인
  운동 블록 완료에서 나오지 경과 시간에서 나오지 않는다. 칼로리도 실제 수행한 블록을 근거로 한다.
  `accumulated_progress_seconds`를 쓰고 `actual_elapsed_seconds`(일시정지 포함)를 쓰지 않는다.
- `calorie_input_snapshot`에 재현에 필요한 값을 모두 남긴다: MET 값과 그 출처 버전, 사용한 시간,
  체중, 정책 버전. 저장된 스냅샷만으로 같은 숫자가 다시 나와야 한다.
- **체중이 없을 때를 반드시 정의한다.** `user_profiles.weight_kg`는 DB에서 nullable이다
  (`app/db/models/profile.py:72`). 다만 온보딩 요청에서는 **필수**이므로
  (`app/modules/profiles/schemas.py`, `weight_kg: float = Field(ge=25, le=300)`) 현재 계약으로
  가입한 사용자에게는 항상 값이 있다. 값이 없는 경우는 과거 행뿐이다.

  **권장: 체중이 없으면 칼로리를 계산하지 않고 `NULL`로 둔다.** 임의의 기본 체중으로 숫자를 만들면
  근거 없는 값을 사실처럼 보여주게 된다. ADR-0004가 칼로리를 "추정치"로 규정한 것은 근거 있는
  추정을 뜻하지 지어낸 값을 허용하는 것이 아니다. 다르게 하려면 `calorie_source_code`가 기본 체중을
  썼다는 사실을 반드시 구분해야 한다.
- MET 매핑이 없는 운동을 정의한다. 208건 매핑과 237건 카탈로그가 일치하지 않을 수 있으므로
  **착수 시 커버리지를 먼저 측정한다.**

### 인수 조건

1. 세션을 완료하면 네 칼로리 컬럼이 모두 채워진다.
2. 같은 세션 데이터로 다시 계산하면 같은 값이 나온다.
3. `calorie_input_snapshot`만으로 값을 재현할 수 있다.
4. 체중이 없는 사용자에서 정의된 동작을 하고, 예외로 세션 완료가 실패하지 않는다.
5. MET 매핑이 없는 운동이 포함돼도 세션 완료가 실패하지 않는다.
6. 칼로리 값이 안전 판정·계획 조정에 입력으로 들어가지 않는다.
7. 중단된 세션과 완료된 세션의 처리가 각각 정의돼 있다.
8. 값이 음수가 되지 않는다(CHECK 제약과 일치).

### 변경 예상 파일

`app/domain/rules/calories.py` (신규), `app/modules/workouts/service.py`,
`app/modules/workouts/schemas.py`, `app/modules/workouts/ports.py`,
`app/db/repositories/workout.py`, MET 데이터 적재 경로,
`docs/DOMAIN_RULES.md`, `docs/API_CONTRACT.md`

### 테스트

- 산식 단위 테스트 (승인된 계수 기준 골든 값)
- 재현성: 스냅샷 → 동일 값
- 체중 없음, MET 없음, 중단 세션 폴백
- 안전 규칙 불변식: 칼로리가 안전 판정에 영향을 주지 않음

### 제외 범위

웨어러블 칼로리 수집. 칼로리 목표 설정 기능. 주간 합계 노출(BL-4).
**승인 전 산식 하드코딩 금지.**
