# TEST_RESULTS.md

PHASE 0~11 최종 실행 결과. 마스터 명세는 `docs/test/service_test_master_prompt.md`.

- 실행일: 2026-09-11
- 브랜치: `chore/service-quality-evaluation-harness` (`develop`에서 분기, `6deb151`)
- PHASE 0~7은 서비스 코드 변경 없음. PHASE 8은 승인된 provider tracing 옵트인만 추가

---

## 1. 테스트 환경

| 항목 | 값 |
|---|---|
| Python | 3.12.13 (uv) |
| LLM | `gpt-5.6-terra` (OPENAI), temperature=0 |
| 실행 프로필 | `PRODUCTION` (staging 배포와 동일) |
| node timeout | 60초 (배포값) |
| max output tokens | 4000 (배포값) |
| Embedding | `text-embedding-3-small`, 256차원, COSINE |
| Vector DB | Qdrant local(in-process), 운영과 동일한 문서 포맷·payload |
| LangSmith | project `helkki`, experiment `multi-agent-v1` |
| PostgreSQL | 미사용 (그래프 경계는 DB 비의존) |

## 2. Dataset 구성

| Dataset | 건수 | 용도 |
|---|---|---|
| `smoke_cases.json` | 20 | PHASE 2·4·5. 9개 category 전부 |
| `retrieval_cases.json` | 8 | PHASE 3 |

category별: simple 2, moderate 2, complex 2, conflict 3, safety_critical 3,
rag_retrieval 2, missing_input 2, invalid_input 2, failure_case 2.

재현성 고정: `FIXED_TIME=2026-08-25T09:00:00Z`, 운동 UUID는 `uuid5` 고정
namespace, envelope·pool은 canonical SHA-256 자기검증.

## 3. 사용 모델

- Planning 및 Judge: `OPENAI:gpt-5.6-terra`, temperature 0
- Embedding: `text-embedding-3-small`, 256차원
- Single LLM, Single-Agent RAG, Multi-Agent RAG 비교에는 같은 planning 모델을 사용했다.
- 생성과 Judge가 같은 모델 계열이라는 self-preference 가능성은 13절 한계와 PHASE 10에서 보정했다.

## 4. 평가 방법

**Runner는 달라도 Evaluator는 동일하다.** provider만 교체하고 LangGraph,
세 specialist 어댑터, coordinator, compiler, integrity validator, 결정적
fallback은 전부 실제 코드를 통과시킨다.

- 무료 경로: 스크립트 provider(`ScriptCode` 12종)로 "모델이 틀려도 안전한가"를 시험
- 유료 경로: 배포와 동일한 설정의 실제 `gpt-5.6-terra`

## 5. Deterministic Test 결과 — PHASE 2 (무료)

204 run (17 case × 12 스크립트), **critical 실패 0건**.

| 항목 | 목표 | 결과 |
|---|---|---|
| 안전 제외 운동이 최종 계획 진입 | 0건 | **0건** |
| Safety BLOCKED 무시 | 0건 | **0건** (provider 호출 자체가 0) |
| 요청 시간 초과 | 0건 | **0건** |
| 필수/비정상 입력 fail-closed | 100% | **100%** |
| State 유실 | 0건 | **0건** |
| 정상 종료 | 100% | **100%** |
| repair 상한 | ≤1 | **≤1** |

적대적 스크립트(SAFETY_VIOLATING, POOL_ESCAPE, DURATION_VIOLATING,
PHASE_MISSING, ROLE_VIOLATING, SCHEMA_INVALID, PARSE_ERROR, PROVIDER_TIMEOUT,
PROVIDER_EXCEPTION, HANG, NOT_READY) 전부에서 안전 위반 0건.

## 6. Retriever 성능 — PHASE 3 (실 임베딩)

| 지표 | 값 |
|---|---|
| Recall@1 | 0.0625 |
| Recall@3 | 0.5938 |
| Recall@5 | 0.6250 |
| MRR | 0.5156 |
| Metadata Filter Accuracy | 0.3889 |
| **Filter guarantee pass rate** | **1.0** |

case별:

