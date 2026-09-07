# TASK-BL1-BL7-STAGE2: 코칭 스타일·장소·성별·키 legacy 컬럼 제거 (2단계)

- Primary owner: 백엔드 개발팀장
- Reviewers: 개발팀장(아키텍처), 프론트엔드 owner(응답 계약 확인)
- 관련 요구사항: `docs/tasks/2026-09-improvements/BACKEND-LEAD.md` BL-1 2단계, BL-7 2단계 (웨이브 3)
- 관련 ADR: ADR-0017
- 목표 브랜치: `feat/be-lead-wave3-drop-legacy-profile-columns`
- 상태: IN_REVIEW (임시 task ID. GitHub issue 발급 시 파일명·본문·브랜치 연결을 갱신한다.)

## 배경과 사용자 가치

BL-1과 BL-7의 1단계가 `origin/develop`에 병합돼 한 릴리스를 지났다. 1단계는 코칭 스타일과
ADR-0017이 폐기한 장소·성별·키를 **더 이상 적용하지 않는** 데서 멈췄고, 컬럼은 AGENTS.md 10절
("쓰기를 멈춘 릴리스에서 프로덕션 컬럼을 지우지 말 것")에 따라 남겨 두었다. 이 작업이 그 컬럼을
제거하는 다음 릴리스다.

사용자에게 보이는 동작 변화는 없다. 스키마에서 아무도 읽지 않는 저장소를 걷어내 이후 프로필
변경이 죽은 컬럼을 함께 끌고 다니지 않게 하는 것이 가치다.

BL-1과 BL-7은 같은 온보딩·프로필 계약을 건드리므로 계획대로 한 PR로 묶는다. 마이그레이션은
직렬이므로 한 브랜치 안에서 0049 → 0050 순서로 연결한다.

## 포함 범위

- migration 0049: `user_profiles.coaching_style_code`와 `ck_user_profiles_coaching_style` 제거.
- migration 0050: `user_profiles.preferred_location_code`, `height_cm`, `sex_code`와
  `user_available_locations` 테이블 제거.
- 위 컬럼을 읽던 repository·service·ports 경로 정리.
- 프로필이 장소를 공급하던 자리를 결정적 상수(`SELECTABLE_LOCATION_CODES`, `DEFAULT_LOCATION_CODE`)로 대체.
- `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`, ADR-0017 시행 기록 갱신.

## 제외 범위

- **응답 필드 제거.** `MeProfile.preferred_location_code`, `MeProfile.available_location_codes`,
  `MeProfile.coaching_style_code`, `OnboardingResponse.coaching_style_code`는 그대로 둔다.
  배포된 프론트가 아직 읽는다(FE-5, FE-8 미완). 고정값으로 응답한다.
- **요청 필드 제거.** 온보딩·PATCH는 legacy 필드를 계속 받고 계속 무시한다. 요청 모델이
  `extra="forbid"`이므로 필드를 지우면 구 클라이언트 요청이 422가 된다.
- `weight_kg` 제거. 온보딩 필수 입력이며 칼로리 추정이 읽는다.
- `decision_explanations.coaching_style_code` 제거. 결정 기록 컬럼이다.
- `input_snapshot.profile` allowlist에서 `preferred_location_code` key 제거.
  `DECISION_INPUT_SCHEMA_VERSION` 상향이 필요하므로 별도 작업이다.
- 프론트엔드 변경(FE-5, FE-8).

## 인수 조건

1. `user_profiles`에 `coaching_style_code`, `preferred_location_code`, `height_cm`, `sex_code`가
   없고 `user_available_locations` 테이블도 없다.
2. `ck_user_profiles_coaching_style` CHECK 제약이 없다.
3. `user_profiles.weight_kg`는 그대로 있다.
4. migration 0050 → 0048 rollback이 네 컬럼과 테이블을 되살리고, 다시 head로 올릴 수 있다.
5. 온보딩이 legacy 필드 없이도, legacy 필드를 포함해서도 성공한다.
6. `PATCH /api/v1/me/profile`이 legacy 필드를 받고 400을 내지 않으며 프로필을 바꾸지 않는다.
7. `GET /api/v1/me`가 `coaching_style_code=SUPPORTIVE`,
   `preferred_location_code=HOME`, `available_location_codes=[HOME]`을 계속 반환한다.
