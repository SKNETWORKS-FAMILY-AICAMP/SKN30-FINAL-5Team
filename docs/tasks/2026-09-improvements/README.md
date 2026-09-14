# 2026-09 배포 후 개선 작업 계획

- 작성일: 2026-09-07
- 기준 코드: `origin/develop` = `5a6fd26` (스테이징 배포본과 동일)
- 소유자: 개발팀장
- 목적: 스테이징 배포 이후 확인된 개선 항목과 확정된 논의 사항을, 코딩 에이전트가 한 항목씩
  독립적으로 수행할 수 있는 단위로 분해한다.

## 이 문서 묶음의 사용법

| 파일 | 대상 |
|---|---|
| `README.md` (이 문서) | 전체 목록, 게이트 결정, 병렬화 계획, 충돌 지도 |
| `BACKEND-LEAD.md` | 백엔드 개발팀장 트랙 (BL-1 ~ BL-7) |
| `BACKEND-MEMBER.md` | 백엔드 팀원 트랙 (BM-1 ~ BM-6) |
| `FRONTEND.md` | 프론트엔드 트랙 (FE-1 ~ FE-15) |

각 작업 블록은 그 자체로 완결된 지시서다. 코딩 에이전트에게는 다음 형태로 넘긴다.

```
docs/tasks/2026-09-improvements/BACKEND-MEMBER.md 의 BM-2 를 수행하라.
AGENTS.md 와 backend/AGENTS.md, 해당 모듈의 AGENTS.md 를 먼저 읽어라.
그 블록의 "제외 범위"를 넘지 마라.
```

작업을 실제로 착수할 때는 `docs/tasks/README.md`의 착수 게이트에 따라 이 블록을 근거로
`docs/tasks/TASK-<issue>.md`를 발급하고 GitHub issue 번호를 연결한다. 이 문서는 계획서이고,
개별 task 문서를 대체하지 않는다.

## 이 계획이 근거로 삼은 현재 코드 사실

착수 전 재확인이 필요한 항목은 각 블록에 표시했다. 아래는 2026-09-07 기준으로 확인한 사실이다.

- `available_time_minutes`의 상한은 `backend/app/modules/checkins/schemas.py:96`에 `le=60`,
  레거시 경로는 같은 파일 145행에 `10 <= requested_duration_minutes <= 60`으로 이중으로 걸려 있다.
- 운동 상세 응답(`backend/app/modules/catalog/schemas.py:286`)에는 주의사항 필드가 없다.
  `cautions_ko`는 `HouseholdEquipmentGuide` 안에만 있고, 이 가이드는 승인 번들에 존재하는
  34개 운동에만 붙는다. 운동 테이블에도 주의사항 컬럼이 없다
  (`backend/app/db/models/catalog.py:247` 기준 `instruction_summary_ko`, `form_cues_ko`뿐).
- `GET /exercises/{id}/variants`(`backend/app/api/v1/exercises.py:126`)는 장소 파라미터를 받지 않는다.
- 루틴 이름은 프론트엔드가 `body_focus_code`와 `training_type_code` 두 코드만으로 만든다
  (`frontend/src/features/home/homeModel.ts:687`). 백엔드에는 루틴 이름 개념이 없다.
- `coaching_style_code`는 `NOT NULL` + CHECK 제약이며(`backend/app/db/models/profile.py:44,71`)
  결정 설명 템플릿이 사용한다(`backend/app/modules/decisions/explanations.py`).
- 바나나코인 백엔드는 이미 있다: 지갑·일일 보상·소비·집 아이템 구매
  (`backend/app/modules/rewards/`, `backend/app/api/v1/rewards.py`).
- 미니게임도 이미 있다(`frontend/src/features/bananaCatch/`). 신규 추가가 아니라 보강 항목이다.
- 칼로리 저장 컬럼과 출처·정책버전·입력 스냅샷 컬럼은 이미 있으나
  (`backend/app/db/models/workout.py:154-159`) 값을 계산하는 코드가 없어 항상 `None`이다.
  검수된 MET 데이터는 `data/generated/exercise-met-mapping-v0.1.0/`에 208건 있다.
- 소셜 로그인은 결정적 도메인 규칙만 있고(`backend/app/domain/rules/auth_provider.py`,
  GOOGLE·KAKAO·NAVER) API route가 없다. `IdentityProviderCode`는 `FIREBASE` 하나뿐이다.