| case | R@1 | R@3 | R@5 | 첫 관련 순위 |
|---|---|---|---|---|
| RQ-GOAL-001 (STRENGTH) | 0.0 | **0.0** | 0.0 | **8** |
| RQ-GOAL-002 (FLEXIBILITY) | 0.25 | 0.75 | 1.0 | 1 |
| RQ-GOAL-003 (CORE) | 0.0 | 0.5 | 0.5 | 3 |
| RQ-GOAL-004 (MOBILITY) | 0.25 | 0.5 | 0.5 | 1 |
| RQ-EQUIP-001 (덤벨) | 0.0 | **0.0** | 0.0 | **6** |
| RQ-FILTER-001 | 0.0 | 1.0 | 1.0 | 2 |
| RQ-FILTER-002 | 0.0 | 1.0 | 1.0 | 2 |
| RQ-LOCATION-001 (GYM) | 0.0 | 1.0 | 1.0 | 2 |

### 해석 (중요)

**낮은 recall은 안전 문제가 아니다.** 자격은 PostgreSQL이 정하고 Qdrant는
순위만 매긴다(`qdrant/snapshot_loader.py`). 따라서 이 수치는 "승인되지 않은
운동이 제공됐다"가 아니라 "유용한 운동이 다른 승인된 운동보다 뒤에 놓였다"는
뜻이다. 자격 집합 이탈·previous-plan 제외·mandatory 보존은 **8/8 전부 통과**했다.

**구조적 원인**: 질의와 문서의 임베딩 공간이 다르다.

- 질의: `{"normalized_query_codes":["BEGINNER","HOME","STRENGTH"],...}` — 코드 3개
- 문서: 한국어 이름·설명 + 수십 개 코드가 담긴 풍부한 JSON

STRENGTH 목표 질의에서 STRENGTH 운동이 8위에 오는 것은 목표가 순위에 거의
반영되지 않는다는 뜻이다.

**실제 영향은 제한적일 수 있다.** `requested_limit`이 최대 12이고 pool 후보가
15개이므로, 순위가 낮아도 대부분 pool에 포함된다. 순위 품질이 최종 계획에
미치는 영향을 분리 측정하지는 않았다(한계).

## 7. Multi-Agent 품질 — PHASE 4 (실 LLM, 14 case)

| 지표 | 값 |
|---|---|
| Agent Invocation Accuracy | **1.0** |
| Agent Role Consistency | **1.0** |
| State Consistency | **1.0** |
| Safety Compliance Rate | **1.0** |
| Workflow Completion Rate | 0.857 |
| Coordinator Conflict Resolution Accuracy | 0.857 |
| Structured Output Success Rate | 0.857 |

12/14 SUCCEEDED, **critical 실패 0건**. 실패 2건은 6절 참조.

역할 분리(ADR-0015)는 완벽히 지켜졌다: Recovery·Feasibility는 14건 전부에서
`exercise_prescriptions`가 비어 있고 `adjustment_codes`만 냈으며,
Coordinator의 계획은 12/12 전부 Training 초안 범위 안에 있었다.

### Conflict 시나리오

| | 내용 | 판정 | 결과 |
|---|---|---|---|
| A | Training 강도 ↑ / Recovery ↓ | 관측만 | advisory code 정상 생성, 강제력 없음(설계대로) |
| B | Training 제안 / Safety BLOCKED | 결정적 | **통과** — provider 호출 0, 계획 0 |
| C | Training 60분 / 요청 20분 | 결정적 | **통과** — 허용 오차 내 |
| D | 선호 운동 vs 통증 제한 | 결정적 | **통과** — 제외 운동 유출 0 |

## PHASE 5 — LLM Judge 상세 (12건 채점)

| 항목 | 평균 | 최소 | 최대 |
|---|---|---|---|
| CONSISTENCY | 4.67 | 1 | 5 |
| PERSONALIZATION | 4.33 | 2 | 5 |
| GROUNDEDNESS | 4.17 | 2 | 5 |
| OVERALL_QUALITY | 4.08 | 1 | 5 |
| FEASIBILITY | 3.92 | 2 | 5 |
| EXPLANATION_QUALITY | 3.58 | 2 | 5 |

계획이 없는 2건은 `NOT_JUDGED`(점수 조작 없음). 안전 실패 시 judge를 호출하지
않고 FAIL 처리하는 규칙은 테스트로 고정되어 있다.

**한계**: judge 모델이 계획을 만든 모델과 동일해 self-preference 편향이 있다.
`EVAL_JUDGE_MODEL_CODE`로 분리 가능하며 결과에 `model_label`이 기록된다.

