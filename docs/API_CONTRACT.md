# API_CONTRACT.md

## 1. 문서 목적

이 문서는 MVP 프론트엔드와 FastAPI 백엔드 사이의 REST 계약을 정의한다.

구현 이후에는 FastAPI가 생성하는 OpenAPI 문서를 기계 판독 가능한 계약의 진실 공급원으로 사용한다. 이 문서는 제품 의미, 상태 전이, 안전 및 호환성 규칙을 설명하는 상위 계약이다.

---

멀티 에이전트 핵심 흐름은 [ADR-0007](adr/0007-multi-agent-structure-correction.md)에 따라 네 proposal 병렬 실행과 Coordinator 최종 결정으로 확정한다. ADR-0002의 이전 독립 안전 게이트 구조는 대체되었다. proposal·Coordinator·공개 회의 요약의 상세 스키마와 설명 필드는 증상 사용자 시나리오 검증 결과에 따라 추후 보완할 수 있다. 결정적 안전 veto, 요청 시간 보존, 실패 안전과 운동 블록 체크 기반 상태 판정은 확정 계약이다.

[ADR-0013](adr/0013-safety-first-llm-multi-agent.md)은 Safety-first LLM 멀티에이전트 V3 목표 계약으로
`ACCEPTED`되었다. 구현·비교 검증과 production 전환 승인 전에는 아래 기존 endpoint와 응답을 바꾸지
않으며 V3 필드는 optional이다. [ADR-0014](adr/0014-qdrant-exercise-pool-vector-retrieval.md)는 내부
ExercisePool retrieval 계약의 `PROPOSED` 초안이며 Qdrant metadata를 public API에 노출하지 않는다.

---

## 2. 공통 원칙

- 모든 제품 API 경로는 /api/v1을 사용한다.
- 요청과 응답은 Pydantic 스키마로 검증한다.
- 공개 ID는 UUID다.
- timestamp는 timezone을 포함한 ISO 8601 문자열이다.
- 일일 리소스는 사용자 timezone의 YYYY-MM-DD local_date를 사용한다.
- 머신 코드는 안정적인 영문 대문자 문자열이다.
- 사용자 표시 문구와 머신 코드를 분리한다.
- 공개 응답 필드는 하위 호환을 유지하고 신규 필드는 가능하면 optional로 추가한다.
- mutation은 멱등성과 중복 요청을 고려한다.
- API 라우터는 비즈니스 규칙을 구현하지 않고 서비스와 도메인 계층에 위임한다.
- 내부 프롬프트, 숨은 추론, 인증 토큰, 원시 웨어러블 샘플을 응답하거나 로그에 기록하지 않는다.
- 웨어러블 요약과 캘린더 수행 여부 확인은 보조 정보이며 공식 운동 수행 상태를 변경하지 않는다. 웨어러블 운동 데이터는 캘린더에 자동 등록하지 않는다.
- 예상 소모 칼로리는 체중 기반 추정치로만 제공하며 진단 또는 안전 판정의 단독 근거로 사용하지 않는다.

---

## 3. 인증

MVP 세션 권한 공급자는 Firebase Authentication이며 첫 직접 social OAuth 구현 provider는 KAKAO다.
상세 provider-neutral 계약과 구현 순서는 `PROPOSED` ADR-0009와 `auth-provider-policy-v1`을 따른다.
ADR-0009가 `ACCEPTED`되기 전 아래 KAKAO endpoint는 예약 계약이며 구현하지 않는다.

클라이언트는 다음 헤더를 보낸다.

~~~http
Authorization: Bearer {firebase_id_token}
~~~

백엔드는 Firebase ID Token을 검증하고 token의 subject를 내부 user identity와 연결한다.

- Google은 Firebase 기본 provider를 사용하고 backend 직접 OAuth endpoint를 호출하지 않는다.
- KAKAO는 승인된 후 첫 독립 PR에서 provider OAuth 결과를 backend adapter가 검증하고 Firebase custom
  token으로 교환한다. Naver는 후속 독립 PR이다.
- FastAPI가 최종 권한으로 인정하는 것은 Firebase ID Token뿐이다.

규칙:

- 이메일, 이름, 닉네임, 전화번호, provider/Firebase subject, ID Token과 provider 원시 응답을
  애플리케이션 로그·trace·metric label에 기록하지 않는다.
- API 요청 body로 Firebase UID를 받지 않는다.
- 모든 사용자 리소스는 검증된 현재 사용자 범위로 제한한다.
- 삭제 대기 또는 비활성 계정은 일반 API 접근을 거부한다.
- 1년 이상 활동이 없는 계정은 DORMANT 서비스 분류와 30일 전 통지 후 삭제 정책을 적용한다. 법정 휴면으로 표현하지 않으며 재활성화·삭제 감사 세부 계약은 출시 전 확정한다.
- 외부 인증 검증은 integration adapter 뒤에 둔다.

Google Firebase 로그인은 client 공식 SDK가 소유한다. 앱은 추가 Google OAuth scope를 요청하지
않고 로그인 후 Firebase ID Token만 공통 Authorization header로 보낸다.

Kakao와 Naver의 모바일 OAuth 시작·교환은 다음 공개 endpoint를 사용한다. 첫 구현 provider는
`KAKAO`이며 `NAVER`는 별도 증분에서 활성화한다. ADR-0009 승인 전에는 예약 계약이다.

~~~http
POST /api/v1/auth/social/{provider_code}/authorize-init
POST /api/v1/auth/social/{provider_code}/exchange
~~~

`authorize-init`은 Firebase 인증 전 호출한다. client는 KAKAO Developers에 등록된 redirect URI와
PKCE S256 challenge를 보내고 server는 독립적인 state·nonce와 600초 만료 authorization URL을 반환한다.
redirect URI는 server allowlist 값과 정확히 일치해야 하며 개인정보 scope는 요청하지 않는다.

~~~text
SocialAuthorizationInitRequest
- redirect_uri: string
- code_challenge: string
- code_challenge_method: S256

SocialAuthorizationInitResponse
- provider_code: KAKAO
- authorization_url: string
- state: string
- nonce: string
- expires_at: ISO 8601 timezone-aware timestamp
~~~

state와 nonce 원문은 응답 후 서버 DB·cache·로그에 저장하지 않는다. PostgreSQL에는 각각의
SHA-256, redirect URI SHA-256, PKCE challenge와 만료 시각만 저장한다. state는 single-use이며
정상 교환 시 row를 즉시 삭제한다. 600초 경계 이후는 `422 OAUTH_STATE_EXPIRED`, 불일치·이미
소비된 state는 `422 INVALID_OAUTH_STATE`다.

authorize-init은 PostgreSQL fixed window로 canonical client IP 10회/분과 `(provider_code,
registered_redirect_uri_key)` 60회/시간을 적용한다. raw IP/URI는 저장하지 않고 HMAC digest와
window/count/expiry만 저장한다.

~~~http
POST /api/v1/auth/social/{provider_code}/exchange
~~~

`provider_code`는 KAKAO 또는 NAVER 예약 코드이며 현재 활성 값은 KAKAO다. 클라이언트는 provider
authorization code, 등록된 redirect URI, 서버가 발급한 state/nonce와 PKCE code verifier를 보낸다.
백엔드는 redirect URI, state/nonce와 S256 verifier를 검증하고 KAKAO OIDC ID token의 RS256 서명,
issuer, audience, expiry와 nonce를 검증한다. 검증된 `sub`만 내부 identity에 연결한 뒤 Firebase
custom token을 반환한다. provider access token을 요청 body로 받거나 저장하지 않는다.

~~~text
SocialTokenExchangeRequest
- authorization_code: string
- redirect_uri: string
- state: string
- nonce: string
- code_verifier: string | null (KAKAO는 필수)

SocialTokenExchangeResponse
- token_type: FIREBASE_CUSTOM_TOKEN
- firebase_custom_token: string
~~~

authorization code는 한 번만 사용할 수 있다. KAKAO의 만료·재사용·미존재 code는 모두
`KOE320 invalid_grant`이므로 민감한 provider 설명 없이 `409 AUTHORIZATION_CODE_REUSED`로
fail-closed 매핑한다. custom token은 응답 후 서버 cache나 도메인 DB에 저장하지 않는다.

두 비인증 social endpoint에는 PostgreSQL fixed-window 제한을 함께 적용한다.

- 요청 IP: 10회/분
- `(provider_code, redirect_uri)`: 60회/시간

제한 키는 운영 secret 기반 HMAC-SHA256만 저장하며 원시 IP와 redirect URI는 rate-limit row나
로그에 남기지 않는다. 초과 요청은 provider 호출 없이 `429 RATE_LIMITED`다. KAKAO timeout,
일시 오류와 5xx는 `503 PROVIDER_UNAVAILABLE`이며 provider 원본 응답을 오류에 포함하지 않는다.

Kakao는 `openid`, state, nonce, PKCE S256이 필수다. Naver 도입 시에는 `openid`, state, PKCE S256이
필수이며 확인한 공식 문서가 nonce를 명시하지 않으므로 nonce를 임의 검증하지 않는다. email,
profile, nickname, birthday, phone scope는 허용하지 않는다.

server는 client가 반환한 nonce를 저장 digest와 먼저 비교하고 KAKAO ID token의 nonce claim도 같은
digest와 constant-time 비교한다. 둘 중 하나라도 다르면 identity를 만들지 않는다.

MVP에서는 명시적 account-link endpoint를 제공하지 않는다. 연결되지 않은 KAKAO subject는 별도
user를 만들고 기존 로그인 user에 자동 연결하거나 email·name으로 병합하지 않는다.

authorization code와 flow는 한 번만 사용할 수 있고 재요청은 `409 AUTHORIZATION_CODE_REUSED`다.
signature, issuer, audience, expiry, subject와 적용 가능한 nonce 검증 후 provider code와 불변
subject만 identity service에 전달한다. access/refresh/ID token과 Firebase custom token은 처리
후 server cache나 도메인 DB에 저장하지 않는다.

같은 subject 반복 로그인은 최초 user를 반환한다. 이미 다른 user에 연결된 subject는
`409 IDENTITY_ALREADY_LINKED`이며 email·이름으로 병합하지 않는다. DB commit 실패 시 custom
token을 반환하지 않고 `503 DATABASE_UNAVAILABLE`로 rollback한다.

---

## 4. 공통 헤더

Mutation 요청:

~~~http
Idempotency-Key: client-generated-uuid
~~~

낙관적 잠금이 필요한 수정:

~~~http
If-Match: "resource-version"
~~~

응답 추적:

~~~http
X-Request-ID: server-generated-uuid
~~~

같은 사용자, 엔드포인트, Idempotency-Key에 같은 요청을 보내면 최초 성공 응답을 반환한다. 같은 키에 다른 payload를 보내면 409 IDEMPOTENCY_KEY_REUSED를 반환한다.

---

## 5. 공통 enum

### 5.1 액션

~~~text
KEEP
DOWNSHIFT
CHANGE
RECOVERY
REST
STOP_AND_SEEK_HELP
~~~

### 5.2 계획 옵션(공개 선택)

~~~text
FINAL_ROUTINE
REST
~~~

`ORIGINAL`과 후보 비교용 내부 candidate는 공개 선택 옵션으로 반환하지 않는다.

### 5.3 불편 심각도

~~~text
NONE
MILD
MODERATE
SEVERE
~~~

### 5.4 주관적 피로

~~~text
LOW
MODERATE
HIGH
~~~

이 코드는 제품 입력이며 의료 상태를 의미하지 않는다.

### 5.5 코치 문구 성향

~~~text
SUPPORTIVE
CONCISE
ENERGETIC
~~~

### 5.6 세션 상태

~~~text
PLANNED
IN_PROGRESS
COMPLETED
PARTIAL
NOT_COMPLETED
STOPPED_FOR_SAFETY
~~~

### 5.7 안전 평가 상태

~~~text
PASS
NEEDS_INPUT
REVISE
BLOCKED
FAILED
~~~

### 5.8 운동 블록 상태

~~~text
PENDING
COMPLETED
~~~

### 5.9 안정시 심박 추세

~~~text
UPWARD
STABLE
DOWNWARD
~~~

`resting_heart_rate_trend`는 웨어러블 제공자별 값을 서버가 위 코드로 정규화한 참고 정보이며 의료 상태를 의미하지 않는다. 값을 산출할 수 없으면 `null`이다.

신체 부위와 이상 반응 코드는 DOMAIN_RULES.md의 목록을 그대로 사용한다.

---

### 5.10 온보딩 통증 부위 노출 범위

코드 집합의 원본은 DOMAIN_RULES 3.2다. 신규 온보딩 UI는 통증 있음/없음을 먼저 묻고, 있음이면
`NECK`, `LOWER_BACK`, `SHOULDER`를 기본 노출한다. `OTHER`는 저장 가능한 body area가 아니라 나머지
실제 `body_area_code` 목록을 여는 UI control이다. 기타 목록에서는 `OTHER`를 제외한 실제 code를
복수 선택하고 각 code의 점수 1..10을 입력한다.

서버의 기존 body area code 집합과 기존 데이터는 삭제·재매핑하지 않는다. `GENERALIZED`처럼 승인된
안전 규칙이 없는 code가 입력되면 DOMAIN_RULES 4.3.1의 fail-closed 경계를 유지한다. 기본/기타 노출
변경과 1..10 severity 매핑은 안전 커버리지 변경이므로 개발팀장·PM·외부 도메인 승인 전 UI와
production validation을 활성화하지 않는다.

---

## 6. 엔드포인트 요약

### 6.1 상태

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /api/v1/health/live | 프로세스 생존 확인 |
| GET | /api/v1/health/ready | DB와 필수 설정 준비 확인 |

health endpoint는 인증 없이 호출할 수 있지만 민감한 설정, DB 주소, 예외 stack을 반환하지 않는다.

- `GET /api/v1/health/live` 성공 응답: `200 {"status_code":"OK"}`
- `GET /api/v1/health/ready` 성공 응답: `200 {"status_code":"READY"}`
- readiness에서 DB 확인이 실패하면 공통 오류 형식의 `503 DATABASE_UNAVAILABLE`을 반환한다.
- 모든 health 응답에는 서버가 생성한 UUID `X-Request-ID` header를 포함한다.

### 6.2 인증, 사용자와 온보딩

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | /api/v1/auth/social/{provider_code}/authorize-init | [예약] KAKAO server-bound OAuth flow 시작 |
| POST | /api/v1/auth/social/{provider_code}/exchange | [예약] KAKAO authorization code를 검증하고 Firebase custom token으로 교환 |
| GET | /api/v1/me | 현재 사용자와 온보딩 상태 |
| GET | /api/v1/me/identities | 현재 사용자에 연결된 인증 provider 목록 |
| PUT | /api/v1/me/onboarding | 프로필과 주의 부위 저장 |
| PATCH | /api/v1/me/profile | 온보딩 이후 프로필 운동 설정 부분 수정 |
| GET | /api/v1/me/consents | 저장된 동의 상태 조회. 온보딩 전에는 빈 목록 |
| PUT | /api/v1/me/consents | 일반·민감·웨어러블·캘린더·마케팅 현재 상태 저장·교체 및 이력 기록 |
| DELETE | /api/v1/me | 계정과 연결 데이터 삭제 요청 |

