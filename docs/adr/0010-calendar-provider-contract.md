# ADR-0010: Google Calendar 외부 컨텍스트와 수동 폴백 계약

- 상태: PROPOSED
- 날짜: 2026-08-14
- 소유자: 개발팀장
- 승인자: 프론트엔드, 백엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항/이슈: `F011-1-1`~`F011-1-8`, `NFR-005`, `NFR-006`, Wave 9C-1
- 정책 버전: `external-context-policy-v1`
- schema version: `calendar-availability-v1`, `calendar-performance-v1`

## 구현 게이트

이 ADR은 Google Calendar 정책 코어와 provider-neutral 계약 제안이다. 필수 승인자가 확인해 상태를
`ACCEPTED`로 변경하기 전에는 Google API 호출, OAuth token 교환, route, repository, migration,
credential 또는 frontend permission UI를 구현하지 않는다. 이번 Wave 9C-1은 결정적 규칙,
provider port, unavailable/synthetic adapter와 합성 테스트까지만 허용한다.

## 배경

ADR-0003은 캘린더를 보조 경로로, ADR-0006은 캘린더 수행 여부를 공식 완료 근거에서 분리했다.
하지만 provider, OAuth state, 최소 scope, 빈 시간 계산, raw payload, 호출 제한, 수행 여부 미지원과
연결 해제의 실제 경계는 남아 있었다. Google Calendar API v3를 MVP 첫 calendar provider로 정하고
실제 adapter 전에 최소 정규화 표면과 수동 폴백을 고정한다. WEARABLE은 Wave 9D로 분리한다.

## 결정

### provider와 최소 scope

- provider code는 `GOOGLE_CALENDAR`다.
- Firebase와 동일한 Google Cloud project를 사용하고 새 project를 만들지 않는다.
- availability는 `POST https://www.googleapis.com/calendar/v3/freeBusy`와
  `https://www.googleapis.com/auth/calendar.freebusy`만 사용한다.
- 이벤트 목록을 조회하지 않는다. 앱은 `https://www.googleapis.com/auth/calendar.app.created`로
  만든 전용 보조 캘린더와 그 안의 운동 일정만 생성·관리한다.
- timezone은 온보딩에 저장된 사용자 IANA timezone을 사용한다. Calendar settings 조회와
  `calendar.settings.readonly` scope는 요청하지 않는다.
- iOS/Android Expo Development Build는 PKCE S256과 등록된 안전한 app/universal-link redirect를
  사용한다. Expo Go/auth proxy와 임의 custom URI에 의존하지 않는다.

### OAuth state와 credential

- `[예약] POST /api/v1/calendar/connection/authorize-init`이 server-generated UUIDv4 flow,
  CSPRNG state, 600초 만료와 authorization URL을 반환한다.
- client는 43~128자 verifier로 S256 challenge를 만들고 init에서 challenge를, connection 완료에서
  raw `state`와 `code_verifier`를 보낸다.
- DB에는 user/flow UUID, provider code, state·redirect URI SHA-256, S256 challenge, 생성·만료 시각만
  저장한다. state는 1회용이며 expiry·state·redirect·verifier 검증 뒤 provider 교환 전에 삭제·commit한다.
- authorization code, raw state/verifier, access/refresh token은 DB·cache·로그에 저장하지 않는다.
- `calendar_connections.token_secret_ref`에는 secret manager 참조만 저장한다.

### availability와 개인정보

- 공개 정규화 응답은 `local_date`, IANA `timezone`, `slots[].start_at/end_at`만 가진다.
- freebusy 응답은 요청 메모리에서 `start/end` 구간으로 축소하고 저장·cache·LLM 입력에 사용하지 않는다.
- title/summary, description, attendees, location, conference/meeting link, notes, calendar/event 원본
  payload와 calendar ID를 수집·저장·로그·snapshot에 포함하지 않는다.
- freebusy는 busy 구간의 종일 여부를 제공하지 않으므로 반환한 모든 구간을 busy로 취급한다.
- on-demand pull만 사용하며 availability cache, stale 상태, webhook, push, polling, worker와 scheduler를
  만들지 않는다.

### 빈 시간 계산

- 조회 범위는 사용자 IANA timezone의 요청 `local_date` 00:00부터 다음 날 00:00까지다.
- 시간대 필터와 특정 요일 강제는 적용하지 않는다.
- 범위 밖 busy는 잘라내고 겹치거나 맞닿은 busy를 병합한다.
- 후보 운동 window 앞뒤에 각각 15분을 확보한다.
- free window가 `requested_duration_minutes + 30분`보다 짧으면 후보로 반환하지 않는다.
- 후보는 시작 시각 오름차순으로 하루 최대 8개다.
- 후보가 없으면 빈 배열을 반환하고 요청 시간을 줄이거나 운동 계획을 삭제·변경하지 않는다.
- 사용자가 수동 가능 시간을 명시하면 빈 목록을 포함해 calendar보다 항상 우선한다.

### 호출 제한과 장애 폴백

- 사용자 기준 availability 30회/고정 1시간, calendar endpoint 합계 60회/고정 1시간을 provider 호출
  전에 적용한다. 30·60번째는 허용하고 31·61번째는 `429 RATE_LIMITED`다.
- 동의 없음은 `409 CONSENT_REQUIRED`, 미연결·권한 거부는 `409 CALENDAR_NOT_CONNECTED`, provider
  timeout·transport·Google 403/429 usage limit·5xx는 `503 PROVIDER_UNAVAILABLE`이다.
- 모든 실패는 수동 daily check-in, 수동 가능 시간, 기본 routine과 앱 block check 경로를 유지한다.
- 외부 실패는 기존 운동 계획, 안전 veto, 사용자 REST 선택 또는 공식 완료를 변경하지 않는다.

