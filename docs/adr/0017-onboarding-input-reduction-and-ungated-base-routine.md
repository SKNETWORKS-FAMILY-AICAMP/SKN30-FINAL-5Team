# ADR-0017: 온보딩 입력 축소와 장소 비게이트 기본 루틴

- 상태: ACCEPTED
- 날짜: 2026-09-02
- 소유자: 제품·개발 공동
- 승인 근거: 사용자 명시 요청(2026-09-02)
- 관련: ADR-0016, `SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md`

## 배경

`SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md`는 온보딩에서 성별·키·장소·1회 운동시간·보유 장비를
제거했다. 그러나 하위 계약이 함께 정리되지 않아 다음 네 지점이 서로 충돌했다.

1. `POST /api/v1/routines`가 프로필의 `default_requested_duration_minutes`로 폴백하고 장소로 후보를
   필터한다. 기본 루틴은 온보딩 트랜잭션의 `ensure_initial_routine`에서 provisioning되므로 첫
   Daily Check-in보다 먼저 실행되고, 두 값을 체크인에서 조회할 수 없다.
2. `MeProfile`과 `PATCH /api/v1/me/profile`이 제거 대상 필드를 그대로 노출한다.
3. 닉네임이 온보딩 요청 예시와 MVP 필수 목록에서만 빠지고 나머지 계약에는 남았다.
4. `attention_area_codes`가 legacy로 강등됐으나 응답·PATCH·decision snapshot allowlist에 남았다.

## 결정

- 닉네임은 온보딩 필수 입력으로 유지한다.
- 성별, 키, BMI, 온보딩 장소, 온보딩 1회 운동시간, 보유 장비는 온보딩에서 수집하지 않는다.
- 운동 장소와 1회 운동시간은 Daily Check-in의 `location_code`와 `available_time_minutes`로만 받는다.
  프로필에 기본값을 두지 않는다.
- **온보딩 트랜잭션에서 만드는 기본 루틴은 장소를 후보 게이트로 사용하지 않는다.** 목표 시간은
  배포 설정으로 승인한 서버 기본 상수를 사용하며, 이 상수는 정책 범위 10–60분 안에 있어야 한다.
- 평소 통증 부위는 온보딩에서 `persistent_pains`로 수집한다. 이 값은 Daily Check-in의 수정 가능한
  기본값일 뿐이며, 제출된 `daily_context_pains`만 Safety 입력이다. 평소 상태 자체의 변경은
  마이페이지의 `persistent_pains` 수정으로 처리한다.
- 제거 대상 요청 필드는 즉시 삭제하지 않고 legacy로 표시해 write 호환 기간을 둔 뒤 별도 릴리스에서
  요청 필드와 컬럼을 순서대로 제거한다.

## 이유

장소가 매일 달라지는 입력이 되면 기본 루틴에 장소를 고정하는 것 자체가 새 모델과 맞지 않는다. 기본
루틴은 템플릿이고, 당일 장소 제약은 이미 매일 재구성하는 Safety-approved Pool과 Feasibility가
적용한다. 2026-08-27에 사용자 보유 장비를 후보 게이트에서 제외한 것과 같은 처리다.

## 대안과 선택하지 않은 이유

- **온보딩에 장소만 남긴다**: 변경은 가장 작지만 "온보딩 장소 삭제" 정책을 되돌려야 하고, 매일 장소가
  바뀌는 사용자에게 의미 없는 값을 계속 묻게 된다.
- **기본 루틴 생성을 첫 Check-in 이후로 미룬다**: 정책상 가장 깔끔하지만 온보딩 직후 홈에 루틴이 없는
  상태를 UX가 감당해야 하고, `온보딩 → 기본 루틴` 수직 슬라이스 흐름을 바꿔야 한다.

## 결과

- `OnboardingUpsertRequest`에서 `sex_code`, `height_cm`, `preferred_location_code`,
  `available_location_codes`, `default_requested_duration_minutes`, `attention_area_codes`를 제거하고
  `persistent_pains`를 추가한다.
- `PATCH /api/v1/me/profile`은 `persistent_pains`를 지원하고 legacy 필드를 호환 기간에만 유지한다.
- 기본 루틴 생성 경로에서 장소 필터를 제거하고 서버 기본 시간 상수를 도입한다. 승인된 상수가 없으면
  `503 PROFILE_CONFIGURATION_UNAVAILABLE`로 fail-closed한다.
- `input_snapshot.profile` allowlist에서 장소·시간·주의 부위를 제거한다. 기존 snapshot은 rewrite하지
  않고 read 경로를 유지한다. 과거 결정의 재현 근거는 저장된 snapshot뿐이다.
- Daily Check-in은 `persistent_pains`를 기본값으로 prefill하고, 통증 입력을 3단계 severity에서
  NRS 1–10으로 바꾼다.

## 확정된 후속 결정 (2026-09-02)

- 기본 루틴 목표 시간 서버 상수는 **30분**이다. 정책 범위 10–60분 안에 있으며 사용자 요청 시간을
  축소하는 근거로 쓰지 않는다.
- 장소 비게이트로 HOME 전용 사용자의 기본 루틴에 GYM 전용 운동이 섞일 수 있으나, 기본 루틴을 사용자에게
  노출하는 화면이 없어 표시 문제는 발생하지 않는다. `HomeContainer`는 기본 루틴에서
  `days[0].requested_duration_minutes`만 읽고, 화면에 렌더링되는 운동 목록은 decision의 최종 추천안이다.
  당일 장소 제약은 매일 재구성하는 Safety-approved Pool이 적용한다.
- 기본 루틴과 당일 결정의 경계를 `ARCHITECTURE.md` §4.0에 명시한다. 사용자 문구에서 `기본 루틴` 내부
  용어를 제거하고 `운동 계획`으로 표현한다.
- `preferred_exercise_type_codes`(선호 운동 유형 `STRENGTH`/`CARDIO`/`MOBILITY`)는 수집하지 않는다.
  운동 목표 `primary_goal_code`(`MUSCLE_GAIN`/`GENERAL_FITNESS`/`FAT_LOSS`)가 이미
  `exercise_goal_tag_links`·`exercise_prescription_profiles` 조인으로 후보 선정을 결정하고 있어 의미가
  겹친다. 기존 컬럼과 요청 필드는 다른 legacy 필드와 같은 순서로 제거한다.
- staging 카탈로그는 `exercise-catalog-v2.0.4-final`이므로 세 목표 모두 승인 pool이 존재한다.
  v2.0.5 배포가 대기 중이다.

## 미확정 사항

- 만 18–64세 범위 밖 기존 가입자의 처리 방침.