### 6.3 운동과 루틴

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /api/v1/exercises | 검수된 운동 목록 조회 |
| GET | /api/v1/exercises/{exercise_id} | 계획에 포함된 검수 운동 상세 |
| GET | /api/v1/exercises/{exercise_id}/variants | 장비가 없을 때 확인할 검수된 변형운동 조회 |
| POST | /api/v1/routines | 기본 루틴 생성 |
| GET | /api/v1/routines/current?local_date=YYYY-MM-DD | 해당 날짜의 활성 루틴 |
| POST | /api/v1/weeks/{week_start}/plan | 콜드스타트·최초 계획·다음 주 초기 계획 생성 (`INITIAL` revision) |
| POST | /api/v1/calendar/connection/authorize-init | Google Calendar OAuth state·PKCE 연결 시작 |
| POST | /api/v1/calendar/connection | authorization code 교환과 연결 활성화 |
| GET | /api/v1/calendar/connection | 현재 캘린더 연결 상태 조회 |
| GET | /api/v1/calendar/availability?local_date=YYYY-MM-DD | 일정과 빈 시간 후보 조회 |
| POST | /api/v1/calendar/events | 운동 계획을 캘린더에 등록 |
| GET | /api/v1/calendar/performance?workout_session_id=UUID | 등록된 운동 일정의 보조 수행 관찰값 확인 |
| DELETE | /api/v1/calendar/connection | 캘린더 연동 해제 |
| POST | /api/v1/wearables/connection | 웨어러블 기기 선택과 인증 연결 시작 |
| POST | /api/v1/wearables/sync | 웨어러블 요약·동기화 실행 및 상태 반환 |
| DELETE | /api/v1/wearables/connection | 웨어러블 연동 해제 |

카탈로그 관리 API는 공개 API에 포함하지 않는다. 운동 목록 조회는 8.4 계약으로 공개한다.
초기에는 노출할 검수 데이터가 없어 제외했으나, 승인된 카탈로그가 적재되면서 사용자가 어떤
운동이 있는지 확인할 수 있어야 한다는 요구가 확인됐다. 목록에는 `DOMAIN_APPROVED` 운동만
포함한다.

### 6.3.1 외부 연동 입력 계약

이 절의 인증·연동·저장 상위 경계는 `ACCEPTED` ADR-0003을 따른다. provider와 세부 payload는 프론트엔드·백엔드·개발팀장 검토로 확정하며, 구현 시 Pydantic 스키마, migration과 호환성 테스트를 함께 갱신한다.

캘린더:

~~~text
[ACCEPTED ADR-0010, external-context-policy-v2]
POST /api/v1/calendar/connection/authorize-init
CalendarConnectionAuthorizeInitRequest
- provider_code: GOOGLE_CALENDAR
- redirect_uri_key: string (server allowlist key)
- code_challenge_s256: string
- consent_version: string

CalendarConnectionAuthorizeInitResponse
- authorization_url: string
- state: string
- expires_at: datetime (요청 생성 후 600초)

POST /api/v1/calendar/connection
CalendarConnectionRequest
- provider_code: GOOGLE_CALENDAR
- authorization_code: string
- state: string
- code_verifier: string
- consent_version: string

CalendarConnectionResponse
- connection_id: UUID
- provider_code: GOOGLE_CALENDAR
- status_code: ACTIVE
- granted_at: datetime
- policy_version: external-context-policy-v2

GET /api/v1/calendar/connection
CalendarConnectionStatusResponse
- connection_id: UUID | null
- provider_code: GOOGLE_CALENDAR
- status_code: ACTIVE | REVOKE_PENDING | REVOKED | NOT_CONNECTED
- granted_at: datetime | null
- revoked_at: datetime | null

CalendarAvailabilityResponse
- local_date: date
- timezone: IANA timezone
- source_code: CALENDAR
- freshness_code: LIVE
- generated_at: datetime
- policy_version: external-context-policy-v2
- schema_version: calendar-availability-v1
- slots: {start_at: datetime, end_at: datetime}[]

POST /api/v1/calendar/events
CalendarEventCreateRequest
- workout_session_id: UUID
- start_at: datetime

CalendarEventCreateResponse
- event_link_id: UUID
- workout_session_id: UUID
- start_at: datetime
- end_at: datetime
- created_at: datetime

CalendarPerformanceResponse
- workout_session_id: UUID
- performed: boolean | null
- performance_checked_at: datetime | null
- guidance_code: CALENDAR_PERFORMANCE_UNAVAILABLE
- policy_version: external-context-policy-v2
- schema_version: calendar-performance-v2

DELETE /api/v1/calendar/connection
CalendarConnectionDeleteResponse
- connection_id: UUID | null
- provider_code: GOOGLE_CALENDAR
- status_code: REVOKED | NOT_CONNECTED
- revoked_at: datetime | null
- remote_calendar_retained: true
~~~

authorize-init은 raw state를 저장하지 않으므로 `Idempotency-Key`를 받지 않는다. 호출마다 이전 미소비
flow를 폐기하고 새 600초 state를 발급하며 client는 마지막 응답만 사용한다. event create는 UUID
`Idempotency-Key`가 필수이고 같은 key와 같은 요청은 최초 응답을 반환하며 다른 요청은
`409 IDEMPOTENCY_KEY_REUSED`다. connection exchange는 single-use state가 at-most-once mutation key이며
성공 여부와 관계없이 provider 호출 전에 소비된다. 반복 요청은 `422 INVALID_OAUTH_STATE`다. delete는
현재 connection 기준 멱등이며 미연결·이미 해제 상태에서도 성공 no-op이다.

`CALENDAR_INTEGRATION` 동의와 외부 권한이 없으면 연결·조회·등록·수행 여부 확인을 수행하지 않는다.
일정 본문 텍스트는 저장하지 않고, 캘린더에는 운동 계획 일정만 등록한다. 권한 거부·조회 실패·등록
실패·수행 여부 확인 실패는 상태와 안내만 반환하며 운동 계획을 삭제하거나 임의 변경하지 않는다.
특정 요일을 필수 운동일로 강제하지 않는다.

Wave 9C의 첫 provider는 Google Calendar API v3(`GOOGLE_CALENDAR`)다. 실제 adapter는
`ACCEPTED` ADR-0010과 TASK-BACKEND-007의 단계에 따라 추가한다. availability는 literal `primary`
calendar 하나를
`POST /calendar/v3/freeBusy`와
`https://www.googleapis.com/auth/calendar.freebusy`, 운동 이벤트는 앱이 만든 보조 캘린더에 한정하는
`https://www.googleapis.com/auth/calendar.app.created`만 사용한다. event list와 일정 제목·설명·참석자·
위치·organizer·creator 및 CalendarList를 조회하지 않는다. 사용자 timezone은 저장된 IANA timezone을
사용하며 `calendar.settings.readonly`를 요청하지 않는다. secondary/shared calendar를 합산하지 않는
MVP 제한은 응답 UI에 표시한다.

동기화는 on-demand pull 전용이고 availability를 cache하지 않으므로 stale 판정이 없다. webhook, push,
polling worker와 scheduler를 사용하지 않는다. 사용자별 availability는 30회/시간, calendar endpoint
전체는 60회/시간이며 초과 시 provider 호출 없이 `429 RATE_LIMITED`다. provider의 403/429 quota,
timeout과 5xx는 원문 없이 `503 PROVIDER_UNAVAILABLE`로 처리하고 수동 체크인·앱 운동 블록 체크를
유지한다.

빈 시간은 요청 `local_date`의 사용자 로컬 00:00부터 다음 날 00:00까지 계산한다. freebusy의 겹치거나
맞닿은 구간을 병합하고, 종일 여부를 추정하지 않고 provider가 반환한 모든 busy 구간을 점유 시간으로
처리한다. 후보 앞뒤에 15분씩 buffer를 두며 사용자 희망 운동시간과 buffer 30분을 수용하지 못한
구간은 제외한다. 후보는 시작 시각 오름차순 최대 8개다. 후보가 없으면 빈 배열을 반환하고 희망
운동시간을 임의 단축하지 않는다.

사용자가 수동 가능 시간을 명시하면 명시적 빈 목록을 포함해 calendar 후보보다 항상 우선한다. Calendar
결과는 사용자의 명시적 가능 시간, REST 선택, 기존 routine 또는 safety veto를 덮어쓰지 않는다.

Google Calendar에는 운동 수행 여부 필드가 없으므로 `performed`는 항상 `null`이다. 확인은 공식
workout session이 `COMPLETED/PARTIAL/NOT_COMPLETED/STOPPED_FOR_SAFETY`가 된 뒤에만 허용하고 같은
link는 `performance_checked_at`부터 10분 뒤에 재확인할 수 있다. Google event를 다시 조회하지 않으며
일정의 confirmed/tentative/cancelled 또는 삭제를 수행 여부로 해석하지 않는다.

운동 이벤트는 사용자 소유 `PLANNED` workout session에만 생성한다. client는 `workout_session_id`와
`start_at`만 보내며 server가 선택된 계획의 요청 시간으로 `end_at`을 계산한다. 보조 캘린더와 이벤트의
고정 summary는 각각 `헬끼 운동 일정`, `헬끼 운동`이고 그 밖의 본문·위치·참석자·회의 링크·메모는
보내지 않는다.

연동 해제는 먼저 `REVOKE_PENDING`으로 provider 접근을 막고 secret 파기 뒤 `REVOKED`로 확정하는
멱등 처리다. Firebase 로그인과 동일한 Google Cloud project를 공유하므로 Calendar 해제에서 Google
token revoke endpoint를 호출하지 않는다. 원격 보조 캘린더와 기존 이벤트는 남고 사용자가 Google
Calendar에서 직접 삭제할 수 있음을 UI가 안내한다.

Calendar OAuth는 9B 구현에 의존하지 않는 전용 transient row를 사용한다. 모바일은 state와 verifier를
OS 보안 저장소에 최대 600초만 보관하고 callback 직후 삭제한다. raw state·verifier·code·token은
DB·일반 저장소·로그·analytics·crash report에 포함하지 않는다. route와 Google adapter는 각각
9C-2D와 9C-2C에서 추가하며 production 증적 전에는 provider disabled를 유지한다.

웨어러블:

~~~text
POST /api/v1/wearables/connection
WearableConnectionRequest
- provider_code: string
- device_code: string
- authorization_code: string
- consent_version: string

POST /api/v1/wearables/sync
WearableSyncRequest
- local_date: date

WearableSyncResponse
- sync_id: UUID
- status_code: SUCCEEDED | FAILED | PERMISSION_DENIED | NOT_CONNECTED | API_ERROR
- summary: WearableDailySummary | null
- failure_code: string | null

WearableDailySummary
- local_date: date
- sleep_minutes: integer | null
- steps: integer | null
- active_minutes: integer | null
- active_calories_burned: number | null
- last_workout_type_code: string | null
- last_workout_started_at: datetime | null
- last_workout_ended_at: datetime | null
- last_workout_duration_minutes: integer | null
- average_heart_rate: number | null
- resting_heart_rate_trend: UPWARD | STABLE | DOWNWARD | null
- normalization_version: string
~~~

`POST /api/v1/wearables/sync`만 웨어러블 요약을 생성·저장하는 공개 경로다. 클라이언트는 요약 수치나 provider 원본을 제출·수정하지 않으며, 서버가 활성 연결의 웨어러블 제공자에서 데이터를 수집하고 원본을 임시 보관한 뒤 정규화·품질 검증·요약 저장을 수행한다. `WearableDailySummary`는 서버가 생성해 반환하는 응답이며 공개 `PUT /api/v1/wearables/summary`는 제공하지 않는다.

`normalization_version`은 서버가 요약을 생성한 웨어러블 정규화 규칙 버전이며 `summary`가 존재할 때 항상 반환한다. 제공자의 API·필드 버전은 공개 응답이 아닌 동기화 출처 메타데이터로 추적한다. 웨어러블 원본은 동기화 처리 중 임시 보관하고 24시간 이내 삭제한다. 원시 샘플·GPS·직접 식별자는 LLM과 공개 응답에 포함하지 않는다. 웨어러블 실패 시 수동 체크인과 앱 운동 블록 체크 경로를 계속 사용할 수 있다. 웨어러블 운동 데이터는 캘린더 이벤트를 자동 생성하거나 갱신하지 않는다.

### 6.3.2 MVP 이후: 수동 외부 기록 계약

수동 외부 기록은 MVP에서 제외하고 추후 기능으로 분류한다. 아래 계약은 후속 기능 검토용이며 초기 공개 API와 MVP 구현 범위에 포함하지 않는다.

~~~text
POST /api/v1/manual-activities
ManualActivityRequest
- activity_type_code: string
- duration_seconds: integer
- intensity_code: string
- weight_kg: number | null
- workout_session_id: UUID | null

ManualActivityResponse
- activity_id: UUID
- estimated_calories_burned: number | null
- estimate_status_code: ESTIMATED | UNKNOWN | FAILED
~~~

운동 종류·시간·강도는 후속 기능에서 필수로 검토한다. 체중이 있으면 버전이 있는 산식으로 예상 소모 칼로리를 계산하고, 없거나 계산에 실패하면 추정치를 만들지 않는다. 후속 수동 외부 기록은 공식 workout block 완료 상태를 변경하지 않는다.

### 6.4 체크인과 결정

| 메서드 | 경로 | 설명 |
|---|---|---|
| PUT | /api/v1/daily-contexts/{local_date} | 당일 체크인 생성 또는 교체 |
| GET | /api/v1/daily-contexts/{local_date} | 당일 체크인 조회 |
| POST | /api/v1/decisions | 현재 컨텍스트로 결정 실행 |
| GET | /api/v1/decisions/{decision_id} | 저장된 결정 조회 |
| POST | /api/v1/decisions/{decision_id}/regenerations | [V3 backend API 구현, 기본 비활성] 추가 입력 없이 다른 루틴 재생성 |
| POST | /api/v1/decisions/{decision_id}/selection | 서버가 허용한 옵션 선택 |

### 6.5 운동 세션

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /api/v1/workout-sessions | 본인의 운동 수행 기록 목록 |
| GET | /api/v1/workout-sessions/{session_id} | 단일 수행 기록 상세 |
| PATCH | /api/v1/workout-sessions/{session_id}/start | 운동 시작 |
| PATCH | /api/v1/workout-sessions/{session_id}/items/{plan_item_id} | 운동 블록 완료 또는 실행 중 되돌리기 |
| POST | /api/v1/workout-sessions/{session_id}/safety-events | 운동 중 통증·이상 반응 보고 |
| POST | /api/v1/workout-sessions/{session_id}/timer-events | 타이머 시작·일시정지·재개·종료 이력 저장 |
| POST | /api/v1/workout-sessions/{session_id}/additional-activities | 계획 외 추가 운동 기록 |
| PATCH | /api/v1/workout-sessions/{session_id}/finish | 수행 항목으로 COMPLETED 또는 PARTIAL 확정 |
| PATCH | /api/v1/workout-sessions/{session_id}/not-completed | NOT_COMPLETED와 가장 큰 이유 저장 |
| POST | /api/v1/workout-sessions/{session_id}/feedback | 난이도와 운동 후 불편 저장 |

### 6.6 주간 리포트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /api/v1/weeks/{week_start} | 주 경계와 상태 조회 |
| POST | /api/v1/weeks/{week_start}/report | 닫힌 주 리포트 요청 생성 |
| GET | /api/v1/weekly-reports/{report_id} | 저장된 리포트 조회 |
| POST | /api/v1/weekly-reports/{report_id}/acknowledgement | 리포트 확인 |
| POST | /api/v1/weeks/{week_start}/plan-revisions | 기존 계획의 Coordinator 기반 AI 수정 또는 직접 편집 저장 (`AI` 또는 `USER` revision) |

### 6.7 후속 또는 선택 기능

다음 경로는 핵심 MVP 계약에 포함하지 않는다.

- 날씨
- 푸시 알림
- MVP에서 선택한 웨어러블 제공자 외 추가 제공자

