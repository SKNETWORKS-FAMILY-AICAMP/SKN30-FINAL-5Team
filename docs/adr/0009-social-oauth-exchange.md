# ADR-0009: KAKAO 소셜 OAuth 교환과 provider 경계

- 상태: PROPOSED
- 날짜: 2026-08-14
- 소유자: 개발팀장
- 승인자: 프론트엔드, 백엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `F010-1-1`~`F010-1-5`, `F025-1-1`, `NFR-004`, `NFR-005`, Wave 9B
- 정책 버전: `auth-provider-policy-v1`
- 신규 code-set: `identity-social-v1` (`identity-mvp-v1`은 변경하지 않음)

## 구현 게이트

이 ADR은 공통 계약 제안이다. 필수 승인자가 확인해 상태를 `ACCEPTED`로 변경하기 전에는 API route,
provider HTTP adapter, repository, `0013` migration과 credential 등록을 구현하지 않는다. 승인 전에는
문서, 결정적 domain rule과 contract/golden/security test만 허용한다.

## 현재 경계

FastAPI의 최종 세션 권한은 Firebase ID Token이다. verifier는 Firebase UID만 `CurrentUserService`로
전달하고 email 등 profile claim을 폐기한다. 현재 `user_identities`는 `FIREBASE`와
`identity-mvp-v1`만 허용하며 Firebase subject와 provider identity가 한 row에 결합돼 있다. KAKAO
subject 추가는 기존 row를 rewrite하지 않는 additive migration이어야 한다.

frontend에는 실제 로그인 흐름이 없고 provider 환경 변수 자리만 있다. 저장소에서 출시 국가, 실제
Kakao 앱과 credential 확보 여부는 확인되지 않았다. F010의 Google/Kakao/Naver MVP 범위는 유지하며
아래 결정은 구현 순서다.

## provider 비교와 선택

| 기준 | Google | Kakao | Naver |
|---|---|---|---|
| 권장 경로 | Firebase 기본 provider | backend authorization code + OIDC + Firebase custom token | backend authorization code + OIDC + Firebase custom token |
| Firebase 중복 | 높음 | 낮음 | 낮음 |
| 최소 scope | Firebase 결과에서 UID만 소비 | `openid`만 | `openid`만 |
| state/nonce/PKCE | Firebase SDK 관리 | state·nonce·PKCE S256 | state·PKCE S256; 공식 문서에서 nonce 미확인 |
| 연결 해제 | Firebase Admin/SDK 경계 | Admin key + subject unlink | 사용자 token revoke + disconnect callback |
| 출시 전 확인 | Firebase/Google console | Kakao 앱·REST key·redirect URI·OIDC | 앱 공개 검수·redirect URI·revoke 운영 |
| 운영 복잡도 | 낮음 | 중간 | 높음 |

첫 직접 OAuth 구현 provider는 **KAKAO**다. backend가 authorization code를 교환하고 OIDC ID token을
검증한 뒤 Firebase custom token을 발급한다. 이는 대한민국 대상 사용자라는 제품 가정과 Firebase와
중복되지 않는 adapter 경계를 먼저 검증하기 위한 순서이며, 출시 국가와 credential은 승인 전에 확인한다.
Google은 기존 Firebase 경로만 사용하고 backend 직접 OAuth를 중복 구현하지 않는다. Naver는 Kakao
수직 슬라이스 안정화, 앱 공개 검수와 token revoke 운영 계약 승인 뒤 두 번째 직접 adapter로 도입한다.

## Kakao 공식 계약

2026-08-14에 Kakao 공식 문서를 확인했다.

- issuer `https://kauth.kakao.com`, ID token RS256
- authorization `https://kauth.kakao.com/oauth/authorize`, token `https://kauth.kakao.com/oauth/token`
- discovery `https://kauth.kakao.com/.well-known/openid-configuration`, JWKS 공개
- `iss`, `aud`, `exp`, `nonce`, 서명과 non-empty `sub` 검증 필수
- discovery가 PKCE `S256`을 제공
- redirect URI는 사전 등록 값과 정확히 일치
- subject는 app-scoped service user ID이며 OIDC claim은 String; 공식 최대 길이는 공개되지 않음
- subject 기반 unlink 지원