- 프로필 이미지 업로드 경로는 백엔드·프론트 모두 구현돼 있다
  (`backend/app/modules/profiles/images.py`, `frontend/src/features/home/MyPageProfileEditor.tsx`).
- 온보딩 요청 스키마는 이미 ADR-0017을 반영했다. `preferred_location_code`,
  `available_location_codes`, `default_requested_duration_minutes`, `coaching_style_code`,
  `height_cm`, `sex_code`가 모두 기본값 또는 optional이며 **필수가 아니다**
  (`app/modules/profiles/schemas.py`). 스키마 주석이 "Location and duration are selected by Daily
  Check-in after onboarding"이라고 명시한다.
- 반면 `weight_kg`는 온보딩 **필수**다(`Field(ge=25, le=300)`). 칼로리 계산의 체중 입력이
  현재 계약에서 항상 확보된다는 뜻이다. DB 컬럼은 nullable이므로 과거 행에는 없을 수 있다.
- 프론트 온보딩 화면에는 장소·성별·키 입력이 없다. 남아 있는 것은 **코칭 스타일 단계**와
  **마이페이지의 성별·키·운동 장소 수정**이다.
- 계획 무결성 검증은 운동 종류 수를 `len(set(ids))`로 센다
  (`app/domain/agents/v3_validation.py:263`). 즉 **같은 운동이 여러 블록에 반복되는 것은 이미
  허용**되며, 반복해도 종류 상한에 한 번만 계산된다. 반복을 만들지 않는 쪽은 검증이 아니라
  생성기다 — 결정적 fallback이 `placed: dict[UUID, PhaseCode]`로 운동당 한 자리만 배정한다
  (`app/integrations/langgraph/fallback.py`).

## 승인 게이트 — 2026-09-07 전부 확정

착수를 막는 게이트는 남아 있지 않다. 아래가 확정된 결정이다.

| 게이트 | 대상 | 결정 |
|---|---|---|
| G1 | BL-2 | **ADR-0009 `ACCEPTED`.** 소셜 로그인 구현 금지가 해제됐다. Kakao → Google → Naver 순서는 ADR이 정한 대로 유지한다. |
| G2 | BL-3, FE-13 | **사용자에게 보이는 웨어러블 표기를 전부 제거한다.** 연동 체크, 동의 항목, 연동 기기 행을 없앤다. 데이터 계약은 **확장성으로만 열어두고** 화면에는 노출하지 않는다. |
| G3 | BM-6 | **체중과 실제 수행한 운동을 근거로 칼로리를 계산한다.** MET × 체중 × 수행 시간 기반 추정이며 ADR-0004의 "추정치" 경계를 유지한다. |
| G4 | BM-1 | **운동 종류는 10개 상한을 유지하되, 스트레칭(WARMUP·COOLDOWN)을 제외한 MAIN 구간에서는 같은 운동의 반복 배치를 허용해 시간을 채운다.** 반복은 연속되지 않게 순서를 섞는다. 예: 푸시업 → 스쿼트 → 데드리프트 → 푸시업. |
| G5 | BM-2 | **확인 완료.** `form_cues_ko`를 주의사항으로 표기한다. 신규 콘텐츠 검수 없음. |
| G6 | BL-1, FE-8 | **코칭 스타일을 가장 일반적인 단일 스타일로 고정하고 선택 화면 자체를 없앤다.** 모든 사용자가 동일한 컨텍스트를 받는다. 온보딩 단계가 줄어드는 데 따른 완료 처리를 함께 고친다. |
| G7 | BM-4, FE-4, FE-5 | **온보딩에서 집·헬스장 선택을 제거하고, 운동 장소는 체크인 화면에서 고른다.** 온보딩 완료 오류가 나지 않게 함께 고친다. 노출 대상은 집과 헬스장 둘뿐이며 **`OUTDOOR`는 표시하지 않는다**(값 자체는 유지). |

### G7과 G6은 이미 승인된 ADR-0017의 미완 실행이다

`docs/adr/0017-onboarding-input-reduction-and-ungated-base-routine.md`(**ACCEPTED**, 2026-09-02)가
G7을 이미 같은 내용으로 결정해 두었다.

> 성별, 키, BMI, 온보딩 장소, 온보딩 1회 운동시간, 보유 장비는 온보딩에서 수집하지 않는다.
> 운동 장소와 1회 운동시간은 Daily Check-in의 `location_code`와 `available_time_minutes`로만 받는다.
> 프로필에 기본값을 두지 않는다.