주간 리포트는 핵심 MVP다. 별도 장문 LLM 해석은 선택 기능이다.

---

## 7. 사용자와 온보딩 스키마

### 7.1 OnboardingUpsertRequest

신규 클라이언트는 아래 예시처럼 필수 `date_of_birth`와 온보딩 값을 전송한다. 생년월일은 입력·수정 요청에서 사용할 수 있다.

~~~json
{
  "nickname": "러너01",
  "date_of_birth": "1997-08-11",
  "primary_goal_code": "string",
  "experience_level_code": "string",
  "timezone": "Asia/Seoul",
  "preferred_location_code": "HOME",
  "available_location_codes": ["HOME", "GYM"],
  "default_requested_duration_minutes": 40,
  "desired_weekly_workout_count": 3,
  "attention_area_codes": ["KNEE"],
  "preferred_exercise_type_codes": ["STRENGTH"],
  "coaching_style_code": "SUPPORTIVE",
  "height_cm": 172.0,
  "weight_kg": 68.5,
  "sex_code": "FEMALE",
  "consents": {
    "general_personal_data": true,
    "sensitive_data": true,
    "wearable_integration": false,
    "calendar_integration": false,
    "marketing": false
  }
}
~~~

검증:

- `date_of_birth`는 필수 `YYYY-MM-DD` 값이며 미래 날짜와 달력상 유효하지 않은 날짜는 `422 INVALID_DATE_OF_BIRTH`로 거부한다. 클라이언트는 입력 오류를 표시한다.
- 서버는 사용자 timezone의 로컬 날짜를 기준으로 만 나이를 계산하며, 나이는 DB에 저장하지 않는다.
- 만 14세 미만이면 `403 AGE_REQUIREMENT_NOT_MET`와 함께 `만 14세 미만은 이용할 수 없습니다`를 반환하고 다음 화면으로 진행시키지 않는다.
- 만 14세 이상이면 별도 연령 안내 없이 다음 화면으로 이동한다.
- 생년월일 수정에도 동일한 서버 검증을 적용한다. 수정 결과가 만 14세 미만이면 해당 계정의 이용을 차단한다.
- 기존 클라이언트 호환 전략은 구현 전에 확정한다. 기존 `adult_confirmed`·`age_band_code` 요청을 deprecation 기간 동안 무시하고 서버 계산값을 사용하는 방식 또는 별도 API 버전 전략 중 하나를 선택하며, 선택한 전략에 대한 프론트엔드·백엔드 호환성 테스트를 추가한다.
- nickname은 서비스 표시용 최소 길이·금칙어 정책을 통과해야 한다. 세부 정책은 PM 문구 검토 후 확정한다.
- nickname은 고유 식별자가 아니며 사용자 간 중복을 허용한다.
- timezone은 유효한 IANA timezone이어야 한다.
- default_requested_duration_minutes는 0보다 커야 하며 사용자가 희망하는 권장 운동 길이다.
- location과 attention area는 서버의 허용 코드여야 한다.
- `sex_code`, `height_cm`, `weight_kg`는 필수다. 누락하면 `422`로 거부한다.
  - `sex_code`는 `FEMALE`, `MALE`, `PREFER_NOT_TO_SAY` 중 하나다.
    `PREFER_NOT_TO_SAY`는 유효한 응답이며 재질문하지 않는다.
  - `height_cm`은 80 이상 250 이하, `weight_kg`은 25 이상 300 이하다. 범위를 벗어나면
    입력 오류로 처리하고 값을 보정하지 않는다.
- `attention_area_codes`는 필수이며 빈 배열을 허용한다. 빈 배열은 "주의 부위 없음"이라는
  명시적 응답이고, 필드 누락과 구분한다. 클라이언트는 있음·없음을 먼저 묻고 있음일 때만
  부위를 입력받는다.
- coaching_style_code가 없으면 SUPPORTIVE를 사용한다.
- consents는 일반 개인정보·민감정보·웨어러블 연동·캘린더 연동·마케팅을 분리해 저장한다. 마케팅 동의는 선택이며, 민감정보·웨어러블·캘린더 동의 철회 시 해당 처리와 외부 동기화를 즉시 중단한다.

`GET /api/v1/me/consents`는 저장된 동의 상태를 `ConsentResponse`와 같은 스키마로 반환하는 read 전용 경로다. 온보딩 전에는 빈 `consents` 목록을 반환하며 이력을 노출하지 않는다.

`PUT /api/v1/me/onboarding`의 최초 동의 저장과 `PUT /api/v1/me/consents`의 동의·철회 변경은 동일한 동의 mutation 서비스가 처리한다. 각 동의 유형의 현재 상태는 `user_consents`에 갱신하고, `GRANTED` 또는 `REVOKED` event를 `user_consent_events`에 append하며 두 작업은 하나의 DB 트랜잭션으로 성공·실패를 함께 처리한다. 멱등 재시도는 같은 event를 중복 생성하지 않는다.

두 endpoint는 UUID `Idempotency-Key` header가 필수다. 서버가 배포 설정으로 승인한
`consent_policy_version`, `primary_goal_code`, `experience_level_code`가 없으면 임의 기본값을
사용하지 않고 `503 PROFILE_CONFIGURATION_UNAVAILABLE`로 차단한다. 기존
`adult_confirmed`·`age_band_code`는 자동 무시하지 않고 미지원 요청 필드로 거부하며
`date_of_birth` 계약을 사용하는 클라이언트만 지원한다.

성별·키·체중은 필수 입력이며 예상 소모 칼로리 추정과 이후 개인화에 사용한다. 칼로리 추정은
진단·안전 판정의 단독 근거가 아니다.

**세 값은 안전 판단에 사용하지 않는다.** 안전 결정은 DOMAIN_RULES 4.3과 4.3.1의 결정적 규칙으로만
내린다. 신체 치수로 위험도를 추정하거나 의학적 상태를 추론하지 않는다.

세 값은 건강 관련 정보다. 로그에 남기지 않고, LLM에 직접 전송하지 않는다.

DB 컬럼은 nullable로 유지한다. 필수화는 요청 스키마 계층에서만 적용한다. 온보딩 이전에 생성된
행이 남아 있을 수 있고, 신체 값에 임의 기본값을 채우는 것은 건강 데이터로서 허용되지 않기
때문이다. 저장된 값이 모두 채워진 것이 확인된 뒤에야 컬럼 제약 변경을 별도로 검토한다.

#### 7.1.1 장비 필드 제거와 호환 전략

2026-08-27 개발팀장 승인으로 이번 릴리스는 명시적인 breaking change 전략을 사용한다.

- `OnboardingUpsertRequest`, `ProfileSettingsUpdateRequest`, `MeProfile`에서 `equipment_codes`를
  즉시 제거한다. 구 클라이언트가 요청에 이 필드를 보내면 알 수 없는 필드로 `400 INVALID_REQUEST`다.
- 온보딩과 프로필 수정은 `user_equipment`를 생성·교체·삭제하지 않는다. 기존 행은 보존한다.
- `user_equipment` 테이블과 ORM 모델은 이번 릴리스에서 삭제하지 않는다. 계정 삭제 정리 경로도
  유지한다.
- 루틴 생성과 계획 검증은 사용자 장비 보유 여부를 조건으로 사용하지 않는다. 운동 자체의
  `required_equipment_codes`는 §8.5의 변형운동 안내를 위해 유지한다.
- 프론트엔드는 같은 릴리스에서 온보딩·마이페이지 장비 입력, API 요청 필드와 프로필 응답 decoding을
  함께 제거해야 한다.

#### 7.1.2 온보딩 통증 V2 목표 계약과 호환 전략

후속 additive rollout의 신규 request shape는 다음 필드를 사용한다. 이번 0단계에서는 현재 OpenAPI,
Pydantic schema와 물리 DB를 변경하지 않는다.

~~~text
PainAreaInput
- body_area_code: string
- intensity_score: integer  # 1..10

OnboardingPainInput
- pain_present: boolean
- pain_areas: PainAreaInput[]
~~~

검증:

- `pain_present=false`이면 `pain_areas`는 빈 목록이어야 한다.
- `pain_present=true`이면 `pain_areas`는 한 개 이상이어야 한다.
- 같은 `body_area_code`를 두 번 보낼 수 없다.
- `OTHER`는 UI control이므로 직접 저장·전송할 수 없다.
- 선택된 모든 부위에 1..10의 정수 `intensity_score`가 필수다.
- `pain-intensity-map-v1`은 1..3=`MILD`, 4..6=`MODERATE`, 7..10=`SEVERE`로 변환한다. 원점수와
  policy version을 함께 보존하며 승인 전 production에 적용하지 않는다.

호환 rollout은 다음 순서를 지킨다.

1. 현재 `attention_area_codes`를 즉시 삭제하거나 의미를 바꾸지 않는다.
2. 후속 API/schema 단계에서 신규 pain pair를 additive하게 받고 legacy `attention_area_codes`와
   동시 전송은 `400 INVALID_REQUEST`로 거부해 모호한 병합을 막는다.
3. legacy 요청은 기존 `user_attention_areas` 의미로 계속 저장하고 intensity를 추정·backfill하지 않는다.
4. 신규 client가 전환된 뒤 legacy field를 deprecated로 문서화하고 사용량·호환 테스트·프론트/백엔드
   owner 승인을 거쳐 별도 release에서 제거를 검토한다.

통증 부위와 점수는 LLM 또는 Qdrant vector, payload, embedding input/query에 포함하지 않는다.

### 7.2 OnboardingResponse

`PUT /api/v1/me/onboarding`이 성공하면 서버는 같은 DB 트랜잭션에서 저장된 프로필을 기준으로
초기 기본 루틴을 생성·저장한다. 이 동작은 `POST /api/v1/routines`의 기존 기본 루틴 생성 규칙과
저장 구조를 재사용하며, 응답 스키마는 변경하지 않는다. 이미 루틴 이력이 있는 사용자의 재요청은
새 version을 생성하지 않는다. 이 요청은 오늘 체크인 또는 오늘의 최종 루틴(결정)을 생성하지 않으며,
그 단계는 기존 `PUT /api/v1/daily-contexts/{local_date}` 후 결정 생성 흐름에서만 수행한다.

~~~json
{
  "user_id": "uuid",
  "onboarding_completed": true,
  "profile_version": 1,
  "coaching_style_code": "SUPPORTIVE",
  "ai_trial_started_at": "2026-08-06T10:00:00+09:00",
  "ai_trial_ends_at": "2026-08-20T10:00:00+09:00",
  "premium_status_code": "NOT_AVAILABLE",
  "created_at": "2026-08-06T10:00:00+09:00",
  "updated_at": "2026-08-06T10:00:00+09:00"
}
~~~

`date_of_birth`는 응답에 반환하지 않는다.

`GET /api/v1/me`의 프로필 응답에는 서버가 사용자 timezone의 로컬 날짜 기준으로 계산한 만 나이 `age`만 표시한다. `age`는 응답 시 일시 계산하며 DB에 저장하지 않고, 가입 자격 확인과 프로필 표시 외에는 사용하지 않는다.

프로필 응답 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `age` | integer | 사용자 timezone의 로컬 날짜 기준으로 서버가 계산한 만 나이 |

프로필 응답 예시:

~~~json
{
  "profile": {
    "age": 29
  }
}
~~~

`PUT /api/v1/me/onboarding`으로 생년월일을 수정할 수 있다. 서버는 저장 전에 수정된 생년월일을 다시 검증하고, 만 14세 미만이면 동일한 차단 오류를 반환한 뒤 이용을 차단한다.

`ai_trial_started_at`, `ai_trial_ends_at`, `premium_status_code`는 승인된 POL-013의 14일 AI 코치 무료 체험을 표현한다. 체험 종료 후 접근 범위는 구현 전 PM·개발팀장 검토로 확정한다.

### 7.2.0 현재 사용자 조회 (구현됨)

GET /api/v1/me

인증된 사용자의 계정 상태와 온보딩 완료 여부, 저장된 프로필을 반환한다. 클라이언트는 이 응답으로
온보딩 화면과 메인 흐름을 분기한다.

~~~text
MeResponse
- user_id: UUID
- status_code: string
- onboarding_completed: boolean
- premium_status_code: string
- ai_trial_started_at: datetime
- ai_trial_ends_at: datetime
- profile: MeProfile | null

MeProfile
- nickname: string
- age: integer | null
- primary_goal_code: string
- experience_level_code: string
- timezone: IANA timezone
- preferred_location_code: string
- available_location_codes: string[]
- default_requested_duration_minutes: integer
- desired_weekly_workout_count: integer
- coaching_style_code: string
- attention_area_codes: string[]
- preferred_exercise_type_codes: string[]
- profile_version: integer
- created_at: datetime
- updated_at: datetime
~~~

온보딩 전 사용자는 `onboarding_completed=false`, `profile=null`이다. 내부 사용자 레코드를 찾을 수
없으면 `404 RESOURCE_NOT_FOUND`다.

`age`는 §7.2의 계약대로 요청 시 사용자 timezone 기준으로 계산하며 DB에 저장하지 않는다. 배포에
birthdate cipher가 없거나 저장된 값을 복호화할 수 없으면 읽기를 실패시키지 않고 `age=null`을
반환한다. `date_of_birth`와 `protected_birthdate`는 응답에 포함하지 않는다.

### 7.2.1 연결된 인증 identity 조회

GET /api/v1/me/identities

~~~text
IdentityListResponse
- identities: IdentitySummary[]

IdentitySummary
- identity_id: UUID
- provider_code: FIREBASE | GOOGLE | KAKAO | NAVER
- created_at: datetime
~~~

현재 사용자에 연결된 활성 identity만 반환한다. `provider_subject`, `firebase_subject`, provider token과 철회된 identity는 공개 응답에 포함하지 않는다.

### 7.3 계정 삭제

DELETE /api/v1/me는 202 Accepted를 반환한다.

~~~json
{
  "deletion_request_id": "uuid",
  "status_code": "DELETION_PENDING",
  "operational_data_delete_by": "2026-08-13T10:00:00+09:00",
  "backup_expiry_days": 30
}
~~~

`Idempotency-Key`는 UUID여야 한다. 최초 요청은 사용자 상태와 삭제 request/job을 같은
transaction에서 저장한다. 같은 키 또는 새로운 키로 재요청해도 최초
`deletion_request_id`와 deadline을 반환하며 사용자별 활성 삭제 job을 추가하지 않는다.

삭제 요청 직후 일반 접근과 외부 동기화를 차단한다. `DELETION_PENDING` 사용자는 일반
인증 dependency에서 `403 ACCOUNT_DISABLED`로 차단되지만 이 endpoint의 재요청에는
제한된 삭제 lifecycle 인증 경계를 사용한다. hard delete 후에는 삭제 기록의 존재를
공개하지 않고 일반 인증 실패를 반환한다.

job은 `requested_at`부터 즉시 실행할 수 있다. `operational_data_delete_by`는 대기 시작
시각이 아니라 운영 DB hard delete의 최대 완료 기한인 `requested_at + 7일`이다. 백업은
요청 시각부터 30일 이내 만료해야 하며, 시간이 지났다는 이유만으로 완료 처리하지 않고
승인된 운영 증적 확인 후 완료 처리한다.

상세 의미는 `ACCEPTED` ADR-0008과 `account-deletion-policy-v1`을 따른다.

- 삭제 요청은 철회할 수 없다.
- `operational_data_delete_by`는 `requested_at + 7일`인 완료 상한이다. job은 요청 직후 실행할
  수 있으며 7일 후부터 실행하는 대기 계약이 아니다.
