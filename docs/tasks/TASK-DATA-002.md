# TASK-DATA-002: 에이전트 기반 MVP 운동 카탈로그 마감과 데이터 보고서

- Primary owner: 개발 리드·백엔드/데이터
- Reviewers: 백엔드, PM(라이선스), 에이전트 검토 역할 4종
- 관련 요구사항: MVP_SCOPE 5.3·11.4, DATA_MODEL 5·15, DOMAIN_RULES 3·4·5·16
- 관련 ADR: 없음
- 목표 브랜치: `feat/data-001-pipeline-bootstrap`

## 배경과 사용자 가치

KSPO와 wger 초기 원천 수집·profiling은 완료됐지만 review batch 110건 중 86건이
`PENDING`이다. 개별 외부 전문가 검수가 현실적으로 어려운 운영 조건에서 에이전트 검토와
결정적 validator를 사용해 MVP 규모의 DRAFT 카탈로그를 마감하고, 추가 원천 수집 필요성을
커버리지 근거로 판단한다.

## 포함 범위

- 현재 `PENDING` 86건 전체의 INCLUDE, MERGE 또는 EXCLUDE 판정
- 에이전트 검토 방법·근거·한계를 나타내는 비식별 증적
- 총 50~80종 범위의 DRAFT 카탈로그 구성
- 한국어 표시명, taxonomy, 초보자 적합성, 시간·휴식, 부하 부위, 원문을 복제하지 않은 수행 안내
- 카탈로그 입력 파일과 생성 산출물 사이의 SHA-256 추적성 보강
- 카탈로그 커버리지와 추가 수집 필요성의 기계적 판정
- 데이터 수집 보고서와 데이터 전처리 보고서
- 기존 snapshot, profile, review batch, 결과, seed, 안전 규칙의 재검증

## 제외 범위

- 전문가 검수로 표현되는 승인
- 사용자별 의료 판단, 진단, 치료 또는 재활 처방
- 이미지·영상 바이너리 수집
- 프로덕션 활성화와 사용자 노출
- DB schema, migration, 실제 seed import
- 칼로리 산식·MET 원천 도입

## 인수 조건

1. 기존 86개 `PENDING` 행이 모두 명시적 판정을 가진다.
2. INCLUDE/MERGE 행은 구조화된 속성·증적을 갖고 기존 validator를 통과한다.
3. 모든 에이전트 검토 결과는 `review_method_code=AGENT_ONLY`이며
   `production_eligible=false`임이 manifest와 보고서에 명시된다.
4. 최종 DRAFT 카탈로그는 50~80종이다.
5. 장소·장비·난이도·운동 유형·패턴·회복 후보 커버리지를 보고한다.
6. 추가 수집은 기존 후보로 필수 커버리지를 채울 수 없을 때만 필요하다고 판정한다.
7. 생성 manifest가 mapping, evidence, attributes, taxonomy와 상위 manifest의 해시를 기록한다.
8. 원문 또는 산출물 변조 시 재검증이 실패한다.
9. 수집 보고서와 전처리 보고서가 규모, 결측, 라이선스, 개인정보, 한계와 후속 작업을 포함한다.
10. 공개 API·DB 계약은 변경하지 않는다.

## 변경 예상 파일

- `data/scripts/**`와 대응 단위 테스트
- `data/normalized/**`
- `data/validation/review_results/**`
- `data/generated/**`
- `data/reports/**`
- `data/PIPELINE.md`와 관련 README

## API 영향

없음. 모든 결과는 오프라인 DRAFT 데이터 산출물이다.

## DB·마이그레이션 영향

없음. DB 적재는 후속 task로 분리한다.

## 안전·개인정보·보안 영향

에이전트 검토는 전문가 검수로 표현하지 않는다. 불확실한 안전 값은 보수적으로 제외하거나
`PENDING`으로 남기며 사용자별 질환·건강 데이터는 사용하지 않는다. 원문에 포함된 공개
기여자 연락처는 추적되는 파생 데이터에서 최소화하고 인증정보는 기록하지 않는다.

## 선행 관계와 차단 요소

- DATA-001 snapshot·profile·review batch 무결성 검증 완료
- taxonomy registry 승인 상태 확인
- 외부 전문가 검수 없이 프로덕션 승격할 수 있는 별도 정책은 이 task에서 결정하지 않음

## 테스트 계획

- 기존 데이터 스크립트 전체 단위 테스트
- 에이전트 검토 계획의 원천 identity·중복·상태 검증
- seed 입력 해시 및 변조 탐지 테스트
- 50~80종 규모와 커버리지 기준 테스트
- 안전 규칙 재생성과 무릎 불편 골든 시나리오
- ruff, format, mypy

## 수동 확인

- 최종 카탈로그의 홈·헬스장·야외 및 운동 유형 분포 확인
- EXCLUDE 사유와 라이선스 판단 표본 확인
- 보고서 수치와 manifest 수치 대조

## 알려진 제한과 후속 작업

에이전트 검토는 자격을 갖춘 운동·재활 전문가의 검수가 아니다. 프로덕션 승격, 사용자 노출,
DB 적재와 운영 모니터링은 별도 작업과 승인 게이트가 필요하다.
