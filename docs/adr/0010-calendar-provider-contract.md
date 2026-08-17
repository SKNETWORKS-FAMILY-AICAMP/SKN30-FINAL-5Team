# ADR-0010: Google Calendar 외부 컨텍스트 계약

- 상태: PROPOSED
- 날짜: 2026-08-14
- 최종 기술 검토: 2026-08-17
- 소유자: 개발팀장
- 승인자: 프론트엔드, 백엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항/이슈: `F011-1-1`~`F011-1-8`, `NFR-004`, `NFR-005`, Wave 9C
- 정책 버전: `external-context-policy-v2`
- schema: `calendar-availability-v1`, `calendar-performance-v2`, `calendar-credential-v1`

## 승인과 구현 게이트

이 문서는 9C-1의 정책 코어를 실제 9C-2 구현에 연결하기 위한 기술 계약 동결안이다. 필수 승인자가
확인해 상태를 `ACCEPTED`로 변경하기 전에는 API route, repository/model, migration과 Google HTTP
adapter를 구현하지 않는다. 승인 전 허용 범위는 문서, 결정적 domain rule, provider port,
unavailable/synthetic adapter와 contract/golden/privacy test다.

ADR이 `ACCEPTED`되면 credential이 없어도 기동하는 disabled/unavailable 구성으로 9C-2A~9C-2E를
구현할 수 있다. production Google 연동 활성화는 별도 운영 게이트다. 실제 OAuth client, 정확한 redirect
URI, secret-manager adapter와 경로, credential owner, consent-screen 검증 증적이 없으면
`CALENDAR_PROVIDER_ENABLED=false`를 유지한다.

## 배경

9C-1은 최소 scope, freebusy 정규화, 수동 폴백, completion 불변과 개인정보 경계를 고정했다. 그러나
기존 제안은 다음 구현 결정을 남겨 두었다.

- API는 `decision_id`·`option_id`, provider port와 DB는 `scheduled_workout_id`를 사용했지만 실제 선택
  흐름은 `workout_session_id`를 생성하고 `scheduled_workout_id`는 연결하지 않는다.
- OAuth transient row, rate-limit row, secret 보상 트랜잭션과 mutation 멱등성이 정의되지 않았다.
- `calendar.app.created` 보조 캘린더 이름과 연동 해제 후 원격 캘린더 처리 UX가 미정이었다.
- account deletion과 동의 철회에서 secret-manager 자격 증명을 제거하는 checkpoint가 필요했다.

## 결정

### 1. Provider, 조회 범위와 최소 OAuth scope

- 첫 provider code는 `GOOGLE_CALENDAR`다.
- Firebase Authentication과 동일한 Google Cloud project를 사용하되 Calendar authorization code flow는
  로그인 token과 별개로 처리한다.
- availability는 `POST https://www.googleapis.com/calendar/v3/freeBusy`와
  `https://www.googleapis.com/auth/calendar.freebusy`만 사용한다.
- MVP freebusy 대상은 literal `primary` 한 개다. secondary/shared calendar를 열거하지 않으며
  `calendarList.list`, event list, calendar title·description·location을 조회하지 않는다. 모든 캘린더를
  합산하는 기능은 `calendar.calendarlist.readonly`의 개인정보 영향 검토를 포함한 후속 ADR 대상이다.
- 운동 이벤트는 `https://www.googleapis.com/auth/calendar.app.created`로 앱이 만든 보조 캘린더에만
  생성한다. `calendar`, `calendar.readonly`, `calendar.events`, `calendar.settings.readonly`, profile,
  email, openid scope는 요청하지 않는다.
- authorization request는 `access_type=offline`, `include_granted_scopes=false`, PKCE S256을 사용한다.
  token 응답에서 두 필수 Calendar scope가 모두 허용됐는지 검사하고 부족하면 연결을 활성화하지 않는다.
  응답에 다른 scope가 있어도 adapter가 해당 API를 호출하거나 데이터를 소비하지 않는다.
- 사용자 timezone은 검증된 프로필 IANA timezone을 사용하고 Google settings endpoint를 호출하지 않는다.