- 이미 `DELETION_PENDING`인 사용자가 같은 키 또는 새로운 UUID `Idempotency-Key`로 다시
  요청하면 `409`나 새 request를 만들지 않고 최초 `deletion_request_id`, status와 deadline을
  동일한 `202 Accepted`로 반환한다.
- 동일 사용자의 활성 deletion request/job은 하나다. 동시 요청도 저장된 최초 결과로 수렴한다.
- `DELETION_PENDING` 사용자는 이 endpoint의 멱등 재요청 외 모든 인증 사용자 제품 API와
  외부 동기화를 `403 ACCOUNT_DISABLED`로 차단한다. 비인증 health endpoint는 영향을 받지 않는다.
- provider 해제가 7일 기한까지 실패해도 로컬 사용자 연결 데이터는 기한 내 hard delete한다.
  backup 만료 확인 후 내부 job은 `COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE`로 끝날 수 있다.
  이 내부 job 상태는 기존 공개 응답에 새 필드로 노출하지 않는다.
- hard delete 후 Firebase token이나 provider subject가 내부 사용자와 연결되지 않으면 일반 인증
  실패를 반환하고 삭제 request의 존재 여부를 공개하지 않는다.
- request/job ID는 UUIDv4다. hard delete 후 감사에는 사용자/provider 식별자, token,
  idempotency key, 요청·응답·원시 오류·건강 snapshot을 남기지 않는다.
- backup 복원 차단용 HMAC-SHA256 keyed-digest tombstone은 요청 후 최대 30일만 보유한다.
  backup 만료는 단순 시간 경과가 아니라 마지막 관련 recovery point 만료 운영 증적으로 확인한다.

---

### 7.4 온보딩 이후 수정 가능 필드

온보딩에서 받은 값 중 사용자가 이후에 바꿀 수 있는 항목이다. 마이페이지는 이 목록을 운동 설정
중심으로 구성하며, 저장된 코드 값을 그대로 노출하지 않고 사용자 언어로 표시한다.

PATCH가 지원하는 필드는 아래 15개다. 표의 `null 거부`는 필드 생략과 다르다. 필드를 보내지 않으면
기존 값을 유지하지만 JSON `null`을 명시하면 `400 INVALID_REQUEST`다.

| 필드 | 타입·허용 값 | 빈 값·중복 | 범위·정규화·교차 검증 | 실패 |
|---|---|---|---|---|
| `primary_goal_code` | string, `^[A-Z][A-Z0-9_]{0,63}$`, 배포 승인 코드 | 빈 문자열·null 거부 | trim·대소문자 변환 없음. 다음 결정부터 반영 | 형식 오류 `400 INVALID_REQUEST`; 미승인 코드 `422 INVALID_ONBOARDING_CODE`; 승인 목록 없음 `503 PROFILE_CONFIGURATION_UNAVAILABLE` |
| `desired_weekly_workout_count` | integer | null 거부 | 1~7회. 진행 중인 주에는 소급 적용하지 않음 | 범위·타입 오류 `400 INVALID_REQUEST` |
| `default_requested_duration_minutes` | integer | null 거부 | 1~240분 | 범위·타입 오류 `400 INVALID_REQUEST` |
| `preferred_location_code` | `HOME`, `GYM`, `OUTDOOR` | 빈 문자열·null 거부 | 최종 `available_location_codes`에 반드시 포함 | enum·교차 검증 오류 `400 INVALID_REQUEST` |
| `available_location_codes` | 위 location code 배열 | 빈 배열·null·중복 거부 | 현재 또는 함께 보낸 `preferred_location_code`를 포함. 순서 외 별도 정규화 없음 | enum·중복·교차 검증 오류 `400 INVALID_REQUEST` |
| `attention_area_codes` | `NECK`, `SHOULDER`, `ELBOW`, `WRIST_HAND`, `UPPER_BACK`, `LOWER_BACK`, `HIP`, `KNEE`, `ANKLE_FOOT`, `CHEST`, `ABDOMEN` 배열 | **빈 배열 허용**, null·중복 거부 | 건강 관련 정보. 빈 배열은 주의 부위 없음 | enum·중복 오류 `400 INVALID_REQUEST` |
| `preferred_exercise_type_codes` | `STRENGTH`, `CARDIO`, `MOBILITY` 배열 | **빈 배열 허용**, null·중복 거부 | 순서 외 별도 정규화 없음 | enum·중복 오류 `400 INVALID_REQUEST` |
| `coaching_style_code` | `SUPPORTIVE`, `CONCISE`, `ENERGETIC` | 빈 문자열·null 거부 | trim·대소문자 변환 없음 | enum 오류 `400 INVALID_REQUEST` |
| `experience_level_code` | string, `^[A-Z][A-Z0-9_]{0,63}$`, 배포 승인 코드 | 빈 문자열·null 거부 | trim·대소문자 변환 없음 | 형식 오류 `400 INVALID_REQUEST`; 미승인 코드 `422 INVALID_ONBOARDING_CODE`; 승인 목록 없음 `503 PROFILE_CONFIGURATION_UNAVAILABLE` |
| `nickname` | string | trim 후 빈 문자열·null 거부 | 앞뒤 공백 제거 후 1~64자. 내부 공백은 유지 | 길이·타입 오류 `400 INVALID_REQUEST` |
| `height_cm` | number | null 거부 | 80~250cm, 보정·반올림 없음. 건강 관련 정보 | 범위·타입 오류 `400 INVALID_REQUEST` |
| `weight_kg` | number | null 거부 | 25~300kg, 보정·반올림 없음. 건강 관련 정보 | 범위·타입 오류 `400 INVALID_REQUEST` |
| `sex_code` | `FEMALE`, `MALE`, `PREFER_NOT_TO_SAY` | 빈 문자열·null 거부 | 대소문자 변환 없음. 건강 관련 정보 | enum 오류 `400 INVALID_REQUEST` |
| `timezone` | 1~64자 IANA timezone string | 빈 문자열·null 거부 | trim 없음. 저장된 생년월일을 새 timezone으로 다시 검증 | 형식 오류 `400 INVALID_REQUEST`; 알 수 없는 timezone `422 INVALID_TIMEZONE`; 암호화 설정·복호화 불가 `503 PROFILE_CONFIGURATION_UNAVAILABLE` |
| `date_of_birth` | ISO 8601 `date` (`YYYY-MM-DD`) | 빈 문자열·null 거부 | 미래 날짜 거부, 최종 timezone 기준 만 14세 규칙 재적용, 암호화 저장 | 형식·미래 날짜 `422 INVALID_DATE_OF_BIRTH`; 만 14세 미만 `403 AGE_REQUIREMENT_NOT_MET`; 암호화 설정 없음 `503 PROFILE_CONFIGURATION_UNAVAILABLE` |

공통 규칙:

- 부분 수정이다. 보내지 않은 scalar와 관계 필드는 기존 값을 유지하고, 보낸 관계 배열만 교체한다.
- 15개 필드는 OpenAPI에서 모두 선택 사항이지만 nullable이 아니다. 빈 객체, 알 수 없는 필드와
  명시적 `null`은 `400 INVALID_REQUEST`다.
- 모든 코드 배열은 중복을 거부한다. `attention_area_codes`와
  `preferred_exercise_type_codes`는 빈 배열을 허용한다.
- `preferred_location_code`는 요청값과 기존값을 병합한 최종 `available_location_codes`에 포함돼야
  한다.
- `primary_goal_code`와 `experience_level_code`는 배포 승인 목록의 값만 허용한다.
- 이 PATCH의 성공·오류 응답은 생년월일, 키·체중·성별과 주의 부위의 원값을 반복하지 않으며,
  해당 값은 로그에도 남기지 않는다. 성공 응답은 새 version과 갱신 시각만 반환한다.
- 낙관적 잠금과 멱등성은 §7.4.1의 기존 `If-Match`·`Idempotency-Key` 계약을 그대로 적용한다.
- `consents`는 이 PATCH의 지원 필드가 아니며 `PUT /api/v1/me/consents`에서 변경한다.

#### 7.4.1 프로필 설정 부분 수정

요청 본문은 §7.4에서 `가능`으로 표시한 필드만 받을 수 있으며 모든 필드는 선택 사항이다. 단,
빈 객체, 알 수 없는 필드, 명시적 `null`, 중복 배열 코드는 `400 INVALID_REQUEST`로 거부한다.

완전한 요청 예시는 다음과 같다. `If-Match` 값의 큰따옴표는 HTTP 헤더 문법의 일부이므로 생략하면
안 된다.

~~~http
PATCH /api/v1/me/profile HTTP/1.1
Authorization: Bearer <Firebase-ID-Token>
Content-Type: application/json
Idempotency-Key: 7e225f2e-7f86-4b5e-96f7-23c18f948210
If-Match: "1"

{
  "desired_weekly_workout_count": 4,
  "preferred_location_code": "GYM",
  "available_location_codes": ["HOME", "GYM"]
}
~~~

`attention_area_codes`의 빈 배열은 허용한다. `preferred_location_code`는 기존 값과 요청 값을 병합한 최종
`available_location_codes`에 포함되어야 한다. 요청하지 않은 scalar와 관계는 유지하며 요청에
포함된 관계만 교체한다.

`If-Match`는 따옴표를 포함한 양의 정수 형식(예: `"1"`)으로 필수 전송한다. 헤더가 없거나 `1`,
`W/"1"`, `"0"`, 음수 또는 숫자가 아닌 값이면 다음 공통 오류 형식의
`400 INVALID_REQUEST`를 반환한다.

~~~http
HTTP/1.1 400 Bad Request
X-Request-ID: 20f092af-7335-414d-bbc9-1bd6ec175d4d

{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "If-Match는 현재 profile_version을 \"1\" 형식으로 포함해야 합니다.",
    "details": [],
    "request_id": "20f092af-7335-414d-bbc9-1bd6ec175d4d"
  }
}
~~~

형식은 올바르지만 값이 현재 `profile_version`과 다르면 저장소를 변경하지 않고 다음
`409 STALE_PROFILE`을 반환한다.

~~~http
HTTP/1.1 409 Conflict
X-Request-ID: 07b44c79-320f-4f15-b2e5-4966dc6a8c91

{
  "error": {
    "code": "STALE_PROFILE",
    "message": "프로필이 변경되었습니다. 최신 상태로 다시 시도해주세요.",
    "details": [],
    "request_id": "07b44c79-320f-4f15-b2e5-4966dc6a8c91"
  }
}
~~~

`STALE_PROFILE`을 받은 클라이언트는 자동으로 이전 요청을 덮어쓰지 않는다. 다음 순서로 충돌을
해결한다.

1. `GET /api/v1/me`를 호출해 최신 프로필과 `profile.profile_version`을 읽는다.
2. 사용자가 의도한 변경을 최신 프로필에 다시 적용한다.
3. 새 `Idempotency-Key`와 최신 version의 `If-Match`를 사용해 PATCH를 재시도한다.

성공한 수정은 scalar, 관계 교체, `profile_version` 1 증가와 멱등성 결과 저장을 한 transaction에서
처리한다. 예를 들어 `If-Match: "1"` 요청이 성공하면 다음과 같이 새 version을 반환한다.

~~~http
HTTP/1.1 200 OK

{
  "profile_version": 2,
  "updated_at": "2026-08-19T02:30:00+00:00"
}
~~~

~~~text
ProfileSettingsUpdateResponse
- profile_version: integer
- updated_at: datetime
~~~

성공 응답의 `profile_version`은 클라이언트가 다음 수정 요청의 `If-Match`에 사용한다. 같은
사용자·endpoint·`Idempotency-Key`에서 동일한 PATCH 본문과 동일한 `If-Match` version을 재시도하면
최초 성공 응답을 재생하고 version을 다시 증가시키지 않는다. 이미 성공한 키를 다른 본문 또는
다른 expected version에 재사용하면 `409 IDEMPOTENCY_KEY_REUSED`다. 따라서 `STALE_PROFILE` 뒤 최신
version으로 변경을 재적용하는 요청에는 새 `Idempotency-Key`를 사용한다. 응답에는 생년월일,
암호화 값, 키·체중·성별, 주의 부위를 반복하지 않는다. 온보딩 프로필이 없으면
`404 RESOURCE_NOT_FOUND`다.

---

## 8. 루틴 스키마

### 8.1 RoutineCreateRequest

~~~json
{
  "effective_from": "2026-08-06",
  "goal_code": "string",
  "requested_duration_minutes": 30
}
~~~

`requested_duration_minutes`는 선택 필드이며 1~240 범위다. 생략하면 프로필의
`default_requested_duration_minutes`를 그대로 목표 시간으로 쓰고
`duration_adjustment_source_code`는 `PROFILE`이 된다. 값을 보내면 그 값이 이 루틴의 목표
시간이 되고 출처는 `USER_OVERRIDE`가 된다. 프로필의 기본값은 말 그대로 기본값이며 이
요청으로 변경되지 않는다. 서버는 사용자를 대신해 `USER_OVERRIDE`를 만들지 않는다.
같은 `Idempotency-Key`로 다른 시간을 보내면 `409 IDEMPOTENCY_KEY_REUSED`다.

서버는 현재 사용자 프로필과 장소, DOMAIN_APPROVED 운동만 사용해 보수적인 기본 루틴을 만든다. 사용자 장비 보유 여부는 운동 선정 조건이 아니다. 클라이언트는 운동 ID, 세트 또는 tier를 임의 지정하지 않는다.

`POST /api/v1/routines`는 `Idempotency-Key`가 필수이며 성공 시 `201`을 반환한다.
서버는 `ACTIVE`, `DOMAIN_APPROVED`, `production_eligible=true`이고 도메인 검수 증적이
있는 단 하나의 catalog version과 승인된 목표 연결·처방만 사용한다. 사용자별 routine
version은 1부터 단조 증가하며, 같은 사용자의 동시 생성은 직렬화한다.

`GET /api/v1/routines/current?local_date=YYYY-MM-DD`는 인증된 현재 사용자에게 해당 날짜에
활성이고 현재 운영 승인된 `ACTIVE` catalog version을 참조하는 루틴만 반환한다. catalog
전환으로 참조 version이 `DEPRECATED`가 된 루틴은 기록으로 보존하되 현재 루틴으로 노출하지
않는다. 사용할 수 있는 현재 루틴이 없으면 `404 ROUTINE_NOT_FOUND`이며, 클라이언트는 기존
`POST /api/v1/routines` 흐름으로 새 `ACTIVE` catalog version 기반 루틴을 생성할 수 있다. 다른
사용자의 루틴은 조회 후보에 포함하지 않는다.

### 8.2 RoutineResponse

~~~text
RoutineResponse
- id: UUID
- version: integer
- goal_code: string
- status_code: DRAFT | ACTIVE | ARCHIVED
- effective_from: date
- catalog_version: string
- days: RoutineDay[]
- created_at: datetime

RoutineDay
- id: UUID
- sequence: integer
- title: string
- training_type_code: string  # STRENGTH, CARDIO 등
- body_focus_code: string | null  # versioned catalog machine code
- requested_duration_minutes: integer
- estimated_duration_seconds: integer
- estimated_calories_burned: number | null  # 체중 기반 추정치
- items: RoutineItem[]

RoutineItem
- id: UUID
- exercise_id: UUID
- exercise_name: string
- sequence: integer
- phase_code: WARMUP | MAIN | COOLDOWN
- tier_code: CORE | SUPPORT | OPTIONAL
- sets: integer
- reps: integer | null
- work_seconds_per_set: integer | null
- rest_seconds_per_set: integer
- instruction_available: boolean
~~~

