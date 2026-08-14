# TASK-BACKEND-006: KAKAO 소셜 OAuth adapter와 identity 연결

- Primary owner: 백엔드 담당
- Reviewers: 프론트엔드 담당, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `F010-1-2`, `F010-1-4`, `F010-1-5`
- 관련 ADR: `ADR-0003`, `ADR-0008`, `ADR-0009`
- 목표 브랜치: `feat/kakao-auth-adapter`

## 배경과 사용자 가치

사용자가 KAKAO 인증을 선택하면 서버가 발급한 일회용 state·nonce와 PKCE를 검증하고, 최소
식별자인 KAKAO app-scoped subject만 내부 계정에 연결해야 한다. 최종 서비스 권한은 기존 Firebase
ID Token으로 유지하고 provider token과 불필요한 개인정보는 저장하지 않는다.

## 포함 범위

- `POST /api/v1/auth/social/KAKAO/authorize-init`
- `POST /api/v1/auth/social/KAKAO/exchange`
- KAKAO authorization/token/OIDC/JWKS integration adapter와 unavailable stub
- Firebase custom token 발급 port·adapter
- state·nonce 600초 single-use 저장소와 PostgreSQL fixed-window rate limit
- KAKAO identity transaction, uniqueness, 멱등 재연결과 자동 병합 차단
- ADR-0008 provider revocation port를 구현하는 KAKAO unlink adapter
- 설정 schema와 `.env.example`, SQLAlchemy model, repository, Alembic `0013_` migration
- unit·API·PostgreSQL integration·migration·privacy regression test

## 제외 범위

- NAVER·Google adapter
- 명시적 계정 연결·병합 API
- email·이름·닉네임·전화번호·생일·프로필 이미지 scope와 저장
- provider access/refresh token 저장과 refresh flow
- Redis, Celery, scheduler, 범용 OAuth framework
- frontend 로그인 화면과 KAKAO 앱 등록·심사
- 실제 secret 값과 credential 파일

## 인수 조건

1. `authorize-init`은 KAKAO, 등록된 redirect URI와 유효한 S256 challenge만 허용한다.
2. 서버는 독립적인 CSPRNG state·nonce와 600초 만료 authorization URL을 반환하고 DB에는 원문이
   아닌 SHA-256만 저장한다.
3. 정상 exchange는 state·redirect URI·PKCE verifier를 검증하고 state row를 transaction에서 한 번만
   소비한다.
4. 600초 경계 전 요청은 허용하고 경계 이후는 `422 OAUTH_STATE_EXPIRED`, 불일치·재사용은
   `422 INVALID_OAUTH_STATE`다.
5. OIDC ID token의 RS256 서명, kid/JWKS, issuer, audience, expiry와 nonce를 모두 검증한다.
6. 검증된 `sub`만 identity service에 전달하며 subject 누락·빈 값·비정상 schema는 실패한다.
7. KAKAO subject의 최초 로그인은 ACTIVE user와 KAKAO identity를
   `identity-social-v1`로 한 transaction에서 만들고 Firebase custom token을 반환한다.
8. 동일 subject 반복 로그인은 같은 user·firebase subject를 사용하며 중복 row를 만들지 않는다.
9. 다른 사용자에 연결된 subject는 자동 병합하지 않고 충돌로 처리한다.
10. DB 실패는 user·identity를 모두 rollback하고 성공 응답이나 부분 저장을 남기지 않는다.
11. KAKAO `code_verifier`는 required이며 S256 불일치는 provider 호출 전에 거부한다.
12. KAKAO `KOE320`은 `409 AUTHORIZATION_CODE_REUSED`, timeout·transport·일시 오류·5xx는
    `503 PROVIDER_UNAVAILABLE`로 안정적으로 매핑한다.
13. IP 10회/분, `(KAKAO, redirect_uri)` 60회/시간 제한을 PostgreSQL에서 원자적으로 적용하고
    초과 요청은 provider를 호출하지 않고 `429 RATE_LIMITED`를 반환한다.
14. rate-limit key는 운영 secret HMAC-SHA256 digest만 저장하고 IP·redirect URI 원문을 저장하지 않는다.
15. KAKAO unlink는 ADR-0008 provider revocation port를 재사용하고 성공·이미 해제를 멱등 성공,
    timeout·4xx·5xx를 기존 retry/final-failure 경계로 전달한다.
16. authorization code, access/refresh/ID/custom token, state·nonce 원문, provider 전체 응답,
    email·이름·프로필 정보는 DB·cache·로그·오류·fixture에 없다.
17. 저장 transaction 완료 전에는 성공 응답을 반환하지 않는다.
18. KAKAO 설정이 없거나 disabled이면 애플리케이션은 기동하지만 두 social endpoint는
    `503 PROVIDER_UNAVAILABLE`로 fail-closed한다.
19. 기존 Firebase ID Token 인증·첫 사용자 생성·계정 삭제 접근 차단은 회귀하지 않는다.
20. migration은 `identity-mvp-v1`을 변경하지 않고 `identity-social-v1`과 KAKAO CHECK만 추가하며
    PostgreSQL upgrade/downgrade round trip을 통과한다.

## 변경 예상 파일