### performance와 공식 완료

- Google Calendar에는 실제 운동 수행 여부 필드가 없다. event `status` 또는 삭제·취소는 수행 증거로
  해석하지 않는다.
- Google provider의 `performed`는 항상 `null`이다. 정적 안내는
  “캘린더에서는 실제 운동 수행 여부를 확인할 수 없습니다. 앱에서 완료한 운동 블록만 공식 기록에 반영됩니다.”다.
- `performance` 확인은 scheduled workout이 `COMPLETED`, `PARTIAL`, `NOT_COMPLETED` 또는
  `REST_SELECTED`로 확정된 뒤에만 처리한다. 같은 link의 재확인은 10분 경계부터 허용한다.
- provider-neutral 합성 입력에서 `performed=true/false`가 들어와도 공식 workout session 상태는
  그대로 보존한다. 캘린더는 safety veto를 우회할 수 없다.

### 연결 해제와 계정 삭제

- `DELETE /connection`은 로컬 status를 `REVOKED`로 바꾸고 `revoked_at`을 기록하며 secret manager
  token을 폐기한다. 반복 호출은 성공 no-op이다.
- Google token revoke는 project에 부여된 다른 OAuth scope와 token에 광범위한 영향을 줄 수 있다.
  Firebase와 같은 project를 쓰는 현재 계약에서는 calendar 단독 provider revoke를 호출하지 않는다.
- 향후 별도 Google Cloud project로 격리할 때만 provider revoke 활성화를 새 ADR로 검토한다.
- 계정 삭제는 새 상태를 만들지 않고 ADR-0008의 provider revocation checkpoint를 재사용한다. 현재
  Google Calendar 단계는 로컬 secret 폐기 완료를 revocation 완료로 전달한다.

## 결정 이유

freebusy-only 조회는 event text를 가져온 뒤 마스킹하는 방식보다 개인정보 노출면이 작다. 수동 입력과
앱 block check를 권위 있는 경로로 유지하면 provider 장애·권한 거부가 핵심 운동 흐름이나 안전 판단을
바꾸지 않는다. 전용 보조 캘린더는 `calendar.app.created` 최소 scope를 실제 구조로 강제한다.

## 검토한 대안

- Events.list로 일정 본문 또는 all-day metadata 조회
- freebusy의 00:00~24:00 구간을 all-day로 추정해 무시
- primary calendar에 광범위한 `calendar.events` scope로 운동 일정 작성
- availability cache, polling 또는 webhook 동기화
- calendar event 상태·삭제를 공식 수행 여부로 사용
- Firebase와 공유한 project에서 Google token revoke 호출

## 선택하지 않은 대안과 이유

- event 목록 조회와 본문 수집은 최소수집 경계를 넓힌다.
- freebusy 구간 모양만으로 all-day 의미를 추정하면 실제 24시간 점유를 잘못 무시할 수 있다.
- primary calendar와 광범위 scope는 앱 소유 이벤트 경계를 약화한다.
- cache·worker는 현재 on-demand MVP에 불필요하며 stale·삭제 surface를 만든다.
- 캘린더는 일정 시스템이지 workout completion system이 아니다.
- 공유 project revoke는 Firebase Google 로그인과 다른 grant에 영향을 줄 위험이 있다.

## 결과와 영향

- 새 domain rule, provider port, unavailable/synthetic adapter와 unit/golden/privacy test를 추가한다.
- 공개 API에 예약 authorize-init과 connection request의 `state`, `code_verifier`가 추가된다.
- 논리 DB에 calendar authorization flow, rate-limit window와 `token_secret_ref`가 추가된다.
- 실제 route·repository·migration·Google adapter는 TASK-BACKEND-007로 이관한다.
- WEARABLE normalized contract와 원본 보유 정책은 Wave 9D에서 별도 확정한다.

## 보안·개인정보·호환성 영향

calendar event text와 provider 원본은 0시간 보유하며 token은 secret manager에서만 관리한다.
새 request field는 9C-2 구현 전 frontend 승인과 OpenAPI compatibility test가 필요하다. 로그는 opaque
request/event ID, provider·endpoint·outcome/failure machine code, policy version, 시각과 latency bucket
allowlist만 사용한다.

## 공식 문서 근거

모두 Google 공식 문서이며 확인일은 **2026-08-14**다.

- Freebusy endpoint·scope·응답: https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- Calendar scope: https://developers.google.com/workspace/calendar/api/auth
- Events resource와 `id`: https://developers.google.com/workspace/calendar/api/v3/reference/events
- Event 생성: https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- API quota와 403/429: https://developers.google.com/workspace/calendar/api/guides/quota
- Calendar timezone setting: https://developers.google.com/workspace/calendar/api/v3/reference/settings/get
- Native OAuth state·PKCE: https://developers.google.com/identity/protocols/oauth2/native-app
- Token revoke 영향: https://developers.google.com/identity/protocols/oauth2/javascript-implicit-flow

## 아직 확정되지 않은 사항

- 전용 보조 캘린더의 사용자 표시 이름과 중복 생성 복구 정책
- Android App Link와 iOS Universal Link의 production redirect URI
- secret manager 제품·경로와 token rotation 운영 owner
- Google OAuth consent screen 검수 일정과 test user 운영

## 후속 작업

1. 필수 reviewer가 ADR을 승인한다.
2. TASK-BACKEND-007에서 route, service, repository, additive migration과 Google API adapter를 구현한다.
3. frontend owner가 authorize-init·PKCE callback과 permission/error UI를 구현한다.
4. 운영 owner가 동일 project OAuth 영향, redirect, consent screen과 secret 폐기를 검증한다.