따라서 G7에는 새 ADR이 필요 없다. **이미 결정된 것을 끝까지 시행하는 작업**이다. 진행 상태는 다음과 같다.

| ADR-0017 항목 | 백엔드 | 프론트엔드 |
|---|---|---|
| 온보딩에서 장소 수집 제거 | 완료 — `preferred_location_code`가 기본값을 가진 legacy 필드다 | 완료 — 온보딩 화면에 장소 입력이 없다 |
| 온보딩에서 성별·키 수집 제거 | 완료 — optional legacy | 완료 — 온보딩에 없음 |
| 장소를 체크인에서만 받기 | 완료 | **미완** — 체크인 선택지를 아직 프로필로 제한한다 |
| 프로필에 장소 기본값 두지 않기 | 미완 — legacy 필드 제거 순서 남음 | **미완** — 마이페이지에 "운동 장소" 수정이 남아 있다 |
| 성별·키를 프로필에서 제거 | 미완 — legacy | **미완** — 마이페이지 프로필 수정에 성별·키가 남아 있다 |

즉 사용자가 본 두 현상 — 체크인 장소가 온보딩 선택에 묶여 있는 것, 마이페이지에 키·성별이 남아
있는 것 — 은 **같은 원인**이다. ADR-0017의 프론트 측 정리가 끝나지 않았다.

### 코칭 스타일도 백엔드는 이미 준비돼 있다

`OnboardingUpsertRequest.coaching_style_code`에 기본값 `SUPPORTIVE`가 있어
(`app/modules/profiles/schemas.py`) 이 필드를 보내지 않아도 온보딩이 성공한다. G6의 백엔드 작업은
설명 템플릿 정리(`decisions/explanations.py`)가 대부분이고, 온보딩 단계 제거는 프론트 작업이다.

### 웨어러블: "확장성으로만 열어둔다"의 경계 (G2)

- **제거**: 온보딩 웨어러블 동의 체크박스, 마이페이지 "연동 기기" 행, "웨어러블 연동" 동의 항목,
  연동 관련 문구 일체. 사용자가 웨어러블이라는 단어를 볼 수 있는 지점을 남기지 않는다.
- **유지(확장성)**: `sleep_source_code`의 `MANUAL | WEARABLE` 값 도메인,
  `ConsentTypeCode.WEARABLE_INTEGRATION` 값, 골든 시나리오 4번(수동 체크인 폴백).
- **이유**: 값 도메인을 좁히면 기존 행이 깨지고, AGENTS.md 11절의 필수 골든 시나리오가 사라진다.
  값을 남겨도 화면에 나오지 않으므로 "현재 서비스에는 표시 안 됨" 요구를 만족한다.
- **선례**: ADR-0016(외부 캘린더 폐기)이 같은 형태의 결정을 기록한 방식을 따른다.

## 작업 목록

| ID | 항목 | 트랙 | 선행 |
|---|---|---|---|
| BL-1 | 코칭 스타일 단일화 (2단계) | 팀장 | – |
| BL-2 | 소셜 로그인 (Kakao → Google → Naver) | 팀장 | – |
| BL-3 | 웨어러블 표기 제거 | 팀장 | – |
| BL-4 | 주간 리포트 지표 확장 | 팀장 | – |
| BL-5 | 프로필 이미지 변경 미반영 원인 규명과 수정 | 팀장 | – |
| BL-6 | 약관·개인정보 처리방침 콘텐츠 계약 | 팀장 | – |
| BL-7 | ADR-0017 잔여 정리: 장소·성별·키 legacy 필드 | 팀장 | – |
| BM-1 | 운동 시간 상한 90분 + MAIN 반복 배치 | 팀원 | – |
| BM-2 | 운동 상세 계약: 주요 부위·단계별 자세 설명·주의사항 | 팀원 | – |
| BM-3 | 장비 대체 변형 운동을 집 운동으로 한정 | 팀원 | – |
| BM-4 | 체크인에서 운동 장소 선택 | 팀원 | – |
| BM-5 | 루틴 이름 결정 규칙 | 팀원 | – |
| BM-6 | 세션 종료 시 소모 칼로리 | 팀원 | – |
| FE-1 | 운동 상세 화면 구성 순서와 가독성 | 프론트 | BM-2 |
| FE-2 | 변형 운동 노출을 집 운동으로 한정 | 프론트 | BM-3 |
| FE-3 | 체크인 위험 신호 질문 중복 제거 | 프론트 | – |
| FE-4 | 체크인 장소 선택 UI | 프론트 | BM-4 |
| FE-5 | 마이페이지 ADR-0017 정리 (성별·키·운동 장소) | 프론트 | BL-7 |
| FE-6 | 운동 시간 90분 UI와 권장 안내 | 프론트 | BM-1 |
| FE-7 | 주간 리포트 리디자인 | 프론트 | BL-4 |
| FE-8 | 코칭 스타일 온보딩 단계 제거 | 프론트 | – |
| FE-9 | 끼끼의 집 버튼 에셋과 쓰다듬기 문구 | 프론트 | – |
| FE-10 | 루틴 이름 표시 | 프론트 | BM-5 |
| FE-11 | 소셜 로그인 UI | 프론트 | BL-2 |
| FE-12 | 바나나코인·끼끼패스 화면 | 프론트 | – |
| FE-13 | 웨어러블 UI 제거 | 프론트 | – |
| FE-14 | `HomeScreen.tsx` 분할 (충돌 완화 선행 작업) | 프론트 | – |
| FE-15 | 프로필 사진 변경 반영 | 프론트 | BL-5 |

