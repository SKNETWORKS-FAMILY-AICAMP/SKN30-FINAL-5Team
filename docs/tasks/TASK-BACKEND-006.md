# TASK-BACKEND-006: KAKAO 소셜 OAuth adapter와 identity 연결

- Primary owner: 백엔드 담당
- Reviewers: 프론트엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `F010-1-1`~`F010-1-5`, `F025-1-1`, `NFR-004`, `NFR-005`
- 관련 ADR: ADR-0003, ADR-0008, ADR-0009
- 선행 게이트: ADR-0009 `ACCEPTED`
- 목표 브랜치: `feat/kakao-auth-adapter`
- code-set: 신규 `identity-social-v1`; 기존 `identity-mvp-v1` 유지

## 포함 범위

- `POST /api/v1/auth/social/KAKAO/authorize-init`와 `/exchange`
- Kakao authorization/token/OIDC/JWKS adapter와 unavailable stub
- Firebase custom-token port/adapter
- PostgreSQL state/nonce 600초 single-use와 fixed-window rate limit
- KAKAO identity transaction, uniqueness, 반복 로그인, 자동 병합 차단
- ADR-0008 provider revocation port를 구현하는 Kakao unlink adapter
- 설정 schema와 `.env.example`, SQLAlchemy model/repository, additive `0013` migration
- OpenAPI/frontend mock, unit/API/PostgreSQL/migration/privacy tests와 운영 runbook

Google 직접 OAuth, Naver adapter, 명시적 account-link/merge API, profile scope, provider token 저장,
Redis/Celery/scheduler/범용 OAuth framework, 실제 secret과 앱 등록은 제외한다.

## 인수 조건

1. authorize-init은 KAKAO, 정확히 등록된 redirect URI와 유효한 S256 challenge만 허용한다.
2. server는 독립 CSPRNG state·nonce와 600초 만료 URL을 반환하고 DB에는 UUID, provider,
   state·nonce·redirect URI SHA-256, challenge와 시각만 저장한다.
3. raw state/nonce/verifier/code/token은 DB, cache, log, metric, trace, fixture, 오류에 없다.
4. exchange transaction은 state·redirect URI·client nonce·expiry·S256 verifier를 검증하고 provider
   호출 전에 row를 삭제·commit한다. 외부 호출 중 DB lock을 유지하지 않고 실패 시 row를 되살리지 않는다.
5. 600초 경계 전은 허용하고 경계 도달은 `422 OAUTH_STATE_EXPIRED`; 불일치·소비 row 없음은
   `422 INVALID_OAUTH_STATE`다.
6. client가 반환한 nonce와 ID token nonce를 모두 저장 digest와 constant-time 비교한다.
7. KAKAO OIDC의 RS256 signature, kid/JWKS, issuer, audience, expiry, nonce와 non-empty sub를 검증한다.
8. `openid`만 요청하고 email/name/nickname/phone/birthday/profile scope·claim을 읽거나 저장하지 않는다.
9. 검증된 opaque sub만 identity service에 전달한다. subject를 변환·대체하지 않는다.
10. 최초 KAKAO subject는 별도 ACTIVE user와 identity를 `identity-social-v1`로 한 transaction에서 만든다.
11. 같은 subject 반복 로그인은 동일 user/Firebase principal/identity를 재사용하고 중복 row를 만들지 않는다.
12. 다른 user에 연결된 subject는 `409 IDENTITY_ALREADY_LINKED`; 자동 병합·암묵적 현재-user 연결은 없다.
13. user/identity DB 실패는 rollback하고 custom token을 만들지 않는다. custom-token 실패는 성공 응답하지
    않으며 다음 로그인에서 commit된 identity를 멱등 재사용한다.
14. KAKAO `code_verifier`는 기존 nullable shape를 유지하되 조건부 필수다.
15. `KOE320 invalid_grant`은 `409 AUTHORIZATION_CODE_REUSED`; timeout/transport/일시 오류/5xx/JWKS
    장애는 `503 PROVIDER_UNAVAILABLE`이다. 원본 provider payload는 비노출이다.
