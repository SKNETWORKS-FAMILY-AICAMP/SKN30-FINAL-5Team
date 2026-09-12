# TEST_RESULTS.md — 배포 전 서비스 품질 평가 최종 보고서

PHASE 0~11 최종 실행 결과. 마스터 명세는 `docs/test/service_test_master_prompt.md`.

- 실행일: 2026-09-11
- 최종 갱신일: 2026-09-12
- 브랜치: `fix/v3-round2-quality-improvement` (`develop`의 `6deb151`에서 분기)
- PHASE 0~7은 서비스 코드 변경 없음. PHASE 8은 승인된 provider tracing 옵트인만 추가

> 이 문서는 마스터 명세가 지정한 공식 최종 산출물이다. 1차(튜닝 데이터셋) 결과를 보존하면서
> 개선 후 2차 held-out 최종 판정을 함께 반영한다. 상세 추적 근거는
> `docs/test/ROUND2_HELDOUT_RESULTS.md`에 있다.
> **Round 2는 2026-09-12 종료했다.** 이후 숫자를 기존 사전 등록 판정에 합산하지 않는다.

### 최종 판정 요약

최종 판정은 자동 재현 가능한 계약·안전·성능 지표만 사용한다. 기존 계획의 Human mean 항목은
평가자 수와 독립성, 평가자 간 일치도를 확보하지 못해 신뢰 가능한 계량 근거가 아니므로 최종
판정에서 제외했다. LLM Judge 점수는 결과를 확인할 수 있도록 아래에 표시하되, 편향과 fallback
교란 때문에 합격·우열 집계에는 넣지 않는 참고 지표로 사용한다.

| 기계 검증 지표 | 기준 | 최종 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi P95 latency | ≤ 30초 | 43.093초 | **미달** |
| conflict/complex plan rate | ≥ Single RAG | conflict 동률, complex 0.667 대 0.944 | **미달** |

| LLM Judge 참고 지표(1~5, blind) | Single LLM | Single RAG | Multi-Agent | 차이(Multi−RAG) | 해석 |
|---|---:|---:|---:|---:|---|
| 전체 계획(fallback 포함) | 2.9770 | 3.6322 | 3.5172 | -0.1150 | fallback 빈도가 섞여 있음 |
| 모델 저작 계획만 | 4.0556 (n=3) | 3.7267 (n=25) | 3.7222 (n=21) | -0.0045 | RAG와 Multi는 사실상 동률 |

같은 case의 모델 저작 계획을 짝지어 비교한 부호검정도 Multi 9승, Single RAG 9승,
`p=1.0000`이었다. 따라서 Judge 관측값은 **Multi-Agent 우월성을 지지하지 않지만**, 독립적인
합격 기준이나 사람 평가의 대체값으로 해석하지 않는다.

기계 검증 가능한 6개 기준의 최종 결과는 **통과 4, 미달 2**이고 LLM Judge는 **참고 1개**다.
따라서 **Multi-Agent가
Single-Agent + RAG보다 더 유효하다는 가설은 입증되지 않았고**, `Single RAG가 동등 이상`
분기로 간다. Human 항목을 제외해도 두 핵심 성능 기준이 미달이므로 결론은 달라지지 않는다.

2026-09-12에 기존 33건을 보존한 60건 확대 표본으로 추가 확인했다. 이 표본은 원래 판정을
소급 변경하지 않는 보조 분석이며, Multi-Agent 우월성 보류 결론을 뒤집지 않았다. 상세는
`ROUND2_HELDOUT_RESULTS.md` 12절이다.

### 테스트 진행과 개선 결과 요약

