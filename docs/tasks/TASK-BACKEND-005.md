# TASK-BACKEND-005: 계정 삭제 API·repository·migration·job

- Primary owner: 백엔드 담당
- Reviewers: 개발팀장, PM·개인정보 검토자, 운영 담당
- 관련 요구사항: `POL-011-1-1`~`POL-011-1-8`, `NFR-004`, `NFR-005`, `NFR-006`
- 관련 ADR: `ADR-0004`, `ADR-0005`, `ADR-0008`
- 목표 브랜치: backend owner의 Wave9A 전용 feature branch/worktree

## 배경과 사용자 가치

사용자가 계정 삭제를 요청하면 즉시 접근·동기화를 차단하고 운영 DB 개인정보를 7일 이내,
해당 데이터를 포함할 수 있는 backup recovery point를 30일 이내 만료해야 한다. provider·DB·backup
실패가 있어도 상태와 재시도가 결정적이어야 하며 hard delete 후 사용자와 연결되는 감사 데이터를
남기지 않아야 한다.

## 포함 범위

- `DELETE /api/v1/me` request service와 `202 Accepted` 응답
- ACTIVE -> DELETION_PENDING 원자적 전이와 즉시 접근·동기화 차단
- 같은 키·새 키·동시 요청의 resource-level 멱등성
- account deletion request/job/audit/tombstone model·repository·Alembic migration
- provider revocation port와 합성 adapter
- checkpoint 기반 동기 실행 job/service와 재시도 계약
- 사용자 연결 FK delete graph와 hard-delete transaction
- backup expiry verification port
- 개인정보 비노출·unit·API·PostgreSQL integration·migration test
- provider 실패와 backup restore 운영 runbook

## 제외 범위

- 실제 Firebase·Google·Kakao·Naver 계정 해제
- 실제 scheduler, queue, batch worker infrastructure
- AWS backup 리소스·lifecycle 생성
- 법률상 보존 예외의 신규 추정
- 삭제 철회 API
- frontend 화면 구현
- 기존 공개 응답 필드의 삭제·이름 변경

## 인수 조건

1. `ACTIVE` 사용자의 최초 요청은 한 트랜잭션에서 `DELETION_PENDING`과 단 하나의 활성
   request/job을 만들고 최초 receipt를 저장한다.
2. 요청 직후 모든 인증 사용자 제품 API와 외부 동기화를 `403 ACCOUNT_DISABLED`로 차단한다.
   비인증 health와 기존 DELETE 멱등 재요청만 예외다.
3. 이미 `DELETION_PENDING`인 사용자의 같은 키와 새 UUID key 요청은 새 job이나 409 없이 최초
   request ID, `operational_data_delete_by`, status를 `202`로 반환한다.
4. 사용자별 활성 deletion request/job unique와 동시 요청 직렬화를 DB·service·integration
   test로 보장한다.
5. `requested_at`부터 job을 실행할 수 있고 `operational_delete_by=requested_at+7일`,
   `backup_expiry_due_at=requested_at+30일`을 UTC instant로 계산한다.
6. job 상태와 단계는 ADR-0008의 machine code와 허용 전이만 사용하며 policy version은
   `account-deletion-policy-v1`이다.
7. checkpoint는 고정 prefix이고 재실행은 완료 단계를 건너뛰며 실패 단계부터 재개한다.
8. provider retryable failure는 `RETRY_PENDING`, 7일 기한의 최종 실패는 `FAILED_FINAL`이다.
9. provider 최종 실패와 무관하게 로컬 user-linked 데이터는 7일 이내 hard delete하고 backup
   expiry 확인 후 `COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE`로 완료할 수 있다.
10. 운영 DB hard delete 실패는 partial commit 없이 rollback하고 `FAILED_REQUIRES_REVIEW`로
    에스컬레이션한다. 성공이나 계정 활성화로 매핑하지 않는다.
11. 삭제 대상은 DATA_MODEL 4.7~4.10과 14절의 모든 user-linked·재식별 가능 데이터다. 특히
    암호화 생년월일, consent event, decision/proposal/feedback, weekly data, idempotency와
    cache/work payload를 포함한다.
12. hard delete 후 감사 row에는 allowlist opaque 필드만 남고 user/provider ID·FK, token,
    idempotency key, request/response, raw error·health snapshot이 없다.
13. request/job ID는 UUIDv4다. keyed HMAC-SHA256 tombstone은 key를 저장·로그하지 않고
    `requested_at+30일`에 만료한다.
14. backup 복원 시 만료 전 tombstone 일치는 접근 차단과 같은 deletion policy 재적용을 만든다.
15. 단순 30일 경과가 아니라 마지막 관련 recovery point 만료 운영 증적이 있어야 `COMPLETED`
    또는 provider 실패 완료 상태로 전이한다.
16. tombstone은 30일을 넘겨 보존하지 않는다. opaque 감사 TTL은 승인된 retention policy를
    입력받으며 임의 default나 영구 보존을 두지 않는다. 불가역 비식별 집계만 사용자 삭제 후
    보존할 수 있다.
