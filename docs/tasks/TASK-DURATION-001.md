# TASK-DURATION-001: 요청 시간 합산·보존 규칙

- Primary owner: 개발·데이터 팀장
- Reviewers: 백엔드 담당자
- 관련 요구사항: `F002-1-17`, `F002-1-18`, `F002-1-20`, `F002-1-21`, `NFR-006-1-8`
- 관련 ADR: 없음
- 목표 브랜치: `feat/duration-core`

## 배경과 사용자 가치

사용자가 요청한 운동 시간은 계획 단계의 hard target이다. 계획이 준비·운동·휴식·전환·마무리 중 일부를 누락하거나 시스템이 사용자 동의 없이 시간을 변경하면 추천의 신뢰성과 재현성이 깨진다. Wave 1에서는 API와 저장소 구현보다 먼저 모든 후속 후보 생성·조정 로직이 공유할 결정적 시간 규칙을 만든다.

## 포함 범위

- `PROFILE`, `USER_OVERRIDE` 시간 출처 코드 검증
- `PROFILE` 출처에서 프로필 기본 시간과 요청 시간이 다른 경우 거부
- 준비·준비운동·동작·휴식·전환·마무리 전체 합산
- 문서에 확정된 초 단위 범위 검증
- 계획 합계와 `requested_duration_minutes * 60`의 정확 일치 검증
- 시간 규칙 버전 노출
- 순수 domain 단위·불변조건 테스트

## 제외 범위

- 정확한 시간을 구성하기 위한 운동 선택·세트·반복·휴식 배분 알고리즘
- 정확 구성 실패의 `NEEDS_INPUT` 또는 `BLOCKED` API 매핑
- requested duration 지원 상한·하한 정책
- 실제 경과 시간과 운동 완료 상태 계산
- API, DB 모델, repository, Alembic migration
- 카탈로그 importer와 안전·통증 제외 규칙

## 인수 조건

1. domain 코드는 FastAPI, SQLAlchemy, Firebase, LLM SDK에 의존하지 않는다.
2. 예상 시간은 준비·준비운동·모든 항목의 동작·휴식·전환·마무리를 빠짐없이 합산한다.
3. 준비 0~60초, 준비운동 60~180초, 항목별 전환 10~20초, 마무리 45~120초와 모든 초 단위 음수 금지를 검증한다.
4. `PROFILE` 출처에서 서버가 프로필 기본 시간과 다른 요청 시간을 만들 수 없다.
5. `USER_OVERRIDE` 출처에서는 사용자가 제출한 양의 시간을 새 목표로 사용할 수 있다.
6. 계획 합계가 요청 시간과 1초라도 다르면 성공 계획으로 검증되지 않는다.
7. 동일 입력은 동일 합계·평가·규칙 버전을 반환한다.
8. 40분 보존과 프로필 40분→사용자 30분 변경 시나리오를 테스트한다.

## 변경 예상 파일

- `backend/app/domain/__init__.py`
- `backend/app/domain/rules/__init__.py`
- `backend/app/domain/rules/duration.py`
- `backend/tests/unit/test_duration.py`
- `docs/tasks/TASK-DURATION-001.md`

## API 영향

없음. API adapter와 공통 오류 응답 매핑은 후속 task에서 연결한다.

## DB·마이그레이션 영향

없음. 후속 decision persistence가 이 모듈의 `duration_rule_version`을 저장해야 한다.

## 안전·개인정보·보안 영향

- 식별자·건강 원본·인증정보를 입력하거나 기록하지 않는다.
- LLM이 시간 목표 또는 검증 결과를 변경할 수 없는 순수 규칙 경계를 제공한다.
- 안전상 계획을 제공할 수 없는 경우의 REST·STOP 우선 규칙은 이 task가 변경하지 않는다.

## 선행 관계와 차단 요소

- `docs/DOMAIN_RULES.md` 5~6절과 `docs/DATA_MODEL.md`의 plan timing 계약을 기준으로 한다.
- requested duration 지원 범위와 정확 구성 실패 상태 매핑은 문서상 후속 승인이 필요하다.

## 테스트 계획

- 정확한 40분 계획 합산·검증
- 명시적 30분 override 합산·검증
- PROFILE 시간 변조 거부
- 알 수 없는 출처 코드와 0 이하 요청 시간 거부
- 각 시간 구성요소 경계값과 범위 밖 값 거부
- 목표보다 짧거나 긴 계획 거부
- 동일 입력 결정성 및 규칙 버전 확인

## 수동 확인

1. `uv run ruff check backend/app/domain backend/tests/unit/test_duration.py`
2. `uv run mypy backend/app/domain`
3. `uv run pytest backend/tests/unit/test_duration.py`

## 알려진 제한과 후속 작업

- API 요청의 `USER_OVERRIDE`가 실제 사용자 행위에서 왔는지는 인증된 API 경계에서 보장해야 한다.
- 계획 생성기는 승인된 카탈로그 후보만 사용해 이 규칙의 정확 일치 검증을 통과해야 한다.
- 지원 시간 범위와 실패 상태 매핑 승인 후 application service와 통합 테스트를 추가한다.
