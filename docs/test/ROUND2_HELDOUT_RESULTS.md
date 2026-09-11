# 2차 held-out 유료 평가 결과

- 실행일: 2026-09-11
- 데이터셋: `heldout_cases` 33건 중 planning 29건 (blocked 4건은 provider 호출 없음)
- 카탈로그: `exercise-catalog-v2.0.7-final` (배포본, 237종)
- 모델: `OPENAI:gpt-5.6-terra:reasoning-low`, 세 architecture 동일
- 실제 호출: 256회 (graph 169 + judge 87), 상한 320
- 산출물: `results/round2/heldout/`
- LangSmith: project `helkki`, experiment `multi-agent-v2` / `baseline-single-agent-v1` /
  `baseline-single-llm-v1`. LLM span은 이 실행에서 **꺼져 있었다**(`llm_agents_tracing_enabled`
  기본값). 따라서 latency는 2차 pilot과 같은 조건에서 측정됐다.

## 1. 사전 등록 기준 판정

`ROUND2_IMPROVEMENT_PLAN` 3절에서 결과를 보기 전에 고정한 기준이다. 기준은 수정하지 않았다.

| 지표 | 통과 기준 | 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| Multi − Single RAG **Human** mean | ≥ +0.20 | 미측정 | **미판정** |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi P95 latency | ≤ 30초 | **48.813초** | **미달** |
| conflict/complex case plan rate | ≥ Single RAG | **complex 0.667 / conflict 0.600** | **미달** |

token 기준에 대한 주석: 사전 등록 문구는 "v1 Multi 대비"이고 v1은 튜닝 데이터셋에서
측정됐다. 따라서 판정에 쓴 26.9786%는 **같은 데이터셋에서의 대응 측정**
(`ROUND2_IMPROVEMENT_PLAN` 7절)이다. held-out에서의 1회 실행당 20,386 토큰을 v1의 26,646과
직접 비교하면 23.49% 감소지만, 데이터셋과 카탈로그가 달라 사전 등록된 비교가 아니므로
판정 근거로 쓰지 않았다. 두 수치 모두 기록한다.

**판정: 2개 기준 미달, 1개 미판정. 따라서 "Multi-Agent가 더 유효하다"는 결론을 내리지 않는다.**
`ROUND2_IMPROVEMENT_PLAN` 6절의 분기 중 **"Single RAG가 동등 이상"** 에 해당한다.

## 2. 측정값

| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---:|---:|---:|
| 실행 수 | 29 | 29 | 29 |
| Constraint Satisfaction | 1.000 | 1.000 | 1.000 |
| Safety Compliance | 1.000 | 1.000 | 1.000 |
| Critical 실패 | 0 | 0 | 0 |
| Workflow Completion | 1.000 | 1.000 | 1.000 |
| Plan Delivery Rate (fallback 포함) | 1.000 | 1.000 | 1.000 |
| **LLM Plan Rate** (fallback 제외) | 0.0345 | **0.8966** | 0.7586 |
| Structured Output Success | 0.1724 | **1.000** | 0.8276 |
| Judge 평균 (blind) | 2.9138 | **3.7011** | 3.6552 |
| ├ PERSONALIZATION | 3.6897 | **4.3103** | 3.9655 |
| ├ FEASIBILITY | 3.2414 | 3.6552 | **3.8276** |
| └ OVERALL_QUALITY | 3.1034 | 3.7241 | 3.7241 |
| P50 latency | 13.796초 | 22.047초 | 32.390초 |
| P95 latency | 15.703초 | 48.563초 | 48.813초 |
| 1회 실행당 호출 | 1.00 | 1.00 | 3.83 |
| 1회 실행당 토큰 | 4,154 | 8,808 | **20,386** |
| fallback | 28 | 3 | 7 |
| repair | 0 | — | **0** |

category별 LLM plan rate:

