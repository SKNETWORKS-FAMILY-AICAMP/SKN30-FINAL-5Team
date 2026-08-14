# ADR-0009: KAKAO 소셜 OAuth 교환과 최소 identity 연결

- 상태: PROPOSED
- 날짜: 2026-08-14
- 소유자: 백엔드 담당
- 승인자: 프론트엔드 담당, 백엔드 담당, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항/이슈: `F010-1-2`, `F010-1-4`, `F010-1-5`, Wave 9B
- 정책 버전: `identity-social-v1`

## 배경

기존 계약은 Kakao/Naver authorization code를 백엔드 adapter가 검증하고 Firebase custom
token으로 교환한다고 정했지만, 서버가 검증할 state와 nonce를 발급하는 API가 없었다. 비인증
교환 endpoint의 rate limit, state/nonce 만료, KAKAO OIDC·PKCE 검증, provider 오류 매핑도
확정되지 않았다. state를 서버가 발급하지 않으면 CSRF·재생 방지 검증을 신뢰할 수 없고,
provider 응답이나 토큰을 저장하면 개인정보 최소화 원칙을 위반한다.

## 결정

### provider와 최종 권한

- 이 증분의 provider는 `KAKAO` 하나다. `NAVER`는 별도 브랜치·ADR 증분으로 구현한다.
- 클라이언트의 최종 세션 권한은 기존과 동일하게 Firebase ID Token이다.
- KAKAO authorization code는 백엔드 adapter가 토큰 endpoint에서 교환하고 OIDC ID token을
  검증한다. 검증된 `sub`만 identity service에 전달한다.
- KAKAO 이메일·이름·닉네임·전화번호·생일·프로필 이미지를 scope로 요청하거나 읽거나 저장하지
  않는다. OIDC를 활성화하고 추가 개인정보 scope 없이 ID token의 `sub`만 사용한다.

### 공식 provider 계약

2026-08-14에 KAKAO 공식 개발자 문서를 확인했다.

- issuer: `https://kauth.kakao.com`
- authorization endpoint: `https://kauth.kakao.com/oauth/authorize`
- token endpoint: `https://kauth.kakao.com/oauth/token`
- discovery: `https://kauth.kakao.com/.well-known/openid-configuration`
- JWKS: `https://kauth.kakao.com/.well-known/jwks.json`
- ID token: RS256, `iss`·`aud`·`exp`·`nonce`와 서명 검증 필수
- PKCE: discovery의 `code_challenge_methods_supported`가 `S256`만 허용
- subject: app-scoped service user ID인 ID token `sub`; 공식 문서의 원천 타입은 `Long`이고
  OIDC claim은 `String`이며 별도 최대 문자열 길이는 공개되지 않음
- unlink: `POST https://kapi.kakao.com/v1/user/unlink`
- redirect URI: 사전 등록·정확 일치, HTTP/HTTPS만 허용, 기본 최대 10개, 임의 path parameter 금지

공식 출처:

