# TASK-DATA-006: tranche 3 운동 검토와 파생 데이터 확장

- Primary owner: 개발 리드·백엔드/데이터 리드
- 관련 문서: `docs/tasks/TASK-DATA-005.md`, `data/AGENTS.md`,
  `docs/DOMAIN_RULES.md`, `docs/DATA_MODEL.md`
- 목표 브랜치: `feat/data-001-pipeline-bootstrap`

## 배경과 사용자 가치

TASK-DATA-005에서 기존 프로파일의 비중복 후보 11건을 후속 검토 큐로 좁혔다. 다음 단계는
개수 확대가 아니라 실제 홈·헬스장 커버리지 공백을 메우는 후보만 보수적으로 포함하고,
포함분에 안전 규칙과 목표 보존형 대체 관계가 함께 생성되는지 확인하는 것이다.

## 포함 범위

- tranche 3 후보 11건을 INCLUDE 또는 EXCLUDE로 완전 분할
- 포함 후보의 정규화 ID, 표시명, taxonomy, 난이도, 부하 부위, 장비·장소, 수행 안내 작성
- 4개 에이전트 역할 검토 증적과 결정 근거 기록
- 기존 50개와 분리된 tranche 3 증분 catalog seed 생성
- 확장 카탈로그 전체를 입력으로 안전 규칙·대체 관계 재생성
- 신규 운동 관련 안전·대체 golden scenario 추가
- 모든 결과를 `AGENT_ONLY`, `production_eligible=false`로 유지

## 제외 범위

- 외부 운동·재활 전문가 승인을 받았다고 간주하는 운영 승격
- API, DB schema, migration 또는 운영 DB 적재
- 정식 데이터 수집·전처리 보고서 갱신
- 새 taxonomy 코드 추가
- 특정 운동과 MET 활동의 자동 매핑
- 사용자별 진단·치료·재활·처방 판단

## 검토 결정 원칙

- INCLUDE: 기존 카탈로그의 명확한 홈/장비/목표 공백을 메우고 승인 코드로 표현 가능
- EXCLUDE: 기존 운동의 세부 변형, 원천 장비 충돌, 동작 의미가 포괄적, 안전한 대체 그룹 부재
- 포함 운동도 `DOMAIN_APPROVED`는 파이프라인 호환 상태일 뿐 전문가 운영 승인 아님

## 인수 조건

1. 11개 후보가 INCLUDE 또는 EXCLUDE로 중복 없이 완전 분할된다.
2. 불확실한 원천 의미나 장비 충돌은 포함하지 않는다.
3. 포함 운동의 부하 부위가 기존 안전 pattern policy와 모순되지 않는다.
4. 기존 50개와 신규 stable code·표시명·원천 identity가 중복되지 않는다.
5. 증분 seed는 입력 큐·검토 계획·taxonomy·검토 정책 해시를 추적한다.
6. 대체 정책에 추가한 운동은 정확한 목표 그룹에만 속하고 더 어려운 대체를 만들지 않는다.
7. 확장 안전 규칙과 대체 관계가 해시 검증과 golden scenario를 통과한다.
8. 모든 결과는 `AGENT_ONLY`, `production_eligible=false`다.
9. 전체 데이터 테스트와 정적 검사가 통과한다.

## 변경 예상 파일

- `docs/tasks/TASK-DATA-006.md`
- `data/normalized/review_tranche_3.agent.json`
- `data/validation/review_results/review_tranche_3_results.json`
- `data/scripts/review_tranche_3_candidates.py`와 테스트
- `data/scripts/build_tranche_3_catalog_seed.py`와 테스트
- `data/generated/exercise-catalog-seed-*-tranche3-v0.1.0/**`
- `data/normalized/exercise_alternative_policy.json`
- 확장 안전 규칙·대체 관계·golden scenario 산출물

## API 영향

없음.

## DB·마이그레이션 영향

없음. seed는 운영 DB에 적재하지 않는다.

## 안전·개인정보·보안 영향

- 공개 운동 원천만 사용하고 사용자 건강 데이터나 식별자를 다루지 않는다.
- 통증 부위 규칙은 기존 보수적 정책에서만 생성하며 새 의료 판단을 추가하지 않는다.
- 원천의 의료 표현은 사용자 안내에 복제하지 않는다.

## 테스트 계획

- 검토 계획 완전 분할·중복·허용 코드·표시명 검증
- 기존 카탈로그와 증분 seed 중복 검증
- seed·안전 규칙·대체 관계 manifest 변조 검증
- 신규 홈 수직 당기기, 낮은 장벽 밀기, 삼두 장비 대체 시나리오
- ruff, format, mypy, 전체 데이터 테스트

## 알려진 제한과 후속 작업

- 증분 카탈로그는 운영 승인이 아니며 실제 서비스 계약 반영은 별도 작업이다.
- 안전한 대체 목표 그룹이 없는 후보는 데이터량 확대를 위해 억지로 포함하지 않는다.
- 정식 보고서는 전체 데이터 작업 종료 후 사용자 제공 양식에 맞춰 별도 작성한다.