## 병렬화 계획

### 웨이브 0 — 선행 정리

- 프론트: **FE-14** (`HomeScreen.tsx` 분할). 뒤따르는 프론트 작업 4건의 충돌을 없애는 선행 작업이므로
  가장 먼저 단독 PR로 병합한다. AGENTS.md 4절에 따라 이 PR에는 기능 변경을 섞지 않는다.
- 팀장: ADR-0009 수정본을 커밋한다. 현재 작업 트리에만 `ACCEPTED`로 바뀌어 있고 커밋되지 않았다.

### 웨이브 1 — 전부 동시 진행 가능

게이트가 모두 풀려 세 트랙이 각자 5~6건을 병렬로 진행한다.

| 팀장 | 팀원 | 프론트 |
|---|---|---|
| BL-1 코칭 스타일 1단계 | BM-1 90분 + MAIN 반복 배치 | FE-3 위험 신호 중복 제거 |
| BL-4 주간 리포트 지표 | BM-2 운동 상세 계약 | FE-8 코칭 스타일 단계 제거 |
| BL-5 프로필 이미지 진단 | BM-3 변형 운동 한정 | FE-9 집 버튼·문구 |
| BL-6 약관 콘텐츠 | BM-4 체크인 장소 선택 | FE-12 바나나코인·끼끼패스 |
| BL-7 ADR-0017 잔여 정리 | BM-5 루틴 이름 규칙 | FE-13 웨어러블 UI 제거 |
| BL-3 웨어러블 표기 제거 | BM-6 세션 종료 칼로리 | |

BM-1은 이 중 가장 무겁다(계획 구성 규칙 변경). 먼저 착수하는 것을 권장한다.
BL-2(소셜 로그인)도 게이트가 풀렸으나 분량이 커서 웨이브 2에 두었다. 팀장 트랙이 웨이브 1을 일찍
끝내면 앞당겨도 된다.

### 웨이브 2 — 웨이브 1 결과에 의존

| 팀장 | 팀원 | 프론트 |
|---|---|---|
| BL-2 소셜 로그인 (Kakao) | – | FE-1, FE-2, FE-4, FE-5, FE-6, FE-7, FE-10, FE-15 |

### 웨이브 3

- **BL-1 2단계** (`coaching_style_code` 컬럼 제거 마이그레이션). 1단계 배포가 안정화된 다음
  릴리스에서만 수행한다.
- **BL-7 2단계** (장소·성별·키 legacy 컬럼 제거). 같은 이유로 분리한다.
- **FE-11** 소셜 로그인 UI.

## 충돌 지도

병렬 작업이 실제로 병렬이 되려면 아래 지점을 관리해야 한다.

### 1. Alembic 마이그레이션은 직렬이다

BL-2, BL-1 2단계, BL-7 2단계가 각각 마이그레이션을 만든다. Alembic 히스토리는 선형이므로 두
브랜치가 같은 `down_revision`을 잡으면 병합 시 헤드가 갈라진다.

규칙: **동시에 열려 있는 마이그레이션 브랜치는 하나만 둔다.** 두 번째 작업은 첫 번째가
`develop`에 병합된 뒤 `down_revision`을 다시 잡는다. 현재 헤드는 `0045_v2_0_6_release_contract`다.