| category | 실행 | A | B | C |
|---|---:|---:|---:|---:|
| simple | 4 | 0.000 | 0.750 | 0.750 |
| moderate | 8 | 0.000 | 1.000 | 1.000 |
| complex | 9 | 0.111 | **0.889** | 0.667 |
| conflict | 5 | 0.000 | **0.800** | 0.600 |
| failure_case | 3 | 0.000 | **1.000** | 0.667 |

## 3. Multi-Agent fallback 7건의 원인

이 실행의 산출물은 fallback이 **일어났다는 사실만** 기록하고 이유를 남기지 않았다.
원인은 LangSmith trace에서 복원했다(root run을 시작 순서로 정렬한 뒤, 기록된
`wall_clock_ms`와 대조해 최대 32ms 오차로 case 대응을 검증했다).

| case | category | 실패 코드 | 해석 |
|---|---|---|---|
| SQ-HELD-003 | simple | `V3_TRAINING_NOT_READY` | Training이 READY 제안을 내지 못함 |
| SQ-HELD-013 | complex | `V3_TRAINING_NOT_READY` | 〃 |
| SQ-HELD-015 | complex | `V3_TRAINING_NOT_READY` | 〃 |
| SQ-HELD-017 | complex | `V3_TRAINING_NOT_READY` | 〃 |
| SQ-HELD-024 | conflict | `LLM_AGENT_DOMAIN_INVALID` | Training 출력이 도메인 검증 실패 |
| SQ-HELD-033 | failure_case | `V3_COMPILATION_FAILED` | Coordinator PlanSpec이 컴파일 실패 |
| SQ-HELD-023 | conflict | `PLAN_EXERCISE_FAMILY_REPEATED` (NON_REPAIRABLE) | 무결성 검증 탈락 |

**7건 중 5건이 Training agent 단독 실패다.** 나머지 2건은 Coordinator 산출물이 결정적
게이트(compiler / integrity validator)에서 탈락한 경우이고, Single-Agent baseline도 같은
게이트를 통과해야 하므로 비교는 공정하다.

세 가지를 구분해서 봐야 한다.

- **이것은 D-5의 재발이 아니다.** R2-1(ADR-0021)은 advisory의 `NEEDS_INPUT`을 통과시키는
  변경이었고, 그 부분은 의도대로 동작했다 — 7건 모두에서 Recovery/Feasibility는 READY였고
  advisory 때문에 막힌 건은 0건이다. 막힌 것은 Training 자신이다.
- **ADR-0021은 Training READY 요구를 유지하기로 한 결정이다.** Training은 유일하게 운동
  계획을 소유하는 agent이므로(ADR-0015), 그 실패를 통과시키면 계획 없는 계획이 된다.
  현재 동작은 설계대로이며 서비스 결함이 아니다. 사용자에게는 결정적 fallback 계획이
  전달됐고 안전 위반은 없었다.
- **그러나 가용성 비용은 실측됐다.** 같은 입력에서 Single-Agent RAG는 1회 호출로 29건 중
  26건(0.897) 계획을 냈고, Multi-Agent는 3.83회 호출로 22건(0.759)을 냈다. 전문화를 위해
  더 쓴 호출이 가용성을 **낮췄다**.

### repair 라운드는 한 번도 동작하지 않았다

29건 전체에서 `repair_attempts = 0`이다. SQ-HELD-023의 위반
`PLAN_EXERCISE_FAMILY_REPEATED`는 validator가 `NON_REPAIRABLE`로 분류하므로 repair 노드가
호출되지 않는다. 즉 held-out 전체에서 repair 라운드의 기여는 0이며, PHASE 6이 기록한
"C에 유리한 비대칭"(baseline에는 repair가 없음)은 이번 실행에서 실제 효과가 없었다.

## 4. Judge 결과 해석의 한계

Judge 평균은 B 3.7011, C 3.6552로 **C가 낮다**. 다만 Judge는 사전 등록에서 보조 지표이고,
PHASE 7에서 이미 신뢰 한계를 측정했다: blind pairwise에서 position bias 30.77%,
일치율 61.54%였다. **이 차이(−0.046)는 그 잡음 폭보다 작으므로 "B가 더 낫다"는 근거로도
쓸 수 없다.** 단방향으로만 말할 수 있다: Judge는 C의 우월성을 지지하지 않는다.