| 단계 | 확인한 문제 | 개선 | 확인 결과 |
|---|---|---|---|
| 1차 deterministic·실 LLM | 안전 우회는 없었지만 Multi-Agent 비용·지연이 큼 | 역할별 최소 payload, reasoning-low | v1 대비 token 26.9786% 감소, 안전 1.000 유지 |
| 2차 held-out 33건 | advisory `NEEDS_INPUT`이 전체 경로를 막음 | ADR-0021: Training만 READY 필수, advisory 부재 허용 | workflow 1.000, 실패 시 fallback 유지 |
| 2차 repair 재측정 | repairable 위반도 repair node에 도달하지 못함 | ADR-0022: 안전 대체와 pool 기반 shape repair 분리 | 실제 repair 1회 도달, 재실패는 fallback |
| 60건 확대 | Training이 가능한 입력 9건을 과도하게 거절 | ADR-0023: 안정 reason code와 결정적 feasibility 사전 검사 | 표적 9건 Training 거절 0건, 7건 직접 통과 |
| 잔여 case 분석 | 실제 시간 오차가 compiler 예외로 소실, family 정보가 모델 payload에 없음 | 시간 오차를 integrity repair로 전달, `family_code` 제공 | 022 family 중복 재발 없이 직접 통과 |
| Coordinator 계약 | 불변 hash·reference 등을 모델이 재생성해 domain-invalid 발생 | ADR-0024: orchestration identity를 서버 소유로 전환 | 종료 후 40회 중 직접 통과 35건, 전달·안전 40/40 |

검증된 ADR-0023·0024, family-aware payload와 duration repair 연결은 authoritative `PRODUCTION`
프로필이 사용하는 공통 V3 런타임에 반영했다. 배포 후 저장되는 결정은 aggregate prompt version
`v3-prompts-v7`로 구분되며 기존 저장 레코드와 공개 API·DB schema는 변경하지 않는다.
배포 경로 회귀는 런타임·프로필·overlay 91건과 decision API·golden·safety·replay 107건이
통과했다. PostgreSQL 원자 저장 통합 테스트는 현재 환경에 `TEST_DATABASE_URL`이 없어 1건
skip됐으므로 실제 배포 전 전용 테스트 DB가 있는 CI에서 반드시 실행해야 한다.

전체 흐름은 `Safety Engine → 승인 pool → 세 specialist → Coordinator → compiler → integrity
validator → fallback`으로 시험했다. 모델 출력이 잘못돼도 안전 veto와 최종 validator를 통과하지
못하면 사용자 계획으로 채택되지 않도록 적대적 스크립트, 실제 provider, 반복 표적 실행을 함께
사용했다.

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
| `heldout_cases.json` | 33 | 2차 최종 평가. planning 29건 + provider 미호출 safety blocked 4건 |
| `expanded_heldout_cases.json` | 60 | 보조 확대 평가. planning 54건 + provider 미호출 safety blocked 6건 |

category별: simple 2, moderate 2, complex 2, conflict 3, safety_critical 3,
rag_retrieval 2, missing_input 2, invalid_input 2, failure_case 2.

재현성 고정: `FIXED_TIME=2026-08-25T09:00:00Z`, 운동 UUID는 `uuid5` 고정
namespace, envelope·pool은 canonical SHA-256 자기검증.

2차 held-out은 튜닝 20건과 case ID·내용이 겹치지 않도록 고정했다. 층화는 simple 4,
moderate 8, complex 9, conflict 5, safety_critical 4, failure_case 3이다. 배포 카탈로그
`exercise-catalog-v2.0.7-final` 237종을 운영 eligibility와 snapshot loader 경로로 구성했다.

## 3. 사용 모델

- Planning 및 Judge: `OPENAI:gpt-5.6-terra`, temperature 0
- Embedding: `text-embedding-3-small`, 256차원
- Single LLM, Single-Agent RAG, Multi-Agent RAG 비교에는 같은 planning 모델을 사용했다.
- 생성과 Judge가 같은 모델 계열이라는 self-preference 가능성이 있어 Judge는 최종 판정에서 제외했다.
- 2차 planning과 Judge는 세 아키텍처 모두 `OPENAI:gpt-5.6-terra:reasoning-low`로 고정했다.

## 4. 평가 방법

**Runner는 달라도 Evaluator는 동일하다.** provider만 교체하고 LangGraph,
세 specialist 어댑터, coordinator, compiler, integrity validator, 결정적
fallback은 전부 실제 코드를 통과시킨다.

- 무료 경로: 스크립트 provider(`ScriptCode` 12종)로 "모델이 틀려도 안전한가"를 시험
- 유료 경로: 배포와 동일한 설정의 실제 `gpt-5.6-terra`

