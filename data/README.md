# Data

- `raw/`: 변경하지 않는 출처 원본 또는 출처 manifest
- `normalized/`: 애플리케이션 중립 정규화 결과
- `generated/`: 승인 seed 등 코드베이스 소비 산출물
- `scripts/`: 수집·정규화·검증 스크립트
- `validation/`: schema, 품질 보고서, 승인 증적

첫 수집 파이프라인의 범위와 승격 게이트는 [PIPELINE.md](PIPELINE.md)를 따릅니다.
현재 구현은 국민체력100 OpenAPI와 wger 공개 exercise catalog의 원문 JSON 수집,
무결성 재검증 및 검토용 profile 생성을 지원합니다. wger는 헬스장 기구·프리웨이트
종목의 보강 후보로만 사용합니다. 정규화, 안전 규칙 작성, 한국어 현지화 및 DB seed
생성은 별도 검토 작업입니다.