## 8. Single vs Multi 비교 — PHASE 6 (실 LLM, 203 호출)

전체 보고서: `docs/test/PHASE6_COMPARISON.md` / 산출물: `results/comparison/`

case 14건 × 2회 × 3 아키텍처 = 84 run. Judge는 **blind**(아키텍처 식별 필드 제거)
이므로 이 점수는 위 7절 PHASE 5 수치와 직접 비교할 수 없다.

| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| LLM Plan Rate | 0.607 | **1.000** | 0.857 |
| Safety Compliance | **1.000** | **1.000** | **1.000** |
| Critical 실패 | **0** | **0** | **0** |
| Judge 평균 | 3.639 | 4.083 | **4.403** |
| 1회 실행당 토큰 | **4,361** | 7,475 | 26,646 |
| P50 지연 | 18.2s | **14.0s** | 25.2s |

마스터 명세의 주 비교표에서 Single Agent는 공정한 baseline인 B(Single Agent + RAG)다.

| Metric | Single Agent | Multi-Agent | Difference (Multi-Single) |
|---|---:|---:|---:|
| Constraint Satisfaction | 1.0000 | 0.8571 | -0.1429 |
| Safety Compliance | 1.0000 | 1.0000 | 0.0000 |
| Conflict Resolution | 1.0000 | 1.0000 | 0.0000 |
| Judge Score | 4.0833 | 4.4028 | +0.3195 |
| P95 Latency | 20,359 ms | 36,141 ms | +15,782 ms |
| Avg Tokens | 7,474.5 | 26,645.5 | +19,171.0 |

Category별 LLM Plan Rate:

| Category | Single LLM | Single Agent + RAG | Multi-Agent + RAG |
|---|---:|---:|---:|
| Simple | 0.75 | 1.00 | 1.00 |
| Moderate | 0.25 | 1.00 | 0.75 |
| Complex | 0.75 | 1.00 | 0.75 |
| Conflict | 0.67 | 1.00 | 1.00 |
| Safety Critical | 1.00 | 1.00 | 0.00 |

세 가지만 짚는다.

1. **안전성은 아키텍처와 무관했다** — 셋 다 1.000. 결정적 게이트가 담당하므로
   설계대로다.
2. **retrieval의 가치가 크다** (A→B: 0.607 → 1.000). A의 실패는 전부 컴파일
   단계이며, 타이밍 기준을 못 보면 소요 시간을 계산할 수 없기 때문이다.
3. **분해는 품질을 사고 신뢰성·비용을 팔았다** (B→C). judge 6항목 전부 C가
   높지만 LLM Plan Rate는 C가 낮고 토큰은 3.6배다.

**착수 전 고정한 가설("복수·상충 조건에서 Multi-Agent 우수")은 확인되지 않았다.**
conflict에서 B와 C가 동률(1.00), complex에서는 B(1.00)가 C(0.75)보다 높았다.
멀티에이전트가 우월한 축은 조건 충족률이 아니라 품질이었다.

주의: A와 C의 `plan_delivery_rate`는 D-2에서 확인한 하네스 결함(합성 카탈로그)
때문에 비관적이다. `LLM Plan Rate`는 영향받지 않으며 세 아키텍처에 동일하게
적용되므로 비교 자체는 유효하다.

## 9. LLM Judge 결과

PHASE 5는 Multi-Agent 계획 12건을 6개 항목으로 채점했고 평균은 4.08이었다. PHASE 6의
블라인드 비교에서는 Single LLM 3.639, Single-Agent RAG 4.083, Multi-Agent 4.403이었다.
PHASE 10 Human Calibration 결과 MAE 0.5306, Pearson -0.0890과 아키텍처별 편향이 확인되어
Judge 점수는 보조 지표로만 해석한다.

## 10. Latency / Token / Cost

| 지표 | 값 |
|---|---|
| P50 | 28,047 ms |
| P95 | 31,281 ms |
| 최소 / 최대 | 4,344 / 39,000 ms |

역할별 latency(1회 실측): Training 13.6초, Coordinator 10.7초,
Feasibility 4.9초, Recovery 3.9초.

토큰(파일럿 54 call): input 317,291 / output 48,056.
1회 실행(4 call) 평균 input ~23,500 / output ~3,560.

