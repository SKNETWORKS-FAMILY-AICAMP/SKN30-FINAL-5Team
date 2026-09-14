# PHASE6_COMPARISON.md

Single LLM(A) / Single Agent + RAG(B) / Multi-Agent + RAG(C) 비교 실험 결과.

- 실행일: 2026-09-11
- 모델: `gpt-5.6-terra`, temperature 0, timeout 60s, max output 4000
  (`infra/deployment/compose.staging.v3production.yaml`와 동일)
- dataset: smoke planning case 14건 × 2회 반복 = 아키텍처당 28 run
- LLM 호출 **203회** (graph 165 + judge 38)
- 산출물: `results/comparison/`
- LangSmith: project `helkki`, experiment `baseline-single-llm-v1` /
  `baseline-single-agent-v1` / `multi-agent-v1`
- **서비스 코드 변경 0줄**

---

## 1. 결론 요약

| | 결과 |
|---|---|
| **안전성** | 세 아키텍처 모두 **1.0**. 안전 제외 운동 유출 0건, critical 실패 0건 |
| **신뢰성** | **B > C > A.** B가 28/28 완벽, C 24/28, A 17/28 |
| **품질(judge)** | **C > B > A.** 4.40 / 4.08 / 3.64 (단, 성공한 run만 채점) |
| **비용** | **A < B << C.** 1회 실행당 토큰 4.4K / 7.5K / **26.6K** |
| **가설** | **확인되지 않았다.** 아래 6절 |

한 줄로: **멀티에이전트 분해는 품질을 사고 신뢰성과 비용을 지불했다.**
안전성은 아키텍처와 무관했다 — 설계상 결정적 게이트가 담당하기 때문이다.

## 2. 공정성 조건

| 항목 | 처리 |
|---|---|
| LLM 모델·temperature·timeout·토큰 상한 | provider 객체를 **한 번만** 만들어 셋이 공유 |
| 사용자 입력·dataset·운동 데이터 | 동일 case 목록, 동일 순서 |
| pool | case당 동일 `ExercisePoolSnapshot` (B와 C는 완전히 동일) |
| 지시문 | baseline 지시문을 배포 중인 `ROLE_PROMPTS` 4개에서 **조립**. 새로 쓰지 않음 |
| Output Schema | `PlanSpec`에서 multi-agent 전용 2개 필드만 제외 |
| 하류 게이트 | 동일한 compiler / integrity validator / deterministic fallback |
| Judge | **blind.** 아키텍처를 식별시키는 `advisory_codes` 필드를 양쪽에서 제거 |

`--offline` 실행에서 동일한 스크립트 응답을 세 경로에 넣으면 **셋 다 같은 계획**이
나오는 것을 확인했다(`test_comparison.py`). 배관이 아니라 아키텍처를 측정하고
있다는 조건이다.

### 2.1 완전히 동일하게 만들지 못한 2가지 (둘 다 C에 유리)

1. **Output Schema.** `PlanSpec`은 canonical 순서의 proposal_reference 3개를
   **구조적으로 요구**한다. baseline은 자기 출력을 TRAINING proposal로 감싸는
   contract adapter를 거쳐야 배포 compiler에 들어간다. adapter는 advice를
   만들어내지 않는다(advisory 2개는 "특화 에이전트 조언 없음" 코드 하나만).
   **출력 계약이 아키텍처 중립이 아니라는 것 자체가 PHASE 6의 발견이다.**
2. **repair 라운드.** C는 1회, baseline은 0회. 이번 실행에서 C의 repair 사용은
   **0회**였으므로 실측 영향은 없다.

### 2.2 A와 B의 차이는 pool 정보량뿐

A는 **출력 스키마를 채우는 데 필수인 4개 필드**만 본다(`exercise_id`,
`stable_code`, `timing_mode_code`, `location_codes`). B는 여기에 retrieval이
제공하는 전부를 더 본다(phase_codes, role_eligibility, FITT 범위, 타이밍 기준,
goal_codes, equipment). 지시문·스키마·하류 게이트는 완전히 동일하다.

따라서 **A→B 차이 = retrieval의 가치**, **B→C 차이 = 멀티에이전트 분해의 가치**다.

## 3. 결과

| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| 실행 수 | 28 | 28 | 28 |
| Constraint Satisfaction | 0.893 | **1.000** | 0.857 |
| **LLM Plan Rate** (fallback 제외) | 0.607 | **1.000** | 0.857 |
| Plan Delivery Rate (fallback 포함) | 0.893 | **1.000** | 0.857 |
| **Safety Compliance** | **1.000** | **1.000** | **1.000** |
| Workflow Success | 0.893 | **1.000** | 0.857 |
| Structured Output Success | 1.000 | 1.000 | 0.893 |
| Critical 실패 | **0** | **0** | **0** |
| Agent Invocation Accuracy | 1.000 | 1.000 | 1.000 |
| Agent Role Consistency | n/a | n/a | 1.000 |
| State Consistency | n/a | n/a | 1.000 |
| Judge 평균 | 3.639 | 4.083 | **4.403** |
| Judge PERSONALIZATION | 4.000 | 4.500 | **4.833** |
| Judge FEASIBILITY | 3.917 | 4.357 | **4.583** |
| Judge OVERALL_QUALITY | 3.667 | 4.429 | **4.583** |
| P50 Latency | 18.2s | **14.0s** | 25.2s |
| P95 Latency | 30.3s | **20.4s** | 36.1s |
| 1회 실행당 LLM 호출 | **1.0** | **1.0** | 3.89 |
| 1회 실행당 토큰 | **4,361** | 7,475 | 26,646 |

`n/a`는 0점이 아니라 **물을 수 없는 질문**이다. advisory specialist가 없는
아키텍처에 "advisory specialist가 계획을 내지 않았는가"를 묻고 1.0을 주면
무승부를 조작하게 된다.

### 3.1 category별 LLM Plan Rate

| category | run | A | B | C |
|---|---|---|---|---|
| simple | 4 | 0.75 | **1.00** | **1.00** |
| moderate | 4 | 0.25 | **1.00** | 0.75 |
| complex | 4 | 0.75 | **1.00** | 0.75 |
| conflict | 6 | 0.67 | **1.00** | **1.00** |
| safety_critical | 2 | **1.00** | **1.00** | 0.00 |
| rag_retrieval | 4 | 0.50 | **1.00** | **1.00** |
| failure_case | 4 | 0.50 | **1.00** | **1.00** |

## 4. A → B: retrieval의 가치는 크다

LLM Plan Rate **0.607 → 1.000**.

A는 28회 중 11회 유효한 계획을 만들지 못했다. 실패는 전부 `V3_COMPILATION_FAILED`
계열 — 컴파일 단계에서 **주장된 duration이 측정된 duration으로 바뀌는** 지점이다.
A는 `default_seconds_per_rep` / `default_work_seconds` / `default_rest_seconds`를
보지 못하므로 계획의 실제 소요 시간을 계산할 수 없다.

동시에 **A도 안전성은 1.000**이었다. pool 밖 운동도, 제외된 운동도 넣지 못했다.
운동 ID 허용목록만 주면 그 경계는 지켜진다는 뜻이다. 지키지 못하는 것은 **시간**이다.

## 5. B → C: 분해는 품질을 사고 신뢰성을 판다

### 5.1 C가 진 지점 — Feasibility가 전체 실행을 막는다

C의 실패 4건 중 **3건이 `V3_FEASIBILITY_NOT_READY`** 다. 호출 수가 3인 것이 증거다:
Feasibility가 non-READY를 반환하면 `after_agents` 라우터가 coordinator를 건너뛰고
바로 fallback으로 간다(`routing.py:14`).

**ADR-0015상 Feasibility의 `adjustment_codes`는 강제력이 없다.** 그런데 그
**readiness는 전체 멀티에이전트 경로에 대한 하드 게이트**다 —
`CoordinatorInput`이 세 proposal 전부 READY를 요구하기 때문이다
(`v3_contracts.py:715`). Training이 완벽한 계획을 만들었어도 버려진다.

**내용은 비구속인데 가용성은 구속이다.** 이 비대칭은 의도된 것으로 보이지 않는다.
자세한 기록은 `TEST_RESULTS.md` D-5.

나머지 1건은 `V3_COMPILATION_FAILED`(coordinator 계획이 duration 창을 벗어남)이다.

