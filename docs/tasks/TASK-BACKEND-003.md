# TASK-BACKEND-003: Firebase 인증 경계와 내부 사용자 연결

- Primary owner: 백엔드
- Reviewers: 개발팀장, 백엔드 담당
- 관련 요구사항: `NFR-005`, `NFR-006`, `POL-013`
- 관련 ADR: `ADR-0003`
- 목표 브랜치: `feat/firebase-auth-boundary`

## 배경과 사용자 가치

클라이언트가 전달한 Firebase ID Token을 백엔드가 최종 세션 권한으로 검증하고,
검증된 subject를 provider-neutral 내부 사용자와 연결한다. 첫 로그인은 별도 가입 API 없이
내부 `users`와 `user_identities`를 원자적으로 생성하며 이후 요청은 같은 사용자를 재사용한다.

## 포함 범위

- Firebase Admin SDK 기반 ID Token verifier adapter
- verifier protocol과 테스트용 대체 구현 경계
- Bearer 인증 FastAPI dependency와 공통 오류 매핑
- 현재 사용자 identity service
- `users`, `user_identities` 모델·저장소·Alembic migration
- 최초 로그인 자동 생성, 재로그인 멱등성, 비활성 계정 접근 차단
- 단위, API, PostgreSQL integration test

## 제외 범위

- 공개 `/me` endpoint와 사용자 프로필 응답
- 온보딩, 약관·동의 저장
- Google/Kakao/Naver OAuth 교환 endpoint
- 계정 휴면 전환, 삭제 실행, 구독 상태 변경
- 사용자 표시명
- 안전 규칙 reason code와 미확정 임계값

## 인수 조건

1. 유효한 Firebase ID Token의 첫 요청은 내부 사용자와 FIREBASE identity를 한 transaction에서 생성한다.
2. 같은 Firebase subject의 반복 요청은 같은 내부 user UUID를 반환하고 중복 행을 만들지 않는다.
3. 동시에 들어온 첫 요청도 active identity 유일성을 보장한다.
4. Firebase token이 없으면 `401 AUTHENTICATION_REQUIRED`, 유효하지 않으면 `401 INVALID_TOKEN`이다.
5. Firebase verifier를 사용할 수 없으면 `503 AUTH_PROVIDER_UNAVAILABLE`이다.
6. ACTIVE가 아닌 내부 계정은 `403 ACCOUNT_DISABLED`이다.
7. token, Firebase subject, 이메일, 전체 이름을 API 응답이나 로그에 노출하지 않는다.
8. DB machine code는 PostgreSQL ENUM이 아닌 문자열 CHECK로 검증한다.
9. code set은 `identity-mvp-v1` 버전을 갖고 기존 문서의 code를 삭제하거나 이름을 바꾸지 않는다.
10. migration upgrade/downgrade/upgrade와 수정 영역 테스트가 통과한다.

## 변경 예상 파일

- `docs/tasks/TASK-BACKEND-003.md`
- `backend/app/modules/identity/**`
- `backend/app/integrations/firebase_auth.py`
- `backend/app/api/dependencies.py`
- `backend/app/db/models/identity.py`
- `backend/app/db/repositories/identity.py`
- `backend/app/main.py`, `backend/app/core/config.py`
- `backend/migrations/versions/0003_identity_auth_boundary.py`
- `backend/tests/**`
- `pyproject.toml`, `uv.lock`

## API 영향

공개 endpoint나 response field를 추가하지 않는다. 후속 보호 endpoint가 재사용할
`get_current_user` dependency를 추가하며 기존 공통 오류 envelope와 승인된 인증 오류 code를 사용한다.

## DB·마이그레이션 영향

`users`와 `user_identities`를 추가한다. 상태·provider·premium machine code는 문자열 CHECK로
검증하고 `code_set_version`을 저장한다. active provider identity와 Firebase subject에는 partial unique
index를 둔다. downgrade는 이번 revision이 만든 두 테이블만 제거한다.

## 안전·개인정보·보안 영향

- ID Token은 검증에만 사용하고 저장하거나 로그에 남기지 않는다.
- Firebase subject는 identity 연결에 필요한 최소 직접 식별자로 DB에만 저장하고 API에 노출하지 않는다.
- 이메일과 전체 이름은 decoded claim에서 읽거나 저장하지 않는다.
- Firebase 장애와 잘못된 token을 분리하여 장애 시 fail-closed 한다.
- Firebase 검증은 integration adapter 뒤에 두어 SDK 예외와 credential 세부정보를 외부에 노출하지 않는다.

## 선행 관계와 차단 요소

- 시작 Alembic head는 최신 `develop`의 `0002_catalog_core`이다.
- Firebase project ID와 Application Default Credentials는 배포 secret으로 제공되어야 한다.
- 설정이 없으면 서버는 기동할 수 있지만 보호 endpoint 인증은 503으로 닫힌다.

## 테스트 계획

- identity service: 최초 생성, 반복 로그인, 비활성 차단, verifier 오류
- Firebase adapter: decoded subject 추출과 SDK 예외의 안전한 변환
- API dependency: Bearer 누락·잘못된 token·provider 장애·비활성 계정 오류 envelope
- PostgreSQL: 실제 생성·멱등성·CHECK/partial unique index·migration round trip
- ruff, mypy, 전체 pytest

## 수동 확인

1. 테스트 Firebase project ID와 ADC를 환경 변수로 설정한다.
2. 보호 endpoint에 Firebase ID Token을 Bearer로 전달한다.
3. 첫 요청 후 `users`, `user_identities`가 각각 한 행 생성되는지 확인한다.
4. 같은 token으로 재요청 후 user UUID와 행 수가 유지되는지 확인한다.
5. 사용자를 DISABLED로 바꾸고 `403 ACCOUNT_DISABLED`를 확인한다.

## 알려진 제한과 후속 작업

- 실제 공개 보호 endpoint는 `/me` 또는 온보딩 Wave에서 연결한다.
- Google/Kakao/Naver provider identity 연결과 custom token 교환은 별도 작업이다.
- 휴면·삭제 lifecycle과 premium 전환 정책은 별도 승인 후 구현한다.