Google 공식 scope 표는 `calendar.freebusy`가 free/busy 조회를, `calendar.app.created`가 앱이 만든
secondary calendar와 그 이벤트의 관리를 허용한다고 설명한다. FreeBusy 요청은 조회할 calendar ID
목록을 명시해야 하므로 최소 권한 MVP는 `primary`만 사용한다.

### 2. 보조 캘린더와 이벤트 UX

- 보조 캘린더의 고정 summary는 `헬끼 운동 일정`이다.
- 이벤트의 고정 summary는 `헬끼 운동`이다.
- 이벤트 payload는 `summary`, `start.dateTime`, `end.dateTime`, 각 IANA timezone만 포함한다.
  description, location, attendees, conferenceData, attachments, reminders override, recurrence, notes와
  extendedProperties를 보내지 않는다.
- 최초 연결마다 새 보조 캘린더를 한 개 만든다. 연결이 ACTIVE인 동안에는 같은 캘린더를 재사용한다.
- 연동 해제와 계정 삭제에서는 원격 보조 캘린더나 기존 이벤트를 자동 삭제하지 않는다. Google OAuth
  grant 전체 revoke도 수행하지 않는다. UI는 `헬끼 운동 일정`과 기존 이벤트가 Google Calendar에
  남으며 사용자가 Google Calendar에서 직접 숨기거나 삭제할 수 있음을 연동 해제 전에 안내한다.
- 재연결은 이전 캘린더를 찾기 위한 CalendarList scope를 추가하지 않고 새 보조 캘린더를 만든다.

### 3. 공식 운동 엔터티 연결

- calendar event link의 공식 FK는 `workout_session_id`다. `scheduled_workout_id`를 사용하지 않는다.
- `POST /api/v1/calendar/events`는 REST가 아닌 선택으로 이미 생성된, 사용자 소유 `PLANNED`
  workout session만 허용한다.
- client는 `workout_session_id`와 `start_at`만 보낸다. 서버가 선택된 계획의
  `requested_duration_minutes`로 `end_at`을 계산한다. Calendar가 운동 시간을 단축·연장할 수 없다.
- 한 workout session에는 event link가 최대 한 개다. 같은 idempotency key와 같은 요청은 최초 응답을
  반환하고, 다른 key로 이미 연결된 session은 `409 CALENDAR_EVENT_ALREADY_LINKED`다.
- performance gate는 `workout_sessions.status_code`의 공식 종료 상태
  `COMPLETED/PARTIAL/NOT_COMPLETED/STOPPED_FOR_SAFETY`를 사용한다. `scheduled_workouts` 상태나
  elapsed time, Calendar event 상태를 사용하지 않는다.
- Google은 수행 여부 필드를 제공하지 않으므로 performance는 provider HTTP 조회 없이 항상
  `performed=null`과 검수 안내를 반환한다. endpoint 호출 시각을 `performance_checked_at`으로
  기록하고 같은 link는 10분 뒤에만 재확인할 수 있다.

### 4. Normalized availability

- 사용자 IANA timezone의 `local_date` 00:00부터 다음 날 00:00까지 primary calendar freebusy를 조회한다.
- 응답에서는 `busy[].start`·`busy[].end`만 즉시 `ProviderBusyInterval`로 정규화한다. calendar ID,
  group/calendar error 원문과 전체 payload를 domain에 전달하지 않는다.
- 겹치거나 맞닿은 busy를 병합하고, 종일 여부를 시간 경계로 추정하지 않으며 provider가 반환한 모든
  구간을 busy로 처리한다.
- 후보 양쪽 15분 buffer를 제외한다. 남은 구간이 요청 운동시간보다 짧으면 후보에서 제외한다.
- 후보는 시작 시각 오름차순 최대 8개다. 없으면 빈 배열이며 요청 운동시간을 변경하지 않는다.
- 사용자의 명시적 수동 가능 시간은 명시적 빈 목록을 포함해 Calendar보다 항상 우선한다.
- availability는 on-demand이며 저장·cache하지 않는다. 따라서 stale 상태가 없고 성공 응답의
  `freshness_code`는 항상 `LIVE`다.