### 5.2 C가 이긴 지점 — 품질

judge 6항목 전부 C > B > A. 평균 4.403 vs 4.083 vs 3.639.

다만 **judge 평균은 성공한 run에만 매겨진다**(A 12건, B 14건, C 12건 채점).
계획을 못 만든 run은 채점 대상이 없어 제외되므로, **실패가 많은 아키텍처일수록
품질 평균이 유리해진다.** C의 우위는 상한으로 읽어야 한다.

### 5.3 fallback으로 떨어지면 품질은 얼마나 내려가는가

아키텍처 A 안에서 같은 judge·같은 case로 비교하면:

| 계획 출처 | 채점 수 | 평균 |
|---|---|---|
| LLM 계획 | 8 | **3.896** |
| 결정적 fallback 계획 | 4 | **3.125** |

약 **0.8점**. 즉 Feasibility 게이트가 걸리면 사용자는 4.4점짜리 멀티에이전트
계획 대신 3.1점짜리 결정적 계획을 받는다. 안전하지만 개인화가 사라진다.

### 5.4 비용

C는 B의 **토큰 3.6배**, **호출 3.9배**, **P50 지연 1.8배**다.
prompt가 큰 이유는 세 Agent와 Coordinator가 **각각 승인된 pool 전체**를 받기
때문이며, 이는 pool 밖 운동을 만들지 못하게 하는 설계상 근거이기도 하다.

## 6. 가설 검증

`TEST_PLAN.md` PHASE 6이 착수 전에 고정한 가설:

> 단순 케이스에서는 차이가 작고, **복수·상충 조건에서는 Multi-Agent가
> 조건 충족률·안전성·일관성에서 우수하다.**

**확인되지 않았다.**

| | 가설 | 실측 |
|---|---|---|
| conflict 조건 충족률 | C > B | C = B = 1.00 (A 0.67) |
| complex 조건 충족률 | C > B | **B 1.00 > C 0.75** |
| 안전성 | C > B | **C = B = A = 1.00** |
| 일관성(structured output) | C > B | **B 1.00 > C 0.893** |

멀티에이전트가 우월한 축은 **조건 충족률이 아니라 품질**이었다.
이 결과는 수정하거나 제외하지 않는다(`TEST_PLAN.md` 0절 2항).

## 7. 한계 — 이 수치를 어디까지 믿을 수 있는가

1. **표본이 작다.** 아키텍처당 28 run(14 case × 2회). safety_critical은 2 run뿐이라
   C의 0.00은 "2회 모두 실패"이며 비율로 읽으면 과대 해석이다.
2. **`plan_delivery_rate`는 하네스 때문에 비관적이다.** A와 C의 fallback 실패는
   D-2에서 확인한 **하네스 결함**(합성 카탈로그 + phase 예약 누락) 때문이다.
   운영 카탈로그에서는 fallback이 계획을 만들었을 것이므로 A·C의 delivery는 더
   높아진다. **`llm_plan_rate`는 이 영향을 받지 않으며**, 세 아키텍처에 동일하게
   적용되므로 **비교 자체는 유효하다.**
3. **judge 평균은 성공에 조건부다** (5.2절).
4. **judge self-preference.** 계획 생성과 채점이 같은 모델 계열이다.
   `EVAL_JUDGE_MODEL_CODE`로 분리 가능하나 이번에는 분리하지 않았다.
5. **A는 하한이다.** "Single LLM"을 스키마가 요구하는 최소 정보만 주는 것으로
   정의했다. 더 준다면 A와 B 사이 어딘가에 위치할 것이다.
6. **비결정성**(D-1). 2회 반복으로는 분산을 충분히 측정하지 못한다.

## 8. 다음

- **PHASE 7 (Pairwise Judge)** 선행 조건은 충족됐다. blind payload가 이미 있으므로
  같은 payload 2개를 순서 무작위로 제시하도록 확장하면 된다.
- **D-5(Feasibility readiness 게이트)** 는 PM·개발팀장 판단 대상이다. advisory
  agent의 non-READY가 전체 경로를 막아야 하는지가 질문이다.
- 표본 확대(50~100건)는 측정 세트를 닫은 뒤에 한다.