- `backend/app/core/config.py`, `backend/.env.example`
- `backend/app/modules/identity/codes.py`, `ports.py`, `schemas.py`, `service.py`
- `backend/app/api/v1/auth_social.py`, `backend/app/api/v1/router.py`
- `backend/app/integrations/kakao_oauth.py`, Firebase custom-token adapter 경계
- `backend/app/db/models/identity.py`
- `backend/app/db/repositories/identity.py`, social OAuth state/rate-limit repository
- `backend/migrations/versions/0013_social_identity.py`
- `backend/tests/unit/test_kakao_oauth.py`, identity service unit tests
- `backend/tests/api/test_auth_social.py`
- `backend/tests/integration/test_social_identity_repository.py`
- `backend/tests/integration/test_migrations.py`

실제 저장소 패턴을 재사용하고 route·domain·repository·integration 경계를 중복 추상화하지 않는다.

## API 영향

- 비인증 `authorize-init` endpoint를 추가한다.
- 기존 exchange request shape를 유지하면서 KAKAO의 `code_verifier`를 조건부 필수화한다.
- `429 RATE_LIMITED`, `422 INVALID_OAUTH_STATE`, `422 OAUTH_STATE_EXPIRED`,
  `503 PROVIDER_UNAVAILABLE`을 공통 오류 계약에 추가한다.
- provider subject, Firebase subject, provider payload와 token은 공개하지 않는다.
- 공개 API 변경은 프론트엔드·백엔드·개발팀장 승인 전 구현하지 않는다.

## DB·마이그레이션 영향

- transient `social_oauth_authorization_requests`와 `social_oauth_rate_limit_windows`를 추가한다.
- state·nonce·rate-limit key는 digest만 저장하며 TTL 이후 요청 시 논리 삭제한다.
- `users`와 `user_identities` CHECK에 `identity-social-v1`을 추가하고 해당 version에서 KAKAO를 허용한다.
- 기존 `identity-mvp-v1` row와 FIREBASE identity는 rewrite하지 않는다.
- unique, CHECK, timestamptz와 원자적 counter update를 PostgreSQL integration test로 검증한다.

## 안전·개인정보·보안 영향

- 비인증 endpoint abuse를 이중 rate limit으로 제한한다.
- state·nonce·code·token과 provider 원본 응답을 로그·metric label·DB에 남기지 않는다.
- 개인정보 scope 자체를 요청하지 않고 OIDC `sub`만 소비한다.
- client secret, Admin key, Firebase credential과 rate-limit digest key는 secret manager 경계에 둔다.
- arbitrary forwarding header를 신뢰하지 않고 production trusted-proxy 설정을 수동 검증한다.

## 선행 관계와 차단 요소

- 선행: ADR-0009 `ACCEPTED`, API/DB/개인정보 문서 PR 승인
- KAKAO test app에 Login·OIDC·client secret 활성화와 정확한 redirect URI 등록 필요
- production unlink에는 Admin key secret 주입 필요
- 공식 PKCE parameter 표 공백은 KAKAO test app 검증 전 production enablement 차단 요소

## 테스트 계획

- unit: 정상 token/OIDC 검증, issuer·audience·expiry·signature·nonce 오류, PKCE S256,
  timeout·4xx·5xx·schema 오류, unlink 성공·실패·반복
- service: state 발급·600초 경계·소비·재사용, 동일 subject 멱등성, subject 충돌, DB rollback
- API: init/exchange schema, 429, 409, 422, 503와 공통 오류 envelope
- integration: PostgreSQL digest row, fixed-window 동시 증가, identity unique, rollback, FK 삭제 순서
- migration: `upgrade head -> downgrade 0012 -> upgrade head`
- privacy: caplog·응답·fixture·DB row에 code, token, raw state/nonce, PII, provider raw response 없음
- regression: 기존 Firebase 인증, deletion-pending 접근 차단과 account-deletion provider port
- `uv run ruff format --check backend data/scripts`, `uv run ruff check backend data/scripts`,
  `uv run mypy`, 관련 테스트와 전체 `uv run pytest`

## 수동 확인

1. KAKAO test app에 REST redirect URI, OIDC와 client secret을 활성화한다.
2. 실제 secret은 secret manager 또는 로컬 비추적 환경 변수로만 주입한다.
3. init authorization URL에 state·nonce·S256 challenge가 있고 개인정보 scope가 없는지 확인한다.
4. 실제 KAKAO authorization code를 한 번 교환해 Firebase custom token을 받는다.
5. custom token을 Firebase ID Token으로 교환해 기존 보호 API에서 같은 내부 user가 조회되는지 확인한다.
6. code/state 재사용, 600초 만료, provider 장애와 rate-limit 경계를 확인한다.
7. 계정 삭제 job에서 KAKAO unlink 성공·실패·재시도를 확인한다.
8. 로그·DB dump·오류 응답에 token, PII, raw state/nonce/provider 응답이 없는지 확인한다.

## 알려진 제한과 후속 작업

- KAKAO 공식 문서는 authorization-code 숫자 TTL과 token rate-limit 수치를 공개하지 않는다.
- discovery는 PKCE S256을 명시하지만 parameter 표의 상세는 test app에서 추가 검증해야 한다.
- 실제 redirect URI, trusted proxy, secret-manager 경로와 앱 심사는 운영 환경별 설정이다.
- NAVER와 명시적 계정 연결·병합은 별도 작업이다.
