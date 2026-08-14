# TASK-BACKEND-007: Google Calendar 외부 컨텍스트 정책과 adapter

- Primary owner: 백엔드 담당
- Reviewers: 프론트엔드, 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `F011-1-1`~`F011-1-8`, `NFR-004`, `NFR-005`
- 관련 ADR: ADR-0003, ADR-0006, ADR-0008, ADR-0010
- 정책 버전: `external-context-policy-v1`
- provider code: `GOOGLE_CALENDAR`

## 단계와 게이트

- 9C-1 `feat/external-context-policy-core`: 결정적 policy, provider port, unavailable 합성 adapter,
  계약·golden·privacy test와 PROPOSED ADR-0010. 실제 provider 호출·route·DB migration 제외.
- 9C-2 `feat/calendar-adapter`: ADR-0010이 `ACCEPTED`된 뒤 실제 Google adapter, API, service,
  repository/model/migration과 운영 설정 구현.

## 9C-1 포함 범위

- Google Calendar 최소 scope와 freebusy-only 개인정보 경계
- 동의·연결 gate, provider 실패와 manual fallback
- availability 30회/시간, 전체 calendar endpoint 60회/시간 fixed window 계약
- freebusy busy 병합, 전후 15분 buffer, 희망 시간 보존, 최대 8개 후보와 DST 규칙
- performance 10분 재확인, Google `performed=null`, 공식 completion 불변
- `CalendarProviderPort`와 local/CI unavailable null object·synthetic contract adapter
- API/Data/Domain/Test/Traceability 계약과 unit/golden/privacy test

## 9C-1 제외 범위

- 실제 Google HTTP/API/SDK 호출과 credential
- FastAPI route, application service, repository/model과 Alembic migration
- `token_secret_ref` 실컬럼과 calendar OAuth transient table
- webhook, push, polling worker, scheduler, Redis와 Celery
- event list·본문·참석자·위치 조회, wearable 코드와 `/manual-activities`

## 9C-1 인수 조건

1. provider는 `GOOGLE_CALENDAR`, scope는 `calendar.freebusy`와 `calendar.app.created`만 제안한다.
2. 사용자 timezone은 기존 IANA timezone을 사용하고 Google settings scope를 요청하지 않는다.
3. freebusy 원본은 저장하지 않고 start/end 정규화 구간만 domain에 전달한다.
4. 종일 여부를 추정하지 않고 freebusy가 반환한 모든 busy 구간을 점유로 처리한다.
5. 겹치거나 맞닿은 busy를 병합하고 후보 앞뒤 15분 buffer를 둔다.
6. 최소 빈 구간은 희망 시간 + 30분이며 후보 없음에도 희망 시간을 단축하지 않는다.
7. 후보는 시작 시각 오름차순 최대 8개이며 DST 23/25시간 로컬 하루를 보존한다.
8. 명시적 수동 가능 시간은 빈 목록을 포함해 calendar 후보보다 우선한다.
9. 동의 철회·미연결·권한 거부·provider 장애에서 수동 체크인과 앱 블록 체크를 유지한다.
10. 30/31·60/61 fixed-window 경계를 provider 호출 전에 판정한다.
11. performance는 공식 종료 상태 이후 10분 간격이며 Google 결과는 항상 `null`이다.
12. 어떤 calendar 관찰값도 공식 workout 상태나 Safety veto를 변경하지 않는다.
13. calendar 본문, token, raw payload/error는 DB·log·metric·trace·snapshot·fixture·LLM에 없다.
14. 실제 provider가 없는 local/CI에서 unavailable null adapter와 synthetic adapter를 검증한다.
15. disconnect는 local `REVOKED`와 secret 파기로 완료하고 동일 Google project에서 remote revoke하지 않는다.
16. ADR 승인 전 실제 route·adapter·migration을 구현하지 않는다.

## 9C-2 승인 전 확인

- ADR-0010 필수 reviewer 승인과 `ACCEPTED` 상태
- 동일 Google Cloud project의 OAuth client·redirect URI·secret manager 경로
- `calendar.app.created` 전용 보조 캘린더 UX
- local disconnect 뒤 Firebase Google 로그인이 유지되는지 test project 검증
- 모바일의 600초 state·PKCE verifier 보관·callback 계약
- `calendar_connections.token_secret_ref`와 calendar OAuth transient schema/migration 승인

## 필수 테스트

- unit: gate, rate limit, 10분 경계, provider 실패, busy 병합·buffer·최소 길이·상한·DST
- golden: 미연동, 권한 거부, completion 불변, `performed=null`, outage, full-day busy
- privacy: 본문·token·raw payload/error 비로그·비응답·비fixture
- 9C-2: 연결·동기화·해제 멱등성, DB rollback, API/integration, PostgreSQL/Alembic round trip
- ruff format/check, mypy, 관련/전체 pytest

## 변경 예상 파일

- 9C-1: `backend/app/domain/rules/external_context.py`, external-context port, unavailable integration,
  unit/golden tests, ADR/API/Data/Domain/Test/Traceability 문서
- 9C-2: config/`.env.example`, calendar schemas/service/API, model/repository, Google adapter,
  additive migration, API/integration/migration/privacy tests와 frontend callback contract