17. 모든 오류·로그·metric label은 allowlist machine code와 opaque request ID만 사용하고 직접
    식별자, provider subject, 생년월일, token, 원시 건강·오류 payload를 포함하지 않는다.

## 변경 예상 파일

- `backend/app/api/v1/me.py` 또는 기존 사용자 router
- `backend/app/schemas/account_deletion.py`
- `backend/app/services/account_deletion.py`
- `backend/app/db/models/account_deletion.py`
- `backend/app/db/repositories/account_deletion.py`
- `backend/app/integrations/account_deletion.py`
- `backend/migrations/versions/*_account_deletion.py`
- `backend/tests/unit/test_account_deletion_service.py`
- `backend/tests/api/test_account_deletion.py`
- `backend/tests/integration/test_account_deletion_repository.py`
- `backend/tests/integration/test_migrations.py`
- 운영 runbook 문서

실제 저장소 구조를 먼저 재사용하고 위 파일명을 그대로 만들기 위해 중복 추상화를 추가하지 않는다.

## API 영향

- 기존 `DELETE /api/v1/me`의 공개 필드와 `202`를 유지한다.
- 새 key로 재요청하는 `DELETION_PENDING` 사용자의 의미를 최초 receipt 반환으로 확정한다.
- 내부 job/provider/backup 상태를 기존 공개 응답에 새 필드로 노출하지 않는다.
- hard delete 후 삭제 request 존재를 인증 오류로 구분 노출하지 않는다.
- OpenAPI, API example, frontend mock과 하위 호환 test는 backend 구현 PR에서 갱신·검토한다.

## DB·마이그레이션 영향

- DATA_MODEL 4.7~4.10은 논리 계약이며 backend owner가 실제 typed column, FK, unique와 index를
  설계한다.
- 사용자별 활성 request/job unique, UUIDv4, timezone-aware timestamp와 machine code CHECK를
  강제한다.
- users hard delete 전에 감사 de-identification과 tombstone 생성을 안전한 transaction 순서로
  처리한다.
- migration은 안전한 downgrade 또는 production forward-fix 전략과 PostgreSQL round trip을
  포함한다.
- 생성된 파일을 수동 수정하거나 schema 변경 없이 ORM만 추가하지 않는다.

## 안전·개인정보·보안 영향

- provider 장애보다 로컬 개인정보 7일 삭제 기한을 우선한다.
- tombstone은 가명정보이며 backup restore 차단에만 사용하고 30일 후 삭제한다.
- HMAC key는 secret manager에 두고 source, fixture, DB, 로그에 저장하지 않는다.
- 가명 decision/proposal/feedback과 재식별 가능 aggregate를 보존하지 않는다.
- 실제 출시 전 provider 삭제, backup 만료와 법적 보존 예외는 개인정보 담당자 검토를 받아야 한다.

## 선행 관계와 차단 요소

- 선행: ADR-0008과 `backend/app/domain/rules/account_deletion.py`
- 실제 provider adapter는 앱 등록·credential·provider별 삭제 API 확정 전 차단
- 실제 backup 완료 처리는 AWS 제품·리전·recovery point evidence 계약 확정 전 차단
- 법률상 보존 예외가 확인되면 구현 전에 새 ADR 필요

## 테스트 계획

- domain unit/golden: `backend/tests/unit/test_account_deletion.py`,
  `backend/tests/scenarios/test_account_deletion_golden.py`
- service unit: 같은/새 key, 동시 요청, deadline, checkpoint, provider·DB failure
- API: 즉시 접근 차단, 202 replay, 오류 envelope, hard delete 후 존재 비노출
- repository: FK graph, transaction rollback, 재실행, audit scrub, tombstone TTL
- privacy invariant: log/caplog, response, snapshot, fixture에 금지 필드 없음
- PostgreSQL integration과 Alembic upgrade/downgrade 또는 forward-fix
- ruff check/format, mypy, 관련 pytest와 전체 backend 회귀

## 수동 확인

1. 합성 사용자로 삭제 요청 후 일반 API가 즉시 차단되는지 확인한다.
2. 다른 UUID key로 재요청해 최초 request ID와 deadline이 유지되는지 확인한다.
3. provider 실패를 주입해 retry checkpoint와 7일 최종 실패 경로를 확인한다.
4. repository 중간 실패를 주입해 부분 row가 남지 않고 같은 단계에서 재개되는지 확인한다.
5. backup restore 합성 흐름에서 tombstone 일치 계정이 차단되고 30일 경계에서 만료되는지 확인한다.
6. 로그·감사 row·DB dump에 금지 개인정보가 없는지 확인한다.

## 알려진 제한과 후속 작업

- 실제 provider 해제, scheduler/queue와 AWS evidence adapter는 별도 운영 task다.
- provider 최종 실패는 로컬 완료를 막지 않지만 운영 incident와 별도 provider 후속 절차가 필요하다.
- 출시 전 법률·개인정보 검토 결과가 달라지면 새 ADR, policy version과 golden test를 함께 갱신한다.
