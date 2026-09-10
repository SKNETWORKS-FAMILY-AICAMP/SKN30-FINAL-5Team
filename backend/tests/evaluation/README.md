# Service quality evaluation harness

배포 전 서비스 품질 평가(`docs/test/service_test_master_prompt.md`)의 PHASE 0~2
구현이다. 계획은 `docs/test/TEST_PLAN.md`, 구조 분석은
`docs/test/TEST_SYSTEM_ANALYSIS.md`를 따른다.

## 핵심 설계

**서비스 코드를 한 줄도 바꾸지 않는다.** provider만 스크립트로 대체하고 나머지는
전부 실제 코드다.

```
EvaluationCase (JSON)
  → scenario.build_scenario()      ConstraintEnvelope + ExercisePoolSnapshot
  → MultiAgentRunner               실제 LangGraph + 실제 어댑터
      ├ ScriptedChatModel          유일한 대체 지점 (비용 0, 완전 재현)
      ├ compile_plan()             실제
      ├ validate_plan_integrity()  실제
      └ DeterministicGraphFallback 실제
  → evaluators/                    runner와 무관한 단일 평가기
  → CaseEvaluation (구조화 findings)
```

묻는 질문은 "모델이 잘하는가"가 아니라 **"모델이 잘못해도 서비스가 안전한가"**다.
그래서 `ScriptCode`가 모델이 틀리는 방식을 하나씩 이름 붙여 주입한다.

## 구성

| 파일 | 역할 |
|---|---|
| `catalog.py` | 고정 UUID 합성 운동 카탈로그 (18종). 모든 값이 `eval-` 접두사 |
| `dataset.py` | case 스키마·로더·개인정보 스캔 |
| `datasets/smoke_cases.json` | 20개 smoke case, 9개 category 전부 |
| `scenario.py` | case → envelope + pool. 입력 거부도 여기서 판정 |
| `planner.py` | 스크립트 모델이 쓰는 결정적 plan 구성기 |
| `runners/fake_chat.py` | 스크립트 provider (`ScriptCode` 12종) |
| `runners/payloads.py` | 역할별 응답 본문 생성 |
| `runners/run_multi_agent.py` | 실제 그래프 실행 |
| `evaluators/` | safety · constraint · structure · failure |
| `harness.py` | 테스트 공용 동기 진입점 |
| `report_cli.py` | `results/` 산출물 재생성 |

## 실행

```bash
# 테스트 (비용 0)
uv run pytest backend/tests/evaluation -q

# 결과 산출물 재생성 (비용 0)
uv run python -m backend.tests.evaluation.report_cli
```

## 재현성

- 시간: `FIXED_TIME = 2026-08-25T09:00:00Z` (기존 `v3_evaluation_fixtures`와 동일)
- 운동 UUID: `uuid5` 고정 namespace
- provider: 스크립트, 무작위성 없음
- envelope/pool: canonical SHA-256 자기 검증

동일 입력이면 `plan_hash`까지 동일하다(`test_repeated_runs_of_one_case_agree`).

## 이 harness가 하지 않는 것

- LLM 실호출 (PHASE 5~7, API Key·예산 승인 필요)
- latency 측정 — 스크립트 provider는 즉시 응답하므로 여기서 낸 percentile은
  harness를 재는 것이지 서비스를 재는 것이 아니다. PHASE 9에서 실제 provider로
  측정한다.
- 검색 품질 (PHASE 3). pool은 case가 직접 지정한다.
- HTTP·DB 경로. 기존 `backend/tests/api/**`, `backend/tests/integration/**` 담당.

## 결과 해석 규칙

`Finding.defect_class`를 반드시 읽는다.

- `SERVICE` — 서비스 결함
- `TEST` — harness나 case가 틀림
- `NOT_A_DEFECT` — 설계상 정상인 관측(INFO)
- `UNDETERMINED` — 사람이 판단해야 함

`EQUIPMENT_UNCONSTRAINED_BY_ENVELOPE`처럼 INFO로 기록되는 관측은 실패가 아니라
**설계 결정을 고정하는 핀**이다. 이 관측이 사라지면 동작이 바뀐 것이므로 검토가
필요하다.