`catalog-v2`의 `body_focus_code` 허용값은 `CHEST`, `BACK`, `SHOULDERS`, `BICEPS`, `TRICEPS`,
`FOREARMS`, `GLUTES`, `QUADRICEPS`, `HAMSTRINGS`, `CALVES`, `CORE`, `FULL_BODY`, `CARDIO`,
`MOBILITY`다. 기존 V1 응답의 `UPPER_BODY`, `LOWER_BODY` decoding은 하위 호환을 위해 유지하지만
V2 importer는 두 legacy code를 새 catalog row에 허용하지 않는다. 필드의 nullable 여부와 이름은
변경하지 않는다.

requested duration은 사용자 선택값이며 서버가 변경하지 않는다. 운동 계획을 반환하는 경우 estimated duration은 `requested_duration_minutes * 60`에서 앞뒤 300초 이내여야 한다. 승인된 후보 중 요청값과 차이가 가장 작은 계획을 선택하며, 같은 차이면 더 짧게 만드는 것보다 더 길게 만드는 계획을 우선한다. 실제 운동 경과 시간은 사용자 속도에 따라 달라질 수 있으며 완료 판정에는 사용하지 않는다.

모든 routine day는 `WARMUP -> MAIN -> COOLDOWN` 순서로 구성한다. WARMUP과 COOLDOWN은
승인된 스트레칭·가동성 처방이고 MAIN에는 목표와 직접 연결된 CORE 운동이 하나 이상
포함되어야 한다. 각 단계가 없거나 승인된 처방으로 요청 시간의 ±5분 범위를 만족할 수 없으면
루틴을 반환하지 않는다. 기본 routine day는 특정 요일을 강제하지 않고 ROTATION
순서로 수행한다.

사용자 가능 장소는 `HOME`, `GYM`, `OUTDOOR` 개별 코드 배열로 관리한다. `HOME`과 `GYM`을
모두 선택한 사용자는 두 장소 중 하나 이상을 지원하는 운동만 받을 수 있다. 기존
`preferred_location_code`는 호환 기간 동안 유지하고, `available_location_codes`가 없으면
해당 단일 값을 사용한다.

### 8.3 운동 자세·설명

GET /api/v1/exercises/{exercise_id}는 계획 블록의 펼침 버튼에서 사용할 다음 정보를 반환한다.

~~~text
ExerciseDetailResponse
- exercise_id: UUID
- exercise_name: string
- training_type_code: string
- primary_body_area_codes: string[]
- instruction_summary: string
- form_cues: string[]
- media_asset_key: string | null
- media_url: string | null
- mascot_animation_asset_key: string | null
- instruction_content_version: string
~~~

자세·설명 콘텐츠는 검수된 정보만 반환하며 카메라 자세 인식이나 자동 자세 판정을 의미하지 않는다.

구현 상태: 이 endpoint는 구현됐다. 인증된 사용자만 호출할 수 있고 `review_status_code`가
`DOMAIN_APPROVED`인 운동만 반환하며, 그 외에는 `404 RESOURCE_NOT_FOUND`다. `media_asset_key`는
미디어 상태가 `AVAILABLE`, 권리 검토가 `APPROVED`이고 승인 registry의 version/hash/count가 모두
일치하는 자산에만 채워진다. 운동에 미디어가 없거나 어느 승인 조건이든 충족하지 않으면 `null`이다.
`media_url`은 같은 승인 조건을 만족하는 운영 승인 catalog 운동에 대해 검증·보존된
`videos/<4자리 source_identity>-<식별문자열>.gif` 객체가 실제로 존재하고 S3 `ContentType`이
`image/gif`일 때만 짧은 만료시간의 presigned GET URL로 채워진다. 객체 확인이나 URL 생성이
실패하면 endpoint 자체를 실패시키지 않고 `null`을 반환한다. URL은 저장하거나 로그에 남기지 않는다.
`mascot_animation_asset_key`는 아직 항상 `null`이다.

---

### 8.4 운동 목록 조회

GET /api/v1/exercises

검수된 운동 목록을 반환한다. 사용자가 어떤 운동이 있는지 둘러보기 위한 읽기 전용 계약이며
계획 생성과 무관하다.

쿼리 파라미터는 모두 선택이다.

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `body_area_code` | string | 주 자극 부위로 필터 |
| `equipment_code` | string | 필요 장비로 필터 |
| `training_type_code` | string | 운동 유형으로 필터 |
| `difficulty_code` | string | 운동 자체 난이도(`BEGINNER`, `INTERMEDIATE`)로 필터 |
| `cursor` | string | 다음 페이지 커서 |
| `limit` | integer | 1~100, 기본 20 |

~~~text
ExerciseListResponse
- items: ExerciseListItem[]
- next_cursor: string | null
- catalog_version: string

ExerciseListItem
- id: UUID
- name: string
- training_type_code: string
- difficulty_code: string
- primary_body_area_codes: string[]
- required_equipment_codes: string[]
- media_asset_key: string | null
~~~

- `review_status_code`가 `DOMAIN_APPROVED`인 운동만 반환한다. 미검수 콘텐츠는 어떤
  파라미터 조합으로도 노출되지 않는다.
- `media_asset_key`는 상세 조회와 같은 승인 조건을 만족할 때만 채워지며, 그 외에는 `null`이다.
- 인증된 사용자만 호출할 수 있다.
- 상세 정보는 8.3의 `GET /api/v1/exercises/{exercise_id}`를 사용한다.
- 목록은 안전 판단과 무관하다. 사용자의 불편 부위에 따른 제외는 계획 생성 시점에만 적용하며,
  이 목록을 부위별로 걸러 안전하다고 표시하지 않는다.
- 정렬은 안정적이어야 하며 커서 페이지네이션 중 항목이 중복되거나 누락되지 않아야 한다.

### 8.5 장비 변형운동 확인

GET /api/v1/exercises/{exercise_id}/variants

루틴 화면과 운동 수행 화면에서 필요한 장비와 장비가 없을 때 확인할 검수된 변형운동을 반환하는
읽기 전용 endpoint다. 운동 교체, routine item 수정 또는 workout session 기록 변경을 수행하지 않는다.

~~~text
ExerciseVariantsResponse
- source_exercise_id: UUID
- source_required_equipment_codes: string[]
- items: ExerciseVariantItem[]
- catalog_version: string
- alternative_set_version: string | null

ExerciseVariantItem
- exercise_id: UUID
- exercise_name: string
- required_equipment_codes: string[]
- instruction_summary: string
- form_cues: string[]
- media_asset_key: string | null
- goal_preservation_code: string
~~~

- 인증된 사용자만 호출할 수 있다.
- source exercise의 원본 catalog는 운영 승인된 `ACTIVE` 또는 `DEPRECATED` 상태여야 하고 source
  exercise도 `DOMAIN_APPROVED`여야 한다. `DRAFT`, 미승인 catalog 또는 존재하지 않는 운동은
  `404 RESOURCE_NOT_FOUND`다. 응답의 `catalog_version`은 현재 ACTIVE가 아니라 source exercise의
  원본 catalog version이다.
- 관계는 `exercise_alternatives.reason_code='EQUIPMENT'`, `review_status_code='DOMAIN_APPROVED'`,
  `production_eligible=true`인 행만 사용한다. `LOCATION`, `DIFFICULTY`, `DISCOMFORT`는 반환하지 않는다.
- variant exercise도 source와 같은 원본 catalog에 속한 `DOMAIN_APPROVED` 운동이어야 한다.
- 변형운동이 없으면 `200`, `items=[]`, `alternative_set_version=null`을 반환한다. 클라이언트는 이때
  변형운동 버튼을 노출하지 않는다.
- items는 `exercise_id`, `goal_preservation_code`, 관계 ID 순으로 결정적으로 정렬한다.
- 여러 운영 승인 alternative set이 한 source에 동시에 연결되면 재현 가능한 단일 set을 정할 수
  없으므로 `503 APPROVED_CATALOG_UNAVAILABLE`로 fail closed한다.
- `media_asset_key`는 §8.3과 동일한 권리·승인 조건을 만족할 때만 반환한다.

---

## 9. 당일 체크인

### 9.1 DailyContextUpsertRequest

~~~json
{
  "fatigue_level_code": "MODERATE",
  "requested_duration_minutes": 40,
  "duration_adjustment_source_code": "PROFILE",
  "location_code": "HOME",
  "sleep_minutes": null,
  "fasting_state_code": null,
  "hydration_state_code": null,
  "discomforts": [
    {
      "body_area_code": "KNEE",
      "severity_code": "MILD"
    }
  ],
  "adverse_reaction_codes": [],
  "available_slots": [
    {
      "start_at": "2026-08-20T19:00:00+09:00",
      "end_at": "2026-08-20T21:00:00+09:00"
    }
  ]
}
~~~

검증:

- 한 body_area_code는 한 번만 보낼 수 있다.
- NONE은 discomfort 항목으로 보내지 않고 목록에서 제외한다.
- requested_duration_minutes는 0보다 크다.
- PROFILE은 프로필 기본 희망 시간을 확인한 경우, USER_OVERRIDE는 사용자가 당일 시간을 직접 변경한 경우다.
- 서버나 agent가 duration_adjustment_source_code=USER_OVERRIDE를 대신 생성할 수 없다.
- 긴급 중단 그룹과 급성 근골격 신호 그룹을 모두 받을 수 있다.
- sleep_minutes는 선택이다.
- 웨어러블이 없어도 요청은 완전하게 유효하다.

PUT은 전체 체크인 표현을 교체한다. 빈 discomforts와 adverse_reaction_codes는 기존 항목을 삭제한다.

#### 9.1.1 available_slots — 사용자 수동 가능 시간

`available_slots`는 사용자가 그날 운동할 수 있다고 직접 밝힌 시간 구간이다. 외부 캘린더 연동은
보류 상태이므로(ADR-0010 "구현 보류") 이 입력이 유일한 availability 입력원이다.

세 가지 상태를 구분한다. 이 구분은 계약이며 클라이언트가 임의로 바꿀 수 없다.

| 전송 값 | 의미 | `availability_source_code` |
|---|---|---|
| 필드 생략 또는 `null` | 사용자가 가능 시간을 밝히지 않음 | `ROUTINE_DEFAULT` |
| `[]` | 사용자가 "오늘은 가능한 시간이 없다"를 명시적으로 선택 | `MANUAL` |
| `[{...}]` | 사용자가 가능 구간을 명시 | `MANUAL` |

명시적 빈 목록은 미입력과 다르며 서버가 이를 미입력으로 취급하거나 다른 값으로 보완하지 않는다.

검증:

- `start_at`과 `end_at`은 timezone offset을 포함한 ISO 8601이다. naive datetime은 거부한다.
- `end_at`은 `start_at`보다 뒤여야 한다.
- 모든 구간은 사용자 프로필 timezone 기준으로 경로의 `local_date`에 속해야 한다. 종료 시각이
  다음 날 00:00인 경계는 허용한다.
- 구간끼리 겹치거나 맞닿을 수 없다.
- 최대 8개다. 서버는 시작 시각 오름차순으로 정규화해 저장하고 반환한다.
- 요청 순서가 달라도 정규화 결과가 같으면 동일한 멱등 요청으로 취급한다.

이 값은 참고 입력이며 다음을 절대 하지 않는다.

- `requested_duration_minutes`를 바꾸지 않는다.
- 운동 계획, 안전 판단, 안전 veto에 영향을 주지 않는다.
- 공식 운동 수행 상태를 바꾸지 않는다.
- 특정 요일을 필수 운동일로 강제하지 않는다.

필수 mutation 헤더:

~~~http
Idempotency-Key: uuid
~~~

최초 생성에는 `If-Match`를 보내지 않는다. 기존 체크인을 교체할 때는 GET 또는 직전 PUT에서
받은 `context_version`을 `If-Match: "2"` 형식으로 보낸다. 기존 체크인에 `If-Match`가
누락됐거나 버전이 다르면 `409 STALE_CONTEXT`다. 동일한 `Idempotency-Key`와 동일한 요청의
재시도는 최초 성공 응답을 반환하며 버전을 다시 증가시키지 않는다. 같은 키를 다른 날짜 또는
본문에 재사용하면 `409 IDEMPOTENCY_KEY_REUSED`다.

`fasting_state_code`와 `hydration_state_code`는 선택적인 사용자 제공 machine code다. 승인된
후보 목록이 확정되기 전까지 서버는 누락값을 보완하거나 수면·공복·수분 상태를 추론하지 않는다.

### 9.2 DailyContextResponse

요청 필드에 다음을 추가한다.

~~~text
- id: UUID
- local_date: date
- context_version: integer
- created_at: datetime
- updated_at: datetime
- availability_source_code: MANUAL | ROUTINE_DEFAULT
~~~

`available_slots`는 요청과 같은 규칙으로 반환한다. 미입력이면 `null`, 명시적 빈 선택이면 `[]`이며
`availability_source_code`가 두 상태를 구분한다. 두 필드 모두 하위 호환을 위해 선택 필드이고,
`availability_source_code`의 기본값은 `ROUTINE_DEFAULT`다. `CALENDAR`는 외부 캘린더 연동이
재개될 때만 나타나는 예약 값이며 현재 응답에 사용하지 않는다.

---

## 10. 결정 실행

### 10.1 DecisionCreateRequest

~~~json
{
  "local_date": "2026-08-06",
  "daily_context_id": "uuid",
  "expected_context_version": 2
}
~~~

서버가 해당 날짜에 유효한 활성 루틴, scheduled workout, 정책, 카탈로그 버전을 선택한다. 클라이언트가 정책 버전이나 에이전트 가중치를 지정할 수 없다.

필수 헤더:

~~~http
Idempotency-Key: uuid
~~~

체크인이 갱신되어 expected_context_version이 오래됐으면 409 STALE_CONTEXT를 반환한다.

### 10.2 DecisionResponse

Wave 6 구현 계약:

- `POST /api/v1/decisions`는 UUID 형식의 `Idempotency-Key`를 필수로 받고 생성 성공 시 201을 반환한다.
- `POST /api/v1/decisions`의 공개 응답은 실행 프로필과 무관하게 기존 `DecisionResponse` 계약을
  유지한다. `V3_EXECUTION_PROFILE` 기본값은 `LEGACY`이며, `SHADOW`도 legacy 응답을 유지한다.
  `DEMO`는 `APP_ENV=staging`에서만 V3 저장 결과를 응답으로 사용한다. `PRODUCTION`은 별도
  production promotion gate가 승인한 경우에만 V3를 사용하고 그렇지 않으면 legacy로 fail closed한다.
- `GET /api/v1/decisions/{decision_id}`는 인증 사용자 소유의 `COMPLETED` 결정만 반환한다.
- `GET /api/v1/decisions?local_date=YYYY-MM-DD`는 해당 날짜의 가장 최근 `COMPLETED` 결정을
  반환한다. 재시작한 클라이언트가 당일 결정을 복원하는 read 전용 경로이며 에이전트·narration을
  다시 실행하지 않는다. 저장된 결정이 없으면 `404 DECISION_NOT_FOUND`다. 응답 스키마는
  `GET /decisions/{decision_id}`와 동일하다.
- 네 proposal 중 누락 또는 `FAILED`가 있으면 `503 DECISION_FAILED`, 추가 입력이 필요하면
  `422 NEEDS_INPUT`을 반환하며 두 오류 응답 모두 plan을 포함하지 않는다.
- `BLOCKED`는 저장이 완료된 정상 결정 응답이지만 `final_plan=null`이다. Safety veto는
  Coordinator 결과와 무관하게 유지된다.
- 성공 응답은 decision run, 네 agent proposal, 후보와 항목, safety review, 공개 option 및
  Coordinator 결과가 동일 트랜잭션에 저장된 뒤에만 반환된다.