2차는 동일 held-out 입력·모델·카탈로그·정책·compiler·integrity validator·fallback을 사용해
A(Single LLM), B(Single-Agent + RAG), C(Multi-Agent + RAG)를 비교했다. 수정 전 256회와
ADR-0022 적용 후 255회의 provider 호출을 각각 독립 산출물로 보존했다. Judge는 아키텍처
식별 필드를 제거한 blind 입력을 받았다. 결과 판정은 `ROUND2_IMPROVEMENT_PLAN.md` 3절에
사전 등록한 기준만 사용했으며, 이후 만든 분해 지표와 calibration은 해석에만 사용했다.

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

2차 held-out에서도 safety golden 33/33, Safety Compliance 1.000, critical/unsafe plan
0건이었다. provider를 호출하지 않는 safety-blocked 4건을 포함하며, Coordinator repair가
실제로 1회 실행된 뒤 같은 위반을 반복한 사례도 최종 validator와 fallback에서 안전하게 종료했다.

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

2차 최종 실행에서 Multi-Agent의 Workflow Completion과 Plan Delivery Rate는 모두 1.000이었다.
다만 LLM이 만든 계획의 비율은 0.7241(21/29), fallback은 8건이었다. 실패 원인은
`V3_TRAINING_NOT_READY` 7건과 repair 후에도 `PLAN_EXERCISE_FAMILY_REPEATED`를 반복한 1건이다.
Training 계약 위반(`V3_TRAINING_PROPOSAL_INVALID`)은 0건이었다.

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

### 2차 held-out 최종 비교 (ADR-0022 적용 후)

마스터 명세의 `Single Agent`는 B(Single-Agent + RAG)다. 아래 표의 Judge·latency·token은
실패 코드가 완전히 기록된 2회차 실행, conflict/complex plan rate는 실행 변동을 줄이기 위한
두 유료 실행 합산값이다.

| Metric | Single Agent + RAG | Multi-Agent + RAG | Difference (Multi-Single) |
|---|---:|---:|---:|
| Constraint Satisfaction | 1.0000 | 1.0000 | 0.0000 |
| Safety Compliance | 1.0000 | 1.0000 | 0.0000 |
| Conflict Plan Rate (합산) | 0.6000 | 0.6000 | 0.0000 |
| Complex Plan Rate (합산) | 0.9444 | 0.6667 | -0.2777 |
| LLM Plan Rate (2회차) | 0.8621 | 0.7241 | -0.1380 |
| Judge Score (전체, blind) | 3.6322 | 3.5172 | -0.1150 |
| Judge Score (저작 계획만) | 3.7267 | 3.7222 | -0.0045 |
| P95 Latency | 40,390 ms | 43,093 ms | +2,703 ms |
| Avg Tokens | 8,721.0 | 19,247.7 | +10,526.7 |

Category별 LLM Plan Rate는 단일 실행의 표본이 3~9건으로 작고 변동이 컸으므로 두 실행을
합산해 병기한다.

| Category | runs/architecture | Single LLM | Single Agent + RAG | Multi-Agent + RAG |
|---|---:|---:|---:|---:|
| Simple | 8 | 0.000 | 0.875 | 0.750 |
| Moderate | 16 | 0.062 | 0.938 | 0.938 |
| Complex | 18 | 0.111 | **0.944** | 0.667 |
| Conflict | 10 | 0.000 | 0.600 | 0.600 |
| Failure case | 6 | 0.167 | **1.000** | 0.667 |
| **전체** | **58** | 0.069 | **0.879** | 0.741 |

이 plan rate 격차를 곧바로 계획 품질 격차로 해석하면 안 된다. Multi-Agent Training은
`READY/NEEDS_INPUT/FAILED` 상태를 표현할 수 있지만 `SingleAgentPlanDraft`에는 상태 필드가 없고
처방이 최소 1개 필수다. 즉 baseline은 구조적으로 거절할 수 없다. 2회차 결과를 `PLAN`,
`DECLINED`, `CONTRACT`, `GATE`, `PROVIDER`로 분해하면 B는 plan 0.8621 / gate rejected
0.1379였고, C는 plan 0.7241 / declined 0.2414 / gate rejected 0.0345였다. 계획을 시도한
run의 게이트 거부율도 C 0.0455 대 B 0.1379였다. 이는 **C가 실제로 낸 계획은 게이트를 더
잘 통과했다**는 보조 근거지만, 거절 7건의 반사실을 알 수 없으므로 사전 등록 판정은 바꾸지 않는다.

