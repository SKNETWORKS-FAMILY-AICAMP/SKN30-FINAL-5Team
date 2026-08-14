# TASK-BACKEND-007: Google Calendar adapter와 외부 컨텍스트 연결

- Primary owner: 백엔드 담당
- Reviewers: 프론트엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `F011-1-1`~`F011-1-8`, `NFR-005`, `NFR-006`
- 관련 ADR: ADR-0003, ADR-0006, ADR-0008, ADR-0010
- 선행 게이트: ADR-0010 `ACCEPTED`, Wave 9C-1 머지
- 목표 브랜치: `feat/calendar-adapter`
- policy/schema: `external-context-policy-v1`, `calendar-availability-v1`,
  `calendar-performance-v1`

## 배경과 사용자 가치

수동 check-in과 앱 block completion을 유지하면서 Google Calendar freebusy를 이용해 개인정보를
최소화한 운동 가능 window를 제안하고, 앱 소유 운동 일정을 전용 보조 캘린더에 등록한다.

## 포함 범위

- calendar authorize-init, connection, availability, event create, performance, disconnect route/service
- Google OAuth authorization-code + PKCE S256, 600초 single-use state
- Calendar provider port의 Google API v3 adapter
- freeBusy 조회와 `calendar.freebusy` 최소 scope
- `calendar.app.created` 전용 보조 캘린더 생성·재사용과 앱 운동 일정 등록
- secret manager token 참조, local revoke/secret 폐기
- PostgreSQL authorization flow와 fixed-window rate limit repository
- calendar connection/event link model과 additive migration
- OpenAPI/frontend callback handoff, API/PostgreSQL/migration/privacy tests와 운영 runbook

실제 wearable adapter, Events.list, calendar 본문 조회, provider raw payload 저장, webhook/push/polling,
worker/scheduler, manual activity, frontend permission UI와 실제 credential 등록은 제외한다.

## 인수 조건

1. `provider_code`는 `GOOGLE_CALENDAR`만 허용한다.
2. authorize-init은 인증된 ACTIVE user, `CALENDAR_INTEGRATION` 동의, 등록 redirect URI와 S256
   challenge만 허용한다.
3. server는 UUIDv4 flow, CSPRNG state와 600초 expiry를 반환하고 DB에는 state·redirect URI SHA-256,
   challenge와 시각만 저장한다.
4. connection은 state·redirect·expiry와 43~128자 verifier의 S256을 검증하고 provider 호출 전에
   flow row를 삭제·commit한다. provider 호출 중 DB lock을 유지하지 않는다.
5. raw state/verifier/code/token, provider response와 client secret은 DB·cache·로그·fixture에 없다.
6. refresh/access token은 secret manager에 저장하고 DB에는 nullable `token_secret_ref`만 둔다.
7. availability는 요청 local date의 저장된 user IANA timezone 00:00~다음 00:00을 freeBusy로
   조회한다. calendar settings scope를 추가하지 않는다.
8. `calendar.freebusy` 응답에서 busy `start/end`만 메모리 정규화하고 모든 반환 구간을 busy로 취급한다.
9. title/description/attendees/location/conference/notes를 조회하는 Events.list 호출이 없다.
10. busy 겹침 병합, 앞뒤 15분, 요청 시간+30분 최소 window, 정렬과 8개 상한을 Wave 9C-1
    domain rule 그대로 사용한다.
11. availability는 cache·저장하지 않고 raw Google payload 보유시간은 0시간이다.
12. 수동 가능 시간이 있으면 빈 목록을 포함해 calendar보다 우선하고 요청 시간을 자동 단축하지 않는다.
13. `calendar.app.created`로 전용 보조 캘린더를 만들고 앱 운동 일정만 생성·조회·변경한다.
14. Google event `id`는 `external_event_id`에 저장하며 schema는 최대 1024자를 보존한다.
15. event title은 승인된 고정 서비스 문구만 provider 요청 메모리에서 만들고 DB·로그에 복제하지 않는다.
16. Google에는 workout performance 필드가 없으므로 `performed=null`만 반환·저장한다.
17. event `status`, 삭제·취소·시간 경과를 미수행 또는 공식 완료로 해석하지 않는다.
18. performance는 scheduled workout 종료 상태 뒤에만 처리하고 같은 link는 10분 경계부터 재확인한다.
19. `performed=true/false/null`, timer와 calendar event가 공식 session status를 바꾸지 않는다.
20. availability 30/31, 전체 endpoint 60/61 고정 1시간 경계를 provider 호출 전에 원자 적용한다.
21. Google 403/429 usage limit, timeout, transport와 5xx는 `503 PROVIDER_UNAVAILABLE`; 원시 오류는
    공개하거나 로그에 남기지 않는다.