### 5. OAuth state와 모바일 callback

- Calendar flow는 9B 구현에 의존하지 않는다. 동일한 보안 primitive를 Calendar 전용 row와 service로
  독립 구현하며, 공통 유틸리티가 나중에 승인되면 동작 변경 없는 리팩터링만 허용한다.
- authorize-init은 server CSPRNG state, client PKCE S256 challenge, allowlist의 `redirect_uri_key`를
  사용한다. state는 600초, 1회용이다.
- DB에는 state SHA-256 digest, S256 challenge, redirect URI key, consent version과 시각만 저장한다.
  raw state, verifier, authorization code, redirect URI와 token은 저장하지 않는다.
- 사용자는 provider로 이동하기 전에 `CALENDAR_INTEGRATION` 동의가 활성 상태여야 한다.
- callback은 `authorization_code`, `state`, `code_verifier`를 전송한다. server는 row를 잠그고 user,
  state digest, redirect key, expiry와 verifier를 constant-time 비교한 뒤 provider 호출 전에 row를
  삭제·commit한다. 실패한 외부 교환은 row를 복구하지 않으며 새 authorize-init이 필요하다.
- 600초 경계 도달은 `422 OAUTH_STATE_EXPIRED`, 불일치·소비·미존재는
  `422 INVALID_OAUTH_STATE`, verifier 불일치는 `400 INVALID_PKCE_VERIFIER`다.
- 모바일은 state와 verifier를 OS 보안 저장소에 최대 600초만 보관하고 callback 직후 또는 실패·취소 시
  삭제한다. deep-link URL, analytics, crash report, clipboard, 일반 AsyncStorage와 로그에 넣지 않는다.
  값이 없거나 만료되면 callback을 교환하지 않고 새 연결을 시작한다.

### 6. Secret 경계와 보상 트랜잭션

- DB의 `token_secret_ref`는 `calendar-credential://{environment}/{connection_id}` 형태의 opaque
  logical reference다. 실제 cloud path나 ARN을 공개 API, 로그, metric에 넣지 않는다.
- production adapter는 승인된 secret-manager product/path를 logical reference에 매핑한다. 실제 adapter
  증적이 없으면 provider를 disabled로 유지한다.
- `calendar-credential-v1` secret payload에는 refresh token, 앱 보조 calendar ID, 허용된 scope code,
  생성·갱신 시각만 허용한다. access token은 요청 메모리에서만 사용한다. provider subject, email,
  calendar/event 본문과 raw token response를 넣지 않는다.
- token exchange와 보조 캘린더 생성 뒤 secret 저장이 실패하면 ACTIVE connection을 만들지 않는다.
- secret 저장 뒤 DB commit이 실패하면 새 secret을 즉시 파기하고, 같은 access token으로 방금 만든 보조
  캘린더 삭제를 best-effort 수행한다. 이 보상 실패는 식별정보 없는 운영 경보로 남기고 성공 연결을
  반환하지 않는다.
- refresh token 갱신은 새 secret version 기록이 성공한 뒤 이전 version을 폐기한다. provider
  `invalid_grant`는 secret을 파기하고 connection을 `REVOKED`로 만든 뒤 `CALENDAR_NOT_CONNECTED`를
  반환한다.

### 7. Persistence 계약

9C-2 migration은 additive하게 다음 typed table을 추가한다.

`calendar_connections`

- UUID PK, `user_id` FK CASCADE, `provider_code`, nullable `provider_subject`, nullable
  `token_secret_ref`, `status_code`, `granted_at`, nullable `revoked_at`, created/updated timestamps
- status는 `ACTIVE/REVOKE_PENDING/REVOKED`다. ACTIVE만 secret ref가 필수이고 REVOKED는 secret ref가
  null이며 revoked_at이 필수다.
- `(user_id, provider_code)` ACTIVE partial unique index와 `token_secret_ref` unique를 둔다.
- Google Calendar는 openid/profile scope를 요청하지 않으므로 `provider_subject`는 항상 null이다.

`calendar_event_links`

