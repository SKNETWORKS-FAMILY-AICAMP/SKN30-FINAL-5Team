# ADR-0008: 계정 삭제 상태·보존·실패 복구 계약

- 상태: ACCEPTED
- 날짜: 2026-08-14
- 소유자: 개발팀장
- 승인자: 사용자 명시 결정(제품·개발 승인)
- 승인 증적: 사용자 명시 승인(2026-08-14, 본 작업 요청). 출시 전 법률·개인정보 검토는 별도 게이트
- 관련 요구사항/이슈: `POL-011-1-1`~`POL-011-1-8`, `NFR-004`, `NFR-005`
- 정책 버전: `account-deletion-policy-v1`

## 관계

- ADR-0004의 운영 DB 7일·백업 30일 기본선을 구체화한다.
- ADR-0005의 암호화 생년월일 삭제 대상을 유지한다.
- 법률상 별도 보존 의무가 확인되면 새 ADR로 본 결정을 변경한다.

## 배경

기존 계약은 삭제 요청 즉시 접근·동기화 차단, 운영 DB 7일 이내 hard delete, 백업 30일
순환 만료를 승인했지만 중복 요청, job 상태, provider 실패, 부분 실패 재실행, 완료 감사와
backup restore 차단 방식을 정하지 않았다. API·repository·migration·job 구현자가 이를
추측하지 않도록 결정적 상태·보존 계약이 필요하다.

## 결정

### 요청과 접근 차단

- `ACTIVE` 사용자의 삭제 요청은 같은 트랜잭션에서 `DELETION_PENDING`과 단 하나의 활성
  deletion request/job을 만든다.
- 요청 직후 모든 인증 사용자 제품 API와 외부 동기화를 차단한다. 비인증 health endpoint와
  기존 삭제 요청을 멱등 조회·재처리하는 deletion lifecycle 경계만 예외다.
- 이미 `DELETION_PENDING`인 사용자가 다른 `Idempotency-Key`로 재요청해도 충돌하거나 새
  job을 만들지 않고 최초 request ID, 상태와 deadline을 `202 Accepted`로 반환한다.
- 삭제 요청은 철회할 수 없다. 외부 해제와 hard delete는 되돌릴 수 없기 때문이다.

### 시간 계약

- job은 `requested_at`부터 즉시 실행할 수 있다.
- `requested_at + 7일`은 운영 DB hard delete의 완료 상한이지 실행 시작일이나 grace period가 아니다.
- `requested_at + 30일`은 해당 사용자를 포함할 수 있는 backup recovery point와 restore-block
  tombstone의 최대 만료 시각이다.
- 모든 기한은 timezone-aware UTC instant로 계산한다.

### 상태 머신

사용자 상태는 `ACTIVE -> DELETION_PENDING -> users row hard delete`다. 완료 사용자를 남기기
위해 `users.status_code=COMPLETED`를 추가하지 않는다.

삭제 job 상태:

```text
PENDING -> RUNNING -> RETRY_PENDING -> RUNNING
RUNNING -> BACKUP_EXPIRY_PENDING -> COMPLETED
RUNNING -> BACKUP_EXPIRY_PENDING -> COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
RUNNING | RETRY_PENDING -> FAILED_REQUIRES_REVIEW -> RUNNING
```

고정 단계:

```text
ACCESS_BLOCK
EXTERNAL_REVOCATION
OPERATIONAL_DATA_DELETE
CACHE_AND_WORK_DELETE
AUDIT_DEIDENTIFICATION
BACKUP_EXPIRY_VERIFICATION
```

완료 checkpoint는 재실행 시 건너뛰며 실패 단계부터 재개한다. 각 단계는 대상이 이미 없어도
성공인 멱등 삭제로 구현한다. 외부 호출을 운영 DB hard-delete 트랜잭션 안에 포함하지 않는다.

### provider 실패

- provider 해제 실패는 `RETRY_PENDING`과 구조화 failure code로 기록하고 7일 기한 전까지 재시도한다.
- 기한까지 실패하면 `FAILED_FINAL`로 확정하고 provider subject를 더 보존하지 않는다.
- provider 장애가 로컬 개인정보의 무기한 보존 근거가 되지 않으므로 운영 DB 사용자 연결 데이터는
  7일 이내 hard delete한다.
- backup 만료 확인 후 최종 job 상태는
  `COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE`다. 식별정보 없는 운영 경보를 발생시키고 실제
  provider 후속 처리는 승인된 별도 운영 절차로 넘긴다.
- 운영 DB hard delete 자체가 기한 내 완료되지 않으면 `FAILED_REQUIRES_REVIEW`이며 성공으로
  간주하지 않고 개인정보 사고 대응 대상으로 에스컬레이션한다.

### 결정적 삭제 대상

승인된 법적 예외가 없는 기본 경로에서 다음 사용자 연결·재식별 가능 데이터는 일반 보유기간보다
계정 삭제 7일 기한을 우선 적용해 삭제한다.