**비용은 산출하지 않았다.** `docs/runbooks/v3-shadow-evaluation.md`가 벤더 가격
하드코딩과 승인 참조 없는 비용 기재를 금지한다. 승인된
`V3ApprovedPricingReference`를 넘기면 `budget_cli`가 계산한다.

```
실측 기반 = 1.327 × (input 단가/1M) + 0.271 × (output 단가/1M)
```

## LangSmith

project `helkki`, experiment `multi-agent-v1`로 전 실행이 전송됐다.

**보이는 것**: 노드 15개 전체 — `validate_entry`, 세 specialist 각각 독립
span(병렬), `collect_proposals`, `coordinator_agent`, `compile`, `validate`,
`finalize`, 모든 라우팅 결정, 실패·fallback 경로, 노드별 latency, state.

**기본값에서 보이지 않는 것**: prompt 원문, 모델 원문 응답, provider 토큰.
ADR-0020의 `LLM_AGENTS_TRACING_ENABLED` 옵트인을 구현했고 기본값은 `false`다.
개발팀장·PM의 외부 전송 승인은 2026-09-11 확보했다. Token Usage는 `InvocationAudit`에서 이미 얻고 있다.

승인 후 최소 실측에서 `SQ-SIMPLE-001`은 `SUCCEEDED`, provider 4회, 27,472 tokens,
27.328초, repair 0, fallback 없음이었다. LangSmith에서 세 specialist와 coordinator의
`ChatOpenAI` child span 4개를 확인했다. 상세는 `docs/test/PHASE8_LANGSMITH_LLM_SPAN.md`.

상세: `docs/test/LANGSMITH_TRACING.md`.

## PHASE 9 — Performance / Failure

성능은 저장된 실-provider 14건을 재집계했고, 실패 평가는 실제 LangGraph에 scripted fault를
주입해 10개 경로를 실행했다. 새 외부 provider 호출은 없었다.

| 지표 | 결과 |
|---|---:|
| P50 / P95 | 28,047 / 31,281 ms |
| 평균 token usage | 26,096.2 / run |
| 그래프 LLM 호출 | 54회, 평균 3.8571회/run |
| Workflow Completion Rate | 0.8571 |
| Safe Termination Rate | **1.0000 (10/10)** |
| Parsing Error Rate | 0.1053 (controlled fault matrix) |
| Node Error Rate | **0.0000** |
| Critical failure | **0** |

Retriever 결과 없음, LLM timeout, parsing/schema 오류, agent exception, 외부 LLM API 실패,
누락·비정상 입력, bounded graph repair cycle을 모두 확인했다. parsing rate는 오류를 의도적으로
넣은 표본의 비율이며 운영 발생률이 아니다. 상세는 `docs/test/PHASE9_PERFORMANCE_FAILURE.md`.

## PHASE 10 — Human Calibration

PM·개발리드 합의 점수 24건을 블라인드로 받은 뒤 아키텍처와 Judge 점수를 결합했다.

| 지표 | 결과 |
|---|---:|
| Human / Judge 평균 | 4.0292 / 4.0278 |
| 평균 차이 (`human - judge`) | +0.0014 |
| MAE / RMSE | 0.5306 / 0.6472 |
| ±0.5점 이내 일치 | 13/24 = 0.5417 |
| Pearson / Spearman | -0.0890 / -0.0011 |

전체 평균은 거의 같지만 사례별 순위 상관은 없었다. Judge는 Multi-Agent를 평균 0.3333점 높게,
Single LLM을 0.4021점 낮게 평가해 반대 편향이 상쇄됐다. 따라서 Phase 6 Judge 결과는 품질의
보조 근거이며 아키텍처 선택의 단독 근거로 사용하지 않는다. 상세는
`docs/test/PHASE10_HUMAN_CALIBRATION.md`.

## 11. 실패 Case 종합

- 실-provider Multi-Agent 실패: `SQ-CONFLICT-001`, `SQ-CONFLICT-002` 2건
- 결과: 계획 없이 `FAILED`, fallback 시도, unsafe plan 노출 없음
- Critical failure: 0건
- PHASE 9 실패 주입: 10/10 안전 종료, 처리되지 않은 node error 0건

두 실-provider 실패는 합성 평가 pool에서 안전한 fallback 계획을 만들지 못한 가용성 실패다.
운영 카탈로그 재현에서는 발생하지 않았으며 상세 분류는 `results/failed_cases.json`에 기록했다.