### 60건 확대 표본 보조 비교

| Metric | Single Agent + RAG | Multi-Agent + RAG | Difference (Multi-Single) |
|---|---:|---:|---:|
| Constraint Satisfaction | 1.0000 | 0.9815 | -0.0185 |
| Safety Compliance | 1.0000 | 1.0000 | 0.0000 |
| LLM Plan Rate | 0.9630 | 0.7407 | -0.2223 |
| Complex Plan Rate | 1.0000 | 0.6250 | -0.3750 |
| Conflict Plan Rate | 0.8333 | 0.6667 | -0.1666 |
| Judge Score (전체) | 3.7377 | 3.5943 | -0.1434 |
| Judge Score (공통 저작 계획 paired) | 3.8042 | 3.8042 | 0.0000 |
| P95 Latency | 48,953 ms | 51,047 ms | +2,094 ms |
| Avg Tokens | 9,171.7 | 22,043.6 | +12,871.9 |

outcome 분해는 B가 plan 52 / rejected 2, C가 plan 40 / declined 9 / rejected 5였다. C의
계획 시도만 보아도 gate 거부율 5/45(0.1111)로 B의 2/54(0.0370)보다 높아, 29건 실행에서
관찰한 C의 gate 우위는 재현되지 않았다.

## 9. 자동 Judge 진단 결과 — 최종 판정 제외

PHASE 5는 Multi-Agent 계획 12건을 6개 항목으로 채점했고 평균은 4.08이었다. PHASE 6의
블라인드 비교에서는 Single LLM 3.639, Single-Agent RAG 4.083, Multi-Agent 4.403이었다.
기존 PHASE 10 대조에서 MAE 0.5306, Pearson -0.0890과 아키텍처별 편향이 확인됐다. 사람 평가도
독립 다수 평가와 평가자 간 일치도를 갖추지 못했으므로 Human과 Judge 점수 모두 최종 판정에서
제외한다. 아래 수치는 자동 평가기의 거동을 설명하는 진단 기록일 뿐이다.

2차 calibration에서 blind Judge는 모델 저작 계획 3.7449와 결정적 fallback 2.8991을
구분했다(+0.8458). 그러나 fallback을 제외하면 B와 C의 평균은 3.7267 대 3.7222이고,
같은 case의 짝지어 부호검정은 9승 대 9승, p=1.0000이었다. 반면 B 대 A는 p=0.0009,
C 대 A는 p=0.0003으로 retrieval의 가치는 구분했다. 저작 계획의 시간 오차와 FEASIBILITY
점수 상관은 -0.0297이므로 이 점수를 시간 실현가능성이나 아키텍처 우월성 근거로 쓰지 않는다.

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

2차 최종 실행의 Multi-Agent는 P50 27.094초, P95 43.093초, 평균 19,247.7 tokens/run,
평균 3.7931 calls/run이었다. B는 P50 23.922초, P95 40.390초, 평균 8,721.0 tokens/run,
1 call/run이었다. Multi P95는 사전 기준 30초를 13.093초 초과했다. v1 Multi 대비 token
감소율 판정에는 데이터셋이 같은 사전 대응 측정치 26.9786%를 사용했다.

D-7 수정 전에는 실패·거절 호출의 telemetry가 누락되어 Multi-Agent token이 run당 약 12%
과소 집계됐다. 60건 확대 실행은 수정 후 수행되어 실패 호출까지 포함한 평균 22,043.6
tokens/run을 기록했다. 승인된 가격 참조가 없어 금액은 산출하지 않았다.

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

## PHASE 10 — 최종 판정 제외

사람 평가는 독립된 다수 평가자와 평가자 간 일치도를 확보하지 못했다. 동일 자료로 보정한 자동
Judge도 아키텍처별 편향을 보여, 둘 다 신뢰 가능한 합격·우열 근거로 사용할 수 없다. 따라서 이
단계의 점수와 상관계수는 최종 결과에서 제외했으며, 과거 산출물은 실행 이력으로만 보존한다.

## 11. 실패 Case 종합

