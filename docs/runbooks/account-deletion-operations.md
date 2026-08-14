# 계정 삭제 운영·실패 복구 runbook

## 목적과 범위

이 문서는 scheduler나 queue 없이 account deletion application/job service를 운영자가
one-shot으로 실행하는 경계를 설명한다. 실제 Firebase 삭제 adapter, AWS backup 리소스,
backup evidence adapter와 audit purge scheduler는 Wave 9A 범위에 포함하지 않는다.

운영 실행 전 승인된 provider revocation adapter와 backup verification adapter를 dependency로
주입해야 한다. token, provider subject, 사용자 UUID, 이메일, 생년월일, 건강 데이터와 원시
exception을 로그나 운영 티켓에 복사하지 않는다.

## 정상 실행

1. `AccountDeletionJobService.runnable_job_ids(session, limit=...)`로 실행 가능한 opaque
   `deletion_job_id`만 조회한다.
2. 각 ID를 별도 `AccountDeletionJobService.run_job(session, deletion_job_id)` 호출로 처리한다.
3. 요청 직후부터 `PENDING` job을 실행한다. 7일 deadline까지 기다리지 않는다.
4. provider 호출은 DB transaction 밖에서 실행된다. 성공 identity는 `revoked_at` checkpoint로
   남겨 재실행할 때 건너뛴다.
5. user-linked DB 삭제와 linked job → opaque audit 전환은 단일 transaction이다.
6. 결과가 `BACKUP_EXPIRY_PENDING`이면 승인된 AWS 운영 증적을 반환하는 adapter가 준비된 후
   같은 job ID를 다시 실행한다.
7. `COMPLETED` 또는 `COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE`를 확인한다.

시간 경과만으로 backup evidence를 만들거나 완료 상태를 직접 기록하지 않는다.

## 상태별 조치

| 상태 | 의미 | 운영 조치 |
|---|---|---|
| PENDING | 요청 저장, 즉시 실행 가능 | `run_job` 실행 |
| RUNNING | 실행 중 또는 중단된 checkpoint | 동일 opaque job ID로 재실행 |
| RETRY_PENDING | provider 재시도 가능 실패 | provider 복구 후 재실행 |
| BACKUP_EXPIRY_PENDING | 로컬 hard delete와 de-identification 완료 | 승인된 backup evidence 확인 후 재실행 |
| FAILED_REQUIRES_REVIEW | 운영 DB 삭제가 완료되지 않은 실패 | 접근 차단 유지, 개발팀장/개인정보 담당자 검토 및 승인된 forward-fix 수행 |
| COMPLETED | provider·로컬 삭제·backup 확인 완료 | 추가 실행 불필요 |
| COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE | provider 최종 실패, 로컬·backup 완료 | 개인정보 승인된 별도 provider 운영 절차로 이관 |

`FAILED_REQUIRES_REVIEW`에는 승인된 성공 전이가 없다. DB에서 상태를 수동 변경하거나 새
job을 임의 생성하지 않는다.

## provider 실패 복구

- 7일 기한 전 실패는 `RETRY_PENDING / EXTERNAL_REVOCATION`이다.
- provider adapter는 이미 존재하지 않는 계정·연결을 성공으로 취급하는 멱등 계약이어야 한다.
- 재실행 시 이미 성공한 identity는 다시 호출하지 않는다.
- 기한 시점의 마지막 시도도 실패하면 `FAILED_FINAL`로 기록하고 식별정보 없는 구조화 경보를
  발생시킨 뒤 로컬 hard delete를 계속한다.
- opaque 감사 레코드에는 provider subject가 없으므로 이후 자동 provider 재시도는 하지 않는다.

## DB 삭제 실패 복구

- transaction rollback으로 사용자 데이터, linked job과 감사 전환의 부분 commit을 막는다.
- 결과는 `FAILED_REQUIRES_REVIEW`이며 완료로 취급하지 않는다.
- 운영 경보에는 `deletion_job_id`와 allowlist `failure_code`만 사용한다.
- 원시 SQL, exception message, stack trace, 사용자 식별자 또는 데이터 snapshot을 상태 컬럼이나
  로그에 저장하지 않는다.
- 원인을 수정한 migration 또는 repository forward-fix와 재처리 방식은 별도 승인을 받는다.

## backup evidence

- `backup_expiry_due_at`은 요청 시각 + 30일이다.
- 실제 AWS recovery point가 해당 사용자를 포함할 수 없다는 운영 증적이 있어야 한다.
- Wave 9A port는 `deletion_job_id`, deadline과 검증 시각만 애플리케이션에 전달한다.
- raw AWS 응답, ARN, 사용자 식별자와 복구 데이터는 opaque 감사 row에 저장하지 않는다.

## 점검 쿼리 원칙

운영 현황 조회에서는 `deletion_job_id`, 상태, stage, deadline, attempt count와 allowlist failure
code만 선택한다. linked job 테이블의 `user_id`와 identity 테이블을 join하거나 결과를 로그로
내보내지 않는다.

## 남은 정책 의존성

- opaque audit의 정확한 TTL과 `audit_expires_at` 설정 방식
- 실제 AWS backup evidence adapter와 운영 증적 owner
- 실제 Firebase/provider 삭제 adapter
- audit purge scheduler 또는 queue 도입 여부