- UUID PK, `calendar_connection_id` FK CASCADE, `workout_session_id` FK CASCADE,
  `external_event_id`, `start_at`, `end_at`, nullable `performed`, nullable
  `performance_checked_at`, created/updated timestamps
- `workout_session_id` unique, `(calendar_connection_id, external_event_id)` unique, `end_at > start_at`
- Google row의 performed는 null만 허용한다.

`calendar_oauth_requests`

- UUID PK, `user_id` FK CASCADE, provider code, unique state SHA-256 digest, redirect URI key,
  PKCE S256 challenge, consent version, created/expires timestamps
- `(user_id, provider_code)` unique로 한 사용자·provider당 미소비 flow는 하나만 둔다. 새 init은 이전
  row를 삭제하고 대체한다. 만료 row는 최대 24시간 이내 운영 cleanup 대상이다.

`calendar_rate_limit_counters`

- `user_id` FK CASCADE, `bucket_code` (`TOTAL/AVAILABILITY`), count, window start/end, updated timestamp
- `(user_id, bucket_code)` PK, non-negative count와 유효 window CHECK
- row lock 또는 원자 upsert로 증가시키고 provider 호출 transaction과 분리 commit한다. provider 실패로
  사용량을 rollback하지 않는다.

### 8. Rate limit과 오류

- authorize-init, connection exchange, availability, event create, performance는 사용자별 전체
  60회/시간 fixed window에 포함한다. availability는 추가로 30회/시간이다.
- limit은 provider 호출 전에 원자 적용한다. 초과 시 provider를 호출하지 않고
  `429 RATE_LIMITED`와 `Retry-After`를 반환한다.
- Google 401/invalid_grant는 연결을 revoke하고 `409 CALENDAR_NOT_CONNECTED`다.
- 사용자 scope 거부와 부족은 `409 CALENDAR_NOT_CONNECTED`, Google 403 permission denial은 같은 code다.
- Google 403/429 usage limit, timeout, transport와 5xx는 raw body 없이
  `503 PROVIDER_UNAVAILABLE`다. 자동 재시도는 이 요청 안에서 하지 않는다.
- provider 장애는 기존 workout plan, manual check-in, block completion과 safety veto를 변경하지 않는다.

### 9. Public API와 멱등성

- `POST /api/v1/calendar/connection/authorize-init`: raw state를 저장하지 않으므로 idempotency response를
  보관하지 않는다. 호출마다 이전 미소비 row를 폐기하고 새 600초 state를 발급한다. client는 요청 중
  재호출을 막고 마지막 응답만 보관한다.
- `POST /api/v1/calendar/connection`: OAuth state 자체가 1회용 mutation key다. 성공 여부와 관계없이
  provider 호출 전에 state를 소비하므로 재사용은 `422 INVALID_OAUTH_STATE`다. ACTIVE 연결 상태에서
  새 authorize-init은 `409 INVALID_STATE_TRANSITION`으로 거부한다.
- `GET /api/v1/calendar/connection`: ACTIVE/REVOKE_PENDING 상태를 조회한다. 연결이 없거나 REVOKED면
  `404 CALENDAR_NOT_CONNECTED`다.
- `GET /api/v1/calendar/availability`: read endpoint지만 rate limit을 적용한다.
- `POST /api/v1/calendar/events`: UUID `Idempotency-Key` 필수.
- `GET /api/v1/calendar/performance`: read endpoint지만 10분 recheck와 rate limit을 적용한다.
- `DELETE /api/v1/calendar/connection`: 별도 key 없이 현재 connection 기준 멱등이다. 이미 없거나
  REVOKED여도 성공 no-op response를 반환한다.

### 10. 연동 해제, 동의 철회와 계정 삭제

- 연동 해제는 DB에서 `REVOKE_PENDING`으로 전환해 provider 접근을 먼저 차단하고, secret-manager
  credential을 파기한 뒤 `REVOKED`, `token_secret_ref=null`, `revoked_at`으로 확정한다.
- secret 파기 실패는 `REVOKE_PENDING`을 유지하고 재실행할 수 있다. 이 상태에서도 provider 호출은
  금지한다.