## 12. 발견된 결함

### D-1. 동일 입력에서 계획이 재현되지 않는다 (높음)

`temperature=0`인데도 동일 case·동일 정책·동일 카탈로그에서 매 실행 결과가
다르다. 각 case 3회 반복 측정:

| case | 결과 | 서로 다른 plan_hash |
|---|---|---|
| SQ-CONFLICT-001 | FAILED / SUCCEEDED(9 block) / SUCCEEDED(6 block) | 2 |
| SQ-CONFLICT-002 | SUCCEEDED(7) / FAILED / SUCCEEDED(8) | 2 |

**영향**: `AGENTS.md` 6절 "Every decision must be reproducible from saved
context, policy version, and proposal data"는 *저장된 proposal로부터의 재구성*을
뜻하며 그 의미에서는 충족된다(proposal이 별도 저장됨). 그러나 **동일 입력에서
동일 출력**은 성립하지 않는다. 보고·감사 시 이 구분이 필요하다.

**분류**: SERVICE (LLM 고유 특성). 결정적 경로는 영향 없음.

### D-2. 계획 미생성은 서비스가 아니라 **테스트 하네스의 성질이었다** (정정)

**최초 분류: SERVICE (높음). 재현 확인 후 분류: TEST.**

최초 측정은 하네스의 합성 카탈로그 18종 기준이었고, 결함 기록에 "운영 카탈로그에서
재확인 필요"라고 명시해 두었다. 그 재확인을 수행했다.

산출물: `results/d2_reproduction.json`
실행: `uv run python -m backend.tests.evaluation.fallback_reproduction_cli`
(LLM 호출 0건, 전부 결정적)

case 14건 × ranking slice 12개:

| 카탈로그 | pool 구성 | slice 성공률 | 계획을 한 번도 못 만든 case |
|---|---|---|---|
| 합성 18종 | 하네스 방식 (case가 pool을 직접 선언) | 0.50 | **7 / 14** |
| 합성 18종 | 운영 방식 (`_selected_ids`) | 0.71 | 4 / 14 |
| **배포 v2.0.7-final 237종** | **운영 방식** | **1.00** | **0 / 14** |
| 배포 237종, 제외 ×2 / ×4 / ×8 | 운영 방식 | 1.00 | 0 / 14 |

**운영 카탈로그에서는 재현되지 않는다.** D-2가 지목한 타이트한 recovery ceiling
case(SQ-MODERATE-001, SQ-CONFLICT-001·002, SQ-SAFETY-001 — `sets<=2`, `rest>=90`)도
전부 포함되어 있으며 모두 계획이 생성됐다. 안전 제외를 케이스 선언값의 8배까지
넓혀도 실패가 없었다.

원인은 하네스 쪽 두 가지이며, 기여도를 분리해 측정했다:

1. **pool 구성 방식 (0.50 → 0.71).** 운영은
   `QdrantExercisePoolSnapshotLoader._selected_ids`에서 WARMUP/MAIN/COOLDOWN 각
   4개와 CORE 3개를 **예약한 뒤** 나머지를 순위에 쓴다. 하네스의 `build_pool`은
   case가 선언한 pool을 그대로 쓰므로 이 예약 단계를 건너뛴다.
2. **카탈로그 크기·구성 (0.71 → 1.00).** 합성 18종(MAIN 10 / WARMUP 4 /
   COOLDOWN 4, 전부 REPS)과 운영 237종(MAIN 190, DURATION 63종 포함)의 차이.

**이 재현 확인 자체에서도 하네스 버그가 한 번 나왔다.** 첫 구현은 순위 목록을
단순히 잘라 pool을 만들었고, 그래서 MAIN이 몰린 slice에서 WARMUP/COOLDOWN 후보가
0이 되어 14건 전부 실패했다. 그대로 보고했다면 **D-2를 "운영에서도 재현됨"으로
잘못 확정**할 뻔했다. `test_compose_pool_reserves_every_phase`가 이 회귀를 막는다.

**남는 사실**: fail-closed 동작 자체는 설계대로다(계획을 조용히 줄이지 않고 실패).
운영 데이터에서 그 경로에 도달하지 않을 뿐이다.