- 실-provider Multi-Agent 실패: `SQ-CONFLICT-001`, `SQ-CONFLICT-002` 2건
- 결과: 계획 없이 `FAILED`, fallback 시도, unsafe plan 노출 없음
- Critical failure: 0건
- PHASE 9 실패 주입: 10/10 안전 종료, 처리되지 않은 node error 0건

두 실-provider 실패는 합성 평가 pool에서 안전한 fallback 계획을 만들지 못한 가용성 실패다.
운영 카탈로그 재현에서는 발생하지 않았으며 상세 분류는 `results/failed_cases.json`에 기록했다.

2차 held-out 최종 실행에서는 계획 전달 실패와 critical 실패가 모두 0건이었다. Multi-Agent의
LLM 계획 미생성 8건은 결정적 fallback으로 사용자 계획을 전달했다. 7건은 유효한 Training
proposal이 자체적으로 `NEEDS_INPUT`을 선택한 경우이고, 1건은 Coordinator가 family 중복을
repair 후에도 반복해 `REPAIR_ATTEMPT_EXHAUSTED`로 종료한 경우다.

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

### D-6. repair 노드가 배포 구성에서 도달 불가능했다 (높음, 수정 완료)

기존 validator는 모든 repairable 판정에 `approved_safe_alternative_ids`를 요구했지만 프로덕션
경로는 이 값을 채우지 않아 Coordinator repair가 실행될 수 없었다. ADR-0022는 안전 대체가
필수인 `SAFETY_EXCLUDED_EXERCISE_INCLUDED`의 경계를 유지하면서, 승인된 pool로 복구 가능한
shape·dosage 위반만 repair에 도달하게 했다. 재측정에서 repair 1회를 확인했고, 산출물은 같은
validator에서 재검증된 뒤 실패 시 fallback으로 갔다. 공개 API·DB schema 변경은 없다.

### D-7. 실패·거절 호출 telemetry가 버려졌다 (중간, 수정 완료)

specialist 실패 분기가 `AgentOutcome`에 telemetry를 넘기지 않아 과금된 호출이 0 token으로
기록됐다. 모든 실패·거절 분기에서 telemetry를 보존하고 `decline_reason_codes`를 감사·평가
산출물까지 전달하도록 수정했다. 판정 로직이나 안전 경계는 바꾸지 않았지만, 수정 전 Multi-Agent
token 수치가 과소 보고됐으므로 비용 비교에는 재측정이 필요하다.

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
7. **사람 평가와 자동 Judge는 최종 판정에서 제외했다.** 독립 다수 평가·평가자 간 일치도가
   없고 Judge에도 self-preference와 fallback 교란이 있기 때문이다.
8. **원래 사전 등록 held-out category별 n=3~9**라 1건이 0.11~0.33을 움직인다. 보조 확대
   표본은 planning category별 n=4~16으로 늘렸지만 새 27건은 원 판정 후 구성되어 소급 판정에는 쓰지 않는다.
9. **출력 계약이 비대칭**이라 `llm_plan_rate`가 계획 능력과 거절 수단 유무를 함께 측정한다.
10. **종료 후 ADR-0024 반복 표본은 두 case만 대상**이므로 전체 category 성능으로 일반화할 수 없다.
11. **종료 후 반복 산출물의 dataset 메타데이터 오류**가 있다. 당시 하네스가 선택한 dataset명을
    `comparison.json`에 전달하지 않아 기본값 `smoke`로 기록했다. 실제 실행 대상은
    `cases_multi_agent.json`의 018·022이며, 결과 수치에는 영향이 없다. 하네스와 회귀 테스트는 수정했다.

## 미실행 항목

| Phase | 상태 | 사유 |
|---|---|---|
| 6. Single vs Multi | **완료** | `docs/test/PHASE6_COMPARISON.md`, `results/comparison/` |
| 7. Pairwise Judge | **완료** | `docs/test/PHASE7_PAIRWISE.md`, `results/pairwise/` |
| Human/Judge 기반 최종 판정 | **제외** | 독립성·평가자 일치도 부족과 Judge 편향 때문에 진단 기록으로만 보존 |
| 전체 dataset 50~100건 확장 | **완료** | 60건, category별 n=4~16 |
| Training 거절 사유 재측정 | **완료** | 476회 확대 실행에 포함; 9건/10개 reason code 수집 |

## 14. 개선 방향