- Calendar 해제에서 Google token revoke endpoint를 호출하지 않는다. Google은 같은 project에 부여된
  grant의 모든 scope를 함께 revoke할 수 있어 Firebase Google 로그인에 영향을 줄 수 있기 때문이다.
- `CALENDAR_INTEGRATION` 동의 철회는 같은 revoke-pending checkpoint를 시작한다. 동의가 false가 되는
  순간부터 cleanup 결과와 무관하게 provider 호출을 금지한다.
- 계정 삭제는 user-linked Calendar row를 hard delete하기 전에 모든 Calendar secret 파기를 완료해야
  한다. secret-manager 장애는 로컬 개인정보 삭제 deadline 위험으로 처리하고 account-deletion job을
  재시도하며, 식별정보 없는 운영 incident로 에스컬레이션한다. 원격 보조 캘린더 삭제나 Google grant
  revoke는 계정 삭제 완료 조건이 아니다.

## 검토한 대안

- CalendarList readonly scope로 모든 calendar ID를 열거
- primary calendar에 직접 운동 이벤트 생성
- event/Calendar 상태를 수행 완료로 해석
- scheduled_workouts에 Calendar link를 연결
- token 원문 또는 secondary calendar ID를 PostgreSQL에 저장
- 연동 해제에서 Google OAuth revoke 호출
- 원격 보조 캘린더를 자동 삭제

## 선택하지 않은 이유

CalendarList는 제목·설명·위치 같은 추가 개인정보 면을 열고, primary calendar 직접 쓰기는 앱이 만든
데이터 경계를 약화한다. `workout_session`만이 현재 공식 block completion과 안전 중단 상태를 가진다.
token·calendar ID의 DB 저장은 secret 경계를 우회하며, Google revoke는 같은 project의 로그인 grant에
영향을 줄 수 있다. 원격 calendar 자동 삭제는 실패·복구와 사용자 소유 데이터 삭제 UX를 불필요하게
복잡하게 만든다.

## 결과와 영향

- Calendar availability는 primary calendar만 반영하므로 사용자의 다른 shared/secondary calendar
  일정은 MVP 후보 계산에 포함되지 않는다. UI에 이 제한을 표시한다.
- workout session을 직접 참조해 공식 completion과 performance gate의 상태 불일치를 제거한다.
- DB·secret-manager 이중 쓰기는 명시적인 보상과 revoke-pending 상태가 필요하다.
- production 활성화는 credential·secret-manager·redirect URI 증적이 준비될 때까지 차단된다.

## 승인 체크리스트

- [ ] 프론트엔드: primary-only 안내, 600초 secure callback, disconnect 잔존-calendar UX
- [ ] 백엔드: API·DB·transaction·idempotency 계약
- [x] 개발팀장: workout-session 연결, 최소 scope, safety/completion/privacy 경계
- [ ] PM·개인정보: 고정 calendar/event 명칭, primary-only, 잔존 원격 calendar 안내
- [ ] 운영: OAuth client/redirect URI, secret-manager adapter/path/owner, test project 증적

모든 필수 항목이 확인된 뒤에만 상태를 `ACCEPTED`로 바꾼다. 체크되지 않은 항목을 승인으로 추정하지
않는다.

## 후속 작업

1. 필수 reviewer가 본 계약을 검토하고 ADR 상태를 결정한다.
2. ACCEPTED 뒤 TASK-BACKEND-007의 9C-2A persistence부터 순차 구현한다.
3. Google test project에서 최소 scope, primary freebusy, 보조 캘린더 생성, quota 오류와 local
   disconnect 뒤 Firebase 로그인이 유지되는지 검증한다.
4. production 활성화 전 운영 credential/secret-manager 증적과 개인정보 검토를 연결한다.

## 공식 근거

- https://developers.google.com/workspace/calendar/api/auth
- https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/workspace/calendar/api/guides/quota
- https://developers.google.com/workspace/calendar/api/guides/errors
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/protocols/oauth2/resources/best-practices
- https://developers.google.com/identity/protocols/oauth2/javascript-implicit-flow#oauth_2.0_endpoints
