# TASK-AGENT-001: 구조화 proposal 계약과 병렬 실행 core

> 상태: SUPERSEDED. 현재 구현·문서 기준은 ADR-0015와 `SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md`의 SafetyPolicyEngine·Training·Recovery·Feasibility 구조다.

- Primary owner: 개발·데이터 팀장
- Reviewers: 백엔드 담당자
- 관련 요구사항: `F002-1-10`, `F002-1-38`~`F002-1-46`, `NFR-006-1-13`
- 관련 ADR: `ADR-0007`
- 목표 브랜치: `feat/agent-001-proposal-core`

## 배경과 사용자 가치

Wave 2에서 catalog, 요청 시간, 결정적 Safety 규칙과 인증 경계가 준비되었다. 다음
결정 파이프라인이 자유 형식 결과나 일부 Agent 성공에 의존하지 않도록 네 전문 Agent가
공유할 내부 proposal 계약과 fail-closed 병렬 실행 경계를 먼저 제공한다.

## 포함 범위

- Training·Recovery·Safety·Feasibility의 고정 machine code와 실행 순서
- 버전이 명시된 내부 `AgentProposal` Pydantic 계약
- proposal 상태·action·요청 시간·운동 ID·제약·근거·정책 버전 구조 검증
- Safety proposal의 상태와 veto 구조 검증
- 동일한 정규화 context와 공통 후보 요청 객체를 네 Agent에 병렬 전달하는 port
- Agent 누락·중복·예외·잘못된 결과를 식별 정보 없는 `FAILED` proposal로 변환
- 네 proposal의 고정 순서 취합과 `READY/NEEDS_INPUT/FAILED` batch 상태
- candidate에 없는 preferred/excluded exercise ID 차단

## 제외 범위

- 정규화 `DecisionContext`와 공통 기본 candidate의 상세 schema·생성 로직
- Training·Recovery·Safety·Feasibility의 개별 정책 구현
- 미승인 수면·최근 부하·복귀 상한 또는 신체 부위별 수치 추가
- Coordinator의 후보 선택·최종 action·Safety 의견 반영 로직
- timeout·재시도 정책과 외부 LLM 호출
- API, SQLAlchemy model, repository, Alembic migration, proposal 저장
- 공개 회의 요약 schema와 사용자 문구

## 인수 조건

1. 네 Agent type과 proposal status/action은 승인된 machine code만 허용한다.
2. `READY` proposal은 요청 시간과 정확히 같은 예상 시간을 가지며, 다른 상태는 운동
   action이나 예상 시간을 가장하지 않는다.
3. proposal의 운동 ID는 실행 요청의 공통 candidate 운동 ID에 포함되어야 한다.
4. proposal의 정책 버전·요청 시간·시간 출처와 agent type이 실행 요청·등록 정보와
   다르면 해당 Agent를 `FAILED`로 처리한다.
5. 네 Agent는 동일한 immutable request를 병렬로 전달받고 결과는 완료 순서와 관계없이
   Training → Recovery → Safety → Feasibility 순서로 취합된다.
6. 필수 Agent 누락·중복·예외·invalid result 중 하나라도 있으면 batch는 `FAILED`이며
   운동 계획 성공으로 진행할 수 없다.
7. `NEEDS_INPUT`이 하나라도 있고 `FAILED`가 없으면 batch는 `NEEDS_INPUT`이며 운동 계획
   성공으로 진행할 수 없다.
8. Safety proposal의 `PASS/REVISE/BLOCKED/NEEDS_INPUT/FAILED`와 veto는 batch에서 변경하지
   않고 보존한다.
9. 예외 메시지·context 원문·직접 식별자·건강 원문을 failure proposal이나 로그에 넣지
   않는다.
10. domain 코드는 FastAPI, SQLAlchemy, Firebase, LLM SDK에 의존하지 않는다.

## 변경 예상 파일

- `docs/tasks/TASK-AGENT-001.md`
- `backend/app/domain/agents/README.md`
- `backend/app/domain/agents/contracts.py`
- `backend/app/domain/agents/runner.py`
- `backend/app/domain/agents/__init__.py`
- `backend/tests/unit/test_agent_contracts.py`
- `backend/tests/unit/test_agent_runner.py`
- `backend/tests/scenarios/test_agent_runner_golden.py`

## API 영향

없음. 이 계약은 내부 domain alpha schema이며 공개 request/response에 추가하지 않는다.

## DB·마이그레이션 영향

없음. 후속 decision persistence task에서 proposal과 final decision을 별도 저장하고 schema
version을 보존해야 한다.

## 안전·개인정보·보안 영향

- Safety 상태와 veto를 별도 필드로 검증하고 취합 과정에서 수정하지 않는다.
- failure reason은 고정 machine code만 사용하며 예외 문자열과 입력 snapshot을 복사하지
  않는다.
- runner는 context 내용을 검사·기록하지 않는다. 호출자는 후속 승인된 context builder를
  통해 생년월일·만 나이·이메일·이름·원시 건강·웨어러블 데이터를 제거해야 한다.

## 선행 관계와 차단 요소

- Wave 2 catalog, duration, Safety core가 `develop`에 병합되어 있다.
- `ACCEPTED` ADR-0007의 네 proposal 병렬 구조와 fail-closed 원칙을 따른다.
- proposal 상세 계약은 아직 잠정이므로 `0.x` 내부 schema로 격리한다.
- 개별 Agent 정책과 Coordinator는 공통 candidate 및 상세 context 계약 승인 전 구현하지
  않는다.

## 테스트 계획

- enum, machine reference, canonical tuple, 상태별 필드와 Safety 불변식 검증
- policy/requested duration/source/agent type 불일치 차단
- candidate 밖 운동 ID 차단
- 동일 request 전달과 네 Agent 동시 실행 확인
- 완료 순서와 무관한 고정 proposal 순서와 재현 결과
- Agent 누락·중복·예외·invalid result의 식별정보 없는 failure 변환
- `FAILED` 우선, `NEEDS_INPUT` 차순위 batch 상태와 계획 성공 차단
- Safety veto 보존 골든 시나리오

## 수동 확인

1. `uv run ruff format --check backend/app/domain/agents backend/tests/unit/test_agent_*.py backend/tests/scenarios/test_agent_runner_golden.py`
2. `uv run ruff check backend/app/domain/agents backend/tests/unit/test_agent_*.py backend/tests/scenarios/test_agent_runner_golden.py`
3. `uv run mypy backend/app/domain/agents`
4. `uv run pytest backend/tests/unit/test_agent_contracts.py backend/tests/unit/test_agent_runner.py`
5. `uv run pytest backend/tests/scenarios/test_agent_runner_golden.py`
6. `uv run pytest backend/tests`

## 알려진 제한과 후속 작업

- timeout·재시도 정책은 ADR-0007 후속 승인이 필요하다.
- 공통 context/candidate builder와 catalog membership의 source-of-truth 연결이 필요하다.
- 네 개별 Agent와 결정적 Coordinator, Safety veto 후보 선택 차단은 별도 task로 구현한다.
- proposal persistence와 공개 요약은 API·DB 계약 및 증상 사용자 시나리오 승인 후 구현한다.