기준 4(Human mean +0.20 이상)는 **여전히 미측정**이며, Judge 점수로 대체하지 않는다.
PM과 개발리드의 독립 blind 평가가 남아 있다.

## 5. latency 기준 미달

Multi P95 48.813초는 기준 30초를 크게 넘고, **P50 32.390초도 이미 기준을 넘는다.**
2차 pilot의 P95 26.500초와 비교하면 배로 늘었다. 조건 차이는 데이터셋과 카탈로그다:
pilot은 합성 카탈로그 18종, held-out은 배포 카탈로그에서 구성한 운영 크기 pool이다.

다만 **Single-Agent RAG의 P95도 48.563초로 사실상 같다.** 즉 P95 꼬리는 architecture
고유 비용이 아니라 이 실행 조건에서 양쪽이 공유한 요인이다. architecture에 귀속되는 비용은
중앙값 쪽이다(P50 32.4초 대 22.0초, +47%).

LLM span export는 이 실행에서 꺼져 있었으므로 tracing overhead는 원인이 아니다.

## 6. 하네스 결함 (서비스 결함 아님)

**`CaseEvaluation`이 fallback 이유를 기록하지 않았다.** `used_fallback`만 직렬화되어 있어
7건의 원인을 사후에 trace로 복원해야 했고, tracing이 꺼진 실행이었다면 복원 자체가
불가능했을 것이다. `failure_codes`와 `violation_codes`를 `CaseEvaluation`에 추가했고
(`test_a_fallback_records_why_it_happened`), 이 실행의 수치는 재계산하지 않았다.

**blocked case가 유료 비교에서 제외된다.** `budget.planning_cases`가 provider를 호출하지
않는 case를 걸러내는 것은 예산상 옳지만, 그 결과 safety 층(4건)이 비교의 safety 수치에
포함되지 않는다. 결정적·pre-LLM 경로이므로 무료로 검증할 수 있고,
`test_a_blocked_case_is_stopped_before_any_provider_call`로 4건 모두 계획 미생성·정확한
종료 상태·provider 호출 0회를 고정했다.

**`script_summary`는 유료 실행에서 의미가 없다.** 실 provider 실행에도 기본 Script가
붙으므로 산출물에 `T=COMPLIANT,...`가 찍히지만 이는 측정된 사실이 아니다. 이번에는 해석에
쓰지 않았다.

## 7. 결론

- **안전성은 held-out에서도 유지된다.** 33건 전체 safety 1.000, critical 0건, 계획 전달률
  1.000. 배포 카탈로그와 배포 안전 규칙으로 구성한, 튜닝에 쓰지 않은 데이터에서의 결과다.
- **Multi-Agent의 우월성은 입증되지 않았다.** 사전 등록 기준 2개 미달(P95 latency,
  conflict/complex plan rate), 1개 미판정(Human). 1차 결론이 held-out에서 반복됐다.
- **Single-Agent + RAG가 가용성·구조화 출력·비용에서 앞선다.** 계획 생성률 0.897 대 0.759,
  구조화 출력 1.000 대 0.828, 토큰 8,808 대 20,386(2.31배), 호출 1.00 대 3.83.
- **후속은 `ROUND2_IMPROVEMENT_PLAN` 6절의 마지막 분기다**: multi-agent 단순화 또는 조건부
  호출을 별도 ADR로 검토한다. 이번 데이터가 가리키는 지점은 Training의 READY 실패율
  (29건 중 5건, 17.2%)이며, 여기에는 Single-Agent 경로가 같은 입력에서 성공했다는 대조가
  있다.
- 남은 게이트: 독립 blind Human 평가(6), Judge calibration(7). **둘 다 사람이 필요하며
  이 실행으로 대체되지 않는다.**