- 라우트는 LLM을 직접 호출하지 않는다. 선택적 narration은 decision 생성 시점에 서비스가 adapter로
  수행하고 결과 문구만 저장하며, `GET`은 저장된 문구를 읽는다. narration이 비활성이거나 실패하면
  검수된 템플릿 문구를 사용하고 `action_code`, `safety_status_code`, `final_plan`, option은 바뀌지
  않는다. `summary`, `public_agent_summaries[].summary`, `safety_summary.summary` 문자열만 영향을
  받으며 내부 prompt와 추론 과정은 응답에 포함하지 않는다.
- selection과 workout session 생성은 Wave 7 범위다.

~~~text
DecisionResponse
- decision_id: UUID
- local_date: date
- status_code: COMPLETED
- safety_status_code: PASS | REVISE | BLOCKED  # 성공 응답에서만 사용
- action_code: KEEP | DOWNSHIFT | CHANGE | RECOVERY | REST | STOP_AND_SEEK_HELP
- requested_duration_minutes: integer
- duration_adjustment_source_code: PROFILE | USER_OVERRIDE
- final_plan: WorkoutPlan | null
- options: DecisionOption[]
- reason_codes: string[]  # 최대 2개
- adjustment_reason_codes: string[] | null  # optional, 안전 조정이 적용된 공개 사유 코드
- summary: string
- guidance: Guidance | null
- public_agent_summaries: AgentSummary[] | null
- safety_summary: SafetySummary | null
- generation_mode_code: ORIGINAL | REGENERATED | null  # V3 additive optional
- decision_engine_code: DETERMINISTIC | LLM_MULTI_AGENT | DETERMINISTIC_FALLBACK | null
- root_decision_id: UUID | null  # V3 lineage, 원본에서는 self 또는 null
- parent_decision_id: UUID | null
- regeneration_sequence: integer | null  # 원본 0, 성공 재생성 1..2
- meaningful_difference_codes: string[] | null
- created_at: datetime

DecisionOption
- option_id: UUID
- option_code: FINAL_ROUTINE | REST
- action_code: action enum
- plan_id: UUID | null
- selectable: boolean
- blocked_reason_code: string | null

WorkoutPlan
- plan_id: UUID
- action_code: KEEP | DOWNSHIFT | CHANGE | RECOVERY
- training_type_code: string
- body_focus_code: string | null
- requested_duration_minutes: integer
- estimated_duration_seconds: integer
- estimated_calories_burned: number | null  # 체중 기반 추정치
- setup_seconds: integer
- warmup_seconds: integer
- cooldown_seconds: integer
- items: WorkoutPlanItem[]

WorkoutPlanItem
- plan_item_id: UUID
- exercise_id: UUID
- exercise_name: string
- sequence: integer
- tier_code: CORE | SUPPORT | OPTIONAL
- sets: integer
- reps: integer | null
- work_seconds: integer
- rest_seconds: integer
- transition_seconds: integer
- estimated_item_seconds: integer
- instruction_available: boolean
- mascot_animation_asset_key: string | null
- replacement_of_exercise_id: UUID | null

Guidance
- code: string
- title: string
- message: string
- tone_code: SERIOUS | NEUTRAL
~~~

`DecisionResponse.status_code=COMPLETED`는 결정 파이프라인이 종료되고 결정 기록이 저장되었다는 뜻이며, 운동 세션이나 개별 운동 블록의 완료를 뜻하지 않는다. 운동 수행 완료는 세션의 블록 체크 상태로 별도 판정한다.

최종 루틴은 사용자의 requested_duration_minutes를 변경하지 않고 반환한다. `estimated_duration_seconds`는 요청 초와의 차이가 300초 이내인 계획 중 차이가 가장 작은 값이어야 하며, 같은 차이면 더 긴 계획을 우선한다. 이 허용 범위는 계획 구성용 제약이며 실제 수행의 hard execution limit이나 완료 조건은 아니다. 검수된 후보와 안전 규칙만으로 ±5분 범위를 만족할 수 없으면 불필요한 운동으로 채우거나 범위를 넘긴 계획을 반환하지 않고 `NEEDS_INPUT` 또는 `BLOCKED`로 계획을 반환하지 않는다. `estimated_calories_burned`는 운동 종류·시간·강도와 사용자가 제공한 체중으로 계산한 추정치이며 체중이 없으면 null이다. 정밀 칼로리 계산이 아니고 진단 또는 안전 판정의 단독 근거로 사용하지 않는다. 사용자가 USER_OVERRIDE를 보내지 않은 상태에서 서버가 requested_duration_minutes를 변경하면 계약 위반이다.

`DecisionResponse.safety_status_code`에서 `PASS`는 승인된 계획, `REVISE`는 안전 조정이 반영된 계획, `BLOCKED`는 안전상 운동 계획이 없는 결정을 뜻한다. `NEEDS_INPUT`과 `FAILED`는 성공한 `DecisionResponse`의 safety status로 반환하지 않는다. 전자는 공통 오류 응답의 `error.code=NEEDS_INPUT`(422)과 누락된 machine-readable field 목록으로, 후자는 `error.code=DECISION_FAILED`(500 또는 503)로 반환하며 계획을 포함하지 않는다. 성공 응답의 safety_status가 `BLOCKED`이면 action은 REST 또는 STOP_AND_SEEK_HELP이고 plan은 null이다.

### 10.3 액션별 null 규칙

| action | final_plan | guidance |
|---|---|---|
| KEEP | 계획 | 선택 |
| DOWNSHIFT | 계획 | 선택 |
| CHANGE | 계획 | 선택 |
| RECOVERY | 저강도 회복 계획 | 필수 |
| REST | null | 필수 |
| STOP_AND_SEEK_HELP | null | 필수 |

STOP_AND_SEEK_HELP에는 option을 제공하지 않으며 `options`는 빈 목록이다. 서버가 REST를 권고한 응답은 `final_plan=null`이고 선택 가능한 `REST` option 하나를 둘 수 있다.

KEEP, DOWNSHIFT, CHANGE, RECOVERY에서는 `FINAL_ROUTINE` option을 정확히 하나 반환하고, 사용자가 운동 대신 쉴 수 있도록 `REST` opt-out을 추가할 수 있다. 이 REST option은 운동 계획이 아니므로 `plan_id=null`이며, 사용자의 휴식 선택은 서버의 원래 추천 action과 별도의 selection으로 저장한다.

### 10.4 REST 응답 예

~~~json
{
  "decision_id": "uuid",
  "local_date": "2026-08-06",
  "status_code": "COMPLETED",
  "safety_status_code": "BLOCKED",
  "action_code": "REST",
  "requested_duration_minutes": 40,
  "duration_adjustment_source_code": "PROFILE",
  "final_plan": null,
  "options": [],
  "reason_codes": ["SEVERE_DISCOMFORT"],
  "summary": "오늘은 운동을 쉬어주세요.",
  "guidance": {
    "code": "REST_AND_RECHECK",
    "title": "오늘은 운동을 쉬어주세요.",
    "message": "상태를 다시 확인한 뒤 다음 운동을 조정할게요.",
    "tone_code": "SERIOUS"
  },
  "public_agent_summaries": null,
  "created_at": "2026-08-06T10:05:00+09:00"
}
~~~

### 10.5 STOP_AND_SEEK_HELP 응답 규칙

- final_plan은 null
- options는 빈 목록
- tone_code는 SERIOUS
- 마스코트 애니메이션 키를 반환하지 않음
- 증상 원인이나 질환명을 반환하지 않음

### 10.6 [V3 backend API 구현, 기본 비활성] 사용자 수동 루틴 재생성

~~~http
POST /api/v1/decisions/{decision_id}/regenerations
Idempotency-Key: uuid
Content-Type: application/json
~~~

~~~json
{
  "expected_plan_id": "uuid",
  "expected_regeneration_sequence": 0
}
~~~

사용자는 상태, 사유 또는 `different` 자유 문구를 다시 입력하지 않는다. 서버는 소유권이 확인된 기존
decision에서 최소 input snapshot, `ConstraintEnvelope`, `ExercisePoolSnapshot`, 이전 plan signature와
lineage를 읽어 내부 `RegenerationContext`를 만든다. body의 plan과 sequence는 stale client가 다른
루틴을 기준으로 재생성하지 않게 하는 optimistic concurrency 값이다.

일반 성공은 새 `decision_id`를 가진 `DecisionResponse`와 HTTP 201이다. 새 run은
`generation_mode_code=REGENERATED`, 같은 `root_decision_id`, 직전 결과의 `parent_decision_id`, 증가한
`regeneration_sequence`를 가진다. 기존 decision을 덮어쓰지 않는다.

V3 graph는 Coordinator만 다시 호출하지 않고 Training·Recovery·Feasibility 세 Agent부터 실행한다.
이전 plan과 정확히 같은 결과는 금지하며 다음 중 하나 이상을 만족해야 한다.

- `CORE_EXERCISE_CHANGED`: 핵심 운동 하나 이상 변경
- `EXERCISE_ORDER_CHANGED`: 운동 순서의 실질적 변경
- `SET_REP_STRUCTURE_CHANGED`: 승인 범위 안의 세트·반복 구조 변경
- `ROUTINE_STRUCTURE_CHANGED`: 루틴 구성 방식 변경

application domain code와 공개 API code는 다음처럼 명시적으로 projection한다. domain enum과 저장 hash는
변경하지 않는다.

| domain code | API code |
|---|---|
| `CORE_EXERCISE_CHANGED` | `CORE_EXERCISE_CHANGED` |
| `SET_REPETITION_STRUCTURE_CHANGED` | `SET_REP_STRUCTURE_CHANGED` |
| `EXERCISE_SEQUENCE_CHANGED` | `EXERCISE_ORDER_CHANGED` |
| `ROUTINE_COMPOSITION_CHANGED` | `ROUTINE_STRUCTURE_CHANGED` |

설명·UUID·표시 순서 key 또는 미미한 시간 변경만으로는 의미 있는 차이로 인정하지 않는다. 새 plan은
동일한 Safety veto·제외, 요청 시간의 ±5분 범위, 목표, recovery ceiling, 장소, 승인 catalog를 만족하고
Plan Compiler와 integrity validator를 다시 통과해야 한다.

root decision당 성공 재생성은 최대 두 번이다. 같은 Idempotency-Key와 같은 요청은 저장된 응답을
반환하고, 같은 키의 다른 요청은 `409 IDEMPOTENCY_KEY_REUSED`다.

| 조건 | HTTP / error.code |
|---|---|
| plan 또는 sequence 불일치 | `409 STALE_REGENERATION` |
| snapshot/envelope/pool 만료 또는 version 불일치 | `409 REGENERATION_CONTEXT_STALE` |
| 성공 재생성 2회 초과 | `409 REGENERATION_LIMIT_REACHED` |
| terminal/safety 상태 또는 `final_plan=null`로 재생성 불가 | `409 REGENERATION_NOT_ALLOWED` |
| 안전하고 목표를 보존하는 의미 있는 대안 없음 | `422 NO_ALTERNATIVE_AVAILABLE` |
| 필수 LLM 실패 후 검증된 deterministic fallback도 없음 | `503 DECISION_FAILED` |
| V3 graph feature 비활성 | `503 V3_ENGINE_DISABLED` |
| DEMO/승인된 PRODUCTION에서 runtime 또는 필수 application adapter 미구성 | `503 V3_COMPOSITION_UNAVAILABLE` |

`STOP_AND_SEEK_HELP`, plan generation을 금지한 Safety veto와 `final_plan=null`인 decision은 재생성
대상이 아니다. REST opt-out을 사용자가 선택한 사실도 압박성 재생성 제안을 만들지 않는다.

현재 backend route, Pydantic/error projection 및 DEMO application composition이 구현됐지만 `v3_regeneration_enabled=false`가
기본값이다. production composition wiring과 frontend 버튼은 별도 승인·구현 전까지 비활성이다.

---

## 11. 옵션 선택

### 11.1 DecisionSelectionRequest

~~~json
{
  "option_id": "uuid"
}
~~~

서버는 option이 해당 decision 소유인지, selectable인지, 최신 안전 상태인지 확인한다.

안전 veto된 내부 후보 또는 STOP_AND_SEEK_HELP의 운동 선택 시도는 409 OPTION_NOT_SELECTABLE이다.

### 11.2 DecisionSelectionResponse

~~~json
{
  "selection_id": "uuid",
  "decision_id": "uuid",
  "option_id": "uuid",
  "selected_action_code": "DOWNSHIFT",
  "workout_session": {
    "session_id": "uuid",
    "status_code": "PLANNED"
  },
  "selected_at": "2026-08-06T10:06:00+09:00"
}
~~~

REST 선택에는 workout_session이 null이다. 이 경우 해당 local_date의 압박 알림 차단 상태가 함께 기록된다.

이 mutation은 UUID `Idempotency-Key` header가 필수다. 같은 키와 같은 요청은 최초의 selection 및
session 응답을 반환하며, 같은 키에 다른 `decision_id` 또는 `option_id`를 보내면
`409 IDEMPOTENCY_KEY_REUSED`를 반환한다. 이미 다른 키로 선택이 확정된 decision은
`409 DECISION_ALREADY_SELECTED`를 반환한다.

---

## 12. 운동 세션

### 12.1 시작

PATCH /api/v1/workout-sessions/{id}/start

요청 body:

~~~json
{
  "started_at": "2026-08-06T10:07:00+09:00"
}
~~~

PLANNED 세션만 시작할 수 있다.

UUID `Idempotency-Key` header가 필수다. 같은 키와 같은 시작 요청은 최초 응답을 반환한다.

응답은 `started_at`, 모든 운동 블록의 PENDING 상태, 첫 번째 current_plan_item_id를 반환한다. 클라이언트는 0초부터 증가하는 전체 경과 타이머를 시작하고 일시정지·재개를 로컬 상태로 관리한다. 서버는 이 타이머로 운동 완료를 판정하지 않는다.

### 12.2 운동 블록 완료

PATCH /api/v1/workout-sessions/{session_id}/items/{plan_item_id}

~~~json
{
  "status_code": "COMPLETED",
  "client_recorded_at": "2026-08-06T10:12:00+09:00"
}
~~~

허용 status는 `PENDING`, `COMPLETED`다. IN_PROGRESS 세션에서만 변경할 수 있으며 같은 상태로 보내는 요청은 멱등하다. PENDING은 최종 종료 전 사용자의 실수 취소에만 사용한다.

응답은 갱신된 블록, `completed_item_count`, `total_item_count`, `next_pending_plan_item_id`를 반환한다. 클라이언트의 체크 버튼·블록 격파·좌측 밀기는 동일한 mutation을 사용한다. 세트·반복·유산소 권장 시간과 경과 타이머는 이 상태를 자동 변경하지 않는다.

UUID `Idempotency-Key` header가 필수다. 이미 같은 상태인 블록에 대한 요청은 `completed_at`을
다시 쓰지 않고 현재 응답을 반환한다.

### 12.2.1 타이머 이력

POST /api/v1/workout-sessions/{session_id}/timer-events

요청의 `event_code`는 `START`, `PAUSE`, `RESUME`, `END` 중 하나이며 `occurred_at`과 클라이언트 기록 시각을 함께 저장한다. 이력은 수행 시간과 이용 패턴 분석용이며 운동 블록 상태나 공식 세션 상태를 변경하지 않는다.

~~~json
{
  "event_code": "PAUSE",
  "occurred_at": "2026-08-06T10:12:00+09:00",
  "client_recorded_at": "2026-08-06T10:12:01+09:00"
}
~~~

UUID `Idempotency-Key` header가 필수다. 성공 응답은 `event_id`, 저장 시각과 변경되지 않은
`session_status_code=IN_PROGRESS`를 반환한다.