## authorization flow

`POST /api/v1/auth/social/{provider_code}/authorize-init`는 Firebase 인증 전에 호출한다. 현재
`provider_code`는 KAKAO만 허용한다. client는 등록된 `redirect_uri`와 client-generated PKCE S256
challenge를 보내고 server는 CSPRNG로 독립 state·nonce를 발급해 authorization URL, state, nonce와
600초 만료 시각을 반환한다. client는 callback 완료까지만 state·nonce·verifier를 보관한다.

PostgreSQL transient row에는 UUID, provider code, state·nonce·redirect URI SHA-256, PKCE challenge,
생성·만료 시각만 저장한다. raw state·nonce·verifier·authorization code·token은 DB, cache, 로그에
저장하지 않는다. exchange transaction은 row를 잠그고 state, redirect URI, client-returned nonce,
expiry와 S256 verifier를 검증한 뒤 provider 호출 전에 row를 삭제하고 commit한다. provider 호출 중
DB lock을 유지하지 않으며 외부 또는 후속 DB 실패에도 row를 되살리지 않고 새 init부터 시작한다.

provider 교환 후 ID token nonce도 직전에 검증한 nonce digest와 constant-time 비교한다. KAKAO의
만료·재사용·미존재 authorization code `KOE320 invalid_grant`은 원본 설명 없이
`409 AUTHORIZATION_CODE_REUSED`로 fail closed 매핑한다. 공식 문서는 authorization-code 숫자 TTL을
공개하지 않으므로 600초는 우리 authorization request 상한이며 provider TTL로 추정하지 않는다.

access/refresh/ID token과 Firebase custom token은 요청 메모리에서만 사용하고 즉시 폐기한다. 현재
제품에는 provider token을 영구 저장해야 하는 기능이 없다.

## abuse control과 오류

authorize-init과 exchange 모두 PostgreSQL fixed window를 적용한다.

- canonical client IP 10회/60초
- `(provider_code, registered_redirect_uri)` 60회/3600초

신뢰 proxy가 설정한 client address만 forwarded 값으로 인정하고 그 외에는 socket peer를 사용한다.
DB에는 운영 secret HMAC-SHA256 key와 window/count/expiry만 저장하며 raw IP/URI는 저장하지 않는다.
window 종료 뒤 요청 시 논리 삭제한다.

| HTTP | code | 의미 |
|---|---|---|
| 422 | `INVALID_OAUTH_STATE` | state/nonce/redirect/PKCE 불일치 또는 이미 소비된 request |
| 422 | `OAUTH_STATE_EXPIRED` | row가 존재하고 600초 경계에 도달 |
| 409 | `AUTHORIZATION_CODE_REUSED` | Kakao `KOE320 invalid_grant` fail-closed 매핑 |
| 409 | `IDENTITY_ALREADY_LINKED` | subject가 다른 user에 이미 연결됨 |
| 429 | `RATE_LIMITED` | 애플리케이션 fixed-window 초과 |
| 503 | `PROVIDER_UNAVAILABLE` | timeout, transport, 일시 오류, 5xx, JWKS 장애 |

issuer·audience·서명·expiry·nonce·subject 실패는 user를 만들지 않고 안전한 인증 오류로 반환한다.
provider URL, payload, exception message는 공개 오류나 로그에 포함하지 않는다.

## identity와 계정 정책

- trust chain은 `verified provider subject -> Firebase principal -> internal user UUID`다.
- 저장 허용값은 internal UUID/FK, provider code, opaque subject, status, policy/code-set version,
  연결·해제·재시도 시각과 allowlist failure code다.
