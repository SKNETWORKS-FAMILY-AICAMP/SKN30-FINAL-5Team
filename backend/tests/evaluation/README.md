# Service quality evaluation harness

배포 전 서비스 품질 평가(`docs/test/service_test_master_prompt.md`)의 PHASE 0~7
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
| `runners/run_multi_agent.py` | 실제 그래프 실행 (아키텍처 C) |
| `runners/single_agent.py` | PHASE 6 baseline (아키텍처 A·B). 1회 호출 + 동일 gate |
| `architectures.py` | 비교 대상 3종과, baseline에 물을 수 없는 지표 목록 |
| `comparison.py` | PHASE 6 집계. runner가 아니라 공통 산출물에서만 계산 |
| `comparison_cli.py` | A/B/C 실행 + 비교표 산출 (PHASE 7 payload도 함께 저장) |
| `judge/pairwise.py` | PHASE 7 맞대결 판정, position bias 측정, 블라인딩 검증 |
| `pairwise_cli.py` | collect(그래프) / judge(맞대결) 분리 실행 |
| `performance_failure*.py` | PHASE 9 실-provider 지표 재집계 + 실패 주입 |
| `production_catalog.py` | 배포 카탈로그 번들 → pool record (D-2 재확인용) |
| `fallback_reproduction*.py` | D-2 재현 확인. LLM 호출 0건 |
| `evaluators/` | safety · constraint · structure · failure |
| `harness.py` | 테스트 공용 동기 진입점 |
| `report_cli.py` | `results/` 산출물 재생성 |

## 실행

```bash
# 테스트 (비용 0)
uv run pytest backend/tests/evaluation -q

# 결과 산출물 재생성 (비용 0)
uv run python -m backend.tests.evaluation.report_cli

# PHASE 6 A/B/C 비교 — 호출량 예측만, 비용 0
uv run python -m backend.tests.evaluation.comparison_cli --dry-run

# PHASE 6 배관 점검 — 세 아키텍처 전부 스크립트 모델로, 비용 0
uv run python -m backend.tests.evaluation.comparison_cli --offline

# PHASE 6 실행 (유료). 절차는 docs/test/PAID_EVALUATION.md
uv run python -m backend.tests.evaluation.comparison_cli --confirm-spend --repeats 2

# PHASE 7 맞대결 (유료). 재채점은 --judge-only로 judge 호출만
uv run python -m backend.tests.evaluation.pairwise_cli --offline
uv run python -m backend.tests.evaluation.pairwise_cli --confirm-spend

# D-2 재현 확인 (비용 0, LLM 호출 없음)
uv run python -m backend.tests.evaluation.fallback_reproduction_cli

# PHASE 9 성능 재집계 + 실패 평가 (비용 0, 저장된 실-provider 결과 재사용)
uv run python -m backend.tests.evaluation.performance_failure_cli
```

`--offline` 실행에서 A·B·C가 **같은 계획**을 내는지 확인하는 것이 배관 점검이다.
같은 스크립트 응답을 세 경로에 넣었는데 결과가 다르면, 이후 유료 실행에서 나오는
차이는 아키텍처가 아니라 harness를 측정한 것이 된다.

## 재현성

- 시간: `FIXED_TIME = 2026-08-25T09:00:00Z` (기존 `v3_evaluation_fixtures`와 동일)
- 운동 UUID: `uuid5` 고정 namespace
- provider: 스크립트, 무작위성 없음
- envelope/pool: canonical SHA-256 자기 검증

동일 입력이면 `plan_hash`까지 동일하다(`test_repeated_runs_of_one_case_agree`).

## PHASE 6 공정성

baseline을 약하게 만들면 실험이 무의미해진다. `test_comparison.py`가 다음을
코드로 고정한다.

- baseline 지시문은 배포 중인 `ROLE_PROMPTS`에서 조립한다. 제거한 문장은
  `_DROPPED_CLAUSES`에 사유와 함께 남기고, 테스트가 그 문장이 실제로 배포
  프롬프트에 있었는지와 계획 규칙이 함께 사라지지 않았는지를 검증한다.
- Output Schema는 `PlanSpec`에서 multi-agent 전용 2개 필드만 뺀 것이다.
  이 집합이 커지면 테스트가 깨진다.
- A는 B가 보는 pool의 **진부분집합**만 본다.
- 세 아키텍처 모두 동일한 compiler·integrity validator·fallback을 통과한다.
- baseline에 물을 수 없는 지표(`agent_role_consistency`, `state_consistency`)는
  1.0이 아니라 **n/a**로 보고한다. 없는 질문에 만점을 주면 무승부가 조작된다.

## PHASE 7 편향 탐지

맞대결 승률은 **탐지기가 작동한다는 증명이 먼저 있어야** 의미가 있다.
`AlwaysFirstPairwiseJudge`(항상 첫 번째를 고르는 모의 심사자)를 넣었을 때
position bias 1.0 / agreement 0.0으로 잡히는지 테스트가 검증한다. 이것이 없으면
bias rate 0.0이 "편향 없음"인지 "탐지기가 안 켜짐"인지 구분되지 않는다.

같은 이유로: 승리는 **두 순서가 같은 계획을 지목했을 때만** 집계하고, 같은
슬롯을 지목한 경우는 bias로만 센다. 계획이 없는 아키텍처가 낀 pair는 판정
제외이며 무승부가 아니다.

## 이 harness가 하지 않는 것

- LLM 실호출 (PHASE 5~7, API Key·예산 승인 필요)
- 새 latency 실호출. PHASE 9는 저장된 실-provider 14건을 재집계하고 scripted provider는
  실패 안전성에만 사용한다.
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