- [Kakao Login REST API](https://developers.kakao.com/docs/en/kakaologin/rest-api)
- [Kakao Login 활용하기](https://developers.kakao.com/docs/ko/kakaologin/utilize)
- [Kakao Login 설정하기](https://developers.kakao.com/docs/ko/kakaologin/prerequisite)
- [Kakao 앱 Redirect URI 설정](https://developers.kakao.com/docs/ko/app-setting/app#platform-key-redirect-uri)
- [Kakao Login 오류 코드](https://developers.kakao.com/docs/en/kakaologin/trouble-shooting)

### authorize-init

새 비인증 endpoint를 추가한다.

```http
POST /api/v1/auth/social/{provider_code}/authorize-init
```

- 현재 `provider_code`는 `KAKAO`만 허용한다.
- 클라이언트는 등록된 `redirect_uri`, PKCE `code_challenge`, 고정값 `S256`을 보낸다.
- 서버는 CSPRNG로 독립적인 state와 nonce를 발급하고 만료 시각과 KAKAO authorization URL을
  반환한다. URL에는 state, nonce, PKCE challenge를 포함하고 개인정보 scope는 포함하지 않는다.
- state·nonce 원문은 응답 후 서버 메모리, 로그, DB에 남기지 않는다.
- PostgreSQL에는 state·nonce SHA-256, redirect URI SHA-256, PKCE challenge, provider code,
  생성·만료 시각만 저장한다.
- TTL은 정확히 600초다. 만료된 요청은 `422 OAUTH_STATE_EXPIRED`, 일치하지 않거나 이미 소비된
  요청은 `422 INVALID_OAUTH_STATE`다.
- 정상 교환에서 state 검증과 row 삭제는 하나의 transaction으로 수행한다. single-use row는
  provider 호출 전 소비하며 외부 실패 시 되살리지 않는다. 사용자는 새 init부터 다시 시작한다.

### PKCE와 nonce

- 클라이언트가 RFC 7636 verifier를 생성하고 `authorize-init`에는 S256 challenge를,
  `exchange`에는 원문 verifier를 전달한다.
- KAKAO 교환의 `code_verifier`는 필수다. 기존 nullable 공개 필드는 삭제하지 않고 KAKAO에 대한
  조건부 필수 검증으로 좁힌다.
- 서버는 verifier의 S256 결과를 저장된 challenge와 constant-time 비교한다.
- KAKAO OIDC가 nonce를 지원하므로 ID token `nonce`는 저장된 nonce SHA-256과 반드시 일치해야 한다.
- issuer, audience, expiry, algorithm, kid와 JWKS 서명 검증 중 하나라도 실패하면 identity를 만들지
  않는다. JWKS는 process-local bounded cache만 허용하고 Redis를 추가하지 않는다.

### rate limit

두 fixed-window 제한을 PostgreSQL에서 원자적으로 증가시킨다.

- 요청 IP 기준: 10회/60초
- `(provider_code, redirect_uri)` 기준: 60회/3600초

모든 `authorize-init`과 `exchange` 요청에 두 제한을 적용한다. IP와 redirect URI 원문은 rate-limit
테이블에 저장하지 않는다. 운영 secret을 사용하는 HMAC-SHA256 keyed digest만 저장하고 window가
끝나면 요청 시 논리 삭제한다. 임의의 `X-Forwarded-For`를 신뢰하지 않고 승인된 reverse proxy가
설정한 client address만 사용한다. 초과 응답은 공통 오류 envelope의 `429 RATE_LIMITED`이며
provider를 호출하지 않는다.

### authorization code와 provider 오류

- authorization code, access token, refresh token, ID token, Firebase custom token은 로그·오류·DB·
  cache에 저장하지 않는다.
- KAKAO는 재사용·만료·미존재 authorization code를 모두 `KOE320 invalid_grant`로 반환하며 공식
  문서에 숫자 code TTL을 공개하지 않는다. 정보 노출 없이 fail-closed하기 위해 이 응답을
  `409 AUTHORIZATION_CODE_REUSED`로 안정적으로 매핑한다.
- provider timeout, transport 오류, `KOE003`, 5xx와 검증용 JWKS 장애는
  `503 PROVIDER_UNAVAILABLE`로 매핑한다.
- 잘못된 issuer·audience·서명·expiry·nonce, subject 누락과 schema 오류는 민감한 provider
  payload 없이 `401 INVALID_TOKEN`으로 매핑한다.

### identity transaction과 자동 병합 금지

- 검증된 KAKAO `sub`에 대해 provider별 lock과 활성
  `(provider_code, provider_subject)` unique를 적용한다.
- 같은 KAKAO subject의 반복 로그인은 같은 내부 user UUID와 firebase subject를 사용한다.
- 다른 사용자에 이미 연결된 subject는 `409 INVALID_STATE_TRANSITION`으로 실패하며 자동 병합하지
  않는다. 이메일은 수집하지 않으므로 병합 근거로 사용할 수 없다.
- 최초 KAKAO 로그인은 `users`와 KAKAO `user_identities`를 하나의 transaction에서 생성한다.
  두 row의 code-set version은 `identity-social-v1`이다. 기존 `identity-mvp-v1` row는 변경하지 않는다.
- DB commit 후에만 Firebase custom token을 만들고 성공 응답한다. DB 실패는 전부 rollback하며,
  custom token 발급 실패 시 저장된 identity를 삭제하거나 성공으로 응답하지 않는다.

### account deletion 연결 해제

- ADR-0008의 provider revocation port와 상태 코드를 재사용한다.
- provider token을 저장하지 않으므로 KAKAO Admin key와 검증·저장된 service user ID를 사용해
  unlink한다. Admin key는 client secret과 함께 개발팀장·운영 담당이 secret manager에서 관리한다.
- unlink 성공, 이미 연결되지 않음은 멱등 성공으로 처리한다. timeout·4xx·5xx는 기존 계정 삭제
  retry/final-failure 상태로 매핑하며 raw provider 오류를 저장하지 않는다.

### 공개 오류 코드

- `429 RATE_LIMITED`
- `422 INVALID_OAUTH_STATE`
- `422 OAUTH_STATE_EXPIRED`
- `503 PROVIDER_UNAVAILABLE`
- `409 AUTHORIZATION_CODE_REUSED` 유지

## 결정 이유

서버 발급 single-use state와 nonce는 클라이언트가 임의로 만든 값보다 검증 가능한 CSRF·replay
경계를 제공한다. PostgreSQL fixed-window는 현재 배포 단위에 Redis를 추가하지 않고도 동시 요청을
원자적으로 제한한다. OIDC `sub`만 사용하면 추가 userinfo 호출과 개인정보 scope가 필요 없다.
최종 권한을 Firebase로 유지하면 기존 보호 API 인증 경계를 바꾸지 않는다.

## 검토한 대안

- 클라이언트가 state와 nonce를 임의 발급
- state와 nonce 원문 또는 provider 전체 응답 저장
- provider access token을 보관해 unlink에 사용
- 이메일 기반 기존 계정 자동 병합
- Redis rate limiter 또는 공통 OAuth framework 도입
- KAKAO OIDC를 끄고 userinfo API에서 subject 조회

## 선택하지 않은 대안과 이유

- 클라이언트 단독 state는 서버가 발급·수명·single-use를 증명할 수 없다.
- 원문과 provider 응답 저장은 재생·개인정보 노출 범위를 늘린다.
- token 보관은 제품 계약에 필요하지 않고 삭제·침해 위험을 증가시킨다.
- 이메일은 요청하지 않으며 변경 가능하므로 병합 근거가 아니다.
- Redis와 범용 OAuth framework는 단일 provider MVP에 불필요한 운영·의존성 비용이다.
- OIDC `sub` 검증은 userinfo 전체 응답보다 수집 범위가 작고 nonce 검증을 제공한다.

## 결과와 영향

공개 API 두 개와 PostgreSQL transient authorization/rate-limit 모델, KAKAO identity CHECK가 필요하다.
기존 Firebase Bearer 인증과 `identity-mvp-v1` row는 유지된다. frontend는 init 응답의 authorization
URL로 이동하고 state·nonce·PKCE verifier를 600초 동안만 로컬 보관해야 한다.

## 보안·개인정보·호환성 영향

비인증 endpoint에는 abuse·enumeration·token 유출 위험이 있다. rate-limit digest key, KAKAO client
secret, Admin key와 Firebase credential은 secret manager에 두고 source·fixture·DB·로그에 저장하지
않는다. 오류는 allowlist machine code만 반환한다. 공개 `code_verifier` 필드는 삭제하지 않고 KAKAO에
대해서만 필수화하므로 schema 형태는 호환되지만 기존 KAKAO 호출자는 init 선행과 PKCE가 필요하다.

## 아직 확정되지 않은 사항

- staging·production에 등록할 정확한 redirect URI 값과 KAKAO 앱 심사 완료 시각
- KAKAO 앱에서 OIDC·client secret 활성화 및 Admin key의 실제 secret-manager 경로
- 공식 문서가 discovery에는 PKCE S256을 노출하지만 authorization/token parameter 표에는 관련
  필드를 별도 기재하지 않은 문서 공백의 production test-project 검증
- KAKAO가 공개하지 않은 authorization-code 숫자 TTL과 token 발급 rate-limit 수치
- 배포 reverse proxy의 신뢰 가능한 client IP 전달 설정

## 후속 작업

1. 필수 승인자가 본 ADR과 API·DB 계약을 검토하고 승인 증적을 남긴다.
2. ADR 상태가 `ACCEPTED`가 된 뒤 backend owner가 TASK-BACKEND-006을 구현한다.
3. 운영 담당이 KAKAO test app에서 OIDC·PKCE·redirect·unlink를 수동 검증한다.
4. NAVER는 별도 ADR·브랜치·PR로 추가한다.