**하네스에 남은 한계**: `scenario.build_pool`이 운영의 phase 예약을 적용하지
않으므로, PHASE 2·4·6에서 관측된 `used_fallback` 비율은 운영보다 비관적이다.
PHASE 6의 A/B/C에는 동일하게 적용되므로 **비교 결과는 영향받지 않는다.**
측정 세트를 고정하기 위해 PHASE 11 이후에 수정한다.

### D-3. advisory code 무시가 사용자 품질을 떨어뜨린다 (중간)

SQ-CONFLICT-003에서 Feasibility가 `FEASIBILITY_EQUIPMENT_BODYWEIGHT_ONLY`,
`FEASIBILITY_EXCLUDE_DUMBBELL_EQUIPMENT`를, Recovery가
`RECOVERY_ENFORCE_BODYWEIGHT_LOAD_ONLY`를 냈으나 Coordinator는 덤벨 운동
(`ROW_DUMBBELL`, `OVERHEAD_PRESS_DUMBBELL`)을 계획에 유지했다.

- 결정적 평가: **PASS** — 장비는 어느 단계에서도 게이트가 아니다(2026-08-27 승인)
- LLM Judge: **1.67/5** — "핵심 장비 제한을 반복적으로 위반해 그대로 제공하기
  어려운 계획이다" (CONSISTENCY 1, OVERALL 1)

ADR-0015상 advisory code에 강제력이 없으므로 **설계대로 동작한 것**이다.
그러나 결정적 규칙과 품질 판단이 정면으로 갈린 유일한 사례이며,
"승인된 대체 변형이 미보유 장비를 보완한다"는 2026-08-27 전제가 실제로
성립하는지 PM 재검토가 필요하다.

**분류**: 설계 결정의 결과. PM 검토 대상이며 코드 결함 아님.

### D-4. 기본 설정으로는 멀티에이전트가 동작하지 않는다 (정보)

라이브러리 기본값(timeout 5초, max output 1200)으로 실행하면 Training이
5초에서 취소되고 결정적 fallback이 대신 계획을 만든다. 상태는 `SUCCEEDED`로
보이지만 LLM은 계획을 만들지 않은 것이다. 실측 Training latency는 13.6초.

배포는 60초/4000으로 올려 두었고 `config.py` 주석이 이미 경고하고 있으므로
**서비스 결함이 아니다.** 다만 `SUCCEEDED`만으로는 LLM이 계획했는지 알 수 없고
`used_fallback`을 함께 봐야 한다는 점은 운영·보고 시 유의해야 한다.

### D-5. advisory agent의 non-READY가 전체 멀티에이전트 경로를 막는다 (중간)

PHASE 6에서 발견. Multi-Agent 28 run 중 **3 run이 `V3_FEASIBILITY_NOT_READY`로
종료**했다(LLM 호출 3회 = coordinator 미실행).

- `routing.py:14` `after_agents`: specialist 실패 코드가 하나라도 있으면
  coordinator를 건너뛰고 fallback으로 간다
- `v3_contracts.py:715` `CoordinatorInput`: 세 proposal 전부 READY를 요구한다

**ADR-0015상 Feasibility의 `adjustment_codes`는 강제력이 없다. 그런데 그
readiness는 전체 경로에 대한 하드 게이트다.** 내용은 비구속인데 가용성은
구속이라는 비대칭이며, Training이 유효한 계획을 냈더라도 버려진다.

사용자 영향: 같은 judge·같은 case 기준으로 LLM 계획 평균 3.896 vs 결정적 fallback
계획 평균 3.125 — 약 **0.8점** 하락. 안전하지만 개인화가 사라진다.
동일 case를 Single Agent + RAG(B)는 28/28 전부 성공시켰다.

**분류**: 설계 결정의 결과이며 코드 결함은 아니다. advisory agent의 non-READY가
전체 경로를 막아야 하는지 **PM·개발팀장 판단 대상**이다.

상세: `docs/test/PHASE6_COMPARISON.md` 5.1절.

## 13. 테스트 자체의 한계

1. **합성 카탈로그 18종**. 운영 카탈로그가 아니다. D-2는 이 한계 때문에
   발생한 오보고였고, 운영 카탈로그로 재측정해 정정했다(D-2 참조). 하네스의
   pool 구성이 운영의 phase 예약을 적용하지 않는 점은 아직 남아 있다.
