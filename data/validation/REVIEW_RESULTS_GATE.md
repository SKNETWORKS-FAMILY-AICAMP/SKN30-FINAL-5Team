# wger 헬스장 검토 결과 게이트

상태: `DRAFT`  
validator version: `0.1.0`  
production eligible: `false`

## 목적

검토자가 작성한 운동 매핑 결과와 역할별 증적을 원본 review batch에 대조한다. 이 게이트는
원천 identity 변경, 근거 없는 승인 및 안전 검수 누락을 실패 처리한다. 검증 성공은
normalized seed 생성이나 프로덕션 승격이 아니다.

## 계약 근거

`docs/DATA_MODEL.md`의 다음 계약을 사용한다.

- exercise의 프로덕션 사용은 `DOMAIN_APPROVED`만 가능하다.
- `catalog_review_records`는 대상, 상태, reviewer role, 내부 비식별 reviewer reference,
  evidence reference와 검토 시각을 보존한다.
- reviewer role은 `DATA_OWNER`, `BACKEND_REVIEWER`, `PM_REVIEWER`,
  `DOMAIN_REVIEWER`다.

외부 검수자의 실제 자격 확인, 계약 및 운영상 ID 발급 방식은 이 파이프라인에서 결정하지
않는다.

## 입력

1. 검증된 gym-core review batch v0.2.0
2. 배치의 `gym_core_review_batch.csv`를 복사해 작성한 mapping results
3. 배치의 `catalog_review_records_template.csv`를 복사해 작성한 evidence results

원본 파일은 manifest 해시 검증 대상이므로 직접 수정하지 않는다.

## 매핑 행 검증

- source ID, UUID, 영문 원천명, 장비, 라이선스 등 원천 필드는 변경할 수 없다.
- `PENDING` 행은 미완료 상태로 검증 가능하지만 승인 후보가 아니다.
- `EXCLUDE`에는 제외 사유가 필요하다.
- `INCLUDE` 또는 `MERGE`에는 다음 값이 모두 필요하다.
  - 소문자 machine code 형식의 정규화 운동 ID
  - 한국어 표시명
  - 소문자 machine code 형식의 taxonomy code
  - 검토된 초보자 적합성
  - 실행 안내, 라이선스 및 도메인 안전 상태 `APPROVED`

현재 movement pattern과 training type의 최종 코드 목록은 미확정이므로 이 단계에서는
코드 형식만 검증하며 DB seed를 생성하지 않는다.

## 증적 행 검증

각 운동에는 다음 네 역할의 증적 행이 하나씩 있어야 한다.

| reviewer role | INCLUDE/MERGE에 필요한 상태 |
|---|---|
| DATA_OWNER | TECH_REVIEWED 또는 DOMAIN_APPROVED |
| BACKEND_REVIEWER | TECH_REVIEWED 또는 DOMAIN_APPROVED |
| PM_REVIEWER | TECH_REVIEWED 또는 DOMAIN_APPROVED |
| DOMAIN_REVIEWER | DOMAIN_APPROVED |

`DRAFT`가 아닌 증적은 다음 값을 모두 요구한다.

- reviewer reference: 이메일·실명이 아닌 내부 비식별 opaque code
- evidence reference: 문서, 이슈, PR 또는 검토 기록 참조
- reviewed_at: timezone이 포함된 ISO 8601 시각

사용자 건강 데이터, 검수자 이메일·실명, 인증정보는 결과 파일에 기록하지 않는다.

## 실행

```powershell
python data/scripts/validate_wger_gym_review_results.py `
  "data/validation/review_batches/<gym-core-review-v0.2.0>" `
  "<mapping-results.csv>" `
  "<evidence-results.csv>"
```

검증 결과의 `review_complete_rows`는 구조와 증적이 완성된 INCLUDE/MERGE 행 수다.
`production_eligible`은 항상 `false`이며, 후속 normalized schema 및 seed 승격 게이트가
별도로 필요하다.
