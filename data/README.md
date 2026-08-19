# Data

- `raw/`: 변경하지 않는 원천 JSON 스냅샷과 출처 매니페스트
- `validation/profiles/`: 원천 품질·커버리지 프로파일
- `validation/review_batches/`: 검토 대상 배치와 빈 증적 템플릿
- `validation/review_results/`: 포함·제외 결정, 역할별 증적, 정규화 속성
- `normalized/`: taxonomy, 안전 정책, 에이전트 검토 정책·계획
- `generated/`: 검증된 DRAFT 카탈로그 시드와 안전 규칙
- `reports/`: 수집 데이터 보고서와 전처리 보고서
- `scripts/`: 수집·프로파일·검토·생성·검증 자동화

2026-08-11 현재 KSPO 50개와 wger 60개 리뷰 후보의 결정을 모두 완료했다. 포함
50개, 제외 60개, 미결 0개이며 카탈로그와 안전 규칙은 모두
`review_method_code=AGENT_ONLY`, `production_eligible=false`인 DRAFT다.

세부 현황과 추가 수집 재개 조건은 [수집 데이터 보고서](reports/DATA_COLLECTION_REPORT.md),
정규화·분포·검증 결과는 [데이터 전처리 보고서](reports/DATA_PREPROCESSING_REPORT.md)를
참조한다. 파이프라인 경계는 [PIPELINE.md](PIPELINE.md)에 정의돼 있다.
