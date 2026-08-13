# TASK-SAFETY-001: 결정적 SafetyRule core

- Primary owner: 개발·데이터 팀장
- Reviewers: 백엔드 담당자, PM, 외부 도메인 검수자
- 관련 요구사항: `F002-1-15`, `F002-1-20`, `F002-1-21`, `NFR-006-1-9`, `NFR-006-1-12`
- 관련 ADR: `ADR-0004`, `ADR-0007`
- 목표 브랜치: `feat/safety-rule-core`

## 배경과 사용자 가치

SafetyAgent와 Coordinator가 안전 입력을 임의 해석하지 않도록, 이상 반응·불편 심각도와 검수된 제외 규칙을 평가하는 결정적 domain 경계를 먼저 제공한다. 안전 결과는 LLM이나 다른 proposal이 완화할 수 없고, 사용한 규칙셋 버전과 적용 규칙을 저장 가능한 형태로 반환해야 한다.

## 포함 범위

- 문서에 확정된 불편 심각도와 이상 반응 machine code
- 긴급 중단 그룹의 `BLOCKED + STOP_AND_SEEK_HELP` 우선 처리
- 급성 근골격 신호 또는 SEVERE 불편의 `BLOCKED + REST` 처리
- MILD/MODERATE 불편과 운동·movement pattern 규칙의 결정적 매칭
- `EXCLUDE`와 `CAUTION` 적용, 현재 후보 전체 제외 시 `BLOCKED + REST`
- `DOMAIN_APPROVED`이면서 `production_eligible=true`인 규칙셋만 계획 판단에 사용
- 규칙셋 누락·미승인의 `FAILED` fail-closed 처리
- 규칙셋·규칙·후보·체크인 입력 불변조건 검증
- 동일 입력의 순서와 관계없는 결정적 결과 및 규칙 버전·근거 참조

## 제외 범위

- 현재 `AGENT_ONLY`, `production_eligible=false`인 생성 안전 규칙의 운영 사용
- 안전 임계값, 수면·누적 부하 수치, 복귀 볼륨 상한 추가
- 대체 운동 탐색, 목표 보존, 장소·장비 검증과 회복안 생성
- SafetyAgent proposal과 Coordinator 구현
- 독립적인 Safety 사전검사 또는 최종 Safety gate
- API, SQLAlchemy 모델, repository, Alembic migration
- 사용자 안내 문구 변경

## 인수 조건

1. 긴급 중단 그룹이 하나라도 있으면 다른 입력보다 우선하여 `STOP_AND_SEEK_HELP`, plan veto를 반환한다.
2. 긴급 중단이 없고 급성 근골격 신호 또는 SEVERE 불편이 있으면 `REST`, plan veto를 반환한다.
3. MILD/MODERATE 불편은 같은 body area·severity 범위·catalog의 exercise 또는 movement pattern 규칙만 적용한다.
4. `EXCLUDE`가 적용된 운동은 현재 후보에서 안전 승인될 수 없다.
5. 모든 운동이 제외되면 `BLOCKED + REST`, 일부 제외·주의면 `REVISE`, 적용 규칙이 없으면 `PASS`다.
6. 안전 규칙이 필요한데 규칙셋이 없거나 운영 승인되지 않았으면 `FAILED`이며 계획을 허용하지 않는다.
7. `DOMAIN_APPROVED` 표기만 있고 `production_eligible=false`인 규칙셋은 거부한다.
8. 동일 의미의 입력 순서가 달라도 같은 정렬된 결과와 ruleset version을 반환한다.
9. domain 코드는 FastAPI, SQLAlchemy, Firebase, LLM SDK에 의존하지 않는다.
10. 새 의료 임계값이나 미승인 신체 부위별 규칙을 코드에 추가하지 않는다.

## 변경 예상 파일

- `docs/tasks/TASK-SAFETY-001.md`
- `backend/app/domain/rules/safety.py`
- `backend/app/domain/rules/__init__.py`
- `backend/tests/unit/test_safety.py`
- `backend/tests/scenarios/test_safety_golden.py`

## API 영향

없음. 후속 SafetyAgent/application service가 이 결과를 proposal·공통 오류 계약에 매핑한다.

## DB·마이그레이션 영향

없음. 후속 persistence는 `safety_rule_set_version`, 적용 rule reference, 제외 운동과 veto를 저장해야 한다.

## 안전·개인정보·보안 영향

- 직접 식별자, 생년월일, 만 나이, 원시 건강 기록을 입력받거나 기록하지 않는다.
- 안전 결과를 낮은 우선순위 proposal 또는 LLM이 완화할 수 없는 불변 domain 결과로 만든다.
- 현재 데이터 파이프라인의 호환성 표기를 외부 전문가 운영 승인으로 해석하지 않는다.
- 이 PR은 안전 코드이므로 백엔드·PM 검토와 필요한 외부 도메인 승인 증적 전 병합하지 않는다.

## 선행 관계와 차단 요소

- `docs/DOMAIN_RULES.md` 2~4절, 13절과 `ACCEPTED` ADR-0004·0007을 기준으로 한다.
- Wave 1 catalog core와 duration core가 `develop`에 병합되어 있어야 한다.
- 운영 규칙 데이터 연결은 외부 검수와 `production_eligible=true` 승격 후 별도 task로 수행한다.

## 테스트 계획

- 긴급 반응과 다른 신호가 함께 있을 때 STOP 우선
- 급성 근골격 신호와 SEVERE 불편의 REST
- 무릎 MILD/MODERATE exercise·movement rule 매칭
- catalog·body area·severity 범위가 다른 규칙 미적용
- EXCLUDE 우선, 일부/전체 제외, CAUTION 처리
- 미승인·비운영·누락 규칙셋 fail-closed
- 잘못된 scope·중복 코드·NONE 입력 거부
- 입력 순서 독립성과 버전·근거 재현
- 무릎 MILD/MODERATE, SEVERE, 긴급 반응, veto 골든 시나리오

## 수동 확인

1. `uv run ruff check backend/app/domain backend/tests/unit/test_safety.py`
2. `uv run mypy backend/app/domain`
3. `uv run pytest backend/tests/unit/test_safety.py`
4. `uv run pytest backend/tests/scenarios/test_safety_golden.py`
5. `uv run pytest backend/tests`

## 알려진 제한과 후속 작업

- 승인된 대체 관계와 장소·장비를 사용한 후보 재구성은 후속 candidate task에서 구현한다.
- SafetyAgent는 이 결과를 구조화 proposal로 변환하되 veto를 완화할 수 없다.
- 안전 규칙 importer와 repository가 production 승인 메타데이터를 domain port로 전달해야 한다.
- 각 신체 부위·movement pattern의 운영 규칙과 회복 콘텐츠는 외부 검수 후 활성화한다.
