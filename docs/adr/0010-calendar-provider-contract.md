# ADR-0010: Google Calendar 외부 컨텍스트 계약

- 상태: PROPOSED
- 날짜: 2026-08-14
- 소유자: 개발팀장
- 승인자: 프론트엔드, 백엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항/이슈: `F011-1-1`~`F011-1-8`, `NFR-004`, `NFR-005`, Wave 9C
- 정책 버전: `external-context-policy-v1`

## 구현 게이트

이 ADR은 Google Calendar 정책 코어와 계약 제안이다. 필수 승인자가 확인해 상태를 `ACCEPTED`로
변경하기 전에는 실제 Google HTTP adapter, API route, repository/model, credential 등록과 migration을
구현하지 않는다. 승인 전에는 문서, 결정적 domain rule, provider port, unavailable 합성 adapter와
contract/golden/privacy test만 허용한다.

## 배경

ADR-0003과 ADR-0006은 캘린더를 선택적 일정 보조 경로로 확정했지만 provider, OAuth, 최소 scope,
빈 시간 계산, rate limit, stale 기준과 반복 연결에 필요한 credential 참조를 확정하지 않았다.
Wave 9C-1은 Google Calendar API v3를 첫 provider로 선택하고 실제 provider 호출 전에 개인정보 경계와
결정적 정책을 고정한다.

## 결정

### Provider와 최소 OAuth scope

- provider code는 `GOOGLE_CALENDAR`이며 iOS/Android Expo Development Build를 지원한다.
- Firebase Authentication과 동일한 Google Cloud project를 재사용하고 별도 project를 만들지 않는다.
- availability는 `POST https://www.googleapis.com/calendar/v3/freeBusy`만 호출하며
  `https://www.googleapis.com/auth/calendar.freebusy`만 요청한다.
- 이벤트 등록·확인은 `https://www.googleapis.com/auth/calendar.app.created`만 요청한다. 이 scope는
  앱이 만든 보조 캘린더와 그 이벤트만 관리하므로 9C-2는 전용 보조 캘린더를 생성해 사용해야 한다.
- 이벤트 목록, 제목, 설명, 참석자, 위치, organizer, creator와 캘린더 본문을 조회하지 않는다.
- 사용자 timezone은 프로필의 검증된 IANA timezone을 사용한다. Google settings 조회에 필요한
  `calendar.settings.readonly` scope는 요청하지 않는다.

### Provider 공식 계약 확인

Google 공식 문서를 2026-08-14에 확인했다.

- freebusy endpoint와 busy 응답은 `busy[].start`·`busy[].end`만 제공한다.
- `calendar.app.created`는 보조 캘린더 생성과 그 캘린더 이벤트의 조회·생성·변경·삭제를 허용한다.
- 이벤트 외부 식별자는 Event resource의 `id`이며 5~1024자다. `iCalUID`와 혼용하지 않는다.
- Event resource의 상태는 `confirmed`, `tentative`, `cancelled`이며 운동 수행 여부 필드는 없다.
  삭제·취소·참석 응답을 미수행으로 추정하지 않고 Google Calendar의 `performed`는 항상 `null`이다.
- Google quota는 per-project/per-user sliding window를 사용하고 초과 시 `403` 또는 `429 usageLimits`가
  가능하다. provider quota 오류는 원문 없이 `PROVIDER_UNAVAILABLE`로 처리한다.
- token revoke는 `POST https://oauth2.googleapis.com/revoke`다. 성공은 200이며 revoke는 동일 project에
  부여된 OAuth scope와 token에 폭넓게 영향을 줄 수 있다. Firebase 로그인과 동일 project를 공유하는
  현재 구조에서는 Calendar 단독 해제에 이 endpoint를 사용하지 않는다.
- Google 사용자 timezone 경로는 `GET /calendar/v3/users/me/settings/timezone`이지만 별도
  `calendar.settings.readonly` scope가 필요하므로 사용하지 않는다.

공식 근거:

- https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- https://developers.google.com/workspace/calendar/api/auth
- https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/workspace/calendar/api/v3/reference/events
- https://developers.google.com/workspace/calendar/api/guides/quota
- https://developers.google.com/workspace/calendar/api/guides/errors
- https://developers.google.com/workspace/calendar/api/v3/reference/settings/get
- https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke

### Raw 데이터와 동기화

- freebusy 원본과 event 원본 payload는 저장하지 않는다. raw 보유기간은 0시간이다.
- access/refresh token 원문은 DB, cache, log, metric, trace, snapshot과 fixture에 저장하지 않는다.
- `calendar_connections.token_secret_ref`에는 secret manager 참조만 저장한다.
- on-demand pull만 허용하고 availability를 cache하지 않는다. webhook, push, polling worker,
  scheduler를 도입하지 않는다.
- availability는 cache가 없으므로 stale 판정이 없다.

### 빈 시간 계산

- 사용자 IANA timezone의 요청 `local_date` 00:00부터 다음 날 00:00까지를 조회한다. 시간대 필터와
  특정 요일 강제를 적용하지 않는다.
- freebusy의 겹치거나 맞닿은 busy 구간은 하나로 병합한다.
- Google freebusy 응답에는 종일 여부가 없으므로 종일 일정을 정확히 식별할 수 없다. 개인정보 최소화
  우선 결정에 따라 freebusy가 반환한 종일 포함 모든 구간을 busy로 처리한다. 자정 경계로 종일 여부를
  추정하지 않는다.
- 후보 운동 구간 앞뒤에 각각 15분 buffer를 둔다. 빈 구간이 사용자 희망 운동시간과 buffer 30분을
  수용하지 못하면 후보에서 제외한다.
