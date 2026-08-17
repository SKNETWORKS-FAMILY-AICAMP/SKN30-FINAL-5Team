# TASK-BACKEND-007: Google Calendar 외부 컨텍스트 정책과 adapter

- Primary owner: 백엔드 담당
- Contract owner: 개발팀장
- Reviewers: 프론트엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `F011-1-1`~`F011-1-8`, `NFR-004`, `NFR-005`
- 관련 ADR: ADR-0003, ADR-0006, ADR-0008, ADR-0010
- 정책 버전: `external-context-policy-v2`
- schema: `calendar-availability-v1`, `calendar-performance-v2`, `calendar-credential-v1`
- provider code: `GOOGLE_CALENDAR`

## 단계와 게이트

- 9C-1: 결정적 policy, provider port, unavailable/synthetic adapter, golden/privacy test 완료.
- 9C-1B contract freeze: workout-session 연결, API/DB/OAuth/secret/삭제 계약과 필수 reviewer 승인 완료.
- 9C-2A persistence foundation
- 9C-2B OAuth·credential service boundary
- 9C-2C Google provider adapter
- 9C-2D Calendar API integration
- 9C-2E integration/privacy/operation hardening

ADR-0010은 `ACCEPTED`다. 각 단계는 앞 단계가 최신 develop에 병합된 뒤 새 브랜치·worktree에서
시작한다. production provider는 OAuth client, redirect URI,
secret-manager adapter/path/owner 증적이 없으면 disabled 상태를 유지한다.

## 확정된 9C-1B 계약

1. availability는 Google `primary` calendar 하나만 freebusy로 조회한다. CalendarList와 event list를
   호출하지 않는다.
2. scope는 `calendar.freebusy`, `calendar.app.created`만 사용하고 profile/email/openid/settings scope를
   요청하지 않는다.
3. 보조 캘린더·이벤트의 고정 summary는 `헬끼 운동 일정`, `헬끼 운동`이다. 본문·위치·참석자·회의
   링크·메모를 보내지 않는다.
4. event link는 `scheduled_workout_id`가 아니라 `workout_session_id`를 참조한다.
5. client는 PLANNED session ID와 start_at만 보내고 server가 선택된 계획의 요청 시간으로 end_at을
   계산한다.
6. performance gate는 workout session의 `COMPLETED/PARTIAL/NOT_COMPLETED/STOPPED_FOR_SAFETY`다.
   Google은 HTTP event 조회 없이 항상 `performed=null`이다.
7. OAuth state는 server-issued 600초 single-use, PKCE S256이며 Calendar 전용 transient row를 쓴다.
   9B 구현에 의존하지 않는다.
8. raw state/verifier/code/token과 provider payload/error는 DB·cache·로그·metric·trace·fixture에 없다.
9. DB에는 opaque `calendar-credential://{environment}/{connection_id}` ref만 저장한다. refresh token과
   보조 calendar ID는 `calendar-credential-v1` secret에만 둔다.
10. disconnect·동의 철회는 `REVOKE_PENDING`으로 접근을 차단하고 secret 파기 뒤 REVOKED로 확정한다.
    Google grant revoke와 원격 보조 캘린더 자동 삭제는 하지 않는다.
11. account deletion은 Calendar DB row hard delete 전에 secret-manager credential을 파기한다.
12. authorize-init은 호출마다 이전 state를 폐기한다. event create는 UUID Idempotency-Key, exchange는
    single-use state, delete는 현재 connection 기준 멱등이다.

## 9C-2A — persistence foundation

포함:

- `calendar_connections`, `calendar_event_links`, `calendar_oauth_requests`,
  `calendar_rate_limit_counters` SQLAlchemy model/repository
- additive Alembic migration과 `backend/app/db/base.py`, model exports
- ACTIVE partial unique, event/session unique, typed CHECK/FK, OAuth digest와 atomic counter
- account deletion FK graph 및 Calendar secret cleanup repository checkpoint
- PostgreSQL repository/concurrency/migration round-trip test

제외:

- FastAPI route, provider HTTP, token exchange, actual secret manager
- domain policy 변경과 public API 변경

인수 조건:

- SQLite 편의 동작만으로 완료 처리하지 않고 PostgreSQL unique/locking/rollback을 검증한다.
- migration 번호는 작업 시작 시 최신 develop의 head 다음 번호를 사용한다. 다른 feature의 번호를
  선점하지 않는다.
- user 삭제가 모든 Calendar row를 제거하고 secret cleanup 대상이 row hard delete 전에 열거된다.

## 9C-2B — OAuth·credential service boundary

포함:

- authorize-init과 callback consume application service
- CSPRNG state, SHA-256 digest, PKCE S256 constant-time 검증, redirect allowlist
- `CalendarCredentialVaultPort`와 unavailable/in-memory test adapter
- secret 저장/DB commit 보상, revoke-pending/finalize, refresh version 교체
- Calendar 전용 rate-limit service와 consent gate