8. 기본 루틴 생성과 주간 계획 생성이 프로필 장소 없이 동작한다.
9. 계정 삭제가 남은 사용자 연결 테이블을 모두 지운다.
10. 기존 `input_snapshot`을 읽는 경로가 깨지지 않는다.

## 변경 예상 파일

- `backend/migrations/versions/0049_drop_profile_coaching_style.py` (신규)
- `backend/migrations/versions/0050_drop_retired_profile_cols.py` (신규)
- `backend/app/db/models/profile.py`, `backend/app/db/models/__init__.py`
- `backend/app/db/repositories/profile.py`, `account_deletion.py`, `routine.py`,
  `weekly_plan.py`, `decision.py`
- `backend/app/modules/profiles/{ports,service,schemas,codes}.py`
- `backend/app/modules/catalog/codes.py`
- `backend/tests/**`, `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`, `docs/adr/0017-*.md`

## API 영향

공개 응답 필드는 제거하지 않는다. 세 필드의 **출처**만 저장 컬럼에서 고정 상수로 바뀐다.
`preferred_location_code`는 현재 모든 프로필이 이미 `HOME`이고 `available_location_codes`는
`["HOME"]`이므로, 현행 계약으로 온보딩한 사용자에게는 응답 값이 달라지지 않는다. 1단계 이전에
다른 장소를 저장한 계정만 표시 값이 `HOME`으로 바뀐다. 해당 필드는 1단계부터 수정할 수 없었다.

요청 계약은 바뀌지 않는다.

## DB·마이그레이션 영향

- 0049, 0050 두 revision. head는 `0050_drop_retired_profile_cols`.
- rollback은 컬럼과 테이블을 되살리고 `SUPPORTIVE`·`HOME`으로 backfill한다. 1단계 이전의
  사용자별 값은 복구하지 않는다. 그 값들은 1단계에서 이미 읽히지 않게 됐다.
- `alembic_version.version_num`이 `varchar(32)`이므로 revision id는 32자 이하로 유지한다.

## 안전·개인정보·보안 영향

- 성별과 키를 저장하지 않게 되어 보관하는 건강 관련 정보가 줄어든다.
- 로그·응답에 새로 노출되는 값이 없다. 마이그레이션은 값을 읽지 않는다.
- 안전 판정 경로는 변경하지 않는다. 당일 장소 제약은 그대로 Safety-approved Pool이 적용한다.

## 선행 관계와 차단 요소

- 선행: BL-1 1단계(`cdec29b`), BL-7 1단계(`134316e`) 병합 및 배포.
- 마이그레이션 직렬 규칙: 이 브랜치가 열려 있는 동안 다른 마이그레이션 브랜치를 열지 않는다.
- FE-5, FE-8은 이 작업의 선행이 아니다. 다만 응답 필드 제거는 그 두 작업 이후로 미룬다.

## 테스트 계획

- `ruff check`, `ruff format --check`, `mypy`, `pytest` 전체.
- PostgreSQL 통합: `test_migrations.py` 전체(신규 rollback 왕복 테스트 포함),
  프로필·루틴·주간계획·결정·워크아웃·계정삭제 repository 테스트.
- API: 온보딩·프로필 설정의 legacy 필드 호환 테스트.

## 수동 확인

1. staging에 `alembic upgrade head`를 적용하고 `\d user_profiles`로 네 컬럼과 CHECK 부재를 확인한다.
2. `GET /api/v1/me`가 세 legacy 응답 필드를 계속 반환하는지 확인한다.
3. 마이페이지에서 장소·성별·키 수정 요청이 200으로 끝나고 아무것도 바뀌지 않는지 확인한다.
4. 신규 계정 온보딩 후 기본 루틴이 생성되는지 확인한다.
5. `alembic downgrade 0048_integrated_catalog_v2_0_7` 후 다시 `upgrade head`가 되는지 확인한다.

## 알려진 제한과 후속 작업

- `MeProfile`의 세 legacy 응답 필드와 `OnboardingResponse.coaching_style_code`가 남아 있다.
  FE-5·FE-8 이후 별도 릴리스에서 제거한다.
- `input_snapshot.profile.preferred_location_code`가 항상 `null`인 채로 남는다.
  key 제거는 `DECISION_INPUT_SCHEMA_VERSION` 상향과 함께 처리한다.
- 배포 직후 같은 날 재요청은 snapshot 값 변화로 input_hash가 달라져 캐시된 결정을 재사용하지 않고
  새 decision run을 만들 수 있다. 일회성이며 unique index 위반은 발생하지 않는다.