### 12.2.2 추가 운동 기록

POST /api/v1/workout-sessions/{session_id}/additional-activities

계획 외 운동의 유형, 지속 시간, 강도와 선택 메모를 저장한다. 추가 운동은 공식 계획 블록 체크 상태를 변경하지 않으며 주간 패턴 분석과 리포트 입력으로만 사용한다.

~~~json
{
  "activity_type_code": "WALKING",
  "duration_seconds": 1200,
  "intensity_code": "LOW",
  "note": null
}
~~~

`duration_seconds`는 0보다 커야 하고 `note`는 최대 500자다. UUID `Idempotency-Key` header가
필수다. 성공 응답은 `activity_id`와 변경되지 않은 `session_status_code=IN_PROGRESS`를 반환한다.

Wave 7A의 start·block·timer·additional-activity mutation은 `ended_at`이 있거나 상태가
`COMPLETED`, `PARTIAL`, `NOT_COMPLETED`, `STOPPED_FOR_SAFETY`인 세션을 모두
`409 SESSION_ENDED`로 거부한다. 타이머 `END` 이벤트 자체는 공식 세션 종료가 아니다.

### 12.3 운동 중 안전 이벤트

POST /api/v1/workout-sessions/{id}/safety-events

~~~json
{
  "occurred_at": "2026-08-06T10:12:00+09:00",
  "discomforts": [
    {
      "body_area_code": "KNEE",
      "severity_code": "SEVERE"
    }
  ],
  "adverse_reaction_codes": []
}
~~~

응답:

~~~text
SafetyEventResponse
- event_id: UUID
- instruction_code: SHOW_CAUTION | STOP_SESSION | STOP_AND_SEEK_HELP
- resulting_action_code: REST | STOP_AND_SEEK_HELP | null
- session_status_code: IN_PROGRESS | STOPPED_FOR_SAFETY
- guidance_code: MILD_DISCOMFORT_CAUTION | MODERATE_DISCOMFORT_CAUTION | SEVERE_OR_ACUTE_STOP | SERIOUS_ADVERSE_REACTION_STOP
- guidance: Guidance
- pressure_notifications_allowed: boolean
~~~

`resulting_action_code`가 `REST` 또는 `STOP_AND_SEEK_HELP`이면
`pressure_notifications_allowed=false`이며, 해당 로컬 날짜의 추가 압박 알림 대상에서 제외한다.
안내 문구는 상태를 진단하거나 치료·처방하지 않고 중단과 도움 요청만 안내한다.

긴급 중단 그룹은 instruction_code=STOP_AND_SEEK_HELP와 resulting_action_code=STOP_AND_SEEK_HELP를 반환하고 세션을 STOPPED_FOR_SAFETY로 바꾼다.

SEVERE 또는 급성 근골격 신호는 instruction_code=STOP_SESSION과 resulting_action_code=REST를 반환하고 세션을 STOPPED_FOR_SAFETY로 바꾼다.

MILD 또는 MODERATE 입력에 대한 운동 중 재조정은 별도 검수된 동적 세션 규칙이 없으므로 MVP에서는 진행 중 계획을 자동 재작성하지 않는다. 이 경우 instruction_code=SHOW_CAUTION, resulting_action_code=null을 반환하고 검수 문구를 표시한다.

### 12.4 수행 종료

~~~json
{
  "finished_at": "2026-08-06T10:22:00+09:00",
  "actual_elapsed_seconds": 1734
}
~~~

IN_PROGRESS 세션만 `/finish`로 종료할 수 있다. 서버가 저장된 운동 블록 체크 상태를 비교해 공식 상태를 계산한다.

- 모든 운동 블록 완료 체크: COMPLETED
- 하나 이상의 블록 완료 체크와 하나 이상의 PENDING 블록: PARTIAL
- 완료 체크 블록 없음: `/finish`를 거부하고 `/not-completed`와 이유를 요구

응답은 server-derived `status_code`, 완료·전체 블록 수, 실제 경과 시간과 선택적 칼로리 추정치를 반환한다. `estimated_calories_burned`는 저장된 체중·운동 종류·시간·강도를 사용해 서버가 계산하는 응답 전용 값이며 클라이언트 요청으로 받지 않는다. `actual_elapsed_seconds`는 일시정지 구간을 제외한 화면 표시 카운터 값이며 상태 계산에 사용하지 않는다. 클라이언트는 최종 상태나 칼로리 추정치를 직접 지정할 수 없다. 칼로리 추정치는 참고 정보이며 안전·의료 판단에 사용하지 않는다.

### 12.5 미수행

~~~json
{
  "ended_at": "2026-08-06T10:07:00+09:00",
  "reason_code": "TIME_SHORTAGE"
}
~~~

허용 코드:

~~~text
TIME_SHORTAGE
FATIGUE
MUSCLE_SORENESS
PAIN
SCHEDULE_CHANGE
LOCATION_EQUIPMENT
WEATHER
DIFFICULTY
LOW_INTEREST
LOW_MOTIVATION
~~~

한 세션에 하나의 이유만 허용한다.

`/not-completed`는 PLANNED 또는 IN_PROGRESS 상태에서 호출할 수 있다. COMPLETED 블록이 하나라도 저장돼 있으면 PARTIAL 종료를 사용해야 하므로 409 INVALID_STATE_TRANSITION을 반환한다. 경과 시간이 길어도 완료 블록이 없으면 NOT_COMPLETED다.

### 12.6 운동 후 피드백

신규 공개 입력의 목표 계약은 한 필드만 사용한다.

~~~json
{
  "difficulty_code": "APPROPRIATE"
}
~~~

운동 후 체감 난이도 코드:

~~~text
EASY
APPROPRIATE
HARD
~~~

표시 문구는 `EASY=쉬웠어요`, `APPROPRIATE=적당했어요`, `HARD=어려워요`를 유지한다. 피드백은 종료
상태의 세션에 한 번만 저장하고 공식 수행 상태를 변경하지 않는다. 미수행 세션은 리포트 생성 전에
`/not-completed`의 `reason_code`를 먼저 저장해야 한다.

현재 구현의 `fatigue_code`, `satisfaction_code`, `pain_occurred`, `discomforts`,
`adverse_reaction_codes`는 즉시 삭제하지 않는다. 후속 호환 단계에서 다음 순서로 전환한다.

1. 기존 request를 계속 수용하고 기존 row/column과 read response를 보존한다.
2. 위 legacy field를 optional+deprecated로 바꿔 신규 client의 difficulty-only request를 허용한다.
3. legacy 값을 보낸 요청은 기존 의미로 저장하되 누락값을 추정하거나 `pain_occurred=false`로 채우지 않는다.
4. 신규 통증·이상 반응 입력은 유지되는 `/safety-events` API를 사용한다. feedback endpoint가 Safety
   Event를 대신 만들거나 안전 결과를 재분류하지 않는다.
5. 사용량·compatibility test와 프론트/백엔드 owner 승인 후 별도 migration/release에서 legacy write
   종료와 nullable/삭제를 검토한다. historical read와 주간 집계는 version으로 보존한다.

웨어러블 또는 외부 운동 API는 공식 세션 상태를 생성하거나 변경할 수 없다. 캘린더의 수행 여부 확인 결과도 공식 세션 상태를 생성하거나 변경할 수 없다.

---

### 12.7 운동 수행 기록 조회

GET /api/v1/workout-sessions
GET /api/v1/workout-sessions/{session_id}

본인의 운동 수행 기록을 조회한다. 사용자가 몇 개 블록까지 수행했는지, 어떤 강도를 선택했는지
확인하기 위한 계약이다.

목록 쿼리 파라미터는 모두 선택이다.

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `from_local_date` | date | 조회 시작일 |
| `to_local_date` | date | 조회 종료일 |
| `status_code` | string | 세션 상태로 필터 |
| `cursor` | string | 다음 페이지 커서 |
| `limit` | integer | 1~100, 기본 20 |

~~~text
WorkoutSessionListResponse
- items: WorkoutSessionSummary[]
- next_cursor: string | null

WorkoutSessionSummary
- session_id: UUID
- local_date: date
- status_code: string
- completed_item_count: integer
- total_item_count: integer
- requested_duration_minutes: integer
- training_type_code: string
- not_completed_reason_code: string | null
- started_at: datetime | null
- finished_at: datetime | null

WorkoutSessionDetailResponse
- session_id: UUID
- local_date: date
- status_code: string
- completed_item_count: integer
- total_item_count: integer
- requested_duration_minutes: integer
- items: WorkoutSessionItemResult[]
- feedback: WorkoutFeedbackSummary | null
- not_completed_reason_code: string | null
- started_at: datetime | null
- finished_at: datetime | null

WorkoutSessionItemResult
- plan_item_id: UUID
- exercise_id: UUID
- exercise_name: string
- status_code: string
- sets: integer
- reps: integer | null
- work_seconds_per_set: integer | null
- completed_at: datetime | null

WorkoutFeedbackSummary
- perceived_difficulty_code: string | null
- post_workout_discomfort_reported: boolean
~~~

- 본인의 기록만 반환한다. 다른 사용자의 `session_id`로 호출하면 `404 RESOURCE_NOT_FOUND`다.
  존재 여부를 알려주지 않기 위해 `403`을 쓰지 않는다.
- `completed_item_count`는 명시적 운동 블록 완료 기록만 센다. 경과 시간, 웨어러블 데이터,
  캘린더 확인 결과는 이 값에 영향을 주지 않는다.
- `perceived_difficulty_code`는 사용자가 고른 주관적 난이도이며 의료적 해석 대상이 아니다.
- 운동 후 불편의 상세 부위·심각도는 이 응답에 포함하지 않는다. 보고 여부만 노출한다.
- 타이머 이력과 추가 운동 기록은 이 계약에 포함하지 않는다. 필요해지면 별도 절로 추가한다.

---

## 13. 주간 리포트와 다음 계획

`week_start`는 사용자 timezone 기준 월요일의 `YYYY-MM-DD`다. 월요일이 아닌 날짜는 422 INVALID_WEEK_START다.

### 13.0 주 상태 조회

GET /api/v1/weeks/{week_start}

~~~json
{
  "week_id": "uuid",
  "week_start": "2026-08-03",
  "week_end": "2026-08-09",
  "timezone": "Asia/Seoul",
  "target_workout_count": 4,
  "plan_origin_code": "COLD_START",
  "cold_start_applied": true,
  "status_code": "CLOSED",
  "closed_at": "2026-08-09T15:00:00Z",
  "report_id": null,
  "report_status_code": null
}
~~~

서버는 요청 시 사용자 timezone의 현재 로컬 날짜를 계산한다. 일요일까지는 `OPEN`이며 다음
월요일 00:00이 되면 scheduler 없이 `CLOSED`로 논리 마감한다. 주가 처음 조회되는 시점의
timezone과 목표 횟수를 `user_weeks`에 스냅샷으로 저장한다.

### 13.1 리포트 생성

POST /api/v1/weeks/{week_start}/report

~~~json
{
  "expected_week_status_code": "CLOSED"
}
~~~

응답:

~~~json
{
  "report_id": "uuid",
  "week_start": "2026-08-03",
  "week_end": "2026-08-09",
  "status_code": "GENERATED",
  "counts": {
    "completed": 2,
    "partial": 1,
    "not_completed": 1,
    "stopped_for_safety": 0
  },
  "primary_miss_reason_code": "TIME_SHORTAGE",
  "completion_rate": 0.5,
  "persistence_rate": 0.75,
  "negotiation_success_rate": 1.0,
  "weekday_failure_summary": {},
  "pattern_summary": {
    "high_completion_windows": [],
    "high_completion_exercise_types": [],
    "high_completion_intensity_codes": [],
    "blocker_reason_codes": []
  },
  "decision_summary": "이번 주 조정 결과와 다음 주 반영 방향",
  "adjustment_direction_code": "MAINTAIN",
  "next_action": "다음 주 첫 운동을 희망 시간에 시작",
  "agent_summaries": null,
  "summary": "이번 주에는 계획 4회 중 2회를 완료하고 1회를 일부 수행했어요.",
  "acknowledged_at": null,
  "generated_at": "2026-08-10T09:00:00+09:00"
}
~~~

열린 주에는 409 WEEK_NOT_CLOSED를 반환한다. 같은 입력과 Idempotency-Key에는 기존 리포트를 반환한다. `pattern_summary`, `decision_summary`, `adjustment_direction_code`, `next_action`은 요구사항 기반 요약이며, `agent_summaries`의 상세 구조는 증상 사용자 시나리오 검증 결과에 따라 추후 보완할 수 있다. 내부 추론은 포함하지 않는다.

UUID `Idempotency-Key` header가 필수다. 서로 다른 키를 사용하더라도 동일한 닫힌 주의
`input_hash`가 같으면 저장된 동일 리포트를 반환한다. 리포트 생성 후 집계 입력이 달라지면
불변 리포트를 덮어쓰지 않고 409 `REPORT_INPUT_CHANGED`를 반환한다. 종료되지 않은 세션 또는
미수행 이유가 없는 `NOT_COMPLETED` 세션이 있으면 409 `WEEK_OUTCOMES_INCOMPLETE`를 반환한다.

`completion_rate`는 `COMPLETED / target_workout_count`, `persistence_rate`는
`(COMPLETED + PARTIAL) / target_workout_count`이며 1을 상한으로 한다.
`negotiation_success_rate`는 `DOWNSHIFT | CHANGE | RECOVERY`로 선택된 세션 중 하나 이상의
계획 블록을 완료한 `COMPLETED | PARTIAL` 비율이고 대상 세션이 없으면 null이다. 이 공식 상태와
비율에는 타이머·경과 시간·웨어러블·캘린더·추가 활동을 사용하지 않는다.

내부 집계의 `pain_report_count`는 신규 aggregate version부터 해당 주에 discomfort가 기록된 distinct
workout safety-event session 수를 사용한다. 한 session의 여러 event/부위는 한 번만 센다. legacy
`workout_feedback.pain_occurred=true`는 safety event가 없는 historical session에 한해 호환 집계하고
중복하지 않는다. onboarding pain과 daily context는 이 지표의 원천이 아니다. 이 내부 집계값을 public
response에 새로 노출하는 변경은 별도 API 승인 없이는 수행하지 않는다.

### 13.2 리포트 조회

GET /api/v1/weekly-reports/{report_id}

현재 사용자 소유의 생성된 리포트를 13.1과 같은 응답 구조로 반환한다. 리포트 조회는
acknowledgement를 암묵적으로 기록하거나 상태를 변경하지 않는다. 존재하지 않거나 다른 사용자
소유인 리포트에는 404 `WEEKLY_REPORT_NOT_FOUND`를 반환한다.

### 13.3 리포트 확인

POST /api/v1/weekly-reports/{report_id}/acknowledgement

~~~json
{
  "acknowledged_at": "2026-08-10T09:02:00+09:00"
}
~~~

확인은 명시적 mutation이며 멱등하다. 최초 가입자의 첫 주 계획은 이전 리포트 없이 생성할 수 있다. 그 이후 직전 주 리포트가 GENERATED 상태이면 다음 계획을 draft로 만들 수는 있어도 finalized 상태로 확정할 수 없다.

UUID `Idempotency-Key` header가 필수다. 최초 acknowledgement 시각만 저장하며 이후 재요청은
기존 `acknowledged_at`을 바꾸지 않고 `ACKNOWLEDGED` 리포트를 반환한다.

### 13.4 다음 계획 초기 생성

POST /api/v1/weeks/{week_start}/plan

UUID `Idempotency-Key` header가 필수이며 request body는 빈 객체다. `source_code`나 안전 상태는
클라이언트가 지정하지 않는다.