제외:

- 실제 Google HTTP, actual cloud secret SDK, public route

인수 조건:

- state row는 provider 호출 전에 삭제·commit되고 외부 실패 후 되살아나지 않는다.
- raw state/verifier/code/token은 persistence와 observability에 없다.
- secret put 뒤 DB 실패는 secret delete를 수행하며 성공 connection을 반환하지 않는다.
- actual secret adapter가 없으면 app은 기동하고 Calendar use case는 safe 503이다.

## 9C-2C — Google provider adapter

포함:

- authorization/token/refresh HTTP adapter
- required scope 검증과 `access_type=offline`, `include_granted_scopes=false`
- primary freebusy, 보조 calendar 생성, 고정 최소 event insert
- quota/permission/invalid_grant/timeout/5xx safe mapping
- 합성 HTTP fixture와 unavailable fallback

제외:

- CalendarList, event list/get, webhook/push/polling, remote grant revoke
- 실제 credential을 CI 필수 조건으로 만드는 작업

인수 조건:

- 요청 URL과 payload allowlist test가 금지 endpoint·field를 차단한다.
- raw provider body/header/token/calendar ID가 exception·log·snapshot에 없다.
- performance는 provider HTTP 호출 없이 `performed=null`을 반환한다.

## 9C-2D — API integration

포함 endpoint:

- `POST /api/v1/calendar/connection/authorize-init`
- `POST /api/v1/calendar/connection`
- `GET /api/v1/calendar/connection`
- `GET /api/v1/calendar/availability`
- `POST /api/v1/calendar/events`
- `GET /api/v1/calendar/performance`
- `DELETE /api/v1/calendar/connection`

인수 조건:

- route는 Pydantic 검증 후 application service만 호출한다.
- user ownership, consent, deletion-pending 접근 차단과 idempotency를 검증한다.
- event create는 PLANNED workout session만 허용하고 server-derived end_at을 사용한다.
- permission/outage/rate limit에도 plan, session, safety veto와 manual fallback이 유지된다.
- 공통 error envelope와 API_CONTRACT 예제를 호환성 test로 고정한다.

## 9C-2E — hardening과 production readiness

- consent 철회·account deletion·secret cleanup end-to-end
- concurrent authorize/event/disconnect/rate-limit 경쟁 조건
- privacy log/snapshot/metric/fixture 검사
- disabled/unavailable boot, provider outage와 transaction compensation
- Google test project에서 최소 scope·primary freebusy·보조 calendar·quota·Firebase 로그인 유지 확인
- production OAuth client/redirect URI/consent screen, secret-manager adapter/path/owner 증적
- frontend secure callback과 primary-only/remote-calendar-retained UX 확인

## 공통 필수 테스트

- unit: gate, rate limit, 10분 경계, provider 실패, busy 병합·buffer·최소 길이·상한·DST
- golden: 미연동, 권한 거부, completion 불변, `performed=null`, outage, full-day busy, REST 무압박
- security/privacy: OAuth replay/expiry/PKCE, raw secret·본문·payload/error 비노출
- persistence: concurrent unique/counter, rollback/compensation, account deletion graph
- migration: PostgreSQL upgrade/downgrade 또는 승인된 forward-fix round trip
- ruff format/check, mypy, 관련/전체 pytest

## Backend adapter handoff checklist

- [x] ADR-0010이 모든 필수 reviewer 확인 후 `ACCEPTED`
- [ ] 앞 단계가 develop에 병합되고 새 worktree가 최신 origin/develop에서 생성됨
- [ ] migration head와 다른 feature migration 충돌 없음
- [ ] provider port는 normalized 값만 반환하고 raw payload type을 domain에 노출하지 않음
- [ ] CalendarCredentialVaultPort 구현과 disabled/unavailable fallback 존재
- [ ] config 기본값은 provider disabled이며 credential 누락 시 기동 가능
- [ ] primary-only와 금지 endpoint/field allowlist test 존재
- [ ] idempotency, ownership, consent, deletion-pending, rate-limit이 provider 호출보다 먼저 적용됨
- [ ] workout-session completion과 safety/REST invariant golden test 통과
- [ ] account deletion 전 secret cleanup과 user-linked row 제거 검증
- [ ] 실제 credential·사용자 데이터가 test/fixture/log/PR에 없음

## 승인·운영 잔여 게이트

- 프론트엔드: 600초 OS 보안 저장소 callback과 원격 calendar 잔존 안내
- PM·개인정보: 고정 summary, primary-only 제한, remote calendar retain UX
- 운영: 실제 OAuth client, redirect URI, consent screen, test users, secret-manager product/path/owner
- Google test project: local disconnect 뒤 Firebase Google 로그인 유지와 quota/error 검증

이 항목은 production enablement를 차단하지만, disabled/unavailable 기본 구성의 9C-2A 착수를
차단하지 않는다.
