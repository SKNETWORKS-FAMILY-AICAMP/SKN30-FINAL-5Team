# TASK-MULTI-AGENT-CANDIDATE-REVIEW-EXPERIMENT

## 목적

현행 운영 그래프를 변경하지 않고 후보 생성·교차 검토·제한 조정 구조가 안전하고 재현 가능한지
평가 하네스에서 검증한다.

## 범위

- 평가 전용 후보·리뷰·선택·조정 계약
- 기존 PlanSpec·compiler·integrity validator 연결
- 정상 흐름과 위조·완화·Safety 우회 회귀 테스트
- 과거 결과용 dataset은 보존하고 장비 비게이트 정책을 반영한 `heldout_cases_v2`와
  `expanded_heldout_cases_v2` 생성
- ADR-0025와 평가 문서

제외 범위는 운영 LangGraph, provider adapter, API, DB, 프론트엔드와 유료 호출이다.

## 인수 조건

1. Training 후보는 정확히 두 개이며 처방 fingerprint가 다르다.
2. Recovery·Feasibility가 각각 모든 후보를 순위화한다.
3. Coordinator는 후보 하나와 실제 review adjustment만 선택한다.
4. 조정은 세트·반복 감소 또는 휴식 증가만 가능하고 완화할 수 없다.
5. 결과 PlanSpec은 기존 compiler와 integrity validator를 통과해야 전달 가능하다.
6. 구조화 계약 및 관련 평가 회귀가 통과한다.

## 위험

- 후보 차이가 형식적이면 Multi-Agent 가치 측정이 왜곡된다.
- 보수적 조정도 요청 시간 창을 벗어날 수 있으므로 최종 validator가 필수다.
- 실험 구조에만 유리한 시나리오를 만들지 않고 Single-Agent+RAG 기준선을 유지해야 한다.

## 무료 구조 검증 결과

2026-09-15 평가 전용 계약과 materialization 경로를 구현했다. 정상 후보 선택은 기존 `PlanSpec`,
compiler와 downstream integrity validator를 통과했다. 중복 후보, 리뷰에 없는 조정 채택, 조정 방향
완화, 같은 필드에 대한 충돌 조정, Safety 제외 운동 선택은 모두 거부됐다.

- Ruff format/check: 통과
- mypy(신규 계약·테스트): 통과
- 표적 테스트: 36 passed
- 전체 `backend/tests/evaluation`: 513 passed, 2 skipped
- 외부 provider 호출: 0

이 결과는 구조와 안전 경계의 실행 가능성을 검증한 것이며 실제 모델의 후보 다양성·리뷰 품질 또는
Single-Agent+RAG 대비 우위를 입증하지 않는다. 다음 증분은 실제 provider adapter, 후보 차이 지표,
Specialist 개입·채택 지표와 blinded paired pilot이다.

## Provider-capable pilot increment (2026-09-15)

The experiment now has a provider adapter and an executable B-vs-D pilot runner. The
four D-path calls are Training candidate generation, parallel Recovery and Feasibility
cross-review, and Coordinator selection. The Coordinator output contains no exercise
prescriptions; the server materializes the selected candidate and review-originated
bounded adjustments before invoking the existing compiler, integrity validator, and
deterministic fallback.

The pilot records selection changes, specialist disagreement, accepted adjustment count,
latency, token usage, fallback use, and the common evaluator findings. The CLI defaults to
a zero-cost forecast, requires `--confirm-spend`, and rejects a run whose five-calls-per-case
forecast exceeds `--max-calls`.

Free verification completed before any paid attempt:

- Ruff format/check: passed
- mypy for the new provider, runner, CLI, and tests: passed
- candidate-review contract and provider tests: 12 passed
- three-case dry run: 15-call ceiling, zero provider calls

The first paid attempt was stopped before provider construction by the environment's
external-data approval gate. No paid call was made by that attempt.

After explicit approval, a three-case paid pilot was run. The initial D schema was rejected
locally by OpenAI native structured-output binding; provider-specific list DTOs replaced the
fixed Pydantic tuples and passed local strict-schema binding before the rerun. In the rerun B
produced 3/3 direct plans. D used fallback in 3/3: one selected recovery candidate showed
specialist disagreement and accepted two bounded adjustments, but the compiled result failed
`PLAN_EXERCISE_VARIETY_EXCEEDED`; the other paths stopped on domain/provider-stage failures.
The result therefore does not establish D superiority. See
`results/candidate-review-pilot/README.md` and `summary-v2.json`.

The next pre-registered correction is to validate both candidates independently through the
common compiler and integrity validator before cross-review. Do not spend on a larger run
until that gate and a sanitized per-stage failure audit are verified offline.