22. 권한 거부·미연결·장애 시 manual check-in·기본 routine·block completion이 유지되고 계획을
    삭제·변경하지 않는다.
23. disconnect는 `REVOKED`, `revoked_at`과 secret 폐기를 local transaction으로 완료한다. 반복은 no-op이다.
24. Firebase와 같은 Google Cloud project에서는 Google revoke endpoint를 호출하지 않는다. 별도
    project 격리 전 remote revoke를 활성화하지 않는다.
25. account deletion은 ADR-0008 checkpoint를 재사용하고 새 deletion 상태를 만들지 않는다.
26. migration은 기존 row를 rewrite하지 않으며 safe downgrade 또는 forward-fix를 문서화한다.
27. Google 설정이 없거나 disabled이면 앱은 기동하고 calendar endpoint는 안전한 unavailable/fallback을 반환한다.
28. external context가 Safety veto, REST 선택, 압박 차단 또는 공식 completion을 우회하지 않는다.

## 변경 예상 파일

- `backend/app/core/config.py`, `backend/.env.example`
- `backend/app/modules/external_context/ports.py`, schema/service 파일
- `backend/app/api/v1/calendar.py`, `backend/app/api/v1/router.py`
- `backend/app/integrations/google_calendar.py`
- calendar model/repository와 신규 additive migration
- API/unit/integration/migration/privacy tests, OpenAPI/frontend mock와 runbook

## API 영향

- `[예약] POST /api/v1/calendar/connection/authorize-init` 구현
- `CalendarConnectionRequest`의 `state`, `code_verifier` 구현
- 기존 availability/event/performance/disconnect field는 유지
- 프론트엔드 승인과 backward-compatibility test 필수

## DB·마이그레이션 영향

- `calendar_connections.token_secret_ref` nullable 추가
- calendar OAuth authorization request와 rate-limit window table 추가
- `external_event_id` 최대 1024자 보장
- 작업 직전 migration head와 다른 worktree 번호 충돌 확인

## 안전·개인정보·보안 영향

- event 본문과 raw provider payload 수집·저장 금지
- raw OAuth material과 token 비영속화
- provider outage가 workout/safety state를 바꾸지 않음
- 동일 project revoke 금지로 Firebase Google 로그인 grant 보호

## 선행 관계와 차단 요소

- ADR-0010 승인
- Google Calendar API가 활성화된 기존 Firebase project
- iOS Universal Link/Android App Link production redirect 등록
- OAuth consent screen, test users, secret manager와 운영 owner
- 전용 보조 캘린더의 승인된 사용자 표시 이름

하나라도 미확정이면 live Google adapter, route, migration 또는 credential 작업을 시작하지 않는다.

## 테스트 계획

- OAuth state/expiry/replay/PKCE/redirect와 transaction consume
- consent·connection·permission denial·unavailable/manual fallback
- freebusy normalization, overlap/buffer/minimum/8-slot/timezone/DST
- 30/31·60/61 limit과 concurrent counter
- app-created calendar/event ID와 retry/idempotency
- performance null, 10분 boundary와 official completion 불변
- disconnect/account deletion secret purge와 no remote revoke
- raw token/event text/payload/error 비노출
- PostgreSQL integration, Alembic upgrade/downgrade/upgrade, OpenAPI compatibility
- ruff format/check, mypy, 관련/전체 pytest

## 수동 확인

1. Expo Development Build에서 등록된 App/Universal Link callback을 확인한다.
2. Google consent 화면에 calendar freebusy와 app-created 범위 외 scope가 없는지 확인한다.
3. 전용 보조 캘린더 생성과 앱 운동 일정만 접근하는지 확인한다.
4. 권한 거부·token 만료·quota 오류에서 기존 계획과 manual 흐름이 유지되는지 확인한다.
5. disconnect 후 Calendar API가 중단되고 Firebase Google 로그인이 유지되는지 확인한다.

## 알려진 제한과 후속 작업

- Google Calendar는 실제 workout performance를 제공하지 않아 `performed`는 항상 null이다.
- remote token revoke는 별도 project 격리 전 비활성이다.
- WEARABLE provider와 normalized health/activity contract는 Wave 9D다.