1. **architecture-neutral 출력 계약 결정**: baseline과 Multi-Agent가 같은 방식으로 거절을
   표현하게 할지 오너가 결정한다. 결정 전에는 plan rate에 분해 지표를 항상 병기한다.
2. **지연 개선**: 사전 판정 P95 43.093초와 확대 표본 P95 51.047초를 모두 고려해,
   30초 이하를 재현하기 전에는 승격 후보로 보지 않는다.
3. **Coordinator domain-invalid 감소**: ADR-0024 반복에서 남은 5/40을 원시 건강정보 없이
   분류할 수 있는 허용 목록형 validation stage code로 관측한다.
4. **D-1 대응**: 재현성 요구 수준을 문서에 명확히 한다. "동일 입력 → 동일 출력"이
   필요하다면 plan 캐싱이나 seed 고정 같은 별도 설계가 필요하다.
5. **오너 결정**: `approved_safe_alternative_ids` 산출 주체, 장비 advisory의 강제 여부,
   Recovery/Feasibility 조건부 호출 또는 구조 단순화를 각각 ADR 범위로 검토한다.
6. **검색 질의 개선 검토**: 질의를 코드 3개가 아니라 문서와 같은 공간으로
   구성하면 순위가 개선될 여지가 있다. 단, 자격은 PostgreSQL이 정하므로
   안전 영향은 없고 순수 품질 개선 과제다.

## 결론

배포 전 안전성 관점에서 **차단 사유는 발견되지 않았다.** 1·2차 모두 안전 준수율 1.000,
critical/unsafe plan 0건이고 모든 실패는 결정적 gate와 fallback에서 fail-closed로 종료했다.
ADR-0021·0022와 D-7 수정도 안전 판정 규칙, 공개 API, DB schema를 바꾸지 않았다.

그러나 최종 판정에 사용한 기계 검증 기준 6개 중 **4개 통과, 2개 미달**이므로
**Multi-Agent가 Single-Agent + RAG보다 더 유효하다는 결론은 내리지 않는다.** 특히 Multi P95
43.093초는 30초 기준을 넘었고, 두 실행 합산 complex plan rate는 0.667로 B의 0.944보다 낮다.

동시에 이 결과를 “Multi-Agent가 계획을 더 못 만든다”로 단정해서도 안 된다. 출력 계약 비대칭
때문에 C만 계획 거절을 표현할 수 있었고, 거절을 제외한 결정적 게이트 거부율은 C 0.0345 대
B 0.1379였다. 자동 Judge 수치는 신뢰성 문제로 최종 판정에서 제외했다. **현재 재현 가능한 증거가 지지하는
결론은 안전성과 전달 성공, 그리고 비용·지연 대비 Multi-Agent 우월성 미입증**이다.

따라서 안전한 현 구조를 즉시 폐기할 근거도, 비용이 더 큰 Multi-Agent를 우월 구조로 승격할
근거도 부족하다. 사전 판정 규칙에 따라 **Single RAG 동등 이상 분기**를 채택하고, 지연 개선,
architecture-neutral 계약과 조건부 agent 호출을 후속 ADR 과제로 넘긴다.

60건 보조 확대 실행에서도 안전·전달은 1.000이었지만 C의 P95는 51.047초, complex/conflict
plan rate는 0.6250/0.6667로 B의 1.0000/0.8333보다 낮았다. Training 거절 9건은 모두
duration/volume 부족을 주장했지만 동일 9건 중 B는 8건에서 공통 gate를 통과했다. 확대 결과는
기존 판정을 바꾸지 않으며, Training 자체 거절 조건과 reason-code taxonomy를 후속 설계 과제로
구체화한다.

## Training 거절 계약 후속 구현 (ADR-0023, 2026-09-12)

개선 방향 1을 구현했다. Training `NEEDS_INPUT` 사유는
`TRAINING.DETERMINISTIC_PLAN_FEASIBILITY_UNPROVEN` 단일 코드로 제한한다. 같은 envelope·pool에서
결정적 fallback provider가 후보를 실제 생성하면 Training에 그 사실을 전달하고, 모순되는 거절은
domain-invalid로 처리해 기존 최대 2회 범위 안에서 재시도한다. 후보를 만들지 못한 경우는
불가능 판정이 아니라 `UNPROVEN`으로 남긴다.