16. authorize-init과 exchange 모두 canonical IP 10회/60초 및 `(KAKAO, registered_redirect_uri)`
    60회/3600초 PostgreSQL fixed window를 원자 적용하고 초과 시 provider를 호출하지 않는다.
17. rate-limit row는 운영 secret HMAC-SHA256만 저장하고 raw IP/URI는 저장하지 않는다. 신뢰 proxy가
    설정한 client address 외 임의 forwarding header를 신뢰하지 않는다.
18. access/refresh/ID/Firebase custom token을 영구 저장하는 column이나 cache를 만들지 않는다.
19. KAKAO unlink는 ADR-0008 port/checkpoint와 기존 삭제 상태만 사용한다. 성공·이미 해제는 멱등 성공,
    실패는 기존 7일 retry/final-failure 경계로 전달한다.
20. migration은 기존 `identity-mvp-v1` row를 rewrite하지 않고 `identity-social-v1`과 KAKAO CHECK,
    transient authorization/rate-limit model을 additive하게 추가한다.
21. KAKAO 설정이 없거나 disabled이면 app은 기동하지만 social endpoint는 `503 PROVIDER_UNAVAILABLE`이다.
22. 기존 Firebase 인증, CurrentUser, deletion-pending 접근 차단과 account deletion이 회귀하지 않는다.
23. client secret/Admin key/Firebase credential/HMAC key는 secret manager에서만 로드하고 local/CI는 stub을 쓴다.
24. 정책 변경은 policy version, ADR, golden/security test를 함께 갱신한다.

## 필수 테스트

- invalid/expired/consumed state, invalid nonce/PKCE, authorization code `KOE320`
- issuer/audience/signature/expiry 불일치와 subject 누락
- provider timeout/5xx/JWKS 장애의 안전한 503
- rate limit 10/11·60/61 경계, window reset과 concurrent counter
- 첫 로그인, 반복 로그인, concurrent subject uniqueness, 다른-user 충돌, 자동 merge 금지
- flow consume transaction, provider 호출 중 DB lock 없음, identity DB rollback, custom-token 실패 재로그인
- account deletion unlink 성공·이미 해제·실패·반복 호출·retry checkpoint
- token/email/name/provider raw response와 raw IP/URI 비노출
- PostgreSQL integration, Alembic `upgrade head -> downgrade 0012 -> upgrade head`
- ruff format/check, mypy, 관련/전체 pytest, OpenAPI compatibility

## 변경 예상 파일

- `backend/app/core/config.py`, `backend/.env.example`
- `backend/app/modules/identity/codes.py`, `ports.py`, `schemas.py`, `service.py`
- `backend/app/api/v1/auth_social.py`, `backend/app/api/v1/router.py`
- `backend/app/integrations/kakao_oauth.py`, Firebase custom-token adapter
- `backend/app/db/models/identity.py`, 관련 repository
- `backend/migrations/versions/0013_social_identity.py`
- unit/API/integration/migration/privacy tests와 OpenAPI/frontend mock

실제 저장소 패턴을 재사용하고 두 번째 provider 요구 전 범용 base class를 만들지 않는다.

## 구현 전 실환경 확인

- ADR-0009가 모든 필수 reviewer 확인 후 `ACCEPTED`인지
- Kakao test app Login/OIDC/client secret, REST/Admin key와 정확한 redirect URI가 준비됐는지
- secret-manager 경로와 trusted proxy client IP 전달 설정이 정해졌는지
- 공식 parameter 표의 PKCE 공백과 미공개 code TTL을 test app에서 확인했는지
- frontend가 state·nonce·verifier를 600초 동안만 보관하고 callback에서 반환하는지

하나라도 미확정이면 실제 route/adapter/migration/credential 작업을 시작하지 않는다.