- 후보는 시작 시각 오름차순으로 하루 최대 8개다.
- 후보가 없어도 빈 배열을 반환하고 사용자 희망 운동시간을 임의 단축하지 않는다.
- 사용자가 수동 가능 시간을 명시하면 명시적 빈 목록을 포함해 calendar 후보보다 항상 우선한다.
- DST 날짜는 로컬 자정 두 개를 UTC instant로 변환해 실제 23시간 또는 25시간 경계를 보존한다.

### 동의, 연결, rate limit과 performance

- `CALENDAR_INTEGRATION` 동의가 없거나 철회되면 연결·조회·등록·확인을 호출하지 않는다.
- 권한 거부, 미연결, timeout, 5xx와 quota 장애에도 수동 체크인과 앱 운동 블록 체크를 유지하고
  운동 계획을 삭제·변경하지 않는다.
- 사용자별 availability는 30회/시간, calendar endpoint 전체는 60회/시간 fixed window다. 초과 시
  provider 호출 전에 `429 RATE_LIMITED`다.
- performance 확인은 공식 `scheduled_workouts.status_code`가 종료 상태가 된 뒤에만 허용한다.
  같은 link의 재확인은 `performance_checked_at`부터 10분 이후에만 허용한다.
- Google Calendar performance는 항상 `performed=null`과 fallback 안내를 반환한다. provider 결과는
  공식 `COMPLETED/PARTIAL/NOT_COMPLETED/STOPPED_FOR_SAFETY`를 생성하거나 변경할 수 없다.

### 연결 해제와 계정 삭제

- `DELETE /api/v1/calendar/connection`은 로컬 상태를 `REVOKED`로 바꾸고 `revoked_at`을 기록한 뒤
  secret manager token을 폐기한다. 반복 요청은 성공 no-op이다.
- Firebase 로그인과 동일한 Google Cloud project에서는 Calendar 단독 provider revoke를 호출하지 않는다.
- 계정 삭제는 새 상태 없이 ADR-0008의 provider revocation checkpoint를 재사용한다.

### OAuth state와 credential 경로

- `calendar_connections`에 nullable `token_secret_ref`를 추가한다. token 원문은 저장하지 않는다.
- calendar OAuth는 9B의 server-issued state·PKCE S256 메커니즘을 재사용한다. state는 600초,
  1회용이며 DB에는 SHA-256 digest와 PKCE challenge만 저장한다.
- identity OAuth table과 의미를 섞지 않고 9C-2 migration에서 calendar 전용 transient row를 additive하게
  추가한다. raw state, verifier, code와 token은 저장하지 않는다.
- 공개 계약에는 `POST /api/v1/calendar/connection/authorize-init`을 additive하게 제안하고,
  `CalendarConnectionRequest`에 `state`와 `code_verifier`를 추가한다. 승인 전 route는 구현하지 않는다.

## 결정 이유

freebusy-only 설계는 일정 본문을 애초에 가져오지 않아 비저장 규칙을 구조적으로 보장한다. 앱의
엄격한 fixed window는 provider quota보다 먼저 과도한 호출을 차단한다. provider performance를 공식
수행 상태와 분리하면 캘린더 삭제·취소를 운동 미수행으로 오해하지 않는다.

## 검토한 대안

- event list를 조회해 종일 일정을 식별
- 자정~자정 busy 구간을 종일 일정으로 추정
- Google Calendar 상태나 삭제를 운동 수행 여부로 해석
- Google settings scope를 추가해 timezone 조회
- availability cache, polling 또는 push 동기화
- token 원문을 PostgreSQL에 저장

## 선택하지 않은 대안과 이유

event list와 settings scope는 개인정보 표면을 넓힌다. 시간 경계 추정은 실제 24시간 일정과 구분할 수
없다. 일정 상태는 운동 수행 증거가 아니다. cache와 background sync는 stale·운영 복잡성을 만들며
MVP on-demand 계약에 필요하지 않다. token 원문 저장은 secret 경계를 위반한다.

## 결과와 영향

`external-context-policy-v1`, `calendar-availability-v1`, `calendar-performance-v1` 결정 규칙과
schema, provider port, unavailable/synthetic adapter와 golden/privacy test를
9C-1에서 추가한다. API route, DB model, migration과 Google HTTP adapter는 ADR 승인 뒤 9C-2에서
추가한다. 기존 API 필드를 삭제하거나 기존 completion 상태를 변경하지 않는다.

## 보안·개인정보·호환성 영향

normalized availability와 nullable performance 외 calendar 원문을 application 경계로 전달하지 않는다.
observability는 allowlist field만 허용한다. 제안 API와 DB 필드는 additive이며 승인·migration 전에는
production 계약으로 사용하지 않는다. 동일 project의 Firebase 로그인 grant를 보호하기 위해 Calendar
단독 remote revoke를 금지한다.

## 아직 확정되지 않은 사항

- `calendar.app.created` 전용 보조 캘린더의 고정 사용자 표시 이름과 삭제 UX
- secret manager의 실제 product/path와 운영 credential owner 증적
- 모바일 callback이 600초 state와 verifier를 보관·반환하는 최종 UI 계약

## 후속 작업

1. 프론트엔드·백엔드·개발팀장·PM/개인정보·운영 검토 후 ADR 상태를 결정한다.
2. ACCEPTED 뒤 TASK-BACKEND-007의 9C-2 route, service, repository, migration과 Google adapter를 구현한다.
3. Google test project에서 최소 scope, 전용 보조 캘린더, quota와 local disconnect 뒤 Firebase 로그인
   유지 여부를 검증한다.