~~~json
{}
~~~

~~~text
InitialPlanResponse
- revision_id: UUID
- revision_sequence: integer
- ai_revision_count: 0
- source_code: INITIAL
- source_weekly_report_id: UUID | null
- safety_status_code: PASS | NEEDS_INPUT | REVISE | BLOCKED | FAILED
- routine: RoutineResponse | null
- selected_location_code: string | null
- finalized: boolean
- finalized_at: datetime | null
- revision_reason_codes: string[]
- finalization_reason_codes: string[]
- created_at: datetime
~~~

이 엔드포인트는 콜드스타트·최초 계획·다음 주 초기 계획만 생성한다. 서버는 사용자 이력과 주간 리포트 상태를 검증한 뒤 `revision_source_code=INITIAL`인 revision을 생성하며, AI 또는 USER 수정은 처리하지 않는다. 최초 가입자의 콜드스타트는 `source_weekly_report_id=null`로 생성할 수 있다.

직전 주 리포트가 `ACKNOWLEDGED`가 아니면 다음 주 초기 계획은 draft로 저장할 수 있지만 `finalized=false`만 허용한다. `finalized=true`는 콜드스타트 예외 또는 직전 주 리포트 `ACKNOWLEDGED` 상태이며, 동시에 `safety_status_code=PASS` 또는 `REVISE`, `routine!=null`인 경우에만 허용한다.

콜드스타트가 아닌 주에는 닫힌 직전 주 리포트가 필요하다. 리포트가 없으면 409
`PREVIOUS_WEEKLY_REPORT_REQUIRED`, 이미 초기 revision이 있으면 409
`INITIAL_PLAN_ALREADY_EXISTS`, 대상 주가 닫혔으면 409 `TARGET_WEEK_CLOSED`다.

### 13.5 다음 계획 수정

POST /api/v1/weeks/{week_start}/plan-revisions

UUID `Idempotency-Key` header가 필수다.

AI 수정 요청:

~~~json
{
  "source_code": "AI",
  "expected_revision_sequence": 1,
  "user_edits": null
}
~~~

USER 수정 요청:

~~~json
{
  "source_code": "USER",
  "expected_revision_sequence": 2,
  "user_edits": {
    "routine_id": "uuid",
    "location_code": "HOME"
  }
}
~~~

~~~text
PlanRevisionResponse
- revision_id: UUID
- revision_sequence: integer
- ai_revision_count: 0 | 1 | 2
- source_code: AI | USER
- source_weekly_report_id: UUID | null
- safety_status_code: PASS | NEEDS_INPUT | REVISE | BLOCKED | FAILED
- routine: RoutineResponse | null
- selected_location_code: string | null
- finalized: boolean
- finalized_at: datetime | null
- revision_reason_codes: string[]
- finalization_reason_codes: string[]
- created_at: datetime
~~~

이 엔드포인트는 기존 `INITIAL` 계획에 대한 `AI` 또는 `USER` 수정만 처리한다. `INITIAL` revision은 이 엔드포인트에서 생성하지 않으며 `/weeks/{week_start}/plan`에서만 생성한다.

`source_code=AI`는 LLM이 루틴을 생성하거나 선택한다는 뜻이 아니다. Training·Recovery·Safety·Feasibility proposal을 병렬 실행한 뒤 멀티에이전트 Coordinator가 요청 내용을 반영한 수정 루틴을 결정하는 서버 흐름이다. `source_code=USER`는 사용자의 직접 편집 흐름이다.

AI 수정은 Coordinator 권한의 서버 선택으로 최대 2회다. 서버가 현재 유효한 routine version을 선택하며 클라이언트는 AI 요청에 `user_edits`를 보낼 수 없다. 성공한 Coordinator 기반 수정 루틴만 `ai_revision_count`에 집계하며, 세 번째 AI 요청은 `409 AI_REVISION_LIMIT_REACHED`다. LLM은 reason code·조정 결과의 설명 문구를 생성하는 선택 기능일 뿐 수정 루틴·요청 시간·안전 상태·veto·후보 선택을 결정하거나 변경하지 않는다. LLM 장애 시 검수된 템플릿 설명을 사용하고 Coordinator 결정과 루틴은 유지한다.

USER 편집은 임의 운동 JSON 대신 사용자 소유의 저장된 routine version과 실행 장소를 참조한다. 서버는 routine의 모든 day가 요청 시간의 ±5분 범위를 만족하는지, 모든 운동이 선택 장소를 지원하는지, 저장된 최신 SafetyAgent 제외 운동과 의견을 반영했는지 다시 조회한다. 사용자 장비 보유 여부는 승인 조건이 아니다. 클라이언트가 안전 상태·의견 반영 코드를 제출할 수 없으며 독립적인 최종 Safety 재검사는 수행하지 않는다. 위반 시 422 `PLAN_REVISION_REJECTED`와 machine-readable reason code를 반환한다.

`NEEDS_INPUT`, `BLOCKED`, `FAILED` revision은 `routine=null`, `finalized=false`로 저장한다. `PASS` 또는 `REVISE` revision은 생성·편집된 routine이 있을 때만 `routine`을 반환하며, `finalized=true`는 콜드스타트 예외 또는 직전 주 리포트 `ACKNOWLEDGED` 상태이고 `safety_status_code=PASS` 또는 `REVISE`, `routine!=null`인 경우에만 허용한다.

`expected_revision_sequence`가 최신 값과 다르면 409 `STALE_PLAN_REVISION`이다. 동일 UUID
`Idempotency-Key`와 동일 요청은 저장된 응답을 반환하고, 같은 키의 다른 요청은 409
`IDEMPOTENCY_KEY_REUSED`다.

---

## 14. 공개 에이전트 요약

회의 UI는 MVP에 포함하며 다음 제한된 구조만 반환한다. 에이전트는 병렬로 실행할 수 있지만 `public_agent_summaries` 배열과 회의 UI의 표시 순서는 다음과 같이 고정한다.

1. `TRAINING`
2. `RECOVERY`
3. `SAFETY`
4. `FEASIBILITY`
5. `COORDINATOR`

클라이언트는 이 배열을 다른 기준으로 재정렬하지 않는다. 에이전트별 입력·판단 결과와 최종 조정 이유는 `summary`·`reason_codes`로 요약하되 내부 추론은 반환하지 않는다. 증상 사용자 시나리오 검증 결과에 따라 상세 필드는 추후 보완할 수 있다.

~~~text
AgentSummary
- agent_type_code: TRAINING | RECOVERY | SAFETY | FEASIBILITY | COORDINATOR
- recommendation_code: action enum
- reason_codes: string[]
- summary: string

SafetySummary
- safety_status_code: PASS | NEEDS_INPUT | REVISE | BLOCKED | FAILED
- vetoed: boolean
- reason_codes: string[]
- summary: string
~~~

반환 금지:

- 내부 프롬프트
- chain-of-thought 또는 숨은 추론
- 다른 사용자 데이터
- 원시 웨어러블 샘플
- 내부 점수와 보안 규칙 상세

`public_agent_summaries`는 위 고정 순서의 Training·Recovery·Safety·Feasibility·Coordinator 요약을 제공한다. Safety 요약은 SafetyAgent의 `safety_status_code`와 `vetoed` 의견을 나타내며, 독립적인 최종 Safety 재검사 결과는 제공하지 않는다.

V3 response에서도 기존 필드 타입은 유지한다. V1/V2 historical response는 위 다섯 요약을 그대로
반환한다. V3의 실제 LLM Agent는 Training·Recovery·Feasibility·Coordinator 네 개이며 Safety는
결정적 `SafetyPolicyEngine`이다. V3도 기존 순서와 길이를 유지하기 위해 세 번째
`agent_type_code=SAFETY`를 policy engine의 호환 projection으로 반환하며 이를 LLM proposal로
해석하지 않는다. `safety_summary`도 policy engine의 공개 가능한 상태·veto·reason code를 나타낸다.

---

## 15. 공통 오류

~~~json
{
  "error": {
    "code": "STALE_CONTEXT",
    "message": "체크인 정보가 변경되었습니다. 최신 상태로 다시 시도해주세요.",
    "details": [],
    "request_id": "uuid"
  }
}
~~~

| HTTP | 대표 코드 |
|---:|---|
| 400 | INVALID_REQUEST, INVALID_OAUTH_NONCE, INVALID_PKCE_VERIFIER, INVALID_IDENTITY_SCOPE |
| 401 | AUTHENTICATION_REQUIRED, INVALID_TOKEN, INVALID_PROVIDER_TOKEN, PROVIDER_TOKEN_EXPIRED, PROVIDER_ISSUER_MISMATCH, PROVIDER_AUDIENCE_MISMATCH, PROVIDER_SUBJECT_MISSING |
| 403 | ACCOUNT_DISABLED, AGE_REQUIREMENT_NOT_MET |
| 404 | RESOURCE_NOT_FOUND, ROUTINE_NOT_FOUND, DAILY_CONTEXT_NOT_FOUND |
| 409 | STALE_CONTEXT, STALE_PROFILE, INVALID_STATE_TRANSITION, OPTION_NOT_SELECTABLE, IDEMPOTENCY_KEY_REUSED, ROUTINE_VERSION_CONFLICT, AUTHORIZATION_CODE_REUSED, IDENTITY_ALREADY_LINKED, LAST_IDENTITY_UNLINK_FORBIDDEN, WEEK_NOT_CLOSED, REPORT_ACKNOWLEDGEMENT_REQUIRED, AI_REVISION_LIMIT_REACHED, CONSENT_REQUIRED, WEARABLE_NOT_CONNECTED, CALENDAR_NOT_CONNECTED, CALENDAR_EVENT_ALREADY_LINKED |
| 422 | INVALID_DOMAIN_CODE, INVALID_DURATION, ROUTINE_DURATION_UNAVAILABLE, ROUTINE_CONTENT_UNAVAILABLE, DUPLICATE_BODY_AREA, INVALID_DATE_OF_BIRTH, NEEDS_INPUT, INVALID_WEEK_START, INVALID_OAUTH_STATE, OAUTH_STATE_EXPIRED |
| 429 | RATE_LIMITED |
| 500 | INTERNAL_ERROR, DECISION_FAILED |
| 503 | DATABASE_UNAVAILABLE, AUTH_PROVIDER_UNAVAILABLE, PROVIDER_UNAVAILABLE, APPROVED_CATALOG_UNAVAILABLE, PROFILE_CONFIGURATION_UNAVAILABLE |

안전한 후보가 없어 REST를 정상 반환하는 것은 오류가 아니다.

오류 응답에 인증 토큰, 이메일, 전체 이름, 체크인 원문, 내부 prompt를 포함하지 않는다.

---

## 16. 권장 시간, 경과 시간과 재현성 계약

WorkoutPlan의 estimated_duration_seconds는 아래 항목 합계와 같아야 한다.

~~~text
setup_seconds
+ warmup_seconds
+ sum(item.work_seconds)
+ sum(item.rest_seconds)
+ sum(item.transition_seconds)
+ cooldown_seconds
~~~

- `requested_duration_minutes`: 사용자가 선택한 희망 시간. 서버가 임의 변경하지 않는다.
- `estimated_duration_seconds`: 계획 구성요소의 합계다. 요청 초와의 차이가 300초 이내인 승인 후보 중 차이가 가장 작은 값이며, 같은 차이면 더 긴 계획을 우선한다. 실제 수행의 hard execution limit이나 완료 조건은 아니다.
- `actual_elapsed_seconds`: 클라이언트가 0초부터 기록한 실제 경과 시간. 완료 판정에 사용하지 않는다.
- `estimated_calories_burned`: 사용자가 제공한 체중과 운동 종류·시간·강도로 계산한 추정치. 체중이 없으면 null이며 진단·안전 판정의 단독 근거가 아니다.

완료 판정의 유일한 근거는 저장된 운동 블록의 `PENDING/COMPLETED` 상태와 안전 중단 이벤트다.

서버는 decision마다 다음 버전을 저장하지만 public 응답에는 노출하지 않아도 된다.

- input schema
- routine
- catalog
- policy
- safety rules
- duration rules
- coordinator
- prompt와 model, LLM 사용 시에만
- V3에서는 ConstraintEnvelope, ExercisePoolSnapshot, LangChain/LangGraph contract, structured output,
  Coordinator attempt, compiler/validator와 fallback version

DB 저장에 실패한 decision 결과는 성공 응답하지 않는다.

---

## 17. 개인정보와 삭제

아래 보유·삭제 기간은 `ACCEPTED` ADR-0004의 승인된 기본 계약이다. 법률상 예외가 확인되거나 기간을 바꿀 때는 새 ADR과 관련 API·DB·운영 작업을 함께 갱신한다.

- direct identifier와 원시 건강 기록을 LLM에 전달하지 않는다.
- Agent와 Coordinator에 DB·repository·ORM·raw SQL Tool을 제공하지 않는다. application loader가
  사용자 범위를 확인하고 최소화 snapshot과 승인 exercise pool을 만든다.
- 웨어러블 연동 시 일 단위 최소 요약만 API로 받는다.
- GPS 전체 경로와 초 단위 심박 샘플은 받지 않는다.
- DELETE /me 후 사용자 연결 데이터의 운영 DB 삭제 목표는 7일이다.
- 백업 만료 최대치는 30일이다.
- 재식별 가능한 decision, proposal, feedback을 삭제 후 기본 보존하지 않는다.
- 비식별 집계는 개인과 다시 연결할 수 없어야 한다.
- 실제 출시 전 삭제와 백업 절차를 법률 또는 개인정보보호 담당자에게 검토받는다.
- 체크인 원자료는 28일, 웨어러블 원본은 24시간, 일별 요약·상세 수행·설문은 90일, 주간 리포트는 12개월을 기본 보유한다.
- 관리자 접속기록은 2년, 마스킹 오류 로그는 7일 보유한다. 동의 철회·연동 해제와 데이터 삭제는 별도 제어한다.

---

## 18. 선택한 대안과 제외한 대안

선택:

- 명시적 local_date와 context version
- 동기식 decision API
- option ID 기반 사용자 선택
- REST와 STOP_AND_SEEK_HELP의 null plan 계약
- Firebase ID Token 검증
- OpenAPI 기반 프론트 타입 생성

선택하지 않음:

- POST /decisions/today처럼 서버가 날짜를 암묵적으로 판단하는 경로
- 클라이언트가 에이전트 가중치와 운동 후보를 지정하는 요청
- 안전 거부 후에도 원래 계획을 강제 선택하는 API
- LLM이 생성한 자유 형식 계획 응답
- action_code가 REST 또는 STOP_AND_SEEK_HELP인데 final_plan이 null이 아닌 응답
- GraphQL과 비동기 decision job

---

## 19. 아직 확정되지 않은 계약

- primary_goal_code 전체 목록
- experience_level_code 전체 목록
- equipment, location, exercise type의 seed 코드
- 높은 피로 외 수면·부하 파생 규칙
- 운동 중 MILD 또는 MODERATE 불편에 대한 세션 재구성 정책
- 멀티 에이전트 로직 설계 후 공개 회의 UI의 agent summary 상세 필드
- 체중 기반 칼로리 추정 산식·계수 버전
- 후속 catalog code-set에서 추가할 training_type_code와 body_focus_code
- 운동 자세·설명 콘텐츠의 승인 및 버전 갱신 정책

## 20. 팀 확인 질문

- USER 계획 편집 request의 최소 필드와 낙관적 잠금 오류 코드는 무엇인지?
- 외부 안전 문구 검수 후 최종 copy version

이 항목을 확정할 때 기존 공개 필드를 깨지 않고 optional 필드 또는 새 버전으로 추가한다.