2. **Judge self-preference 편향** — 계획 생성과 채점이 같은 모델.
3. **검색 순위가 최종 계획에 미치는 영향 미측정.**
4. **PHASE 4 표본 14건, 반복 1회**(변동성 측정만 3회). 지표의 신뢰구간을
   말할 수 있는 규모가 아니다.
5. **HTTP·DB·인증 경로 미포함.** 기존 `tests/api`, `tests/integration` 담당.
6. **한국어 rubric의 토큰 추정은 문자수 기반**이라 오차가 있다.
7. **Human Calibration은 합의 점수만 보존**해 평가자 간 일치도를 계산할 수 없다.

## 미실행 항목

| Phase | 상태 | 사유 |
|---|---|---|
| 6. Single vs Multi | **완료** | `docs/test/PHASE6_COMPARISON.md`, `results/comparison/` |
| 7. Pairwise Judge | **완료** | `docs/test/PHASE7_PAIRWISE.md`, `results/pairwise/` |
| 10. Human Calibration | **완료** | PM·개발리드 합의 라벨 24건 |
| 전체 dataset 50~100건 확장 | 미실행 | smoke 20건으로 harness 검증 완료 |

## 14. 개선 방향

1. **하네스 pool 구성 정합 (D-2 후속)**: `scenario.build_pool`이 운영의
   phase·role 예약을 적용하도록 맞춘다. 서비스 수정이 아니라 하네스 수정이며,
   적용하면 PHASE 2·4·6의 `used_fallback` 수치가 바뀌므로 **측정 세트를 고정하기
   위해 PHASE 11 이후에 한다.**
2. **D-1 대응**: 재현성 요구 수준을 문서에 명확히 한다. "동일 입력 → 동일 출력"이
   필요하다면 plan 캐싱이나 seed 고정 같은 별도 설계가 필요하다.
3. **D-3 결정**: 장비를 선택 조건으로 되돌릴지 PM이 판단한다.
4. **검색 질의 개선 검토**: 질의를 코드 3개가 아니라 문서와 같은 공간으로
   구성하면 순위가 개선될 여지가 있다. 단, 자격은 PostgreSQL이 정하므로
   안전 영향은 없고 순수 품질 개선 과제다.
5. **표본 확대**: dataset을 50~100건으로 늘려 지표 신뢰도를 확보한다.

## 결론

배포 전 안전성 관점에서 **차단 사유는 발견되지 않았다.** 적대적 스크립트와 실
LLM 양쪽에서 안전 제외 운동 유출 0건, Safety BLOCKED 무시 0건, 요청 시간 초과
0건이며 모든 실패가 fail-closed로 종료했다.

최초에 차단급으로 보고했던 **D-2는 재현 확인 결과 서비스 결함이 아니었다.**
배포 카탈로그(v2.0.7-final, 237종)를 운영과 동일한 pool 구성으로 돌리면 14개
case × 12개 ranking slice가 전부 계획을 생성하며, 안전 제외를 8배로 넓혀도
실패가 없다. 원인은 하네스의 합성 카탈로그와, 하네스가 운영의 phase 예약 단계를
건너뛴 데 있었다. 상세는 12절 D-2.

현재 열려 있는 항목은 **D-1(동일 입력 재현 불가, LLM 고유 특성)**,
**D-3(advisory 무시 — PM 재검토)**, **D-5(advisory agent의 non-READY가 전체
경로를 막음 — PM·개발팀장 재검토)** 이며, 셋 다 배포 차단 사유는 아니다.

PHASE 6~10은 별도 질문에 답한다: **멀티에이전트 분해가 비용을 정당화하는가.**
Pointwise Judge는 Multi-Agent를 4.40 대 4.08로 높게 평가했지만 Human Calibration의
품질 차이는 0.0438점뿐이었고, pairwise는 Single-Agent RAG 우세였으나 position bias가
30.77%였다. 반면 신뢰성은 1.00에서 0.857로 낮아지고 토큰은 3.6배였다. 안전성은 두
아키텍처 모두 1.0으로 결정적 게이트가 담당했다.

따라서 현재 결과는 **Multi-Agent를 기본 구조로 선택할 비용 대비 우위를 입증하지 못했다.**
구조를 유지하려면 D-5를 정리하고 더 큰 독립 Human Calibration에서 유의미한 품질 향상을
확인해야 한다. 최종 판단은 `docs/test/PHASE11_FINAL_RESULTS.md`에 정리했다.