- identity, profile, 암호화 생년월일, 동의 현재 상태와 event
- equipment, attention area, preference, routine, daily context
- wearable·calendar 연결과 사용자별 integration metadata
- decision run, proposal, candidate, safety review, option, explanation
- workout, timer, safety event, feedback, weekly report와 plan revision
- mutation idempotency response, 사용자별 cache·work payload·snapshot

비식별 집계는 개인과 다시 연결할 수 없고 같은 집합의 다른 데이터와 결합해도 singling-out할 수
없는 경우에만 보존한다. 가명·해시·user ID 제거만으로는 비식별 집계로 분류하지 않는다.

### opaque 감사와 restore-block tombstone

- request/job ID는 추측 가능한 sequence가 아닌 UUIDv4다.
- hard delete 완료 시 감사 레코드에서 user ID/FK, provider subject, idempotency key, 요청·응답,
  원시 오류와 건강 snapshot을 제거한다.
- 허용 감사 필드는 opaque request/job ID, job·단계·provider 상태, completion/failure machine code,
  policy version, attempt count, 요청·운영 삭제·backup 기한 및 완료 시각뿐이다.
- opaque 감사의 정확한 추가 보존기간은 출시 전 PM·법률/개인정보 검토에서 별도 승인한다.
  구현은 무기한 기본값을 두지 않고 승인된 retention policy가 없으면 audit purge 기간 확정을
  fail-closed 후속 작업으로 남긴다.
- backup restore 차단을 위해 내부 user UUID의 HMAC-SHA256 keyed digest, opaque request ID,
  policy version, 생성·만료 시각만 가진 가명 tombstone을 허용한다.
- tombstone key는 secret manager 경계에 두고 row나 로그에 저장하지 않는다. tombstone은
  `requested_at + 30일`에 만료·삭제하며 분석, 감사 집계, 사용자 추적에 재사용하지 않는다.
- backup 복원 시 만료 전 tombstone이 일치하면 해당 사용자의 접근을 차단하고 같은 삭제 policy를
  재적용한다.

### backup 책임 경계

- 애플리케이션은 deadline, policy version, tombstone 판정, 복원 시 접근 차단·재삭제를 책임진다.
- AWS 운영은 backup lifecycle, 최대 30일 만료, restore 절차와 recovery point 만료 증적을 책임진다.
- 단순히 30일이 경과했다는 이유로 `COMPLETED`로 만들지 않는다. 사용자를 포함할 수 있는 마지막
  recovery point가 만료됐다는 운영 증적이 있어야 backup expiry를 확인한다.
- 실제 AWS 리소스, scheduler, queue는 이 정책 작업의 구현 범위가 아니다.

## 결정 이유

사용자 접근 차단, 운영 DB 삭제, 외부 provider와 backup은 서로 다른 실패·책임 경계를 가진다.
사용자 row에 모든 상태를 넣으면 hard delete 후 감사가 불가능하고, provider 실패가 전체 삭제를
막으면 승인된 7일 기한을 지킬 수 없다. 별도 job과 최소 opaque 감사, 30일 tombstone은 로컬
삭제를 우선하면서 backup 복원으로 개인정보가 되살아나는 것을 막는 최소 계약이다.

## 검토한 대안

- 삭제 요청 후 7일을 기다렸다가 실행
- provider 해제가 성공할 때까지 로컬 데이터 무기한 보존
- users row를 `COMPLETED`로 유지
- provider subject나 user UUID를 완료 감사에 보존
- 가명 decision/proposal을 분석용으로 보존
- backup 만료를 애플리케이션이 사용자별 물리 삭제

## 선택하지 않은 이유

- 7일은 완료 상한이며 대기기간이 아니다.
- 외부 장애는 개인정보 보유 연장 근거가 아니다.
- users row 보존과 식별자 감사는 hard delete·최소 보존 원칙에 맞지 않는다.
- 가명 데이터는 비식별 통계가 아니며 다시 연결될 수 있다.
- snapshot backup은 사용자별 row 삭제가 아니라 recovery point lifecycle로 만료한다.

## 보안·개인정보·호환성 영향

삭제 job과 tombstone key가 노출되면 계정 상태 추적이나 복원 차단 우회가 가능하다. 로그에는
request ID를 포함한 구조화 운영 상태만 허용하고 user/provider 식별자, token, 생년월일,
원시 건강·오류 payload를 금지한다. 기존 `DELETE /api/v1/me` 공개 응답 필드는 유지하며
중복 요청 의미만 명확히 한다. 실제 API·DB 구현은 backend owner의 migration·호환성 검토가 필요하다.

## 아직 확정되지 않은 사항

- 실제 provider별 삭제 API와 운영 자격 증명 owner
- 실제 AWS backup 제품·리전·recovery point 증적 형식
- hard delete 후 identifier-free opaque 감사 레코드의 정확한 보존기간
- 출시 전 법률·개인정보 검토에서 확인될 별도 보존 의무

## 후속 작업

1. backend owner가 API service, repository, migration, provider port와 job을 구현한다.
2. 운영 owner가 provider 최종 실패와 backup restore runbook을 승인한다.
3. 출시 전 법률·개인정보 검토 결과가 이 계약을 바꾸면 새 ADR로 변경한다.
