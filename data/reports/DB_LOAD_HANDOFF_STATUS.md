# DB 적재 전 인계 상태

- 기준일: 2026-08-24
- 인계 범위: `data/generated/exercise-catalog-v2.0.0-final/`
- 인계 목적: DB 적재 실행 전 데이터·검토 결과를 백엔드 담당자에게 전달
- DB 적재 실행: 하지 않음

## 작업 상태

주인님 확인 기준으로 다음 세 항목은 완료 상태로 인계한다.

| 항목 | 인계 상태 | 대상 산출물 |
|---|---|---|
| 1. 대표 운동 속성·콘텐츠·권리 검토 | `USER_DECLARED_COMPLETE` | 대표 운동 102건, 콘텐츠·안전 보조 산출물 |
| 2. 안전 규칙·운동 매핑 도메인 검토 | `USER_DECLARED_COMPLETE` | 안전 규칙 384건, REX 매핑 406건 |
| 3. 목표 보존 대체 관계 검토 | `USER_DECLARED_COMPLETE` | 대체 관계 116건 |

`USER_DECLARED_COMPLETE`는 이번 인계 지시로 기록한 업무 상태이며, 생성 파일의
`production_eligible`, `activation_status`, `review_status_code`를 임의로 변경한
운영 승격을 의미하지 않는다. 원본 증적과 승인자·승인 시각은 기존 검토 파일을
그대로 보존한다.

## 적재 전 기술 확인

- 최종 산출물 SHA-256은 `finalization_validation_report.json`과 일치한다.
- 최종 폴더는 현재 백엔드 `CatalogImporter`가 요구하는 `seed_manifest.json` 및
  JSONL bundle 형식이 아니다.
- 백엔드 기본 적재 명령은 이 폴더가 아닌
  `exercise-catalog-seed-merged-mvp-v0.4.0` 및 별도 파생 bundle을 참조한다.
- 따라서 본 문서는 DB 적재 직전 인계 문서이며, DB 적재 가능 판정이나 적재 완료
  기록이 아니다.

## 다음 담당 작업

1. 승인 증적을 백엔드 bundle 계약(`seed_manifest.json`, JSONL, 파생 manifest)에
   매핑한다.
2. 백엔드 importer 검증과 실제 대상 DB의 dry-run을 수행한다.
3. 검증 통과 후에만 DB 적재 및 catalog activation을 실행한다.

근거: [최종화 검증 보고서](../generated/exercise-catalog-v2.0.0-final/finalization_validation_report.json),
[V2 스키마 정합성 검토](V2_SCHEMA_ALIGNMENT_REVIEW.md),
[Catalog importer 계약](../../backend/app/modules/catalog/service.py).