웨이브 1에는 마이그레이션이 하나도 없다. 웨이브 3의 두 컬럼 제거 작업은 순서를 정해 하나씩 진행한다.

### 1-2. BL-1과 BL-7은 같은 온보딩 계약을 건드린다

둘 다 `app/modules/profiles/schemas.py`의 `OnboardingUpsertRequest`와 프로필 응답을 수정한다.
같은 팀장 트랙이므로 파일 충돌은 나지 않지만, **한 PR로 묶거나 엄격히 순차 진행한다.**
두 브랜치를 동시에 열면 같은 스키마에서 충돌한다.

같은 이유로 프론트의 FE-8(코칭 스타일 단계 제거)과 FE-5(마이페이지 정리)도 온보딩·마이페이지
계약을 공유한다. 두 작업은 각각 다른 화면 파일을 건드리므로 병렬 가능하지만,
`frontend/src/api/types.ts`를 함께 수정하게 되면 그 파일만 조율한다.

### 2. `frontend/src/features/home/HomeScreen.tsx` (5,308줄)

FE-3, FE-4, FE-6, FE-10이 모두 이 파일을 건드린다. FE-14로 먼저 분할하지 않으면 네 작업을
직렬화해야 한다. 분할을 선택하는 쪽을 권장한다.

### 3. 트랙 간 모듈 소유

파일 충돌이 나지 않도록 백엔드 두 트랙의 모듈 소유를 분리했다.

| 트랙 | 소유 모듈 |
|---|---|
| 팀장 | `app/modules/profiles/**`, `app/modules/identity/**`, `app/modules/weekly_reports/**`, `app/modules/decisions/explanations.py`, `app/domain/rules/auth_provider.py` |
| 팀원 | `app/modules/catalog/**`, `app/modules/checkins/**`, `app/modules/workouts/**`, `app/modules/routines/**`, `app/domain/rules/duration.py`, `app/domain/rules/plan_shape.py` |

상대 트랙 모듈을 수정해야 하면 먼저 소유자에게 알리고, 별도 PR로 분리한다.

### 4. 트랙을 넘는 데이터 의존 (파일 충돌 아님)

- BL-4(주간 리포트 총 소모 칼로리)는 BM-6이 채우는 `workout_sessions.estimated_calories_burned`를
  읽는다. 컬럼은 이미 존재하므로 두 작업은 순서와 무관하게 진행할 수 있다. BM-6 전에는 합계가
  0 또는 null이 되므로, BL-4는 "아직 계산되지 않음" 상태를 응답에서 구분할 수 있어야 한다.
- `docs/API_CONTRACT.md`는 여러 작업이 함께 고친다. 각 PR은 자기 절만 수정하고, 문서 전체 재정렬은
  하지 않는다.

## 공통 규칙

모든 작업에 적용된다. 각 블록에서 반복하지 않는다.

- 브랜치: 이슈당 하나. `feat/…`, `fix/…`, `chore/…`. `main`·`develop` 직접 커밋 금지.
- 백엔드 완료 조건: `ruff format`, `ruff check`, `mypy`, 해당 영역 `pytest`가 모두 통과해야 한다.
  실행하지 않은 테스트를 통과했다고 보고하지 않는다.
- 프론트엔드 완료 조건: 린터, 타입 체크, 변경 동작에 대한 컴포넌트 테스트, 프로덕션 빌드.
- 공개 응답 필드는 하위 호환을 유지한다. 새 필드는 가능하면 optional로 추가한다.
- 스키마 변경은 Alembic 마이그레이션과 함께 간다. 롤백 또는 전진 수정 전략을 문서화한다.
- 인증 토큰, 이메일, 이름, 원시 건강 기록을 로그에 남기지 않는다.
- 기능 PR에 무관한 리팩터링을 섞지 않는다.
- PR 본문에 테스트 요약과 위험 평가를 넣는다.

## 이 계획에 포함하지 않은 항목

- **서비스 테스트 계획 및 결과**: 저장소 루트에 `헬끼_멀티에이전트_테스트_계획_및_결과_보고서_30기_5팀.docx`가
  이미 있다. 신규 개발 작업이 아니라 문서 갱신 항목이므로 PM 트랙에서 다룬다.
- **끼끼 컨텐츠 보강 아이디어**: 아이디어가 나온 뒤에 범위를 정한다. 미니게임은
  `frontend/src/features/bananaCatch/`로 이미 존재하므로 "추가"가 아니라 "보강"이다.
