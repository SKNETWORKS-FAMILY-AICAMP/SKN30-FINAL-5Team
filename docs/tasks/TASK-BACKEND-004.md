# TASK-BACKEND-004: 온보딩 적격성·생년월일 보호·동의 기반

- Primary owner: 백엔드
- Reviewers: 개발팀장, 백엔드 담당, PM·개인정보 검토자
- 관련 요구사항: `F025`, `NFR-005`, `NFR-006`
- 관련 ADR: `ADR-0004`, `ADR-0005`
- 목표 브랜치: `feat/onboarding-consent`

## 배경과 사용자 가치

검증된 Firebase 사용자가 온보딩에서 생년월일과 운동 선호, 분리된 동의를 저장할 수 있는
백엔드 경계를 만든다. 클라이언트의 생년월일 선택 제한과 개인정보·만 14세 이상 확인을 1차
게이트로 두고, 서버는 온보딩과 생년월일 수정 시 사용자 timezone의 로컬 날짜로 만 14세 이상
여부만 최종 검증한다. 숫자 나이는 계산·저장·응답하지 않으며 생년월일 원문이 불필요한 계층으로
확산되지 않게 한다.

## 이번 착수 범위

- 사용자 timezone 기준 만 14세 적격성 검증(숫자 나이 산출 없음)
- 미래 생년월일과 잘못된 timezone 거부
- 프로필 계층 전용 생년월일 암호화 port
- local/test 전용 AES-GCM adapter
- 사용자 UUID를 AES-GCM additional authenticated data로 결합
- 단위 테스트와 개인정보 비노출 검증

## 승인 후 후속 범위

- `PUT /api/v1/me/onboarding`
- `PUT /api/v1/me/consents`
- `user_profiles`, `user_consents`, append-only `user_consent_events`
- 장비·주의 부위·선호 운동 유형 관계 저장
- 동의 mutation 멱등성 및 원자성
- 공개 API·PostgreSQL integration test와 Alembic migration

## 제외 범위

- `/me` 조회와 identity 목록
- 계정 삭제와 동의 철회 후 외부 provider 해제
- routine, decision, agent 입력
- production KMS adapter와 cloud key lifecycle
- 닉네임 금칙어·표시 문구 정책

## 현재 차단 조건

1. `primary_goal_code`, `experience_level_code`의 첫 수직 슬라이스 machine code 승인이 필요하다.
2. 온보딩 boolean 동의 요청을 DB의 필수 `policy_version`에 매핑할 승인된 버전이 필요하다.
3. `adult_confirmed`, `age_band_code`를 무시할지 별도 API 버전을 사용할지 호환 전략 승인이 필요하다.
4. 닉네임 최소 길이·금칙어 정책은 PM 검토 전 임의 구현하지 않는다.
5. 현재 `API_CONTRACT.md`의 `/me.age` 계산·응답 계약은 이번 결정과 충돌하므로 공개 endpoint 연결
   전에 개발팀장·프론트엔드·백엔드 승인으로 계약과 호환 전략을 갱신해야 한다.
6. 만 14세 이상 확인을 일반 개인정보 동의와 분리된 자격 확인으로 저장할지, consent policy에
   포함할지에 대한 요청 필드와 감사 저장 계약 승인이 필요하다.

## 인수 조건

1. 정확히 만 14세가 되는 일반 경계일은 허용하고 하루 전은 차단한다.
2. 서버 기준 시각을 사용자 timezone의 로컬 날짜로 변환해 판정한다.
3. 2월 29일 출생자는 비윤년의 3월 1일부터 적격으로 판정한다.
4. 검증 결과는 숫자 나이를 포함하지 않고 적격 여부만 성공 또는 도메인 오류로 표현한다.
5. 미래 생년월일과 알 수 없는 timezone을 안전한 도메인 오류로 거부한다.
6. 생년월일 암호문은 같은 입력도 매번 달라야 한다.
7. 다른 사용자 UUID나 변조된 암호문으로 복호화할 수 없어야 한다.
8. 암호화 오류에 생년월일, 키, 암호문을 포함하지 않는다.
9. AES-GCM adapter는 local/test에서만 생성 가능하며 production 구현을 가장하지 않는다.

## 변경 예상 파일

- `docs/tasks/TASK-BACKEND-004.md`
- `backend/app/modules/profiles/age.py`
- `backend/app/modules/profiles/ports.py`
- `backend/app/integrations/birthdate_crypto.py`
- `backend/tests/unit/test_profile_age.py`
- `backend/tests/unit/test_birthdate_crypto.py`
- `pyproject.toml`, `uv.lock`

## API 영향

이번 기반 커밋은 공개 endpoint와 request/response field를 추가하지 않는다. 승인 공백 해소 후
`API_CONTRACT.md`에서 계산 나이 응답을 제거하고 만 14세 이상 확인과 생년월일 적격성 검증 계약을
확정한 뒤 경로와 오류 envelope를 구현한다.

## DB·마이그레이션 영향

이번 기반 커밋은 DB schema를 변경하지 않는다. 현재 Alembic head는
`0003_identity_auth_boundary`이다. 후속 migration은 승인된 consent policy version과 profile code
집합을 포함해 최신 develop head에서 추가한다.

## 안전·개인정보·보안 영향

- 숫자 나이는 계산·저장·응답하지 않으며 평문 생년월일을 로그·분석·agent·decision snapshot으로
  전달하지 않는다.
- AES-GCM 256-bit key는 호출자가 secret 설정으로 제공하며 소스와 fixture에 저장하지 않는다.
- 암호문은 무작위 nonce와 사용자별 authenticated data를 사용한다.
- production에서는 후속 KMS adapter 승인 전 local/test adapter 사용을 거부한다.

## 테스트 계획

- 일반 만 14세 당일·하루 전 경계와 숫자 나이 비노출
- 2월 29일 출생자의 비윤년 3월 1일 경계
- timezone 날짜 경계와 미래 날짜
- AES-GCM round trip, 무작위 nonce, 사용자 교체·변조 차단
- production 환경 adapter 차단
- ruff, mypy, 전체 pytest

## 알려진 제한과 후속 작업

- 공개 온보딩·동의 API와 persistence는 위 차단 조건 승인 후 같은 Wave 3 범위에서 이어간다.
- local/test key의 환경 변수 이름·rotation은 API wiring 시 config와 함께 추가한다.
- production KMS 공급자와 key 접근 감사는 cloud 결정 후 별도 adapter로 구현한다.