- 활성 `(provider_code, provider_subject)`와 Firebase principal subject는 각각 전역 unique다.
- 같은 subject 반복 로그인은 같은 user/principal/identity를 재사용한다.
- 연결되지 않은 KAKAO subject의 첫 로그인은 별도 user를 만든다.
- 다른 user에 연결된 subject는 `IDENTITY_ALREADY_LINKED`; email/name 기반 자동 병합은 금지한다.
- 명시적 account-link API는 MVP에서 제외하고 로그인 결과를 현재 로그인 user에 암묵 연결하지 않는다.
- email, email_verified, name, nickname, picture, phone, birthday, birthyear, age, gender, locale과
  provider 원본 응답은 scope로 요청하거나 저장·병합 판단·로그에 사용하지 않는다.

user/identity mutation은 한 DB transaction이다. commit 뒤에만 Firebase custom token을 발급한다.
DB 실패는 전부 rollback하고 custom token을 반환하지 않는다. custom-token 발급 실패 시 이미 commit된
identity를 임의 삭제하지 않으며 다음 동일 subject 로그인은 멱등 재사용한다.

## 연결 해제와 계정 삭제

MVP 공개 account-link/standalone-unlink API는 만들지 않는다. 계정 삭제는 새 삭제 상태를 추가하지 않고
ADR-0008 provider revocation port/checkpoint를 재사용한다. provider token을 저장하지 않으므로 Kakao
Admin key와 저장된 subject로 unlink한다. 성공과 이미 해제는 멱등 성공이며 실패는 ADR-0008의 7일
retry budget 안에서 재시도한다. 기한 뒤 local hard delete를 우선하고 기존
`COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE`를 허용한다.

## 개인정보·운영 경계

로그·metric label·trace·snapshot·fixture·오류 details에 code/token/state/nonce/verifier,
provider/Firebase subject, raw IP/URI, email/name/profile 또는 provider 원본 응답을 남기지 않는다.
client secret, Admin key, Firebase credential과 rate-limit HMAC key는 개발팀장·운영 담당 소유의 secret
manager에서만 로드한다. local/CI는 실제 secret 없는 stub adapter를 사용한다.

## 공식 문서 근거

모두 공식 문서이며 확인일은 **2026-08-14**다.

- Firebase Auth/Google/custom token/link/delete/session: https://firebase.google.com/docs/auth , https://firebase.google.com/docs/auth/web/google-signin , https://firebase.google.com/docs/auth/admin/create-custom-tokens , https://firebase.google.com/docs/auth/web/account-linking , https://firebase.google.com/docs/auth/admin/manage-users , https://firebase.google.com/docs/auth/admin/manage-sessions
- Google OIDC: https://developers.google.com/identity/openid-connect/openid-connect
- Kakao REST/OIDC/state/nonce/PKCE/unlink: https://developers.kakao.com/docs/en/kakaologin/rest-api
- Kakao OIDC 검증·보안: https://developers.kakao.com/docs/ko/kakaologin/utilize
- Kakao 앱·redirect URI·scope: https://developers.kakao.com/docs/ko/kakaologin/prerequisite , https://developers.kakao.com/docs/ko/app-setting/app#platform-key-redirect-uri
- Kakao 오류: https://developers.kakao.com/docs/en/kakaologin/trouble-shooting
- Naver OIDC/PKCE/등록·검수: https://developers.naver.com/docs/login/devguide/devguide.md
- Naver token revoke: https://developers.naver.com/docs/login/api/api.md

## 승인 전 확인 사항

- PM: 출시 국가·대상 사용자가 대한민국인지, 세 provider 모두를 MVP 출시 게이트로 유지하는지
- 운영/개발팀장: Kakao 앱, OIDC/client secret, REST/Admin key, production redirect URI와 secret 경로
- 프론트엔드/백엔드: 600초 동안 state·nonce·verifier를 보관하는 mobile/web callback handoff
- 운영: trusted proxy client IP 전달, Kakao test app PKCE와 unlink
- Kakao가 공개하지 않은 authorization-code 숫자 TTL과 provider token rate-limit

이 항목과 ADR 상태가 `ACCEPTED`되기 전 Phase 3 구현을 시작하지 않는다.
