# TASK-V3-ROUND2-QUALITY-IMPROVEMENT: 멀티에이전트 품질·가용성 개선과 2차 평가

- Primary owner: AI/data lead
- Reviewers: 개발리드, PM
- 관련 요구사항: F002, F029, NFR-003, NFR-006
- 관련 ADR: ADR-0015, ADR-0021
- 목표 브랜치: `fix/v3-round2-quality-improvement`

## 배경과 사용자 가치

1차 평가는 Multi-Agent가 안전하다는 근거는 확보했지만 Single-Agent RAG보다 비용 대비 품질이
우월하다는 근거는 확보하지 못했다. advisory `NEEDS_INPUT`이 전체 경로를 차단하고, 역할과 무관한
payload가 토큰을 늘리며, Judge와 사람 평가의 사례별 상관도 낮았다. 안전 불변식을 유지하면서
가용성·조정 추적성·토큰 효율을 개선한 뒤 독립된 2차 평가가 필요하다.

## 포함 범위

- ADR-0021 readiness 계약 구현
- Recovery/Feasibility 역할별 최소 LLM payload
- specialist와 Coordinator prompt 개선 및 version bump
- 계약·라우팅·privacy·fallback·golden/safety 회귀 테스트
- v1과 분리된 2차 테스트 결과와 보고서
- Human 평가를 1차 지표로 사용하고 Judge calibration은 별도 보고

## 제외 범위

- SafetyPolicyEngine, pain/recovery policy 값, integrity validator 규칙 변경
- 공개 API와 DB schema 변경
- 신규 운동·금기·대체 규칙 생성
- V1 결과 파일 수정
- Recovery/Feasibility 제거 또는 새 conflict/review round 도입

## 인수 조건

1. Training이 `READY`이고 advisory만 `NEEDS_INPUT`이면 Coordinator가 실행된다.
2. Training non-READY, 임의 specialist `FAILED`, 누락, timeout, provider/schema/domain 오류는
   기존 fail-closed 경로를 유지한다.
3. Safety golden 100%, critical failure 0건, safety veto 우회 0건이다.
4. 오프라인 workflow completion은 100%, 실-provider 목표는 95% 이상이다.
5. 2차 held-out Human 평균에서 Multi-Agent - Single-Agent RAG 차이가 `+0.20` 이상이다.
6. v1 Multi-Agent 대비 평균 input+output token을 25% 이상 줄인다.
7. Multi-Agent P95 latency 목표는 30초 이하이며 미달 시 우월성 결론을 보류한다.
8. 같은 case/model/catalog/policy로 비교하고 기존 20개 case는 회귀용으로만 사용한다.

## 변경 예상 파일

- `docs/adr/0021-v3-advisory-readiness-and-minimum-payload.md`
- `docs/tasks/TASK-V3-ROUND2-QUALITY-IMPROVEMENT.md`
- `docs/test/ROUND2_IMPROVEMENT_PLAN.md`
- `docs/ARCHITECTURE.md`
- `backend/app/domain/agents/AGENTS.md`
- `backend/app/domain/agents/v3_contracts.py`
- `backend/app/integrations/langgraph/{nodes.py,routing.py,README.md}`
- `backend/app/integrations/llm_agents/{payload.py,prompts.py}`
- 관련 `backend/tests/unit/`, `backend/tests/scenarios/`, `backend/tests/evaluation/`

## API 영향

없음. `/api/v1` request/response 필드는 변경하지 않는다.

## DB·마이그레이션 영향

없음. 기존 proposal status와 persistence 필드를 그대로 사용한다.

## 안전·개인정보·보안 영향

Safety envelope와 최종 validator를 유지한다. LLM payload는 줄어들며 직접 식별자·원시 건강·웨어러블
값을 추가하지 않는다. 테스트 fixture는 합성 데이터만 사용한다.

## 선행 관계와 차단 요소

- 1차 baseline commit `3b78731`, tag `evaluation-v1-baseline`
- 개발리드·PM 권한 보유 프로젝트 오너가 2026-09-11 테스트 및 품질 개선 전체를 승인했다.
- 유료 실행은 AWS Secrets Manager 설정이 실제 runtime에 주입되는지 preflight 후 진행한다.

## 테스트 계획

- Ruff format/check, mypy
- 변경 영역 unit/contract/privacy/routing tests
- 필수 golden scenarios와 safety invariant/fallback tests
- 기존 20 case 오프라인 회귀
- 실-provider 5~10 case smoke 후 held-out 비교 실행
- Human blind 평가와 Judge calibration 분리

## 수동 확인

- advisory `NEEDS_INPUT` run에서 Coordinator span과 최종 validator span 확인
- provider failure run에서 Coordinator 미호출과 fallback/terminal 확인
- role별 serialized payload 크기와 금지 필드 확인
- v2 결과가 v1 디렉터리 및 manifest를 수정하지 않는지 확인

## 알려진 제한과 후속 작업

- 작은 실-provider 표본에서는 통계적 우월성을 확정하지 않는다.
- 독립 평가자 원점수를 보존하지 못하면 평가자 간 일치도를 계산할 수 없다.
- P95·token·Human 기준 중 하나라도 미달하면 구조 승격 대신 추가 개선 또는 단순화 결정을 검토한다.