이 변경은 안전 veto·compiler·최종 integrity validator를 변경하지 않으며 공개 API/DB 스키마에도
영향이 없다. 구현 직후에는 유료 평가를 실행하지 않았으므로 확대 표본 수치와 최종 판정은
그대로 유지했다.

이후 최소 표적 유료 재측정을 실행했다. 과거 Training 거절 9건과 대조군 3건을 Multi-Agent
단독·Judge 제외로 실행했으며 실제 호출은 49회였다. 과거 거절 9건에서 `NEEDS_INPUT`은 0건,
LLM 계획 직접 통과는 7건이었다. 나머지 2건은 Training 거절이 아니라 compilation 실패 1건과
Coordinator family 중복 repair 소진 1건으로, 모두 결정적 fallback이 계획을 전달했다.
12건 전체 Plan Delivery·Safety·Workflow는 1.000이고 critical 실패는 0건이다.

이 표적 결과는 ADR-0023의 직접 목표를 확인하지만 전체 비교 표본이 아니므로 기존 A/B/C 수치와
최종 판정은 변경하지 않는다. 상세 산출물은 `results/round2/adr23_targeted_paid/`에 있다.

### 표적 실행 잔여 실패 수정

`SQ-HELD-018`의 compilation 실패는 compiler가 측정한 시간 오차를 최종 integrity validator보다
먼저 예외로 종료해 `REQUESTED_DURATION_MISMATCH` repair가 도달 불가능했던 것이 원인이었다.
compiler는 이제 측정 결과를 보존하고, downstream validator가 기존 허용 범위와 bounded repair를
그대로 집행한다. `SQ-HELD-022`는 모델용 pool projection에 catalog `family_code`가 빠져 같은
family의 서로 다른 exercise ID를 구분할 수 없었던 것이 원인이었다. Training과 Coordinator에
해당 필드를 제공하고 prompt에 family 중복 방지 및 repair 방법을 명시했다.

관련 회귀 94건과 ruff·운영 소스 mypy가 통과했다. 안전 veto, 허용 시간 범위, repair 1회 상한,
fallback 및 공개 API/DB schema는 변경하지 않았다. 수정 직후에는 추가 유료 호출을 실행하지
않았고, 아래의 두 건 표적 재실행을 별도로 수행했다.

잔여 두 건만 추가로 유료 재실행했다. Judge 없이 Multi-Agent 2건을 실행해 실제 8회를 호출했다.
`SQ-HELD-022`는 LLM 계획으로 직접 통과해 family 중복이 재발하지 않았다. `SQ-HELD-018`은 기존
compilation 실패는 재발하지 않았지만 Coordinator가 `LLM_AGENT_DOMAIN_INVALID`로 종료돼
deterministic fallback이 계획을 전달했다. 두 건의 Plan Delivery·Safety·Workflow·Constraint
Satisfaction은 모두 1.000이고 critical 실패는 0건이다. 산출물은
`results/round2/residual_two_paid_20260912/`에 있다.

Round 2 종료와 함께 ADR-0024를 적용했다. Coordinator의 schema/envelope/pool identity, 요청 시간,
proposal reference, repair attempt와 hash는 모델 출력이 아니라 검증된 `CoordinatorInput`에서
서버가 결정한다. 모델이 선택하는 action·운동 처방·decision code는 기존 domain/compiler/integrity
경계를 그대로 통과한다. Coordinator 관련 회귀 110건과 별도의 golden·safety veto·재현성·LLM
fallback 회귀 290건, backend ruff와 app mypy가 통과했다. 이 시점의 공식 판정은 바꾸지 않았다.

이후 오너 승인으로 종료 후 축소 재측정을 별도 실행했다. `SQ-HELD-018`, `SQ-HELD-022`를 각각
20회 실행해 실제 159회를 호출했다. LLM 직접 통과는 각각 16/20과 19/20, 전체 35/40이었다.
fallback 5건에도 모든 계획이 전달됐고 안전·workflow·constraint satisfaction은 1.000,
critical 실패는 0건이었다. 결과는 `results/round2/adr24_two_cases_r20/`에 있으며 사전 등록
표본이 아니므로 공식 Round 2 판정을 변경하지 않는다.
